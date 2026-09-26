"""committee-eval: how good or bad was one finished committee review?

A second playbook over the committee's own record. For one finished committee
run it gives six scores, each backed by evidence the master checked: three from
an LLM judge whose every quote must verify against a pinned snapshot
(verdict_grounded, edits_address_concerns, concern_coverage), and three computed
straight from the record (efficiency, concision, verdict_consistency). It reads
the target strictly read-only, and it never gates or feeds the accept/reject
ruling.

Every dimension carries a version, so a score is only ever compared with scores
taken under the same definition. The voice rules and the one word counter live
in playbooks/committee/voice.py; this module imports only ``RULES`` and
``measure`` from it, so there is never a second definition to drift.

Stdlib-only.
"""
from __future__ import annotations

import difflib
import errno
import hashlib
import json
import os
import re
import sqlite3
import statistics
import sys
import tempfile
import time
import urllib.parse
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from engine import config
from engine import playbook as _playbook
from engine.models import Driver, Finding, Reduction, Run, Ticket
from playbooks.committee import cast, thread, turnblock
from playbooks.committee.playbook import _SIMULATION
from playbooks.committee.voice import RULES, measure

# D5 order. A loop that changes a dimension's definition, bands or inputs bumps its n.
DIMENSIONS: dict[str, str] = {
    "verdict_grounded": "verdict_grounded@1",
    "edits_address_concerns": "edits_address_concerns@1",
    "concern_coverage": "concern_coverage@1",
    "efficiency": "efficiency@1",
    "concision": "concision@1",
    "verdict_consistency": "verdict_consistency@1",
}
JUDGE_DIMS = ("verdict_grounded", "edits_address_concerns", "concern_coverage")
DETERMINISTIC_DIMS = ("efficiency", "concision", "verdict_consistency")

MIN_ANCHORS = 2  # anchored targets a judge dimension needs before it can read calibrated (D8)
QUOTE_MAX = 300  # a judge quote is clipped to this many characters before it is verified (C3)
# A shorter quote verifies nothing: "." or "e" is a substring of every text (D6).
QUOTE_MIN_WORDS, QUOTE_MIN_CHARS = 3, 12
EVIDENCE_MAX = 5  # evidence items kept per judge dimension; extras are dropped (C3)
DETAIL_MAX = 20  # concerns and absent_stakeholders kept each in concern_coverage.detail (C3)
RATIONALE_MAX = 1000  # a judge rationale is clipped to this many characters (C3)
FENCE_TAG = "hermes-eval"

VERBATIM = (
    "every quote is verbatim and contiguous from the place it cites "
    "(no ellipses, no paraphrase)"
)

# The D5 judge anchors, written to inputs/rubric.md under the version lines.
# D5's closing note on run-9's expected absent stakeholders is left out: it is
# an acceptance note about one run, and telling the judge would bias every run.
RUBRIC = "\n".join((
    "verdict_grounded",
    "5: every claim in the chair prose traces to a turn or to the document, and the "
    "verdict follows from the arguments.",
    "3: mostly grounded, with some unsupported claims.",
    "1: asserts things nobody said, or contradicts the thread.",
    "",
    "edits_address_concerns",
    "5: each edit does what its delegation asked and resolves the concern behind it.",
    "3: partial.",
    "1: cosmetic, partial or unrelated edits.",
    "Read the per-edit snapshots under inputs/doc/ when present; cite the delegating "
    'owner turn, the junior_ic report, or the edited text itself (`where:"original"|"revised"`, C3).',
    "",
    "concern_coverage",
    "5: every seated member's main concerns were answered by the owner or by an edit, "
    "and the thread names no needed stakeholder missing from the room.",
    "1: major concerns went unanswered, or a missing function is named repeatedly.",
    "Concerns come from each member's own turns, never from persona config. The judge "
    "also gets `seats`, `unanswered_reviewer_turns` and `outside_room_mentions`.",
    "",
    f"Evidence: {VERBATIM}.",
))

_WALL_WORDS = 120  # C8: a wall is a paragraph over 120 words; the one threshold (D11 imports only RULES and measure)


def words(text: str) -> int:
    """The one word count, voice's, so eval never grows a second counter."""
    return measure(text)["words"]


def _num(row: object, key: str) -> int | float:
    """A measure value, or 0 when the row or the value is not a number (reduce never raises)."""
    value = row.get(key) if isinstance(row, dict) else None
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def voice_shares(rows: list[dict]) -> dict:
    """C8's four shares over the measured population P, one measure dict per turn.

    n = |P|. Each share is rounded to 4 dp, and every share is None when n == 0.
    """
    n = len(rows)
    if n == 0:
        return {"n": 0, "pointer_share": None, "walls_share": None,
                "example_share": None, "filler_per_turn": None}
    return {
        "n": n,
        "pointer_share": round(sum(_num(r, "pointers") >= 1 for r in rows) / n, 4),
        "walls_share": round(sum(_num(r, "longest_paragraph_words") > _WALL_WORDS for r in rows) / n, 4),
        "example_share": round(sum(_num(r, "examples") >= 1 for r in rows) / n, 4),
        "filler_per_turn": round(sum(_num(r, "filler_hits") for r in rows) / n, 4),
    }


def dimension_versions(rules: tuple[str, ...] = RULES) -> dict[str, str]:
    """DIMENSIONS, with concision tied to the voice rules it scores against.

    concision gains "+" and the first 8 hex of sha256 over the rules, so a rules
    swap moves its version and an old concision score can never silently compare.
    """
    digest = hashlib.sha256("\n".join(rules).encode()).hexdigest()[:8]
    return {**DIMENSIONS, "concision": DIMENSIONS["concision"] + "+" + digest}


def rubric_version(versions: dict[str, str]) -> str:
    """One id for a whole set of dimension versions: "r" and 8 hex."""
    return "r" + hashlib.sha256(json.dumps(versions, sort_keys=True).encode()).hexdigest()[:8]


# --- the target: read strictly read-only (D2) and parsed (D3) -----------------

ENV_RUN = "HERMES_COMMITTEE_EVAL_RUN"
ENV_HOME = "HERMES_COMMITTEE_EVAL_HOME"
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# thread.md: the only entry boundaries are thread.py's own turn and decision headings.
_TURN_HEADING = re.compile(r"^## turn (\d{2,}) — (.+) \((\w+)\)$")
_DECISION_HEADING = re.compile(r"^## decision — .+$")
_LABEL = re.compile(r"^(?:\*\*)?(Charge|Artifact|Committee):(?:\*\*)?\s*(.*)$")
_SEAT = re.compile(r"^- (\w+) — (.+)$")
# The master's footer under the chair's words (playbook._reduce_decision).
_FOOTER = re.compile(r"^- (re-check of |dropped_)")


def eval_home() -> str:
    """This process's HERMES_HOME, resolved: the eval run and all it writes live here."""
    return os.path.realpath(config.resolve_home())


def source_home(environ: Mapping[str, str] = os.environ) -> str:
    """The target's home, resolved: HERMES_COMMITTEE_EVAL_HOME, else the eval home."""
    raw = environ.get(ENV_HOME)
    return os.path.realpath(raw) if raw else eval_home()


