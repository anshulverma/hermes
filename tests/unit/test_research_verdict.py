"""Tests for the research playbook's machine-readable verdict.

TDD: written FIRST, watched fail, then playbooks/research/verdict.py implemented.

The transport hands the master one thing: the agent's final prose under
``answer``. So a verdict has to travel inside that prose, in a form that cannot
be confused with it. Scraping words does not work -- in real syntheses
"blocking" and "clean" occur as ordinary adjectives ("the blocking window is
bounded by a lease", "not a clean kill"), and of ten apparent verdict words only
two were verdicts. A fenced block with its own tag is unambiguous, and its
absence is unambiguous too.
"""
from __future__ import annotations

import pytest

from playbooks.research import verdict as V


def _fenced(body: str) -> str:
    return f"Some prose.\n\n```{V.FENCE_TAG}\n{body}\n```\n"


# --- parsing -------------------------------------------------------------

def test_a_fenced_verdict_block_is_parsed():
    answer = _fenced('{"verdict": "blocking", "headline": "Tier leaks per launch"}')

    v = V.parse(answer)

    assert v == {"verdict": "blocking", "headline": "Tier leaks per launch"}


def test_the_vocabulary_is_closed():
    """An agent inventing its own word must not become a colour nobody defined."""
    assert V.parse(_fenced('{"verdict": "catastrophic"}')) is None


@pytest.mark.parametrize("word", ["blocking", "needs-discussion", "clean"])
def test_every_defined_verdict_parses(word):
    assert V.parse(_fenced('{"verdict": "%s"}' % word))["verdict"] == word


def test_a_verdict_is_case_and_space_insensitive():
    assert V.parse(_fenced('{"verdict": " Needs-Discussion "}'))["verdict"] == "needs-discussion"


def test_no_block_is_no_verdict_rather_than_a_guess():
    # 7 of 17 real syntheses carry no verdict. That has to stay visible as
    # "unstated" rather than being inferred into a colour.
    assert V.parse("The blocking window is bounded by a 90-minute lease.") is None
    assert V.parse("This is not a clean kill.") is None
    assert V.parse("") is None
    assert V.parse(None) is None


def test_a_malformed_block_is_no_verdict():
    assert V.parse(_fenced("{not json}")) is None
    assert V.parse(_fenced("[]")) is None


def test_the_last_block_wins_when_an_agent_emits_two():
    """An agent that restates its verdict has settled on the later one."""
    answer = _fenced('{"verdict": "clean"}') + _fenced('{"verdict": "blocking"}')

    assert V.parse(answer)["verdict"] == "blocking"


def test_a_headline_is_carried_and_capped():
    v = V.parse(_fenced('{"verdict": "clean", "headline": "%s"}' % ("x" * 500)))

    assert len(v["headline"]) <= V.HEADLINE_MAX


def test_unknown_keys_are_dropped_not_carried():
    v = V.parse(_fenced('{"verdict": "clean", "mood": "cheerful"}'))

    assert "mood" not in v


def test_a_non_string_headline_is_ignored_not_rendered():
    v = V.parse(_fenced('{"verdict": "clean", "headline": {"a": 1}}'))

    assert "headline" not in v


# --- stripping -----------------------------------------------------------

def test_the_block_is_removed_from_the_prose_it_travelled_in():
    """The verdict is rendered as a pill; leaving the raw JSON in the prose
    shows the reader plumbing."""
    answer = _fenced('{"verdict": "clean"}')

    stripped = V.strip(answer)

    assert "Some prose." in stripped
    assert V.FENCE_TAG not in stripped
    assert "verdict" not in stripped


def test_stripping_prose_with_no_block_changes_nothing():
    assert V.strip("just prose") == "just prose"


def test_stripping_tolerates_no_input():
    assert V.strip(None) == ""


def test_an_ordinary_code_block_survives_stripping():
    answer = "Look:\n\n```python\nprint('hi')\n```\n"

    assert "print('hi')" in V.strip(answer)


# --- the instruction handed to the agent ---------------------------------

def test_the_instruction_names_the_tag_and_every_verdict():
    text = V.instruction()

    assert V.FENCE_TAG in text
    for word in V.VERDICTS:
        assert word in text


def test_the_instruction_is_small_enough_to_carry():
    """It rides in every goal, which is capped at 4000 characters."""
    assert len(V.instruction()) < 400


def test_what_the_instruction_asks_for_is_what_parse_accepts():
    """The contract has to be self-consistent: an agent that follows the
    instruction literally must produce something parse() accepts."""
    import re

    m = re.search(r"```" + V.FENCE_TAG + r"\n(.*?)\n```", V.instruction(), re.S)
    assert m, "the instruction must contain a worked example"
    assert V.parse(f"prose\n\n```{V.FENCE_TAG}\n{m.group(1)}\n```\n") is not None
