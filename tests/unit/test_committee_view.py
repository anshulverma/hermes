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
import re
from pathlib import Path

import pytest

from engine.models import Reduction, Run
from playbooks.committee import cast, selection, thread, voice
from playbooks.committee import eval as ev
from playbooks.committee.view import SELECTION_PHASES, view_data

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
        "voice", "selection", "one_on_ones",
    }
    assert data["evaluation"] is None  # never scored: no runs/<id>/eval.json
    assert data["kind"] == "committee"
    assert len(data["roster"]) == 9
    assert all(
        set(row) == {"role", "name", "title", "state", "stance", *_ROW_KEYS}
        for row in data["roster"]
    )
    assert set(data["progress"]) == {
        "turn", "cap", "holder", "queue", "ended", "paused", "one_on_one",
    }
    assert data["one_on_ones"] == []  # run-2 predates 1:1s
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
    # selection C6: run-2 predates selection, so no block and no seat reasons.
    assert data["selection"] is None
    assert all(row[key] is None for row in data["roster"] for key in _ROW_KEYS)


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
        "paused": None, "one_on_one": None,
    }
    assert data["one_on_ones"] == []
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

    # A `voice` dict no reduce would write. json.loads reads NaN, and a string
    # or a list where a count belongs raised out of voice.summary; NaN sent on
    # as it was failed the route's strict serialiser. Both were a 500.
    nan = float("nan")
    junk = [{"words": "many"}, {"words": nan}, {"words": [1]}, {"cap": "x"},
            {"tells": [1]}, {"tells": {"turn_refs": "x"}}, {"dashes": "x"}]
    turns = [_voiced(n, "tl", "Defer it: `a.py:1` for example.") for n in range(1, len(junk) + 2)]
    for turn, bad in zip(turns, junk):
        turn.json["voice"].update(bad)
    for key, value in (("words", "x"), ("headers", nan)):
        decision = Reduction(kind="decision", json={
            "verdict": "Approve.", "delivered": True,
            "voice": {**voice.measure("Approve.", "chair"), key: value},
        }, phase="decision")

        data = view_data(_run("decision"), turns + [decision])

        json.dumps(data, allow_nan=False)
        assert data["voice"][f"chair_{key}"] is None, key
    assert data["verdict"]["voice"] is None  # NaN is never sent on
    assert data["timeline"][1]["voice"] is None
    assert data["timeline"][0]["voice"]["words"] == "many"  # junk, but serialisable
    assert data["voice"]["median_words_by_role"] == {"tl": 5.0, "chair": 1.0}
    # Finite counts whose sum is not: the summary is left out, never a 500.
    for turn in turns[-2:]:
        turn.json["voice"]["dashes"] = 1e308
    assert view_data(_run("decision"), turns)["voice"] is None

    # The image sha256, images_count and the tells flag, hand-edited: a sha256
    # that is NaN or a list, a NaN count, tells that are not a dict and flags
    # holding junk. Still JSON-strict, still no raise, and no junk sha256 sent.
    for sha in (nan, ["ab"], {"x": 1}, None):
        odd = _voiced(1, "owner", _FIGURES, violations=[], flags=["tells", 7, None])
        odd.json["voice"]["images"][0].update(ok=True, sha256=sha)
        odd.json["voice"].update(images_count=nan, tells="loud")
        data = view_data(_run("t02-owner"), [odd])
        json.dumps(data, allow_nan=False)
        entry = data["timeline"][0]
        assert entry["segments"][1]["ok"] is True and "sha256" not in entry["segments"][1]
        assert entry["badges"] == ["tells"] and entry["flags"] == ["tells"]
        assert entry["voice"] is None  # NaN is never sent on


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
        "origin_one_on_one": None,
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


def test_a_verified_image_segment_carries_the_sha256_the_master_recorded():
    digest = "ab" * 32
    doc = _voiced(2, "owner", _FIGURES)
    doc.json["voice"]["images"][0].update(ok=True, sha256=digest)
    image = view_data(_run("t03-tpm"), [doc])["timeline"][0]["segments"][1]
    assert image["ok"] is True and image["sha256"] == digest

    # absent unless the record passed and holds 64 lowercase hex; never on mermaid
    for ok, sha in ((True, None), (True, "AB" * 32), (True, "ab" * 31), (True, 7),
                    (False, digest), (None, digest)):
        doc = _voiced(2, "owner", _FIGURES)
        doc.json["voice"]["images"][0].update(ok=ok, sha256=sha)
        doc.json["voice"]["images"][1]["sha256"] = digest
        segments = view_data(_run("t03-tpm"), [doc])["timeline"][0]["segments"]
        assert "sha256" not in segments[1] and "sha256" not in segments[2], (ok, sha)


def test_a_turn_with_narration_or_hedging_is_badged_ai_tells():
    kept = _voiced(2, "owner", "I think we defer: `a.py:1` for example.")
    entry = view_data(_run("t03-tpm"), [kept])["timeline"][0]
    assert entry["flags"] == ["tells"] and entry["badges"] == ["tells"]
    assert entry["voice"]["tells"]["hedge"] == 1


def test_segments_stop_at_eight_figures_and_a_huge_body_is_one_disarmed_text():
    body = "Lead.\n" + "\n".join(f"![c{n}](images/x{n}.svg)" for n in range(12)) + "\nTail."
    segments = view_data(_run("t03-tpm"), [_voiced(2, "owner", body)])["timeline"][0]["segments"]
    assert [s["kind"] for s in segments] == ["text"] + ["image"] * 8 + ["text"]
    assert segments[-1]["text"].startswith("!\u200b[c8](images/x8.svg)\n")
    assert "![" not in segments[-1]["text"] and segments[-1]["text"].endswith("Tail.")

    huge = "Lead.\n" + "![x](images/t02-owner.svg)\n" * 3000  # over 64 KB
    doc = _voiced(2, "owner", "Lead.")
    doc.json["body"] = huge
    segments = view_data(_run("t03-tpm"), [doc])["timeline"][0]["segments"]
    assert segments == [{"kind": "text", "text": huge.strip().replace("![", "!\u200b[")}]
    small = "Lead.\n" + "![x](images/t02-owner.svg)\n" * 2000  # 54 KB: still split
    doc.json["body"] = small
    segments = view_data(_run("t03-tpm"), [doc])["timeline"][0]["segments"]
    assert [s["kind"] for s in segments] == ["text"] + ["image"] * 8 + ["text"]


