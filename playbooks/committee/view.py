"""Everything the committee's view renders, assembled from a run's reductions.

The control plane serves this: the view route loads the run's reductions and
hands them here. It runs in the SERVER process, which has never called ``seed``
-- ``_state_by_run`` is empty there -- so nothing in this module may read
playbook instance state. Every number on screen comes off the reductions
``reduce`` already wrote, in the order the queue returns them (``ORDER BY id``),
which is the order they happened in.

One read is not pure and is stated rather than hidden: the size of the two
artifacts. The turn cap rides on the turn reductions; the environment is read
only as a fallback for runs captured before that key existed.

Stdlib-only.
"""
from __future__ import annotations

import os
from pathlib import Path

from engine.models import Reduction, Run
from playbooks.committee import cast


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
    decision = next(
        (r.json for r in reversed(reductions)
         if r.kind == "decision" and isinstance(r.json, dict)),
        None,
    )
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
        "stances": stances,
        "verdict": _verdict(decision),
        "artifacts": _artifacts(reductions),
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
        # Criterion 8, carried as data rather than inferred from the chair's
        # prose: `_SIMULATION` is a sentence a chair could fail to write.
        "simulation": True,
    }


# --- the two files ---------------------------------------------------------

def _artifacts(reductions: list[Reduction]) -> dict:
    """The original and the revised copy, named and sized.

    Both paths ride on the reductions. Nothing here calls
    ``thread.revised_path``, which would create the run's directory as a side
    effect of a GET.
    """
    latest = {"artifact": "", "revised": ""}
    for reduction in reductions:
        doc = reduction.json if isinstance(reduction.json, dict) else {}
        for key in latest:
            value = doc.get(key)
            if isinstance(value, str) and value:
                latest[key] = value

    original = Path(latest["artifact"]) if latest["artifact"] else None
    revised = Path(latest["revised"]) if latest["revised"] else None
    revised_bytes = _size(revised)
    return {
        # DELIBERATELY not symmetric with `revised` below. `original` is null
        # only when no reduction named a path at all; a path that names nothing
        # readable renders 0 bytes rather than null, because spec §6 types this
        # non-nullable and the diff panel has a file name to show either way.
        # The asymmetry is real: "0 bytes" is a claim and absence is not, so an
        # original that has vanished reads as an empty file. `revised` cannot
        # afford that -- a zero-byte revised copy is a state the run can reach.
        "original": (
            {"name": original.name, "bytes": max(_size(original), 0)}
            if original is not None else None
        ),
        # None until the junior IC's copy exists: `seed` records this path on
        # every run, delegation or not, so only the file proves anything.
        "revised": (
            {"name": revised.name, "bytes": revised_bytes}
            if revised is not None and revised_bytes >= 0 else None
        ),
    }


def _size(target: Path | None) -> int:
    """The file's size, or -1 when there is no file there.

    ``-1`` rather than ``0``: a zero-byte revised copy is a real state and must
    not read as "no copy was ever made".
    """
    if target is None:
        return -1
    try:
        return target.stat().st_size if target.is_file() else -1
    except OSError:
        return -1


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
    value = doc.get("turn")
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


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
