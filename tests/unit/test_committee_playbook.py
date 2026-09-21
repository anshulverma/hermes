"""Tests for the committee playbook.

TDD: written FIRST, watched fail, then the module implemented.

A committee turn has to say more than its prose does -- whether the speaker
wants the floor again, whether the owner is delegating an edit or closing the
discussion -- and the transport gives the master exactly one channel to say it
on: the worker's final text under ``answer``. So the signal rides in a fenced
block with its own tag, the convention
``playbooks/research/verdict.py:14-18,30,34`` established. Present and
parseable, or absent -- and absent stays absent, never inferred into a False.
"""
from __future__ import annotations

import itertools
import random
import re

import pytest

from engine.models import Driver, Finding, Reduction, Result, Run, Ticket
from playbooks.committee import cast, turnblock
from playbooks.committee import turnblock as T
from playbooks.committee.playbook import _apply_block


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


def _fenced(body: str) -> str:
    """An answer the way a worker writes one: prose, then the block."""
    return f"I think the second section is doing two jobs.\n\n```{T.FENCE_TAG}\n{body}\n```\n"


# --- turnblock: parsing --------------------------------------------------

def test_a_well_formed_turn_block_is_parsed():
    answer = _fenced(
        "request_floor: yes\n"
        "delegate: no\n"
        "action: tighten the intro to one paragraph\n"
        "close: no"
    )

    assert T.parse(answer) == {
        "request_floor": True,
        "delegate": False,
        "action": "tighten the intro to one paragraph",
        "close": False,
    }


def test_no_block_is_no_signal_rather_than_a_guess():
    """An unstated key must never be defaulted to False -- the reduction
    records what the speaker actually said, not what we assumed."""
    assert T.parse("I have nothing further. Ship it.") == {}
    assert T.parse("") == {}
    assert T.parse(None) == {}


def test_unknown_keys_are_dropped_not_carried():
    """`urgency` and `reason` were deliberately cut: the queue is FIFO and the
    prose already says why. An agent adding them back changes nothing."""
    answer = _fenced("request_floor: yes\nurgency: high\nreason: this blocks launch")

    assert T.parse(answer) == {"request_floor": True}


def test_a_malformed_block_yields_nothing():
    """"Said their piece, nothing further" is the right reading of junk."""
    assert T.parse(_fenced("request_floor\ndelegate:\n???")) == {}


def test_yes_and_no_are_case_insensitive():
    assert T.parse(_fenced("request_floor: YES\nclose: No")) == {
        "request_floor": True,
        "close": False,
    }


def test_the_last_block_wins_when_a_speaker_emits_two():
    answer = _fenced("close: yes") + _fenced("close: no")

    assert T.parse(answer) == {"close": False}


def test_a_delegation_with_an_empty_action_carries_no_action():
    """reduce drops such a delegation whole; parse's job is to report that the
    action line was not usable, not to invent one."""
    assert T.parse(_fenced("delegate: yes\naction:")) == {"delegate": True}


def test_an_action_longer_than_the_cap_is_clipped():
    action = T.parse(_fenced("action: " + "x" * 500))["action"]

    assert len(action) == T.ACTION_MAX


def test_a_junk_flag_value_is_dropped_rather_than_read_as_no():
    """`request_floor: maybe` is not a no. Absent stays absent."""
    assert T.parse(_fenced("request_floor: maybe")) == {}


def test_a_colon_inside_an_action_survives():
    answer = _fenced("delegate: yes\naction: rename section 2: Findings")

    assert T.parse(answer) == {
        "delegate": True,
        "action": "rename section 2: Findings",
    }


# --- turnblock: stripping ------------------------------------------------

def test_the_block_is_removed_from_the_prose_it_travelled_in():
    """The block is plumbing. It is consumed by reduce; the thread shows a
    reader the turn, not the signalling."""
    stripped = T.strip(_fenced("request_floor: yes\nclose: no"))

    assert stripped == "I think the second section is doing two jobs."
    assert T.FENCE_TAG not in stripped
    assert "request_floor" not in stripped


def test_an_ordinary_code_fence_survives_stripping():
    """The tag is what identifies our block. A speaker quoting code keeps it."""
    answer = "Look at this:\n\n```python\nprint('hi')\n```\n"

    assert "print('hi')" in T.strip(answer)
    assert T.strip(answer) == answer.strip()


def test_stripping_prose_with_no_block_changes_nothing():
    assert T.strip("I have nothing further.") == "I have nothing further."


def test_stripping_tolerates_no_input():
    """A failed worker yields no answer at all, and the thread still gets a
    stub entry -- so strip has to survive None."""
    assert T.strip(None) == ""
    assert T.strip("") == ""


# --- turnblock: the instruction handed to a speaker ----------------------

def test_the_reviewer_instruction_documents_only_the_floor_request():
    """delegate and close are the owner's to use. Documenting them to a
    reviewer invites a block reduce is obliged to throw away."""
    text = T.instruction()

    assert T.FENCE_TAG in text
    assert "request_floor" in text
    for key in ("delegate", "action", "close"):
        assert key not in text


def test_the_owner_instruction_documents_all_four_keys():
    text = T.instruction(owner=True)

    assert T.FENCE_TAG in text
    for key in T.KEYS:
        assert key in text


def test_the_instructions_are_small_enough_to_ride_in_every_goal():
    """Both ride in a goal capped at 3600 characters that it shares with the
    persona, the charge and two paths."""
    assert len(T.instruction()) < 500
    assert len(T.instruction(owner=True)) < 500


def test_what_the_instruction_asks_for_is_what_parse_accepts():
    """The contract has to be self-consistent: a speaker that follows the
    instruction literally must produce something parse() reads."""
    pattern = r"```" + T.FENCE_TAG + r"\n(.*?)\n```"

    reviewer = re.search(pattern, T.instruction(), re.S)
    assert reviewer, "the reviewer instruction must contain a worked example"
    assert T.parse(_fenced(reviewer.group(1))) == {"request_floor": False}

    owner = re.search(pattern, T.instruction(owner=True), re.S)
    assert owner, "the owner instruction must contain a worked example"
    assert T.parse(_fenced(owner.group(1))) == {
        "request_floor": False,
        "delegate": False,
        "close": False,
    }


# --- the cast ---------------------------------------------------------------

_PERSONA_FIELDS = {
    "role",
    "name",
    "title",
    "altitude",
    "goal",
    "ambition",
    "stake",
    "lens",
    "style",
}


def test_cast_has_nine_roles_each_with_nine_filled_fields():
    """Every persona is complete: the request asked for all nine fields."""
    assert len(cast.CAST) == 9
    assert set(cast.CAST) == {
        "owner",
        "senior_director",
        "manager",
        "tpm",
        "pm",
        "tl",
        "staff_ic",
        "data_scientist",
        "junior_ic",
    }
    for role, p in cast.CAST.items():
        assert set(p) == _PERSONA_FIELDS, role
        assert p["role"] == role
        for field, value in p.items():
            assert isinstance(value, str), f"{role}.{field}"
            assert value.strip(), f"{role}.{field} is empty"


def test_seniority_is_the_seven_reviewers_in_order():
    """Opening-round order, with the owner and the junior IC held out (§4)."""
    assert cast.SENIORITY == (
        "senior_director",
        "manager",
        "tpm",
        "pm",
        "tl",
        "staff_ic",
        "data_scientist",
    )
    assert cast.OWNER not in cast.SENIORITY
    assert cast.JUNIOR not in cast.SENIORITY
    assert set(cast.SENIORITY) <= set(cast.CAST)
    assert len(set(cast.SENIORITY)) == 7


def test_persona_resolves_the_chair_sentinel_to_the_chairing_persona():
    assert cast.CHAIR == "chair"
    assert cast.CHAIR_ROLE == "senior_director"
    assert cast.persona(cast.CHAIR) is cast.CAST["senior_director"]
    assert cast.persona("pm")["name"] == "Elena Vargas"
    with pytest.raises(KeyError):
        cast.persona("cto")


def test_brief_carries_every_persona_field():
    text = cast.brief("staff_ic")
    p = cast.CAST["staff_ic"]
    assert text.startswith("You are Priya Raman, Staff Engineer.")
    for field in ("altitude", "goal", "ambition", "stake", "lens", "style"):
        assert p[field] in text, field


def test_title_names_the_speaker_and_the_kind():
    assert cast.title("tpm", "turn") == (
        "Sam Iyer (tpm) takes the floor in the committee thread"
    )
    assert cast.title(cast.JUNIOR, "edit") == (
        "Alex Moreau (junior_ic) applies the edit the owner delegated"
    )
    assert cast.title(cast.CHAIR, "decision") == (
        "Dana Whitfield (chair) delivers the committee decision"
    )


# --- goal assembly ----------------------------------------------------------

_ARTIFACT = "/home/x/.hermes/runs/committee-20260918-000000/artifact/proposal.md"
_THREAD = "/home/x/.hermes/runs/committee-20260918-000000/thread.md"
_REVISED = "/home/x/.hermes/runs/committee-20260918-000000/revised/proposal.md"
_CHARGE = "Approve the storage migration?"

# The three completion conditions, quoted verbatim from spec §9. They are
# written out here rather than imported so the test fails if the wording drifts.
_DONE_TURN = (
    "Done when: your turn is written as your answer and ends with one "
    "hermes-turn block."
)
_DONE_DECISION = (
    "Done when: your answer is the committee's decision — approve / approve "
    "with changes / do not approve — with the reasons, and states that this "
    "verdict is a simulation, not an approval."
)
_GUARDRAIL = (
    "This review lands nothing, submits nothing and touches no repository. "
    "Read the artifact and the thread, and write no file at all."
)


def test_reviewer_goal_carries_its_material_and_its_completion_condition():
    g = cast.goal(
        "tl",
        charge=_CHARGE,
        artifact=_ARTIFACT,
        thread=_THREAD,
        revised=_REVISED,
    )
    assert "You are Marcus Feld, Tech Lead." in g
    assert _ARTIFACT in g
    assert _THREAD in g
    assert _CHARGE in g
    assert _GUARDRAIL in g
    assert turnblock.instruction(owner=False).strip() in g
    assert g.endswith(_DONE_TURN)