def test_the_verdict_draws_no_diagram_its_mermaid_is_disarmed_text():
    body = ("Approve.\n\nFigure: Recorded as accepted\n```mermaid\ngraph TD; A[APPLIED]\n```\n"
            "Description: a fake tile.\n\nThe end.")
    data = view_data(_run("decision"), [
        Reduction(kind="decision", json={"verdict": body, "delivered": True}, phase="decision")])
    segments = data["verdict"]["segments"]
    assert [s["kind"] for s in segments] == ["text", "text", "text"]
    assert segments[1]["text"] == (
        "Figure: Recorded as accepted\n```\ngraph TD; A[APPLIED]\n```\n"
        "Description: a fake tile.")
    # a source holding a backtick run gets a longer fence, so it cannot close early
    tricky = "Figure: f\n````mermaid\na ``` b\n```\n````\nDescription: d"
    data = view_data(_run("decision"), [
        Reduction(kind="decision", json={"verdict": tricky, "delivered": True}, phase="decision")])
    (segment,) = data["verdict"]["segments"]
    assert segment["text"] == "Figure: f\n````\na ``` b\n```\n````\nDescription: d"
    # image syntax in the source is disarmed like any other text
    evil = "```mermaid\ngraph TD; A[\"![x](http://evil.example/a.png)\"]\n```"
    data = view_data(_run("decision"), [
        Reduction(kind="decision", json={"verdict": evil, "delivered": True}, phase="decision")])
    (segment,) = data["verdict"]["segments"]
    assert "![" not in segment["text"] and "!\u200b[x]" in segment["text"]


def test_a_mermaid_block_before_a_verified_image_leaves_the_image_verified():
    # measure records the mermaid block as well, so the image is second in the
    # recorded list: the position counts every figure, not only file images.
    doc = _voiced(2, "owner", "Lead.\nFigure: flow\n```mermaid\ngraph TD; A-->B\n```\n"
                  "Description: two.\n\n![curve](images/t02-owner.svg)\nDescription: a curve.")
    for image in doc.json["voice"]["images"]:
        image["ok"] = True  # as check_images records a mermaid block and a passing own file
    segments = view_data(_run("t03-tpm"), [doc])["timeline"][0]["segments"]

    assert [(s["kind"], s.get("ok")) for s in segments] == [
        ("text", None), ("mermaid", None), ("image", True)]


# Image syntax voice's scan misses, so it stays in a text segment and measure
# counts no image (no retake), yet react-markdown drew each of the first five
# as <img src="http://evil.example/...">: a label across lines (twice), a raw
# tag or an autolink outranking a code span, a backtick in a fence's info
# string. The last two hide one in a Description: or Figure: line, which the
# scan never reads.
_LEAKS = (
    "Lead.\n![alt\ntext](http://evil.example/a.png)\nDescription: x",
    "![a](images/t02-owner.svg)![b\n](http://evil.example/b.png)",
    'Lead <b title="`">![x](http://evil.example/c.png)<b title="`"> end.',
    "Lead <http://a.example/`>![x](http://evil.example/d.png)<http://c.example/`> end.",
    "Lead.\n![a](images/t02-owner.svg)\nDescription: see ![x](http://evil.example/z.png)",
    "Figure: ![y](http://evil.example/y.png)\n```mermaid\ngraph TD; A-->B\n```\nDescription: two",
)


@pytest.mark.parametrize("body", _LEAKS)
def test_no_prose_the_view_sends_carries_image_syntax(body):
    data = view_data(_run("decision"), [
        _voiced(2, "owner", body),
        Reduction(kind="decision", json={"verdict": body, "delivered": True}, phase="decision"),
    ])

    for segments in (data["timeline"][0]["segments"], data["verdict"]["segments"]):
        prose = [seg[key] for seg in segments
                 for key in ("text", "caption", "description") if key in seg]
        assert not any("![" in p for p in prose)
        assert any("!\u200b[" in p for p in prose)  # disarmed, as Diff.tsx does, not dropped


def test_a_backtick_in_a_backtick_fences_info_string_opens_no_fence():
    # CommonMark renders these lines as prose, so the image is split out as one
    # (refused), never left to Markdown inside a text segment.
    body = "``` x`y\n![x](http://evil.example/f.png)\n```"
    segments = view_data(_run("t03-tpm"), [_voiced(2, "owner", body)])["timeline"][0]["segments"]
    assert [(s["kind"], s.get("ok")) for s in segments] == [
        ("text", None), ("image", False), ("text", None)]


def test_the_top_level_voice_reads_the_rows_eval_reads():
    # Turn 1 settled twice and the chair was retaken: the last row per turn
    # and the latest decision count, as in eval's voice_summary, so the view
    # and the eval never disagree on one run.
    chair = lambda text: {"verdict": text, "delivered": True,  # noqa: E731
                          "voice": voice.measure(text, "chair")}
    rows = [
        _voiced(1, "tl", "word " * 10), _voiced(1, "tl", "word " * 100),
        _voiced(2, "owner", "word " * 20),
        Reduction(kind="decision", json=chair("Approve it."), phase="decision"),
        Reduction(kind="decision", json=chair("Defer it to next half."), phase="decision-take2"),
    ]
    summary = view_data(_run("decision-take2"), rows)["voice"]

    assert summary == ev.voice_summary([(r.kind, r.json) for r in rows], {})
    assert summary["median_words_by_role"] == {"tl": 100.0, "owner": 20.0, "chair": 5.0}


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


def test_the_voice_rows_the_view_labels_are_the_keys_summary_returns():
    # The Metrics tab renders one row per VOICE_LABEL key and reads voice[key]:
    # a key renamed on one side only shows a dash forever, with every test green.
    source = (Path(__file__).parents[2] / "playbooks" / "committee" / "view" / "src"
              / "CommitteeView.tsx").read_text(encoding="utf-8")
    block = source.split("const VOICE_LABEL", 1)[1].split("];", 1)[0]
    labelled = re.findall(r"\[\s*'(\w+)',", block)
    summary = voice.summary([
        ("turn", {"role": "tl", "voice": voice.measure("A point, see §2.")}),
        ("decision", {"voice": voice.measure("Approve.", "chair")}),
    ])

    assert labelled == list(summary)


# --- selection (selection C6) -------------------------------------------------

_ROW_KEYS = ("rationale", "nominated_by", "nominated_by_name", "source")
_SELECTOR = {1: "owner", 2: "manager", 3: "senior_director"}

# A derived seat at plain sizes, the way selection.validate builds one.
_CREW_OWNER = {
    "name": "Priya Nair", "title": "Crew Owner, fleet team",
    "altitude": "the fleet crews, this year.", "goal": "keep crews team-owned.",
    "ambition": "", "stake": "owns the crews federation would share.",
    "lens": "who can touch a host.", "style": cast.DERIVED_STYLE,
}

RUN9 = Path(__file__).parent.parent / "data" / "committee-eval" / "run-9"


def _sel(stage: int, **over) -> Reduction:
    """A kept stage's `selection` reduction as `_reduce_select` writes it (C5)."""
    role = _SELECTOR[stage]
    doc = {
        "stage": stage, "role": role, "final": stage == 3, "delivered": True,
        "body": f"Stage {stage}: everyone below has a stake in this proposal.",
        "parsed": True, "code": None, "proposed": [], "proposed_dropped": 0,
        "error": None, "cap": 30, "take": 1, "takes": 1, "kept": True, "voice": None,
        "violations": [], "flags": [],
    }
    doc.update(over)
    return Reduction(kind="selection", json=doc, phase=f"s{stage}-{role}")


