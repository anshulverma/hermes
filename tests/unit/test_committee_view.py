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
from playbooks.committee import cast, thread, voice
from playbooks.committee import eval as ev
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
        "kind", "roster", "progress", "timeline", "verdict", "document", "evaluation",
        "voice",
    }
    assert data["evaluation"] is None  # never scored: no runs/<id>/eval.json
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
            "take", "takes", "violations", "flags", "voice", "segments",
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


def test_the_chair_holds_the_floor_during_a_decision_retake(run2):
    data = view_data(_run("decision-take2"), run2[:20])

    assert data["progress"]["holder"] == cast.CHAIR


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


def test_an_edit_readable_without_its_original_keeps_the_run_captured(run2):
    """Every worker runs bypassPermissions and can delete doc/00-original on a
    new run. The edit snapshots it left are still worth stepping through; only
    Original and Edit 1, which need the original, say they could not read it."""
    thread.write_snapshot(RUN_ID, "doc/t03.md", b"after t03\n")

    document = view_data(_run("decision"), run2)["document"]

    assert document["captured"] is True
    assert document["original"]["bytes"] is None
    assert document["steps"][0]["bytes"] == 10


def test_a_step_reads_delivery_and_its_recheck_as_recorded(run2):
    run2[5].json["delivered"] = False   # t06: the junior never delivered
    run2[8].json["verified"] = "junk"   # t09: no boolean re-check
    del run2[11].json["verified"]       # t12: no re-check key at all

    steps = view_data(_run("decision"), run2)["document"]["steps"]

    assert steps[1]["delivered"] is False
    assert steps[2]["verified"] is None
    assert steps[3]["verified"] is None


def test_before_any_turn_settles_the_document_is_named_from_the_thread_header():
    """`open` writes doc/00-original and the header, then the first worker can
    run for an hour with no reduction naming the file. The header is the
    master's own record of the artifact `open` resolved."""
    thread.write_header(RUN_ID, charge="Decide.", artifact="/host/repo/docs/proposal.md",
                        roster=["owner — Maya Okonkwo"])
    # run-6/7/8: stopped at open before doc/ existed -- named, nothing to show.
    assert view_data(_run("t01-senior_director"), [])["document"]["captured"] is False

    thread.write_snapshot(RUN_ID, "doc/00-original.md", b"# Proposal\n")
    document = view_data(_run("t01-senior_director"), [])["document"]

    assert document == {
        "name": "proposal.md", "captured": True,
        "original": {"path": "doc/00-original.md", "bytes": 11},
        "steps": [], "final": None, "dropped_delegation": None,
    }
    # Only before the first turn: a legacy run's turns that name no file stay
    # unnamed, whatever its thread says.
    legacy = [Reduction(kind="turn", json={"turn": 1, "role": "senior_director", "delivered": True})]
    assert view_data(_run("t02-owner"), legacy)["document"]["name"] is None


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
    # The realistic lost run: it died at a turn, before any decision existed.
    (lambda rs: rs[:-1] + [Reduction(kind="lost", json={"error": "gone"})], "no_ruling"),
    (lambda rs: rs[:-1] + [
        Reduction(kind="decision", json=dict(rs[-1].json, delivered=False))], "no_ruling"),
], ids=["in_session", "awaiting", "accepted", "rejected", "superseded", "lost",
        "lost_before_decision", "chair_failed"])
def test_final_is_labelled_by_how_the_ruling_stands(run2, change, ruling):
    assert view_data(_run("decision"), change(run2))["document"]["final"]["ruling"] == ruling


def test_view_data_creates_nothing_under_the_home(run2, tmp_path):
    view_data(_run("decision"), run2)
    view_data(_run("open"), [])

    assert not (tmp_path / "runs").exists()


# --- voice (C10) ---------------------------------------------------------------

def _voiced(n, role, body, **over):
    """A turn reduction as voice's `_reduce_turn` writes it."""
    metrics = voice.measure(body, role)
    doc = {
        "role": role, "turn": n, "delivered": True, "body": body, "stance": None,
        "artifact": "/x/proposal.md", "revised": "/x/revised/proposal.md", "cap": 30,
        "request_floor": False, "delegate": False, "close": False, "action": None,
        "verified": None, "answers_turn": None, "delegated_by_turn": None, "error": None,
        "take": 1, "takes": 1, "kept": True, "voice": metrics,
        "violations": voice.violations(metrics, role), "flags": voice.flags(metrics, role),
    }
    doc.update(over)
    return Reduction(kind="turn", json=doc, phase=f"t{n:02d}-{role}")