def test_owner_goal_says_whose_floor_it_is_and_gets_the_owner_block():
    g = cast.goal(
        cast.OWNER,
        charge=_CHARGE,
        artifact=_ARTIFACT,
        thread=_THREAD,
        revised=_REVISED,
    )
    assert "You are Maya Okonkwo, Staff Engineer & proposal owner." in g
    assert "Answer the member who spoke last" in g
    assert turnblock.instruction(owner=True).strip() in g
    assert _ARTIFACT in g
    assert _THREAD in g
    assert g.endswith(_DONE_TURN)


def test_junior_goal_names_the_revised_path_and_the_delegated_action():
    g = cast.goal(
        cast.JUNIOR,
        charge=_CHARGE,
        artifact=_ARTIFACT,
        thread=_THREAD,
        revised=_REVISED,
        action="add a rollback section naming who pages",
    )
    assert "You are Alex Moreau, Software Engineer." in g
    assert _ARTIFACT in g
    assert _THREAD in g
    assert _REVISED in g
    assert "add a rollback section naming who pages" in g
    # The one file it may write, and the only file it may write.
    assert "the only file you may write" in g
    # Its block keys are all ignored (§5.4), so it is not asked for a block.
    assert "hermes-turn" not in g
    assert g.endswith(
        f"Done when: {_REVISED} carries the delegated change and your answer "
        "states in one line what you changed."
    )


def test_junior_goal_without_an_action_is_a_named_failure():
    with pytest.raises(ValueError, match="junior_ic"):
        cast.goal(
            cast.JUNIOR,
            charge=_CHARGE,
            artifact=_ARTIFACT,
            thread=_THREAD,
            revised=_REVISED,
        )


def test_chair_goal_is_the_decision_and_calls_the_verdict_a_simulation():
    g = cast.goal(
        cast.CHAIR,
        charge=_CHARGE,
        artifact=_ARTIFACT,
        thread=_THREAD,
        revised=_REVISED,
    )
    assert "You are Dana Whitfield, Senior Director of Engineering." in g
    assert _ARTIFACT in g
    assert _THREAD in g
    assert _REVISED in g
    assert "simulation" in g
    assert _GUARDRAIL in g
    assert g.endswith(_DONE_DECISION)


def test_the_guardrail_survives_a_maximal_charge():
    """The charge absorbs the cut; the tail is never clipped."""
    g = cast.goal(
        "data_scientist",
        charge="x" * 5000,
        artifact=_ARTIFACT,
        thread=_THREAD,
        revised=_REVISED,
    )
    assert _GUARDRAIL in g
    assert g.endswith(_DONE_TURN)
    assert "x" * cast.CHARGE_MAX not in g
    assert "x" * (cast.CHARGE_MAX - 1) in g
    assert "…" in g


def test_every_goal_stays_under_the_budget_at_maximum_size():
    """Longest persona, an over-length charge and action, and deep paths."""
    deep = "/home/anshulverma/.hermes/runs/committee-20260918-000000/" + "d" * 100
    artifact = f"{deep}/proposal-under-review.md"
    thread = f"{deep}/thread.md"
    revised = f"{deep}/revised/proposal-under-review.md"
    for role in list(cast.CAST) + [cast.CHAIR]:
        g = cast.goal(
            role,
            charge="c" * 5000,
            artifact=artifact,
            thread=thread,
            revised=revised,
            action="a" * 5000,
        )
        assert len(g) < cast.GOAL_MAX, f"{role}: {len(g)}"
        assert len(g) > 1500, f"{role}: {len(g)}"


# --- thread.md: the transcript ---

def test_thread_header_carries_the_charge_the_artifact_and_the_roster(tmp_path):
    """write_header lands under HERMES_HOME and names the charge, the artifact and everyone."""
    from playbooks.committee import thread

    run_id = "committee-20260918-000000"
    artifact = str(tmp_path / "proposal.md")
    thread.write_header(
        run_id,
        charge="Decide whether to approve the queue rewrite.",
        artifact=artifact,
        roster=[
            "Dana Okoye, Senior Director (senior_director)",
            "Priya Raman, Staff Engineer (staff_ic)",
        ],
    )

    written = thread.path(run_id)
    assert written == tmp_path / "runs" / run_id / "thread.md"
    text = written.read_text(encoding="utf-8")
    assert text.startswith(f"# Committee — {run_id}")
    assert "**Charge:** Decide whether to approve the queue rewrite." in text
    assert f"**Artifact:** {artifact}" in text
    assert "- Dana Okoye, Senior Director (senior_director)" in text
    assert "- Priya Raman, Staff Engineer (staff_ic)" in text


def test_thread_appends_turns_in_order_and_never_truncates(tmp_path):
    """Two turns land in order, in the spec's heading format, and keep the header."""
    from playbooks.committee import cast, thread

    run_id = "committee-20260918-000000"
    thread.write_header(run_id, charge="c", artifact="a", roster=[])
    thread.append_turn(run_id, turn=3, role="staff_ic", body="The retry loop is unbounded.\n")
    thread.append_turn(run_id, turn=4, role="owner", body="Agreed, I will cap it.")

    text = thread.path(run_id).read_text(encoding="utf-8")
    staff = cast.persona("staff_ic")
    owner = cast.persona("owner")
    h3 = f"## turn 03 — {staff['name']}, {staff['title']} (staff_ic)"
    h4 = f"## turn 04 — {owner['name']}, {owner['title']} (owner)"

    assert f"{h3}\n\nThe retry loop is unbounded.\n" in text
    assert f"{h4}\n\nAgreed, I will cap it.\n" in text
    assert text.index(h3) < text.index(h4)
    # append-only: the second write did not truncate the first, nor the header
    assert text.count("# Committee") == 1
    assert text.count("## turn ") == 2


def test_thread_empty_body_writes_the_no_turn_stub(tmp_path):
    """A turn whose worker produced nothing still gets a contiguous, visible entry."""
    from playbooks.committee import cast, thread

    run_id = "committee-20260918-000000"
    thread.write_header(run_id, charge="c", artifact="a", roster=[])
    thread.append_turn(run_id, turn=7, role="pm", body="   ")

    text = thread.path(run_id).read_text(encoding="utf-8")
    pm = cast.persona("pm")
    assert thread.NO_TURN == "_(no turn delivered — the worker failed; see hermes show)_"
    assert f"## turn 07 — {pm['name']}, {pm['title']} (pm)\n\n{thread.NO_TURN}\n" in text


def test_thread_decision_heading_names_the_chair(tmp_path):
    """append_decision writes the chair heading, with no role suffix."""
    from playbooks.committee import cast, thread

    run_id = "committee-20260918-000000"
    thread.write_header(run_id, charge="c", artifact="a", roster=[])
    thread.append_decision(
        run_id,
        body="Approve with changes. This verdict is a simulation, not an approval.",
    )

    text = thread.path(run_id).read_text(encoding="utf-8")
    chair = cast.persona(cast.CHAIR_ROLE)
    heading = f"## decision — {chair['name']}, {chair['title']}"
    assert f"{heading}\n\nApprove with changes." in text
    tail = text.split("## decision")[1]
    assert "(senior_director)" not in tail


# --- the revised copy and its digest ---

def test_thread_revised_path_uses_the_basename(tmp_path):
    """A nested or relative artifact path cannot escape the run's revised directory."""
    from playbooks.committee import thread

    run_id = "committee-20260918-000000"
    revised = tmp_path / "runs" / run_id / "revised"

    assert thread.revised_path(run_id, "/a/b/../nested/proposal.md") == revised / "proposal.md"
    assert revised.is_dir()  # state_dir("runs", run_id, "revised") created it
    assert thread.revised_path(run_id, "../../etc/passwd") == revised / "passwd"


def test_thread_ensure_revised_copies_once_and_never_clobbers(tmp_path):
    """First call byte-copies the original; a second call leaves the junior IC's edit alone."""
    from playbooks.committee import thread

    run_id = "committee-20260918-000000"
    artifact = tmp_path / "proposal.md"
    artifact.write_bytes(b"hello\n")

    copy = thread.ensure_revised(run_id, str(artifact))
    assert copy == tmp_path / "runs" / run_id / "revised" / "proposal.md"
    assert copy.read_bytes() == b"hello\n"

    copy.write_bytes(b"hello\nworld\n")  # the junior IC's edit
    mtime = copy.stat().st_mtime_ns

    again = thread.ensure_revised(run_id, str(artifact))
    assert again == copy
    assert copy.read_bytes() == b"hello\nworld\n"
    assert copy.stat().st_mtime_ns == mtime
    assert artifact.read_bytes() == b"hello\n"  # the original is never touched


def test_thread_digest_is_empty_for_a_missing_file_and_tracks_content(tmp_path):
    """digest() is the §7 re-check: absent reads as "", and content changes move it."""
    from playbooks.committee import thread

    target = tmp_path / "revised.md"
    assert thread.digest(target) == ""
    assert thread.digest(str(target)) == ""

    target.write_bytes(b"hello\n")
    assert thread.digest(target) == (
        "5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03"
    )

    target.write_bytes(b"hello\nworld\n")
    assert thread.digest(str(target)) == (
        "4a1e67f2fe1d1cc7b31d0ca2ec441da4778203a036a77da10344c85e24ff0f92"
    )

    assert thread.digest(tmp_path) == ""  # a directory is not a file


# --- part 1: the class skeleton and its per-run state -----------------------


def _run(config=None, phase="open", reductions=None):
    """Helper: construct a Run for testing."""
    return Run(
        id="committee-20260918-000000",
        playbook="committee",
        site="local",
        base_ref="main",
        config=config if config is not None else {},
        phase=phase,
        reductions=reductions or [],
    )


def _committee():
    """A fresh CommitteePlaybook, imported late the way the research tests do."""
    from playbooks.committee.playbook import CommitteePlaybook

    return CommitteePlaybook()


def test_the_playbook_names_itself_and_its_two_static_phases():
    """name and phases are the only attributes the engine reads off a playbook."""
    pb = _committee()

    assert pb.name == "committee"
    assert pb.phases == ["open", "decision"]
    # phases is per-instance, not shared class state
    assert pb.phases is not _committee().phases


