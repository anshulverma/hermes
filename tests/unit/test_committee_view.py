"""Tests for the committee's view payload.

Driven by the first live committee run. ``tests/data/committee-run-2-reductions.json``
is all 21 reductions run-2 wrote -- twenty turns and the chair's decision --
copied out of the run database unedited, so these assertions are against what
the playbook really produces rather than against a shape invented here.

That capture predates the six keys ``reduce`` learned for the view (``body``,
``stance``, ``artifact``, ``revised``, ``cap``, ``ended``), so the fixtures
below synthesise those six onto the rows and leave every other value
byte-for-byte as run-2 wrote it. Where a test needs a state run-2 never reached
-- a pending floor request, a meeting still sitting -- it slices or edits the
capture and says so.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.models import Reduction, Run
from playbooks.committee import cast, thread
from playbooks.committee.view import view_data

FIXTURE = Path(__file__).parent.parent / "data" / "committee-run-2-reductions.json"

# Run-2's cap, as the live run was launched: HERMES_COMMITTEE_MAX_TURNS=20.
_CAP = 20

# Synthesised onto three of run-2's turns: the owner speaks at 02 and 20, the
# manager at 04. Every other turn is left with no `stance` key at all. The real
# reduction writes `"stance": None` there rather than omitting it (`_reduce_turn`
# assigns `block.get("stance")` unconditionally); `view.py` reads absent and
# None identically, which is what these turns pin.
_STANCES = {
    2: "conceding the trigger table, holding the line on the delegation half",
    4: "cannot staff it this half; defer",
    20: "I no longer support my own proposal; drop it",
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    """Keep host configuration out of the tests and pin HERMES_HOME to tmp_path."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    for var in (
        "HERMES_COMMITTEE_ARTIFACT",
        "HERMES_COMMITTEE_MAX_TURNS",
        "HERMES_COMMITTEE_DRIVER",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def artifacts(tmp_path):
    """The two files run-2 reviewed, at the sizes the live run measured."""
    original = tmp_path / "federation-future.md"
    original.write_bytes(b"x" * 11397)
    revised = tmp_path / "revised"
    revised.mkdir()
    revised = revised / "federation-future.md"
    revised.write_bytes(b"y" * 19100)
    return original, revised


@pytest.fixture
def run2(artifacts):
    """Run-2's 21 reductions, hydrated the way engine/queue.py does."""
    original, revised = artifacts
    out = []
    for row in json.loads(FIXTURE.read_text(encoding="utf-8")):
        doc = dict(row["json"])
        doc["artifact"] = str(original)
        doc["revised"] = str(revised)
        if row["kind"] == "turn":
            doc["body"] = f"Turn {doc['turn']:02d}, in the speaker's own words."
            doc["cap"] = _CAP
            if doc["turn"] in _STANCES:
                doc["stance"] = _STANCES[doc["turn"]]
        else:
            # Run-2's turn 20 carries `close: true`, and an owner close outranks
            # the cap even when the cap would have stopped the meeting on the
            # next hop: `next_phase` is `"owner closed" if s["closed"] else
            # "turn cap"`. So the meeting ended because the owner closed it --
            # turn 20 is headed "Closing: the record." -- not because it ran out.
            doc["ended"] = "owner closed"
        out.append(Reduction(kind=row["kind"], json=doc, phase=row["phase"]))
    return out


def _run(phase: str) -> Run:
    """A Run snapshot at one phase. The view reads nothing else off it."""
    return Run(
        id="committee-20260919-000000",
        playbook="committee",
        site="local",
        base_ref="main",
        config={},
        phase=phase,
        reductions=[],
    )


# --- the shape --------------------------------------------------------------

