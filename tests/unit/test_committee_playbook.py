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

import re

import pytest

from playbooks.committee import cast, turnblock
from playbooks.committee import turnblock as T


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