def test_state_starts_at_turn_one_with_the_opening_round_loaded():
    """The per-run dict is created on first use, with exactly the documented keys."""
    from playbooks.committee import cast

    pb = _committee()
    run = _run()
    s = pb._state(run)

    assert set(s) == {
        "turn", "opening", "queue", "delegation", "pending_action", "last_speaker",
        "closed", "verdict", "current_role", "current_turn", "dropped_delegation",
        "rechecks", "pre_edit_digest", "charge", "artifact", "revised", "roster",
        "max_turns",
    }
    assert s["turn"] == 1
    assert s["opening"] == list(cast.SENIORITY)
    assert isinstance(s["opening"], list)  # a copy: popping must not touch the cast
    # regression 1: last_speaker starts "owner", not None -- with None the owner-reply
    # rule fires before the opening round and mints t01-owner, a reply to an empty thread.
    assert s["last_speaker"] == "owner"
    assert s["max_turns"] == 30
    assert s["queue"] == [] and s["rechecks"] == [] and s["roster"] == {}
    assert s["pre_edit_digest"] == ""
    assert s["delegation"] is None and s["pending_action"] is None
    assert s["dropped_delegation"] is None and s["current_role"] is None
    assert s["closed"] is False and s["verdict"] == "" and s["current_turn"] == 0
    assert s["charge"] == "" and s["artifact"] == "" and s["revised"] == ""
    assert pb._state(run) is s  # same run, same dict


def test_state_is_lru_bounded_at_sixteen_runs():
    """The cache evicts the oldest run, as playbooks/research/playbook.py:232-244 does."""
    from playbooks.committee.playbook import _CACHE_MAX

    assert _CACHE_MAX == 16
    pb = _committee()
    first = _run()
    first.id = "committee-run-000"
    pb._state(first)
    for n in range(1, _CACHE_MAX + 1):
        later = _run()
        later.id = f"committee-run-{n:03d}"
        pb._state(later)

    assert len(pb._state_by_run) == _CACHE_MAX
    assert "committee-run-000" not in pb._state_by_run
    assert "committee-run-016" in pb._state_by_run


# --- the state machine: the executable model of spec 5.3, ported ------------
#
# The model drove a transcription of the pseudocode; these drive the real
# CommitteePlaybook.next_phase through the real _apply_block. Three layers, all
# three kept: the named regressions and boundaries, all 125 three-turn prefixes
# of the block vocabulary, and a seeded fuzz loop over random blocks and caps.
#
# There is no second transcription of the gates here: _drive calls the product's
# _apply_block, so deleting the gates from reduce turns every layer below RED.

_REVIEWERS = list(cast.SENIORITY)


def _drive(script, max_turns=30):
    """Drive a whole run through the real next_phase.

    `script` maps a phase name to the block its speaker emits, or is a callable
    (phase, state) -> block. A `_ok: False` key models a turn whose worker
    produced no finding. Returns (pb, run, state, phases_seen, speakers).
    """
    pb = _committee()
    run = _run()
    s = pb._state(run)
    s["max_turns"] = max_turns
    seen = ["open"]
    speakers = []
    while True:
        nxt = pb.next_phase(run)
        if nxt is None:
            break
        assert nxt not in seen, f"REPEATED PHASE {nxt!r} (seen={seen})"
        assert len(seen) < 400, f"NON-TERMINATION: {seen[:40]}..."
        seen.append(nxt)
        run.phase = nxt
        if nxt == "decision":
            s["verdict"] = "approve"  # what reduce("decision") will set
            speakers.append("chair")
            continue
        # the turn number reduce() reads must match the name next_phase minted
        assert nxt == f"t{s['current_turn']:02d}-{s['current_role']}"
        speakers.append(s["current_role"])
        block = script(nxt, s) if callable(script) else dict(script.get(nxt, {}))
        # a turn whose worker produced no finding contributes nothing to the
        # gates; next_phase still advances past it
        if block.get("_ok", True):
            _apply_block(s, s["current_role"], block)
    return pb, run, s, seen, speakers


def check_invariants(s, seen, speakers, max_turns=30):
    """Every property the model asserted on every run it drove."""
    assert len(seen) == len(set(seen)), "duplicate phase name"
    assert seen[-1] == "decision", f"did not end at decision: {seen[-1]}"
    assert seen.count("decision") == 1, "decision reached more than once"
    nums = [int(p[1:3]) for p in seen if p.startswith("t")]
    if nums:
        assert max(nums) <= max_turns, f"turn cap exceeded: max NN={max(nums)} > {max_turns}"
        assert nums == sorted(nums), "turn numbers out of order"
        assert len(nums) == len(set(nums)), "turn number reused"
    # Only the cap may drop a delegation (spec 5.3). `s["delegation"] is None` would
    # be a tautology here -- both exits to `decision` go through `_decision`, which
    # clears it unconditionally -- so assert the property that actually discriminates.
    if s["dropped_delegation"]:
        assert s["turn"] > s["max_turns"], "a delegation was dropped with turns to spare"
    # every reviewer turn is answered by the owner, unless the cap cut it off
    body = speakers[:-1]  # drop the chair
    for i, who in enumerate(body):
        if who in _REVIEWERS and i + 1 < len(body):
            assert body[i + 1] == "owner", f"reviewer {who} at {i} unanswered by {body[i+1]}"
        # a trailing reviewer is the documented cap cut-off


# --- the seven regressions from spec 11, each a defect caught in hardening ---


def test_regression_turn_01_is_the_first_opening_reviewer():
    # 1: with last_speaker=None the owner-reply rule fires first and mints t01-owner,
    # an owner reply to an empty thread -- the turn the `open` bootstrap exists to delete.
    _, _, _, seen, sp = _drive({})

    assert seen[1] == "t01-senior_director", seen[1]
    assert sp[0] == "senior_director", f"turn 01 speaker is {sp[0]}, expected first reviewer"
    assert "t01-owner" not in seen


def test_regression_the_decision_phase_is_seeded_as_the_chair():
    # 2: both exits to `decision` go through _decision, which sets
    # current_role="chair". seed hardcodes the chair for the decision phase, so this
    # line is not what builds that ticket -- what it buys is that the state dict stays
    # truthful about who is speaking. _reduce_turn attributes a turn off current_role
    # and fails closed when it is wrong, so a stale role is a real defect.
    _, _, closed_state, closed_seen, _ = _drive({"t02-owner": {"close": True}})
    assert closed_seen[-1] == "decision"
    assert closed_state["current_role"] == "chair"

    _, _, capped_state, capped_seen, _ = _drive(lambda phase, s: {}, max_turns=3)
    assert capped_seen[-1] == "decision", capped_seen
    assert capped_state["current_role"] == "chair"


def test_regression_a_turn_with_no_finding_still_advances_the_counter():
    # 3: the counter advances in next_phase, not reduce. Advanced in reduce it would
    # stall on a failed turn and re-emit that phase name, which _phase_reduced
    # (engine/dispatch.py:311-321) reads as "already reduced" -- a silent deadlock.
    _, _, s, seen, sp = _drive({
        "t03-manager": {"_ok": False, "request_floor": True},
        "t04-owner": {"_ok": False, "close": True},
    })
    check_invariants(s, seen, sp)

    assert seen[4] == "t04-owner" and seen[5] == "t05-tpm", seen[:8]
    assert len(seen) == len(set(seen))
    assert s["queue"] == [], "a floor request from a turn with no finding was honoured"
    assert s["closed"] is False, "a close from a turn with no finding was honoured"
    assert max(int(p[1:3]) for p in seen if p.startswith("t")) == 14


def test_regression_next_phase_returns_none_at_decision_so_is_done_is_reachable():
    # 4: is_done is consulted only when next_phase returns None
    # (engine/dispatch.py:281-292); a machine that kept minting names never finishes.
    pb = _committee()
    run = _run(phase="decision")
    s = pb._state(run)

    assert pb.next_phase(run) is None
    assert pb.is_done(run) is False  # no verdict yet -> the run ends failed, by design
    s["verdict"] = "approve with changes"
    assert pb.is_done(run) is True

    mid = _committee()
    mid_run = _run(phase="t04-owner")
    mid._state(mid_run)["verdict"] = "approve"
    assert mid.is_done(mid_run) is False, "is_done fired before the decision phase"


def test_regression_the_floor_queue_is_entered_after_the_opening_round():
    # 5: once `opening` drains, rule 5 must actually pop the queue -- an early exit to
    # decision would silently discard every floor request the committee made.
    _, _, s, seen, sp = _drive({
        "t01-senior_director": {"request_floor": True},
        "t05-tpm": {"request_floor": True},
    })
    check_invariants(s, seen, sp)

    assert s["queue"] == []
    assert seen[15] == "t15-senior_director" and seen[17] == "t17-tpm", seen[14:]
    tail = sp[sp.index("data_scientist"):]
    assert tail == [
        "data_scientist", "owner", "senior_director", "owner", "tpm", "owner", "chair",
    ], tail


def test_regression_a_delegation_is_consumed_exactly_once_and_never_lost():
    # 6: the ordering defect the fuzz found at max_turns=2 -- with `close` tested first,
    # "make this change and we're done" dropped the edit on the floor. What catches it
    # across the driven runs is check_invariants' dropped_delegation clause: a
    # delegation dropped with turns still on the clock.
    _, _, once, once_seen, once_sp = _drive(
        {"t02-owner": {"delegate": True, "action": "tighten the risk section"}}
    )
    check_invariants(once, once_seen, once_sp)
    assert once_seen[3] == "t03-junior_ic", once_seen[:5]
    assert once_sp.count("junior_ic") == 1, f"delegation consumed more than once: {once_sp}"
    assert once["pending_action"] == "tighten the risk section"
    assert once_sp[once_sp.index("junior_ic") + 1] != "owner", \
        "junior_ic wrongly triggered an owner reply"

    _, _, both, both_seen, both_sp = _drive(
        {"t02-owner": {"close": True, "delegate": True, "action": "x"}}
    )
    check_invariants(both, both_seen, both_sp)
    assert both_sp.count("junior_ic") == 1, f"the delegated edit was dropped: {both_sp}"
    assert both_seen == [
        "open", "t01-senior_director", "t02-owner", "t03-junior_ic", "decision",
    ], both_seen

    _, _, capped, capped_seen, capped_sp = _drive(
        {"t02-owner": {"delegate": True, "action": "too late"}}, max_turns=2
    )
    check_invariants(capped, capped_seen, capped_sp, max_turns=2)
    assert "junior_ic" not in capped_sp, "the cap did not stop the edit"
    assert capped["delegation"] is None
    assert capped["dropped_delegation"] == "too late", \
        "a cap-dropped delegation must be recorded, not lost"