_FIGURES = (
    "Staffing is the risk.\n"
    "![staffing curve](images/t02-owner.svg)\n"
    "Description: engineers per week, flat after week 6.\n"
    "Figure: the pipeline\n"
    "```mermaid\ngraph TD; A-->B\n```\n"
    "Description: two stages."
)


def test_a_voiced_entry_carries_its_take_its_rules_and_its_badges():
    kept = _voiced(2, "owner", "Word " * 160, takes=3, take=3,
                   violations=["over_cap"], flags=["no_pointer", "no_example"])
    entry = view_data(_run("t03-tpm"), [kept])["timeline"][0]

    assert (entry["take"], entry["takes"]) == (3, 3)
    assert entry["violations"] == ["over_cap"]
    assert entry["flags"] == ["no_pointer", "no_example"]
    assert entry["voice"]["words"] == 160
    assert entry["badges"] == ["voice_flag", "retaken", "no_pointer", "no_example"]


def test_segments_merge_the_masters_image_check_by_position():
    doc = _voiced(2, "owner", _FIGURES)
    doc.json["voice"]["images"][0]["ok"] = True
    entry = view_data(_run("t03-tpm"), [doc])["timeline"][0]

    assert [s["kind"] for s in entry["segments"]] == ["text", "image", "mermaid"]
    assert entry["segments"][1] == {
        "kind": "image", "name": "t02-owner.svg", "ref": "images/t02-owner.svg",
        "caption": "staffing curve", "description": "engineers per week, flat after week 6.",
        "ok": True,
    }
    assert entry["segments"][2]["source"] == "graph TD; A-->B"

    unchecked = _voiced(2, "owner", _FIGURES)
    unchecked.json.pop("voice")
    image = view_data(_run("t03-tpm"), [unchecked])["timeline"][0]["segments"][1]
    assert image["ok"] is False  # absent means refused, never assumed

    # A recorded image the master never passed stays refused: measure leaves
    # ok None, and check_images writes False for a foreign or missing file.
    for ok in (None, False):
        refused = _voiced(2, "owner", _FIGURES)
        refused.json["voice"]["images"][0]["ok"] = ok
        image = view_data(_run("t03-tpm"), [refused])["timeline"][0]["segments"][1]
        assert image["ok"] is False, ok

    # A pass rides only onto the reference it was recorded for, never onto
    # whatever sits at its position when the body is split again.
    drifted = _voiced(2, "owner", _FIGURES)
    drifted.json["voice"]["images"][0].update(
        ok=True, name="t09-tl.svg", ref="images/t09-tl.svg")
    image = view_data(_run("t03-tpm"), [drifted])["timeline"][0]["segments"][1]
    assert image["ok"] is False


def test_a_legacy_entry_has_no_voice_and_no_badge(run2):
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))[0]  # run-2 as written: no body
    entry = view_data(_run("decision"), [Reduction(kind="turn", json=raw["json"])])["timeline"][0]

    assert (entry["take"], entry["takes"], entry["voice"]) == (None, None, None)
    assert entry["violations"] == [] and entry["flags"] == [] and entry["segments"] == []
    assert not {"voice_flag", "retaken", "no_pointer", "no_example"} & set(entry["badges"])
    assert view_data(_run("decision"), run2)["voice"] is None


def test_take_reductions_stay_out_of_the_timeline_and_the_floor():
    first = _voiced(1, "tl", "Defer it: `a.py:1` for example.")
    take = Reduction(kind="take", json={"phase": "t02-owner", "role": "owner", "turn": 2,
                                        "take": 1, "kept": False, "delivered": True,
                                        "body": "x", "request_floor": True},
                     phase="t02-owner")
    data = view_data(_run("t02-owner-take2"), [first, take])

    assert [e["n"] for e in data["timeline"]] == [1]
    assert data["progress"]["holder"] == "tl" and data["progress"]["queue"] == []


