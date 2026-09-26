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
import math
import os
import re
import stat
from pathlib import Path

from engine import config
from engine.models import Reduction, Run
from playbooks.committee import cast, selection, thread, voice


def view_data(run: Run, reductions: list[Reduction]) -> dict:
    """The whole view payload for one committee run.

    ``run`` is read for exactly one thing -- whether the chair has the floor --
    and its phase name is checked against the static ``DECISION_PHASES``, never
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
    # Every name on screen resolves through the run's own seats (selection D4).
    seats = _seats(run, reductions)
    holder, queue, spoken = _floor(run, turns, decision, seats)
    stances = _stances(turns, seats)

    return {
        "kind": "committee",
        "roster": _roster(spoken, holder, queue, stances, seats),
        "progress": {
            "turn": _turn_no(turns[-1].json) if turns else 0,
            "cap": _cap(reductions),
            "holder": holder,
            "queue": queue,
            "ended": (decision or {}).get("ended"),
        },
        "timeline": [_entry(r.json, seats) for r in turns],
        # No top-level `stances` block: `_stances` feeds `_roster`, which is the
        # only surface that renders a stance. The payload key was typed, fixtured
        # and asserted on both sides of the seam, and read by nothing.
        "verdict": _verdict(decision),
        "document": _document(run, turns, decision_row, lost),
        # selection C6: the stages, who was considered and any fallback. None
        # for a legacy run, a run lost mid-meeting, or one not yet past open.
        "selection": _selection(run, reductions, seats),
        # committee-eval D10/C7: None until the run is scored from this home.
        "evaluation": _evaluation(run.id),
        # voice C11 over the rows eval's voice_summary reads -- the last turn
        # reduction per number, as `_document` folds them, and the latest
        # decision -- so the view and the eval agree on a run. Null for a run
        # reduced before voice existed, which the view says in words.
        "voice": _serialisable(voice.summary(
            [("turn", doc) for doc in {_turn_no(r.json): r.json for r in turns}.values()]
            + ([("decision", decision)] if decision is not None else [])
        )),
    }


# --- the floor -------------------------------------------------------------

def _floor(
    run: Run, turns: list[Reduction], decision: dict | None, seats: dict[str, dict]
) -> tuple[str | None, list[str], list[str]]:
    """Who has spoken, who is waiting, and who holds the floor right now.

    The floor queue is reconstructed rather than read: ``reduce`` records what
    a speaker ASKED for and ``next_phase`` pops the queue FIFO when it grants
    it, so replaying those two rules over the turns in order reproduces the
    queue the state machine holds and this process cannot see.
    """
    # Imported here rather than at module scope: playbook.py imports this
    # module, so importing it back at module scope would be a cycle.
    from playbooks.committee.playbook import DECISION_PHASES

    spoken: list[str] = []
    queue: list[str] = []
    last: str | None = None

    for reduction in turns:
        doc = reduction.json
        role = _role(doc)
        if role not in seats:
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
    elif run.phase in DECISION_PHASES:
        holder = cast.CHAIR  # the chair is writing the verdict, or a retake of it
    else:
        holder = last
    return holder, queue, spoken


def _roster(
    spoken: list[str], holder: str | None, queue: list[str], stances: dict,
    seats: dict[str, dict],
) -> list[dict]:
    """The run's seats and where each of them stands, in roster order.

    ``seats`` is ``_seats``: owner, reviewers in opening order, junior IC, which
    for a legacy run is ``cast.CAST``'s own order. Why a seat is there and who
    put it forward come off its seat record; a legacy persona has neither, so
    all four keys are None.
    """
    # The chair sentinel lights up the reviewer seat it chairs from. Mapped
    # here rather than through `cast.persona`, which raises on a role outside
    # the static cast.
    seat = cast.CHAIR_ROLE if holder == cast.CHAIR else holder
    rows = []
    for role, who in seats.items():
        if role == seat:
            state = "holds_floor"
        elif role in queue:
            state = "queued"
        elif role in spoken:
            state = "spoke"
        else:
            state = "idle"
        said = stances.get(role)
        nominated = _str(who.get("nominated_by")) or None
        # "fixed" and "default" are not people, so they name nobody.
        by = seats.get(nominated) if nominated in _SELECTORS else None
        rows.append({
            "role": role,
            "name": who["name"],
            "title": who["title"],
            "state": state,
            "stance": said[-1]["text"] if said else None,
            "rationale": _str(who.get("rationale")) or None,
            "nominated_by": nominated,
            "nominated_by_name": by["name"] if by else None,
            "source": _str(who.get("source")) or None,
        })
    return rows


# --- the transcript --------------------------------------------------------

def _entry(doc: dict, seats: dict[str, dict]) -> dict:
    """One turn, as the timeline reads it."""
    role = _role(doc)
    who = seats.get(role)
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
        # voice C10. A turn reduced before voice has none of these keys and
        # reads as null / empty: no badge, no metric, never a made-up 0.
        "take": _int(doc.get("take")),
        "takes": _int(doc.get("takes")),
        "violations": _strings(doc.get("violations")),
        "flags": _strings(doc.get("flags")),
        "voice": _serialisable(doc.get("voice")),
        "segments": _segments(doc),
    }


# One oversized answer must not cost a view request seconds and gigabytes, nor
# the browser thousands of drawn figures: past these the body is shown as text.
_SEGMENT_BODY_MAX = 64 * 1024  # characters
_SHA256 = re.compile(r"[0-9a-f]{64}")
_DISARMED = "!\u200b["  # "![" with a zero-width space: Markdown draws no image


def _segments(doc: dict) -> list[dict]:
    """The body as voice.segments splits it, each image's ``ok`` merged in.

    ``ok`` comes from the master's check recorded on the reduction, matched by
    position over the same ordered list of images (mermaid included) that
    ``measure`` recorded, and only onto the reference it was recorded for. It
    is False whenever it is absent: this process never stats a worker's file
    on the master's behalf. A passing image also carries the ``sha256`` the
    master recorded, so the server serves those bytes and no later overwrite.
    Later loops build segments with this, never with voice.segments(body)
    directly.

    At most ``voice.IMAGE_RECORDS`` figures: from the line holding the next
    one, the rest of the body is one text segment. A body over
    ``_SEGMENT_BODY_MAX`` characters is one text segment, never split.

    No "![" leaves here in prose. Image syntax the scan misses stays in a text
    segment, where Markdown would fetch it: a label across lines, a raw tag or
    an autolink outranking a code span. A ``Figure:`` or ``Description:`` line
    is never scanned at all. So every ``text``, ``caption`` and ``description``
    gets a U+200B after the "!", as Diff.tsx does to a document; the view's
    renderer does it again.
    """
    body = doc.get("body") if isinstance(doc.get("body"), str) else ""
    recorded = doc.get("voice") if isinstance(doc.get("voice"), dict) else {}
    checked = recorded.get("images") if isinstance(recorded.get("images"), list) else []
    if len(body) > _SEGMENT_BODY_MAX:
        split = [{"kind": "text", "text": body.strip()}] if body.strip() else []
    else:
        split = voice.segments(body, limit=voice.IMAGE_RECORDS)
    out, index = [], 0
    for seg in split:
        if seg["kind"] in ("image", "mermaid"):
            if seg["kind"] == "image":
                got = checked[index] if index < len(checked) else None
                ok = isinstance(got, dict) and got.get("ok") is True and (
                    (got.get("kind"), got.get("name"), got.get("ref"))
                    == ("image", seg["name"], seg["ref"])
                )
                seg = {**seg, "ok": ok}
                sha = got.get("sha256") if ok else None
                if isinstance(sha, str) and _SHA256.fullmatch(sha):
                    seg["sha256"] = sha
            index += 1
        out.append({key: value.replace("![", _DISARMED)
                    if key in ("text", "caption", "description") else value
                    for key, value in seg.items()})
    return out


def _as_text(seg: dict) -> dict:
    """A mermaid segment as a text segment: its caption, source and description, fenced.

    The fence is longer than any backtick run in the source, so no line of it
    can close the block early.
    """
    source = seg.get("source") or ""
    runs = [len(run) for run in re.findall(r"`+", source)]
    fence = "`" * max(3, max(runs, default=0) + 1)
    lines = [f"Figure: {seg['caption']}"] if seg.get("caption") else []
    lines += [fence, source, fence]
    lines += [f"Description: {seg['description']}"] if seg.get("description") else []
    return {"kind": "text", "text": "\n".join(lines).replace("![", _DISARMED)}


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
    # voice C10: the rules a kept take broke, whether it was retaken, and the
    # three soft flags a reader scans for (``tells``: narration, turn numbers,
    # the unchanged original or hedging; the counts ride on ``voice.tells``).
    if _strings(doc.get("violations")):
        badges.append("voice_flag")
    if (_int(doc.get("takes")) or 1) > 1:
        badges.append("retaken")
    for flag in ("no_pointer", "no_example", "tells"):
        if flag in _strings(doc.get("flags")):
            badges.append(flag)
    return badges


def _stances(turns: list[Reduction], seats: dict[str, dict]) -> dict[str, list[dict]]:
    """Every stance stated, by role, oldest first.

    Absent stays absent: a persona that stated none has no key here at all,
    never an empty list and never a neutral default (spec §7).
    """
    out: dict[str, list[dict]] = {}
    for reduction in turns:
        doc = reduction.json
        role = _role(doc)
        text = doc.get("stance")
        if role in seats and isinstance(text, str) and text.strip():
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
        "takes": _int(decision.get("takes")),
        "violations": _strings(decision.get("violations")),
        "voice": _serialisable(decision.get("voice")),
        # Split and disarmed like a turn body. No image check is passed in, so
        # every file image is refused: the chair may add none, so none is
        # drawn. Nor is a diagram: a chair's mermaid block (a kept take 3 can
        # carry one) would draw a fake "accepted" tile above the real buttons,
        # so it is shown as its source, fenced, in a text segment.
        "segments": [_as_text(seg) if seg["kind"] == "mermaid" else seg
                     for seg in _segments({"body": decision.get("verdict")})],
        # No `simulation` key. It was a constant `True` -- criterion 8 wants the
        # disclaimer to be independent of whether the chair wrote it, and the
        # view satisfies that by rendering the notice UNCONDITIONALLY, which is
        # the fail-safe direction. A flag nothing reads is a flag that can be
        # flipped to False with no test noticing and no notice disappearing.
    }


# --- selection (selection C6) ----------------------------------------------

# The three selectors, whose nominations the roster names by person.
_SELECTORS = (cast.OWNER, "manager", cast.CHAIR_ROLE)
# voice's soft flags. A selector is asked for no pointer or example, so on a
# stage they ride on `flags` and are never badged (orchestrator decision 11).
_SOFT_BADGES = ("no_pointer", "no_example", "tells")


def _final(reductions: list[Reduction]) -> dict | None:
    """The latest ``selection`` reduction with ``final: true``, or None."""
    return next(
        (r.json for r in reversed(reductions)
         if r.kind == "selection" and isinstance(r.json, dict)
         and r.json.get("final") is True),
        None,
    )


def _selection_state(run: Run, reductions: list[Reduction]) -> str | None:
    """seated | fallback | lost | selecting, or None (selection C6).

    The phase is compared, never parsed: while no turn exists, anything that is
    not a static or decision phase is an s-phase or one of its retakes.
    """
    # Imported here rather than at module scope, as in `_floor`: playbook.py
    # imports this module.
    from playbooks.committee.playbook import DECISION_PHASES

    final = _final(reductions)
    if final is not None:
        return "fallback" if _str(final.get("fallback")) else "seated"
    kinds = {r.kind for r in reductions}
    if "turn" in kinds:
        return None  # a legacy run, lost mid-meeting or not
    if "lost" in kinds:
        return "lost"
    if run.phase in (None, "open", "ruling") or run.phase in DECISION_PHASES:
        return None
    return "selecting"


def _seats(run: Run, reductions: list[Reduction]) -> dict[str, dict]:
    """slug -> seat record for this run, read off its reductions alone.

    The ratified roster once the final selection reduction exists; the fixed
    four while selection runs or after it was lost; ``cast.CAST`` for a run
    reduced before selection existed. A seat without a string role, name and
    title is dropped here, so every reader may index those three.
    """
    final = _final(reductions)
    if final is None:
        if _selection_state(run, reductions) in ("selecting", "lost"):
            return selection.fixed_seats()
        return dict(cast.CAST)
    seats: dict[str, dict] = {}
    for seat in _as_list(final.get("seated")):
        if isinstance(seat, dict) and all(
            isinstance(seat.get(key), str) for key in ("role", "name", "title")
        ):
            seats.setdefault(seat["role"], seat)
    return seats


def _selection(
    run: Run, reductions: list[Reduction], seats: dict[str, dict]
) -> dict | None:
    """The Selection card: each kept stage, who was considered, any fallback.

    ``considered_dropped`` and ``invalid_dropped`` count what resolve's caps
    cut, so the card can say how many more there were (decisions 5 and 8).
    """
    state = _selection_state(run, reductions)
    if state is None:
        return None
    final = _final(reductions) or {}
    return {
        "state": state,
        # Only a kept take is a `selection` reduction (a discarded one is a
        # voice `take`), so this is one entry per kept stage, in stage order.
        "stages": [_stage(r.json, seats) for r in reductions
                   if r.kind == "selection" and isinstance(r.json, dict)],
        "fallback": _str(final.get("fallback")) or None,
        "considered": [_considered(c, seats) for c in _as_list(final.get("considered"))
                       if isinstance(c, dict)],
        "considered_dropped": _count(final.get("considered_dropped")),
        "invalid_dropped": _count(final.get("invalid_dropped")),
    }


def _stage(doc: dict, seats: dict[str, dict]) -> dict:
    """One kept stage, with voice's fields as a timeline entry has them."""
    who = seats.get(_role(doc))
    body = doc.get("body")
    return {
        "stage": _int(doc.get("stage")),
        "role": _role(doc),
        "name": who["name"] if who else "unattributed",
        "delivered": bool(doc.get("delivered")),
        "body": body if isinstance(body, str) else "",
        "proposed": [
            {key: _str(p.get(key)) or "" for key in ("role", "name", "title", "rationale")}
            for p in _as_list(doc.get("proposed")) if isinstance(p, dict)
        ],
        "proposed_dropped": _count(doc.get("proposed_dropped")),
        "segments": _segments(doc),
        "badges": [b for b in _badges(doc, attributed=True) if b not in _SOFT_BADGES],
        "take": _int(doc.get("take")),
        "takes": _int(doc.get("takes")),
        "violations": _strings(doc.get("violations")),
        "flags": _strings(doc.get("flags")),
    }