def test_regression_no_phase_repeats_and_the_cap_holds_across_a_full_run():
    # 7: a repeated phase name deadlocks the run silently (engine/dispatch.py:311-321)
    # and an NN above the cap breaks acceptance criterion 5.
    for max_turns in (1, 2, 3, 5, 8, 13, 30):
        _, _, s, seen, sp = _drive(lambda phase, st: {"request_floor": True},
                                   max_turns=max_turns)
        check_invariants(s, seen, sp, max_turns=max_turns)
        nums = [int(p[1:3]) for p in seen if p.startswith("t")]
        assert len(seen) == len(set(seen)), f"max_turns={max_turns}: {seen}"
        assert not nums or max(nums) <= max_turns, f"max_turns={max_turns}: {seen}"


# --- the two documented boundaries ------------------------------------------


def test_the_default_run_is_t01_through_t14_then_the_decision():
    """7 reviewers + 7 owner replies, no delegations, empty queue: highest NN is 14."""
    _, _, _, seen, _ = _drive({})

    assert seen == [
        "open",
        "t01-senior_director", "t02-owner",
        "t03-manager", "t04-owner",
        "t05-tpm", "t06-owner",
        "t07-pm", "t08-owner",
        "t09-tl", "t10-owner",
        "t11-staff_ic", "t12-owner",
        "t13-data_scientist", "t14-owner",
        "decision",
    ], seen


def test_max_turns_thirty_mints_t30_and_never_t31():
    """_turn post-increments: turn==30 mints t30 and leaves 31, which routes to decision."""
    _, _, s, seen, sp = _drive(lambda phase, st: {"request_floor": True}, max_turns=30)
    check_invariants(s, seen, sp, max_turns=30)

    nums = [int(p[1:3]) for p in seen if p.startswith("t")]
    assert max(nums) == 30
    assert not any(p.startswith("t31") for p in seen), seen[-3:]
    assert s["turn"] == 31


# --- the exhaustive and fuzz layers -----------------------------------------

_BLOCK_VOCABULARY = [
    {},
    {"request_floor": True},
    {"close": True},
    {"delegate": True, "action": "a"},
    {"_ok": False},
]

# The model ran 4000 fuzz iterations; 500 is what ships. Measured on this machine:
# 4000 runs cost 0.081 s and 500 cost 0.008 s, against a 16 s suite. 500 still draws
# each of the eight caps ~60 times, and the seed is fixed so the sample is the same
# sample on every run -- the delegate/close defect showed up at max_turns=2 within
# the first handful of iterations, as a dropped_delegation with turns to spare.
_FUZZ_RUNS = 500
_FUZZ_SEED = 20260918
_FUZZ_CAPS = [1, 2, 3, 5, 8, 13, 30, 31]


def test_every_three_turn_prefix_of_the_block_vocabulary_holds():
    """All 125 three-turn prefixes of the block vocabulary keep every invariant."""
    checked = 0
    for combo in itertools.product(_BLOCK_VOCABULARY, repeat=3):
        def script(phase, s, c=combo):
            index = s["turn"] - 2  # the turn that just spoke, 0-based
            return dict(c[index]) if 0 <= index < len(c) else {}

        try:
            _, _, s, seen, sp = _drive(script)
            check_invariants(s, seen, sp)
        except AssertionError as exc:
            raise AssertionError(f"combo={combo}: {exc}") from exc
        checked += 1

    assert checked == 125


def test_seeded_fuzz_over_random_blocks_and_random_caps():
    """500 seeded random runs, caps 1..31, every invariant on every run."""
    rng = random.Random(_FUZZ_SEED)
    for iteration in range(_FUZZ_RUNS):
        max_turns = rng.choice(_FUZZ_CAPS)

        def script(phase, s, r=rng):
            block = {}
            if r.random() < 0.35:
                block["request_floor"] = True
            if r.random() < 0.15:
                block["delegate"] = True
                block["action"] = "do the thing"
            if r.random() < 0.06:
                block["close"] = True
            if r.random() < 0.10:
                block["_ok"] = False
            return block

        try:
            _, _, s, seen, sp = _drive(script, max_turns=max_turns)
            check_invariants(s, seen, sp, max_turns=max_turns)
        except AssertionError as exc:
            raise AssertionError(
                f"seed-iter {iteration} max_turns={max_turns}: {exc}"
            ) from exc


# --- the four transport-path methods (spec §5.6) ---------------------------


def _payload(kind: str, role: str, action=None) -> dict:
    """Helper: a ticket payload of the exact shape seed() emits."""
    return {
        "role": role,
        "title": f"turn — {role}",
        "goal": "Read the artifact and take your turn.",
        "kind": kind,
        "action": action,
    }


def _ok_result(payload: dict, outcome: str = "ok") -> Result:
    """Helper: a worker Result carrying ``payload``."""
    return Result(
        outcome=outcome,
        termination_reason="goal_met" if outcome == "ok" else "driver_error",
        result_ref=None,
        error_summary=None,
        started_at=1000.0,
        ended_at=2000.0,
        payload=payload,
    )


def _result_doc(payload: dict, outcome: str = "ok") -> dict:
    """Helper: the outer result document contracts.validate_result checks."""
    return {
        "outcome": outcome,
        "termination_reason": "goal_met" if outcome == "ok" else "driver_error",
        "result_ref": None,
        "evidence_ref": None,
        "started_at": 1000.0,
        "ended_at": 2000.0,
        "error_summary": None,
        "payload": payload,
    }


def test_every_ticket_kind_validates_against_the_one_payload_schema():
    """One schema, every phase: turn, edit and decision all pass it."""
    from engine import contracts
    from playbooks.committee.playbook import CommitteePlaybook

    pb = CommitteePlaybook()
    cases = [
        ("t01-senior_director", _payload("turn", "senior_director")),
        ("t04-junior_ic", _payload("edit", "junior_ic", action="Add a rollback plan.")),
        ("decision", _payload("decision", "chair")),
    ]
    for phase, payload in cases:
        contracts.validate(payload, pb.payload_schema(phase))


def test_payload_schema_rejects_an_extra_key():
    """additionalProperties:false — a stray key is a terminal contract failure."""
    from engine import contracts
    from playbooks.committee.playbook import CommitteePlaybook

    payload = _payload("turn", "tpm")
    payload["urgency"] = "high"

    with pytest.raises(contracts.ContractError) as exc:
        contracts.validate(payload, CommitteePlaybook().payload_schema("t02-tpm"))
    assert "Additional property 'urgency' not allowed" in str(exc.value)


def test_payload_schema_requires_role_title_goal_and_kind():
    """Four required keys; dropping any one of them fails validation."""
    from engine import contracts
    from playbooks.committee.playbook import CommitteePlaybook

    schema = CommitteePlaybook().payload_schema("t03-pm")
    for key in ("role", "title", "goal", "kind"):
        payload = _payload("turn", "pm")
        del payload[key]
        with pytest.raises(contracts.ContractError) as exc:
            contracts.validate(payload, schema)
        assert f"Required key '{key}' is missing" in str(exc.value)


def test_action_is_nullable_and_kind_is_a_closed_vocabulary():
    """action is None on every turn but the junior IC's; kind is an enum of three."""
    from engine import contracts
    from playbooks.committee.playbook import CommitteePlaybook

    schema = CommitteePlaybook().payload_schema("t05-owner")

    contracts.validate(_payload("turn", "owner", action=None), schema)
    contracts.validate(_payload("edit", "junior_ic", action="Name the risk owner."), schema)

    absent = _payload("turn", "owner")
    del absent["action"]
    contracts.validate(absent, schema)  # not required, so absent is fine too

    with pytest.raises(contracts.ContractError) as exc:
        contracts.validate(_payload("vote", "owner"), schema)
    assert "Value 'vote' not in enum ['turn', 'edit', 'decision']" in str(exc.value)

    with pytest.raises(contracts.ContractError) as exc:
        contracts.validate(_payload("turn", "owner", action=7), schema)
    assert "Expected one of [string, null], got number" in str(exc.value)


def test_result_schema_accepts_prose_and_tolerates_extra_keys():
    """The prose is the result; the hermes-turn block is parsed out of it later."""
    from engine import contracts
    from playbooks.committee.playbook import CommitteePlaybook

    schema = CommitteePlaybook().result_schema("t06-staff_ic")

    contracts.validate_result(_result_doc({"answer": "I have two concerns."}), schema)
    contracts.validate_result(
        _result_doc({"answer": "I have two concerns.", "tokens": 812, "notes": ["a"]}),
        schema,
    )


def test_a_result_with_no_usable_answer_is_rejected_unless_the_worker_failed():
    """answer is required and must be text — but only when the outcome is ok."""
    from engine import contracts
    from playbooks.committee.playbook import CommitteePlaybook

    schema = CommitteePlaybook().result_schema("decision")

    with pytest.raises(contracts.ContractError) as exc:
        contracts.validate_result(_result_doc({}), schema)
    assert "$.payload: Required key 'answer' is missing" in str(exc.value)

    with pytest.raises(contracts.ContractError) as exc:
        contracts.validate_result(_result_doc({"answer": 3}), schema)
    assert "$.payload.answer: Expected string, got number" in str(exc.value)

    # validate_result skips the payload when outcome != "ok", which is why a dead
    # turn costs a thread stub (reduce's NO_TURN body) and not a contract failure.
    contracts.validate_result(_result_doc({}, outcome="driver_failed"), schema)


def test_driver_is_goal_only_by_default():
    """No methodology command unless one is configured: the prompt is the goal."""
    from playbooks.committee.playbook import CommitteePlaybook

    driver = CommitteePlaybook().driver("t01-senior_director")
    assert driver.command is None
    assert driver.args == {}
    assert driver.loop is None