def _seat(role: str, nominated_by: str, **derived) -> dict:
    """A seat record as `selection.resolve` builds it: library, or derived."""
    persona = derived or dict(cast.LIBRARY[role])
    return {
        **persona, "role": role, "rationale": f"{role} has a stake in this proposal",
        "nominated_by": nominated_by, "source": "derived" if derived else "library",
    }


def _seated(*reviewers) -> list:
    """Roster order: owner, the chair, the manager, the reviewers, the junior IC."""
    fixed = selection.fixed_seats()
    return [fixed["owner"], fixed["senior_director"], fixed["manager"],
            *reviewers, fixed["junior_ic"]]


def _ratified(*reviewers: dict, **over) -> Reduction:
    """The chair's final reduction, seating `reviewers` after the fixed two."""
    slugs = ["senior_director", "manager"] + [seat["role"] for seat in reviewers]
    doc = {"seated": _seated(*reviewers), "reviewers": slugs, "considered": [],
           "considered_dropped": 0, "invalid_dropped": 0, "fallback": None,
           "cap": 2 * len(slugs) + 16}
    doc.update(over)
    return _sel(3, **doc)


def _said(n: int, role: str, **over) -> Reduction:
    """A delivered meeting turn by `role`, with the keys `_reduce_turn` writes."""
    doc = {
        "role": role, "turn": n, "delivered": True, "body": f"Turn {n:02d} by {role}.",
        "stance": None, "request_floor": False, "delegate": False, "close": False,
        "action": None, "verified": None, "error": None, "cap": 24,
    }
    doc.update(over)
    return Reduction(kind="turn", json=doc, phase=f"t{n:02d}-{role}")


def _run9_reductions() -> list[Reduction]:
    """run-9's reduction rows from eval's committed fixture, hydrated as the queue does."""
    [rows] = sorted(RUN9.glob("*reductions*.json"))
    out = []
    for row in json.loads(rows.read_text(encoding="utf-8")):
        doc = json.loads(row["json"]) if isinstance(row["json"], str) else row["json"]
        out.append(Reduction(kind=row["kind"], json=doc, phase=row.get("phase"),
                             review_state=row.get("review_state") or "pending"))
    return out


def test_selection_states_selecting_and_lost_show_the_fixed_four():
    fixed = ["owner", "senior_director", "manager", "junior_ic"]
    lost = Reduction(kind="lost", json={"error": "the meeting was lost"})
    cases = [
        ("s1-owner", [], "selecting", 0),                 # s1 minted, nothing reduced yet
        ("s2-manager-take2", [_sel(1)], "selecting", 1),  # a selector's retake
        ("s2-manager", [_sel(1), lost], "lost", 1),
    ]
    for phase, reductions, state, stages in cases:
        data = view_data(_run(phase), reductions)
        rows = data["roster"]

        assert data["selection"]["state"] == state, phase
        assert len(data["selection"]["stages"]) == stages, phase
        assert data["selection"]["fallback"] is None
        assert data["selection"]["considered"] == []
        assert (data["selection"]["considered_dropped"],
                data["selection"]["invalid_dropped"]) == (0, 0)
        assert [row["role"] for row in rows] == fixed, phase
        assert data["progress"]["holder"] is None
        assert {row["state"] for row in rows} == {"idle"}
        assert [row["rationale"] for row in rows] == [cast.FIXED_RATIONALE[r] for r in fixed]
        assert {(row["nominated_by"], row["nominated_by_name"], row["source"])
                for row in rows} == {("fixed", None, "fixed")}
        assert data["timeline"] == [] and data["verdict"] is None

    # Not yet past open, or already at the chair or the ruling: nothing to select.
    for phase in (None, "open", "ruling", "decision", "decision-take2"):
        assert view_data(_run(phase), [])["selection"] is None, phase


def test_a_seated_run_before_t01_carries_the_roster_and_the_selection_block():
    security = _seat("security", "owner")
    crew = _seat("crew_owner", "manager", **_CREW_OWNER)
    considered = [
        {"stakeholder": "Legal", "role": None,
         "reason": "no legal exposure in the document", "represented_by": "security"},
        {"stakeholder": "Release engineering", "role": None,
         "reason": "dropped by Ruth Delgado", "represented_by": None},
    ]
    proposed = [{"role": "security", "name": security["name"],
                 "title": "Security Engineer", "rationale": security["rationale"]}]
    reductions = [
        _sel(1, proposed=proposed, proposed_dropped=5), _sel(2),
        # decisions 5/8: what resolve's caps cut is counted, never lost silently
        _ratified(security, crew, considered=considered,
                  considered_dropped=3, invalid_dropped=2),
    ]

    data = view_data(_run("t01-senior_director"), reductions)
    rows = {row["role"]: row for row in data["roster"]}

    assert list(rows) == [
        "owner", "senior_director", "manager", "security", "crew_owner", "junior_ic",
    ]
    assert (rows["security"]["name"], rows["security"]["title"]) == (
        security["name"], "Security Engineer")
    assert rows["security"]["rationale"] == "security has a stake in this proposal"
    assert (rows["security"]["nominated_by"], rows["security"]["nominated_by_name"],
            rows["security"]["source"]) == ("owner", "Maya Okonkwo", "library")
    assert (rows["crew_owner"]["name"], rows["crew_owner"]["title"]) == (
        "Priya Nair", "Crew Owner, fleet team")
    assert (rows["crew_owner"]["nominated_by_name"], rows["crew_owner"]["source"]) == (
        "Ruth Delgado", "derived")
    assert rows["owner"]["rationale"] == cast.FIXED_RATIONALE["owner"]
    assert (rows["owner"]["nominated_by"], rows["owner"]["nominated_by_name"]) == ("fixed", None)
    assert {row["state"] for row in rows.values()} == {"idle"}
    # Four reviewers resolve to 2*4+16 = 24, read off the final reduction: never
    # the default 30 this process would otherwise guess.
    assert data["progress"] == {
        "turn": 0, "cap": 24, "holder": None, "queue": [], "ended": None,
        "paused": None, "one_on_one": None,
    }
    assert data["timeline"] == [] and data["document"]["name"] is None

    block = data["selection"]
    assert set(block) == {
        "state", "current", "stages", "fallback", "considered", "considered_dropped",
        "invalid_dropped",
    }
    assert (block["state"], block["fallback"], block["current"]) == ("seated", None, None)
    assert (block["considered_dropped"], block["invalid_dropped"]) == (3, 2)
    assert [(s["stage"], s["role"], s["name"]) for s in block["stages"]] == [
        (1, "owner", "Maya Okonkwo"), (2, "manager", "Ruth Delgado"),
        (3, "senior_director", "Dana Whitfield"),
    ]
    assert block["stages"][0]["proposed"] == [{**proposed[0], "source": "library"}]
    assert [s["proposed_dropped"] for s in block["stages"]] == [5, 0, 0]
    assert block["considered"] == [
        {**considered[0], "represented_by_name": security["name"]},
        {**considered[1], "represented_by_name": None},
    ]
    json.dumps(data, allow_nan=False)


