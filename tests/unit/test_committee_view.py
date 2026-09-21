"""Tests for the committee's view payload.

Driven by the first live committee run. ``tests/data/committee-run-2-reductions.json``
is all 21 reductions run-2 wrote -- twenty turns and the chair's decision --
copied out of the run database unedited, so these assertions are against what
the playbook really produces rather than against a shape invented here.

That capture predates the five keys ``reduce`` learned for the view (``body``,
``stance``, ``artifact``, ``revised``, ``ended``), so the fixtures below
synthesise those five onto the rows and leave every other value byte-for-byte
as run-2 wrote it. Where a test needs a state run-2 never reached -- a pending
floor request, a meeting still sitting -- it slices or edits the capture and
says so.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.models import Reduction, Run
from playbooks.committee import cast
from playbooks.committee.view import view_data

FIXTURE = Path(__file__).parent.parent / "data" / "committee-run-2-reductions.json"

# Synthesised onto three of run-2's turns: the owner speaks at 02 and 20, the
# manager at 04. Every other turn carries no `stance` key at all -- absent, the
# way turnblock leaves an unwritten key.
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
            if doc["turn"] in _STANCES:
                doc["stance"] = _STANCES[doc["turn"]]
        else:
            # Run-2 reached turn 20 under HERMES_COMMITTEE_MAX_TURNS=20.
            doc["ended"] = "turn cap"
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

def test_view_data_returns_every_block_the_contract_names(run2, artifacts):
    original, _ = artifacts
    data = view_data(_run("decision"), run2)

    assert set(data) == {
        "kind", "roster", "progress", "timeline", "stances", "verdict", "artifacts",
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
        set(entry) == {"n", "role", "name", "title", "body", "action", "badges", "verified"}
        for entry in data["timeline"]
    )
    assert data["artifacts"] == {
        "original": {"name": original.name, "bytes": 11397},
        "revised": {"name": "federation-future.md", "bytes": 19100},
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


def test_the_chair_holds_the_floor_while_the_decision_is_running(run2):
    """Between the last turn and the verdict the chair is speaking, and the
    seat they chair from is the one that lights up."""
    data = view_data(_run("decision"), run2[:20])
    state = {row["role"]: row["state"] for row in data["roster"]}

    assert data["progress"]["holder"] == cast.CHAIR == "chair"
    assert state["senior_director"] == "holds_floor"
    assert data["verdict"] is None


def test_progress_counts_the_turns_against_the_cap(run2, monkeypatch):
    monkeypatch.setenv("HERMES_COMMITTEE_MAX_TURNS", "20")

    progress = view_data(_run("decision"), run2)["progress"]

    assert progress["turn"] == 20
    assert progress["cap"] == 20
    assert progress["holder"] is None  # the meeting is over
    assert progress["ended"] == "turn cap"


# --- stances ----------------------------------------------------------------

def test_stances_accumulate_and_absent_stays_absent(run2):
    """Criterion 10. A persona that stated none has no entry at all -- not an
    empty list, and never a neutral default."""
    data = view_data(_run("decision"), run2)
    stance = {row["role"]: row["stance"] for row in data["roster"]}

    assert set(data["stances"]) == {"owner", "manager"}
    assert data["stances"]["owner"] == [
        {"turn": 2, "text": _STANCES[2]},
        {"turn": 20, "text": _STANCES[20]},
    ]
    assert data["stances"]["manager"] == [{"turn": 4, "text": _STANCES[4]}]

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
    assert verdict["simulation"] is True
    assert verdict["artifact_intact"] is True
    assert verdict["dropped_delegation"] is None
    assert verdict["dropped_floor_requests"] == []
    assert [check["turn"] for check in verdict["checks"]] == [3, 6, 9, 12, 15, 18]
    assert all(check["verified"] is True for check in verdict["checks"])


@pytest.mark.parametrize(
    "ended", ["owner closed", "queue empty", "turn cap", "chair turn failed"]
)
def test_progress_names_why_the_meeting_stopped(run2, ended):
    """Criterion 11. Run-2 hit the cap and nothing on screen said so."""
    run2[-1].json["ended"] = ended

    assert view_data(_run("decision"), run2)["progress"]["ended"] == ended


# --- the edges --------------------------------------------------------------

def test_a_run_with_no_reductions_renders_an_empty_meeting():
    """`open` is a zero-ticket bootstrap, so the first poll sees nothing."""
    data = view_data(_run("open"), [])

    assert data["timeline"] == []
    assert data["stances"] == {}
    assert data["verdict"] is None
    assert data["artifacts"] == {"original": None, "revised": None}
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
    assert data["stances"] == {}


def test_the_revised_copy_is_none_until_the_file_exists(run2, artifacts):
    """`seed` records the revised path on every run, delegation or not, so the
    path proves nothing about whether a copy was ever made."""
    original, revised = artifacts
    revised.unlink()

    artifacts_block = view_data(_run("decision"), run2)["artifacts"]

    assert artifacts_block["original"] == {"name": original.name, "bytes": 11397}
    assert artifacts_block["revised"] is None