def test_the_top_level_voice_summarises_kept_rows_and_the_verdict_says_how_it_was_kept():
    turn = _voiced(1, "tl", "Defer it: `a.py:1` for example.")
    decision = Reduction(kind="decision", json={
        "verdict": "Approve.\n\n![x](http://evil.example/a.png)", "delivered": True,
        "rechecks": [], "takes": 2, "violations": ["too_many_images"],
        "voice": {"words": 1, "cap": 300}, "ended": "queue empty",
    }, phase="decision-take2", review_state="pending")
    data = view_data(_run("decision-take2"), [turn, decision])

    assert data["voice"]["owner_reviewer_median_words"] == 5.0
    assert data["voice"]["chair_words"] == 1
    verdict = data["verdict"]
    assert verdict["takes"] == 2 and verdict["violations"] == ["too_many_images"]
    assert verdict["voice"] == {"words": 1, "cap": 300}
    assert [s["kind"] for s in verdict["segments"]] == ["text", "image"]
    assert verdict["segments"][1]["ok"] is False


# --- the evaluation (committee-eval D10, C7) ------------------------------------

def _eval_body(home: str, run: str, created_at: float, versions: dict) -> dict:
    """One eval.json body in committee-eval's C5 shape, schema 1.

    Judge scores 2 / null / 3, deterministic 3 / 1 / 1. edits_address_concerns
    is the judge dimension none of whose evidence verified, so it carries no
    score and no quote: a partial judge.
    """
    def item(where, quote, verified, turn=None):
        return {"turn": turn, "where": where, "line": None, "quote": quote,
                "verified": verified}

    def dim(scorer, score, evidence, error=None):
        return {"scorer": scorer, "score": score, "rationale": "stated",
                "evidence": evidence, "error": error}

    return {
        "schema": 1,
        "rubric_version": ev.rubric_version(versions),
        "rubric": dict(versions),
        "target": {"home": home, "run": run, "created_at": created_at,
                   "playbook": "committee", "state": "done",
                   "review_state": "pending", "legacy": False},
        "eval_run": f"committee-eval-{run}",
        "evaluated_at": 1790000000.5,
        "original_source": "snapshot",
        "metrics": {},
        "flags": [
            {"id": "action_clipped", "turn": 3, "line": 812, "quote": "the last forty chars"},
            {"id": "verdict_count_mismatch", "turn": None, "line": 820, "quote": "seven of",
             "claimed": 7, "recorded": 8},
        ],
        "dimensions": {
            "verdict_grounded": dim("judge", 2, [
                item("turn", "a quote nobody wrote", False, 12),
                item("decision", "Approve with changes.", True),
            ]),
            "edits_address_concerns": dim(
                "judge", None, [item("turn", "invented", False, 6)], "no verifiable evidence"),
            "concern_coverage": dim("judge", 3, [item("turn", "Fair point.", True, 2)]),
            "efficiency": dim("deterministic", 3, [item("metric", "cost_usd=30.3875", True)]),
            "concision": dim("deterministic", 1, [
                item("metric", "words.median_reviewer_owner=825.0", True)]),
            "verdict_consistency": dim("deterministic", 1, [
                item("metric", "flags.verdict_count_mismatch=1", True)]),
        },
        "headline": "weakest: concision 1/5: words.median_reviewer_owner=825.0",
        "judge": {"status": "partial", "evidence_rejected": 2, "cost_usd": 0.41,
                  "tokens": None, "error": "edits_address_concerns: no verifiable evidence"},
    }