def test_driver_reads_the_environment_at_call_time(monkeypatch):
    """Constructed before the var is set and still picks it up (spec §5.6)."""
    from playbooks.committee.playbook import CommitteePlaybook

    pb = CommitteePlaybook()
    assert pb.driver("decision").command is None

    monkeypatch.setenv("HERMES_COMMITTEE_DRIVER", "/monk")
    assert pb.driver("decision").command == "/monk"

    monkeypatch.setenv("HERMES_COMMITTEE_DRIVER", "   ")
    assert pb.driver("decision").command is None


def test_driver_is_the_same_for_every_phase(monkeypatch):
    """The method a persona reviews by does not change with whose turn it is."""
    from playbooks.committee.playbook import CommitteePlaybook

    monkeypatch.setenv("HERMES_COMMITTEE_DRIVER", "/dexter:solve")
    pb = CommitteePlaybook()
    expected = Driver(command="/dexter:solve", args={}, loop=None)
    for phase in ("open", "t01-senior_director", "t12-junior_ic", "decision"):
        assert pb.driver(phase) == expected


def test_verify_is_always_true():
    """Criterion 8: verify never returns False. See the method's docstring."""
    from playbooks.committee.playbook import CommitteePlaybook

    pb = CommitteePlaybook()
    run = _run(phase="t01-senior_director")
    ticket = Ticket(
        id=f"{run.id}/t01-senior_director",
        run_id=run.id,
        phase="t01-senior_director",
        state="running",
        resource_req="cpu",
        priority=0.0,
        attempts=0,
        payload=_payload("turn", "senior_director"),
    )

    assert pb.verify(run, ticket, _ok_result({"answer": "Two questions."}), site=None) is True
    assert pb.verify(run, ticket, _ok_result({}), site=None) is True
    assert pb.verify(run, ticket, _ok_result({"answer": "   "}), site=None) is True
    assert pb.verify(run, ticket, _ok_result({"answer": 3, "junk": None}), site=None) is True
    assert pb.verify(run, ticket, _ok_result({}, outcome="driver_failed"), site=None) is True


def test_the_transport_path_methods_need_no_per_run_state(monkeypatch):
    """What a separate `hermes serve --host` process sees: an empty state dict.

    A fresh instance has never called seed, reduce or next_phase for this run, so
    _state_by_run is empty — and all four transport-path methods still work, and
    leave it empty.
    """
    from engine import contracts
    from playbooks.committee.playbook import CommitteePlaybook

    monkeypatch.setenv("HERMES_COMMITTEE_DRIVER", "/monk")
    pb = CommitteePlaybook()
    assert pb._state_by_run == {}

    run = _run(phase="t09-junior_ic")
    ticket = Ticket(
        id=f"{run.id}/t09-junior_ic",
        run_id=run.id,
        phase="t09-junior_ic",
        state="running",
        resource_req="cpu",
        priority=0.0,
        attempts=0,
        payload=_payload("edit", "junior_ic", action="Add the rollback plan."),
    )

    contracts.validate(ticket.payload, pb.payload_schema(ticket.phase))
    contracts.validate_result(
        _result_doc({"answer": "Added it."}), pb.result_schema(ticket.phase)
    )
    assert pb.driver(ticket.phase).command == "/monk"
    assert pb.verify(run, ticket, _ok_result({"answer": "Added it."}), site=None) is True

    # None of the four reached for per-run state, so none of them minted any.
    assert pb._state_by_run == {}


# --- seed: the open bootstrap, the site guard, configuration ---------------


class _NamedSite:
    """A site stub: the §8 guard reads nothing off a site but ``name``."""

    def __init__(self, name: str):
        self.name = name


@pytest.fixture
def artifact(tmp_path, monkeypatch, clean_env):
    """An existing artifact file, exported the way §6 requires."""
    path = tmp_path / "proposal.md"
    path.write_text("# Proposal\n\nShip the thing.\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_COMMITTEE_ARTIFACT", str(path))
    return path


def test_seed_open_is_a_zero_ticket_bootstrap(artifact):
    """`open` seeds no ticket and writes the header: charge, artifact, roster."""
    from playbooks.committee import cast, thread

    pb = _committee()
    run = _run(config={"goals": ["Decide whether to fund the migration."]}, phase="open")

    assert pb.seed(run, _NamedSite("local")) == []

    header = thread.path(run.id).read_text(encoding="utf-8")
    assert "Decide whether to fund the migration." in header
    assert str(artifact) in header
    for role in cast.CAST:
        assert role in header
        assert cast.persona(role)["name"] in header

    s = pb._state(run)
    assert s["charge"] == "Decide whether to fund the migration."
    assert s["artifact"] == str(artifact)
    assert s["revised"] == str(thread.revised_path(run.id, str(artifact)))
    assert s["max_turns"] == 30


def test_seed_open_requires_the_artifact_variable():
    """Unset HERMES_COMMITTEE_ARTIFACT fails fast, naming the variable."""
    pb = _committee()
    with pytest.raises(ValueError) as excinfo:
        pb.seed(_run(phase="open"), _NamedSite("local"))
    assert "HERMES_COMMITTEE_ARTIFACT" in str(excinfo.value)


def test_seed_open_rejects_a_path_that_is_not_a_file(tmp_path, monkeypatch):
    """A path naming no readable file fails fast, naming the variable and the path."""
    from playbooks.committee import thread

    missing = tmp_path / "no-such-proposal.md"
    monkeypatch.setenv("HERMES_COMMITTEE_ARTIFACT", str(missing))

    pb = _committee()
    run = _run(phase="open")
    with pytest.raises(ValueError) as excinfo:
        pb.seed(run, _NamedSite("local"))

    message = str(excinfo.value)
    assert "HERMES_COMMITTEE_ARTIFACT" in message
    assert str(missing) in message
    # validated before anything is written
    assert not thread.path(run.id).exists()


def test_site_guard_accepts_local_subprocess_sites_only(artifact):
    """§8: `local` and `fan-*` pass; anything else raises, naming the site."""
    for name in ("local", "fan-claude", "fan-codex"):
        assert _committee().seed(_run(phase="open"), _NamedSite(name)) == []

    for name in ("devserver", "ssh", "fan"):
        with pytest.raises(ValueError) as excinfo:
            _committee().seed(_run(phase="open"), _NamedSite(name))
        assert repr(name) in str(excinfo.value)


def test_max_turns_reads_the_env_and_falls_back_on_junk(artifact, monkeypatch):
    """The cap is resolved once, at open seed time, and junk means 30."""
    monkeypatch.setenv("HERMES_COMMITTEE_MAX_TURNS", "5")
    pb = _committee()
    run = _run(phase="open")
    pb.seed(run, _NamedSite("local"))
    assert pb._state(run)["max_turns"] == 5

    monkeypatch.setenv("HERMES_COMMITTEE_MAX_TURNS", "soon")
    other = _committee()
    other.seed(run, _NamedSite("local"))
    assert other._state(run)["max_turns"] == 30


def test_charge_defaults_when_no_goals_and_is_clipped(artifact):
    """No --goals means the default charge; a long one is clipped at CHARGE_MAX."""
    from playbooks.committee import cast
    from playbooks.committee.playbook import DEFAULT_CHARGE

    pb = _committee()
    run = _run(config={}, phase="open")
    pb.seed(run, _NamedSite("local"))
    assert pb._state(run)["charge"] == DEFAULT_CHARGE
    assert DEFAULT_CHARGE == "Decide whether to approve this proposal."

    long_pb = _committee()
    long_run = _run(config={"goals": ["x" * 500, "y" * 500]}, phase="open")
    long_pb.seed(long_run, _NamedSite("local"))
    assert len(long_pb._state(long_run)["charge"]) == cast.CHARGE_MAX
    assert cast.CHARGE_MAX == 400


def test_turn_ticket_carries_exactly_the_frozen_payload_keys(artifact):
    """A turn phase seeds one ticket for s["current_role"], id f"{run.id}/{phase}"."""
    from engine import contracts
    from playbooks.committee import cast, thread

    pb = _committee()
    site = _NamedSite("local")
    run = _run(phase="open")
    pb.seed(run, site)

    phase = pb.next_phase(_run(phase="open"))
    assert phase == "t01-senior_director"

    tickets = pb.seed(_run(phase=phase), site)
    assert len(tickets) == 1
    t = tickets[0]
    assert t.id == f"{run.id}/{phase}"
    assert t.run_id == run.id
    assert t.phase == phase
    assert t.state == "queued"
    assert t.resource_req == "cpu"
    assert t.priority == 0.0
    assert t.attempts == 0
    assert set(t.payload) == {"role", "title", "goal", "kind", "action"}
    assert t.payload["role"] == "senior_director"
    assert t.payload["kind"] == "turn"
    assert t.payload["action"] is None
    assert str(artifact) in t.payload["goal"]
    assert str(thread.path(run.id)) in t.payload["goal"]
    assert len(t.payload["goal"]) <= cast.GOAL_MAX
    contracts.validate(t.payload, pb.payload_schema(phase))


def test_junior_seed_byte_copies_the_original_and_leaves_it_untouched(artifact):
    """§5.5: the revised copy is in place before the junior IC's worker runs."""
    from playbooks.committee import cast, thread

    pb = _committee()
    site = _NamedSite("local")
    run = _run(phase="open")
    pb.seed(run, site)
    original = artifact.read_bytes()

    s = pb._state(run)
    s["current_role"] = cast.JUNIOR
    s["pending_action"] = "cut the roadmap section to one paragraph"

    tickets = pb.seed(_run(phase="t04-junior_ic"), site)

    revised = thread.revised_path(run.id, str(artifact))
    assert revised.read_bytes() == original
    assert artifact.read_bytes() == original
    t = tickets[0]
    assert set(t.payload) == {"role", "title", "goal", "kind", "action"}
    assert t.payload["role"] == "junior_ic"
    assert t.payload["kind"] == "edit"
    assert t.payload["action"] == "cut the roadmap section to one paragraph"
    assert str(revised) in t.payload["goal"]


