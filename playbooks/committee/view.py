"""Everything the committee's view renders, assembled from a run's reductions.

The control plane serves this: the view route loads the run's reductions and
hands them here. It runs in the SERVER process, which has never called ``seed``
-- ``_state_by_run`` is empty there -- so nothing in this module may read
playbook instance state. Every number on screen comes off the reductions
``reduce`` already wrote, in the order the queue returns them (``ORDER BY id``),
which is the order they happened in.

Three reads are not pure and are stated rather than hidden: the size of each
document snapshot under ``runs/<id>/doc/``, stat'd under THIS process's
HERMES_HOME by the fixed layout ``thread.snapshot_key`` names -- never at a path
a reduction recorded, which is the master's host path and means nothing inside
a container -- before any turn has settled, the artifact line of the run's
own ``thread.md`` header, and the run's ``eval.json`` with this home's
``evals.jsonl`` (``_evaluation``), which committee-eval writes and nothing
here does. The turn cap rides on the turn reductions; the environment is read
only as a fallback for runs captured before that key existed.

Stdlib-only.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from engine import config
from engine.models import Reduction, Run
from playbooks.committee import cast, thread


def view_data(run: Run, reductions: list[Reduction]) -> dict:
    """The whole view payload for one committee run.

    ``run`` is read for exactly one thing -- whether the chair has the floor --
    and its phase name is compared against the static ``"decision"``, never
    parsed for a speaker (the runtime phase name is display-only, §5.6).
    """
    # Nothing `reduce` writes reaches the out-of-contract shapes guarded below
    # and in `_role`/`_as_list` -- they need a hand-edited database. But this
    # runs inside a route, so a raise here is a 500 on a run's page rather than
    # a view that says less than it hoped to.
    reductions = reductions or []
    turns = [r for r in reductions if r.kind == "turn" and isinstance(r.json, dict)]
    # The row, not only its json: the ruling is the row's `review_state`.
    decision_row = next(
        (r for r in reversed(reductions)
         if r.kind == "decision" and isinstance(r.json, dict)),
        None,
    )
    decision = decision_row.json if decision_row is not None else None
    lost = any(r.kind == "lost" for r in reductions)
    holder, queue, spoken = _floor(run, turns, decision)
    stances = _stances(turns)

    return {
        "kind": "committee",
        "roster": _roster(spoken, holder, queue, stances),
        "progress": {
            "turn": _turn_no(turns[-1].json) if turns else 0,
            "cap": _cap(reductions),
            "holder": holder,
            "queue": queue,
            "ended": (decision or {}).get("ended"),
        },
        "timeline": [_entry(r.json) for r in turns],
        # No top-level `stances` block: `_stances` feeds `_roster`, which is the
        # only surface that renders a stance. The payload key was typed, fixtured
        # and asserted on both sides of the seam, and read by nothing.
        "verdict": _verdict(decision),
        "document": _document(run, turns, decision_row, lost),
        # committee-eval D10/C7: None until the run is scored from this home.
        "evaluation": _evaluation(run.id),
    }


# --- the floor -------------------------------------------------------------

def _floor(
    run: Run, turns: list[Reduction], decision: dict | None
) -> tuple[str | None, list[str], list[str]]:
    """Who has spoken, who is waiting, and who holds the floor right now.

    The floor queue is reconstructed rather than read: ``reduce`` records what
    a speaker ASKED for and ``next_phase`` pops the queue FIFO when it grants
    it, so replaying those two rules over the turns in order reproduces the
    queue the state machine holds and this process cannot see.
    """
    spoken: list[str] = []
    queue: list[str] = []
    last: str | None = None

    for reduction in turns:
        doc = reduction.json
        role = _role(doc)
        if role not in cast.CAST:
            # Fail closed, the way `_reduce_turn` does: a turn nobody can be
            # named for is attributed to nobody here either.
            continue
        if role in queue:
            # `next_phase` pops the queue when it MINTS the turn, so the floor
            # was granted whether or not the worker then delivered. Above the
            # `delivered` guard for exactly that reason.
            queue.remove(role)
        if not doc.get("delivered"):
            # `_apply_block` (playbook.py:63-65) runs none of the gates on a
            # turn nobody delivered and hands the floor back to the owner.
            # Mirror it: the seat never spoke, so badging it "spoke" -- or
            # leaving it holding the floor -- contradicts the transcript entry
            # directly below, which says no turn was delivered.
            last = cast.OWNER
            continue
        if role not in spoken:
            spoken.append(role)
        # `_apply_block`: the owner, the junior IC and the chair never queue.
        if doc.get("request_floor") and role not in (cast.OWNER, cast.JUNIOR, cast.CHAIR):
            queue.append(role)
        last = role

    if decision is not None:
        # The meeting is over, so nobody holds the floor and nobody is waiting
        # for it: a seat still badged "waiting to speak" is waiting for a turn
        # that will never come. The verdict card tells that story in the past
        # tense, off the decision's own `dropped_floor_requests`.
        holder, queue = None, []
    elif run.phase == "decision":
        holder = cast.CHAIR  # the chair is writing the verdict
    else:
        holder = last
    return holder, queue, spoken


def _roster(
    spoken: list[str], holder: str | None, queue: list[str], stances: dict
) -> list[dict]:
    """The nine personas and where each of them stands, in seniority order."""
    # `persona` maps the chair sentinel back to the reviewer seat it chairs
    # from, so "the chair is ruling" lights up that member's row.
    seat = cast.persona(holder)["role"] if holder else None
    rows = []
    for role, who in cast.CAST.items():
        if role == seat:
            state = "holds_floor"
        elif role in queue:
            state = "queued"
        elif role in spoken:
            state = "spoke"
        else:
            state = "idle"
        said = stances.get(role)
        rows.append({
            "role": role,
            "name": who["name"],
            "title": who["title"],
            "state": state,
            "stance": said[-1]["text"] if said else None,
        })
    return rows


# --- the transcript --------------------------------------------------------

def _entry(doc: dict) -> dict:
    """One turn, as the timeline reads it."""
    role = _role(doc)
    who = cast.persona(role) if role in cast.CAST else None
    action = doc.get("action")
    # The same guard `_stances` uses: absent, blank or junk is None, never "".
    stance = doc.get("stance")
    return {
        "n": _turn_no(doc),
        "role": role,
        "name": who["name"] if who else "unattributed",
        "title": who["title"] if who else "",
        "body": doc.get("body") or "",
        # Criterion 7's first half. The decision reduction's `rechecks` carries
        # this too, but that does not exist until the meeting ends -- nineteen
        # turns after the first delegation on the measured run -- so a timeline
        # without it shows a delegation and never says what was delegated.
        "action": action if isinstance(action, str) and action else None,
        "badges": _badges(doc, attributed=who is not None),
        "verified": doc.get("verified") if isinstance(doc.get("verified"), bool) else None,
        # The document stepper reads a reviewer's stance off the entry, by turn.
        "stance": stance.strip() if isinstance(stance, str) and stance.strip() else None,
    }


def _badges(doc: dict, *, attributed: bool) -> list[str]:
    """What happened on this turn beyond its prose.

    The slugs are the turn reduction's own key names plus three derived from it
    (``unattributed``, ``no_turn``, ``signals_only``). Slugs, not phrases: the
    view keys its labels and its tones on these exact strings, and a phrase here
    would fall through to "render the slug as itself" with no tone at all --
    green on both sides of the seam, wrong on screen.

    There is no ``edit applied`` / ``edit did not apply`` badge. ``verified`` on
    the same entry already carries that, and the view renders it as its own
    re-check line; badging it as well prints the same outcome twice.
    """
    # Imported here rather than at module scope: playbook.py imports this
    # module, so importing it back at module scope would be a cycle.
    from playbooks.committee.playbook import _SIGNALS_ONLY

    badges = []
    if not attributed:
        badges.append("unattributed")
    if not doc.get("delivered"):
        badges.append("no_turn")
    elif doc.get("body") == _SIGNALS_ONLY:
        # Delivered, but the speaker sent only their signal block. Not silence
        # and not a failure -- a distinct third thing (spec §5.2).
        badges.append("signals_only")
    if doc.get("request_floor"):
        badges.append("request_floor")
    if doc.get("delegate"):
        badges.append("delegate")
    if doc.get("close"):
        badges.append("close")
    if doc.get("error"):
        badges.append("error")
    return badges


def _stances(turns: list[Reduction]) -> dict[str, list[dict]]:
    """Every stance stated, by role, oldest first.

    Absent stays absent: a persona that stated none has no key here at all,
    never an empty list and never a neutral default (spec §7).
    """
    out: dict[str, list[dict]] = {}
    for reduction in turns:
        doc = reduction.json
        role = _role(doc)
        text = doc.get("stance")
        if role in cast.CAST and isinstance(text, str) and text.strip():
            out.setdefault(role, []).append({"turn": _turn_no(doc), "text": text.strip()})
    return out


def _verdict(decision: dict | None) -> dict | None:
    """The decision card, or None while the committee is still sitting."""
    if decision is None:
        return None
    return {
        "text": decision.get("verdict") or "",
        "checks": [dict(c) for c in _as_list(decision.get("rechecks")) if isinstance(c, dict)],
        "artifact_intact": decision.get("artifact_intact"),
        "dropped_delegation": decision.get("dropped_delegation"),
        "dropped_floor_requests": _as_list(decision.get("dropped_floor_requests")),
        # No `simulation` key. It was a constant `True` -- criterion 8 wants the
        # disclaimer to be independent of whether the chair wrote it, and the
        # view satisfies that by rendering the notice UNCONDITIONALLY, which is
        # the fail-safe direction. A flag nothing reads is a flag that can be
        # flipped to False with no test noticing and no notice disappearing.
    }


# --- the document's versions ----------------------------------------------

# Reviewer seats: everyone in the cast who is neither the owner nor the junior IC.
_REVIEWERS = frozenset(cast.CAST) - {cast.OWNER, cast.JUNIOR}


def _document(
    run: Run, turns: list[Reduction], decision: Reduction | None, lost: bool
) -> dict:
    """The original, one step per junior-IC turn, and the final version.

    Every ``path`` is run-relative, named by ``thread.snapshot_key``, and sized
    here under this process's own home -- so the server can serve each one
    from ``runs/<id>/`` without reading a reduction. Steps carry turn numbers,
    never names: the view takes names, stances and prose from ``timeline``.
    """
    artifact = ""
    for doc in [r.json for r in turns] + ([decision.json] if decision else []):
        value = doc.get("artifact")
        if isinstance(value, str) and value:
            artifact = value
    if not artifact and not turns:
        # No turn has settled, so no reduction names the file -- but `open`
        # already kept doc/00-original, and the first worker can run for an
        # hour. The thread header is the master's record of the same path.
        artifact = thread.header_artifact(run.id)
    name = Path(artifact).name or None
    block = {
        "name": name, "captured": False, "original": None, "steps": [], "final": None,
        "dropped_delegation": _dropped(decision),
    }
    if name is None:
        return block

    key = thread.snapshot_key(artifact, None)
    original = {"path": key, "bytes": _size(thread.run_file(run.id, key))}
    by_turn = {_turn_no(r.json): r.json for r in turns}  # the last reduction per turn wins
    steps = []
    for n in sorted(t for t, doc in by_turn.items() if t > 0 and _role(doc) == cast.JUNIOR):
        doc = by_turn[n]
        key = thread.snapshot_key(artifact, n)
        owner_turn, reviewer_turn, provenance = _provenance(n, doc, by_turn)
        steps.append({
            "turn": n,
            "path": key,
            "bytes": _size(thread.run_file(run.id, key)),
            "delivered": bool(doc.get("delivered")),
            "verified": doc.get("verified") if isinstance(doc.get("verified"), bool) else None,
            "owner_turn": owner_turn,
            "reviewer_turn": reviewer_turn,
            "provenance": provenance,
        })

    final = None
    if steps:
        # The last edit that applied, else the original. Always a doc/ file,
        # never revised/: the stepper serves every version the same way.
        applied = [step for step in steps if step["verified"] is True]
        last = applied[-1] if applied else {**original, "turn": None}
        final = {
            "path": last["path"], "turn": last["turn"], "bytes": last["bytes"],
            "ruling": _ruling(decision, lost),
        }
    # Any readable version, not only the original: a worker (bypassPermissions)
    # can delete doc/00-original, and the edits it leaves are still worth
    # stepping through. Original and Edit 1 then say they could not read it.
    captured = original["bytes"] is not None or any(s["bytes"] is not None for s in steps)
    block.update(captured=captured, original=original, steps=steps, final=final)
    return block


def _provenance(n: int, doc: dict, by_turn: dict[int, dict]) -> tuple:
    """(owner_turn, reviewer_turn, provenance) for junior-IC turn ``n``.

    The recorded link wins whenever the reduction carries the key. Only a
    reduction from before the key existed -- ABSENT, not null -- falls back to
    turn order, which holds for the ``next_phase`` that wrote it: a delegation
    is consumed by the very next mint, and an owner turn is minted only right
    after a delivered reviewer turn.
    """
    if "delegated_by_turn" in doc:
        owner = _int(doc.get("delegated_by_turn"))
        if owner is None:
            return None, None, "unknown"
        return owner, _int((by_turn.get(owner) or {}).get("answers_turn")), "recorded"
    owner = by_turn.get(n - 1) or {}
    if _role(owner) != cast.OWNER or owner.get("delegate") is not True:
        return None, None, "unknown"
    reviewer = by_turn.get(n - 2) or {}
    heard = _role(reviewer) in _REVIEWERS and bool(reviewer.get("delivered"))
    return n - 1, (n - 2 if heard else None), "inferred"


def _ruling(decision: Reduction | None, lost: bool) -> str:
    """How the meeting's verdict stands, which is what Final is labelled by."""
    if lost:
        return "no_ruling"
    if decision is None:
        return "in_session"
    if not decision.json.get("delivered"):
        return "no_ruling"
    if decision.review_state == "pending":
        return "awaiting_ruling"
    if decision.review_state in ("accepted", "rejected"):
        return decision.review_state
    return "no_ruling"  # superseded