def test_a_fallback_selection_is_reported():
    resolved = selection.fallback("chair_failed")
    chair = _sel(3, delivered=False, body="", parsed=False, code="no_answer", **resolved)

    data = view_data(_run("t01-senior_director"), [_sel(1), _sel(2), chair])

    block = data["selection"]
    assert (block["state"], block["fallback"], block["considered"]) == (
        "fallback", "chair_failed", [])
    assert block["stages"][2]["delivered"] is False
    assert "no_turn" in block["stages"][2]["badges"]
    rows = {row["role"]: row for row in data["roster"]}
    assert list(rows) == list(cast.CAST)  # today's nine, in today's order
    assert rows["tpm"]["rationale"] == "in the default committee (the chair gave no usable list)"
    assert (rows["tpm"]["nominated_by"], rows["tpm"]["nominated_by_name"],
            rows["tpm"]["source"]) == ("default", None, "library")

    # "default" and "fixed" are legal derived slugs (neither is reserved), and
    # a seat by either name is still nobody's nominator.
    odd = dict(chair.json, seated=[
        *resolved["seated"], _seat("default", "senior_director", **_CREW_OWNER),
        _seat("fixed", "owner", **_CREW_OWNER),
    ])
    data = view_data(_run("t01-senior_director"), [Reduction(kind="selection", json=odd)])
    rows = {row["role"]: row for row in data["roster"]}
    assert (rows["tpm"]["nominated_by_name"], rows["owner"]["nominated_by_name"]) == (None, None)
    assert rows["default"]["nominated_by_name"] == "Dana Whitfield"


def test_a_stage_carries_voice_fields_badges_and_segments():
    body = (
        "Seat security before anyone else.\n"
        "Figure: who sits where\n"
        "```mermaid\ngraph TD; A-->B\n```\n"
        "Description: the owner seats security first."
    )
    soft = ["no_pointer", "no_example", "tells", "dashes", "long_first_line"]
    kept = _sel(1, body=body, voice=voice.measure(body, "owner"), take=3, takes=3,
                violations=["over_cap"], flags=soft)

    stage = view_data(_run("s2-manager"), [kept])["selection"]["stages"][0]

    assert set(stage) == {
        "stage", "role", "name", "delivered", "body", "proposed", "proposed_dropped",
        "not_seated", "not_seated_dropped", "invalid_count",
        "code", "segments", "badges", "take", "takes", "violations", "flags",
    }
    # a reduction from before the notes were carried reads as none (payload contract 2)
    assert (stage["not_seated"], stage["not_seated_dropped"], stage["invalid_count"]) == (
        [], 0, 0)
    assert (stage["take"], stage["takes"]) == (3, 3)
    assert (stage["violations"], stage["flags"]) == (["over_cap"], soft)
    # decision 11: a selector is asked for no pointer or example, so voice's
    # soft flags ride on `flags` and are never badged; the hard rules still are.
    assert stage["badges"] == ["voice_flag", "retaken"]
    assert stage["body"] == body
    # for a selector the list is the answer, so no stage says "signals only" (I2),
    # not even one reduced before the seat-list stub existed
    from playbooks.committee.playbook import _SIGNALS_ONLY
    listed = view_data(_run("s2-manager"), [_sel(1, body=_SIGNALS_ONLY)])["selection"]
    assert "signals_only" not in listed["stages"][0]["badges"]
    mermaid = [seg for seg in stage["segments"] if seg["kind"] == "mermaid"]
    assert [seg["source"] for seg in mermaid] == ["graph TD; A-->B"]


def test_a_stage_image_that_checked_ok_is_ok():
    body = "Seat security.\n![who sits where](images/s1-owner.svg)\nDescription: the seats."
    checked = voice.measure(body, "owner")
    checked["images"][0]["ok"] = True        # what the master's _grade recorded
    unchecked = voice.measure(body, "owner")  # ok stays None: never assumed

    def image(metrics):
        doc = _sel(1, body=body, voice=metrics)
        stage = view_data(_run("s2-manager"), [doc])["selection"]["stages"][0]
        return next(seg for seg in stage["segments"] if seg["kind"] == "image")

    assert (image(checked)["ok"], image(checked)["name"]) == (True, "s1-owner.svg")
    assert image(unchecked)["ok"] is False


def test_a_proposed_seat_the_chair_dropped_still_says_library_or_derived():
    """The roster marks only a seated derived seat, so each listed seat carries its own source."""
    crew = {"role": "crew_owner", "name": "Priya Nair", "title": "Crew Owner, fleet team",
            "rationale": "owns the crews"}
    sre = {"role": "sre", "name": cast.LIBRARY["sre"]["name"],
           "title": cast.LIBRARY["sre"]["title"], "rationale": "carries the pager"}
    security = _seat("security", "owner")
    reductions = [_sel(1, proposed=[crew, sre]), _sel(2), _ratified(security)]

    for phase, rows in (("s2-manager", reductions[:1]), ("t01-senior_director", reductions)):
        [stage, *_] = view_data(_run(phase), rows)["selection"]["stages"]

        # Neither seat reached the roster; the chair seated security alone.
        assert [(p["role"], p["source"]) for p in stage["proposed"]] == [
            ("crew_owner", "derived"), ("sre", "library")], phase


def test_a_stage_carries_why_its_list_could_seat_nobody():
    stages = view_data(_run("t01-senior_director"), [
        _sel(1, code="too_few"), _sel(2, code=7), _ratified(_seat("security", "owner")),
    ])["selection"]["stages"]
    absent = dict(_sel(1).json)
    del absent["code"]  # a reduction written before the key
    [legacy] = view_data(_run("s2-manager"), [Reduction(kind="selection", json=absent)])[
        "selection"]["stages"]

    assert [s["code"] for s in stages] == ["too_few", None, None]
    assert legacy["code"] is None


def test_the_selector_at_work_is_named_while_a_stage_runs():
    """Payload contract 1: `current` names who is seating the committee, from a
    static map over SELECTION_PHASES (compared, never parsed), and is null
    unless the run is selecting."""
    verbs = {"owner": "proposing", "manager": "amending", "senior_director": "ratifying"}
    for phase in SELECTION_PHASES:
        role = phase.split("-take")[0].split("-", 1)[1]
        current = view_data(_run(phase), [])["selection"]["current"]
        assert current == {"role": role, "name": cast.CAST[role]["name"],
                           "verb": verbs[role]}, phase
    assert len(SELECTION_PHASES) == 3 * voice.MAX_TAKES

    lost = Reduction(kind="lost", json={"error": "the meeting was lost"})
    assert view_data(_run("s2-manager"), [_sel(1), lost])["selection"]["current"] is None
    seated = [_sel(1), _sel(2), _ratified(_seat("security", "owner"))]
    assert view_data(_run("t01-senior_director"), seated)["selection"]["current"] is None
    # a phase that only looks like a stage is not one
    assert view_data(_run("s4-owner"), [_sel(1)])["selection"]["current"] is None