def test_a_second_junior_seed_keeps_the_edited_revised_copy(artifact):
    """ensure_revised copies only when absent: a later edit builds on the first."""
    from playbooks.committee import cast, thread

    pb = _committee()
    site = _NamedSite("local")
    run = _run(phase="open")
    pb.seed(run, site)

    s = pb._state(run)
    s["current_role"] = cast.JUNIOR
    s["pending_action"] = "cut the roadmap section to one paragraph"
    pb.seed(_run(phase="t04-junior_ic"), site)

    revised = thread.revised_path(run.id, str(artifact))
    revised.write_text("# Proposal\n\nShip the thing, but smaller.\n", encoding="utf-8")

    s["pending_action"] = "add a rollback plan"
    pb.seed(_run(phase="t06-junior_ic"), site)

    assert revised.read_text(encoding="utf-8") == "# Proposal\n\nShip the thing, but smaller.\n"
    assert artifact.read_text(encoding="utf-8") == "# Proposal\n\nShip the thing.\n"


def test_a_junior_seed_survives_an_artifact_deleted_mid_run(artifact):
    """A vanished original degrades the turn; it must not abandon the run.

    `seed` is called unguarded inside the master loop
    (engine/dispatch.py:287), so an OSError out of ensure_revised would leave
    the run `running` with no terminal state and no event. The turn is
    dispatched with an empty pre-edit digest instead, which is what reduce's
    §7 re-check reads as an edit that did not land.
    """
    from playbooks.committee import cast, thread

    pb = _committee()
    site = _NamedSite("local")
    run = _run(phase="open")
    pb.seed(run, site)

    artifact.unlink()
    s = pb._state(run)
    s["current_role"] = cast.JUNIOR
    s["pending_action"] = "add a rollback plan"

    tickets = pb.seed(_run(phase="t04-junior_ic"), site)

    assert len(tickets) == 1
    assert tickets[0].payload["kind"] == "edit"
    assert s["pre_edit_digest"] == ""
    assert not thread.revised_path(run.id, s["artifact"]).exists()


def test_decision_ticket_is_built_for_the_chair(artifact):
    """`decision` seeds one chair ticket with the chair goal."""
    from playbooks.committee import cast, thread

    pb = _committee()
    site = _NamedSite("local")
    run = _run(phase="open")
    pb.seed(run, site)
    s = pb._state(run)

    tickets = pb.seed(_run(phase="decision"), site)
    assert len(tickets) == 1
    t = tickets[0]
    assert t.id == f"{run.id}/decision"
    assert t.phase == "decision"
    assert t.payload["role"] == cast.CHAIR
    assert cast.CHAIR == "chair"
    assert t.payload["kind"] == "decision"
    assert t.payload["action"] is None
    assert t.payload["goal"] == cast.goal(
        cast.CHAIR,
        charge=s["charge"],
        artifact=s["artifact"],
        thread=str(thread.path(run.id)),
        revised=s["revised"],
        action=None,
    )


def test_the_site_guard_runs_before_the_config_check(artifact, monkeypatch):
    """A bad site is reported as a bad site, not as a missing artifact."""
    monkeypatch.delenv("HERMES_COMMITTEE_ARTIFACT", raising=False)
    pb = _committee()
    with pytest.raises(ValueError) as excinfo:
        pb.seed(_run(phase="open"), _NamedSite("devserver"))
    message = str(excinfo.value)
    assert "'devserver'" in message
    assert "HERMES_COMMITTEE_ARTIFACT" not in message


# --- reduce: the turn path and the gates (spec 5.2, 5.4) ------------------


def _finding(run, ticket_id: str, answer: str) -> Finding:
    """Helper: construct a Finding the way the queue writes one."""
    return Finding(run_id=run.id, ticket_id=ticket_id, kind="result", json={"answer": answer})


def _turn_answer(prose: str, **keys) -> str:
    """Prose plus one hermes-turn block carrying `keys` as `key: value` lines."""
    lines = "\n".join(f"{key}: {value}" for key, value in keys.items())
    return f"{prose}\n\n```hermes-turn\n{lines}\n```\n"


def test_reduce_open_writes_nothing_and_returns_no_reductions():
    """The zero-ticket bootstrap has nothing to fold."""
    from playbooks.committee import thread

    pb = _committee()
    run = _run(phase="open")

    assert pb.reduce(run, "open", [], _NamedSite("local")) == []
    assert not thread.path(run.id).exists()


def test_reduce_turn_appends_the_stripped_prose_and_queues_a_floor_request():
    """A reviewer's prose lands under its own heading; its request_floor queues it."""
    from playbooks.committee import cast, thread

    pb = _committee()
    run = _run(phase="t03-staff_ic")
    s = pb._state(run)
    s.update(current_role="staff_ic", current_turn=3, opening=[])

    answer = _turn_answer(
        "The rollout plan is thin on the middle six weeks.", request_floor="yes"
    )
    reductions = pb.reduce(
        run, "t03-staff_ic", [_finding(run, f"{run.id}/t03-staff_ic", answer)],
        _NamedSite("local"),
    )

    persona = cast.persona("staff_ic")
    text = thread.path(run.id).read_text()
    assert f"## turn 03 — {persona['name']}, {persona['title']} (staff_ic)" in text
    assert "The rollout plan is thin on the middle six weeks." in text
    assert "hermes-turn" not in text
    assert s["queue"] == ["staff_ic"]

    assert len(reductions) == 1
    assert reductions[0].kind == "turn"
    assert reductions[0].json["role"] == "staff_ic"
    assert reductions[0].json["turn"] == 3
    assert reductions[0].json["delivered"] is True
    assert reductions[0].json["request_floor"] is True
    assert reductions[0].json["verified"] is None
    assert reductions[0].json["error"] is None


def test_reduce_drops_a_floor_request_from_the_owner():
    """The owner already speaks after every reviewer; it never queues itself."""
    pb = _committee()
    run = _run(phase="t04-owner")
    s = pb._state(run)
    s.update(current_role="owner", current_turn=4, opening=[])

    answer = _turn_answer("Fair; I will take that away.", request_floor="yes")
    reductions = pb.reduce(
        run, "t04-owner", [_finding(run, f"{run.id}/t04-owner", answer)],
        _NamedSite("local"),
    )

    assert s["queue"] == []
    assert reductions[0].json["request_floor"] is True  # said, not honoured


def test_reduce_drops_a_floor_request_from_the_junior_ic():
    """The junior IC executes; it has no standing to take the floor (spec 4)."""
    pb = _committee()
    run = _run(phase="t05-junior_ic")
    s = pb._state(run)
    s.update(current_role="junior_ic", current_turn=5, opening=[])

    answer = _turn_answer("Edited the rollout section.", request_floor="yes")
    pb.reduce(
        run, "t05-junior_ic", [_finding(run, f"{run.id}/t05-junior_ic", answer)],
        _NamedSite("local"),
    )

    assert s["queue"] == []


def test_reduce_drops_a_floor_request_from_a_role_still_in_the_opening_round():
    """Without the opening half, a role could sit in both lists and speak twice."""
    pb = _committee()
    run = _run(phase="t02-tpm")
    s = pb._state(run)
    s.update(current_role="tpm", current_turn=2)  # `opening` left as seeded

    assert "tpm" in s["opening"]
    answer = _turn_answer("I want the dependency list.", request_floor="yes")
    pb.reduce(
        run, "t02-tpm", [_finding(run, f"{run.id}/t02-tpm", answer)], _NamedSite("local")
    )

    assert s["queue"] == []
    assert "tpm" in s["opening"]


def test_reduce_does_not_double_queue_a_role_already_waiting():
    """A second request from a role already in the queue adds nothing."""
    pb = _committee()
    run = _run(phase="t06-manager")
    s = pb._state(run)
    s.update(current_role="manager", current_turn=6, opening=[])

    answer = _turn_answer("Still worried about the numbers.", request_floor="yes")
    pb.reduce(
        run, "t06-manager", [_finding(run, f"{run.id}/t06-manager", answer)],
        _NamedSite("local"),
    )
    assert s["queue"] == ["manager"]

    s["current_turn"] = 8
    pb.reduce(
        run, "t08-manager", [_finding(run, f"{run.id}/t08-manager", answer)],
        _NamedSite("local"),
    )
    assert s["queue"] == ["manager"]


def test_reduce_honours_close_from_the_owner():
    """`close` from the owner routes the next hop to the decision."""
    pb = _committee()
    run = _run(phase="t10-owner")
    s = pb._state(run)
    s.update(current_role="owner", current_turn=10, opening=[])

    answer = _turn_answer("We have enough; taking it to a decision.", close="yes")
    reductions = pb.reduce(
        run, "t10-owner", [_finding(run, f"{run.id}/t10-owner", answer)],
        _NamedSite("local"),
    )

    assert s["closed"] is True
    assert s["delegation"] is None
    assert reductions[0].json["close"] is True


def test_reduce_honours_a_delegation_with_an_action_from_the_owner():
    """`delegate: yes` plus a non-empty action arms one junior-IC turn."""
    pb = _committee()
    run = _run(phase="t11-owner")
    s = pb._state(run)
    s.update(current_role="owner", current_turn=11, opening=[])

    answer = _turn_answer(
        "Agreed, we will fix that.",
        delegate="yes",
        action="add a rollback paragraph to the rollout section",
    )
    reductions = pb.reduce(
        run, "t11-owner", [_finding(run, f"{run.id}/t11-owner", answer)],
        _NamedSite("local"),
    )

    assert s["delegation"] == "add a rollback paragraph to the rollout section"
    assert reductions[0].json["delegate"] is True
    assert reductions[0].json["action"] == "add a rollback paragraph to the rollout section"


def test_reduce_drops_a_delegation_with_an_empty_action():
    """An edit nobody described is not an edit; the whole delegation is dropped."""
    pb = _committee()
    run = _run(phase="t12-owner")
    s = pb._state(run)
    s.update(current_role="owner", current_turn=12, opening=[])

    answer = _turn_answer("Someone should fix that.", delegate="yes", action="")
    reductions = pb.reduce(
        run, "t12-owner", [_finding(run, f"{run.id}/t12-owner", answer)],
        _NamedSite("local"),
    )

    assert s["delegation"] is None
    assert reductions[0].json["delegate"] is True