def connect_ro(home: str) -> sqlite3.Connection | None:
    """``<home>/queue.db`` opened read-only, or None when it is not a regular file.

    The D2 URI with ``mode=ro``: never ``migrate.connect``, which creates and
    chmods. queue.db itself is never written, but on a WAL database SQLite
    may create its ``-wal`` (empty) and ``-shm`` beside it.

    Raises:
        sqlite3.Error: queue.db exists but SQLite cannot open it.
    """
    db = f"{home}/queue.db"
    if not os.path.isfile(db):
        return None
    conn = sqlite3.connect("file:" + urllib.parse.quote(db) + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _reductions(conn: sqlite3.Connection, run_id: str) -> list[tuple[str, str, object]]:
    """Every reduction of the run by ascending id: (kind, review_state, json or None)."""
    rows = []
    for row in conn.execute(
        "SELECT kind, review_state, json FROM reductions WHERE run_id = ? ORDER BY id",
        (run_id,),
    ):
        try:
            doc = json.loads(row["json"])
        except (TypeError, ValueError, RecursionError):
            doc = None  # malformed json is skipped, never raised
        rows.append((row["kind"], row["review_state"], doc))
    return rows


def _decision(rows: list[tuple[str, str, object]]) -> tuple[dict, str]:
    """The latest decision reduction's json, the only one read, and its review_state."""
    for kind, review_state, doc in reversed(rows):
        if kind == "decision":
            return (doc if isinstance(doc, dict) else {}), review_state
    return {}, ""


def _legacy(rows: list[tuple[str, str, object]]) -> bool:
    """D2: a turn reduction without ``body`` marks a run read through thread.md."""
    return any(kind == "turn" and isinstance(doc, dict) and "body" not in doc
               for kind, _, doc in rows)


def validate_target(home: str, run_id: str | None) -> str | None:
    """None when (home, run_id) is an evaluable committee run, else the one reason why not.

    Evaluable (D2): queue.db exists, the id is well formed, the run exists and
    is a committee run, its latest decision was delivered, and a legacy run
    still has its thread.md. runs.state and the ruling never gate (Q1/R1). A
    queue.db SQLite cannot read is "unreadable", with SQLite's reason. Never
    raises; creates nothing.
    """
    if not run_id:
        return f"{ENV_RUN} is not set"
    try:
        conn = connect_ro(home)
        if conn is None:
            return f"no queue.db in {home}"
        with closing(conn):
            if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
                return f"bad run id: {run_id}"
            row = conn.execute("SELECT playbook FROM runs WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                return f"run not found: {run_id}"
            if row["playbook"] != "committee":
                return f"not a committee run: {run_id} ({row['playbook']})"
            rows = _reductions(conn, run_id)
    except sqlite3.Error as exc:
        return f"queue.db unreadable in {home}: {exc}"
    if _decision(rows)[0].get("delivered") is not True:
        return f"no delivered decision: {run_id}"
    if _legacy(rows) and thread.read_regular(Path(home) / "runs" / run_id / "thread.md") is None:
        return "legacy run without thread.md"
    return None


@dataclass
class Target:
    """One committee run as the eval reads it. Built by ``load_target``, never written back."""

    # the run
    home: str
    run_id: str
    created_at: float
    state: str
    review_state: str
    legacy: bool
    # the reductions
    turns: dict[int, dict]  # the winning turn json per number, keys ascending
    duplicate_turns: int
    takes: int
    other_kinds: dict[str, int]
    decision: dict
    # the transcript
    thread_path: str
    thread_raw: bytes | None  # the bytes read once: inputs/thread.md copies these, never a re-read
    thread_text: str | None
    thread: dict | None
    # the document
    artifact: str
    original_path: str | None
    original: bytes | None
    original_source: str  # "snapshot" or "live"
    revised_path: str
    revised: bytes | None
    steps: list[dict]  # {"turn", "key", "path", "data"} per junior_ic turn, ascending
    # the work
    attempts: list[dict]  # {"id", "started_at", "ended_at", "outcome"}, ascending id
    traces: dict[int, bytes | None]


def _lines(text: str) -> list[str]:
    """``text``'s lines, ended by "\\n" only (a CRLF counts once), with no trailing "".

    Never ``str.splitlines``: it also ends a line at a form feed, U+0085 or
    U+2028, so one such character quoted in a turn would shift every later
    line number by one.
    """
    lines = text.replace("\r\n", "\n").split("\n")
    return lines[:-1] if lines[-1] == "" else lines


def parse_thread(text: str) -> dict:
    """thread.md as D3 reads it: header, labels, the Committee roster, turn and decision entries.

    The header is every line before the first ``## `` line. Entry boundaries are
    only thread.py's ``## turn NN — Name (role)`` and ``## decision — …``
    headings, so any other ``## `` line after the first boundary is body. Lines
    between the header and the first boundary (selection, 1:1 plans) belong to
    no entry. Lines are 1-based and inclusive over ``_lines(text)``: an entry
    runs from its heading to the line before the next boundary. A turn number
    written twice keeps its last entry.
    """
    lines = _lines(text) if isinstance(text, str) else []
    first = next((i for i, line in enumerate(lines) if line.startswith("## ")), len(lines))
    labels: dict[str, str] = {}
    seats: list[str] = []
    in_committee = False
    for line in lines[:first]:
        label = _LABEL.match(line)
        if label:
            labels.setdefault(label.group(1), label.group(2).strip())
            in_committee = label.group(1) == "Committee"
        elif in_committee and line.strip():
            if not line.startswith("- "):
                in_committee = False  # e.g. "Seat library:" ends the block
            else:
                seat = _SEAT.match(line)
                if seat and seat.group(1) not in seats:
                    seats.append(seat.group(1))
    heads: list[tuple[int, int | None, str | None]] = []  # (index, turn, role); turn None = decision
    for i, line in enumerate(lines):
        turn = _TURN_HEADING.match(line)
        if turn:
            heads.append((i, int(turn.group(1)), turn.group(3)))
        elif _DECISION_HEADING.match(line):
            heads.append((i, None, None))
    turns: dict[int, dict] = {}
    decision = None
    for k, (i, n, role) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        entry = {"body": "\n".join(lines[i + 1:end]).strip(), "line_start": i + 1, "line_end": end}
        if n is None:
            decision = entry
        else:
            turns[n] = {"role": role, **entry}
    return {
        "header": {"text": "\n".join(lines[:first]),
                   "line_start": 1 if first else None, "line_end": first or None},
        "labels": labels,
        "roster": seats,
        "turns": dict(sorted(turns.items())),
        "decision": decision,
    }


def _resolve(home: str, path: object) -> str:
    """An artifact path as recorded; a relative one is taken against the source home."""
    if not isinstance(path, str) or not path.strip():
        return ""
    path = path.strip()
    return path if os.path.isabs(path) else os.path.join(home, path)


def load_target(home: str, run_id: str) -> Target:
    """Read one evaluable run strictly read-only: rows over mode=ro, files by plain joins.

    Nothing is created on the source home or the eval home: no thread.path,
    revised_path or run_file, no config.state_dir, no migrate.connect, no
    trace_path (D2). Every file goes through ``thread.read_regular``. Malformed
    reduction json never raises; a turn reduction without an int ``turn`` is
    skipped. Text is decoded utf-8 with errors="replace" (G11).

    Raises:
        ValueError: the target is not evaluable (``validate_target``'s reason).
    """
    reason = validate_target(home, run_id)
    conn = None if reason else connect_ro(home)
    if conn is None:
        raise ValueError(reason or f"no queue.db in {home}")
    with closing(conn):
        run = conn.execute("SELECT created_at, state FROM runs WHERE id = ?", (run_id,)).fetchone()
        rows = _reductions(conn, run_id)
        attempts = [dict(a) for a in conn.execute(
            "SELECT a.id, a.started_at, a.ended_at, a.outcome FROM attempts a"
            " JOIN tickets t ON a.ticket_id=t.id WHERE t.run_id=? ORDER BY a.id", (run_id,))]

    turns: dict[int, dict] = {}
    turn_rows = takes = 0
    other: dict[str, int] = {}
    for kind, _, doc in rows:
        n = doc.get("turn") if isinstance(doc, dict) else None
        if kind == "turn" and isinstance(n, int) and not isinstance(n, bool):
            turn_rows += 1
            turns[n] = doc  # the last by id per number wins
        elif kind == "take":
            takes += 1
        elif kind not in ("turn", "decision"):
            other[kind] = other.get(kind, 0) + 1
    turns = dict(sorted(turns.items()))
    decision, review_state = _decision(rows)

    run_dir = Path(home) / "runs" / run_id
    raw = thread.read_regular(run_dir / "thread.md")
    text = None if raw is None else raw.decode("utf-8", errors="replace")
    parsed = None if text is None else parse_thread(text)
    recorded = [_resolve(home, d.get("artifact")) for _, _, d in rows if isinstance(d, dict)]
    artifact = next((a for a in reversed(recorded) if a), "")
    if not artifact and parsed is not None:
        artifact = _resolve(home, parsed["labels"].get("Artifact"))

    snapshot = run_dir / thread.snapshot_key(artifact, None)
    original = thread.read_regular(snapshot)
    if original is not None:
        original_path, original_source = str(snapshot), "snapshot"
    else:  # a live original may have drifted since the run; nothing can tell
        original_path, original_source = artifact or None, "live"
        original = thread.read_regular(artifact) if artifact else None
    name = Path(artifact).name
    revised_path = str(run_dir / "revised" / name) if name not in ("", "..") else ""
    steps = []
    for n, doc in turns.items():
        if doc.get("role") == cast.JUNIOR:
            key = thread.snapshot_key(artifact, n)
            steps.append({"turn": n, "key": key, "path": str(run_dir / key),
                          "data": thread.read_regular(run_dir / key)})

    return Target(
        home=home, run_id=run_id, created_at=float(run["created_at"]), state=run["state"],
        review_state=review_state, legacy=_legacy(rows),
        turns=turns, duplicate_turns=turn_rows - len(turns),
        takes=takes, other_kinds=other, decision=decision,
        thread_path=str(run_dir / "thread.md"), thread_raw=raw, thread_text=text, thread=parsed,
        artifact=artifact, original_path=original_path, original=original,
        original_source=original_source, revised_path=revised_path,
        revised=thread.read_regular(revised_path) if revised_path else None, steps=steps,
        attempts=attempts,
        traces={a["id"]: thread.read_regular(run_dir / "traces" / f"{a['id']}.jsonl")
                for a in attempts},
    )


def chair_prose(decision: dict) -> str:
    """The chair's own words (D3): the decision ``body``, else the verdict minus the footer.

    The footer is what ``_reduce_decision`` appends: every ``- re-check of …``
    and ``- dropped_…`` line and the simulation paragraph. Without the strip,
    the footer's APPLIED lines would satisfy any count check. Never raises.
    """
    if not isinstance(decision, dict):
        return ""
    text = decision.get("body")
    if isinstance(text, str):
        return text
    verdict = decision.get("verdict")
    if not isinstance(verdict, str):
        return ""
    kept = [line for line in _lines(verdict.replace(_SIMULATION, ""))
            if not _FOOTER.match(line)]
    return "\n".join(kept).strip()


def body(target: Target, n: int) -> str:
    """Turn n's prose: its reduction ``body``, else (legacy) its thread.md entry, else ""."""
    text = target.turns.get(n, {}).get("body")
    if isinstance(text, str):
        return text
    entry = (target.thread or {}).get("turns", {}).get(n)
    return entry["body"] if entry else ""


def roster(target: Target) -> list[str]:
    """Every seat: the header's Committee block, then turn roles by first appearance (D3)."""
    seats = list(target.thread["roster"]) if target.thread else []
    for doc in target.turns.values():
        role = doc.get("role")
        if isinstance(role, str) and role not in seats:
            seats.append(role)
    return seats


def reviewers(target: Target) -> list[str]:
    """The roster minus the owner and the junior IC, in roster order."""
    return [seat for seat in roster(target) if seat not in (cast.OWNER, cast.JUNIOR)]


def unanswered_reviewer_turns(target: Target) -> list[int]:
    """Delivered reviewer turns no delivered owner turn answered, ascending (D3).

    With doc-diff's ``answers_turn`` on the owner turns (present, even null,
    means recorded), turn N is answered iff a delivered owner turn has
    ``answers_turn == N``. Without it, N is answered iff the first later turn
    that is not the junior IC's is a delivered owner turn. Order-based, never
    N+1 arithmetic, so interleaved edits and gaps in the numbering are fine.
    """
    seats = set(reviewers(target))
    numbers = list(target.turns)
    owners = [t for t in target.turns.values() if t.get("role") == cast.OWNER]
    recorded = any("answers_turn" in t for t in owners)
    answered = {t["answers_turn"] for t in owners if t.get("delivered")
                and isinstance(t.get("answers_turn"), int)
                and not isinstance(t.get("answers_turn"), bool)}
    out = []
    for i, n in enumerate(numbers):
        doc = target.turns[n]
        role = doc.get("role")
        if not isinstance(role, str) or role not in seats or not doc.get("delivered"):
            continue
        if recorded:
            ok = n in answered
        else:
            nxt = next((target.turns[m] for m in numbers[i + 1:]
                        if target.turns[m].get("role") != cast.JUNIOR), None)
            ok = nxt is not None and nxt.get("role") == cast.OWNER and bool(nxt.get("delivered"))
        if not ok:
            out.append(n)
    return out


# --- the record: what happened and what it cost (C5 record half, G4) ----------

OUTSIDE_ROOM = re.compile(r"(?i)\b(outside|not in) this room\b")

# eval's token key <- (the cost-state's modelUsage key, the transcript's message.usage key) (G4)
TOKEN_KEYS = {
    "input": ("inputTokens", "input_tokens"),
    "output": ("outputTokens", "output_tokens"),
    "cache_creation": ("cacheCreationInputTokens", "cache_creation_input_tokens"),
    "cache_read": ("cacheReadInputTokens", "cache_read_input_tokens"),
}


def _is_number(value: object) -> bool:
    """An int or a float, never a bool (JSON ``true`` is not a cost)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def trace_totals(traces: list[bytes | str | None]) -> dict:
    """Cost and tokens over trace files' contents, one entry per expected trace (G4).

    Per trace, the LAST cost-state line decides its cost: its numeric
    ``totalCostUSD``, or none when it says ``hasUnknownModelCost``. Tokens are
    that trace's last cost-state ``modelUsage``, summed over models: Claude
    Code's own totals, which match what it bills. A trace without modelUsage
    (legacy) falls back to its transcript, each ``message.id``'s usage once from
    its last line, which misses part of the bill. ``tokens_source`` says which:
    "modelUsage", "transcript", "mixed", or null when no trace was found.
    ``None`` is a trace that does not exist; a str (``engine.trace.read``) is
    read as its utf-8 bytes, so only ``\\n``/``\\r`` end a line. ``cost_usd`` is
    null unless there is at least one trace and every one has a cost; ``tokens``
    is null when no trace was found. Malformed lines are skipped. Never raises.
    judge.reduce reuses this for the judge's own trace (Task 9).
    """
    tokens = dict.fromkeys(TOKEN_KEYS, 0)
    cost = 0.0
    found = with_cost = 0
    sources = set()
    for data in traces:
        if isinstance(data, str):
            data = data.encode("utf-8", "replace")
        if not isinstance(data, bytes):
            continue
        found += 1
        last_cost = model_usage = None
        usage: dict[str, dict] = {}
        for raw in data.splitlines():
            try:
                line = json.loads(raw)
            except (ValueError, RecursionError):
                continue
            if not isinstance(line, dict):
                continue
            if line.get("type") == "cost-state":
                if line.get("hasUnknownModelCost") is True:
                    last_cost = None
                elif _is_number(line.get("totalCostUSD")):
                    last_cost = line["totalCostUSD"]
                if isinstance(line.get("modelUsage"), dict):
                    model_usage = line["modelUsage"]
            elif line.get("type") == "assistant":
                msg = line.get("message")
                if (isinstance(msg, dict) and isinstance(msg.get("id"), str)
                        and isinstance(msg.get("usage"), dict)):
                    usage[msg["id"]] = msg["usage"]
        if last_cost is not None:
            with_cost += 1
            cost += last_cost
        source, pick, rows = (("modelUsage", 0, model_usage.values()) if model_usage is not None
                              else ("transcript", 1, usage.values()))
        sources.add(source)
        for counts in rows:
            if not isinstance(counts, dict):
                continue
            for key, names in TOKEN_KEYS.items():
                value = counts.get(names[pick])
                tokens[key] += value if _is_number(value) else 0
    return {
        "cost_usd": round(cost, 4) if traces and with_cost == len(traces) else None,
        "tokens": tokens if found else None,
        "tokens_source": sources.pop() if len(sources) == 1 else ("mixed" if sources else None),
        "found": found,
        "with_cost": with_cost,
    }


def _time(attempts: list[dict]) -> dict:
    """Summed and wall-clock seconds over the attempts, to 0.1 s, or null when unknown.

    An attempt is unmeasured when it lacks a numeric timestamp, or failed with
    ``ended_at == started_at``: a timeout or contract failure is recorded that
    way (engine/transport.py, queue.record_contract_fail) after running for an
    unknown time. ``unmeasured`` counts them. Any unmeasured attempt, or no
    attempt at all, makes both times null, never a partial sum that would let a
    failing run look cheaper (the null rule cost follows).
    """
    spans = [(a.get("started_at"), a.get("ended_at")) for a in attempts]
    unmeasured = sum(1 for (start, end), a in zip(spans, attempts)
                     if not (_is_number(start) and _is_number(end))
                     or (a.get("outcome") != "ok" and end == start))
    if unmeasured or not spans:
        return {"summed_attempt_s": None, "wall_clock_s": None, "unmeasured": unmeasured}
    return {
        "summed_attempt_s": round(sum(end - start for start, end in spans), 1),
        "wall_clock_s": round(max(e for _, e in spans) - min(s for s, _ in spans), 1),
        "unmeasured": 0,
    }


def _ended(target: Target) -> str:
    """D3: the decision's ``ended``, else whether the last delivered owner turn closed."""
    if target.decision.get("ended"):
        return str(target.decision["ended"])
    owners = [t for t in target.turns.values()
              if t.get("role") == cast.OWNER and t.get("delivered")]
    return "owner closed" if owners and owners[-1].get("close") else "unknown"


def _outside_room_mentions(target: Target) -> list[dict]:
    """Lines inside turn and decision entries that name someone outside the room.

    Lines before t01 (the header, selection, 1:1 plans) belong to no entry (D3).
    With no thread.md, the turn bodies and the chair prose are scanned instead,
    with ``line`` null. ``quote`` is the stripped line clipped to QUOTE_MAX.
    """
    if target.thread is None or target.thread_text is None:
        texts = [body(target, n) for n in target.turns] + [chair_prose(target.decision)]
        return [{"line": None, "quote": ln.strip()[:QUOTE_MAX]}
                for text in texts for ln in _lines(text) if OUTSIDE_ROOM.search(ln)]
    lines = _lines(target.thread_text)
    entries = list(target.thread["turns"].values())
    if target.thread.get("decision"):
        entries.append(target.thread["decision"])
    hits = sorted({
        i for e in entries
        for i in range(e["line_start"], min(e["line_end"], len(lines)) + 1)
        if OUTSIDE_ROOM.search(lines[i - 1])
    })
    return [{"line": i, "quote": lines[i - 1].strip()[:QUOTE_MAX]} for i in hits]


def compute_metrics(target: Target) -> dict:
    """C5's metrics from the loaded target: what the record says happened.

    Turns are the winning reduction per number (Task 3). Time, cost, tokens and
    traces cover every attempt on the run's tickets in ascending attempt id, so
    selection, 1:1 and retake work is in the bill. ``_prose_metrics`` adds the
    prose and document keys: words, voice, bytes and edits.
    """
    turns, decision = target.turns, target.decision
    delivered = [t for t in turns.values() if t.get("delivered")]
    owner = [t for t in delivered if t.get("role") == cast.OWNER]
    by_role: dict[str, int] = {}
    for t in turns.values():
        role = str(t.get("role"))
        by_role[role] = by_role.get(role, 0) + 1
    raw_rechecks = decision.get("rechecks")
    rechecks = ([c for c in raw_rechecks if isinstance(c, dict)]
                if isinstance(raw_rechecks, list) else [])
    dropped_floor = decision.get("dropped_floor_requests")
    seated, revs = roster(target), reviewers(target)
    spoken = [r for r in revs if any(t.get("role") == r for t in delivered)]
    caps = [t["cap"] for t in turns.values() if t.get("cap") is not None]
    totals = trace_totals([target.traces.get(a["id"]) for a in target.attempts])
    return {
        "turns": len(turns),
        "turns_by_role": by_role,
        "undelivered_turns": len(turns) - len(delivered),
        "owner_turns_delivered": len(owner),
        "delegations": sum(1 for t in owner if t.get("delegate") and t.get("action")),
        "rechecks": len(rechecks),
        "rechecks_verified": sum(1 for c in rechecks if c.get("verified") is True),
        "floor_requests": [{"turn": n, "role": t.get("role")}
                           for n, t in turns.items() if t.get("request_floor")],
        "errors": sum(1 for t in [*turns.values(), decision] if t.get("error") is not None),
        "ended": _ended(target),
        "cap": caps[-1] if caps else None,
        "artifact_intact": decision.get("artifact_intact"),
        "dropped": {
            "delegation": decision.get("dropped_delegation"),
            "floor_requests": list(dropped_floor) if isinstance(dropped_floor, list) else [],
        },
        "seats": {"roster": seated, "reviewers": revs, "spoken": spoken,
                  "unheard": [r for r in revs if r not in spoken]},
        "unanswered_reviewer_turns": unanswered_reviewer_turns(target),
        "outside_room_mentions": _outside_room_mentions(target),
        "time": _time(target.attempts),
        "cost_usd": totals["cost_usd"],
        "tokens": totals["tokens"],
        "tokens_source": totals["tokens_source"],
        "traces": {"expected": len(target.attempts), "found": totals["found"],
                   "with_cost": totals["with_cost"]},
        "other_kinds": dict(target.other_kinds),
        "extra_takes": target.takes + target.duplicate_turns,
        **_prose_metrics(target),
    }


# --- the prose and the document (C5 words, voice, bytes, edits; D3 per-edit) --


def changed(before: bytes, after: bytes) -> tuple[int, int]:
    """``(lines_added, lines_removed)`` from ``before`` to ``after``.

    ``difflib.unified_diff(n=0)`` over the utf-8 lines with their endings kept
    (undecodable bytes replaced), skipping its two file-header lines, then the
    lines that start ``+`` and ``-`` (D3). Kept endings make a change to a line
    ending alone count: adding a missing final newline is ``(1, 1)``.
    doc-diff's backfill strips them (``lineterm=""``) and counts that ``(0, 0)``.
    """
    a = before.decode("utf-8", "replace").splitlines(keepends=True)
    b = after.decode("utf-8", "replace").splitlines(keepends=True)
    added = removed = 0
    for line in list(difflib.unified_diff(a, b, n=0))[2:]:
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed


def _prose_population(target: Target) -> list[int]:
    """Voice's population P (C8), ascending: the delivered reviewer and owner turns.

    A turn whose reduction says ``voice: null`` (voice's undelivered or
    signals-only take) is unmeasured and left out, so the voice shares and the
    reviewer/owner median always read the same turns.
    """
    return [n for n in sorted(target.turns)
            if target.turns[n].get("delivered") and target.turns[n].get("role") != cast.JUNIOR
            and not ("voice" in target.turns[n] and target.turns[n]["voice"] is None)]


def _chair_entry(target: Target) -> str:
    """The full decision text: the thread entry on a legacy run, else the verdict."""
    entry = (target.thread or {}).get("decision") if target.legacy else None
    if isinstance(entry, dict) and isinstance(entry.get("body"), str):
        return entry["body"]
    verdict = target.decision.get("verdict")
    return verdict if isinstance(verdict, str) else ""


def _prose_words(target: Target) -> dict:
    """``words``: all delivered prose plus the decision entry, the reviewer/owner median, the chair."""
    delivered = [n for n in sorted(target.turns) if target.turns[n].get("delivered")]
    counts = [words(body(target, n)) for n in _prose_population(target)]
    entry = _chair_entry(target)
    return {
        "prose_total": sum(words(body(target, n)) for n in delivered) + words(entry),
        # statistics.median raises on an empty list: no reviewer or owner prose is null
        "median_reviewer_owner": float(statistics.median(counts)) if counts else None,
        "chair_entry": words(entry),
        "chair_prose": words(chair_prose(target.decision)),
    }


def _prose_voice(target: Target) -> dict:
    """``voice``: C8's shares over P (D11).

    A reduction's ``voice`` dict is used verbatim; any other turn in P is
    measured from its body (``voice: null`` turns are not in P).
    """
    rows = []
    for n in _prose_population(target):
        rec = target.turns[n]
        recorded = rec.get("voice")
        rows.append(recorded if isinstance(recorded, dict)
                    else measure(body(target, n), rec.get("role") or "reviewer"))
    return voice_shares(rows)


def _edit_counts(target: Target) -> dict:
    """``edits``: per-edit counts from the doc/ snapshots, and the whole-run total (D3).

    Step N is diffed against step N-1's snapshot, and the first step against
    doc/00-original. A step whose file or predecessor is unreadable gets null
    counts. Without the original snapshot there is no per-edit history
    ("unavailable"), because the eval never replays traces. ``total`` is the
    original against the revised copy, null when either is missing.
    """
    total = None
    if target.original is not None and target.revised is not None:
        added, removed = changed(target.original, target.revised)
        total = {"lines_added": added, "lines_removed": removed}
    if target.original_source != "snapshot":
        return {"per_edit": "unavailable", "steps": [], "total": total}
    steps, before = [], target.original
    for step in target.steps:
        after = step["data"]
        added = removed = None
        if before is not None and after is not None:
            added, removed = changed(before, after)
        steps.append({"turn": step["turn"], "lines_added": added, "lines_removed": removed})
        before = after
    partial = any(s["lines_added"] is None for s in steps)
    return {"per_edit": "partial" if partial else "snapshot", "steps": steps, "total": total}


def _prose_metrics(target: Target) -> dict:
    """C5's prose and document half, merged into ``compute_metrics``."""
    return {
        "words": _prose_words(target),
        "voice": _prose_voice(target),
        "bytes": {
            "original": None if target.original is None else len(target.original),
            "revised": None if target.revised is None else len(target.revised),
        },
        "edits": _edit_counts(target),
    }


# --- D4 flags: the record's own contradictions (measure only, G1, G2) --------

# A message the junior IC got cut off, never a domain phrase ("cut off from the root").
TRUNCATION = re.compile(
    r"(?i)\b(message|delegation|action|request|instruction)s?\b.{0,40}\b(cut off|truncated|stopped at)\b")

_ONES = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
_TENS = ("ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
         "seventeen", "eighteen", "nineteen", "twenty")
# G2: one..twenty, twenty-one..twenty-nine (hyphen or space), thirty.
NUMBER_WORDS: dict[str, int] = {
    **{word: n for n, word in enumerate(_ONES, 1)},
    **{word: n for n, word in enumerate(_TENS, 10)},
    **{f"twenty{sep}{word}": 20 + n for sep in ("-", " ") for n, word in enumerate(_ONES, 1)},
    "thirty": 30,
}
# Longest first, so the alternation never settles for "twenty" in "twenty-one".
_NUMBER = r"(\d+|" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + r")"
EDIT_CLAIM = re.compile(r"(?i)\b" + _NUMBER + r" edits? (landed|applied|were made)\b")
# "Seven of the eight edits landed": the claim is the number before "of" (none: no claim).
_OF_BEFORE = re.compile(r"(?i)(?:\b" + _NUMBER + r"\s+)?\bof( the| these| all)?\s+$")
# "Two edits applied only partially" counts no landed edits.
_IN_PART_AFTER = re.compile(r"(?i)\s+(only\s+)?(partially|partly|in part)\b")
FLAG_ORDER = (
    "delegation_truncated_but_applied", "action_clipped",
    "verdict_count_mismatch", "thread_missing",
)


def _number(said: str) -> int:
    """A claimed number, digits or words."""
    said = said.lower()
    return int(said) if said.isdigit() else NUMBER_WORDS[said]


def edit_claims(text: str) -> list[int]:
    """Every count of edits ``text`` claims landed, in order (G2).

    A match right after "N of (the|these|all)" claims N, the number before
    "of"; with no number there it claims nothing. A match followed by
    "(only) partially|partly|in part" claims nothing.
    """
    claims = []
    for m in EDIT_CLAIM.finditer(text):
        if _IN_PART_AFTER.match(text, m.end()):
            continue
        of = _OF_BEFORE.search(text, 0, m.start())
        if of is None:
            claims.append(_number(m.group(1)))
        elif of.group(1):
            claims.append(_number(of.group(1)))
    return claims


def _span(target: Target, n: int | None) -> tuple[int, int] | None:
    """Turn ``n``'s (or, for None, the decision's) thread.md line range."""
    parsed = target.thread or {}
    entry = parsed.get("decision") if n is None else (parsed.get("turns") or {}).get(n)
    if not isinstance(entry, dict):
        return None
    start, end = entry.get("line_start"), entry.get("line_end")
    return (start, end) if isinstance(start, int) and isinstance(end, int) else None


def _find_line(lines: list[str] | None, span, test, after: int = 0) -> int | None:
    """The first 1-based line in ``span`` past ``after`` that passes ``test``."""
    if lines is None or span is None:
        return None
    for n in range(max(span[0], after + 1), min(span[1], len(lines)) + 1):
        if test(lines[n - 1]):
            return n
    return None


def _delegator(target: Target, n: int) -> dict | None:
    """The owner turn whose delegation junior turn ``n`` applied (D4)."""
    by = (target.turns.get(n) or {}).get("delegated_by_turn")
    if isinstance(by, int) and not isinstance(by, bool):
        return target.turns.get(by)
    earlier = [
        m for m, j in target.turns.items()
        if m < n and j.get("role") == cast.OWNER and j.get("delivered") and j.get("delegate")
    ]
    return target.turns[max(earlier)] if earlier else None


def compute_flags(target: Target, metrics: dict) -> list[dict]:
    """D4 flags, every field per G1 and every claim per G2. Never raises on odd json."""
    lines = None if target.thread_text is None else _lines(target.thread_text)
    decision = target.decision if isinstance(target.decision, dict) else {}
    flags: list[dict] = []
    for n in sorted(target.turns):
        turn = target.turns[n]
        if turn.get("role") != cast.JUNIOR or turn.get("verified") is not True:
            continue
        hit = next((ln.strip() for ln in _lines(body(target, n)) if TRUNCATION.search(ln)), None)
        if hit is None:
            continue
        line = _find_line(lines, _span(target, n), TRUNCATION.search)
        flags.append({
            "id": "delegation_truncated_but_applied", "turn": n, "line": line,
            "quote": (lines[line - 1].strip() if line else hit)[:QUOTE_MAX],
        })
    checks = decision.get("rechecks")
    for check in checks if isinstance(checks, list) else []:
        n = check.get("turn") if isinstance(check, dict) else None
        if not isinstance(n, int) or isinstance(n, bool):
            continue
        action = check.get("action") if isinstance(check.get("action"), str) else ""
        voice = (_delegator(target, n) or {}).get("voice")
        if isinstance(voice, dict):
            chars = voice.get("action_chars")
            clipped = (isinstance(chars, (int, float)) and not isinstance(chars, bool)
                       and chars > turnblock.ACTION_MAX)
        else:
            clipped = len(action) >= turnblock.ACTION_MAX
        if clipped:
            prefix = f"- re-check of turn {n:02d} "
            flags.append({
                "id": "action_clipped", "turn": n, "quote": action[-40:],
                "line": _find_line(lines, _span(target, None), lambda ln: ln.startswith(prefix)),
            })
    recorded = metrics.get("rechecks_verified")
    after = 0
    for raw in _lines(chair_prose(decision)):
        text = raw.strip()
        wrong = [n for n in edit_claims(text) if n != recorded]
        if not wrong:
            continue
        line = _find_line(lines, _span(target, None), lambda ln: text in ln, after)
        after = line or after
        quote = (lines[line - 1].strip() if line else text)[:QUOTE_MAX]
        flags.extend({
            "id": "verdict_count_mismatch", "turn": None, "line": line, "quote": quote,
            "claimed": n, "recorded": recorded,
        } for n in wrong)
    if not target.legacy and target.thread_text is None:
        flags.append({"id": "thread_missing", "turn": None, "line": None, "quote": ""})
    return sorted(flags, key=lambda f: (
        FLAG_ORDER.index(f["id"]), f["turn"] is None, f["turn"] or 0,
        f["line"] is None, f["line"] or 0,
    ))


# --- D5 deterministic dimensions, C5 headline, D7 canonical block -----------

_BANDS = ((150, 5), (300, 4), (500, 3), (800, 2))
_EFFICIENCY_KEYS = (
    "cost_usd", "time.summed_attempt_s", "turns", "cap",
    "dropped.delegation", "dropped.floor_requests",
)
_CONCISION_KEYS = (
    "words.median_reviewer_owner", "voice.walls_share", "voice.pointer_share",
    "voice.example_share", "voice.filler_per_turn",
)
_COUNTED = ("delegation_truncated_but_applied", "verdict_count_mismatch")


def _metric(metrics: dict, dotted: str):
    """``metrics`` at a dotted key, None where any step is missing."""
    value = metrics
    for key in dotted.split("."):
        value = value.get(key) if isinstance(value, dict) else None
    return value


def _scored(start: int, first: str, penalties: list[tuple], evidence: list[dict]) -> dict:
    """One deterministic dimension: ``start`` minus each hit's points, floor 1 (D5)."""
    hits = [(points, step) for points, step in penalties if points]
    score = start - sum(points for points, _ in hits)
    steps = [first] + [step for _, step in hits] + (["floor 1"] if score < 1 else [])
    return {"scorer": "deterministic", "score": max(score, 1),
            "rationale": "; ".join(steps), "evidence": evidence, "error": None}


def _metric_evidence(metrics: dict, keys: tuple[str, ...]) -> list[dict]:
    """One D5 evidence item per input the rule reads, in D5 table order."""
    return [{"turn": None, "where": "metric", "line": None,
             "quote": f"{key}={json.dumps(_metric(metrics, key))}", "verified": True}
            for key in keys]


def score_deterministic(metrics: dict, flags: list[dict]) -> dict[str, dict]:
    """efficiency, concision and verdict_consistency, each with its rationale (D5)."""
    cost, secs = _metric(metrics, "cost_usd"), _metric(metrics, "time.summed_attempt_s")
    turns, cap = _metric(metrics, "turns"), _metric(metrics, "cap")
    dropped = [name for key, name in (("dropped.delegation", "delegation"),
                                      ("dropped.floor_requests", "floor requests"))
               if _metric(metrics, key)]
    # An unknown cost or time fails its check: a run that hides its bill never scores better.
    efficiency = _scored(5, "start 5", [
        (cost is None, "cost_usd unknown: -1"),
        (cost is not None and cost > 20, f"cost_usd {cost} > 20: -1"),
        (secs is None, "summed_attempt_s unknown: -1"),
        (secs is not None and secs > 3000, f"summed_attempt_s {secs} > 3000: -1"),
        (cap is not None and turns is not None and turns >= cap, f"turns {turns} >= cap {cap}: -1"),
        (bool(dropped), f"dropped {' and '.join(dropped)}: -1"),
    ], _metric_evidence(metrics, _EFFICIENCY_KEYS))

    median = _metric(metrics, "words.median_reviewer_owner")
    if median is None:  # nothing measured is unknown, never the best band
        concision = {"scorer": "deterministic", "score": None, "rationale": "",
                     "evidence": _metric_evidence(metrics, _CONCISION_KEYS),
                     "error": "no measured reviewer/owner prose"}
    else:
        start, first = next(
            ((band, f"start {band} (median_reviewer_owner {median} <= {edge})")
             for edge, band in _BANDS if median <= edge),
            (1, f"start 1 (median_reviewer_owner {median} > 800)"),
        )
        walls, pointer, example, filler = (_metric(metrics, key) for key in _CONCISION_KEYS[1:])
        concision = _scored(start, first, [
            (walls is not None and walls > 0.25, f"walls_share {walls} > 0.25: -1"),
            (pointer is not None and pointer < 0.5, f"pointer_share {pointer} < 0.5: -1"),
            (example is not None and example < 0.5, f"example_share {example} < 0.5: -1"),
            (filler is not None and filler > 1, f"filler_per_turn {filler} > 1: -1"),
        ], _metric_evidence(metrics, _CONCISION_KEYS))

    # The chair's contradicting sentences lead, so headline, show and the view quote one.
    counted = sorted((f for f in flags if isinstance(f, dict) and f.get("id") in _COUNTED),
                     key=lambda f: f["id"] != "verdict_count_mismatch")
    mismatch = sum(f["id"] == "verdict_count_mismatch" for f in counted)
    truncated = len(counted) - mismatch
    consistency = _scored(5, "start 5", [
        (2 * mismatch, f"verdict_count_mismatch x{mismatch}: -{2 * mismatch}"),
        (min(2, truncated), f"delegation_truncated_but_applied x{truncated}: -{min(2, truncated)}"),
    ], [
        {"turn": f.get("turn"), "line": f.get("line"), "quote": f.get("quote", ""),
         "where": "decision" if f["id"] == "verdict_count_mismatch" else "turn",
         "verified": True}
        for f in counted
    ] or _metric_evidence(metrics, ("rechecks_verified",)))
    return {"efficiency": efficiency, "concision": concision, "verdict_consistency": consistency}


def headline(dimensions: dict[str, dict], judge_error: str | None) -> str:
    """C5: the weakest scored dimension, ties to D5 order, with its first verified quote."""
    scored = [
        (dim["score"], i, key) for i, key in enumerate(DIMENSIONS)
        if isinstance(dim := dimensions.get(key), dict) and isinstance(dim.get("score"), int)
    ]
    if not scored:
        return f"not scored: {judge_error}"
    score, _, key = min(scored)
    quote = next((str(item.get("quote", "")) for item in dimensions[key].get("evidence") or []
                  if isinstance(item, dict) and item.get("verified") is True), "")
    return f"weakest: {key} {score}/5: {quote[:120]}"


def canonical(obj) -> str:
    """D7's canonical JSON: sorted keys, raw unicode, no spaces."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def deterministic_block(metrics: dict, flags: list[dict], deterministic: dict) -> str:
    """The measure half of an eval, byte-identical for the same target (D7)."""
    return canonical({"metrics": metrics, "flags": flags, "deterministic": deterministic})


def measure_target(home: str, run_id: str) -> dict:
    """Load one target and compute everything measure owns: metrics, flags, scores."""
    target = load_target(home, run_id)
    metrics = compute_metrics(target)
    flags = compute_flags(target, metrics)
    return {"target": target, "metrics": metrics, "flags": flags,
            "deterministic": score_deterministic(metrics, flags)}


# --- D6: the judge's pinned snapshot, and its goal ----------------------------


def build_entries(target: Target) -> dict:
    """inputs/entries.json: every turn, the header and the chair's prose, with their lines.

    Bodies follow D3 (the reduction's ``body``; the thread entry on a legacy run),
    and the decision is chair prose only, so the re-check footer can never back a
    quote. With no thread.md every line is null and the header text is "" (G3).
    Turn keys are strings, so the dict round-trips through JSON unchanged.
    """
    parsed = target.thread or {}
    spans = parsed.get("turns") or {}
    header = parsed.get("header") or {}
    decision = parsed.get("decision") or {}
    turns = {}
    for n in sorted(target.turns):
        entry = spans.get(n) or {}
        turns[str(n)] = {
            "role": target.turns[n].get("role") or entry.get("role"),
            "body": body(target, n),
            "line_start": entry.get("line_start"),
            "line_end": entry.get("line_end"),
        }
    return {
        "header": {"text": header.get("text") or "", "line_start": header.get("line_start"),
                   "line_end": header.get("line_end")},
        "turns": turns,
        "decision": {"chair_prose": chair_prose(target.decision),
                     "line_start": decision.get("line_start"),
                     "line_end": decision.get("line_end")},
    }


def rubric_text(versions: dict[str, str], version: str) -> str:
    """inputs/rubric.md: the rubric version, one line per dimension version, a blank line, RUBRIC (G3)."""
    head = [f"rubric_version: {version}", *(f"{dim}: {v}" for dim, v in versions.items())]
    return "\n".join([*head, "", RUBRIC]) + "\n"


def _write_private(path: Path, data: bytes) -> str:
    """Write ``data`` to ``path`` as a 0600 file, following no symlink; return its sha256."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with open(fd, "wb") as handle:
        os.fchmod(handle.fileno(), 0o600)  # an existing file keeps its old mode through O_TRUNC
        handle.write(data)
    return hashlib.sha256(data).hexdigest()


def write_inputs(eval_run_id: str, target: Target, block: str,
                 versions: dict[str, str], version: str) -> dict:
    """Snapshot everything the judge reads into ``<eval home>/runs/<eval_run_id>/inputs/``.

    The judge quotes these copies and judge.reduce verifies against them alone,
    so a source that moves later cannot move a score. ``digests`` pins each
    source file (by the bytes copied) and ``inputs_digests`` each file written
    here; judge.reduce re-hashes both (D6). Every file is 0600, and directories
    are made only by ``config.state_dir`` in the eval home: nothing is written to
    the source home. ``inputs`` names are relative to ``dir``, None when absent.

    Raises:
        OSError: the eval home cannot be written. measure.reduce turns that into
            an eval_target error.
    """
    root = config.state_dir("runs", eval_run_id, "inputs")
    ext = Path(thread.snapshot_key(target.artifact, None)).suffix
    names: dict = dict.fromkeys(
        ("thread", "entries", "original", "revised", "doc", "metrics", "rubric"))
    digests: dict[str, str] = {}
    inputs_digests: dict[str, str] = {}

    def put(name: str, data: bytes, source: str | None = None) -> str:
        path = root / name
        inputs_digests[str(path)] = _write_private(path, data)
        if source is not None:
            digests[source] = inputs_digests[str(path)]
        return name

    # The raw bytes load_target measured: a re-read could copy a file that moved
    # since, and a re-encode of text decoded with errors="replace" would not
    # hash to the source's digest.
    if target.thread_raw is not None:
        names["thread"] = put("thread.md", target.thread_raw, target.thread_path)
    entries = json.dumps(build_entries(target), ensure_ascii=False, indent=1)
    names["entries"] = put("entries.json", entries.encode("utf-8"))
    if target.original is not None:
        names["original"] = put("original" + ext, target.original, target.original_path)
    if target.revised is not None:
        names["revised"] = put("revised" + ext, target.revised, target.revised_path)
    steps = [s for s in target.steps if s.get("data") is not None]
    if steps:
        config.state_dir("runs", eval_run_id, "inputs", "doc")
        names["doc"] = [put("doc/" + Path(s["key"]).name, s["data"], s["path"]) for s in steps]
    names["metrics"] = put("metrics.json", block.encode("utf-8"))
    names["rubric"] = put("rubric.md", rubric_text(versions, version).encode("utf-8"))
    return {"inputs": {"dir": str(root), **names}, "digests": digests,
            "inputs_digests": inputs_digests}


_GOAL_ROLE = (
    "You are the judge of one finished committee review. Score it on three "
    "dimensions from the files below, and back every score with quotes."
)

# C3's output contract, from the constants, so the fence tag and limits have one source.
_GOAL_CONTRACT = (
    f"Done when: your answer ends with one ```{FENCE_TAG} fenced block holding one JSON "
    f"object with the keys {', '.join(JUDGE_DIMS)}. Each key maps to "
    '{"score": <an integer 1-5>, "rationale": "<why>", "evidence": [{"turn": <the turn '
    'number, or null>, "where": "turn" | "decision" | "header" | "original" | "revised", '
    '"quote": "<verbatim>"}]}, '
    f"with at most {EVIDENCE_MAX} evidence items per dimension and each quote at most "
    f"{QUOTE_MAX} characters. concern_coverage may also carry "
    '"concerns": [{"member": "<seat>", "concern": "<what>", "raised_turn": <n>, '
    '"answered_turn": <n or null>}] and "absent_stakeholders": [{"who": "<function>", '
    '"turn": <n>, "quote": "<verbatim>"}].'
)


def judge_goal(inputs: dict) -> str:
    """The judge's whole goal. At most cast.GOAL_MAX for an inputs dir of 300 chars (T8).

    It names the inputs directory once, then the files in it (an absent copy is
    called unavailable, never named), the read-only rule, the verbatim-quote rule
    and the C3 output contract. The rubric is never inlined: rubric.md holds it.
    """
    files = []
    if inputs.get("thread"):
        files.append(f"{inputs['thread']} (the transcript)")
    files.append(f"{inputs['entries']} (every turn, the header and the chair's prose, "
                 "each with its line range)")
    files.append(f"{inputs['original']} (the document the committee was handed)"
                 if inputs.get("original") else "no original copy (unavailable)")
    files.append(f"{inputs['revised']} (the document after the delegated edits)"
                 if inputs.get("revised") else "no revised copy (unavailable: judge the edits "
                 "from the delegations and the junior_ic reports)")
    if inputs.get("doc"):
        files.append("doc/ (the document after each edit, one file per junior_ic turn)")
    files.append(f"{inputs['metrics']} (the record's counts, including seats, "
                 "unanswered_reviewer_turns and outside_room_mentions)")
    files.append(f"{inputs['rubric']} (how to score each dimension: read it first)")
    return "\n\n".join((
        _GOAL_ROLE,
        f"The inputs directory: {inputs['dir']}\nIn it: " + "; ".join(files) + ".",
        "This is read only: write, edit or create nothing.",
        f"Quote rule: {VERBATIM}. A \"decision\" quote comes from the chair's prose, "
        "never from the re-check lines under it.",
        _GOAL_CONTRACT,
    ))


# --- D6: parse the judge's answer, and verify every quote against inputs/ ------

# Both fence lines stand alone: a ``` inside a JSON string can never close a
# fence early and hand the win to a block echoed from the transcript.
_FENCE_RE = re.compile(
    r"^[ \t]*```[ \t]*" + re.escape(FENCE_TAG) + r"[ \t]*\n(.*?)\n[ \t]*```[ \t]*$",
    re.DOTALL | re.IGNORECASE | re.MULTILINE)
_WHERE = ("turn", "decision", "header", "original", "revised")
_ENTRY_TEXT = {"turn": "body", "decision": "chair_prose", "header": "text"}


def parse_answer(answer: str | None) -> dict | None:
    """The last ``hermes-eval`` fence whose body parses as a JSON object, or None.

    A fence opens on a line holding only ```hermes-eval and closes on a line
    holding only ```. Walked in reverse, as research's verdict.parse does: a
    restated answer wins, and a broken last fence falls back to the one before it.
    """
    if not isinstance(answer, str):
        return None
    for raw in reversed(_FENCE_RE.findall(answer)):
        try:
            doc = json.loads(raw)
        except (ValueError, RecursionError):
            continue
        if isinstance(doc, dict):
            return doc
    return None


def _collapse(text: str) -> str:
    """Whitespace collapsed to single spaces: how a quote and its place are compared."""
    return " ".join(text.split())


def read_snapshot(inputs: dict, digests: dict) -> dict:
    """The inputs/ files a quote may cite, each read once and checked against measure's digest.

    ``{"entries": dict, "thread" | "original" | "revised": str | None}``. A file
    that is missing, not a regular file, or whose sha256 is not the one
    ``digests`` (the eval_target's inputs_digests, by absolute path) records
    reads as absent, so a copy changed after the re-hash backs no quote.
    Never the source. Never raises.
    """
    root = inputs.get("dir") if isinstance(inputs, dict) else None
    digests = digests if isinstance(digests, dict) else {}
    snap: dict = {}
    for key in ("entries", "thread", "original", "revised"):
        name = inputs.get(key) if isinstance(inputs, dict) else None
        data = None
        if isinstance(root, str) and isinstance(name, str):
            path = str(Path(root) / name)
            data = thread.read_regular(path)
            if data is not None and hashlib.sha256(data).hexdigest() != digests.get(path):
                data = None
        snap[key] = None if data is None else data.decode("utf-8", "replace")
    try:
        entries = json.loads(snap["entries"] or "null")
    except (ValueError, RecursionError):
        entries = None
    snap["entries"] = entries if isinstance(entries, dict) else {}
    return snap


def _entry_for(entries: object, where: str, turn: int | None) -> dict | None:
    """The entries.json place an item cites: a turn by number, the decision or the header."""
    if not isinstance(entries, dict):
        return None
    if where == "turn":
        turns = entries.get("turns")
        entry = turns.get(str(turn)) if isinstance(turns, dict) and turn is not None else None
    else:
        entry = entries.get(where)
    return entry if isinstance(entry, dict) else None


def _entry_line(text: str | None, entry: dict, key: str) -> int | None:
    """The first line of thread.md ``text`` in the entry's range holding ``key``, else its first line."""
    start, end = entry.get("line_start"), entry.get("line_end")
    if text is None or not isinstance(start, int) or not isinstance(end, int):
        return None
    found = _find_line(_lines(text), (start, end), lambda line: key in _collapse(line))
    return start if found is None else found


def verify_evidence(item: object, snap: dict) -> dict | None:
    """One judge evidence item, checked against the snapshot ``read_snapshot`` read (D6 step 2).

    ``verified`` iff the quote (clipped to QUOTE_MAX, whitespace collapsed, at
    least QUOTE_MIN_WORDS words and QUOTE_MIN_CHARS characters) is a substring
    of the place it cites: a turn's body, the chair prose or the header text
    from inputs/entries.json, or the whole inputs/ copy for "original"/"revised".
    ``line`` is the first line holding the quote's first 40 characters
    (thread.md within the entry's range, falling back to its first line; or the
    copy), null when unverified or when inputs/ has no thread.md. None for a
    malformed item, which the caller counts as rejected.
    """
    if not isinstance(item, dict):
        return None
    where, quote, turn = item.get("where"), item.get("quote"), item.get("turn")
    if where not in _WHERE or not isinstance(quote, str):
        return None
    if turn is not None and (not isinstance(turn, int) or isinstance(turn, bool)):
        return None
    quote = _collapse(quote[:QUOTE_MAX])
    out = {"turn": turn, "where": where, "quote": quote, "line": None, "verified": False}
    if len(quote) < QUOTE_MIN_CHARS or words(quote) < QUOTE_MIN_WORDS:
        return out
    key = quote[:40]
    if where in ("original", "revised"):
        text = snap.get(where)
        if text is not None and quote in _collapse(text):
            lines = _lines(text)
            out["verified"] = True
            out["line"] = _find_line(lines, (1, len(lines)), lambda line: key in _collapse(line))
        return out
    entry = _entry_for(snap.get("entries"), where, turn)
    text = entry.get(_ENTRY_TEXT[where]) if entry else None
    if isinstance(text, str) and quote in _collapse(text):
        out["verified"] = True
        out["line"] = _entry_line(snap.get("thread"), entry, key)
    return out


def concern_cap(score: int | None, metrics: dict) -> int | None:
    """concern_coverage's cap (D5): at most 3 unless every seated reviewer was heard and answered.

    Fails closed: metrics whose ``seats.unheard`` or ``unanswered_reviewer_turns``
    is missing or not a list cap too, because unknown is never "all heard".
    """
    if score is None:
        return None
    seats = metrics.get("seats") if isinstance(metrics, dict) else None
    unheard = seats.get("unheard") if isinstance(seats, dict) else None
    unanswered = metrics.get("unanswered_reviewer_turns") if isinstance(metrics, dict) else None
    clear = unheard == [] and unanswered == []
    return score if clear else min(score, 3)


def _valid_score(value: object) -> bool:
    """C3: an int 1-5. A bool is not a score, and neither is 4.0 or "4"."""
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 5


def _text(value: object) -> str | None:
    """A detail text field: a str clipped to QUOTE_MAX, else None."""
    return value[:QUOTE_MAX] if isinstance(value, str) else None


def _turn(value: object) -> int | None:
    """A detail turn field: an int (never a bool), else None."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


_CONCERN_FIELDS = {"member": _text, "concern": _text, "raised_turn": _turn, "answered_turn": _turn}
_ABSENT_FIELDS = {"who": _text, "turn": _turn, "quote": _text}


def _detail(given: object, snap: dict) -> dict:
    """concern_coverage's ``detail`` (C3): the judge's concerns and absent stakeholders, bounded.

    Only dict items, at most DETAIL_MAX of each, only C3's keys (texts clipped
    to QUOTE_MAX, turns ints or null). An absent stakeholder's quote is verified
    against its turn like evidence (it carries ``line`` and ``verified``) but is
    never evidence: it neither scores nor counts as rejected.
    """
    def items(key: str, fields: dict) -> list[dict]:
        raw = given.get(key) if isinstance(given, dict) else None
        rows = [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []
        return [{f: clean(r.get(f)) for f, clean in fields.items()} for r in rows[:DETAIL_MAX]]

    absent = []
    for row in items("absent_stakeholders", _ABSENT_FIELDS):
        checked = verify_evidence({"where": "turn", "turn": row["turn"], "quote": row["quote"]}, snap)
        absent.append({**row, "quote": checked["quote"] if checked else row["quote"],
                       "line": checked["line"] if checked else None,
                       "verified": bool(checked and checked["verified"])})
    return {"concerns": items("concerns", _CONCERN_FIELDS), "absent_stakeholders": absent}


def score_judge(parsed: dict | None, inputs: dict, digests: dict,
                metrics: dict) -> tuple[dict[str, dict], int]:
    """The three judge dimensions in C5 shape, and how many evidence items were rejected.

    Evidence is verified against the inputs/ snapshot, each file read once and
    checked against ``digests`` (the eval_target's inputs_digests), never the
    source. ``metrics`` is the eval_target's, never inputs/metrics.json. A
    score counts only when it is an int 1-5 AND at least one of its quotes
    verifies; otherwise it is null with an error, an invalid score first. At
    most EVIDENCE_MAX items are read per dimension (extras are dropped, not
    counted); a malformed item is dropped and counted, an unverified one kept
    with ``verified: false`` and counted. A rationale is clipped to
    RATIONALE_MAX. concern_coverage is capped by ``concern_cap`` and carries
    ``_detail``. Never raises.
    """
    snap = read_snapshot(inputs, digests)
    rejected = 0
    dims: dict[str, dict] = {}
    for dim in JUDGE_DIMS:
        given = parsed.get(dim) if isinstance(parsed, dict) else None
        out = {"scorer": "judge", "score": None, "rationale": "", "evidence": [], "error": None}
        if not isinstance(parsed, dict):
            out["error"] = "no parseable hermes-eval fence"
        elif not isinstance(given, dict):
            out["error"] = "missing from the answer"
        else:
            if isinstance(given.get("rationale"), str):
                out["rationale"] = given["rationale"][:RATIONALE_MAX]
            items = given.get("evidence")
            for item in (items if isinstance(items, list) else [])[:EVIDENCE_MAX]:
                checked = verify_evidence(item, snap)
                if checked is None or not checked["verified"]:
                    rejected += 1
                if checked is not None:
                    out["evidence"].append(checked)
            if not _valid_score(given.get("score")):
                out["error"] = "score is not an integer 1-5"
            elif not any(e["verified"] for e in out["evidence"]):
                out["error"] = "no verifiable evidence"
            else:
                out["score"] = given["score"]
        if dim == "concern_coverage":
            detail = _detail(given, snap)
            capped = concern_cap(out["score"], metrics)
            if capped != out["score"]:
                detail["capped_from"] = out["score"]
                out["score"] = capped
            out["detail"] = detail
        dims[dim] = out
    return dims, rejected


# --- D7/D8: eval.json, the ledger, calibration ---------------------------------

EVAL_JSON_MAX = 256 * 1024
LEDGER_MAX = 2 * 1024 * 1024
# evals/<first 8 hex of sha1(source realpath)>-<run id>.json (eval_json_path)
_EVALS_NAME = re.compile(r"[0-9a-f]{8}-[A-Za-z0-9][A-Za-z0-9._-]*\.json")


def eval_json_path(eval_home: str, source_home: str, run_id: str) -> Path:
    """Where the latest evaluation of (source home, run) lives. Creates nothing.

    Same home, compared as realpaths: ``<home>/runs/<run>/eval.json`` (Q5), the
    one file the eval writes under the target's run directory. A foreign home
    gets zero writes, so its result goes under ``<eval home>/evals/``, prefixed
    with the source realpath's sha1 so one run id in two homes never collides.
    """
    home, source = os.path.realpath(eval_home), os.path.realpath(source_home)
    if home == source:
        return Path(home) / "runs" / run_id / "eval.json"
    tag = hashlib.sha1(source.encode("utf-8")).hexdigest()[:8]
    return Path(home) / "evals" / f"{tag}-{run_id}.json"


def write_eval_json(path: Path, body: dict) -> None:
    """Replace ``path`` with ``body`` atomically: a 0600 temp file, then os.replace.

    Only the two paths ``eval_json_path`` gives: ``runs/<run id>/eval.json``
    (G11: the target may have no ``runs/<run>/`` yet) and
    ``evals/<8 hex>-<run id>.json``, under the eval home. Anything else, a
    foreign home or a ``..`` included, is refused and never written. The
    directory is made only by ``config.state_dir``, and the temp file sits in
    it and is fsynced before the replace. The file holds the latest
    evaluation; the ledger keeps them all.

    Raises:
        ValueError: ``path`` is not one of those two.
        OSError: the write failed; no temp file is left. judge.reduce turns
            either into an error value.
    """
    path = Path(path)
    parts = path.parent.relative_to(eval_home()).parts
    same_home = (len(parts) == 2 and parts[0] == "runs" and RUN_ID.fullmatch(parts[1])
                 and path.name == "eval.json")
    if not same_home and not (parts == ("evals",) and _EVALS_NAME.fullmatch(path.name)):
        raise ValueError(f"not an eval.json path under the eval home: {path}")
    directory = config.state_dir(*parts)
    fd, temp = tempfile.mkstemp(dir=directory, prefix=f".{path.name}.")
    try:
        with open(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(body, indent=2, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, directory / path.name)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def ledger_path(home: str) -> Path:
    """``<home>/evals.jsonl``: every eval and every anchor, append-only."""
    return Path(home) / "evals.jsonl"


def append_ledger(home: str, line: dict) -> None:
    """Append ``line`` as one canonical JSON line with a single ``os.write``, then fsync.

    ``O_APPEND`` lands that one write whole at the end of the file even when
    two evals append at once. When the file does not end in a newline (a
    crash, a full disk or trailing NULs tore its last line), the same write
    starts with one, so the torn line never swallows this one. Created 0600,
    never through a symlink, never truncated or rewritten.

    Raises:
        OSError: the ledger cannot be opened (a symlink included), or the
            write was short.
    """
    data = (canonical(line) + "\n").encode("utf-8")
    path = ledger_path(home)
    fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        size = os.fstat(fd).st_size
        if size and os.pread(fd, 1, size - 1) != b"\n":
            data = b"\n" + data
        if os.write(fd, data) != len(data):
            raise OSError(errno.EIO, f"short write to {path}")
        os.fsync(fd)
    finally:
        os.close(fd)


def read_ledger(path: Path, limit: int | None = None) -> list[dict] | None:
    """The ledger's JSON-object lines in file order, or None when they cannot be known.

    Only a missing ledger is ``[]``: nothing is evaluated or anchored yet. None
    (unknown) past ``limit`` bytes, and for anything that is not a readable
    regular file: a symlink, a FIFO, a directory or a permission error, read
    through ``thread.read_regular``. Lines that do not parse as a JSON object
    are skipped. None too for a line nested past json's recursion limit, which
    may be an object (an anchor) no one can read. It splits on "\\n" only,
    because a canonical line may hold a literal U+2028, which ``splitlines``
    would cut. It creates nothing.
    """
    try:
        size = os.lstat(path).st_size
    except FileNotFoundError:
        return []
    except OSError:
        return None
    if limit is not None and size > limit:
        return None
    data = thread.read_regular(path)
    if data is None:
        return None
    if limit is not None and len(data) > limit:
        return None
    lines = []
    for raw in data.decode("utf-8", "replace").split("\n"):
        try:
            line = json.loads(raw)
        except ValueError:
            continue
        except RecursionError:
            return None
        if isinstance(line, dict):
            lines.append(line)
    return lines


def eval_line(body: dict) -> dict:
    """The C6 ledger line for one eval.json body: all six dimensions, ``ts`` now.

    It reads ``target.{home, run, created_at}``, ``rubric_version``,
    ``rubric.<id>``, ``dimensions.<id>.score``, ``eval_run`` and ``judge.status``.
    """
    target = body["target"]
    return {
        "ts": time.time(),
        "source": "eval",
        "target": {"home": target["home"], "run": target["run"], "created_at": target["created_at"]},
        "rubric_version": body["rubric_version"],
        "dimensions": {d: {"version": body["rubric"][d], "score": body["dimensions"][d]["score"]}
                       for d in DIMENSIONS},
        "eval_run": body["eval_run"],
        "judge_status": body["judge"]["status"],
        "rater": None,
        "note": None,
    }


def anchor_line(target: dict, scores: dict[str, int], versions: dict[str, str],
                rater: str | None, note: str | None) -> dict:
    """The C6 ledger line for the user's own scores: only the entered dimensions.

    Each carries its dimension's current version, so the anchor stays valid
    until that one dimension is redefined, whatever happens to the others (D5).
    The caller (``eval_cli anchor``) has already checked the ids and the 1-5 range.
    """
    return {
        "ts": time.time(),
        "source": "anchor",
        "target": {"home": target["home"], "run": target["run"], "created_at": target["created_at"]},
        "rubric_version": rubric_version(versions),
        "dimensions": {d: {"version": versions[d], "score": scores[d]} for d in DIMENSIONS if d in scores},
        "eval_run": None,
        "judge_status": None,
        "rater": rater,
        "note": note,
    }


def _target_key(line: dict) -> tuple | None:
    """A ledger line's target key ``(home, run, created_at)``, or None when malformed."""
    target = line.get("target")
    if not isinstance(target, dict):
        return None
    home, run, created_at = target.get("home"), target.get("run"), target.get("created_at")
    if isinstance(home, str) and isinstance(run, str) and isinstance(created_at, (int, float)):
        return (home, run, created_at)
    return None


def _cells(line: dict) -> list[tuple[str, dict]]:
    """A ledger line's ``(dimension id, {version, score})`` pairs; malformed cells skipped."""
    dims = line.get("dimensions")
    if not isinstance(dims, dict):
        return []
    return [(d, cell) for d, cell in dims.items() if isinstance(cell, dict)]


def _score(value: object) -> int | None:
    """An int score, or None (a null, a bool or anything else is no score)."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def latest_evals(lines: list[dict]) -> dict[tuple, dict]:
    """The latest eval line per target key ``(home, run, created_at)``, in ledger order.

    First the last line per ``eval_run`` (a resumed judge.reduce appends a
    second one), then the last of those per target.
    """
    per_run: dict[str, dict] = {}
    for line in lines:
        if isinstance(line, dict) and line.get("source") == "eval" and isinstance(line.get("eval_run"), str):
            per_run.pop(line["eval_run"], None)  # re-insert, so the order is each run's last line
            per_run[line["eval_run"]] = line
    latest: dict[tuple, dict] = {}
    for line in per_run.values():
        key = _target_key(line)
        if key is not None:
            latest[key] = line
    return latest


def calibration(ledger_lines: list[dict]) -> dict[str, str]:
    """``{judge dimension version: label}``, computed from the ledger and never stored (D8).

    A target counts at version V when it has an anchor for that dimension at V
    (the latest at V wins, so an older-version anchor appended later never
    hides it) and its latest eval line (``latest_evals``) scored that dimension at V.
    A null eval score is no score, so a later failed eval hides an earlier one
    (G6). The label is ``"off (Δn)"`` when any |eval - anchor| >= 2, with n the
    largest; else ``"calibrated"`` with at least MIN_ANCHORS targets; else
    ``"uncalibrated"``. Every current judge version, and every judge version in
    any eval line, gets a label. Deterministic versions never do.
    """
    lines = [line for line in ledger_lines if isinstance(line, dict)]
    versions = {v for d, v in dimension_versions().items() if d in JUDGE_DIMS}
    anchors: dict[tuple, int] = {}
    for line in lines:
        key = _target_key(line)
        for d, cell in _cells(line):
            version, score = cell.get("version"), _score(cell.get("score"))
            if d not in JUDGE_DIMS or not isinstance(version, str):
                continue
            if line.get("source") == "eval":
                versions.add(version)
            elif line.get("source") == "anchor" and key is not None and score is not None:
                anchors[(key, d, version)] = score  # the latest per target, dimension AND version
    deltas: dict[str, list[int]] = {v: [] for v in versions}
    for key, line in latest_evals(lines).items():
        for d, cell in _cells(line):
            version, score = cell.get("version"), _score(cell.get("score"))
            anchor = anchors.get((key, d, version)) if isinstance(version, str) else None
            if d in JUDGE_DIMS and score is not None and anchor is not None:
                deltas[version].append(abs(score - anchor))
    labels = {}
    for version, diffs in deltas.items():
        worst = max(diffs, default=0)
        labels[version] = (f"off (Δ{worst})" if worst >= 2
                           else "calibrated" if len(diffs) >= MIN_ANCHORS else "uncalibrated")
    return labels


# --- the playbook (D1): measure -> judge -> score ----------------------------

PAYLOAD_SCHEMA = {
    "type": "object",
    "required": ["role", "title", "goal", "kind"],
    "additionalProperties": False,
    "properties": {
        "role": {"type": "string"},
        "title": {"type": "string"},
        "goal": {"type": "string"},
        "kind": {"type": "string", "enum": ["judge"]},
    },
}

RESULT_SCHEMA = {
    "type": "object",
    "required": ["answer"],
    "additionalProperties": True,
    "properties": {"answer": {"type": "string"}},
}

# Static. The snapshot next_phase gets carries the PRIOR phase's reductions
# (engine/queue.py _load_prior_reductions), never the reductions of the phase
# it is leaving.
_NEXT = {"measure": "judge", "judge": "score", "score": None}


def _eval_target(run: Run) -> dict | None:
    """The latest ``eval_target`` reduction's json on this snapshot, or None."""
    for r in reversed(run.reductions or []):
        if r.kind == "eval_target" and isinstance(r.json, dict):
            return r.json
    return None


def _changed(digests: dict, base: str | None = None) -> list[str]:
    """Every recorded file that no longer hashes to its sha256, as a path string.

    ``thread.digest`` is "" for a file that has gone, so a deleted copy counts as
    changed. A relative key resolves against ``base`` (the inputs directory).
    """
    out = []
    for key, want in sorted(digests.items()):
        p = Path(key)
        if base and not p.is_absolute():
            p = Path(base) / p
        if thread.digest(p) != want:
            out.append(str(p))
    return out


def _target_json(t: Target) -> dict:
    """C5 ``target``. Its (home, run, created_at) is the key the ledger and compare share."""
    return {"home": t.home, "run": t.run_id, "created_at": t.created_at,
            "playbook": "committee", "state": t.state,
            "review_state": t.review_state, "legacy": t.legacy}


def _eval_body(run_id: str, et: dict, dims: dict, flags: list, judge: dict) -> dict:
    """The C5 eval.json body from the eval_target, the six dimensions, the flags and the judge block."""
    return {
        "schema": 1,
        "rubric_version": et["rubric_version"],
        "rubric": et["rubric"],
        "target": et["target"],
        "eval_run": run_id,
        "evaluated_at": time.time(),
        "original_source": et["original_source"],
        "metrics": et["metrics"],
        "flags": flags,
        "dimensions": dims,
        "headline": headline(dims, judge["error"]),
        "judge": judge,
    }


def _eval_json_for(et: dict) -> Path:
    """Where the eval of the eval_target's target is written (D7)."""
    return eval_json_path(eval_home(), et["target"]["home"], et["target"]["run"])


def _failed_eval(run: Run, error: str) -> dict:
    """judge.reduce's fallback: a failed eval, written where it can be, so disk and reduction agree.

    Rebuilt from the eval_target alone: the judge dimensions null with
    ``error``, the deterministic half and measure's flags kept. eval.json and
    the ledger line are each tried once, on their own, so a failed ledger write
    can never leave an "ok" eval.json behind. With a malformed eval_target
    there is nothing to rebuild from: the minimal body, and no write. Never raises.
    """
    judge = {"status": "failed", "evidence_rejected": 0, "cost_usd": None, "tokens": None,
             "error": error}
    try:
        et = _eval_target(run)
        dims = {d: {"scorer": "judge", "score": None, "rationale": "", "evidence": [],
                    "error": error} if d in JUDGE_DIMS else et["deterministic"][d]
                for d in DIMENSIONS}
        body = _eval_body(run.id, et, dims, list(et["flags"]), judge)
        path = _eval_json_for(et)
    except Exception:
        return {"eval_run": run.id, "judge": judge}
    writes = (lambda: write_eval_json(path, body),
              lambda: append_ledger(eval_home(), eval_line(body)))
    for write in writes:
        try:
            write()
        except Exception:
            pass
    return body


class CommitteeEvalPlaybook:
    """Score one finished committee run in three phases: ``measure``, ``judge``, ``score`` (D1).

    No instance state. Everything a later phase needs rides on the eval_target
    reduction or on a digest-pinned file under runs/<eval-run>/inputs/, so
    ``hermes run resume <eval-run> --wait`` finishes the run in a fresh process.
    The environment is read once, in measure's reduce. There is no view seam
    either, so eval runs get the generic tabs, like any viewless playbook.
    """

    name = "committee-eval"
    phases = ["measure", "judge", "score"]

    def seed(self, run: Run, site) -> list[Ticket]:
        """One goal-only judge ticket, built from the eval_target reduction alone.

        measure and score seed nothing. judge seeds nothing either when measure
        recorded an error, or when the eval_target is malformed (no inputs): the
        judge phase then reduces to failed and the run ends failed. A seed-time
        raise (engine/cli.py cmd_run) would instead strand it ``running``.
        """
        if run.phase != "judge":
            return []
        et = _eval_target(run)
        if not et or et.get("error"):
            return []
        try:
            goal, target = judge_goal(et["inputs"]), et.get("target") or {}
            title = f"Score committee run {target.get('run')} on the rubric"
        except Exception:  # a malformed eval_target seeds nothing, never raises
            return []
        return [Ticket(
            id=f"{run.id}/judge",
            run_id=run.id,
            phase="judge",
            state="queued",
            resource_req="cpu",
            priority=0.0,
            attempts=0,
            payload={
                "role": "judge",
                "title": title,
                "goal": goal,
                "kind": "judge",
            },
        )]

    def payload_schema(self, phase: str) -> dict:
        """C3, for every phase."""
        return PAYLOAD_SCHEMA

    def result_schema(self, phase: str) -> dict:
        """``{answer}``, with extra keys allowed: a contract fail is terminal on first sight."""
        return RESULT_SCHEMA

    def driver(self, phase: str) -> Driver:
        """Goal-only (C1). How to judge travels in the goal and in inputs/rubric.md."""
        return Driver(command=None, args={}, loop=None)

    def verify(self, run, ticket, result, site) -> bool:
        """Always True. A False parks the judge in needs_human and blocks the run.

        The no-trust checks (verbatim quotes, re-hashing) live in judge's reduce.
        """
        return True

    def reduce(self, run: Run, phase: str, findings: list[Finding], site) -> list[Reduction]:
        """Fold one phase. Never raises: engine/dispatch.py _do_reduce has no guard."""
        if phase == "measure":
            return [Reduction(kind="eval_target", json=self._measure(run, site))]
        if phase != "judge":
            return []
        try:
            return self._judge(run, findings)
        except Exception as exc:  # a malformed reduction or a failed write, never a raise
            return [Reduction(kind="eval", json=_failed_eval(
                run, f"judge reduce: {type(exc).__name__}: {exc}"))]

    def _measure(self, run: Run, site) -> dict:
        """Resolve, validate, measure and snapshot the target (D2-D6). Returns the C4 eval_target.

        This is the only reader of HERMES_COMMITTEE_EVAL_RUN and _HOME. A failure
        is the value ``{"target": <partial>, "error": reason}``, and a failed
        validation has written nothing anywhere.
        """
        run_id = os.environ.get(ENV_RUN) or None
        partial = {"home": None, "run": run_id}
        try:
            partial["home"] = home = source_home()
            name = str(getattr(site, "name", ""))
            if name != "local" and not name.startswith("fan-"):
                # inputs/ and every judge read live under the eval home, on the master
                return {"target": partial, "error": f"site must be local or fan-*: {name}"}
            reason = validate_target(home, run_id)
            if reason:
                return {"target": partial, "error": reason}
            measured = measure_target(home, run_id)
            t = measured["target"]
            versions = dimension_versions()
            version = rubric_version(versions)
            block = deterministic_block(
                measured["metrics"], measured["flags"], measured["deterministic"])
            written = write_inputs(run.id, t, block, versions, version)
        except Exception as exc:  # reduce never raises
            return {"target": partial, "error": f"measure failed: {type(exc).__name__}: {exc}"}
        return {
            "target": _target_json(t),
            "legacy": t.legacy,
            "digests": written["digests"],
            "inputs_digests": written["inputs_digests"],
            "inputs": written["inputs"],
            "rubric": versions,
            "rubric_version": version,
            "metrics": measured["metrics"],
            "flags": measured["flags"],
            "deterministic": measured["deterministic"],
            "original_source": t.original_source,
            "error": None,
        }

    def _judge(self, run: Run, findings: list[Finding]) -> list[Reduction]:
        """Re-hash, score and pick a status, then write eval.json and one ledger line (D6, D7).

        It reads only the eval_target reduction, inputs/ and this run's own traces,
        so a fresh process can re-reduce it. A second reduce appends a second
        ledger line with the same eval_run, which readers dedupe. Once measure has
        succeeded, every status writes, so a failed judge keeps the deterministic half.
        """
        et = _eval_target(run)
        if not et or et.get("error"):
            return []  # is_done then sees only the error, and the run ends failed
        inputs, metrics = et["inputs"], et["metrics"]
        # Re-hash first. A run whose sources or copies changed is never scored, so
        # a quote planted in an inputs/ copy is never even read.
        changed = (_changed(et.get("digests") or {})
                   + _changed(et.get("inputs_digests") or {}, inputs.get("dir")))
        answers = [f.json.get("answer") for f in findings or () if isinstance(f.json, dict)]
        answer = next((a for a in reversed(answers) if isinstance(a, str) and a.strip()), None)
        parsed = None if changed else parse_answer(answer)
        judged, rejected = score_judge(parsed, inputs, et.get("inputs_digests") or {}, metrics)
        flags = list(et["flags"])
        if changed:
            flags.append({"id": "target_changed_during_eval", "turn": None, "line": None,
                          "quote": "", "paths": changed})
            status, error = "failed", "target changed during eval: " + ", ".join(changed)
        elif not findings:
            status, error = "failed", "the judge returned no result (driver_failed or timeout)"
        elif parsed is None:
            status, error = "unparseable", "no parseable hermes-eval fence"
        else:
            unscored = [f"{d}: {judged[d]['error']}" for d in JUDGE_DIMS
                        if judged[d]["score"] is None]
            status, error = ("partial", "; ".join(unscored)) if unscored else ("ok", None)
        if status == "failed":
            for d in JUDGE_DIMS:
                judged[d]["score"], judged[d]["error"] = None, error
        dims = {d: judged[d] if d in JUDGE_DIMS else et["deterministic"][d] for d in DIMENSIONS}
        traces = config.resolve_home() / "runs" / run.id / "traces"
        totals = trace_totals([thread.read_regular(p) for p in sorted(traces.glob("*.jsonl"))])
        body = _eval_body(run.id, et, dims, flags, {
            "status": status,
            "evidence_rejected": rejected,
            "cost_usd": totals["cost_usd"] if totals["found"] else None,
            "tokens": totals["tokens"],
            "error": error,
        })
        write_eval_json(_eval_json_for(et), body)
        append_ledger(eval_home(), eval_line(body))
        return [Reduction(kind="eval", json=body)]

    def next_phase(self, run: Run) -> str | None:
        """measure -> judge -> score -> None, whatever measure found."""
        return _NEXT.get(run.phase)

    def is_done(self, run: Run) -> bool:
        """Done iff the judge's eval says ok, read at the zero-ticket score sentinel.

        At ``score`` the snapshot carries judge's reductions, or measure's when
        judge recorded none (an error target). It never raises on a malformed one.
        """
        return run.phase == "score" and any(
            r.kind == "eval" and isinstance(r.json, dict)
            and isinstance(r.json.get("judge"), dict)
            and r.json["judge"].get("status") == "ok"
            for r in run.reductions or ()
        )


# `python -m playbooks.committee.eval` imports the package first, which imports this
# module and registers it. runpy then runs this file a second time as __main__.
# Only the imported copy registers (engine/playbook.py register is last-write-wins).
if __name__ != "__main__":
    _playbook.register("committee-eval", CommitteeEvalPlaybook())

if __name__ == "__main__":
    from playbooks.committee.eval_cli import main

    sys.exit(main())
