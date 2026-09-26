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
from playbooks.committee.playbook import DECISION_PHASES, _apply_block


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


def test_every_key_in_the_declared_vocabulary_is_one_the_parser_reads():
    """KEYS is "the closed vocabulary" -- so `_one` must parse against it.

    `_FLAGS` used to be a second hand-written list, which made KEYS dead: a
    sixth signal declared there would be a key the parser silently drops, with
    a green suite either way. The two free-text keys are named here rather than
    read out of `_TEXT`: `_FLAGS` is derived from `_TEXT`, so comparing the two
    would be true by construction whatever KEYS says.
    """
    assert set(T.KEYS) == set(T._FLAGS) | {T.ACTION, T.STANCE}
    for flag in T._FLAGS:
        assert T.parse(_fenced(f"{flag}: yes")) == {flag: True}, flag
    assert T.parse(_fenced(f"{T.ACTION}: cut the appendix")) == {T.ACTION: "cut the appendix"}
    assert T.parse(_fenced(f"{T.STANCE}: unconvinced")) == {T.STANCE: "unconvinced"}


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
    # A distinguishable head: with a payload of one repeated character `[:200]`
    # and `[-200:]` are the same string, and clipping from the wrong end
    # survives the whole suite.
    action = T.parse(_fenced("action: keep-this " + "x" * 500))["action"]

    # Pinned literally: cast.py reads ACTION_MAX into the 3600-character goal
    # budget, so a silent change here silently changes what a worker is handed.
    assert T.ACTION_MAX == 200
    assert len(action) <= T.ACTION_MAX
    assert action.endswith("…")
    assert action.startswith("keep-this ")


def test_a_junk_flag_value_is_dropped_rather_than_read_as_no():
    """`request_floor: maybe` is not a no. Absent stays absent."""
    assert T.parse(_fenced("request_floor: maybe")) == {}


def test_a_colon_inside_an_action_survives():
    answer = _fenced("delegate: yes\naction: rename section 2: Findings")

    assert T.parse(answer) == {
        "delegate": True,
        "action": "rename section 2: Findings",
    }


def test_a_stance_is_free_text_the_way_an_action_is():
    """Where a speaker stands is one line of English, not a yes/no flag. Read
    as a flag it would be dropped as junk, which is the whole signal gone."""
    answer = _fenced(
        "request_floor: yes\nstance: fund it only if the rollback owner is named"
    )

    assert T.parse(answer) == {
        "request_floor": True,
        "stance": "fund it only if the rollback owner is named",
    }


def test_a_stance_nobody_stated_stays_absent():
    """The rule this module exists for, applied to the fifth key: a persona
    that stated no stance has none, and must never be rendered as neutral."""
    assert T.parse(_fenced("request_floor: no")) == {"request_floor": False}
    assert "stance" not in T.parse(_fenced("close: yes"))


def test_a_stance_longer_than_the_cap_is_clipped():
    # A distinguishable head, for the reason the action test gives.
    stance = T.parse(_fenced("stance: keep-this " + "y" * 500))["stance"]

    # Pinned literally: a stance rides in the same 3600-character goal budget
    # an action does, so a silent change here silently changes what a worker
    # is handed.
    assert T.STANCE_MAX == 200
    assert len(stance) <= T.STANCE_MAX
    assert stance.endswith("…")
    assert stance.startswith("keep-this ")


def test_a_long_action_is_cut_at_a_word_near_the_cap():
    """Six of eight run-9 actions stopped mid-word at exactly 200 characters."""
    # Spaces sit at 4 + 8k, so index 199 falls inside a word: a word cut
    # (at the space at 196) and the mid-token fallback give different strings.
    action = T.parse(_fenced("action: keep " + "wording " * 40))["action"]

    assert len(action) < T.ACTION_MAX
    assert action.endswith("…")
    assert action[:-1].split()[-1] == "wording"  # no half word before the ellipsis
    assert len(action) > T.ACTION_MAX // 2
    # a space at index 200 is past the cap, and exactly 200 characters is not cut
    assert len(T.parse(_fenced("action: " + "a" * 150 + " " + "b" * 49 + " tail"))["action"]) <= T.ACTION_MAX
    assert T.parse(_fenced("action: " + "a" * 200))["action"] == "a" * 200


def test_the_word_cut_keeps_at_least_half_the_cap():
    # A space at exactly half the cap is a word cut; one before it would keep
    # too little, so the cut falls mid-token at the cap instead.
    half = T.parse(_fenced("stance: " + "a" * 100 + " " + "b" * 150))["stance"]
    assert half == "a" * 100 + "…"
    short = T.parse(_fenced("stance: " + "a" * 99 + " " + "b" * 150))["stance"]
    assert short == ("a" * 99 + " " + "b" * 150)[:T.STANCE_MAX - 1] + "…"


def test_lengths_reports_the_raw_unclipped_action_and_stance():
    answer = _fenced("action: " + "a" * 230 + "\nstance: holding")

    assert T.lengths(answer) == {"action_chars": 230, "stance_chars": 7}
    assert T.lengths(_fenced("request_floor: no")) == {}
    assert T.lengths(None) == {} and T.lengths("no block at all") == {}
    # the last block wins, as in parse
    assert T.lengths(_fenced("action: first") + _fenced("action: " + "b" * 12)) == {
        "action_chars": 12}


def test_the_instructions_ask_for_a_sentence_action_and_a_short_stance():
    owner = T.instruction(owner=True)

    assert "`action: <one sentence, 200 characters or fewer>`" in owner
    for text in (owner, T.instruction()):
        assert "`stance: <20 words or fewer>`" in text
        assert " -- " not in text and "—" not in text and "–" not in text


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

def test_the_reviewer_instruction_documents_the_floor_request_and_the_stance():
    """delegate and close are the owner's to use. Documenting them to a
    reviewer invites a block reduce is obliged to throw away. A stance is not
    owner-only: every speaker issued a block is asked for one."""
    text = T.instruction()

    assert T.FENCE_TAG in text
    assert "request_floor" in text
    assert T.STANCE in text
    for key in ("delegate", "action", "close"):
        assert key not in text


def test_the_owner_instruction_documents_all_five_keys():
    text = T.instruction(owner=True)

    # The closed vocabulary, pinned literally: `for key in T.KEYS` passes just as
    # happily against a one-element KEYS, which is the whole test gone.
    assert T.KEYS == ("request_floor", "delegate", "action", "close", "stance")
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
    # Label AND value, per field: bare containment passes a brief that swapped
    # two labels over, which hands the worker somebody else's frame.
    for field in ("altitude", "goal", "ambition", "stake", "lens", "style"):
        assert f"{field}: {p[field]}" in text, field


def test_title_names_the_turn_the_speaker_and_the_kind():
    # Seven owner rows that all read "Maya Okonkwo (owner) takes the floor" are
    # one row seven times on a board. The turn number tells them apart.
    assert cast.title("tpm", "turn", turn=5) == "turn 5 — Sam Iyer (tpm) takes the floor"
    assert cast.title(cast.JUNIOR, "edit", turn=15, action="tighten the rollout section") == (
        "turn 15 — Alex Moreau (junior_ic) edits: tighten the rollout section"
    )
    # The decision is not a turn, so it does not claim a number.
    assert cast.title(cast.CHAIR, "decision", turn=20) == (
        "Dana Whitfield (chair) delivers the committee decision"
    )
    # An unknown kind fails loudly. A fallback to "turn" would title the
    # DECISION ticket "takes the floor".
    with pytest.raises(KeyError):
        cast.title("pm", "vote", turn=1)


def test_an_edit_title_clips_the_action_to_fit_a_card():
    # A delegated action may run to turnblock.ACTION_MAX; a card title may not.
    long = "rewrite " + "the rollout section " * 20
    t = cast.title(cast.JUNIOR, "edit", turn=9, action=long)
    assert t.startswith("turn 9 — Alex Moreau (junior_ic) edits: rewrite the rollout")
    assert t.endswith("…")
    assert len(t) <= 110


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
    "Done when: your answer is the committee's decision (approve, approve with "
    "changes, or do not approve) with the reasons, and says in one clause that "
    "it is a simulation, not an approval."
)
_GUARDRAIL = (
    "This review lands nothing, submits nothing and touches no repository. "
    "Read the artifact and the thread, and write no file at all."
)


def _labelled(goal: str, *lines: str) -> None:
    """Assert each `label: value` line appears whole.

    Bare containment of the values is not enough. `cast.goal` writes two paths
    on adjacent lines, and swapping the two values in that template leaves every
    containment assertion green -- while aiming the one write-permitted persona
    at the original artifact under `--permission-mode bypassPermissions`. The
    brief() test already applies this discipline; the goal tests did not.
    """
    for line in lines:
        assert line in goal, line


def test_reviewer_goal_carries_its_material_and_its_completion_condition():
    g = cast.goal(
        "tl",
        charge=_CHARGE,
        artifact=_ARTIFACT,
        thread=_THREAD,
        revised=_REVISED,
    )
    assert "You are Marcus Feld, Tech Lead." in g
    _labelled(
        g,
        f"The charge: {_CHARGE}",
        f"The artifact under review: {_ARTIFACT}",
        f"The thread: {_THREAD}",
    )
    assert _REVISED not in g  # a reviewer is never shown the editable copy
    assert _GUARDRAIL in g
    assert turnblock.instruction(owner=False).strip() in g
    # The speaker must not also append to thread.md: reduce is its sole writer.
    assert "Hermes appends it for you" in g
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
    # The close gate is enforced master-side; the goal must also SAY so, or the
    # model is fighting a rule it cannot see (spec 5.4).
    assert "cannot close the discussion until every member of the committee" in g
    assert turnblock.instruction(owner=True).strip() in g
    _labelled(
        g,
        f"The charge: {_CHARGE}",
        f"The artifact under review: {_ARTIFACT}",
        f"The thread: {_THREAD}",
    )
    assert "Hermes appends it for you" in g
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
    # Label AND value. This is the one persona permitted to write, and swapping
    # the two path values in the template leaves bare containment green while
    # aiming it at the original artifact under bypassPermissions.
    _labelled(
        g,
        f"The charge: {_CHARGE}",
        f"The original artifact, which stays untouched: {_ARTIFACT}",
        f"The revised copy you edit: {_REVISED}",
        f"The thread the request came out of: {_THREAD}",
        "The owner delegated this to you: add a rollback section naming who pages",
    )
    # The one file it may write, and the only file it may write.
    assert "the only file you may write" in g
    # And it already exists as a byte copy. Without that, a model can reasonably
    # rewrite it wholesale or reconstruct it from memory and lose content -- and
    # the §7 re-check would still pass, because it only asks whether the sha256
    # moved.
    assert "already a byte copy of the original" in g
    assert "change only what was delegated" in g
    # Its block keys are all ignored (§5.4), so it is not asked for a block.
    assert "hermes-turn" not in g
    assert g.endswith(
        f"Done when: {_REVISED} carries the delegated change and your answer is "
        "one sentence of 40 words or fewer saying what you changed."
    )

    # The action is clipped to ACTION_MAX, not to the charge's CHARGE_MAX: it
    # shares the goal budget with a charge that may already be 400 characters.
    long_action = cast.goal(
        cast.JUNIOR,
        charge=_CHARGE,
        artifact=_ARTIFACT,
        thread=_THREAD,
        revised=_REVISED,
        action="z" * 5000,
    )
    assert "z" * turnblock.ACTION_MAX not in long_action
    assert "z" * (turnblock.ACTION_MAX - 1) in long_action
    assert turnblock.ACTION_MAX < cast.CHARGE_MAX


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
    _labelled(
        g,
        f"The charge: {_CHARGE}",
        f"The artifact reviewed: {_ARTIFACT}",
        "The revised copy, which exists only if the committee delegated an "
        f"edit: {_REVISED}",
        f"The whole thread: {_THREAD}",
    )
    assert "simulation" in g
    assert _GUARDRAIL in g
    assert g.endswith(_DONE_DECISION)

    # The brief is the senior_director's, reviewer `style` and all: "asks two
    # questions and stops talking". A chair handed that plus _DONE_DECISION may
    # well return two questions, and `is_done` accepts any non-empty prose as
    # the verdict -- so the run would end `done` on a non-decision. The goal has
    # to overrule the inherited style in so many words.
    assert cast.CAST["senior_director"]["style"] in g
    assert "in the chair you rule rather than question" in g

    # Spec §9: material, not method. The chair is told WHAT to produce and is
    # handed the thread; HOW to weigh it belongs behind HERMES_COMMITTEE_DRIVER.
    # Neither carve-out (the junior IC's required output, `lens`) covers the chair.
    assert "Read the thread end to end and rule on the charge." in g
    for procedure in (
        "Weigh what was actually said",
        "name who is owed an answer",
        "what would change your mind",
    ):
        assert procedure not in g, procedure


@pytest.mark.parametrize("role", list(cast.CAST) + [cast.CHAIR])
def test_every_goal_says_an_unchanged_original_is_the_design_not_a_failure(role):
    """The one defect the whole test suite could not find, pinned for everyone.

    In the first live run the chair inspected the *repository* file, found it
    unchanged, wrote "six delegations, zero bytes ... I will not fund a
    deferral whose enforcement mechanism has a measured yield of zero", and
    ruled partly against the proposal on that reading. All six delegations had
    landed: the revised copy went 11,397 -> 19,100 bytes and every re-check
    reported APPLIED. The original was unchanged because that is the playbook's
    criterion 6 -- the guarantee working, not the edit mechanism failing.

    Parametrised over every speaker, not just the chair, because the chair did
    not originate the reading: the thread has reviewers minting it five turns
    earlier and the chair citing them. The one persona that got it right is the
    one whose goal already named the revised copy.
    """
    g = cast.goal(
        role,
        charge=_CHARGE,
        artifact=_ARTIFACT,
        thread=_THREAD,
        revised=_REVISED,
        action="add a rollback section naming who pages",
    )

    # Four separate claims, asserted separately: a mutant that drops any one of
    # them leaves a speaker able to reach the wrong reading again.
    assert "The original artifact is never modified" in g
    assert "that is by design" in g
    assert "not an edit that failed" in g
    assert "a recommendation plus that copy, not a landed change" in g

    # Present tense. "every delegated edit LANDED" is a claim about this run
    # that the goal cannot know -- `_reduce_decision` appends `DID NOT APPLY`
    # for a failed re-check, beneath the chair's own prose.
    assert "every delegated edit lands in" in g
    assert "landed in" not in g

    # It goes ABOVE the guardrail and the completion condition, which are the
    # contract with the worker and stay where they are.
    guardrail = (
        "The revised copy named above is the only file you may write"
        if role == cast.JUNIOR else _GUARDRAIL
    )
    assert guardrail in g
    assert g.index("The original artifact is never modified") < g.index(guardrail)