def test_reduce_ignores_delegate_and_close_from_a_reviewer():
    """Only the accountable owner may delegate or close (spec 5.4)."""
    pb = _committee()
    run = _run(phase="t07-tl")
    s = pb._state(run)
    s.update(current_role="tl", current_turn=7, opening=[])

    answer = _turn_answer(
        "This is done; have someone cut the appendix.",
        delegate="yes",
        action="cut the appendix",
        close="yes",
    )
    reductions = pb.reduce(
        run, "t07-tl", [_finding(run, f"{run.id}/t07-tl", answer)], _NamedSite("local")
    )

    assert s["closed"] is False
    assert s["delegation"] is None
    assert reductions[0].json["delegate"] is True  # recorded as said
    assert reductions[0].json["close"] is True


def test_reduce_writes_the_no_turn_stub_when_no_finding_arrived():
    """A driver_failed worker writes no finding; the transcript stays contiguous."""
    from playbooks.committee import cast, thread

    pb = _committee()
    run = _run(phase="t09-pm")
    s = pb._state(run)
    s.update(current_role="pm", current_turn=9, opening=[])

    reductions = pb.reduce(run, "t09-pm", [], _NamedSite("local"))

    persona = cast.persona("pm")
    text = thread.path(run.id).read_text()
    assert f"## turn 09 — {persona['name']}, {persona['title']} (pm)" in text
    assert thread.NO_TURN in text

    assert len(reductions) == 1
    assert reductions[0].json["delivered"] is False
    assert reductions[0].json["request_floor"] is False
    assert reductions[0].json["action"] is None
    assert reductions[0].json["error"] is None
    assert s["queue"] == []


def test_reduce_records_a_block_only_answer_as_delivered_not_as_a_failure():
    """A turn that was all signal and no prose still happened (spec 5.2).

    The NO_TURN stub belongs to "no finding", not to "no prose": an owner whose
    whole answer is the block has closed the meeting, and writing "the worker
    failed" into the permanent transcript would be a lie.
    """
    from playbooks.committee import thread
    from playbooks.committee.playbook import _SIGNALS_ONLY

    pb = _committee()
    run = _run(phase="t10-owner")
    s = pb._state(run)
    s.update(current_role="owner", current_turn=10, opening=[])

    answer = _turn_answer("", close="yes")
    reductions = pb.reduce(
        run, "t10-owner", [_finding(run, f"{run.id}/t10-owner", answer)],
        _NamedSite("local"),
    )

    assert s["closed"] is True
    assert reductions[0].json["delivered"] is True
    assert reductions[0].json["close"] is True

    text = thread.path(run.id).read_text()
    assert _SIGNALS_ONLY in text
    assert thread.NO_TURN not in text


def test_reduce_grants_no_owner_authority_to_an_unattributable_turn():
    """A turn with no speaker fails closed: no gates, and the reason recorded."""
    pb = _committee()
    run = _run(phase="t04-owner")
    s = pb._state(run)
    s.update(current_role=None, current_turn=4, opening=[])

    answer = _turn_answer("Closing this.", close="yes", delegate="yes", action="x")
    reductions = pb.reduce(
        run, "t04-owner", [_finding(run, f"{run.id}/t04-owner", answer)],
        _NamedSite("local"),
    )

    assert s["closed"] is False and s["delegation"] is None
    assert "speaker" in reductions[0].json["error"]


def test_reduce_never_raises_when_the_thread_cannot_be_written():
    """An exception out of reduce kills the master loop; it is recorded instead."""
    from playbooks.committee import thread

    pb = _committee()
    run = _run(phase="t02-manager")
    s = pb._state(run)
    s.update(current_role="manager", current_turn=2, opening=[])

    # A directory where the transcript file belongs: open(path, "a") raises
    # IsADirectoryError. chmod would not do -- state_dir chmods the run
    # directory back to 0700 on every call, and tests may run as root.
    thread.path(run.id).mkdir(parents=True, exist_ok=True)

    answer = _turn_answer("Numbers, please.", request_floor="yes")
    reductions = pb.reduce(
        run, "t02-manager", [_finding(run, f"{run.id}/t02-manager", answer)],
        _NamedSite("local"),
    )

    assert len(reductions) == 1
    assert "thread" in reductions[0].json["error"]
    # the gates still ran: a failed write must not swallow the floor request
    assert s["queue"] == ["manager"]


# --- reduce: the independent re-check of a junior-IC edit (spec 7) --------


def test_reduce_records_a_junior_ic_edit_that_changed_the_file_as_verified(tmp_path):
    """The master re-hashes the revised copy: changed means the edit landed."""
    from playbooks.committee import thread

    pb = _committee()
    run = _run(phase="t05-junior_ic")
    artifact = tmp_path / "proposal.md"
    artifact.write_text("the original proposal\n")
    revised = thread.ensure_revised(run.id, str(artifact))
    pre = thread.digest(revised)  # what seed() snapshots just before the worker runs
    revised.write_text("the original proposal\nand a rollback paragraph\n")

    s = pb._state(run)
    s.update(
        current_role="junior_ic",
        current_turn=5,
        opening=[],
        artifact=str(artifact),
        revised=str(revised),
        pending_action="add a rollback paragraph",
        pre_edit_digest=pre,
    )

    reductions = pb.reduce(
        run,
        "t05-junior_ic",
        [_finding(run, f"{run.id}/t05-junior_ic", "Added a rollback paragraph.")],
        _NamedSite("local"),
    )

    assert reductions[0].json["verified"] is True
    assert reductions[0].json["error"] is None
    assert s["rechecks"] == [
        {"turn": 5, "action": "add a rollback paragraph", "verified": True}
    ]
    assert artifact.read_text() == "the original proposal\n"  # original untouched


def test_reduce_records_a_junior_ic_edit_that_changed_nothing_as_unverified(tmp_path):
    """An identical revised copy means the worker claimed an edit it did not make."""
    from playbooks.committee import thread

    pb = _committee()
    run = _run(phase="t05-junior_ic")
    artifact = tmp_path / "proposal.md"
    artifact.write_text("the original proposal\n")
    revised = thread.ensure_revised(run.id, str(artifact))  # byte-copy, never edited

    s = pb._state(run)
    s.update(
        current_role="junior_ic",
        current_turn=5,
        opening=[],
        artifact=str(artifact),
        revised=str(revised),
        pending_action="add a rollback paragraph",
        pre_edit_digest=thread.digest(revised),
    )

    reductions = pb.reduce(
        run,
        "t05-junior_ic",
        [_finding(run, f"{run.id}/t05-junior_ic", "Added a rollback paragraph.")],
        _NamedSite("local"),
    )

    assert reductions[0].json["verified"] is False
    assert s["rechecks"] == [
        {"turn": 5, "action": "add a rollback paragraph", "verified": False}
    ]


def test_reduce_junior_edit_measures_this_edit_not_drift_from_the_original(tmp_path):
    """A SECOND delegated edit that changed nothing must still fail its re-check.

    `ensure_revised` copies once and never again, so after the first edit lands
    the revised copy differs from the original forever. Comparing against the
    original would report every later edit as verified -- including one that did
    nothing, which is exactly the silent no-op criterion 7 exists to catch. The
    comparison is against the digest seed() snapshotted before this worker ran.
    """
    from playbooks.committee import thread

    pb = _committee()
    run = _run(phase="t09-junior_ic")
    artifact = tmp_path / "proposal.md"
    artifact.write_text("the original proposal\n")
    revised = thread.ensure_revised(run.id, str(artifact))
    # Edit one already landed; the copy is permanently unlike the original.
    revised.write_text("the original proposal\nand a rollback paragraph\n")

    s = pb._state(run)
    s.update(
        current_role="junior_ic",
        current_turn=9,
        opening=[],
        artifact=str(artifact),
        revised=str(revised),
        pending_action="also name the on-call owner",
        # what seed() saw just before this second worker ran -- unchanged since
        pre_edit_digest=thread.digest(revised),
    )

    reductions = pb.reduce(
        run,
        "t09-junior_ic",
        [_finding(run, f"{run.id}/t09-junior_ic", "Named the on-call owner.")],
        _NamedSite("local"),
    )

    assert reductions[0].json["verified"] is False, \
        "a second no-op edit was waved through by comparing against the original"
    assert s["rechecks"] == [
        {"turn": 9, "action": "also name the on-call owner", "verified": False}
    ]


def test_reduce_records_a_missing_revised_file_as_unverified(tmp_path):
    """No revised copy at all is the loudest failure of the re-check."""
    pb = _committee()
    run = _run(phase="t05-junior_ic")
    artifact = tmp_path / "proposal.md"
    artifact.write_text("the original proposal\n")

    s = pb._state(run)
    s.update(
        current_role="junior_ic",
        current_turn=5,
        opening=[],
        artifact=str(artifact),
        revised=str(tmp_path / "nowhere" / "proposal.md"),
        pending_action="add a rollback paragraph",
    )

    reductions = pb.reduce(
        run,
        "t05-junior_ic",
        [_finding(run, f"{run.id}/t05-junior_ic", "Added a rollback paragraph.")],
        _NamedSite("local"),
    )

    assert reductions[0].json["verified"] is False
    assert reductions[0].json["error"] is None  # an absent file is an answer, not a crash


def test_reduce_treats_a_missing_pre_edit_snapshot_as_a_failed_recheck(tmp_path):
    """An empty `pre_edit_digest` is a FAILED snapshot, and can only be a failure.

    `seed` leaves it empty in exactly one case: the original vanished before any
    copy could be made, so nothing was hashed. If the worker then CREATES the
    revised file out of nothing, its digest is not "" -- and comparing the two
    reports the fabrication as a verified edit, which inverts the one
    master-side no-trust check there is. "" is unreachable on the healthy path:
    the digest of a zero-byte file is e3b0c442..., never "".
    """
    from playbooks.committee import thread

    pb = _committee()
    run = _run(phase="t05-junior_ic")
    revised = thread.revised_path(run.id, "proposal.md")
    revised.write_text("a revised copy the worker invented from nothing\n")

    s = pb._state(run)
    s.update(
        current_role="junior_ic",
        current_turn=5,
        opening=[],
        artifact=str(tmp_path / "proposal.md"),  # gone before seed could copy it
        revised=str(revised),
        pending_action="add a rollback paragraph",
        pre_edit_digest="",  # what seed's OSError path leaves behind
    )

    reductions = pb.reduce(
        run,
        "t05-junior_ic",
        [_finding(run, f"{run.id}/t05-junior_ic", "Added a rollback paragraph.")],
        _NamedSite("local"),
    )

    assert thread.digest(revised) != ""  # the invented file hashes perfectly well
    assert reductions[0].json["verified"] is False, \
        "an invented revised copy was reported as a verified edit"
    assert reductions[0].json["error"] is None
    assert s["rechecks"] == [
        {"turn": 5, "action": "add a rollback paragraph", "verified": False}
    ]