def test_evaluation_payload_states(tmp_path):
    """T26 (committee-eval C7, D10). Null with no eval.json; the error state for
    bad JSON, a non-object, ``schema != 1`` and a file over 256 KB; ok, with
    calibration read off this home's evals.jsonl at request time: none, two
    anchors within one, an unreadable ledger and a ledger over 2 MB. No call
    creates anything."""
    versions = ev.dimension_versions()
    home = str(tmp_path.resolve())
    run_dir = tmp_path / "runs" / RUN_ID

    def evaluation():
        before = sorted(tmp_path.rglob("*"))
        out = view_data(_run("decision"), [])["evaluation"]
        assert sorted(tmp_path.rglob("*")) == before  # no mkdir, no ledger file
        return out

    def labels():
        return {dim: row["calibration"] for dim, row in evaluation()["dimensions"].items()}

    # Never scored: null, not an empty table, and not even runs/ appears.
    assert evaluation() is None

    # The error state says why. The oversized file is a well-formed schema-1
    # body, so only the size check can refuse it.
    run_dir.mkdir(parents=True)
    eval_json = run_dir / "eval.json"
    for content, why in [
        ("{not json", "not JSON"),
        ("[1]", "not a JSON object"),
        (json.dumps({"schema": 2}), "schema is 2"),
        (json.dumps({"schema": 1, "pad": "x" * ev.EVAL_JSON_MAX}), "limit"),
    ]:
        eval_json.write_text(content, encoding="utf-8")
        out = evaluation()
        assert set(out) == {"state", "error"} and out["state"] == "error", content[:20]
        assert why in out["error"]

    # The limit is inclusive: exactly EVAL_JSON_MAX bytes is read, one more is refused.
    body = json.dumps(_eval_body(home, RUN_ID, 1789000000.0, versions))
    for extra, state in ((0, "ok"), (1, "error")):
        eval_json.write_text(body + " " * (ev.EVAL_JSON_MAX - len(body.encode()) + extra), encoding="utf-8")
        assert evaluation()["state"] == state, extra

    # ok, before any ledger exists: every judge dimension uncalibrated, every
    # deterministic one None (G6), rows in D5 order, the first VERIFIED quote.
    body = _eval_body(home, RUN_ID, 1789000000.0, versions)
    eval_json.write_text(json.dumps(body), encoding="utf-8")
    ok = evaluation()
    fresh = {"rationale": "stated", "stale": False}
    assert ok == {
        "state": "ok",
        "rubric_version": ev.rubric_version(versions),
        "evaluated_at": 1790000000.5,
        "headline": "weakest: concision 1/5: words.median_reviewer_owner=825.0",
        "judge_status": "partial",
        "judge_error": "edits_address_concerns: no verifiable evidence",
        "dimensions": {
            "verdict_grounded": {"score": 2, "scorer": "judge",
                                 "quote": "Approve with changes.",
                                 "calibration": "uncalibrated", **fresh},
            "edits_address_concerns": {"score": None, "scorer": "judge",
                                       "quote": None, "calibration": "uncalibrated", **fresh},
            "concern_coverage": {"score": 3, "scorer": "judge",
                                 "quote": "Fair point.", "calibration": "uncalibrated", **fresh},
            "efficiency": {"score": 3, "scorer": "deterministic",
                           "quote": "cost_usd=30.3875", "calibration": None, **fresh},
            "concision": {"score": 1, "scorer": "deterministic",
                          "quote": "words.median_reviewer_owner=825.0", "calibration": None,
                          **fresh},
            "verdict_consistency": {"score": 1, "scorer": "deterministic",
                                    "quote": "flags.verdict_count_mismatch=1",
                                    "calibration": None, **fresh},
        },
        "flags": ["action_clipped", "verdict_count_mismatch"],
    }
    assert list(ok["dimensions"]) == list(ev.DIMENSIONS)

    # Each dimension carries its whole rationale, clipped at eval.json's own limit with a closing
    # "…" (a hand-edited file may hold more), and whether it was scored under an older definition.
    long = dict(body, dimensions=dict(body["dimensions"], concern_coverage=dict(
        body["dimensions"]["concern_coverage"], rationale="r" * 4500)))
    eval_json.write_text(json.dumps(long), encoding="utf-8")
    assert evaluation()["dimensions"]["concern_coverage"]["rationale"] == "r" * 3999 + "…"
    older = dict(body, rubric=dict(versions, concision="concision@0", verdict_grounded="verdict_grounded@0"))
    eval_json.write_text(json.dumps(older), encoding="utf-8")
    assert {d: row["stale"] for d, row in evaluation()["dimensions"].items()} == {
        d: d in ("verdict_grounded", "concision") for d in ev.DIMENSIONS}
    eval_json.write_text(json.dumps(body), encoding="utf-8")

    # Two anchored targets within one calibrate a judge dimension. Neither eval
    # scored edits_address_concerns, so its anchors pair with nothing (G6).
    other = _eval_body("/elsewhere/home", "run-2", 1788000000.0, versions)
    for doc in (body, other):
        ev.append_ledger(home, ev.eval_line(doc))
        target = {key: doc["target"][key] for key in ("home", "run", "created_at")}
        scores = {"verdict_grounded": 3, "edits_address_concerns": 4, "concern_coverage": 2}
        ev.append_ledger(home, ev.anchor_line(target, scores, versions, "av", None))
    deterministic = {"efficiency": None, "concision": None, "verdict_consistency": None}
    assert labels() == {"verdict_grounded": "calibrated",
                        "edits_address_concerns": "uncalibrated",
                        "concern_coverage": "calibrated", **deterministic}

    # Labelled by eval.json's OWN version of each dimension: a file scored
    # under an older verdict_grounded is not vouched for by today's anchors.
    old = dict(body, rubric=dict(versions, verdict_grounded="verdict_grounded@0"))
    eval_json.write_text(json.dumps(old), encoding="utf-8")
    assert labels()["verdict_grounded"] == "uncalibrated"
    assert labels()["concern_coverage"] == "calibrated"
    eval_json.write_text(json.dumps(body), encoding="utf-8")

    # A ledger that cannot be read (a symlink, which read_ledger refuses) is
    # unknown, never "nothing anchored".
    unknown = {"verdict_grounded": "unknown", "edits_address_concerns": "unknown",
               "concern_coverage": "unknown", **deterministic}
    ledger, real = tmp_path / "evals.jsonl", tmp_path / "ledger.real"
    ledger.rename(real)
    ledger.symlink_to(real)
    assert labels() == unknown
    ledger.unlink()
    real.rename(ledger)

    # Past 2 MB the ledger is not read, so no label can be claimed.
    with open(ledger, "ab") as handle:
        handle.write(b"\n" * ev.LEDGER_MAX)
    assert labels() == unknown