def test_the_chair_is_told_to_judge_the_edits_by_the_copy_it_is_handed():
    """Only the chair is handed the revised copy's path, and only the chair is
    asked to weigh what is in it. Pinned because it is the one sentence of the
    paragraph spec §8 does not ask for, so nothing else would notice it going."""
    g = cast.goal(
        cast.CHAIR,
        charge=_CHARGE,
        artifact=_ARTIFACT,
        thread=_THREAD,
        revised=_REVISED,
    )

    assert "Judge the delegated edits by the copy named above." in g
    # The sentence is worthless if the chair cannot find the copy it points at,
    # so the path stays on its own labelled line -- label and value together, so
    # that swapping the two paths in the template is caught.
    _labelled(
        g,
        "The revised copy, which exists only if the committee delegated an "
        f"edit: {_REVISED}",
    )
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
    """Every shape, take 1 and retake, at its maximum size stays under GOAL_MAX.

    Longest persona, an over-length charge, action and retake note, a 48-char
    image stem and deep paths. Also the cast's write invariant under
    bypassPermissions, in three classes: the junior's take 1 may write the
    revised copy and nothing else; the owner and the reviewers may write one
    image and nothing else; the chair and a junior retake may write nothing.
    """
    # Pinned literally: both are read as budgets elsewhere, and a mutant that
    # widens either passes every length assertion below.
    assert (cast.CHARGE_MAX, cast.GOAL_MAX) == (400, 3600)

    deep = "/home/anshulverma/.hermes/runs/committee-20260918-000000/" + "d" * 100
    artifact = f"{deep}/proposal-under-review.md"
    thread = f"{deep}/thread.md"
    revised = f"{deep}/revised/proposal-under-review.md"
    for role in list(cast.CAST) + [cast.CHAIR]:
        for retake in (None, "r" * 5000):
            g = cast.goal(
                role,
                charge="c" * 5000,
                artifact=artifact,
                thread=thread,
                revised=revised,
                action="a" * 5000,
                image="x" * 48,
                retake=retake,
            )
            shape = f"{role} retake={retake is not None}"
            assert len(g) < cast.GOAL_MAX, f"{shape}: {len(g)}"
            assert len(g) > 1500, f"{shape}: {len(g)}"
            # Case-folded: a second, contradictory sentence reads exactly the
            # same to a worker whatever its capitalisation.
            low = g.lower()
            if role == cast.JUNIOR and retake is None:
                assert "the only file you may write" in low and revised in g, shape
                assert "write no file at all" not in low and "one image" not in low, shape
            elif role in (cast.CHAIR, cast.JUNIOR):
                assert "write no file at all" in low, shape
                assert "the only file you may write" not in low, shape
            else:
                assert "the only file you may write is one image" in low, shape
                assert "images folder beside the thread" in low, shape
                assert "write no file at all" not in low, shape


def _goal(role, **over):
    kw = dict(charge=_CHARGE, artifact=_ARTIFACT, thread=_THREAD, revised=_REVISED,
              action="add a rollback section naming who pages")
    kw.update(over)
    return cast.goal(role, **kw)


@pytest.mark.parametrize("role", list(cast.CAST) + [cast.CHAIR])
def test_every_goal_points_at_the_ground_rules_with_its_cap_and_carries_no_dash(role):
    from playbooks.committee import voice

    pointer = (
        "Follow the ground rules at the top of the thread; they outrank your style. "
        f"Your cap: {voice.cap_text(role)}."
    )
    for g in (_goal(role), _goal(role, retake="Retake 2 of 3."), _goal(role, image="t02-x")):
        assert pointer in g, role
        assert "—" not in g and "–" not in g and " -- " not in g, role
    # built without `image`, no goal offers an image file
    assert "image, .svg" not in _goal(role)


def test_a_retake_note_is_its_own_paragraph_before_the_done_line_and_is_clipped():
    from playbooks.committee import voice

    note = "Retake 2 of 3. Your last take broke the ground rules: 212 words (cap 150). Say it again within them."
    assert f"\n\n{note}\n\n{_DONE_TURN}" in _goal("tl", retake=note)
    assert _goal("tl", retake=note).endswith(_DONE_TURN)
    assert f"\n\n{note}\n\n{_DONE_DECISION}" in _goal(cast.CHAIR, retake=note)
    long = _goal("tl", retake="r" * 5000)
    assert "r" * voice.RETAKE_NOTE_MAX not in long
    assert "r" * (voice.RETAKE_NOTE_MAX - 1) in long


def test_the_junior_retake_is_report_only():
    g = _goal(cast.JUNIOR, retake="Retake 2 of 3. Say it again within them.")

    _labelled(
        g,
        f"The revised copy you edit: {_REVISED}",
        "The owner delegated this to you: add a rollback section naming who pages",
    )
    # Take 1 may have written nothing (a report of why it could not), so the
    # retake is never told its edit landed, and may say it changed nothing.
    assert "Do not edit the revised copy again; whatever your first take changed stands." in g
    assert "already in the revised copy" not in g
    assert "Retake 2 of 3. Say it again within them." in g
    assert _GUARDRAIL in g and "the only file you may write" not in g.lower()
    assert g.endswith(
        "Done when: your answer is one sentence of 40 words or fewer saying what your "
        "first take changed, or that it changed nothing."
    )
    assert "Do not edit the revised copy again" not in _goal(cast.JUNIOR)  # take 1 edits


def test_owner_and_reviewers_may_write_one_image_named_for_their_phase():
    g = _goal("owner", image="t02-owner")

    assert (
        "The only file you may write is one image, t02-owner.svg or t02-owner.png, "
        "in the images folder beside the thread; write nothing else."
    ) in g
    assert _GUARDRAIL not in g
    assert _GUARDRAIL in _goal("tl")  # no image stem, no write
    assert _GUARDRAIL in _goal(cast.CHAIR, image="decision")  # the chair never gets one


def test_a_retake_title_says_which_take():
    assert cast.title("tpm", "turn", turn=5, take=1) == "turn 5 — Sam Iyer (tpm) takes the floor"
    assert cast.title("tpm", "turn", turn=5, take=2) == (
        "turn 5 — Sam Iyer (tpm) takes the floor (take 2)"
    )
    assert cast.title(cast.CHAIR, "decision", turn=0, take=3).endswith("decision (take 3)")


def test_the_tpm_and_tl_styles_ask_one_question_at_a_time():
    assert cast.CAST["tpm"]["style"] == "asks for dates and names; one question per risk."
    assert cast.CAST["tl"]["style"] == (
        "draws the boundary and asks where the proposal sits on it."
    )
    assert cast.CAST["senior_director"]["altitude"] == "company: three orgs and a year out."


# --- thread.md: the transcript ---

def test_thread_header_carries_the_charge_the_artifact_the_roster_and_the_rules(tmp_path):
    """write_header lands under HERMES_HOME: charge, artifact, everyone, then the ground rules."""
    import re

    from playbooks.committee import thread, voice

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
        rules=voice.RULES,
    )

    written = thread.path(run_id)
    assert written == tmp_path / "runs" / run_id / "thread.md"
    text = written.read_text(encoding="utf-8")
    assert text.startswith(f"# Committee — {run_id}")
    # Plain labels: the header is held to the rules it states.
    assert "\nCharge: Decide whether to approve the queue rewrite.\n" in text
    assert f"\nArtifact: {artifact}\n" in text
    assert "\nCommittee:\n" in text
    assert "**" not in text
    assert "- Dana Okoye, Senior Director (senior_director)" in text
    assert "- Priya Raman, Staff Engineer (staff_ic)" in text
    rules = "\n\nGround rules for every speaker:\n" + "\n".join(voice.RULES) + "\n"
    assert text.endswith(rules)
    assert text.index("- Priya Raman") < text.index("Ground rules for every speaker:")
    # eval's roster pattern (eval D3) can never seat a rules line
    assert not any(re.match(r"^- (\w+) — (.+)$", line) for line in voice.RULES)
    # doc-diff's reader names the document from the plain label ...
    assert thread.header_artifact(run_id) == artifact
    # ... and from a pre-voice run's bold one, still on disk and possibly still open
    legacy = "committee-20260918-000001"
    thread._append(legacy, f"# Committee — {legacy}\n\n**Artifact:** /x/p.md\n")
    assert thread.header_artifact(legacy) == "/x/p.md"


def test_images_dir_is_the_runs_private_images_folder(tmp_path):
    from playbooks.committee import thread

    folder = thread.images_dir("committee-x")

    assert folder == tmp_path / "runs" / "committee-x" / "images"
    assert folder.is_dir() and (folder.stat().st_mode & 0o777) == 0o700


@pytest.mark.parametrize("create", [True, False])
@pytest.mark.parametrize("planted", ["symlink", "file"])
def test_images_dir_refuses_a_planted_symlink_or_file(tmp_path, planted, create):
    """A worker can plant images/ as a symlink: never follow it, never chmod its target."""
    from playbooks.committee import thread

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir(mode=0o755)
    elsewhere.chmod(0o755)
    run_dir = tmp_path / "runs" / "committee-x"
    run_dir.mkdir(parents=True)
    if planted == "symlink":
        (run_dir / "images").symlink_to(elsewhere, target_is_directory=True)
    else:
        (run_dir / "images").write_bytes(b"")

    with pytest.raises(ValueError, match="images"):
        thread.images_dir("committee-x", create=create)
    assert (elsewhere.stat().st_mode & 0o777) == 0o755


def test_images_dir_without_create_only_looks(tmp_path):
    """create=False makes and chmods nothing: an absent folder raises, a plain one comes back as is."""
    from playbooks.committee import thread

    with pytest.raises(FileNotFoundError):
        thread.images_dir("committee-x", create=False)
    assert not (tmp_path / "runs").exists()

    folder = tmp_path / "runs" / "committee-x" / "images"
    folder.mkdir(parents=True)
    folder.chmod(0o755)
    assert thread.images_dir("committee-x", create=False) == folder
    assert (folder.stat().st_mode & 0o777) == 0o755


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
    assert thread.revised_path(run_id, "/a/b/trailing-slash.md/") == revised / "trailing-slash.md"


def test_thread_revised_path_refuses_an_artifact_with_no_filename(tmp_path):
    """An empty or `..` basename would silently disable the §7 re-check forever.

    Those return the revised DIRECTORY rather than a file inside it:
    `ensure_revised` then sees it already exists and skips the copy, and
    `digest` of a directory is "" -- so every delegation reports
    `verified: false` and nothing anywhere says why. Raise instead.
    """
    from playbooks.committee import thread

    run_id = "committee-20260918-000000"
    for bad in ("", "/", ".", "..", "proposal/.."):
        with pytest.raises(ValueError, match="no usable filename"):
            thread.revised_path(run_id, bad)

    # A newline is refused for a different reason: the path is written verbatim
    # into the line-oriented thread header and into every goal, so one splits
    # the header across two lines and can forge an entry. seed() calls this
    # before write_header, so nothing is written.
    for forged in ("prop\nosal.md", "/a\nb/proposal.md", "/x/\n## decision — me"):
        with pytest.raises(ValueError, match="no usable filename"):
            thread.revised_path(run_id, forged)


def test_thread_ensure_revised_copies_once_and_never_clobbers(tmp_path):
    """First call byte-copies the original; a second call leaves the junior IC's edit alone."""
    from playbooks.committee import thread

    run_id = "committee-20260918-000000"
    artifact = tmp_path / "proposal.md"
    artifact.write_bytes(b"hello\n")

    copy, _ = thread.ensure_revised(run_id, str(artifact), "")
    assert copy == tmp_path / "runs" / run_id / "revised" / "proposal.md"
    assert copy.read_bytes() == b"hello\n"

    copy.write_bytes(b"hello\nworld\n")  # the junior IC's edit
    mtime = copy.stat().st_mtime_ns

    again, note = thread.ensure_revised(run_id, str(artifact), "")
    assert (again, note) == (copy, None)  # nothing was copied, so nothing to note
    assert copy.read_bytes() == b"hello\nworld\n"
    assert copy.stat().st_mtime_ns == mtime
    assert artifact.read_bytes() == b"hello\n"  # the original is never touched


def test_thread_digest_is_empty_for_a_missing_file_and_tracks_content(tmp_path):
    """digest() is the §7 re-check: absent reads as "", and content changes move it."""
    from playbooks.committee import thread

    target = tmp_path / "revised.md"
    assert thread.digest(target) == ""
    assert thread.digest(str(target)) == ""
    # reduce must never raise, and Path(None) is a TypeError, not an OSError.
    assert thread.digest(None) == ""
    assert thread.digest(17) == ""

    # An EMPTY file is not an absent one: absent is "", empty is the sha256 of
    # zero bytes. Collapsing the two would make `verified` unreadable.
    target.write_bytes(b"")
    assert thread.digest(target) == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )

    target.write_bytes(b"hello\n")
    assert thread.digest(target) == (
        "5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03"
    )

    target.write_bytes(b"hello\nworld\n")
    assert thread.digest(str(target)) == (
        "4a1e67f2fe1d1cc7b31d0ca2ec441da4778203a036a77da10344c85e24ff0f92"
    )

    assert thread.digest(tmp_path) == ""  # a directory is not a file


# --- the document's versions: doc/ snapshots (doc-diff D1) ---


def test_snapshot_key_names_each_version_by_turn_with_a_safe_suffix():
    """Names come from (artifact, turn) alone, so no path rides on a reduction."""
    from playbooks.committee import thread

    assert thread.snapshot_key("/a/b/proposal.md", None) == "doc/00-original.md"
    assert thread.snapshot_key("/a/b/proposal.md", 3) == "doc/t03.md"
    assert thread.snapshot_key("/a/b/Makefile", 3) == "doc/t03"
    assert thread.snapshot_key("/a/b/a.b c", 3) == "doc/t03"
    assert thread.snapshot_key("/a/b/x.tar.gz", 3) == "doc/t03.gz"
    assert thread.snapshot_key("/a/b/notes." + "x" * 17, 3) == "doc/t03"
    # The cap has no upper bound; order comes from `turn`, never the name.
    assert thread.snapshot_key("/a/b/proposal.md", 100) == "doc/t100.md"
    assert thread.snapshot_key("", None) == "doc/00-original"


def test_run_file_and_snapshot_key_create_nothing(tmp_path):
    """The view calls these from a GET, and a GET must create nothing."""
    from playbooks.committee import thread

    key = thread.snapshot_key("/a/proposal.md", 3)
    assert thread.run_file("run-1", key) == tmp_path / "runs" / "run-1" / "doc" / "t03.md"
    assert not (tmp_path / "runs").exists()


