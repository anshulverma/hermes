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
