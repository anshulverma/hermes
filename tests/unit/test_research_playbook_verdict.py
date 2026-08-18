"""The research playbook carrying verdicts end to end.

TDD: written FIRST. Covers asking for the verdict in the goal, parsing it out of
the answer at reduce time, and keeping the prose free of the plumbing it rode in.
"""
from __future__ import annotations

import json

import pytest

from engine.models import Finding, Run
from playbooks.research import verdict as V
from playbooks.research.playbook import ResearchPlaybook


def _run(**config) -> Run:
    return Run(
        id="r-verdict", playbook="research", site="local", base_ref="main",
        config=config, phase="research", reductions=[],
    )


def _answer(text: str, word: str | None = None, headline: str | None = None) -> str:
    if word is None:
        return text
    doc = {"verdict": word}
    if headline:
        doc["headline"] = headline
    return f"{text}\n\n```{V.FENCE_TAG}\n{json.dumps(doc)}\n```\n"


@pytest.fixture
def pb():
    return ResearchPlaybook()


# --- the ask -------------------------------------------------------------

def test_the_analysis_goal_asks_for_a_verdict(pb):
    from playbooks.research.playbook import _research_goal

    goal = _research_goal({"id": "ITEM-1", "context": "material"})

    assert V.FENCE_TAG in goal
    assert "blocking" in goal


def test_the_merge_goal_asks_for_a_verdict(pb):
    from playbooks.research.playbook import _synthesize_goal

    goal = _synthesize_goal(
        {"id": "ITEM-1", "context": "material"},
        [{"agent": "claude", "analysis": "found nothing"}],
        [],
    )

    assert V.FENCE_TAG in goal


def test_the_report_goal_does_not_ask_for_one(pb):
    """A report is about a batch; a single verdict over seventeen items would
    average away exactly the thing a reader needs."""
    from playbooks.research.playbook import _report_goal

    goal = _report_goal([{"item_id": "ITEM-1", "synthesis": "text"}])

    assert V.FENCE_TAG not in goal


# --- carrying it through reduce ------------------------------------------

def test_a_synthesis_carries_its_verdict_into_the_reduction(pb, tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    findings = [Finding(run_id="r-verdict", ticket_id="r-verdict/synthesize-ITEM-1",
        kind="result", json={"answer": _answer("merged account", "blocking", "Tier leaks")},
    )]

    [reduction] = pb.reduce(_run(), "synthesize", findings, site=None)

    entry = reduction.json["syntheses"][0]
    assert entry["verdict"] == "blocking"
    assert entry["headline"] == "Tier leaks"


def test_a_synthesis_without_a_verdict_records_none_rather_than_guessing(
    pb, tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    prose = "The blocking window is bounded by a 90-minute lease; not a clean kill."
    findings = [Finding(run_id="r-verdict", ticket_id="r-verdict/synthesize-ITEM-1",
        kind="result", json={"answer": prose},
    )]

    [reduction] = pb.reduce(_run(), "synthesize", findings, site=None)

    assert reduction.json["syntheses"][0]["verdict"] is None


def test_the_prose_keeps_the_account_and_loses_the_block(pb, tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    findings = [Finding(run_id="r-verdict", ticket_id="r-verdict/synthesize-ITEM-1",
        kind="result", json={"answer": _answer("the merged account", "clean")},
    )]

    [reduction] = pb.reduce(_run(), "synthesize", findings, site=None)

    text = reduction.json["syntheses"][0]["synthesis"]
    assert "the merged account" in text
    assert V.FENCE_TAG not in text


def test_the_reduction_counts_the_verdicts_it_holds(pb, tmp_path, monkeypatch):
    """The point of the exercise: a reader sees the shape of the batch without
    opening seventeen write-ups."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    findings = [
        Finding(run_id="r-verdict", ticket_id=f"r-verdict/synthesize-ITEM-{i}",
                kind="result", json={"answer": _answer("x", word)})
        for i, word in enumerate(["blocking", "clean", "clean", None], start=1)
    ]

    [reduction] = pb.reduce(_run(), "synthesize", findings, site=None)

    assert reduction.json["verdict_counts"] == {
        "blocking": 1, "needs-discussion": 0, "clean": 2, "unstated": 1,
    }


def test_an_analysis_carries_its_verdict_too(pb, tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_RESEARCH_AGENTS", "claude")
    findings = [Finding(run_id="r-verdict", ticket_id="r-verdict/research-ITEM-1-claude",
        kind="result", json={"answer": _answer("analysis body", "needs-discussion")},
    )]

    reductions = pb.reduce(_run(), "research", findings, site=None)

    analyses = reductions[0].json["analyses"]
    assert analyses[0]["verdict"] == "needs-discussion"
    assert V.FENCE_TAG not in analyses[0]["analysis"]


def test_verify_still_passes_on_an_answer_that_is_only_a_verdict_block(pb):
    """Stripping must not turn a thin-but-valid answer into an empty one at the
    gate: verify reads the raw answer, which is non-empty."""
    result = type("R", (), {"payload": {"answer": _answer("", "clean")}})()

    assert pb.verify(_run(), None, result, None) is True