def test_read_regular_reads_a_regular_file_and_nothing_else(tmp_path):
    """A symlink, a FIFO, a directory or nothing at all reads as None, at once."""
    import os
    import threading

    from playbooks.committee import thread

    real = tmp_path / "real.md"
    real.write_bytes(b"bytes\n")
    link = tmp_path / "link.md"
    link.symlink_to(real)
    fifo = tmp_path / "pipe.md"
    os.mkfifo(fifo)
    # Every fd read_regular opens, on every path, is closed again: it runs in
    # the long-lived master process. The fds this test's files are open on, not
    # a process-wide count another thread or a GC pass could move.
    def open_under_tmp():
        found = set()
        for fd in os.listdir("/proc/self/fd"):
            try:
                target = os.readlink(f"/proc/self/fd/{fd}")
            except OSError:
                continue  # closed since the listing
            if target.startswith(str(tmp_path)):
                found.add((fd, target))
        return found

    before = open_under_tmp()

    assert thread.read_regular(real) == b"bytes\n"
    assert thread.read_regular(str(real)) == b"bytes\n"
    assert thread.read_regular(link) is None       # O_NOFOLLOW
    # In a thread, so a blocking open fails this test instead of hanging the suite.
    fifo_read = []
    reader = threading.Thread(
        target=lambda: fifo_read.append(thread.read_regular(fifo)), daemon=True
    )
    reader.start()
    reader.join(timeout=5)
    assert not reader.is_alive(), "opening a FIFO blocked: O_NONBLOCK is gone"
    assert fifo_read == [None]
    assert thread.read_regular(tmp_path) is None   # a directory
    assert thread.read_regular(tmp_path / "missing.md") is None
    assert thread.read_regular(None) is None       # reduce must never raise
    assert thread.read_regular("a\0b") is None     # an embedded NUL is a ValueError
    assert open_under_tmp() - before == set()


def test_write_snapshot_is_private_and_the_last_write_wins(tmp_path):
    from playbooks.committee import thread

    thread.write_snapshot("run-1", "doc/t03.md", b"first\n")
    thread.write_snapshot("run-1", "doc/t03.md", b"second\n")

    doc = tmp_path / "runs" / "run-1" / "doc"
    assert (doc / "t03.md").read_bytes() == b"second\n"
    assert (doc / "t03.md").stat().st_mode & 0o777 == 0o600
    assert doc.stat().st_mode & 0o777 == 0o700
    assert sorted(p.name for p in doc.iterdir()) == ["t03.md"]  # no temp left behind


def test_a_failed_snapshot_write_leaves_no_file_and_no_temp(tmp_path, monkeypatch):
    """The temp is dot-prefixed, so even a crash mid-write is never served."""
    import os

    from playbooks.committee import thread

    temps = []

    def boom(src, dst):
        temps.append(src)
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="disk full"):
        thread.write_snapshot("run-1", "doc/t03.md", b"x")

    doc = tmp_path / "runs" / "run-1" / "doc"
    assert temps and os.path.basename(temps[0]).startswith(".t03.md.")
    # In the target's own directory: a temp anywhere else can sit on another
    # filesystem, where os.replace fails with EXDEV.
    assert os.path.dirname(temps[0]) == str(doc)
    assert list(doc.iterdir()) == []


@pytest.mark.parametrize("key", [
    "../escaped.md", "doc/../escaped.md", "{tmp}/escaped.md", "escaped.md",
    "doc/sub/t03.md", "doc/..", "doc", "",
])
def test_write_snapshot_refuses_a_key_outside_doc(tmp_path, key):
    """Only ``doc/<name>`` is a snapshot; any other key escapes or misfiles it.

    The absolute case points inside tmp_path: ``state_dir`` chmods what it is
    handed to 0700, so a regression must never be handed a real directory.
    """
    from playbooks.committee import thread

    with pytest.raises(ValueError, match="not a doc/ snapshot"):
        thread.write_snapshot("run-1", key.format(tmp=tmp_path), b"x")

    assert not (tmp_path / "runs").exists()  # refused before anything was created
    assert not (tmp_path / "escaped.md").exists()


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


def test_the_playbook_names_itself_and_its_three_static_phases():
    """name and phases are the only attributes the engine reads off a playbook."""
    pb = _committee()

    assert pb.name == "committee"
    assert pb.phases == ["open", "decision", "ruling"]
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
        "closed", "current_role", "current_turn", "dropped_delegation",
        "rechecks", "pre_edit_digest", "artifact_digest", "charge", "artifact",
        "revised", "roster", "max_turns", "ended",
        "delegation_turn", "dropped_delegation_turn", "answers_turn", "delegated_by_turn",
        "snapshot_note",
        "base", "take", "retake", "note", "held", "edit_digest",
    }
    assert (s["base"], s["take"], s["retake"], s["note"], s["held"], s["edit_digest"]) == (
        "", 1, None, None, None, "")
    assert s["delegation_turn"] is None and s["dropped_delegation_turn"] is None
    assert s["answers_turn"] is None and s["delegated_by_turn"] is None
    assert s["turn"] == 1
    assert s["opening"] == list(cast.SENIORITY)
    assert isinstance(s["opening"], list)  # a copy: popping must not touch the cast
    # regression 1: last_speaker starts "owner", not None -- with None the owner-reply
    # rule fires before the opening round and mints t01-owner, a reply to an empty thread.
    assert s["last_speaker"] == "owner"
    assert s["max_turns"] == 30
    assert s["queue"] == [] and s["rechecks"] == [] and s["roster"] == {}
    assert s["pre_edit_digest"] == "" and s["artifact_digest"] == ""
    assert s["delegation"] is None and s["pending_action"] is None
    assert s["dropped_delegation"] is None and s["current_role"] is None
    assert s["closed"] is False and s["current_turn"] == 0
    assert s["charge"] == "" and s["artifact"] == "" and s["revised"] == ""
    # nothing has ended yet
    assert s["ended"] is None
    assert pb._state(run) is s  # same run, same dict