def test_a_stage_says_who_it_left_out_and_who_speaks_for_them():
    """Payload contract 2: a stage's not_seated notes, the first thread.LIST_MAX,
    each represented only as its thread entry says (a seat on that stage's
    list or a fixed seat, never the owner), with its two counts."""
    sec = cast.LIBRARY["security"]
    proposed = [{"role": "security", "name": sec["name"], "title": sec["title"],
                 "rationale": "owns the zones"}]
    notes = [
        {"stakeholder": "Legal", "reason": "no contract changes", "represented_by": "security"},
        {"stakeholder": "Finance", "reason": "already budgeted", "represented_by": "manager"},
        {"stakeholder": "Support", "reason": "later", "represented_by": "sre"},  # not listed
        {"stakeholder": "Board", "reason": "not asked", "represented_by": "owner"},
        {"stakeholder": "Growth", "reason": "no users move", "represented_by": None},
    ] + [{"stakeholder": f"Team {k}", "reason": "no change", "represented_by": None}
         for k in range(thread.LIST_MAX)]
    stage = view_data(_run("s2-manager"), [_sel(
        1, proposed=proposed, not_seated=notes, not_seated_dropped=4, invalid_count=2,
    )])["selection"]["stages"][0]

    assert len(stage["not_seated"]) == thread.LIST_MAX
    assert stage["not_seated"][:5] == [
        {"stakeholder": "Legal", "reason": "no contract changes",
         "represented_by": "security", "represented_by_name": sec["name"]},
        {"stakeholder": "Finance", "reason": "already budgeted",
         "represented_by": "manager", "represented_by_name": cast.CAST["manager"]["name"]},
        {"stakeholder": "Support", "reason": "later",
         "represented_by": None, "represented_by_name": None},
        {"stakeholder": "Board", "reason": "not asked",
         "represented_by": None, "represented_by_name": None},
        {"stakeholder": "Growth", "reason": "no users move",
         "represented_by": None, "represented_by_name": None},
    ]
    assert (stage["not_seated_dropped"], stage["invalid_count"]) == (4, 2)
    junk = view_data(_run("s2-manager"), [_sel(1, not_seated="x", invalid_count=-3)])
    assert (junk["selection"]["stages"][0]["not_seated"],
            junk["selection"]["stages"][0]["invalid_count"]) == ([], 0)


def test_the_latest_selection_marked_final_true_seats_the_view():
    """Two final reductions: the later one's committee is the view's. A `final`
    that is not exactly true (a hand-edited "true" or 1) never counts (V04, V05)."""
    first = _ratified(_seat("security", "owner"))
    later = _ratified(_seat("sre", "manager"))
    fake = Reduction(kind="selection", json={
        **later.json, "seated": _seated(_seat("privacy", "owner")),
        "reviewers": ["senior_director", "manager", "privacy"], "final": "true"})
    ones = Reduction(kind="selection", json={**fake.json, "final": 1})

    def reviewers(reductions):
        return [row["role"] for row in view_data(_run("t01-senior_director"), reductions)[
            "roster"]][3:-1]

    assert reviewers([_sel(1), first, _sel(2), later, fake, ones]) == ["sre"]
    assert reviewers([_sel(1), first, fake, ones]) == ["security"]
    assert view_data(_run("s3-senior_director"), [_sel(1), fake, ones])["selection"][
        "state"] == "selecting"


def test_a_legacy_run_lost_mid_meeting_has_no_selection(run2):
    lost = Reduction(kind="lost", json={"error": "the meeting was lost"})

    data = view_data(_run("t05-senior_director"), run2[:4] + [lost])

    assert data["selection"] is None
    assert [row["role"] for row in data["roster"]] == list(cast.CAST)
    assert all(row[key] is None for row in data["roster"] for key in _ROW_KEYS)


def test_a_legacy_run_before_its_first_turn_keeps_the_nine():
    """Only an s-phase or a selection reduction says selection ran. A run from
    before selection, at t01 with no turn settled, keeps today's nine and no
    Selection card: never "selecting" or "lost" with the fixed four."""
    take = Reduction(kind="take", json={
        "phase": "t01-senior_director", "role": "senior_director", "turn": 1, "take": 1,
        "kept": False, "delivered": True, "body": "x"}, phase="t01-senior_director")
    lost = Reduction(kind="lost", json={"error": "the meeting was lost"})
    for phase, reductions in (
        ("t01-senior_director", []),            # minted, nothing settled yet
        ("t01-senior_director-take2", [take]),  # a voice retake of the first turn
        ("t01-senior_director", [lost]),        # lost at t01
    ):
        data = view_data(_run(phase), reductions)

        assert data["selection"] is None, phase
        assert [row["role"] for row in data["roster"]] == list(cast.CAST), phase
        assert all(row[key] is None for row in data["roster"] for key in _ROW_KEYS), phase

    # The playbook's three stage names (`_select`) and voice's retakes of each.
    assert SELECTION_PHASES == (
        "s1-owner", "s1-owner-take2", "s1-owner-take3",
        "s2-manager", "s2-manager-take2", "s2-manager-take3",
        "s3-senior_director", "s3-senior_director-take2", "s3-senior_director-take3",
    )


def test_a_derived_seat_is_named_in_floor_stances_and_entries():
    crew = _seat("crew_owner", "manager", **_CREW_OWNER)
    reductions = [
        _sel(1), _sel(2), _ratified(crew),
        _said(1, "crew_owner", stance="defer until crews can opt out", request_floor=True),
        _said(2, "owner"),
    ]

    data = view_data(_run("t03-senior_director"), reductions)
    entry = data["timeline"][0]
    rows = {row["role"]: row for row in data["roster"]}

    assert (entry["role"], entry["name"], entry["title"]) == (
        "crew_owner", "Priya Nair", "Crew Owner, fleet team")      # _entry
    assert "unattributed" not in entry["badges"]
    assert data["progress"]["queue"] == ["crew_owner"]              # _floor
    assert data["progress"]["holder"] == "owner"
    assert rows["crew_owner"]["state"] == "queued"
    assert rows["crew_owner"]["stance"] == "defer until crews can opt out"  # _stances

    # A derived seat holding the floor lights its own row (_roster), never a 500.
    data = view_data(_run("t02-owner"), reductions[:4])
    assert data["progress"]["holder"] == "crew_owner"
    assert {row["role"]: row["state"] for row in data["roster"]}["crew_owner"] == "holds_floor"