def test_evaluation_refuses_what_it_cannot_trust(tmp_path, monkeypatch):
    """T26, the edges (committee-eval C7). view_data never raises, and an
    eval.json it cannot trust is the error state -- never ok, never None: JSON
    nested past the parser's recursion limit, a symlinked eval.json (dangling
    too) or runs/<id>, a file that grew past 256 KB between the size check and
    the read, one read_regular refuses, and schema-1 junk inside. Only a missing
    runs/<id> or eval.json is None. No error names an absolute path."""
    home = str(tmp_path.resolve())
    run_dir = tmp_path / "runs" / RUN_ID
    eval_json = run_dir / "eval.json"
    body = json.dumps(_eval_body(home, RUN_ID, 1789000000.0, ev.dimension_versions()))

    def evaluation():
        return view_data(_run("decision"), [])["evaluation"]

    def refused(why):
        out = evaluation()
        assert out["state"] == "error" and why in out["error"], out
        assert str(tmp_path) not in out["error"] and home not in out["error"], out

    # `runs` is a file, so lstat(runs/<id>) fails with ENOTDIR: its strerror, no path.
    (tmp_path / "runs").write_text("")
    refused("Not a directory")
    (tmp_path / "runs").unlink()
    assert evaluation() is None

    run_dir.mkdir(parents=True)
    eval_json.write_text("[" * 200_000, encoding="utf-8")  # RecursionError, not ValueError
    refused("not JSON")

    eval_json.write_text(body, encoding="utf-8")
    real_read = thread.read_regular
    monkeypatch.setattr(thread, "read_regular", lambda path: b" " * (ev.EVAL_JSON_MAX + 1))
    refused("limit")  # it grew after the size check
    monkeypatch.setattr(thread, "read_regular", lambda path: None)
    refused("not a readable regular file")
    monkeypatch.setattr(thread, "read_regular", real_read)
    assert evaluation()["state"] == "ok"

    eval_json.write_text(json.dumps(dict(json.loads(body), dimensions=[1])), encoding="utf-8")
    refused("could not be read")  # the catch-all: schema 1 with junk inside

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "eval.json").write_text(body, encoding="utf-8")
    eval_json.unlink()
    eval_json.symlink_to(outside / "eval.json")
    refused("not a regular file")
    eval_json.unlink()
    eval_json.symlink_to(tmp_path / "nowhere.json")  # dangling: not "never scored"
    refused("not a regular file")
    eval_json.unlink()
    run_dir.rmdir()
    run_dir.symlink_to(outside, target_is_directory=True)  # an eval.json outside the home
    refused("not a directory")
    run_dir.unlink()
    assert evaluation() is None