def test_view_data_returns_every_block_the_contract_names(run2):
    data = view_data(_run("decision"), run2)

    assert set(data) == {
        "kind", "roster", "progress", "timeline", "verdict", "document",
    }
    assert data["kind"] == "committee"
    assert len(data["roster"]) == 9
    assert all(
        set(row) == {"role", "name", "title", "state", "stance"}
        for row in data["roster"]
    )
    assert set(data["progress"]) == {"turn", "cap", "holder", "queue", "ended"}
    assert len(data["timeline"]) == 20
    assert all(
        set(entry) == {
            "n", "role", "name", "title", "body", "action", "badges", "verified", "stance",
        }
        for entry in data["timeline"]
    )
    assert set(data["document"]) == {
        "name", "captured", "original", "steps", "final", "dropped_delegation",
    }


def test_the_timeline_reads_oldest_first_and_names_every_speaker(run2):
    """Criterion 6. Outputs.tsx sorts newest-first, which is exactly backwards
    for a conversation; the view's own order is the reduction order."""
    timeline = view_data(_run("decision"), run2)["timeline"]

    assert [entry["n"] for entry in timeline] == list(range(1, 21))
    assert timeline[0]["role"] == "senior_director"
    assert timeline[0]["name"] == "Dana Whitfield"
    assert timeline[0]["title"] == "Senior Director of Engineering"
    assert timeline[0]["body"] == "Turn 01, in the speaker's own words."
    assert timeline[-1]["role"] == "owner"
    assert timeline[-1]["name"] == "Maya Okonkwo"
    # the owner answers every reviewer: seven reviewer turns, seven owner replies
    assert [e["role"] for e in timeline].count("owner") == 7


def test_a_delegated_turn_carries_its_action_and_its_recheck(run2):
    """Criterion 7, both halves: the delegated edit AND its outcome.

    The action is the half that was missing. It rides on the turn reduction and
    on the decision's `rechecks`, but the decision does not exist until the
    meeting ends -- nineteen turns later on the measured run -- so a timeline
    that drops it shows a delegation with nothing said about what was delegated.

    The badges are the reduction's own key names, not phrases: `delegate`, not
    "delegated". Task 8 keys `BADGE_LABEL`/`BADGE_TONE` on these exact strings.
    There is no "edit applied" badge because `verified` on the same entry
    already says it, and the view renders that separately.
    """
    timeline = view_data(_run("decision"), run2)["timeline"]
    delegating = timeline[1]   # t02-owner delegated the first rewrite
    edit = timeline[2]         # t03-junior_ic applied it
    reviewer = timeline[0]     # t01-senior_director did neither

    assert delegating["role"] == "owner"
    assert delegating["badges"] == ["delegate"]
    assert delegating["action"].startswith('Rewrite §2 "When to reach for it"')
    assert delegating["verified"] is None

    assert edit["role"] == "junior_ic"
    assert edit["badges"] == []
    assert edit["action"] is None
    assert edit["verified"] is True

    assert reviewer["badges"] == []
    assert reviewer["action"] is None
    assert reviewer["verified"] is None


def test_a_failed_recheck_and_an_undelivered_turn_are_badged_as_failures(run2):
    """A re-check that did not apply must read as a failure, not as silence,
    and a turn that carried only its signal block is not a failed turn."""
    from playbooks.committee.playbook import _SIGNALS_ONLY

    failed = dict(run2[2].json, verified=False)
    silent = dict(run2[3].json, delivered=False, body="", error="thread: disk full")
    # t01: every flag false, so `signals_only` is the whole badge list.
    signals = dict(run2[0].json, body=_SIGNALS_ONLY)
    reductions = [
        Reduction(kind="turn", json=failed),
        Reduction(kind="turn", json=silent),
        Reduction(kind="turn", json=signals),
    ]

    timeline = view_data(_run("t04-manager"), reductions)["timeline"]

    # The failure is `verified`, which the view renders as DID NOT APPLY. No
    # badge duplicates it.
    assert timeline[0]["badges"] == []
    assert timeline[0]["verified"] is False
    assert timeline[1]["badges"] == ["no_turn", "error"]
    assert timeline[1]["body"] == ""
    assert timeline[2]["badges"] == ["signals_only"]
    assert timeline[2]["verified"] is None


# --- the roster and the floor ----------------------------------------------