def test_state_is_never_evicted_from_under_a_live_run():
    """No LRU. Evicting a live run's memory is a crash, not a saving.

    A re-created state restarts at turn 1, so next_phase re-mints `t01-…` --
    `UNIQUE constraint failed: tickets.id` on an unguarded INSERT -- or seed
    raises `KeyError: None` off `current_role`. Either abandons the run
    `running`. master_loop has one caller and drives one run per process, so a
    bound buys nothing and costs that.
    """
    pb = _committee()
    first = _run()
    first.id = "committee-run-000"
    pb._state(first)["turn"] = 9
    for n in range(1, 40):
        later = _run()
        later.id = f"committee-run-{n:03d}"
        pb._state(later)

    assert pb._state(first)["turn"] == 9, "a live run's memory was evicted"
    assert len(pb._state_by_run) == 40


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
    produced no finding. Returns (pb, run, state, phases_seen, speakers,
    delivered) -- `speakers` is who next_phase MINTED and `delivered` is whether
    that worker produced anything, parallel lists: which turns were answered
    depends on both.
    """
    pb = _committee()
    run = _run()
    s = pb._state(run)
    s["max_turns"] = max_turns
    seen = ["open"]
    speakers = []
    delivered = []
    while True:
        nxt = pb.next_phase(run)
        if nxt is None or nxt == "ruling":
            break  # `ruling` is the human's: no speaker, nothing left to model
        assert nxt not in seen, f"REPEATED PHASE {nxt!r} (seen={seen})"
        assert len(seen) < 400, f"NON-TERMINATION: {seen[:40]}..."
        seen.append(nxt)
        run.phase = nxt
        block = script(nxt, s) if callable(script) else dict(script.get(nxt, {}))
        if block.get("_retake"):
            # A take reduce discarded: its gates never run, and the same
            # speaker is asked again (`_discard` sets exactly this).
            s["retake"] = "Retake note."
        if nxt in DECISION_PHASES:
            speakers.append("chair")
            delivered.append(True)
            continue
        # the turn number reduce() reads must match the name next_phase minted;
        # a retake is `{base}-take{k}` of the same speaker and the same NN
        want = (f"t{s['current_turn']:02d}-{s['current_role']}" if s["take"] == 1
                else f"{s['base']}-take{s['take']}")
        assert nxt == want, (nxt, want)
        speakers.append(s["current_role"])
        delivered.append(bool(block.get("_ok", True)))
        if block.get("_retake"):
            continue
        # The product's gates, including what a turn with no finding does to the
        # machine. `_drive` transcribes none of that -- deleting a gate from
        # _apply_block turns every layer below RED.
        _apply_block(s, s["current_role"], block, delivered=delivered[-1])
    return pb, run, s, seen, speakers, delivered


def _kept(phases):
    """Which phases were kept: a take is discarded iff its retake follows it."""
    out = []
    for i, phase in enumerate(phases):
        base, _, k = phase.partition("-take")
        nxt = f"{base}-take{int(k or 1) + 1}"
        out.append(not (i + 1 < len(phases) and phases[i + 1] == nxt))
    return out


def check_invariants(s, seen, speakers, max_turns=30, delivered=None):
    """Every property the model asserted on every run it drove."""
    assert len(seen) == len(set(seen)), "duplicate phase name"
    assert seen[-1] in DECISION_PHASES, f"did not end at a decision phase: {seen[-1]}"
    kept = _kept(seen[1:])  # seen[0] is `open`; speakers run parallel to seen[1:]
    assert sum(
        1 for phase, k in zip(seen[1:], kept) if phase in DECISION_PHASES and k
    ) == 1, "not exactly one kept decision"
    nums = [int(p[1:3]) for p in seen if p.startswith("t") and "-take" not in p]
    if nums:
        assert max(nums) <= max_turns, f"turn cap exceeded: max NN={max(nums)} > {max_turns}"
        assert nums == sorted(nums), "turn numbers out of order"
        assert len(nums) == len(set(nums)), "turn number reused"
    # Only the cap may drop a delegation (spec 5.3). `s["delegation"] is None` would
    # be a tautology here -- both exits to `decision` go through `_decision`, which
    # clears it unconditionally -- so assert the property that actually discriminates.
    if s["dropped_delegation"]:
        assert s["turn"] > s["max_turns"], "a delegation was dropped with turns to spare"
    # kept speakers only: a discarded take is followed by its own retake, never
    # by the owner, and it said nothing the room heard
    body = [who for who, k in zip(speakers, kept) if k][:-1]  # drop the chair
    said = [d for d, k in zip(delivered or [True] * len(speakers), kept) if k][:-1]
    for i, who in enumerate(body):
        if i + 1 >= len(body):
            break  # a trailing reviewer is the documented cap cut-off
        if who in _REVIEWERS and said[i]:
            # every reviewer turn that delivered is answered by the owner
            assert body[i + 1] == "owner", f"reviewer {who} at {i} unanswered by {body[i+1]}"
        if not said[i]:
            # ... and a turn that delivered nothing is answered by NOBODY. Its
            # thread entry is the NO_TURN stub, and the owner sent to reply to
            # it either hallucinates an answer or burns the turn.
            assert body[i + 1] != "owner", f"the owner was sent to answer silence at {i}"


# --- the seven regressions from spec 11, each a defect caught in hardening ---


def test_regression_turn_01_is_the_first_opening_reviewer():
    # 1: with last_speaker=None the owner-reply rule fires first and mints t01-owner,
    # an owner reply to an empty thread -- the turn the `open` bootstrap exists to delete.
    _, _, _, seen, sp, ok = _drive({})

    assert seen[1] == "t01-senior_director", seen[1]
    assert sp[0] == "senior_director", f"turn 01 speaker is {sp[0]}, expected first reviewer"
    assert "t01-owner" not in seen


def test_regression_the_decision_phase_is_seeded_as_the_chair():
    # 2: both exits to `decision` go through _decision, which sets
    # current_role="chair". seed hardcodes the chair for the decision phase, so this
    # line is not what builds that ticket -- what it buys is that the state dict stays
    # truthful about who is speaking. _reduce_turn attributes a turn off current_role
    # and fails closed when it is wrong, so a stale role is a real defect.
    # t14-owner, not t02: a close before the opening round drains is ignored.
    _, _, closed_state, closed_seen, _, _ = _drive({"t14-owner": {"close": True}})
    assert closed_state["closed"] is True
    assert closed_seen[-1] == "decision"
    assert closed_state["current_role"] == "chair"

    _, _, capped_state, capped_seen, _, _ = _drive(lambda phase, s: {}, max_turns=3)
    assert capped_seen[-1] == "decision", capped_seen
    assert capped_state["current_role"] == "chair"


def test_regression_a_turn_with_no_finding_still_advances_the_counter():
    # 3: the counter advances in next_phase, not reduce. Advanced in reduce it would
    # stall on a failed turn and re-emit that phase name, which _phase_reduced
    # (engine/dispatch.py:311-321) reads as "already reduced" -- a silent deadlock.
    # Two silent turns back to back. Neither is answered -- a turn that said
    # nothing is answered by nobody -- and the counter walks past both onto a
    # new phase name each time.
    _, _, s, seen, sp, ok = _drive({
        "t03-manager": {"_ok": False, "request_floor": True},
        "t04-tpm": {"_ok": False, "close": True},
    })
    check_invariants(s, seen, sp, delivered=ok)

    assert seen[3:6] == ["t03-manager", "t04-tpm", "t05-pm"], seen[:8]
    assert len(seen) == len(set(seen))
    assert s["queue"] == [], "a floor request from a turn with no finding was honoured"
    assert s["closed"] is False, "a close from a turn with no finding was honoured"
    assert max(int(p[1:3]) for p in seen if p.startswith("t")) == 12


def test_regression_the_decision_leads_to_the_ruling_and_then_to_is_done():
    # 4: is_done is consulted only when next_phase returns None
    # (engine/dispatch.py:296-313); a machine that kept minting names never finishes.
    from engine.models import Reduction

    def decision(review_state, delivered=True):
        return Reduction(kind="decision", json={"delivered": delivered},
                         review_state=review_state)

    pb = _committee()
    assert pb.next_phase(_run(phase="decision")) == "ruling"
    run = _run(phase="ruling")
    assert pb.next_phase(run) is None

    # A fresh instance, as after a restart: the ruling is read off the decision
    # reduction, which the engine hands `ruling` as its prior phase.
    run.reductions = [decision("accepted")]
    assert pb.is_done(run) is True
    for held in (decision("pending"), decision("rejected"), decision("accepted", delivered=False)):
        run.reductions = [held]
        assert pb.is_done(run) is False, held

    early = _run(phase="decision")
    early.reductions = [decision("accepted")]
    assert pb.is_done(early) is False, "is_done fired before the ruling"


def test_regression_the_floor_queue_is_entered_after_the_opening_round():
    # 5: once `opening` drains, rule 5 must actually pop the queue -- an early exit to
    # decision would silently discard every floor request the committee made.
    _, _, s, seen, sp, ok = _drive({
        "t01-senior_director": {"request_floor": True},
        "t05-tpm": {"request_floor": True},
    })
    check_invariants(s, seen, sp, delivered=ok)

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
    _, _, once, once_seen, once_sp, once_ok = _drive(
        {"t02-owner": {"delegate": True, "action": "tighten the risk section"}}
    )
    check_invariants(once, once_seen, once_sp, delivered=once_ok)
    assert once_seen[3] == "t03-junior_ic", once_seen[:5]
    assert once_sp.count("junior_ic") == 1, f"delegation consumed more than once: {once_sp}"
    assert once["pending_action"] == "tighten the risk section"
    assert once_sp[once_sp.index("junior_ic") + 1] != "owner", \
        "junior_ic wrongly triggered an owner reply"

    # Both signals on one turn, at the first turn a close is actually honoured.
    _, _, both, both_seen, both_sp, both_ok = _drive(
        {"t14-owner": {"close": True, "delegate": True, "action": "x"}}
    )
    check_invariants(both, both_seen, both_sp, delivered=both_ok)
    assert both_sp.count("junior_ic") == 1, f"the delegated edit was dropped: {both_sp}"
    assert both_seen[-3:] == ["t14-owner", "t15-junior_ic", "decision"], both_seen[-4:]
    assert both["closed"] is True

    # The boundary itself: `turn <= max_turns`, not `<`. On the LAST available
    # turn the edit still happens. With `<` the delegation is dropped one turn
    # early and the committee spends that turn on another reviewer instead --
    # a change no other case in this file can see.
    _, _, just, just_seen, _, _ = _drive(
        {"t02-owner": {"delegate": True, "action": "just in time"}}, max_turns=3
    )
    assert just_seen == [
        "open", "t01-senior_director", "t02-owner", "t03-junior_ic", "decision",
    ], just_seen
    assert just["dropped_delegation"] is None

    _, _, capped, capped_seen, capped_sp, capped_ok = _drive(
        {"t02-owner": {"delegate": True, "action": "too late"}}, max_turns=2
    )
    check_invariants(capped, capped_seen, capped_sp, max_turns=2, delivered=capped_ok)
    assert "junior_ic" not in capped_sp, "the cap did not stop the edit"
    assert capped["delegation"] is None
    assert capped["dropped_delegation"] == "too late", \
        "a cap-dropped delegation must be recorded, not lost"


def test_regression_no_phase_repeats_and_the_cap_holds_across_a_full_run():
    # 7: a repeated phase name deadlocks the run silently (engine/dispatch.py:311-321)
    # and an NN above the cap breaks acceptance criterion 5.
    for max_turns in (1, 2, 3, 5, 8, 13, 30):
        _, _, s, seen, sp, ok = _drive(lambda phase, st: {"request_floor": True},
                                   max_turns=max_turns)
        check_invariants(s, seen, sp, max_turns=max_turns, delivered=ok)
        nums = [int(p[1:3]) for p in seen if p.startswith("t")]
        assert len(seen) == len(set(seen)), f"max_turns={max_turns}: {seen}"
        assert not nums or max(nums) <= max_turns, f"max_turns={max_turns}: {seen}"


# --- the two documented boundaries ------------------------------------------


def test_the_default_run_is_t01_through_t14_then_the_decision():
    """7 reviewers + 7 owner replies, no delegations, empty queue: highest NN is 14."""
    _, _, _, seen, _, _ = _drive({})

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
    _, _, s, seen, sp, ok = _drive(lambda phase, st: {"request_floor": True}, max_turns=30)
    check_invariants(s, seen, sp, max_turns=30, delivered=ok)

    nums = [int(p[1:3]) for p in seen if p.startswith("t")]
    assert max(nums) == 30
    assert not any(p.startswith("t31") for p in seen), seen[-3:]
    assert s["turn"] == 31


def test_a_stance_on_a_junior_ic_turn_moves_no_gate():
    """The junior IC's block keys are all ignored (spec 5.4) and a stance is
    no exception: it is recorded on the reduction, never acted on. The state
    machine must not grow a fourth gate for it."""
    pb = _committee()
    s = pb._state(_run())
    queue_before = list(s["queue"])

    _apply_block(
        s,
        cast.JUNIOR,
        {"stance": "the delegated edit is in", "request_floor": True, "close": True},
    )

    assert s["queue"] == queue_before
    assert s["closed"] is False
    assert s["delegation"] is None
    assert s["last_speaker"] == cast.OWNER


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
            _, _, s, seen, sp, ok = _drive(script)
            check_invariants(s, seen, sp, delivered=ok)
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
            _, _, s, seen, sp, ok = _drive(script, max_turns=max_turns)
            check_invariants(s, seen, sp, max_turns=max_turns, delivered=ok)
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
    assert s["artifact_digest"] == thread.digest(artifact)
    assert s["revised"] == str(thread.revised_path(run.id, str(artifact)))
    assert s["max_turns"] == 30


def test_open_writes_the_ground_rules_and_makes_the_images_folder(artifact, tmp_path):
    from playbooks.committee import thread, voice

    pb = _committee()
    run = _run(phase="open")
    pb.seed(run, _NamedSite("local"))

    assert "\n".join(voice.RULES) in thread.path(run.id).read_text(encoding="utf-8")
    images = tmp_path / "runs" / run.id / "images"
    assert images.is_dir() and (images.stat().st_mode & 0o777) == 0o700


def test_open_snapshots_the_bytes_it_hashed_before_the_header(artifact, tmp_path):
    """doc/00-original is exactly what `artifact_digest` hashed, in one process."""
    import hashlib

    from playbooks.committee import thread

    pb = _committee()
    run = _run(phase="open")
    pb.seed(run, _NamedSite("local"))

    snap = tmp_path / "runs" / run.id / "doc" / "00-original.md"
    assert snap.read_bytes() == artifact.read_bytes()
    assert hashlib.sha256(snap.read_bytes()).hexdigest() == (
        pb._state_by_run[run.id]["artifact_digest"]
    )
    assert snap.stat().st_mode & 0o777 == 0o600
    assert thread.path(run.id).read_text(encoding="utf-8").startswith(
        f"# Committee — {run.id}"
    )


def test_a_failed_open_snapshot_fails_open_before_any_header(artifact, tmp_path, monkeypatch):
    """Snapshot first, header second: no header claims a meeting that never opened."""
    from playbooks.committee import thread

    def boom(run_id, key, data):
        raise OSError("disk full")

    monkeypatch.setattr(thread, "write_snapshot", boom)
    pb = _committee()
    run = _run(phase="open")

    with pytest.raises(OSError, match="disk full"):
        pb.seed(run, _NamedSite("local"))
    assert not (tmp_path / "runs" / run.id / "thread.md").exists()


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

    # Resolved ONCE, at `open`: the docstring says so and nothing else did. A
    # mid-run environment change must not swap the cap or the artifact under a
    # conversation that is already half-written.
    s = pb._state(run)
    before = (s["max_turns"], s["artifact"], s["revised"], s["charge"])
    swapped = artifact.parent / "a-different-proposal.md"
    swapped.write_text("# Something else\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_COMMITTEE_MAX_TURNS", "2")
    monkeypatch.setenv("HERMES_COMMITTEE_ARTIFACT", str(swapped))
    s["current_role"] = "manager"
    pb.seed(_run(phase="t02-manager"), _NamedSite("local"))
    assert (s["max_turns"], s["artifact"], s["revised"], s["charge"]) == before

    monkeypatch.setenv("HERMES_COMMITTEE_ARTIFACT", str(artifact))
    monkeypatch.setenv("HERMES_COMMITTEE_MAX_TURNS", "soon")
    other = _committee()
    other.seed(run, _NamedSite("local"))
    assert other._state(run)["max_turns"] == 30


def test_a_cap_below_one_is_junk_like_any_other_junk(artifact, monkeypatch):
    """`0` and `-5` parse, and mint a committee that never speaks.

    `int("0")` does not raise, so the junk fallback above never sees it, and the
    chair ends up ruling on an empty thread. A cap that cannot produce a single
    turn is not a time-box, it is a typo.
    """
    from playbooks.committee.playbook import DEFAULT_MAX_TURNS

    for value in ("0", "-5", "-1"):
        monkeypatch.setenv("HERMES_COMMITTEE_MAX_TURNS", value)
        pb = _committee()
        run = _run(phase="open")
        pb.seed(run, _NamedSite("local"))
        assert pb._state(run)["max_turns"] == DEFAULT_MAX_TURNS, value

    # 1 is a legitimate, if brutal, cap: one turn, then the decision.
    monkeypatch.setenv("HERMES_COMMITTEE_MAX_TURNS", "1")
    pb = _committee()
    run = _run(phase="open")
    pb.seed(run, _NamedSite("local"))
    assert pb._state(run)["max_turns"] == 1


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
    charge = long_pb._state(long_run)["charge"]
    assert len(charge) == cast.CHARGE_MAX
    assert cast.CHARGE_MAX == 400
    # Cut with an ellipsis, not with a raw slice: a charge chopped mid-word is
    # what the worker reads as the question it is answering.
    assert charge.endswith("…")

    wordy = _committee()
    wordy_run = _run(config={"goals": ["word " * 200]}, phase="open")
    wordy.seed(wordy_run, _NamedSite("local"))
    assert wordy._state(wordy_run)["charge"].endswith("word…")


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
    assert t.payload["title"] == "turn 1 — Dana Whitfield (senior_director) takes the floor"
    assert t.payload["kind"] == "turn"
    assert t.payload["action"] is None
    assert str(artifact) in t.payload["goal"]
    assert str(thread.path(run.id)) in t.payload["goal"]
    assert len(t.payload["goal"]) <= cast.GOAL_MAX
    contracts.validate(t.payload, pb.payload_schema(phase))


def test_junior_seed_byte_copies_the_original_and_leaves_it_untouched(artifact):
    """§5.5: the revised copy is in place before the junior IC's worker runs."""
    import hashlib

    from playbooks.committee import cast, thread

    pb = _committee()
    site = _NamedSite("local")
    run = _run(phase="open")
    pb.seed(run, site)
    original = artifact.read_bytes()

    s = pb._state(run)
    s["current_role"] = cast.JUNIOR
    s["current_turn"] = 4
    s["pending_action"] = "cut the roadmap section to one paragraph"

    tickets = pb.seed(_run(phase="t04-junior_ic"), site)

    revised = thread.revised_path(run.id, str(artifact))
    assert revised.read_bytes() == original
    assert artifact.read_bytes() == original
    # The §7 snapshot: taken AFTER ensure_revised, over the COPY. On this first
    # delegation the copy is byte-identical to the original, so the digest is
    # the original's -- which is the only thing that makes the two readings
    # distinguishable on the second delegation (see the test below).
    assert s["pre_edit_digest"] == hashlib.sha256(original).hexdigest()
    t = tickets[0]
    assert set(t.payload) == {"role", "title", "goal", "kind", "action"}
    assert t.payload["role"] == "junior_ic"
    assert t.payload["title"] == (
        "turn 4 — Alex Moreau (junior_ic) edits: cut the roadmap section to one paragraph"
    )
    assert t.payload["kind"] == "edit"
    assert t.payload["action"] == "cut the roadmap section to one paragraph"
    assert str(revised) in t.payload["goal"]


def test_a_second_junior_seed_keeps_the_edited_revised_copy(artifact):
    """ensure_revised copies only when absent: a later edit builds on the first."""
    import hashlib

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
    # The second snapshot is of the EDITED copy, not of the original: comparing
    # a later edit against the original reports `verified: true` for every one
    # of them, including an edit that changed nothing (spec §7).
    assert s["pre_edit_digest"] == hashlib.sha256(revised.read_bytes()).hexdigest()
    assert s["pre_edit_digest"] != hashlib.sha256(artifact.read_bytes()).hexdigest()


def test_a_junior_seed_survives_an_artifact_deleted_mid_run(artifact):
    """A vanished original AND snapshot degrade the turn; they must not abandon the run.

    `ensure_revised` copies from doc/00-original first, so only both files gone
    reaches its OSError. `seed` is called unguarded inside the master loop
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
    thread.run_file(run.id, thread.snapshot_key(str(artifact), None)).unlink()
    s = pb._state(run)
    s["current_role"] = cast.JUNIOR
    s["pending_action"] = "add a rollback plan"

    tickets = pb.seed(_run(phase="t04-junior_ic"), site)

    assert len(tickets) == 1
    assert tickets[0].payload["kind"] == "edit"
    assert s["pre_edit_digest"] == ""
    assert not thread.revised_path(run.id, s["artifact"]).exists()


def test_edit_one_starts_from_the_open_time_bytes_even_if_the_original_moved(artifact):
    """Every worker runs bypassPermissions. If one touches the original, the junior
    still edits what the committee was handed, and the re-check baseline is the
    digest `open` took."""
    from playbooks.committee import cast, thread

    pb = _committee()
    site = _NamedSite("local")
    run = _run(phase="open")
    pb.seed(run, site)
    handed = artifact.read_bytes()
    artifact.write_text("# Proposal\n\nSomeone rewrote this mid-review.\n", encoding="utf-8")

    s = pb._state(run)
    s.update(current_role=cast.JUNIOR, current_turn=3, pending_action="tighten the intro")
    pb.seed(_run(phase="t03-junior_ic"), site)

    assert thread.revised_path(run.id, str(artifact)).read_bytes() == handed
    assert s["pre_edit_digest"] == s["artifact_digest"]


def test_ensure_revised_prefers_the_open_snapshot_and_falls_back_to_the_artifact(tmp_path):
    """doc/00-original when it is a regular file holding the bytes `open`
    hashed; the live artifact otherwise, with a note saying so.

    Every worker runs bypassPermissions, so one can delete doc/00-original,
    swap it for a symlink or rewrite it. A symlink is refused, not followed,
    and rewritten bytes fail the digest: neither is the snapshot `open` wrote.
    """
    import hashlib

    from playbooks.committee import thread

    artifact = tmp_path / "proposal.md"
    artifact.write_bytes(b"live\n")
    key = thread.snapshot_key(str(artifact), None)
    handed = hashlib.sha256(b"handed\n").hexdigest()
    fallback = ("snapshot: doc/00-original.md is not the file open wrote, so the "
                "revised copy was made from the live artifact")

    copy, note = thread.ensure_revised("run-deleted", str(artifact), handed)
    assert (copy.read_bytes(), note) == (b"live\n", fallback)

    thread.write_snapshot("run-new", key, b"handed\n")
    copy, note = thread.ensure_revised("run-new", str(artifact), handed)
    assert (copy.read_bytes(), note) == (b"handed\n", None)

    thread.write_snapshot("run-rewritten", key, b"rewritten by a worker\n")
    copy, note = thread.ensure_revised("run-rewritten", str(artifact), handed)
    assert (copy.read_bytes(), note) == (b"live\n", fallback)

    decoy = tmp_path / "decoy.md"
    decoy.write_bytes(b"handed\n")  # even the right bytes, behind a symlink
    link = thread.run_file("run-linked", key)
    link.parent.mkdir(parents=True)
    link.symlink_to(decoy)
    copy, note = thread.ensure_revised("run-linked", str(artifact), handed)
    assert (copy.read_bytes(), note) == (b"live\n", fallback)


def test_a_rewritten_open_snapshot_is_not_edit_ones_baseline_and_the_turn_says_so(artifact):
    """doc/00-original is worker-writable, and `artifact_intact` hashes only the
    live file. Copying a rewritten snapshot would fold the tampering silently
    into the recommended revision; the live file, which that check covers, is
    used instead, and the junior turn's reduction names what happened."""
    from playbooks.committee import cast, thread

    pb = _committee()
    site = _NamedSite("local")
    pb.seed(_run(phase="open"), site)
    handed = artifact.read_bytes()
    run = _run(phase="t03-junior_ic")
    thread.run_file(run.id, thread.snapshot_key(str(artifact), None)).write_bytes(
        b"# Proposal\n\nRewritten by a reviewer worker.\n"
    )

    s = pb._state(run)
    s.update(current_role=cast.JUNIOR, current_turn=3, pending_action="tighten the intro")
    pb.seed(run, site)

    assert thread.revised_path(run.id, str(artifact)).read_bytes() == handed
    assert s["pre_edit_digest"] == s["artifact_digest"]
    junior = pb.reduce(
        run, "t03-junior_ic",
        [_finding(run, f"{run.id}/t03-junior_ic", _turn_answer("Nothing to tighten."))],
        site,
    )[0]
    assert "snapshot: doc/00-original.md is not the file open wrote" in junior.json["error"]


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
    assert t.payload["title"] == "Dana Whitfield (chair) delivers the committee decision"
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