def _dropped(decision: Reduction | None) -> dict | None:
    """The delegation the turn cap cut off, as a note -- never a step."""
    doc = decision.json if decision is not None else {}
    action = doc.get("dropped_delegation")
    if not (isinstance(action, str) and action):
        return None
    return {"owner_turn": _int(doc.get("dropped_delegation_turn")), "action": action}


def _size(target: Path) -> int | None:
    """The size of the regular file at ``target``, or None for anything else.

    ``lstat`` at every level the route opens without following a symlink --
    ``runs/<id>/``, ``doc/`` and the file -- so a size here never promises a
    read the route then refuses. None, not 0 -- a zero-byte version is real.
    """
    try:
        run_dir, doc, info = (os.lstat(p) for p in (target.parent.parent, target.parent, target))
    except OSError:
        return None
    if stat.S_ISDIR(run_dir.st_mode) and stat.S_ISDIR(doc.st_mode) and stat.S_ISREG(info.st_mode):
        return info.st_size
    return None


# --- the evaluation (committee-eval D10, C7) -------------------------------

def _evaluation(run_id: str) -> dict | None:
    """The run's evaluation as the Metrics tab reads it, or None when there is none.

    ``runs/<id>/eval.json`` exists only when committee-eval scored this run from
    this same home (its D7). Anything else -- never scored, or scored from a
    foreign home -- is None, never an empty score table. Calibration labels are
    computed here from this home's ``evals.jsonl`` at request time and never
    stored (D8): a ledger ``read_ledger`` cannot read -- past ``LEDGER_MAX``, a
    symlink, unreadable -- makes every judge label "unknown".

    Creates nothing -- no mkdir, no ledger file -- and never raises: this runs
    inside a GET, so an oversized or hand-edited file is an error state on the
    page, not a 500.
    """
    # Imported here rather than at module scope: eval imports playbook, which
    # imports this module, so importing it at module scope would be a cycle.
    from playbooks.committee import eval as ev

    def error(message: str) -> dict:
        return {"state": "error", "error": message}

    path = thread.run_file(run_id, "eval.json")
    try:
        size = os.stat(path).st_size
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        return error(f"eval.json could not be read: {exc}")
    if size > ev.EVAL_JSON_MAX:
        return error(f"eval.json is {size} bytes, over the {ev.EVAL_JSON_MAX}-byte limit")
    data = thread.read_regular(path)
    if data is None:
        return error("eval.json is not a readable regular file")
    try:
        body = json.loads(data.decode("utf-8"))
    except ValueError as exc:  # a UnicodeDecodeError is a ValueError too
        return error(f"eval.json is not JSON: {exc}")
    if not isinstance(body, dict):
        return error("eval.json is not a JSON object")
    if body.get("schema") != 1:
        return error(f"eval.json schema is {body.get('schema')!r}, not 1")

    try:
        # [] only when the ledger is missing (nothing anchored: "uncalibrated");
        # None when it cannot be known, which no label may paper over.
        lines = ev.read_ledger(ev.ledger_path(config.resolve_home()), ev.LEDGER_MAX)
        labels = None if lines is None else ev.calibration(lines)
        rubric = body.get("rubric") or {}
        scored = body.get("dimensions") or {}
        judge = body.get("judge") or {}
        dimensions = {}
        for dim in ev.DIMENSIONS:  # D5 order: the table's row order
            doc = scored.get(dim) or {}
            if dim not in ev.JUDGE_DIMS:
                label = None  # deterministic dimensions are never calibrated (G6)
            elif labels is None:
                label = "unknown"
            else:
                label = labels.get(rubric.get(dim), "uncalibrated")
            dimensions[dim] = {
                "score": doc.get("score"),
                "scorer": "judge" if dim in ev.JUDGE_DIMS else "deterministic",
                "quote": next((item.get("quote") for item in doc.get("evidence") or []
                               if item.get("verified") is True), None),
                "calibration": label,
            }
        return {
            "state": "ok",
            "rubric_version": body.get("rubric_version"),
            "evaluated_at": body.get("evaluated_at"),
            "headline": body.get("headline"),
            "judge_status": judge.get("status"),
            # Not in C7's key list, but its UI table shows "the judge status and
            # error", and nothing else in the payload carries the error.
            "judge_error": judge.get("error"),
            "dimensions": dimensions,
            "flags": [flag.get("id") for flag in body.get("flags") or []],
        }
    except Exception as exc:  # schema 1 with junk inside, or a hand-edited ledger
        return error(f"eval.json could not be read: {exc!r}")