def test_an_unknown_role_is_unattributed_and_never_raises():
    final = _ratified(
        seated=_seated(7, {"role": "nameless"}),  # junk only a hand edit writes
        considered=[{"stakeholder": "Legal", "role": None, "reason": "no exposure",
                     "represented_by": "tpm"}, "junk"],
        proposed=[{"role": "tpm"}, 3],
        proposed_dropped=float("nan"), considered_dropped="many", invalid_dropped=-4,
    )
    reductions = [
        _sel(1, role="ghost"), Reduction(kind="selection", json=["junk"]), final,
        _said(1, "tpm", request_floor=True, stance="I was never seated"),
        _said(2, "ghost"),
    ]

    data = view_data(_run("t03-owner"), reductions)

    json.dumps(data, allow_nan=False)
    assert [row["role"] for row in data["roster"]] == [
        "owner", "senior_director", "manager", "junior_ic",
    ]
    assert [e["name"] for e in data["timeline"]] == ["unattributed", "unattributed"]
    assert all("unattributed" in e["badges"] for e in data["timeline"])
    assert data["progress"]["queue"] == [] and data["progress"]["holder"] is None
    assert all(row["stance"] is None for row in data["roster"])
    stages = data["selection"]["stages"]
    assert stages[0]["name"] == "unattributed"
    assert stages[1]["proposed"] == [
        {"role": "tpm", "name": "", "title": "", "rationale": "", "source": "library"}]
    assert stages[1]["proposed_dropped"] == 0
    assert (data["selection"]["considered_dropped"], data["selection"]["invalid_dropped"]) == (0, 0)
    assert data["selection"]["considered"] == [{
        "stakeholder": "Legal", "role": None, "reason": "no exposure",
        "represented_by": "tpm", "represented_by_name": None,
    }]


def test_run9_renders_the_nine_unchanged():
    """AC9 over the real run-9 rows: a legacy run keeps today's nine, unexplained."""
    reductions = _run9_reductions()
    assert any(r.kind == "turn" for r in reductions)  # really a meeting's rows

    data = view_data(_run("ruling"), reductions)

    assert data["selection"] is None
    assert [(row["role"], row["name"], row["title"]) for row in data["roster"]] == [
        (role, who["name"], who["title"]) for role, who in cast.CAST.items()
    ]
    assert all(row[key] is None for row in data["roster"] for key in _ROW_KEYS)
    assert all(entry["name"] == cast.CAST[entry["role"]]["name"]
               for entry in data["timeline"] if entry["role"] in cast.CAST)


# --- the 1:1s (one-on-ones C8, D10) -------------------------------------------
# `_oo` = one-on-one. Every reduction below has the exact shape the playbook
# writes (C5 selection, C6 plan/turn/one_on_one), so the view is tested against
# what `reduce` produces and never against a shape invented here.

_OO_CREW = {  # a derived seat (selection C3/C4): only its run's selection knows it
    "role": "crew_owner", "name": "Noor Haddad", "title": "Crew owner, platform team",
    "altitude": "", "goal": "", "ambition": "", "stake": "", "lens": "",
    "style": cast.DERIVED_STYLE, "rationale": "owns the crews the proposal moves",
    "nominated_by": "owner", "source": "derived",
}

_OO_FIGURE = (
    "We own the crews today.\n"
    "Figure: who runs what\n"
    "```mermaid\ngraph TD; crews-->teams\n```\n"
    "Description: crews stay with their teams."
)


def _oo_library(role: str) -> dict:
    return {**cast.LIBRARY[role], "role": role, "rationale": f"{role} has a stake",
            "nominated_by": "owner", "source": "library"}


def _oo_room() -> Reduction:
    """selection's final reduction: tpm, library `security` and a derived seat."""
    from playbooks.committee import selection

    fixed = selection.fixed_seats()
    seated = [fixed["owner"], fixed["senior_director"], fixed["manager"],
              _oo_library("tpm"), _oo_library("security"), _OO_CREW, fixed["junior_ic"]]
    return Reduction(kind="selection", phase="s3-senior_director", json={
        "stage": 3, "role": "senior_director", "final": True, "delivered": True,
        "body": "Seated.", "parsed": True, "code": None, "proposed": [], "error": None,
        "cap": 26, "take": 1, "takes": 1, "kept": True, "voice": None,
        "violations": [], "flags": [], "seated": seated,
        "reviewers": ["senior_director", "manager", "tpm", "security", "crew_owner"],
        "considered": [], "fallback": None,
    })


def _oo_pair(seq, host, members, topic, origin="upfront", called_by="owner") -> dict:
    """A C3 pair, as `one_on_ones_scheduled` records it."""
    return {"seq": seq, "origin": origin, "called_by": called_by, "host": host,
            "members": list(members), "topic": topic}


def _oo_plan(*scheduled: dict) -> Reduction:
    return Reduction(kind="one_on_one_plan", phase="p01-owner", json={
        "delivered": True, "body": "One 1:1 first.",
        "one_on_ones_scheduled": list(scheduled), "one_on_ones_dropped": [],
        "fallback": None if scheduled else "no valid pairs", "one_on_one_budget": 16,
        "error": None, "take": 1, "takes": 1, "kept": True, "voice": None,
        "violations": [], "flags": [],
    })


def _oo_turn(n, role, *, scheduled=(), align=None) -> Reduction:
    """A kept meeting turn carrying the C6 1:1 keys (no artifact: no document)."""
    return Reduction(kind="turn", phase=f"t{n:02d}-{role}", json={
        "role": role, "turn": n, "delivered": True, "body": f"Turn {n:02d}.",
        "stance": None, "cap": 26, "request_floor": False, "delegate": False,
        "close": False, "action": None, "verified": None, "answers_turn": None,
        "delegated_by_turn": None, "error": None, "take": 1, "takes": 1, "kept": True,
        "voice": None, "violations": [], "flags": [], "align": align,
        "one_on_ones_scheduled": list(scheduled), "one_on_ones_dropped": [],
        "one_on_one_budget": 16,
    })


def _oo(pair, speaker, exchange, *, used, after_turn=0, closing=False, aligned=None,
        agreed=None, still_open=None, ended=None, final=False, body=None) -> Reduction:
    """A kept `one_on_one` reduction with every C6 field."""
    return Reduction(kind="one_on_one", phase=f"o{used:02d}-{speaker}", json={
        **pair, "after_turn": after_turn, "speaker": speaker,
        "exchange": None if closing else exchange, "closing": closing,
        "delivered": True, "body": f"{speaker} speaks." if body is None else body,
        "aligned": aligned, "agreed": agreed, "still_open": still_open,
        "delegate": False, "action": None, "final": final, "ended": ended,
        "outcome": ({"aligned": ended == "aligned", "agreed": agreed,
                     "still_open": still_open} if final else None),
        "delegated_action": None, "one_on_one_budget": 16, "one_on_one_used": used,
        "error": None, "take": 1, "takes": 1, "kept": True, "voice": None,
        "violations": [], "flags": [],
    })


def _oo_person(role: str, library: bool = False) -> dict:
    who = (cast.LIBRARY if library else cast.CAST)[role]
    return {"role": role, "name": who["name"], "title": who["title"]}