def test_reduce_refuses_a_close_before_the_opening_round_drains():
    """The owner may not end a nine-persona committee at turn 02 (spec 5.4).

    The owner persona's goal is "get a clear decision" and its style "concedes
    fast on small things", so a real worker that hears one reviewer, answers it
    and closes produces a two-turn "committee" that reaches `done` looking
    perfectly healthy while six members never speak. The gate is enforced here,
    not merely asked for in the goal.
    """
    pb = _committee()
    run = _run(phase="t02-owner")
    s = pb._state(run)
    s.update(current_role="owner", current_turn=2)  # `opening` left as seeded

    assert s["opening"], "the opening round has not drained"
    answer = _turn_answer("Heard; I think we are done here.", close="yes")
    reductions = pb.reduce(
        run, "t02-owner", [_finding(run, f"{run.id}/t02-owner", answer)],
        _NamedSite("local"),
    )

    assert s["closed"] is False
    assert reductions[0].json["close"] is True  # said, not honoured

    # The same block, once every member has spoken, does close the discussion.
    s.update(opening=[], current_turn=14)
    pb.reduce(
        run, "t14-owner", [_finding(run, f"{run.id}/t14-owner", answer)],
        _NamedSite("local"),
    )
    assert s["closed"] is True


def test_an_early_close_does_not_shorten_the_committee():
    """The whole machine, not just the gate: t02's close leaves the round intact."""
    _, _, s, seen, sp, ok = _drive({"t02-owner": {"close": True}})
    check_invariants(s, seen, sp, delivered=ok)

    assert s["closed"] is False
    assert seen[-2:] == ["t14-owner", "decision"], seen
    assert set(cast.SENIORITY) <= set(sp), f"a member never spoke: {sp}"


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


def test_reduce_does_not_send_the_owner_to_answer_a_turn_that_said_nothing():
    """A failed reviewer turn leaves the NO_TURN stub; nobody replies to it.

    Observed live: t01 failed, the thread carried the stub, and t02 was still
    minted as an owner reply. `driver_failed` is terminal on first occurrence
    with no retry, so any single worker hiccup produces this. The owner's floor
    text says "Answer the member who spoke last"; a real model reading
    `_(no turn delivered …)_` hallucinates a reply or burns the turn.

    Driven through the real next_phase/reduce pair, not a hand-built state dict:
    what is under test is exactly the handover between them.
    """
    from playbooks.committee import thread

    pb = _committee()
    run = _run(phase="open")
    phase = pb.next_phase(run)
    assert phase == "t01-senior_director"
    run.phase = phase
    s = pb._state(run)
    assert s["last_speaker"] == "senior_director"  # what _turn recorded

    pb.reduce(run, phase, [], _NamedSite("local"))  # the worker produced nothing

    assert thread.NO_TURN in thread.path(run.id).read_text()
    assert s["last_speaker"] == cast.OWNER
    assert pb.next_phase(run) == "t02-manager", "the owner was sent to answer silence"

    # The comparison arm: a turn that DID deliver is answered, as always.
    other = _committee()
    other_run = _run(phase="open")
    other_phase = other.next_phase(other_run)
    other_run.phase = other_phase
    other.reduce(
        other_run,
        other_phase,
        [_finding(other_run, f"{other_run.id}/{other_phase}", "Two questions.")],
        _NamedSite("local"),
    )
    assert other.next_phase(other_run) == "t02-owner"


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


@pytest.mark.parametrize("phase", ["t04-owner", "decision"])
def test_a_process_that_never_held_the_meeting_grants_nothing_and_ends_it(phase):
    """Past `open` with no speaker on record, this instance never held the
    meeting: no thread entry under anyone's name, no owner authority, no
    verdict, and no re-minted `t01` -- the run ends failed, saying why."""
    from playbooks.committee import thread

    pb = _committee()
    run = _run(phase=phase)

    answer = _turn_answer("Closing this.", close="yes", delegate="yes", action="x")
    reductions = pb.reduce(
        run, phase, [_finding(run, f"{run.id}/{phase}", answer)], _NamedSite("local"),
    )

    s = pb._state(run)
    assert s["closed"] is False and s["delegation"] is None
    assert [r.kind for r in reductions] == ["lost"]
    assert "cannot be resumed" in reductions[0].json["error"]
    assert not thread.path(run.id).exists()
    if phase != "decision":  # decision -> ruling reads the database, not this instance
        assert pb.next_phase(run) is None


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


def test_reduce_never_raises_on_a_finding_whose_json_is_not_a_dict():
    """A truthy non-dict under `finding.json` must not raise out of reduce.

    `(["x"] or {})` is the list, so `.get` is an AttributeError -- out of reduce,
    out of engine/dispatch.py:305, and the run is abandoned `running` with no
    terminal state and no event. A non-dict carries no answer, which is the same
    thing as a turn that delivered nothing.
    """
    from playbooks.committee import thread

    pb = _committee()
    run = _run(phase="t03-pm")
    s = pb._state(run)
    s.update(current_role="pm", current_turn=3, opening=[])

    findings = [
        Finding(run_id=run.id, ticket_id=f"{run.id}/t03-pm", kind="result", json=["x"]),
        Finding(run_id=run.id, ticket_id=f"{run.id}/t03-pm", kind="result", json="prose"),
        Finding(run_id=run.id, ticket_id=f"{run.id}/t03-pm", kind="result", json=None),
        Finding(run_id=run.id, ticket_id=f"{run.id}/t03-pm", kind="result", json=7),
    ]
    reductions = pb.reduce(run, "t03-pm", findings, _NamedSite("local"))

    assert len(reductions) == 1
    assert reductions[0].json["delivered"] is False
    assert reductions[0].json["error"] is None
    assert thread.NO_TURN in thread.path(run.id).read_text()

    # A real answer alongside the junk still wins: the fold skips, never stops.
    s["current_turn"] = 4
    salvaged = pb.reduce(
        run,
        "t04-pm",
        [findings[0], _finding(run, f"{run.id}/t04-pm", "Two concerns.")],
        _NamedSite("local"),
    )
    assert salvaged[0].json["delivered"] is True
    assert "Two concerns." in thread.path(run.id).read_text()


# --- reduce: the independent re-check of a junior-IC edit (spec 7) --------


def test_reduce_records_a_junior_ic_edit_that_changed_the_file_as_verified(tmp_path):
    """The master re-hashes the revised copy: changed means the edit landed."""
    from playbooks.committee import thread

    pb = _committee()
    run = _run(phase="t05-junior_ic")
    artifact = tmp_path / "proposal.md"
    artifact.write_text("the original proposal\n")
    revised, _ = thread.ensure_revised(run.id, str(artifact), "")
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
    revised, _ = thread.ensure_revised(run.id, str(artifact), "")  # byte-copy, never edited

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
    revised, _ = thread.ensure_revised(run.id, str(artifact), "")
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
    """No revised copy at all is the loudest failure of the re-check.

    `pre_edit_digest` is a REAL digest here, so the `before and ...` clause does
    not short-circuit and `data is not None` -- `read_regular` found no regular
    file -- is what has to catch this. Without it, hashing None raises inside
    the re-check, and an absent file -- an answer -- is recorded as a crash.
    """
    from playbooks.committee import thread

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
        pre_edit_digest=thread.digest(artifact),
    )
    assert s["pre_edit_digest"], "the guard under test is short-circuited"

    reductions = pb.reduce(
        run,
        "t05-junior_ic",
        [_finding(run, f"{run.id}/t05-junior_ic", "Added a rollback paragraph.")],
        _NamedSite("local"),
    )

    assert reductions[0].json["verified"] is False
    # An absent file is an answer, not a crash -- and no snapshot to show for it.
    assert reductions[0].json["error"] == "snapshot: revised copy is not a regular file"
    assert not (tmp_path / "runs" / run.id / "doc" / "t05.md").exists()