# --- odds and ends ---------------------------------------------------------

def _as_list(value: object) -> list:
    """``value`` when it is a list, otherwise an empty one.

    ``or []`` is not enough: a ``rechecks`` or ``dropped_floor_requests`` that
    is a scalar is truthy and then not iterable, which is a ``TypeError`` out
    of a route.
    """
    return list(value) if isinstance(value, list) else []


def _role(doc: dict) -> str:
    """The speaker a reduction names, or "" for anything that is not a name.

    ``isinstance`` rather than ``or ""``: a ``role`` that is a list or a dict --
    only reachable by hand-editing the database, but reachable -- makes
    ``role not in cast.CAST`` a ``TypeError: unhashable type`` out of a route.
    """
    role = doc.get("role")
    return role if isinstance(role, str) else ""


def _turn_no(doc: dict) -> int:
    """The turn number a reduction carries, or 0 if it carries junk."""
    return _int(doc.get("turn")) or 0


def _int(value: object) -> int | None:
    """``value`` when it is an int and not a bool, otherwise None."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _cap(reductions: list[Reduction]) -> int:
    """The turn cap this run actually ran under.

    ``seed`` resolves it once per run into per-run state, which this process
    cannot see, so ``reduce`` puts it on every turn reduction -- the same
    channel, and for the same reason, as the two artifact paths.

    The environment is the FALLBACK, for runs captured before that key existed.
    It is a guess and must not be read as anything else: this function runs in
    the server process, started by a separate ``hermes serve`` that need never
    have had ``HERMES_COMMITTEE_MAX_TURNS`` set, so a run that capped at 20
    rendered "turn 20 of 30".
    """
    # Imported here rather than at module scope: playbook.py imports this
    # module, so importing it back at module scope would be a cycle.
    from playbooks.committee.playbook import DEFAULT_MAX_TURNS, ENV_MAX_TURNS

    for reduction in reversed(reductions):
        doc = reduction.json if isinstance(reduction.json, dict) else {}
        cap = doc.get("cap")
        if isinstance(cap, int) and not isinstance(cap, bool) and cap >= 1:
            return cap

    try:
        cap = int(os.environ.get(ENV_MAX_TURNS, DEFAULT_MAX_TURNS))
    except (TypeError, ValueError):
        return DEFAULT_MAX_TURNS
    return cap if cap >= 1 else DEFAULT_MAX_TURNS


# --- the built bundle ------------------------------------------------------

# Committed next to the source it is built from. Absolute and inside the
# package, so the server never derives a path from a URL. Reached BY PATH and
# never by import: this module shadows the `view/` directory beside it, so
# `playbooks.committee.view` is this file and there is no package to import
# `dist` out of.
DIST = Path(__file__).resolve().parent / "view" / "dist" / "committee.umd.js"


def view_asset() -> Path | None:
    """Absolute path to the built UMD bundle, or None when it is not built."""
    return DIST if DIST.exists() else None
