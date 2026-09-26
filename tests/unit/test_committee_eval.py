"""Tests for committee-eval (playbooks/committee/eval.py) and its voice seam.

TDD: written FIRST, watched fail, then the module implemented.

The eval scores one finished committee run on six dimensions, and every number
it reports has to come from the record or from a quote the master verified. So
these tests pin each rule on fixed inputs and, from the fixtures on, on two real
runs frozen under tests/data/committee-eval/. No test reads ~/.hermes, /data or
the repo's docs/.
"""
from __future__ import annotations

import hashlib
import json
import re

from playbooks.committee import eval as E
from playbooks.committee import voice

MEASURE_KEYS = {"words", "pointers", "examples", "longest_paragraph_words", "filler_hits"}


def _w(k: int) -> str:
    return " ".join(["w"] * k)


def test_voice_measure_and_version():
    """T17: voice.measure and the C8 shares on fixed inputs; a rules change moves concision's version, and only it."""
    # Every key, all ints; empty and non-str input count as "" and never raise.
    empty = dict.fromkeys(MEASURE_KEYS, 0)
    assert voice.measure("") == empty
    for junk in (None, 42, b"a b", ["a b"]):
        assert voice.measure(junk) == empty
    m = voice.measure("a b  c\n\nd", role="owner")
    assert set(m) == MEASURE_KEYS and all(type(v) is int for v in m.values())
    assert m["words"] == 4 and E.words("a b  c\n\nd") == 4

    # A paragraph is a maximal run of non-blank lines; a wall is more than 120 words.
    assert voice.WALL_WORDS == 120
    assert voice.measure(_w(120))["longest_paragraph_words"] == 120
    assert voice.measure(_w(60) + "\n" + _w(61))["longest_paragraph_words"] == 121
    assert voice.measure(_w(100) + "\n  \n" + _w(21))["longest_paragraph_words"] == 100

    # Pointers: a path:line (with a range) and a section, in both spellings.
    assert voice.measure("See playbooks/committee/eval.py:12-14, §3.2 and Section 5.1.")["pointers"] == 3
    assert voice.measure("file.py:12-14")["pointers"] == 1
    assert voice.measure("§3.2")["pointers"] == 1
    assert voice.measure("line 12 of the file")["pointers"] == 0

    # Examples: 2 phrases + 1 inline span (the one inside the fence is not counted)
    # + 1 fenced block + 1 number with a unit.
    ex = voice.measure(
        "For example, e.g. the `retry` flag cuts p99 by 200 ms.\n"
        "\n"
        "```python\n"
        "call(`inside`)\n"
        "```\n"
    )
    assert ex["examples"] == 5
    assert voice.measure("Plain words only.")["examples"] == 0

    # Filler: C8's 15 phrases in order, each a case-insensitive substring.
    assert voice.FILLER == (
        "great question", "it's worth noting", "it is worth noting", "to be clear",
        "let me be clear", "i want to be clear", "at the end of the day", "that said",
        "happy to", "i'd be happy", "in summary", "to summarize", "hope this helps",
        "let's dive", "delve",
    )
    filler = voice.measure("Great question. That said, I delved in; to be clear, I'd be happy to help.")
    # great question, that said, delve (inside "delved"), to be clear, i'd be happy, happy to
    assert filler["filler_hits"] == 6

    # RULES: one line per element, no bold, no long dashes, no heading.
    assert voice.RULES and isinstance(voice.RULES, tuple)
    for rule in voice.RULES:
        assert isinstance(rule, str) and rule.strip()
        assert "**" not in rule and "\u2013" not in rule and "\u2014" not in rule
        assert "\n" not in rule and not rule.startswith("#")

    # The C8 shares over fixed rows, and over nothing.
    rows = [
        {"words": 9, "pointers": 1, "examples": 0, "longest_paragraph_words": 121, "filler_hits": 2},
        {"words": 9, "pointers": 0, "examples": 3, "longest_paragraph_words": 120, "filler_hits": 1},
        {"words": 9, "pointers": 2, "examples": 1, "longest_paragraph_words": 5, "filler_hits": 0},
    ]
    assert E.voice_shares(rows) == {
        "n": 3, "pointer_share": 0.6667, "walls_share": 0.3333,
        "example_share": 0.6667, "filler_per_turn": 1.0,
    }
    assert E.voice_shares([]) == {
        "n": 0, "pointer_share": None, "walls_share": None,
        "example_share": None, "filler_per_turn": None,
    }
    assert E.voice_shares([{}, {"pointers": "2", "filler_hits": None}]) == {
        "n": 2, "pointer_share": 0.0, "walls_share": 0.0,
        "example_share": 0.0, "filler_per_turn": 0.0,
    }
    assert E.voice_shares([voice.measure(_w(121)), voice.measure(_w(120))])["walls_share"] == 0.5

    # The rubric's identity: six dimensions in D5 order, all @1, and the judge anchors.
    assert tuple(E.DIMENSIONS) == E.JUDGE_DIMS + E.DETERMINISTIC_DIMS == (
        "verdict_grounded", "edits_address_concerns", "concern_coverage",
        "efficiency", "concision", "verdict_consistency",
    )
    assert all(v == f"{k}@1" for k, v in E.DIMENSIONS.items())
    assert (E.MIN_ANCHORS, E.QUOTE_MAX, E.EVIDENCE_MAX, E.FENCE_TAG) == (2, 300, 5, "hermes-eval")
    assert E.VERBATIM in E.RUBRIC and all(d in E.RUBRIC for d in E.JUDGE_DIMS)

    # A rules swap moves concision's version and the rubric version, and nothing else.
    now = E.dimension_versions()
    digest = hashlib.sha256("\n".join(voice.RULES).encode()).hexdigest()[:8]
    assert now == {**E.DIMENSIONS, "concision": "concision@1+" + digest}
    assert E.DIMENSIONS["concision"] == "concision@1"
    swapped = E.dimension_versions(voice.RULES + ("Say it in one line.",))
    assert swapped["concision"] != now["concision"]
    assert {k: v for k, v in swapped.items() if k != "concision"} == {
        k: v for k, v in now.items() if k != "concision"
    }
    assert E.rubric_version(now) == "r" + hashlib.sha256(
        json.dumps(now, sort_keys=True).encode()
    ).hexdigest()[:8]
    assert re.fullmatch(r"r[0-9a-f]{8}", E.rubric_version(now))
    assert E.rubric_version(swapped) != E.rubric_version(now)
