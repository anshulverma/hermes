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

import hashlib
import json
import os
import re
import sqlite3
import urllib.parse
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from engine import config
from playbooks.committee import cast, thread
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
EVIDENCE_MAX = 5  # evidence items kept per judge dimension; extras are dropped (C3)
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
    chmods. Creates nothing (SQLite may touch a WAL database's ``-shm``).
    """
    try:
        db = f"{home}/queue.db"
        if not os.path.isfile(db):
            return None
        conn = sqlite3.connect("file:" + urllib.parse.quote(db) + "?mode=ro", uri=True)
    except (OSError, TypeError, ValueError, sqlite3.Error):
        return None
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
    queue.db SQLite cannot read counts as none. Never raises; creates nothing.
    """
    if not run_id:
        return f"{ENV_RUN} is not set"
    conn = connect_ro(home)
    if conn is None:
        return f"no queue.db in {home}"
    try:
        with closing(conn):
            if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
                return f"bad run id: {run_id}"
            row = conn.execute("SELECT playbook FROM runs WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                return f"run not found: {run_id}"
            if row["playbook"] != "committee":
                return f"not a committee run: {run_id} ({row['playbook']})"
            rows = _reductions(conn, run_id)
    except sqlite3.Error:
        return f"no queue.db in {home}"
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


def parse_thread(text: str) -> dict:
    """thread.md as D3 reads it: header, labels, the Committee roster, turn and decision entries.

    The header is every line before the first ``## `` line. Entry boundaries are
    only thread.py's ``## turn NN — Name (role)`` and ``## decision — …``
    headings, so any other ``## `` line after the first boundary is body. Lines
    between the header and the first boundary (selection, 1:1 plans) belong to
    no entry. Lines are 1-based and inclusive over ``text.splitlines()``: an
    entry runs from its heading to the line before the next boundary. A turn
    number written twice keeps its last entry.
    """
    lines = text.splitlines() if isinstance(text, str) else []
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
        thread_path=str(run_dir / "thread.md"), thread_text=text, thread=parsed,
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
    kept = [line for line in verdict.replace(_SIMULATION, "").splitlines()
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