def _considered(entry: dict, seats: dict[str, dict]) -> dict:
    """A stakeholder considered but not seated, and who speaks for them."""
    rep = _str(entry.get("represented_by")) or None
    who = seats.get(rep) if rep else None
    return {
        "stakeholder": _str(entry.get("stakeholder")) or "",
        "role": _str(entry.get("role")) or None,
        "reason": _str(entry.get("reason")) or "",
        "represented_by": rep,
        "represented_by_name": who["name"] if who else None,
    }


def _count(value: object) -> int:
    """A non-negative int count, or 0 for anything else."""
    return max(0, _int(value) or 0)


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
    page, not a 500. Only a missing ``runs/<id>/`` or eval.json is None; a
    symlink at either level (dangling too) is an error, as in ``_size``. Every
    field reaches the UI as the type it renders or null, and no error names an
    absolute path.
    """
    # Imported here rather than at module scope: eval imports playbook, which
    # imports this module, so importing it at module scope would be a cycle.
    from playbooks.committee import eval as ev

    def error(message: str) -> dict:
        return {"state": "error", "error": message}

    def too_big(size: int) -> dict:
        return error(f"eval.json is {size} bytes, over the {ev.EVAL_JSON_MAX}-byte limit")

    path = thread.run_file(run_id, "eval.json")
    try:
        # lstat: a symlinked runs/<id> would render an eval.json from outside
        # this home as this run's.
        if not stat.S_ISDIR(os.lstat(path.parent).st_mode):
            return error(f"runs/{run_id} is not a directory")
        info = os.lstat(path)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:  # strerror, never the path str(exc) carries
        return error(f"eval.json could not be read: {getattr(exc, 'strerror', None) or 'bad path'}")
    if not stat.S_ISREG(info.st_mode):
        return error("eval.json is not a regular file")
    if info.st_size > ev.EVAL_JSON_MAX:
        return too_big(info.st_size)
    data = thread.read_regular(path)
    if data is None:
        return error("eval.json is not a readable regular file")
    if len(data) > ev.EVAL_JSON_MAX:  # it grew between the lstat and the read
        return too_big(len(data))
    try:
        body = json.loads(data.decode("utf-8"))
    # A UnicodeDecodeError is a ValueError too; RecursionError is nesting past
    # json's limit, which a 256 KB file of "[" reaches.
    except (ValueError, RecursionError) as exc:
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
        current = ev.dimension_versions()
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
                "score": ev._score(doc.get("score")),
                "scorer": "judge" if dim in ev.JUDGE_DIMS else "deterministic",
                "quote": _str(next((item.get("quote") for item in doc.get("evidence") or []
                                    if item.get("verified") is True), None)),
                "calibration": label,
                # Why the score is what it is; eval.json keeps up to 4000 characters.
                "rationale": ev.clip(rationale, ev.RATIONALE_MAX)
                if isinstance(rationale := doc.get("rationale"), str) and rationale else None,
                # Scored under an older definition than today's: show and compare star it.
                "stale": rubric.get(dim) != current[dim],
            }
        evaluated_at = body.get("evaluated_at")
        return {
            "state": "ok",
            "rubric_version": _str(body.get("rubric_version")),
            # Finite only: json.loads reads NaN and 1e999, and the route's
            # allow_nan=False serialiser would turn them into a 500 on every poll.
            "evaluated_at": evaluated_at if isinstance(evaluated_at, (int, float))
            and not isinstance(evaluated_at, bool) and math.isfinite(evaluated_at) else None,
            "headline": _str(body.get("headline")),
            "judge_status": _str(judge.get("status")),
            # Not in C7's key list, but its UI table shows "the judge status and
            # error", and nothing else in the payload carries the error. Shown
            # as written: judge.reduce writes it in the master, and the page
            # is the same user's.
            "judge_error": _str(judge.get("error")),
            "dimensions": dimensions,
            "flags": [flag["id"] for flag in _as_list(body.get("flags"))
                      if isinstance(flag, dict) and isinstance(flag.get("id"), str)],
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


def _strings(value: object) -> list[str]:
    """The strings in ``value`` when it is a list, otherwise an empty list."""
    return [v for v in _as_list(value) if isinstance(v, str)]


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


def _str(value: object) -> str | None:
    """``value`` when it is a str, otherwise None: an object is a React crash."""
    return value if isinstance(value, str) else None


def _serialisable(value: object) -> dict | None:
    """``value`` when it is a dict the route's allow_nan=False serialiser takes.

    json.loads reads NaN into a hand-edited ``voice``, which sent on as it is
    turns every poll of the run's page into a 500. None instead: not measured.
    """
    try:
        return value if isinstance(value, dict) and json.dumps(value, allow_nan=False) else None
    except (TypeError, ValueError):
        return None


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