# --- reduce: the decision (spec 5.2, 5.3, criteria 7, 8, 9) ---------------


def test_reduce_decision_folds_the_verdict_and_calls_it_a_simulation():
    """Criterion 9: the decision must say plainly that it is not an approval."""
    from playbooks.committee import cast, thread

    pb = _committee()
    run = _run(phase="decision")
    s = pb._state(run)
    s["current_role"] = "chair"

    answer = "Approve with changes: land the rollback paragraph first."
    reductions = pb.reduce(
        run, "decision", [_finding(run, f"{run.id}/decision", answer)], _NamedSite("local")
    )

    red = reductions[0]
    assert red.kind == "decision"
    assert red.json["delivered"] is True
    assert "Approve with changes" in red.json["verdict"]
    assert "simulation" in red.json["verdict"]
    assert "not an approval" in red.json["verdict"]
    assert red.json["rechecks"] == []
    assert red.json["dropped_delegation"] is None
    assert red.json["error"] is None

    chair = cast.persona(cast.CHAIR_ROLE)
    text = thread.path(run.id).read_text()
    assert f"## decision — {chair['name']}, {chair['title']}" in text
    assert "Approve with changes" in text
    assert "simulation" in text

    # `is_done` reads the chair's prose, never the assembled text.
    assert s["verdict"] == answer
    assert pb.is_done(run) is True


def test_reduce_decision_names_a_failed_recheck():
    """Criterion 7: an edit that silently did not apply is named, never buried."""
    from playbooks.committee import thread

    pb = _committee()
    run = _run(phase="decision")
    s = pb._state(run)
    s["current_role"] = "chair"
    s["rechecks"] = [
        {"turn": 5, "action": "add a rollback paragraph", "verified": False},
        {"turn": 9, "action": "cut the appendix", "verified": True},
    ]

    reductions = pb.reduce(
        run, "decision", [_finding(run, f"{run.id}/decision", "Approve.")],
        _NamedSite("local"),
    )

    red = reductions[0]
    assert "DID NOT APPLY" in red.json["verdict"]
    assert "add a rollback paragraph" in red.json["verdict"]
    assert "cut the appendix" in red.json["verdict"]
    assert red.json["rechecks"] == [
        {"turn": 5, "action": "add a rollback paragraph", "verified": False},
        {"turn": 9, "action": "cut the appendix", "verified": True},
    ]

    text = thread.path(run.id).read_text()
    assert "turn 05" in text
    assert "DID NOT APPLY" in text


def test_reduce_decision_names_a_dropped_delegation():
    """The cap can drop an edit the owner asked for; the decision says so."""
    pb = _committee()
    run = _run(phase="decision")
    s = pb._state(run)
    s["current_role"] = "chair"
    s["dropped_delegation"] = "rewrite the risks section"

    reductions = pb.reduce(
        run, "decision", [_finding(run, f"{run.id}/decision", "Do not approve.")],
        _NamedSite("local"),
    )

    red = reductions[0]
    assert red.json["dropped_delegation"] == "rewrite the risks section"
    assert "dropped_delegation" in red.json["verdict"]
    assert "rewrite the risks section" in red.json["verdict"]


def test_reduce_decision_with_no_finding_leaves_the_verdict_empty():
    """A failed chair turn ends the run failed, deliberately (spec 5.3)."""
    from playbooks.committee import thread

    pb = _committee()
    run = _run(phase="decision")
    s = pb._state(run)
    s["current_role"] = "chair"

    reductions = pb.reduce(run, "decision", [], _NamedSite("local"))

    red = reductions[0]
    assert red.kind == "decision"
    assert red.json["verdict"] == ""
    assert red.json["delivered"] is False
    assert s["verdict"] == ""
    assert pb.is_done(run) is False

    # the transcript still stands, and still names what happened
    text = thread.path(run.id).read_text()
    assert "no decision delivered" in text
    assert "simulation" in text


def test_reduce_decision_never_raises_when_the_thread_cannot_be_written():
    """The decision fold is wrapped exactly like the turn fold."""
    from playbooks.committee import thread

    pb = _committee()
    run = _run(phase="decision")
    s = pb._state(run)
    s["current_role"] = "chair"
    thread.path(run.id).mkdir(parents=True, exist_ok=True)

    reductions = pb.reduce(
        run, "decision", [_finding(run, f"{run.id}/decision", "Approve.")],
        _NamedSite("local"),
    )

    assert len(reductions) == 1
    assert "thread" in reductions[0].json["error"]
    assert s["verdict"] == "Approve."  # the run still finishes


def test_no_reduction_carries_needs_human_ticket_ids():
    """Criterion 8: that key routes the ticket to needs_human and wedges the run."""
    pb = _committee()
    run = _run(phase="t03-tl")
    s = pb._state(run)
    s.update(current_role="tl", current_turn=3, opening=[])

    produced = []
    produced += pb.reduce(run, "open", [], _NamedSite("local"))
    answer = _turn_answer("Ship it.", request_floor="no")
    produced += pb.reduce(
        run, "t03-tl", [_finding(run, f"{run.id}/t03-tl", answer)], _NamedSite("local")
    )
    s["current_role"] = "chair"
    produced += pb.reduce(
        run, "decision", [_finding(run, f"{run.id}/decision", "Approve.")],
        _NamedSite("local"),
    )

    assert len(produced) == 2
    for reduction in produced:
        assert "needs_human_ticket_ids" not in reduction.json


# --- registration and wiring ---------------------------------------------


def test_registration_importing_the_package_registers_committee():
    """`import playbooks.committee` is the whole registration step.

    The package __init__ re-exports the playbook module, whose bottom-of-file
    register() call is the import side-effect. The registry holds one instance
    (engine/playbook.py:52), which is what spec 5.2 relies on for per-run state.
    """
    import playbooks.committee  # noqa: F401

    from engine import playbook as _playbook
    from playbooks.committee.playbook import CommitteePlaybook

    pb = _playbook.load("committee")
    assert isinstance(pb, CommitteePlaybook)
    assert pb.name == "committee"
    assert _playbook.load("committee") is pb


def test_registration_instance_satisfies_the_playbook_protocol():
    """All eight methods plus name/phases are present on the registered object."""
    import playbooks.committee  # noqa: F401

    from engine import playbook as _playbook
    from engine.playbook import Playbook

    pb = _playbook.load("committee")
    assert isinstance(pb, Playbook)
    for method in (
        "seed",
        "payload_schema",
        "result_schema",
        "driver",
        "reduce",
        "verify",
        "next_phase",
        "is_done",
    ):
        assert callable(getattr(pb, method)), method


def test_registration_phases_are_open_then_decision():
    """phases[0] is the phase the CLI seeds (engine/cli.py:385)."""
    import playbooks.committee  # noqa: F401

    from engine import playbook as _playbook

    pb = _playbook.load("committee")
    assert pb.phases == ["open", "decision"]
    assert pb.phases[0] == "open"


def test_registration_resolves_through_playbook_modules_env(tmp_path):
    """HERMES_PLAYBOOK_MODULES=playbooks.committee resolves the playbook with no engine edit.

    _load_playbook_site_agent calls _import_registration_modules() (engine/cli.py:226)
    before playbook.load(playbook_name) (engine/cli.py:228), and that importer walks
    config.playbook_modules() (engine/cli.py:173-179). So the env var is the whole
    wiring -- acceptance criteria 11 and 13 together.

    A subprocess, because sys.modules must start clean: in-process, another test in
    this file has already imported playbooks.committee.playbook, which would make the
    package __init__ re-export look unnecessary.
    """
    import os
    import subprocess
    import sys
    from pathlib import Path

    workspace = Path(__file__).parent.parent.parent

    script = f"""
import sys

sys.path.insert(0, r"{workspace}")

import argparse

from engine.cli import _load_playbook_site_agent
from engine.playbook import Playbook

assert "playbooks.committee" not in sys.modules, "committee was pre-imported"

args = argparse.Namespace(playbook="committee", site="local", agent="claude")
pb, st, ag = _load_playbook_site_agent(args)

assert pb.name == "committee", pb.name
assert type(pb).__name__ == "CommitteePlaybook", type(pb).__name__
assert pb.phases == ["open", "decision"], pb.phases
assert isinstance(pb, Playbook)
assert st.name == "local", st.name
assert ag.name == "claude", ag.name

print("OK")
"""

    home = tmp_path / "hermes-home"
    home.mkdir()
    # Drop every inherited HERMES_* var: the real HERMES_HOME/local is a
    # per-developer auto-discovery directory (engine/cli.py:139-171) and must
    # not be imported into this assertion.
    env = {k: v for k, v in os.environ.items() if not k.startswith("HERMES_")}
    env.update(
        {
            "PYTHONPATH": str(workspace),
            "HERMES_HOME": str(home),
            "HERMES_PLAYBOOK_MODULES": "playbooks.committee",
        }
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=workspace,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, f"{result.stderr}\n{result.stdout}"
    assert result.stdout.strip() == "OK"


def test_wiring_adds_nothing_to_engine_server_or_web():
    """Acceptance criterion 13: engine/, server/ and web/ are unmodified.

    Dexter and research are wired by a hardcoded import in _load_playbook_site_agent
    (engine/cli.py:211-212). Committee is deliberately NOT, because that is an engine
    edit. This fails the moment someone "fixes" the wiring that way.
    """
    from pathlib import Path

    workspace = Path(__file__).parent.parent.parent

    hits = []
    for tree in ("engine", "server", "web/src"):
        for path in sorted((workspace / tree).rglob("*")):
            if not path.is_file() or path.suffix not in (".py", ".sql", ".ts", ".tsx"):
                continue
            text = path.read_text(encoding="utf-8", errors="replace").lower()
            if "committee" in text:
                hits.append(str(path.relative_to(workspace)))

    assert hits == [], f"committee is named inside engine/server/web: {hits}"