def test_the_roster_carries_all_four_states(run2):
    """Four seats, four states, one mid-meeting slice.

    Run-2 never had a pending floor request -- nobody asked -- so turn 01's
    request_floor is flipped here to produce the queued case.
    """
    mid = run2[:4]                              # t01..t04, the meeting still sitting
    mid[0].json["request_floor"] = True         # the senior director wants a second turn

    data = view_data(_run("t04-manager"), mid)
    state = {row["role"]: row["state"] for row in data["roster"]}

    assert state == {
        "senior_director": "queued",     # spoke, then asked for the floor again
        "manager": "holds_floor",        # the last turn to settle
        "owner": "spoke",
        "junior_ic": "spoke",
        "tpm": "idle",
        "pm": "idle",
        "tl": "idle",
        "staff_ic": "idle",
        "data_scientist": "idle",
    }
    assert data["progress"]["holder"] == "manager"
    assert data["progress"]["queue"] == ["senior_director"]


def test_a_granted_floor_request_leaves_the_queue(run2):
    """next_phase pops the queue when it grants the floor; so does this."""
    mid = run2[:4]
    mid[0].json["request_floor"] = True

    # ...and then the senior director speaks again, asking for nothing.
    again = dict(mid[0].json, turn=5, request_floor=False)
    data = view_data(_run("t05-senior_director"), mid + [Reduction(kind="turn", json=again)])

    assert data["progress"]["queue"] == []
    assert data["progress"]["holder"] == "senior_director"


def _copy(reductions: list[Reduction]) -> list[Reduction]:
    """The slice, with its docs copied, so an edit cannot leak between tests."""
    return [Reduction(kind=r.kind, json=dict(r.json), phase=r.phase) for r in reductions]


def test_a_turn_nobody_delivered_neither_spoke_nor_holds_the_floor(run2):
    """The roster must not contradict the transcript on the same screen.

    ``_apply_block`` runs none of the gates on an undelivered turn and hands the
    floor back to the owner, precisely so ``next_phase`` moves on instead of
    sending someone to answer a stub. Without the same guard here the seat is
    badged "spoke" -- above a transcript entry reading "no turn delivered" --
    and mid-run it is handed the floor as well.
    """
    mid = _copy(run2[:4])
    mid[-1].json.update(delivered=False, body="")  # t04-manager produced nothing

    data = view_data(_run("t04-manager"), mid)
    state = {row["role"]: row["state"] for row in data["roster"]}

    assert state["manager"] == "idle"                  # never spoke
    assert data["progress"]["holder"] == cast.OWNER    # the floor went back
    assert state["owner"] == "holds_floor"
    assert data["timeline"][-1]["badges"] == ["no_turn"]


def test_a_granted_floor_request_leaves_the_queue_even_when_the_turn_fails(run2):
    """``next_phase`` pops the queue when it MINTS the turn, so a worker that
    then produced nothing still burned the floor it was granted. The decision's
    ``dropped_floor_requests`` reads the same way, and these two must agree."""
    mid = _copy(run2[:4])
    mid[0].json["request_floor"] = True
    failed = dict(mid[0].json, turn=5, request_floor=False, delivered=False, body="")

    data = view_data(
        _run("t05-senior_director"), mid + [Reduction(kind="turn", json=failed)]
    )

    assert data["progress"]["queue"] == []
    assert data["progress"]["holder"] == cast.OWNER


def test_the_floor_queue_closes_with_the_meeting(run2):
    """A seat still "waiting to speak" after the verdict is waiting for a turn
    that will never come. The verdict card already tells that story in the past
    tense, off the decision's own ``dropped_floor_requests``."""
    run2[0].json["request_floor"] = True  # never granted; the meeting ended first

    data = view_data(_run("decision"), run2)

    assert data["progress"]["queue"] == []
    assert data["progress"]["holder"] is None
    assert [row["role"] for row in data["roster"] if row["state"] == "queued"] == []