def test_reduce_treats_a_missing_pre_edit_snapshot_as_a_failed_recheck(tmp_path):
    """An empty `pre_edit_digest` is a FAILED snapshot, and can only be a failure.

    `seed` leaves it empty in exactly one case: no copy could be made -- the
    original and doc/00-original both vanished, or the write into revised/
    failed -- so nothing was hashed. If the worker then CREATES the
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
        artifact=str(tmp_path / "proposal.md"),  # gone, like doc/00-original
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


# --- reduce: the doc/tNN snapshot of every junior-IC turn (doc-diff D1) -----


def _junior_turn(pb, run, tmp_path, turn=5):
    """State for junior-IC turn `turn` whose revised copy seed() already made."""
    from playbooks.committee import thread

    artifact = tmp_path / "proposal.md"
    artifact.write_text("the original proposal\n")
    copy, _ = thread.ensure_revised(run.id, str(artifact), "")
    pb._state(run).update(
        current_role="junior_ic",
        current_turn=turn,
        opening=[],
        artifact=str(artifact),
        revised=str(copy),
        pending_action="add a rollback paragraph",
        pre_edit_digest=thread.digest(copy),
    )
    return copy


def _edited(run):
    return [_finding(run, f"{run.id}/t05-junior_ic", "Added a rollback paragraph.")]


def test_a_junior_turn_leaves_a_snapshot_of_the_copy_it_judged(tmp_path):
    pb = _committee()
    run = _run(phase="t05-junior_ic")
    copy = _junior_turn(pb, run, tmp_path)
    copy.write_text("the original proposal\nand a rollback paragraph\n")

    red = pb.reduce(run, "t05-junior_ic", _edited(run), _NamedSite("local"))[0]

    snap = tmp_path / "runs" / run.id / "doc" / "t05.md"
    assert snap.read_bytes() == copy.read_bytes()
    assert red.json["verified"] is True
    assert red.json["error"] is None


def test_an_undelivered_junior_turn_still_leaves_its_unchanged_snapshot(tmp_path):
    pb = _committee()
    run = _run(phase="t05-junior_ic")
    _junior_turn(pb, run, tmp_path)

    red = pb.reduce(run, "t05-junior_ic", [], _NamedSite("local"))[0]

    assert red.json["delivered"] is False
    assert red.json["verified"] is False
    assert (tmp_path / "runs" / run.id / "doc" / "t05.md").read_bytes() == (
        b"the original proposal\n"
    )


def test_a_symlinked_revised_copy_is_neither_verified_nor_snapshotted(tmp_path):
    pb = _committee()
    run = _run(phase="t05-junior_ic")
    copy = _junior_turn(pb, run, tmp_path)
    elsewhere = tmp_path / "elsewhere.md"
    elsewhere.write_text("a file the worker pointed the copy at\n")
    copy.unlink()
    copy.symlink_to(elsewhere)

    red = pb.reduce(run, "t05-junior_ic", _edited(run), _NamedSite("local"))[0]

    assert red.json["verified"] is False
    assert red.json["error"] == "snapshot: revised copy is not a regular file"
    assert not (tmp_path / "runs" / run.id / "doc" / "t05.md").exists()


def test_a_failed_snapshot_write_is_recorded_and_the_meeting_goes_on(tmp_path, monkeypatch):
    from playbooks.committee import thread

    pb = _committee()
    run = _run(phase="t05-junior_ic")
    copy = _junior_turn(pb, run, tmp_path)
    copy.write_text("the original proposal\nand a rollback paragraph\n")

    def boom(run_id, key, data):
        raise OSError("disk full")

    monkeypatch.setattr(thread, "write_snapshot", boom)
    red = pb.reduce(run, "t05-junior_ic", _edited(run), _NamedSite("local"))[0]

    assert red.json["verified"] is True
    assert red.json["error"] == "snapshot: disk full"
    assert pb.next_phase(run) == "decision"


def test_a_turn_settled_again_overwrites_its_snapshot(tmp_path):
    """A committee-voice retake re-settles the same turn: the last settle wins."""
    pb = _committee()
    run = _run(phase="t05-junior_ic")
    copy = _junior_turn(pb, run, tmp_path)

    copy.write_text("take one\n")
    pb.reduce(run, "t05-junior_ic", _edited(run), _NamedSite("local"))
    copy.write_text("take two\n")
    pb.reduce(run, "t05-junior_ic", _edited(run), _NamedSite("local"))

    assert (tmp_path / "runs" / run.id / "doc" / "t05.md").read_bytes() == b"take two\n"


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


def test_reduce_decision_names_an_original_artifact_that_changed(artifact):
    """Criterion 6, first half: the original is promised inviolate. Re-check it.

    In a live run the promise is one sentence of prose against a worker running
    `--permission-mode bypassPermissions`; both test layers pass only because
    their doubles cannot write. So the master re-hashes the original at the
    decision, symmetrically with the junior-IC re-check, and names a mismatch.
    """
    from playbooks.committee import thread

    pb = _committee()
    run = _run(phase="open")
    pb.seed(run, _NamedSite("local"))
    s = pb._state(run)
    s["current_role"] = "chair"

    # ... mid-run, something writes the file the committee was told not to touch.
    artifact.write_text("# Proposal\n\nShip the thing, and also this.\n", encoding="utf-8")

    reductions = pb.reduce(
        run, "decision", [_finding(run, f"{run.id}/decision", "Approve.")],
        _NamedSite("local"),
    )

    red = reductions[0]
    assert red.json["artifact_intact"] is False
    assert "CHANGED DURING THE REVIEW" in red.json["verdict"]
    assert str(artifact) in red.json["verdict"]
    # ... and a human reading only thread.md learns it too.
    assert "CHANGED DURING THE REVIEW" in thread.path(run.id).read_text()


def test_reduce_decision_says_nothing_when_the_original_is_untouched(artifact):
    """The healthy path: no line, and `artifact_intact` records the fact."""
    pb = _committee()
    run = _run(phase="open")
    pb.seed(run, _NamedSite("local"))
    pb._state(run)["current_role"] = "chair"

    reductions = pb.reduce(
        run, "decision", [_finding(run, f"{run.id}/decision", "Approve.")],
        _NamedSite("local"),
    )

    assert reductions[0].json["artifact_intact"] is True
    assert "CHANGED DURING THE REVIEW" not in reductions[0].json["verdict"]


def test_reduce_decision_names_a_deleted_original(artifact):
    """An original that vanished is a change like any other, not a crash.

    `digest` of an absent file is "", which is not the snapshot, so the
    comparison already catches it -- and reduce must never raise.
    """
    pb = _committee()
    run = _run(phase="open")
    pb.seed(run, _NamedSite("local"))
    pb._state(run)["current_role"] = "chair"
    artifact.unlink()

    reductions = pb.reduce(
        run, "decision", [_finding(run, f"{run.id}/decision", "Approve.")],
        _NamedSite("local"),
    )

    assert reductions[0].json["artifact_intact"] is False
    assert reductions[0].json["error"] is None


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


def test_reduce_decision_names_floor_requests_the_review_never_reached():
    """Symmetry with dropped_delegation: the queue is otherwise discarded silently.

    `_decision` moves a pending delegation to `dropped_delegation` and says so,
    but `s["queue"]` was thrown away without a word -- so a close or a cap could
    cut off three members who had asked for a second turn and nothing anywhere
    recorded it.
    """
    pb = _committee()
    run = _run(phase="decision")
    s = pb._state(run)
    s["current_role"] = "chair"
    s["queue"] = ["staff_ic", "tpm"]

    reductions = pb.reduce(
        run, "decision", [_finding(run, f"{run.id}/decision", "Approve.")],
        _NamedSite("local"),
    )

    red = reductions[0]
    assert red.json["dropped_floor_requests"] == ["staff_ic", "tpm"]
    assert "dropped_floor_requests" in red.json["verdict"]
    assert "staff_ic, tpm" in red.json["verdict"]


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
    assert red.json["delivered"] is False  # what `is_done` reads: the run ends failed

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
    assert reductions[0].json["delivered"] is True  # the run still finishes


def test_only_the_decision_reduction_routes_to_review(artifact):
    """The decision routes the chair's own ticket; no mid-run reduction may.

    That key sends the ticket to needs_human, which blocks advancement. On a turn
    that wedges the conversation; on the decision it holds only `done`. The id
    has to be the ticket `seed` minted: a wrong one routes nothing, silently.
    """
    pb = _committee()
    site = _NamedSite("local")
    pb.seed(_run(phase="open"), site)
    decision_ticket = pb.seed(_run(phase="decision"), site)[0]
    run = _run(phase="t03-tl")
    s = pb._state(run)
    s.update(current_role="tl", current_turn=3, opening=[])

    mid_run = pb.reduce(run, "open", [], site)
    answer = _turn_answer("Ship it.", request_floor="no")
    mid_run += pb.reduce(run, "t03-tl", [_finding(run, f"{run.id}/t03-tl", answer)], site)
    s["current_role"] = "chair"
    decision = pb.reduce(
        run, "decision", [_finding(run, decision_ticket.id, "Approve.")], site
    )

    assert len(mid_run) == 1
    assert "needs_human_ticket_ids" not in mid_run[0].json
    assert decision[0].json["needs_human_ticket_ids"] == [decision_ticket.id]


def test_a_failed_chair_routes_nothing_to_review():
    """No verdict, nothing to rule on: the run ends failed, not held."""
    pb = _committee()
    run = _run(phase="decision")
    pb._state(run)["current_role"] = "chair"

    reductions = pb.reduce(run, "decision", [], _NamedSite("local"))

    assert reductions[0].json["needs_human_ticket_ids"] == []


# --- what a reduction carries for the view (spec 6, 7) ---------------------
#
# `view_data` runs in the SERVER process, where this instance has never seen the
# run and `_state_by_run` is empty. Everything the view renders therefore has to
# be ON a reduction -- including the two artifact paths, which look redundant on
# a turn and are not.


def test_a_turn_reduction_carries_the_prose_both_artifact_paths_and_the_cap():
    """The reduction is the view's only channel; `thread.md` is not in the DB.

    The cap rides here for the same reason the two paths do. `view_data` runs in
    the SERVER process: reading HERMES_COMMITTEE_MAX_TURNS there gets that
    process's value, and a `hermes serve` started without it rendered "turn 20
    of 30" for a run that capped at 20 and used all of it.
    """
    pb = _committee()
    run = _run(phase="t03-staff_ic")
    s = pb._state(run)
    s.update(
        current_role="staff_ic",
        current_turn=3,
        opening=[],
        artifact="/srv/proposals/migration.md",
        revised="/var/hermes/runs/r1/revised/migration.md",
        max_turns=20,
    )

    answer = _turn_answer("The rollout plan is thin.", request_floor="yes")
    red = pb.reduce(
        run, "t03-staff_ic", [_finding(run, f"{run.id}/t03-staff_ic", answer)],
        _NamedSite("local"),
    )[0]

    assert red.json["body"] == "The rollout plan is thin."
    assert "hermes-turn" not in red.json["body"]  # stripped, as the transcript is
    assert red.json["artifact"] == "/srv/proposals/migration.md"
    assert red.json["revised"] == "/var/hermes/runs/r1/revised/migration.md"
    assert red.json["cap"] == 20


def test_a_turn_reduction_body_distinguishes_signals_only_from_silence():
    """A delivered turn carrying no prose is not a failed turn (spec 5.2)."""
    from playbooks.committee.playbook import _SIGNALS_ONLY

    pb = _committee()
    run = _run(phase="t04-owner")
    s = pb._state(run)
    s.update(current_role="owner", current_turn=4, opening=[])

    signals = pb.reduce(
        run, "t04-owner",
        [_finding(run, f"{run.id}/t04-owner", _turn_answer("", close="no"))],
        _NamedSite("local"),
    )[0]
    assert signals.json["delivered"] is True
    assert signals.json["body"] == _SIGNALS_ONLY

    s["current_turn"] = 5
    silent = pb.reduce(run, "t05-owner", [], _NamedSite("local"))[0]
    assert silent.json["delivered"] is False
    assert silent.json["body"] == ""


def test_a_turn_reduction_carries_a_stance_and_absent_stays_absent():
    """A persona that stated no stance has none, never a neutral one (spec 7)."""
    pb = _committee()
    run = _run(phase="t01-senior_director")
    s = pb._state(run)
    s.update(current_role="senior_director", current_turn=1, opening=[])

    stated = pb.reduce(
        run, "t01-senior_director",
        [_finding(
            run, f"{run.id}/t01-senior_director",
            _turn_answer("The dates are the problem.",
                         stance="against until the dates are funded"),
        )],
        _NamedSite("local"),
    )[0]
    assert stated.json["stance"] == "against until the dates are funded"

    s.update(current_role="manager", current_turn=2)
    quiet = pb.reduce(
        run, "t02-manager",
        [_finding(run, f"{run.id}/t02-manager", _turn_answer("No view yet.", close="no"))],
        _NamedSite("local"),
    )[0]
    assert quiet.json["stance"] is None
    assert "stance" in quiet.json  # present-and-None, never missing

    s.update(current_role="senior_director", current_turn=8)
    pb.reduce(
        run, "t08-senior_director",
        [_finding(
            run, f"{run.id}/t08-senior_director",
            _turn_answer("Funded now; I can live with it.", stance="for, with the funding"),
        )],
        _NamedSite("local"),
    )

    # An unattributable turn still records the stance it stated on its own
    # reduction; `view.py:_stances` is what refuses to file it under a persona.
    s.update(current_role="", current_turn=9)
    orphan = pb.reduce(
        run, "t09-nobody",
        [_finding(run, f"{run.id}/t09-nobody",
                  _turn_answer("Who am I?", stance="drop it"))],
        _NamedSite("local"),
    )[0]
    assert orphan.json["stance"] == "drop it"  # the reduction still records it


def test_next_phase_records_why_the_meeting_stopped():
    """Three of the four endings are decided by the branch `next_phase` takes."""
    # the owner closed, after the opening round drained
    _, _, closed, seen, _, _ = _drive({"t14-owner": {"close": True}})
    assert seen[-1] == "decision"
    assert closed["ended"] == "owner closed"

    # the cap cut the discussion off
    _, _, capped, _, _, _ = _drive(lambda phase, s: {}, max_turns=3)
    assert capped["ended"] == "turn cap"

    # nobody asked for a second turn
    _, _, quiet, _, _, _ = _drive({})
    assert quiet["ended"] == "queue empty"

    # both at once: the close is the reason, the cap is incidental. Mirrors the
    # `or` in next_phase, which reads `closed` first.
    _, _, both, _, _, _ = _drive({"t14-owner": {"close": True}}, max_turns=14)
    assert both["closed"] is True and both["turn"] > 14
    assert both["ended"] == "owner closed"


def test_next_phase_records_which_turn_each_owner_and_junior_turn_answers():
    """Provenance is recorded at the mint, not inferred later from turn order."""
    minted = {}

    def script(phase, s):
        minted[phase] = (s["answers_turn"], s["delegated_by_turn"])
        if phase == "t02-owner":
            return {"delegate": True, "action": "tighten the risk section"}
        return {}

    _drive(script)

    assert minted["t01-senior_director"] == (None, None)
    assert minted["t02-owner"] == (1, None)
    assert minted["t03-junior_ic"] == (None, 2)
    assert minted["t04-manager"] == (None, None)
    assert minted["t05-owner"] == (4, None)


def test_a_junior_turn_records_the_delegating_owner_turn_even_with_turns_between():
    """Today the junior is minted right after the owner, so the delegating turn
    and the last turn coincide. Items 2 and 3 put turns between them, and the
    recorded link must still name the owner turn that delegated."""
    pb = _committee()
    run = _run(phase="t05-tpm")
    s = pb._state(run)
    s.update(current_role="tpm", current_turn=5, turn=6, last_speaker="tpm",
             delegation="tighten the risk section", delegation_turn=2)

    assert pb.next_phase(run) == "t06-junior_ic"
    assert s["delegated_by_turn"] == 2


def test_every_turn_reduction_carries_both_links_null_when_not_applicable():
    """Always written: an ABSENT key is what marks a pre-change reduction."""
    pb = _committee()
    run = _run(phase="t02-owner")
    s = pb._state(run)
    s.update(current_role="owner", current_turn=2, opening=[], answers_turn=1)

    owner = pb.reduce(
        run, "t02-owner",
        [_finding(run, f"{run.id}/t02-owner", _turn_answer("Conceded.", close="no"))],
        _NamedSite("local"),
    )[0]
    assert owner.json["answers_turn"] == 1
    assert "delegated_by_turn" in owner.json and owner.json["delegated_by_turn"] is None

    s.update(current_role="manager", current_turn=4, answers_turn=None)
    reviewer = pb.reduce(
        run, "t04-manager",
        [_finding(run, f"{run.id}/t04-manager", _turn_answer("Numbers?", close="no"))],
        _NamedSite("local"),
    )[0]
    assert reviewer.json["answers_turn"] is None
    assert reviewer.json["delegated_by_turn"] is None

    # No revised copy here, so the re-check records an error rather than raising.
    s.update(current_role="junior_ic", current_turn=3, answers_turn=None,
             delegated_by_turn=2, pending_action="tighten")
    junior = pb.reduce(
        run, "t03-junior_ic",
        [_finding(run, f"{run.id}/t03-junior_ic", _turn_answer("Done.", close="no"))],
        _NamedSite("local"),
    )[0]
    assert junior.json["delegated_by_turn"] == 2
    assert junior.json["answers_turn"] is None


def test_a_cap_dropped_delegation_names_the_owner_turn_that_asked_for_it():
    _, _, capped, _, _, _ = _drive(
        {"t02-owner": {"delegate": True, "action": "too late"}}, max_turns=2
    )
    assert capped["dropped_delegation"] == "too late"
    assert capped["dropped_delegation_turn"] == 2

    pb = _committee()
    run = _run(phase="decision")
    pb._state(run).update(
        current_role="chair", dropped_delegation="too late", dropped_delegation_turn=2
    )
    red = pb.reduce(
        run, "decision", [_finding(run, f"{run.id}/decision", "Do not approve.")],
        _NamedSite("local"),
    )[0]
    assert red.json["dropped_delegation_turn"] == 2

    quiet = _committee()
    quiet_run = _run(phase="decision")
    quiet._state(quiet_run)["current_role"] = "chair"
    none = quiet.reduce(
        quiet_run, "decision",
        [_finding(quiet_run, f"{quiet_run.id}/decision", "Approve.")],
        _NamedSite("local"),
    )[0]
    assert "dropped_delegation_turn" in none.json
    assert none.json["dropped_delegation_turn"] is None


def test_the_decision_reduction_carries_the_ending_and_both_artifact_paths():
    """The view reads the ending off the decision, not off instance state."""
    pb = _committee()
    run = _run(phase="decision")
    s = pb._state(run)
    # `artifact_digest` is left empty, so `artifact_intact` folds to False here.
    # That is the subject of its own tests, not of this one.
    s.update(
        current_role="chair",
        ended="turn cap",
        artifact="/srv/proposals/migration.md",
        revised="/var/hermes/runs/r1/revised/migration.md",
    )

    red = pb.reduce(
        run, "decision", [_finding(run, f"{run.id}/decision", "Approve with changes.")],
        _NamedSite("local"),
    )[0]

    assert red.json["ended"] == "turn cap"
    assert red.json["artifact"] == "/srv/proposals/migration.md"
    assert red.json["revised"] == "/var/hermes/runs/r1/revised/migration.md"


def test_the_decision_reduction_always_names_an_ending():
    """A chair that delivered nothing IS the ending, whatever routed the run here."""
    pb = _committee()
    run = _run(phase="decision")
    pb._state(run).update(current_role="chair", ended="turn cap")

    failed = pb.reduce(run, "decision", [], _NamedSite("local"))[0]
    assert failed.json["delivered"] is False
    assert failed.json["ended"] == "chair turn failed"

    # A `decision` state that never went through next_phase -- only reachable by
    # seeding the phase directly -- still names an ending rather than None.
    fresh = _committee()
    fresh_run = _run(phase="decision")
    fresh._state(fresh_run)["current_role"] = "chair"
    fallback = fresh.reduce(
        fresh_run, "decision",
        [_finding(fresh_run, f"{fresh_run.id}/decision", "Approve.")],
        _NamedSite("local"),
    )[0]
    assert fallback.json["ended"] == "queue empty"


# --- retakes (voice D3) ------------------------------------------------------

def test_retakes_keep_every_invariant_and_consume_no_turns():
    """T11: a retake is the same turn said again, so the default run's NN
    sequence is unchanged and every model invariant still holds."""
    script = {
        "t02-owner": {"_retake": True},
        "t02-owner-take2": {"_retake": True},
        "t05-tpm": {"_retake": True},
    }
    _, _, s, seen, sp, ok = _drive(script)

    check_invariants(s, seen, sp, delivered=ok)
    assert seen[2:5] == ["t02-owner", "t02-owner-take2", "t02-owner-take3"]
    assert "t05-tpm-take2" in seen
    assert [p for p in seen if "-take" not in p] == _drive({})[3]
    assert s["turn"] == 15


def test_a_pending_retake_runs_before_a_pending_delegation_and_the_cap():
    pb = _committee()
    run = _run(phase="t30-owner")
    s = pb._state(run)
    s.update(current_role="owner", current_turn=30, turn=31, max_turns=30, opening=[],
             delegation="Cut the ask.", delegation_turn=30)
    pb._begin(s, "t30-owner")
    s["retake"] = "Retake 2 of 3."

    assert pb.next_phase(run) == "t30-owner-take2"
    assert s["delegation"] == "Cut the ask." and s["turn"] == 31
    run.phase = "t30-owner-take2"
    assert pb.next_phase(run) == "decision"  # the cap still drops the delegation
    assert s["dropped_delegation"] == "Cut the ask."

    early = _run(phase="t04-owner")
    early.id = "committee-early"
    e = pb._state(early)
    e.update(current_role="owner", current_turn=4, turn=5, opening=[],
             delegation="Cut the ask.", delegation_turn=4)
    pb._begin(e, "t04-owner")
    e["retake"] = "Retake 2 of 3."
    assert pb.next_phase(early) == "t04-owner-take2"
    early.phase = "t04-owner-take2"
    assert pb.next_phase(early) == "t05-junior_ic"  # the delegation follows


# 202 words and one bold span: over the cap and bold, for any speaker.
_WALL = "**Bold** claim. " + "word " * 200


def _speaking(pb, run, role, turn, *, base=None):
    """State for a speaking phase next_phase just minted: speaker, NN, take 1."""
    s = pb._state(run)
    s.update(current_role=role, current_turn=turn, opening=[], turn=turn + 1)
    pb._begin(s, base or f"t{turn:02d}-{role}")
    return s


def test_a_violating_take_is_discarded_and_retaken_under_the_same_turn():
    """T4: nothing of the discarded take reaches the room or moves a gate."""
    from playbooks.committee import thread

    pb = _committee()
    run = _run(phase="t02-owner")
    s = _speaking(pb, run, "owner", 2)
    answer = _turn_answer(_WALL, delegate="yes", action="Cut the staffing ask.", close="yes")

    red = pb.reduce(run, "t02-owner", [_finding(run, f"{run.id}/t02-owner", answer)],
                    _NamedSite("local"))

    assert [r.kind for r in red] == ["take"]
    doc = red[0].json
    assert (doc["phase"], doc["role"], doc["turn"], doc["take"]) == ("t02-owner", "owner", 2, 1)
    assert doc["kept"] is False and doc["delivered"] is True
    assert doc["violations"] == ["over_cap", "bold"]
    assert doc["voice"]["words"] == 202 and doc["action"] == "Cut the staffing ask."
    assert "needs_human_ticket_ids" not in doc
    assert not {"artifact", "revised", "cap"} & set(doc)
    assert not thread.path(run.id).exists()
    assert s["delegation"] is None and s["closed"] is False
    assert s["held"] == {"answer": answer, "take": 1}

    assert pb.next_phase(run) == "t02-owner-take2"
    assert (s["turn"], s["current_turn"], s["last_speaker"]) == (3, 2, "owner")
    assert s["note"] == (
        "Retake 2 of 3. Rules broken: 202 words (cap 150); 1 bold. Say it again within them."
    )


def test_a_discarded_reviewer_take_queues_no_floor_request():
    pb = _committee()
    run = _run(phase="t03-tl")
    s = _speaking(pb, run, "tl", 3)

    pb.reduce(run, "t03-tl",
              [_finding(run, f"{run.id}/t03-tl", _turn_answer(_WALL, request_floor="yes"))],
              _NamedSite("local"))

    assert s["queue"] == [] and s["last_speaker"] == "owner"


def test_discard_merges_a_later_loops_extra_keys():
    pb = _committee()
    run = _run(phase="s1-owner")
    s = _speaking(pb, run, "owner", 0, base="s1-owner")
    discard, metrics, violations, flags = pb._grade(run, s, "owner", _WALL)

    red = pb._discard(run, s, "owner", _WALL, metrics, violations, flags, None, extra={"stage": 1})

    assert discard is True and red[0].kind == "take"
    assert red[0].json["stage"] == 1 and red[0].json["turn"] is None
    assert red[0].json["phase"] == "s1-owner"


def test_retake_and_image_names_key_on_the_base_not_on_turn_and_role():
    pb = _committee()
    site = _NamedSite("local")
    names, goals = [], []
    for base in ("s1-owner", "o01-owner"):
        run = _run(phase=base)
        run.id = f"committee-{base}"
        s = _speaking(pb, run, "owner", 0, base=base)
        goals.append(pb.seed(run, site)[0].payload["goal"])
        s["retake"] = "Retake 2 of 3."
        names.append(pb.next_phase(run))

    assert names == ["s1-owner-take2", "o01-owner-take2"]
    assert "one image, s1-owner.svg or s1-owner.png" in goals[0]
    assert "one image, o01-owner.svg or o01-owner.png" in goals[1]


def test_grade_without_file_images_never_accepts_a_file():
    from playbooks.committee import thread

    pb = _committee()
    run = _run(phase="o01-owner")
    s = _speaking(pb, run, "owner", 0, base="o01-owner")
    (thread.images_dir(run.id) / "o01-owner.svg").write_bytes(b"<svg></svg>")
    answer = "Staffing is flat.\n![curve](images/o01-owner.svg)\nDescription: engineers per week."

    assert pb._grade(run, s, "owner", answer)[2] == []
    discard, metrics, violations, _ = pb._grade(run, s, "owner", answer, file_images=False)
    assert violations == ["image_missing"] and discard is True
    assert metrics["images"][0]["ok"] is False


def test_keep_regrades_a_held_take_with_the_callers_file_images():
    """A phase that grades with file_images=False keeps image_missing on the held take."""
    from playbooks.committee import thread

    pb = _committee()
    run = _run(phase="o01-owner-take2")
    s = _speaking(pb, run, "owner", 0, base="o01-owner")
    (thread.images_dir(run.id) / "o01-owner.svg").write_bytes(b"<svg></svg>")
    held = "Staffing is flat.\n![curve](images/o01-owner.svg)\nDescription: engineers per week."
    s.update(take=2, held={"answer": held, "take": 1})

    _, take, takes, metrics, violations, _ = pb._keep(
        run, s, "owner", "", None, [], [], file_images=False)

    assert (take, takes, violations) == (1, 2, ["image_missing", "retake_failed"])
    assert metrics["images"][0]["ok"] is False


def test_grading_a_file_image_never_makes_the_images_folder(tmp_path):
    """reduce only looks: an absent images folder is an image not ok, and stays absent."""
    pb = _committee()
    run = _run(phase="t02-owner")
    s = _speaking(pb, run, "owner", 2)
    answer = "Staffing is flat.\n![curve](images/t02-owner.svg)\nDescription: engineers per week."

    discard, metrics, violations, _ = pb._grade(run, s, "owner", answer)

    assert (discard, violations, metrics["images"][0]["ok"]) == (True, ["image_missing"], False)
    assert not (tmp_path / "runs" / run.id).exists()


def test_a_refused_images_folder_is_an_image_not_ok_and_never_raises(tmp_path):
    """A worker that plants images/ as a symlink gets no image through it, and
    reduce still returns: take 1 is sent back, take 3 is kept and flagged."""
    from playbooks.committee import thread

    pb = _committee()
    run = _run(phase="t02-owner")
    s = _speaking(pb, run, "owner", 2)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "t02-owner.svg").write_bytes(b"<svg></svg>")  # a valid file, behind the link
    (tmp_path / "runs" / run.id).mkdir(parents=True)
    (tmp_path / "runs" / run.id / "images").symlink_to(elsewhere, target_is_directory=True)
    answer = "Staffing is flat.\n![curve](images/t02-owner.svg)\nDescription: engineers per week."

    discard, metrics, violations, _ = pb._grade(run, s, "owner", answer)
    assert (discard, violations, metrics["images"][0]["ok"]) == (True, ["image_missing"], False)

    s["take"] = 3
    doc = pb.reduce(run, "t02-owner-take3", [_finding(run, f"{run.id}/t02-owner-take3", answer)],
                    _NamedSite("local"))[0]
    assert doc.kind == "turn" and doc.json["violations"] == ["image_missing"]
    assert doc.json["voice"]["images"][0]["ok"] is False
    assert "## turn 02" in thread.path(run.id).read_text()


def test_a_turn_seed_makes_the_images_folder_and_offers_no_image_through_a_refused_one(tmp_path):
    """A run opened before the images folder existed gets it (0700) from the
    turn that offers the image, not from a worker at 0755. A planted symlink
    makes seed offer no image instead of failing the run."""
    pb = _committee()
    site = _NamedSite("local")
    run = _run(phase="t02-owner")
    _speaking(pb, run, "owner", 2)
    folder = tmp_path / "runs" / run.id / "images"
    assert not folder.exists()

    offered = pb.seed(run, site)[0].payload["goal"]

    assert folder.is_dir() and (folder.stat().st_mode & 0o777) == 0o700
    assert "one image, t02-owner.svg or t02-owner.png" in offered

    planted = _run(phase="t03-tl")
    planted.id = "committee-planted"
    _speaking(pb, planted, "tl", 3)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (tmp_path / "runs" / planted.id).mkdir(parents=True)
    (tmp_path / "runs" / planted.id / "images").symlink_to(elsewhere, target_is_directory=True)

    refused = pb.seed(planted, site)[0].payload["goal"]

    assert "one image" not in refused and "write no file at all" in refused


def test_a_retake_ticket_names_its_take_and_carries_the_note():
    pb = _committee()
    run = _run(phase="t02-owner")
    s = _speaking(pb, run, "owner", 2)
    s["retake"] = "Retake 2 of 3. Your last take broke the ground rules: 1 bold."
    run.phase = pb.next_phase(run)

    ticket = pb.seed(run, _NamedSite("local"))[0]

    assert ticket.id == f"{run.id}/t02-owner-take2"
    assert ticket.payload["title"] == "turn 2 — Maya Okonkwo (owner) takes the floor (take 2)"
    assert "Retake 2 of 3. Your last take broke the ground rules: 1 bold." in ticket.payload["goal"]
    assert "one image, t02-owner.svg or t02-owner.png" in ticket.payload["goal"]
    assert set(ticket.payload) == {"role", "title", "goal", "kind", "action"}


def _meet(pb, run, answers, *, until):
    """The real loop, not the model: next_phase, seed, reduce, from `open` on.

    ``answers`` maps a phase to its worker's answer; every other phase answers
    a short compliant turn. Stops once ``until(phase)`` holds for a phase it
    just seeded, and returns every ticket seeded, by phase.
    """
    site = _NamedSite("local")
    pb.seed(run, site)
    seeded = {}
    while True:
        run.phase = pb.next_phase(run)
        seeded[run.phase] = ticket = pb.seed(run, site)[0]
        if until(run.phase):
            return seeded
        answer = answers.get(run.phase, _turn_answer(
            "Defer it: `engine/dispatch.py:284` drops the lease, e.g. at 3 s.", stance="defer"))
        pb.reduce(run, run.phase, [_finding(run, ticket.id, answer)], site)


@pytest.mark.parametrize("cap, after", [(2, "decision"), (30, "t03-")])
def test_the_speaker_after_a_kept_retake_gets_no_retake_note(artifact, monkeypatch, cap, after):
    """The cap routes the chair in after t02's retake (cap 2), or the next turn
    is minted (cap 30): either starts at take 1, with nothing of t02's note."""
    monkeypatch.setenv("HERMES_COMMITTEE_MAX_TURNS", str(cap))
    pb = _committee()
    run = _run()

    seeded = _meet(pb, run, {"t02-owner": _WALL}, until=lambda phase: phase.startswith(after))

    assert list(seeded)[1:3] == ["t02-owner", "t02-owner-take2"]
    assert "Retake 2 of 3" in seeded["t02-owner-take2"].payload["goal"]
    ticket = seeded[run.phase]
    assert "Retake" not in ticket.payload["goal"] and "(take" not in ticket.payload["title"]
    s = pb._state(run)
    assert (s["base"], s["take"]) == (run.phase, 1)