def test_evaluation_payload_carries_only_what_the_ui_renders(tmp_path):
    """C7: every field reaches the UI as the type it renders, whatever the file
    holds. A score is an int or null (via eval's _score: no "high", no bool);
    headline, rubric_version, judge status and error, and each quote are a str
    or null; evaluated_at is a number or null; flags are string ids only. The
    quote is the first whose ``verified`` is exactly True, and the scorer comes
    from JUDGE_DIMS, never from the file."""
    doc = _eval_body(str(tmp_path.resolve()), RUN_ID, 1789000000.0, ev.dimension_versions())
    dims = doc["dimensions"]
    dims["verdict_grounded"].update(score="high", rationale={"why": "an object"})
    dims["efficiency"].update(score=True, scorer="judge", rationale="")
    dims["concision"]["scorer"] = "judge"
    dims["concern_coverage"].update(scorer="deterministic", evidence=[
        {"quote": "one is not True", "verified": 1},
        {"quote": {"text": "an object"}, "verified": True},
    ])
    dims["verdict_consistency"]["evidence"] = [
        {"quote": "truthy is not True", "verified": "true"},
        {"quote": "flags.verdict_count_mismatch=1", "verified": True},
    ]
    doc.update(headline={"text": "x"}, rubric_version=7, evaluated_at="yesterday",
               judge={"status": ["ok"], "error": {"why": 1}},
               flags=[{"id": "action_clipped"}, {"turn": 3}, {"id": 5}, "bare", None])
    (tmp_path / "runs" / RUN_ID).mkdir(parents=True)
    (tmp_path / "runs" / RUN_ID / "eval.json").write_text(json.dumps(doc), encoding="utf-8")

    out = view_data(_run("decision"), [])["evaluation"]

    assert out["state"] == "ok", out
    assert (out["headline"], out["rubric_version"], out["evaluated_at"],
            out["judge_status"], out["judge_error"]) == (None, None, None, None, None)
    assert out["flags"] == ["action_clipped"]
    rows = out["dimensions"]
    assert {d: rows[d]["score"] for d in ev.DIMENSIONS} == {
        "verdict_grounded": None, "edits_address_concerns": None, "concern_coverage": 3,
        "efficiency": None, "concision": 1, "verdict_consistency": 1}
    assert {d: rows[d]["scorer"] for d in ev.DIMENSIONS} == {
        d: "judge" if d in ev.JUDGE_DIMS else "deterministic" for d in ev.DIMENSIONS}
    assert rows["concern_coverage"]["quote"] is None
    assert rows["verdict_consistency"]["quote"] == "flags.verdict_count_mismatch=1"
    assert {d: rows[d]["rationale"] for d in ev.DIMENSIONS} == {
        **dict.fromkeys(ev.DIMENSIONS, "stated"), "verdict_grounded": None, "efficiency": None}
    assert all(rows[d]["stale"] is False for d in ev.DIMENSIONS)

    doc["evaluated_at"] = 1790000000  # an int is a number too
    (tmp_path / "runs" / RUN_ID / "eval.json").write_text(json.dumps(doc), encoding="utf-8")
    assert view_data(_run("decision"), [])["evaluation"]["evaluated_at"] == 1790000000

    # json.loads reads NaN, Infinity and 1e999 as floats, but the route serialises
    # with allow_nan=False: only a finite number is forwarded, or every poll 500s.
    for raw in ("NaN", "Infinity", "-Infinity", "1e999"):
        text = json.dumps(dict(doc, evaluated_at=0)).replace('"evaluated_at": 0', f'"evaluated_at": {raw}')
        (tmp_path / "runs" / RUN_ID / "eval.json").write_text(text, encoding="utf-8")
        out = view_data(_run("decision"), [])["evaluation"]
        assert (out["state"], out["evaluated_at"]) == ("ok", None), raw
        json.dumps(out, allow_nan=False)