def test_the_chair_holds_the_floor_while_the_decision_is_running(run2):
    """Between the last turn and the verdict the chair is speaking, and the
    seat they chair from is the one that lights up."""
    data = view_data(_run("decision"), run2[:20])
    state = {row["role"]: row["state"] for row in data["roster"]}

    assert data["progress"]["holder"] == cast.CHAIR == "chair"
    assert state["senior_director"] == "holds_floor"
    assert data["verdict"] is None


def test_progress_counts_the_turns_against_the_cap_the_run_used(run2, monkeypatch):
    """The cap rides on the reductions, NOT on this process's environment.

    ``view_data`` runs in the server process, which is a separate
    ``hermes serve`` that need never have seen the master's environment. The
    env is set to a different value here on purpose: reading it would render
    "turn 20 of 30" for a run that capped at 20 and used all of it.
    """
    monkeypatch.setenv("HERMES_COMMITTEE_MAX_TURNS", "30")

    progress = view_data(_run("decision"), run2)["progress"]

    assert progress["turn"] == 20
    assert progress["cap"] == _CAP == 20
    assert progress["holder"] is None  # the meeting is over
    assert progress["ended"] == "owner closed"


def test_a_run_captured_before_the_cap_key_falls_back_to_the_environment(
    run2, monkeypatch
):
    """Legacy runs -- every committee run already in the database -- carry no
    `cap`, and the environment is all there is. Stated, not hidden."""
    monkeypatch.setenv("HERMES_COMMITTEE_MAX_TURNS", "12")
    for reduction in run2:
        reduction.json.pop("cap", None)

    assert view_data(_run("decision"), run2)["progress"]["cap"] == 12


# --- stances ----------------------------------------------------------------

def test_the_roster_carries_the_latest_stance_and_absent_stays_absent(run2):
    """Criterion 10. A persona that stated none has no stance at all -- not an
    empty string, and never a neutral default.

    `roster[].stance` is the only place a stance reaches the screen. There used
    to be a top-level `stances` block beside it carrying every stance ever
    filed; it was typed, fixtured and asserted on both sides and rendered by
    nothing.
    """
    data = view_data(_run("decision"), run2)
    stance = {row["role"]: row["stance"] for row in data["roster"]}

    assert stance["owner"] == _STANCES[20]   # the latest, not the first
    assert stance["manager"] == _STANCES[4]
    assert stance["tl"] is None
    assert stance["senior_director"] is None


# --- the verdict ------------------------------------------------------------

def test_the_verdict_is_absent_until_the_decision_settles(run2):
    assert view_data(_run("t20-owner"), run2[:20])["verdict"] is None


def test_the_verdict_carries_the_chairs_text_the_rechecks_and_the_disclaimer(run2):
    """Criterion 8: the simulation disclaimer is data, not a sentence the view
    has to find in the chair's prose."""
    verdict = view_data(_run("decision"), run2)["verdict"]

    assert verdict["text"].startswith("I've read the artifact, the revised copy")
    assert verdict["artifact_intact"] is True
    assert verdict["dropped_delegation"] is None
    assert verdict["dropped_floor_requests"] == []
    assert [check["turn"] for check in verdict["checks"]] == [3, 6, 9, 12, 15, 18]
    assert all(check["verified"] is True for check in verdict["checks"])


@pytest.mark.parametrize(
    "ended", ["owner closed", "queue empty", "turn cap", "chair turn failed"]
)
def test_progress_names_why_the_meeting_stopped(run2, ended):
    """Criterion 11. The first live run ended with nothing on screen saying why."""
    run2[-1].json["ended"] = ended

    assert view_data(_run("decision"), run2)["progress"]["ended"] == ended


# --- the edges --------------------------------------------------------------

def test_a_run_with_no_reductions_renders_an_empty_meeting():
    """`open` is a zero-ticket bootstrap, so the first poll sees nothing."""
    data = view_data(_run("open"), [])

    assert data["timeline"] == []
    assert data["verdict"] is None
    assert data["document"] == {
        "name": None, "captured": False, "original": None, "steps": [],
        "final": None, "dropped_delegation": None,
    }
    # 30 is DEFAULT_MAX_TURNS, pinned literally: it is what a reader compares
    # the turn count against.
    assert data["progress"] == {
        "turn": 0, "cap": 30, "holder": None, "queue": [], "ended": None,
    }
    assert {row["state"] for row in data["roster"]} == {"idle"}
    assert all(row["stance"] is None for row in data["roster"])


