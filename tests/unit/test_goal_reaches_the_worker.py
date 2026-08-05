"""The material a goal refers to must actually reach the worker process.

This is the assertion whose absence let a regression ship. Every other test
stopped at the payload -- asserting the context was *in the ticket*, which was
true and worthless, because nothing carries the payload to the process. The
prompt is built from ``goal_envelope.goal`` and the driver, and that is the
whole channel.

So these tests go all the way: seed through the real playbook, build the real
dispatch envelope, and ask the real agent adapters what argv they would exec.
A marker planted in the source material has to survive to the command line.
"""
import os

import pytest

from engine import transport
from engine.models import Run

MARKER = "ZZ-marker-only-in-the-source-material-ZZ"


class _StubSite:
    """The minimum `_build_envelope` needs: a site that can promise no-ship."""

    def guarantees_no_ship(self) -> bool:
        return True

    def context(self, host: str) -> dict:
        return {}


@pytest.fixture(autouse=True)
def _home(monkeypatch, tmp_path):
    """Keep the per-run sidecar out of the real HERMES_HOME."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    for var in ("HERMES_RESEARCH_SOURCE", "HERMES_RESEARCH_AGENTS", "HERMES_RESEARCH_LIMIT"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def source(request):
    from playbooks.research import sources

    items: list[dict] = []
    name = f"boundary-source-{request.node.name}"
    sources.register(name, lambda config: list(items))
    return name, items


def _playbook():
    from playbooks.research.playbook import ResearchPlaybook

    return ResearchPlaybook()


def _run(config, phase="research", reductions=None, run_id="run-boundary"):
    return Run(
        id=run_id,
        playbook="research",
        site="fan-claude",
        base_ref="main",
        config=config,
        phase=phase,
        reductions=reductions or [],
    )


def _argv_for(ticket, run, playbook, agent):
    """The argv the agent would actually exec for this ticket."""
    envelope = transport._build_envelope(
        ticket, run, playbook, "main", _StubSite(), "localhost"
    )
    driver = transport._driver_from_envelope(envelope)
    return " ".join(agent.build_invocation(envelope, driver))


def _agents():
    from agents.claude.agent import ClaudeAgent
    from agents.codex.agent import CodexAgent

    return [("claude", ClaudeAgent()), ("codex", CodexAgent())]


@pytest.mark.parametrize("agent_name", ["claude", "codex"])
def test_research_material_reaches_the_command_line(source, agent_name):
    """The item's context must be in what the process is invoked with."""
    name, items = source
    items.append({"id": "item-1", "title": "One", "context": f"Summary: {MARKER}"})
    pb = _playbook()
    run = _run({"source": name, "agents": ["claude"]})
    ticket = pb.seed(run, site=None)[0]

    agent = dict(_agents())[agent_name]
    argv = _argv_for(ticket, run, pb, agent)

    assert MARKER in argv, (
        "the goal points at material the worker never receives: the payload does "
        "not travel, only the goal string does"
    )


def test_synthesize_material_reaches_the_command_line(source):
    """The analyses being merged must reach the merging worker."""
    from engine.models import Reduction
    from agents.claude.agent import ClaudeAgent

    name, items = source
    items.append({"id": "item-1", "title": "One", "context": "ctx"})
    pb = _playbook()
    config = {"source": name, "agents": ["claude"]}
    reductions = [Reduction(kind="item_analyses", json={
        "item": {"id": "item-1", "title": "One", "context": "ctx"},
        "analyses": [{"agent": "claude", "analysis": f"finding: {MARKER}"}],
        "succeeded_agents": ["claude"],
        "failed_agents": [],
        "status": "ok",
    })]
    run = _run(config, phase="synthesize", reductions=reductions)
    ticket = pb.seed(run, site=None)[0]

    assert MARKER in _argv_for(ticket, run, pb, ClaudeAgent())


def test_report_material_reaches_the_command_line(source):
    """The syntheses being written up must reach the reporting worker."""
    from engine.models import Reduction
    from agents.claude.agent import ClaudeAgent

    name, items = source
    items.append({"id": "item-1", "title": "One", "context": "ctx"})
    pb = _playbook()
    config = {"source": name, "agents": ["claude"]}
    reductions = [Reduction(kind="item_syntheses", json={
        "syntheses": [
            {"ticket_id": "t", "item_id": "item-1", "synthesis": f"merged: {MARKER}"}
        ],
        "item_count": 1,
    })]
    run = _run(config, phase="report", reductions=reductions)
    ticket = pb.seed(run, site=None)[0]

    assert MARKER in _argv_for(ticket, run, pb, ClaudeAgent())


def test_oversized_material_is_truncated_not_dropped(source):
    """Inlining is bounded: the head arrives, the tail is cut, the goal stays sane.

    Both halves matter. Unbounded inlining is what the pointer was reaching for
    when it removed the material entirely; a cap keeps the goal from becoming a
    document without going back to sending nothing.
    """
    from playbooks.research.playbook import _CONTEXT_MAX
    from agents.claude.agent import ClaudeAgent

    head = "HEAD-" + MARKER
    tail = "TAIL-should-not-survive"
    name, items = source
    items.append({
        "id": "item-1",
        "title": "One",
        "context": head + ("x" * (_CONTEXT_MAX * 2)) + tail,
    })
    pb = _playbook()
    run = _run({"source": name, "agents": ["claude"]})
    ticket = pb.seed(run, site=None)[0]

    goal = ticket.payload["goal"]
    argv = _argv_for(ticket, run, pb, ClaudeAgent())

    assert head in argv, "the start of the material must survive"
    assert tail not in argv, "the material must be capped, not inlined whole"
    assert len(goal) < _CONTEXT_MAX * 3, f"goal ran away at {len(goal)} chars"