def test_a_fresh_process_after_a_discarded_take_leaves_the_thread_at_the_last_kept_turn():
    from playbooks.committee import thread

    pb = _committee()
    site = _NamedSite("local")
    run = _run(phase="t01-tl")
    _speaking(pb, run, "tl", 1)
    pb.reduce(run, "t01-tl", [_finding(run, f"{run.id}/t01-tl", "Defer it.")], site)
    _speaking(pb, run, "owner", 2)
    pb.reduce(run, "t02-owner", [_finding(run, f"{run.id}/t02-owner", _WALL)], site)

    fresh = _committee()
    run.phase = "t02-owner-take2"
    assert fresh.next_phase(run) is None
    assert fresh.reduce(run, "t02-owner-take2", [], site)[0].kind == "lost"
    text = thread.path(run.id).read_text()
    assert "## turn 01" in text and "## turn 02" not in text


def test_the_third_take_is_kept_verbatim_and_flagged():
    """T5: never clipped, recorded as the turn, with the rules it broke."""
    from playbooks.committee import thread, turnblock

    pb = _committee()
    run = _run(phase="t02-owner-take3")
    s = _speaking(pb, run, "owner", 2)
    s.update(take=3, held={"answer": "earlier", "take": 2}, retake=None)
    answer = _turn_answer(_WALL, close="no")

    doc = pb.reduce(run, "t02-owner-take3", [_finding(run, f"{run.id}/t02-owner-take3", answer)],
                    _NamedSite("local"))[0]

    assert doc.kind == "turn"
    assert (doc.json["take"], doc.json["takes"], doc.json["kept"]) == (3, 3, True)
    assert doc.json["violations"] == ["over_cap", "bold"]
    # the first sentence, "**Bold** claim.", is short: no long_first_line
    assert doc.json["flags"] == ["no_pointer", "no_example"]
    assert doc.json["body"] == turnblock.strip(answer)
    assert turnblock.strip(answer) in thread.path(run.id).read_text()
    assert s["held"] is None and s["retake"] is None


def test_a_kept_take_one_records_its_voice():
    pb = _committee()
    run = _run(phase="t03-staff_ic")
    _speaking(pb, run, "staff_ic", 3)
    answer = _turn_answer("Defer it: `engine/dispatch.py:284` drops the lease, e.g. at 3 s.",
                          stance="defer")

    doc = pb.reduce(run, "t03-staff_ic", [_finding(run, f"{run.id}/t03-staff_ic", answer)],
                    _NamedSite("local"))[0].json

    assert (doc["take"], doc["takes"], doc["kept"]) == (1, 1, True)
    assert doc["violations"] == [] and doc["flags"] == []
    assert doc["voice"]["pointers"] == 1 and doc["voice"]["stance_chars"] == 5