def test_an_unattributable_turn_is_named_as_such_and_moves_nothing(run2):
    """`_reduce_turn` fails closed when it cannot name the speaker, writing
    role "". The view must not hand that turn to a persona either."""
    orphan = dict(
        run2[0].json,
        role="",
        stance="I am nobody",
        error="speaker: the turn could not be attributed",
    )

    data = view_data(_run("t01-senior_director"), [Reduction(kind="turn", json=orphan)])
    entry = data["timeline"][0]

    assert entry["role"] == ""
    assert entry["name"] == "unattributed"
    assert entry["title"] == ""
    assert entry["n"] == 1
    assert entry["badges"] == ["unattributed", "error"]
    # nobody spoke, nobody holds the floor, and no stance was recorded
    assert {row["state"] for row in data["roster"]} == {"idle"}
    assert data["progress"]["holder"] is None
    assert all(row["stance"] is None for row in data["roster"])


def test_view_data_does_not_raise_on_a_reduction_no_reduce_would_write(run2):
    """Four out-of-contract shapes, all reachable only by hand-editing the DB.

    `view_data` runs inside a route, so a raise here is a 500 on a run's page.
    Every one of these was a TypeError before: `reductions=None`; a `role` that
    is unhashable; and `rechecks` / `dropped_floor_requests` as scalars, which
    are truthy and then not iterable.
    """
    assert view_data(_run("open"), None)["timeline"] == []

    hostile = [
        Reduction(kind="turn", json=dict(run2[0].json, role=["senior_director"])),
        Reduction(kind="turn", json=dict(run2[1].json, role={"role": "owner"})),
        Reduction(kind="decision", json=dict(
            run2[-1].json, rechecks=7, dropped_floor_requests="tpm")),
    ]

    data = view_data(_run("decision"), hostile)

    assert [entry["name"] for entry in data["timeline"]] == ["unattributed"] * 2
    assert data["verdict"]["checks"] == []
    assert data["verdict"]["dropped_floor_requests"] == []


# --- the document's versions (doc-diff C3) --------------------------------------

RUN_ID = "committee-20260919-000000"  # what `_run` builds


def _steps(reductions):
    """{turn: (owner_turn, reviewer_turn, provenance)} off the document block."""
    return {
        step["turn"]: (step["owner_turn"], step["reviewer_turn"], step["provenance"])
        for step in view_data(_run("decision"), reductions)["document"]["steps"]
    }


def test_the_document_sizes_every_version_under_this_process_home(run2, tmp_path):
    """Never at a path a reduction recorded: those are the master's host paths.

    The snapshot is 11000 bytes and the host original 11397, so a size read off
    the recorded path -- a 404 inside a container -- cannot pass for this one.
    """
    thread.write_snapshot(RUN_ID, "doc/00-original.md", b"o" * 11000)
    for turn in (3, 6, 9, 12):
        thread.write_snapshot(RUN_ID, f"doc/t{turn:02d}.md", b"e" * (11397 + turn))
    doc = tmp_path / "runs" / RUN_ID / "doc"
    (doc / "t15.md").symlink_to(doc / "t12.md")  # the route refuses it; so does the size
    # t18 was never written: "could not read", never "no edit was made".

    document = view_data(_run("decision"), run2)["document"]

    assert document["name"] == "federation-future.md"
    assert document["captured"] is True
    assert document["original"] == {"path": "doc/00-original.md", "bytes": 11000}
    assert [step["turn"] for step in document["steps"]] == [3, 6, 9, 12, 15, 18]
    assert document["steps"][0] == {
        "turn": 3, "path": "doc/t03.md", "bytes": 11400, "delivered": True,
        "verified": True, "owner_turn": 2, "reviewer_turn": 1, "provenance": "inferred",
    }
    assert document["steps"][4]["bytes"] is None   # the symlink
    assert document["steps"][5]["bytes"] is None   # never written
    assert document["final"] == {
        "path": "doc/t18.md", "turn": 18, "bytes": None, "ruling": "awaiting_ruling",
    }
    assert document["dropped_delegation"] is None