def test_view_groups_one_on_ones_by_after_turn():
    """An up-front group and a pause group, both named through the run's seats."""
    upfront = _oo_pair(1, "manager", ["crew_owner", "manager"], "who owns the crews")
    pause = _oo_pair(2, "owner", ["security", "owner"], "threat model", origin="pause")
    reductions = [
        _oo_room(), _oo_plan(upfront),
        _oo(upfront, "crew_owner", 1, used=1, aligned=True, body=_OO_FIGURE),
        _oo(upfront, "manager", 2, used=2, aligned=True, agreed="crews stay team-owned",
            ended="aligned", final=True),
        _oo_turn(1, "senior_director"),
        _oo_turn(2, "owner", scheduled=[pause], align="security owner: threat model"),
        _oo(pause, "security", 1, after_turn=2, used=3),
    ]

    data = view_data(_run("o04-owner"), reductions)
    first, second = data["one_on_ones"]

    assert [e["n"] for e in data["timeline"]] == [1, 2]  # 1:1s never join the timeline
    assert set(first) == {
        "seq", "origin", "called_by", "after_turn", "host", "members", "topic",
        "exchanges", "ended", "aligned", "agreed", "still_open", "delegated_action",
    }
    assert set(first["exchanges"][0]) == {
        "exchange", "speaker", "name", "body", "segments", "delivered", "aligned",
        "closing", "badges",
    }
    assert (first["seq"], first["origin"], first["called_by"], first["after_turn"]) == (
        1, "upfront", "owner", 0)
    assert first["host"] == _oo_person("manager")
    assert first["members"] == [
        {"role": "crew_owner", "name": "Noor Haddad", "title": "Crew owner, platform team"},
        _oo_person("manager"),
    ]
    assert first["topic"] == "who owns the crews"
    opening = first["exchanges"][0]
    assert (opening["exchange"], opening["speaker"], opening["name"]) == (
        1, "crew_owner", "Noor Haddad")
    assert (opening["delivered"], opening["aligned"], opening["closing"]) == (True, True, False)
    assert opening["body"] == _OO_FIGURE
    assert [s["kind"] for s in opening["segments"]] == ["text", "mermaid"]  # voice's split
    assert opening["badges"] == []
    assert (first["ended"], first["aligned"], first["agreed"], first["still_open"]) == (
        "aligned", True, "crews stay team-owned", None)
    assert first["delegated_action"] is None

    assert (second["seq"], second["origin"], second["after_turn"]) == (2, "pause", 2)
    assert second["members"] == [_oo_person("security", library=True), _oo_person("owner")]
    assert second["exchanges"][0]["name"] == cast.LIBRARY["security"]["name"]
    assert (second["ended"], second["aligned"], second["agreed"]) == (None, None, None)


def test_view_one_on_one_outcome_and_exchange_fields():
    """The group's outcome comes off the final reduction's `outcome`, never that
    exchange's own keys (a host can omit on her closing exchange what she stated
    earlier), and each exchange keeps its delivery, closing flag and badges."""
    closed = _oo_pair(1, "owner", ["tpm", "security"], "the appendix")
    unheard = _oo_pair(2, "manager", ["crew_owner", "manager"], "who owns the crews")
    closing = _oo(closed, "owner", None, used=3, closing=True, ended="budget", final=True)
    closing.json.update(
        outcome={"aligned": False, "agreed": "tpm first", "still_open": "who signs"},
        agreed=None, still_open=None, delegated_action="Cut the appendix.")
    silent = _oo(unheard, "crew_owner", 1, used=4, ended="not delivered", final=True)
    silent.json.update(delivered=False, body="", takes=2)
    reductions = [
        _oo_room(), _oo_plan(closed, unheard),
        _oo(closed, "tpm", 1, used=1), _oo(closed, "security", 2, used=2, ended="budget"),
        closing, silent,
    ]

    first, second = view_data(_run("t01-senior_director"), reductions)["one_on_ones"]

    assert (first["agreed"], first["still_open"], first["delegated_action"]) == (
        "tpm first", "who signs", "Cut the appendix.")
    ex = first["exchanges"][-1]
    assert (ex["closing"], ex["exchange"]) == (True, None)
    ex = second["exchanges"][0]
    assert (ex["delivered"], ex["badges"]) == (False, ["no_turn", "retaken"])


def test_view_paused_and_in_one_on_one():
    """D10 and gap 2: the lag, a member exchange, the closing exchange, and every
    way a meeting stops that leaves no pause behind."""
    pair = _oo_pair(1, "manager", ["tpm", "security"], "rollout order",
                    origin="pause", called_by="manager")
    meeting = [
        _oo_room(), _oo_plan(),
        _oo_turn(1, "senior_director"), _oo_turn(2, "owner"),
        _oo_turn(3, "manager", scheduled=[pair], align="tpm security: rollout order"),
        _oo_turn(4, "owner"),
    ]
    opens = _oo(pair, "tpm", 1, used=1, after_turn=4, aligned=True)
    answers = _oo(pair, "security", 2, used=2, after_turn=4, aligned=True, ended="aligned")
    closes = _oo(pair, "manager", None, used=3, after_turn=4, closing=True,
                 agreed="tpm sequences it, security signs off", ended="aligned", final=True)

    def seen(reductions, phase):
        data = view_data(_run(phase), reductions)
        busy = sorted(r["role"] for r in data["roster"] if r["state"] == "in_one_on_one")
        return data, busy

    # No exchange kept yet: the view lags one phase ("1:1s next") and the floor stands.
    data, busy = seen(meeting, "o01-tpm")
    assert data["progress"]["paused"] == {
        "pairs": [{
            "seq": 1, "host": _oo_person("manager"),
            "members": [_oo_person("tpm"), _oo_person("security", library=True)],
        }],
        "current": None,
    }
    assert busy == [] and data["progress"]["holder"] == "owner"

    # A member exchange is running: both members are in the 1:1, nobody has the floor.
    data, busy = seen(meeting + [opens], "o02-security")
    assert data["progress"]["paused"]["current"] == {"seq": 1, "exchange": 2}
    assert [p["seq"] for p in data["progress"]["paused"]["pairs"]] == [1]  # the running one too
    assert busy == ["security", "tpm"] and data["progress"]["holder"] is None
    assert {r["role"]: r["state"] for r in data["roster"]}["owner"] == "spoke"

    # The members are done and the host's closing exchange is running: the host alone.
    data, busy = seen(meeting + [opens, answers], "o03-manager")
    assert data["progress"]["paused"]["current"] == {"seq": 1, "exchange": None}
    assert [p["seq"] for p in data["progress"]["paused"]["pairs"]] == [1]
    assert busy == ["manager"] and data["progress"]["holder"] is None
    assert data["one_on_ones"][0]["ended"] is None  # only the final reduction finishes it

    # The closing exchange finalised it: nothing pending, and the floor is back.
    data, busy = seen(meeting + [opens, answers, closes], "t05-tpm")
    assert data["progress"]["paused"] is None and busy == []
    assert data["progress"]["holder"] == "owner"
    assert data["one_on_ones"][0]["agreed"] == "tpm sequences it, security signs off"

    # Mid-1:1: the process lost, the chair's retake phase, or a decision. No pause.
    lost = Reduction(kind="lost", json={"error": "the meeting was lost"})
    decision = Reduction(kind="decision", phase="decision", review_state="pending", json={
        "verdict": "Approve.", "delivered": True, "rechecks": [], "ended": "turn cap",
        "dropped_one_on_ones": [],
    })
    for reductions, phase in [
        (meeting + [opens, lost], "o02-security"),
        (meeting + [opens], "decision-take2"),
        (meeting + [opens, decision], "ruling"),
    ]:
        data, busy = seen(reductions, phase)
        assert data["progress"]["paused"] is None and busy == [], phase