@pytest.mark.parametrize("retake", ["undelivered", "signals only"])
def test_a_retake_that_delivers_nothing_keeps_the_held_take(retake):
    from playbooks.committee import thread, turnblock

    pb = _committee()
    run = _run(phase="t02-owner-take2")
    s = _speaking(pb, run, "owner", 2)
    held = _turn_answer("Defer it: " + "word " * 160, close="no", stance="defer")
    s.update(take=2, held={"answer": held, "take": 1})
    findings = [] if retake == "undelivered" else [
        _finding(run, f"{run.id}/t02-owner-take2", _turn_answer("", close="no"))]

    doc = pb.reduce(run, "t02-owner-take2", findings, _NamedSite("local"))[0].json

    assert (doc["take"], doc["takes"]) == (1, 2)
    assert doc["violations"] == ["over_cap", "retake_failed"]
    assert doc["voice"]["words"] == 162 and doc["voice"]["stance_chars"] == 5  # re-graded
    assert doc["delivered"] is True and doc["body"] == turnblock.strip(held)
    assert thread.path(run.id).read_text().count("## turn 02") == 1
    assert s["held"] is None


def test_an_undelivered_take_one_is_kept_with_no_voice():
    pb = _committee()
    run = _run(phase="t03-tl")
    _speaking(pb, run, "tl", 3)

    doc = pb.reduce(run, "t03-tl", [], _NamedSite("local"))[0].json

    assert doc["delivered"] is False and doc["voice"] is None
    assert (doc["take"], doc["takes"], doc["violations"], doc["flags"]) == (1, 1, [], [])


def test_a_chair_retake_keeps_every_invariant():
    _, _, s, seen, sp, ok = _drive({"decision": {"_retake": True}, "decision-take2": {"_retake": True}})

    check_invariants(s, seen, sp, delivered=ok)
    assert seen[-3:] == ["decision", "decision-take2", "decision-take3"]


# The chair: 400 words under a `## Ruling` header, 402 by the count. Over the
# chair's cap of 300.
_CHAIR_WALL = "## Ruling\n\n" + "word " * 400


def _chairing(pb, run):
    s = pb._state(run)
    s["opening"] = []
    pb._decision(s, "queue empty")
    return s


def test_a_chair_take_over_the_cap_is_discarded_and_decision_take2_is_kept():
    """T6: only the kept verdict is written and held, under its own phase."""
    from playbooks.committee import thread

    pb = _committee()
    site = _NamedSite("local")
    run = _run(phase="decision")
    _chairing(pb, run)

    red = pb.reduce(run, "decision", [_finding(run, f"{run.id}/decision", _CHAIR_WALL)], site)

    assert red[0].kind == "take" and red[0].json["turn"] is None
    assert red[0].json["violations"] == ["over_cap", "headers"]
    assert "needs_human_ticket_ids" not in red[0].json
    assert not thread.path(run.id).exists()
    assert pb.next_phase(run) == "decision-take2"

    run.phase = "decision-take2"
    ticket = pb.seed(run, site)[0]
    assert ticket.id == f"{run.id}/decision-take2" and ticket.payload["kind"] == "decision"
    assert ticket.payload["title"].endswith("delivers the committee decision (take 2)")
    assert (
        "Retake 2 of 3. Rules broken: 402 words (cap 300); 1 headers. Say it again within them."
        in ticket.payload["goal"]
    )

    prose = "Approve with changes: land the rollback plan first."
    kept = pb.reduce(run, "decision-take2", [_finding(run, ticket.id, prose)], site)[0]
    assert kept.kind == "decision"
    assert kept.json["needs_human_ticket_ids"] == [f"{run.id}/decision-take2"]
    assert (kept.json["take"], kept.json["takes"], kept.json["body"]) == (2, 2, prose)
    assert kept.json["voice"]["words"] == 8 and kept.json["violations"] == []
    assert thread.path(run.id).read_text().count("## decision") == 1
    assert pb.next_phase(run) == "ruling"
    ruled = _run(phase="ruling", reductions=[
        Reduction(kind="decision", json=kept.json, review_state="accepted")])
    assert pb.is_done(ruled) is True


def test_a_failed_chair_retake_records_the_held_prose_unruled_and_the_run_fails():
    from playbooks.committee import thread, turnblock
    from playbooks.committee.playbook import _SIMULATION

    pb = _committee()
    run = _run(phase="decision-take2")
    s = _chairing(pb, run)
    s.update(take=2, held={"answer": _CHAIR_WALL, "take": 1})

    doc = pb.reduce(run, "decision-take2", [], _NamedSite("local"))[0].json

    assert doc["delivered"] is False and doc["ended"] == "chair retake failed"
    assert doc["needs_human_ticket_ids"] == []
    assert doc["body"] == turnblock.strip(_CHAIR_WALL)
    assert doc["verdict"].startswith("## Ruling") and _SIMULATION in doc["verdict"]
    assert doc["violations"] == ["over_cap", "headers", "retake_failed"]
    assert (doc["take"], doc["takes"]) == (1, 2)
    assert "## decision" in thread.path(run.id).read_text()
    ruled = _run(phase="ruling", reductions=[
        Reduction(kind="decision", json=doc, review_state="pending")])
    assert pb.is_done(ruled) is False


def test_a_fresh_process_after_a_discarded_chair_take_goes_to_ruling_and_fails():
    pb = _committee()
    run = _run(phase="decision")
    _chairing(pb, run)
    take = pb.reduce(run, "decision", [_finding(run, f"{run.id}/decision", _CHAIR_WALL)],
                     _NamedSite("local"))[0]

    fresh = _committee()
    assert fresh.next_phase(run) == "ruling"
    assert fresh._state_by_run == {}  # a read, not a state it grows
    assert fresh.is_done(_run(phase="ruling", reductions=[take])) is False


def test_a_verdict_is_graded_against_the_chairs_own_cap():
    """200 words: over a reviewer's 150, within the chair's 300, so take 1 is kept."""
    pb = _committee()
    run = _run(phase="decision")
    _chairing(pb, run)
    verdict = "Approve with changes. " + "word " * 197

    doc = pb.reduce(run, "decision", [_finding(run, f"{run.id}/decision", verdict)],
                    _NamedSite("local"))[0]

    assert doc.kind == "decision" and doc.json["voice"]["words"] == 200
    assert doc.json["violations"] == []


def _junior_take_one_discarded(pb, run, tmp_path):
    """A junior take 1 that edited the copy and then broke the one-sentence rule."""
    from playbooks.committee import thread

    copy = _junior_turn(pb, run, tmp_path)
    s = pb._state(run)
    pb._begin(s, "t05-junior_ic")
    copy.write_text("the original proposal\nand a rollback paragraph\n")
    red = pb.reduce(run, "t05-junior_ic", [_finding(
        run, f"{run.id}/t05-junior_ic", "I added the rollback paragraph. It names the owner.",
    )], _NamedSite("local"))
    assert red[0].kind == "take" and red[0].json["violations"] == ["multi_sentence"]
    assert s["edit_digest"] == thread.digest(copy)
    return copy, s


def test_a_discarded_junior_take_is_retaken_report_only(tmp_path):
    """T7: the retake edits nothing, and the kept report still verifies take 1's edit."""
    pb = _committee()
    site = _NamedSite("local")
    run = _run(phase="t05-junior_ic")
    copy, s = _junior_take_one_discarded(pb, run, tmp_path)
    before = s["pre_edit_digest"]

    assert pb.next_phase(run) == "t05-junior_ic-take2"
    run.phase = "t05-junior_ic-take2"
    ticket = pb.seed(run, site)[0]
    assert ticket.payload["kind"] == "edit"
    assert ticket.payload["action"] == "add a rollback paragraph"
    assert s["pre_edit_digest"] == before  # no re-snapshot on a retake
    assert "write no file at all" in ticket.payload["goal"].lower()
    assert "Do not edit the revised copy again" in ticket.payload["goal"]

    kept = pb.reduce(run, "t05-junior_ic-take2", [_finding(
        run, ticket.id, "I added the rollback paragraph.")], site)[0]
    assert kept.kind == "turn" and kept.json["verified"] is True
    assert kept.json["error"] is None and (kept.json["take"], kept.json["takes"]) == (2, 2)
    assert (tmp_path / "runs" / run.id / "doc" / "t05.md").read_bytes() == copy.read_bytes()


def test_a_junior_retake_that_edits_the_copy_records_the_error(tmp_path):
    pb = _committee()
    run = _run(phase="t05-junior_ic")
    copy, s = _junior_take_one_discarded(pb, run, tmp_path)
    run.phase = pb.next_phase(run)
    copy.write_text("the original proposal\nand a rollback paragraph\nand another edit\n")

    kept = pb.reduce(run, run.phase, [_finding(
        run, f"{run.id}/{run.phase}", "I added the rollback paragraph.")], _NamedSite("local"))[0]

    assert kept.json["error"] == "retake modified the revised copy"
    assert kept.json["verified"] is True


def test_a_junior_retake_that_writes_a_copy_take_one_removed_records_the_error(tmp_path):
    """Take 1 left no regular copy, so there is no digest to compare; a
    report-only retake that writes one anyway is still caught."""
    pb = _committee()
    site = _NamedSite("local")
    run = _run(phase="t05-junior_ic")
    copy = _junior_turn(pb, run, tmp_path)
    pb._begin(pb._state(run), "t05-junior_ic")
    copy.unlink()
    pb.reduce(run, "t05-junior_ic", [_finding(
        run, f"{run.id}/t05-junior_ic", "The copy was gone. I wrote nothing.")], site)
    run.phase = pb.next_phase(run)
    pb.seed(run, site)
    assert not copy.exists()  # a retake never re-copies the file
    copy.write_text("a copy the retake wrote\n")

    kept = pb.reduce(run, run.phase, [_finding(
        run, f"{run.id}/{run.phase}", "My first take changed nothing.")], site)[0]

    assert kept.json["error"] == "retake modified the revised copy"


def test_a_junior_take_two_that_edits_and_is_sent_back_is_still_caught_at_take_three(tmp_path):
    """The copy's digest is take 1's: a discarded take 2 that edited does not move it."""
    pb = _committee()
    site = _NamedSite("local")
    run = _run(phase="t05-junior_ic")
    copy, _ = _junior_take_one_discarded(pb, run, tmp_path)
    run.phase = pb.next_phase(run)
    copy.write_text(copy.read_text() + "and a second edit\n")
    sent_back = pb.reduce(run, run.phase, [_finding(
        run, f"{run.id}/{run.phase}", "I added it. Then I added more.")], site)[0]
    assert sent_back.kind == "take"
    run.phase = pb.next_phase(run)
    assert run.phase == "t05-junior_ic-take3"

    kept = pb.reduce(run, run.phase, [_finding(
        run, f"{run.id}/{run.phase}", "I added the rollback paragraph.")], site)[0]

    assert kept.json["take"] == 3
    assert kept.json["error"] == "retake modified the revised copy"


def test_a_junior_retake_that_edits_then_delivers_nothing_keeps_take_one_and_the_error(tmp_path):
    """Dispatched takes count, not the kept one: take 1 is kept, take 2's edit is named."""
    pb = _committee()
    run = _run(phase="t05-junior_ic")
    copy, _ = _junior_take_one_discarded(pb, run, tmp_path)
    run.phase = pb.next_phase(run)
    copy.write_text(copy.read_text() + "and another edit\n")

    kept = pb.reduce(run, run.phase, [], _NamedSite("local"))[0].json

    assert (kept["take"], kept["takes"]) == (1, 2)
    assert kept["violations"] == ["multi_sentence", "retake_failed"]
    assert kept["error"] == "retake modified the revised copy"


def test_a_later_junior_turn_starts_clean_after_an_earlier_retake(tmp_path):
    from playbooks.committee import thread

    pb = _committee()
    site = _NamedSite("local")
    run = _run(phase="t05-junior_ic")
    copy, s = _junior_take_one_discarded(pb, run, tmp_path)
    run.phase = pb.next_phase(run)
    pb.reduce(run, run.phase, [_finding(run, f"{run.id}/{run.phase}", "Done.")], site)

    s.update(current_turn=7)
    pb._begin(s, "t07-junior_ic")
    s["pre_edit_digest"] = thread.digest(copy)
    copy.write_text(copy.read_text() + "and a second delegated edit\n")
    kept = pb.reduce(run, "t07-junior_ic", [_finding(
        run, f"{run.id}/t07-junior_ic", "I added the second edit.")], site)[0]

    assert kept.json["error"] is None and kept.json["verified"] is True
    assert kept.json["take"] == 1


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


def test_registration_phases_are_open_decision_ruling():
    """phases[0] is the phase the CLI seeds (engine/cli.py:385)."""
    import playbooks.committee  # noqa: F401

    from engine import playbook as _playbook

    pb = _playbook.load("committee")
    assert pb.phases == ["open", "decision", "ruling"]
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
assert pb.phases == ["open", "decision", "ruling"], pb.phases
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
    """Acceptance criterion 13, as far as a grep can prove it: no .py/.sql/.ts/.tsx
    PRODUCTION file under engine/, server/ or web/src names the committee.

    Web test files are exempt, and deliberately. The playbook-view seam is
    generic -- `view_asset`/`view_data`, `window.HermesView_{name}`, one tab
    driven by `has_view` -- and the way you prove a generic seam works is to
    stand a concrete playbook in it. `web/src/ds/playbook-view-load.test.tsx`
    loads the committee's own built bundle, `web/src/views/CommitteeView.test.tsx`
    renders the committee's own component, and the App and client fixtures set
    `playbook: 'committee'`. None of that is wiring: delete every one of those
    files and the control plane behaves identically. The production halves --
    `PlaybookView.tsx`, `TopBar.tsx`, `App.tsx`, `server/app.py` -- still may not
    name it, and this test still says so.

    Not the whole criterion -- an unrelated engine edit would pass this -- but it
    is the half that a wrong fix actually trips. Dexter and research are wired by
    a hardcoded import in _load_playbook_site_agent (engine/cli.py:211-212);
    committee is deliberately NOT, because that is an engine edit. This fails the
    moment someone "fixes" the wiring that way. `git diff main..HEAD -- engine/
    server/ web/` is the assertion for the rest.
    """
    from pathlib import Path

    workspace = Path(__file__).parent.parent.parent

    candidates = [
        p for tree in ("engine", "server", "web/src")
        for p in sorted((workspace / tree).rglob("*"))
    ]
    # web/ ROOT as well, non-recursively: the config files there are not `src`,
    # and that is exactly where committee-specific wiring hid from this guard.
    candidates += sorted(p for p in (workspace / "web").glob("*"))

    hits = []
    for path in candidates:
        if not path.is_file() or path.suffix not in (".py", ".sql", ".ts", ".tsx"):
            continue
        if path.name.endswith((".test.ts", ".test.tsx")):
            continue
        # The one knowing exception, and the whole reason the scan was widened
        # to see it at all: this config hardcodes the global name, the entry and
        # the outDir. Spec §2 defers a second playbook view, and a build needs
        # somewhere concrete to point until there is one. When the second view
        # arrives this becomes a loop over a registry and the exemption goes.
        if path.name == "vite.playbook-view.config.ts":
            continue
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        if "committee" in text:
            hits.append(str(path.relative_to(workspace)))

    assert hits == [], f"committee is named inside engine/server/web: {hits}"