def test_a_run_whose_versions_were_never_captured_says_so(run2, artifacts):
    """Run-9 before its backfill: a document name, the host files still at the
    recorded paths, and nothing under ``runs/<id>/doc/``. The view branches on
    ``captured``; the host copies must not make it True."""
    assert all(path.is_file() for path in artifacts)

    document = view_data(_run("decision"), run2)["document"]

    assert document["name"] == "federation-future.md"
    assert document["captured"] is False
    assert document["original"] == {"path": "doc/00-original.md", "bytes": None}
    assert [step["bytes"] for step in document["steps"]] == [None] * 6
    assert document["final"]["bytes"] is None


def test_a_zero_byte_version_is_sized_zero_not_missing(run2):
    thread.write_snapshot(RUN_ID, "doc/00-original.md", b"")

    document = view_data(_run("decision"), run2)["document"]

    assert document["original"]["bytes"] == 0
    assert document["captured"] is True


@pytest.mark.parametrize("level", ["doc", "run"])
def test_a_symlinked_directory_sizes_nothing_as_the_route_serves_nothing(
    run2, tmp_path, level
):
    """The route opens ``runs/<id>/`` and ``doc/`` without following a symlink,
    so a size for a file behind one would promise a read that then fails."""
    thread.write_snapshot(RUN_ID, "doc/00-original.md", b"o" * 11000)
    run_dir = tmp_path / "runs" / RUN_ID
    moved = run_dir / "doc" if level == "doc" else run_dir
    moved.rename(tmp_path / "elsewhere")
    moved.symlink_to(tmp_path / "elsewhere", target_is_directory=True)

    document = view_data(_run("decision"), run2)["document"]

    assert document["original"]["bytes"] is None
    assert document["captured"] is False


def test_steps_ascend_by_turn_and_a_turn_settled_twice_keeps_its_last_reduction(run2):
    retake = Reduction(kind="turn", json=dict(run2[2].json, verified=False))  # t03 again
    shuffled = list(reversed(run2[:-1])) + [retake, run2[-1]]

    steps = view_data(_run("decision"), shuffled)["document"]["steps"]

    assert [step["turn"] for step in steps] == [3, 6, 9, 12, 15, 18]
    assert steps[0]["verified"] is False


def test_final_is_the_last_step_that_applied_or_else_the_original(run2):
    run2[17].json["verified"] = False  # t18 did not apply
    final = view_data(_run("decision"), run2)["document"]["final"]
    assert (final["path"], final["turn"]) == ("doc/t15.md", 15)

    for reduction in run2:
        if reduction.json.get("role") == "junior_ic":
            reduction.json["verified"] = False
    final = view_data(_run("decision"), run2)["document"]["final"]
    assert (final["path"], final["turn"]) == ("doc/00-original.md", None)

    no_edits = [r for r in run2 if r.json.get("role") != "junior_ic"]
    document = view_data(_run("decision"), no_edits)["document"]
    assert document["steps"] == []
    assert document["final"] is None


def test_a_dropped_delegation_is_a_note_naming_its_owner_turn_never_a_step(run2):
    run2[-1].json.update(dropped_delegation="Fold §9 into §8", dropped_delegation_turn=20)
    document = view_data(_run("decision"), run2)["document"]
    assert document["dropped_delegation"] == {"owner_turn": 20, "action": "Fold §9 into §8"}
    assert [step["turn"] for step in document["steps"]] == [3, 6, 9, 12, 15, 18]

    del run2[-1].json["dropped_delegation_turn"]  # a decision from before the key
    assert view_data(_run("decision"), run2)["document"]["dropped_delegation"] == {
        "owner_turn": None, "action": "Fold §9 into §8",
    }