def test_view_paused_before_t01_lists_every_up_front_pair():
    """Gap 2 before the first turn: the plan's pairs are pending too, and every
    pending pair is listed, the running one included."""
    one = _oo_pair(1, "owner", ["owner", "tpm"], "the rollout")
    two = _oo_pair(2, "manager", ["manager", "security"], "the threat model")
    reductions = [_oo_room(), _oo_plan(one, two), _oo(one, "tpm", 1, used=1)]

    data = view_data(_run("o02-owner"), reductions)
    paused = data["progress"]["paused"]

    assert [p["seq"] for p in paused["pairs"]] == [1, 2]
    assert paused["current"] == {"seq": 1, "exchange": 2}
    assert sorted(r["role"] for r in data["roster"] if r["state"] == "in_one_on_one") == [
        "owner", "tpm"]


def test_view_cap_unaffected_by_one_on_one_reductions(monkeypatch):
    """1:1 reductions carry no cap, role or turn (C6), and the 1:1 budget rides on
    the reductions, never on this process's environment (D10)."""
    monkeypatch.setenv("HERMES_COMMITTEE_MAX_TURNS", "30")
    monkeypatch.setenv("HERMES_COMMITTEE_MAX_ONE_ON_ONE_TURNS", "4")
    pair = _oo_pair(1, "owner", ["tpm", "owner"], "the rollout", origin="pause")
    before = [_oo_room(), _oo_plan(), _oo_turn(1, "senior_director"),
              _oo_turn(2, "owner", scheduled=[pair], align="tpm owner: the rollout")]
    assert view_data(_run("o01-tpm"), before)["progress"]["one_on_one"] == {
        "used": 0, "budget": 16,  # no exchange kept yet
    }

    reductions = before + [
        _oo(pair, "tpm", 1, used=1, after_turn=2), _oo(pair, "owner", 2, used=2, after_turn=2),
        _oo(pair, "tpm", 3, used=3, after_turn=2),
    ]
    data = view_data(_run("o04-owner"), reductions)

    assert data["progress"]["cap"] == 26            # the master's cap, not the env's 30
    assert data["progress"]["turn"] == 2            # a 1:1 is never a meeting turn
    assert [e["n"] for e in data["timeline"]] == [1, 2]
    assert data["progress"]["one_on_one"] == {"used": 3, "budget": 16}  # not the env's 4
    assert data["progress"]["paused"]["current"] == {"seq": 1, "exchange": 4}  # after the latest


def test_view_legacy_run2_has_no_one_on_ones(run2):
    """Run-2 predates 1:1s: no reduction carries `one_on_one_budget` (C8)."""
    data = view_data(_run("decision"), run2)
    mid = view_data(_run("t04-manager"), run2[:4])

    assert data["one_on_ones"] == [] and mid["one_on_ones"] == []
    assert (data["progress"]["paused"], data["progress"]["one_on_one"]) == (None, None)
    assert (mid["progress"]["paused"], mid["progress"]["one_on_one"]) == (None, None)
    assert [row["role"] for row in data["roster"]] == list(cast.CAST)
    assert {row["state"] for row in data["roster"]} == {"spoke"}
    assert mid["progress"]["holder"] == "manager"
    assert data["verdict"]["dropped_one_on_ones"] == []
    assert [step["origin_one_on_one"] for step in data["document"]["steps"]] == [None] * 6


def test_view_renders_a_one_on_one_without_its_file(tmp_path):
    """The private 1:1 file is the workers'. The view reads reductions alone and
    creates nothing (D9, D10)."""
    pair = _oo_pair(1, "owner", ["crew_owner", "owner"], "who owns the crews")
    reductions = [
        _oo_room(), _oo_plan(pair),
        _oo(pair, "crew_owner", 1, used=1, aligned=True, body="We own them."),
        _oo(pair, "owner", 2, used=2, aligned=True, body="Then keep them.",
            agreed="crews stay team-owned", ended="aligned", final=True),
    ]

    group = view_data(_run("t01-senior_director"), reductions)["one_on_ones"][0]

    assert [x["body"] for x in group["exchanges"]] == ["We own them.", "Then keep them."]
    assert group["agreed"] == "crews stay team-owned"
    assert not (tmp_path / "runs").exists()  # nothing read, nothing created

    # A file that disagrees with the reductions changes nothing: it is never opened.
    decoy = thread.one_on_one_path(RUN_ID, seq=1, members=["crew_owner", "owner"])
    decoy.write_text("# 1:1 1: DECOY\n\n## exchange 1: DECOY\n\nDECOY\n", encoding="utf-8")
    assert view_data(_run("t01-senior_director"), reductions)["one_on_ones"][0] == group


def test_edit_step_from_a_one_on_one_is_attributed_to_it(run2):
    """AC11, view half: a 1:1's edit names its seq and never a meeting turn (D7,
    C8), and that check runs before the `delegated_by_turn` branch."""
    run2[2].json.update(origin_one_on_one=1, delegated_by_turn=None)  # t03: from 1:1 1
    run2[5].json.update(origin_one_on_one=None, delegated_by_turn=5)  # t06: a meeting's
    run2[4].json["answers_turn"] = 4
    run2[8].json["origin_one_on_one"] = True                          # t09: a bool is no seq

    steps = {s["turn"]: s for s in view_data(_run("decision"), run2)["document"]["steps"]}

    def link(n):
        step = steps[n]
        return (step["owner_turn"], step["reviewer_turn"], step["provenance"],
                step["origin_one_on_one"])

    assert link(3) == (None, None, "recorded", 1)
    assert link(6) == (5, 4, "recorded", None)
    assert link(9) == (8, 7, "inferred", None)
    assert link(12) == (11, 10, "inferred", None)  # legacy: the key is absent


def test_view_verdict_lists_dropped_one_on_ones(run2):
    """Every drop the decision recorded, every reason (C6). The Verdict card picks
    the `budget` and `meeting ended` ones itself (Task 15)."""
    assert view_data(_run("decision"), run2)["verdict"]["dropped_one_on_ones"] == []

    drops = [
        {"seq": None, "text": "tpm tl: rollout", "members": ["tpm", "tl"], "reason": "budget"},
        {"seq": 3, "text": "pm tl: scope", "members": ["pm", "tl"], "reason": "meeting ended"},
        {"seq": None, "text": "tl tl: x", "members": None, "reason": "same member"},
    ]
    run2[-1].json["dropped_one_on_ones"] = drops + ["junk", 7]
    assert view_data(_run("decision"), run2)["verdict"]["dropped_one_on_ones"] == drops

    run2[-1].json["dropped_one_on_ones"] = "tpm tl"  # a scalar, hand-edited: no raise
    assert view_data(_run("decision"), run2)["verdict"]["dropped_one_on_ones"] == []