def test_every_timeline_entry_carries_its_stance(run2):
    run2[5].json["stance"] = "   "  # t06: blank is no stance
    run2[6].json["stance"] = "  padded  "  # t07: stated, and trimmed
    timeline = view_data(_run("decision"), run2)["timeline"]

    assert timeline[1]["stance"] == _STANCES[2]
    assert timeline[3]["stance"] == _STANCES[4]
    assert timeline[0]["stance"] is None  # no key at all
    assert timeline[5]["stance"] is None
    assert timeline[6]["stance"] == "padded"


def test_reductions_without_the_keys_are_placed_by_turn_order(run2):
    """Run-2 and run-9 predate `delegated_by_turn`: reviewer N-2, owner N-1."""
    assert _steps(run2) == {
        3: (2, 1, "inferred"), 6: (5, 4, "inferred"), 9: (8, 7, "inferred"),
        12: (11, 10, "inferred"), 15: (14, 13, "inferred"), 18: (17, 16, "inferred"),
    }


def test_a_broken_turn_order_is_unknown_rather_than_guessed(run2):
    run2[1].json["delegate"] = False           # t02 delegated nothing
    run2[3].json["delivered"] = False          # t04's reviewer never spoke
    run2[8].json["delegated_by_turn"] = None   # t09: recorded as not applicable

    steps = _steps(run2)

    assert steps[3] == (None, None, "unknown")
    assert steps[6] == (5, None, "inferred")
    assert steps[9] == (None, None, "unknown")


@pytest.mark.parametrize("seat", [cast.OWNER, cast.JUNIOR])
def test_turn_order_names_a_reviewer_only_from_a_reviewer_seat(run2, seat):
    """N-2 answered nothing unless a reviewer spoke it: the owner and the junior
    IC hold no reviewer seat."""
    run2[0].json["role"] = seat  # t01, two turns before t03

    assert _steps(run2)[3] == (2, None, "inferred")


def test_only_a_delegate_of_true_is_a_delegation_to_infer_from(run2):
    """``is not True``, so 1 -- equal to True, and truthy -- is not one."""
    run2[1].json["delegate"] = 1  # t02

    assert _steps(run2)[3] == (None, None, "unknown")


def test_a_recorded_link_wins_over_turn_order(run2):
    run2[5].json["delegated_by_turn"] = 2  # t06 applied t02's delegation
    run2[1].json["answers_turn"] = 1
    run2[8].json["delegated_by_turn"] = 8  # t08 carries no answers_turn key

    steps = _steps(run2)

    assert steps[6] == (2, 1, "recorded")
    assert steps[9] == (8, None, "recorded")


def _stamped(reductions, state):
    return reductions[:-1] + [
        Reduction(kind="decision", json=reductions[-1].json, review_state=state)
    ]


@pytest.mark.parametrize("change, ruling", [
    (lambda rs: rs[:-1], "in_session"),
    (lambda rs: rs, "awaiting_ruling"),
    (lambda rs: _stamped(rs, "accepted"), "accepted"),
    (lambda rs: _stamped(rs, "rejected"), "rejected"),
    (lambda rs: _stamped(rs, "superseded"), "no_ruling"),
    (lambda rs: rs + [Reduction(kind="lost", json={"error": "gone"})], "no_ruling"),
    (lambda rs: rs[:-1] + [
        Reduction(kind="decision", json=dict(rs[-1].json, delivered=False))], "no_ruling"),
], ids=["in_session", "awaiting", "accepted", "rejected", "superseded", "lost", "chair_failed"])
def test_final_is_labelled_by_how_the_ruling_stands(run2, change, ruling):
    assert view_data(_run("decision"), change(run2))["document"]["final"]["ruling"] == ruling


def test_view_data_creates_nothing_under_the_home(run2, tmp_path):
    view_data(_run("decision"), run2)
    view_data(_run("open"), [])

    assert not (tmp_path / "runs").exists()
