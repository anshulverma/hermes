"""Tests for testkit.mock_agent.MockAgent.

TDD: written first. Every outcome / termination_reason must be reachable
deterministically from the scenario table.
"""
import pytest


def _envelope(scenario=None, ticket_id="run-1/t-0"):
    payload = {}
    if scenario is not None:
        payload["scenario"] = scenario
    return {
        "ticket_id": ticket_id,
        "run_id": "run-1",
        "phase": "work",
        "resource_req": "cpu",
        "base_ref": "main",
        "payload": payload,
        "payload_sha256": "deadbeef",
        "timeout_s": 3600,
        "site_context": {},
        "goal_envelope": {
            "goal": "do the thing",
            "driver": {"command": "/echo", "args": {}, "loop": None},
            "done_contract": {"type": "object"},
            "guardrails": {"no_ship": True},
        },
    }


def test_mock_agent_name_and_registration():
    import testkit  # noqa: F401
    from engine import agent
    from testkit.mock_agent import MockAgent

    ag = agent.load("mock")
    assert isinstance(ag, MockAgent)
    assert ag.name == "mock"


def test_build_invocation_returns_argv_list():
    from testkit.mock_agent import MockAgent
    from engine.models import Driver

    ag = MockAgent()
    argv = ag.build_invocation(_envelope("ok"), Driver(command="/echo", args={}, loop=None))
    assert isinstance(argv, list)
    assert all(isinstance(x, str) for x in argv)
    assert argv  # non-empty


def test_health_checks_pass_by_default():
    from testkit.mock_agent import MockAgent
    import sites.local  # noqa: F401
    from engine import site

    ag = MockAgent()
    checks = ag.health_checks("localhost", site.load("local"))
    assert all(c.ok for c in checks)
    assert checks


@pytest.mark.parametrize(
    "scenario,outcome,termination_reason",
    [
        ("ok", "ok", "goal_met"),
        ("contract_fail", "driver_failed", "contract_fail"),
        ("driver_error", "driver_failed", "driver_error"),
        ("timeout", "driver_failed", "timeout"),
        ("transport_error", "infra_failed", "transport_error"),
    ],
)
def test_parse_result_scenarios_deterministic(scenario, outcome, termination_reason):
    from testkit.mock_agent import MockAgent
    from engine.models import Result

    ag = MockAgent()
    env = _envelope(scenario)
    r1 = ag.parse_result("", env)
    r2 = ag.parse_result("", env)

    assert isinstance(r1, Result)
    assert r1.outcome == outcome
    assert r1.termination_reason == termination_reason
    # Deterministic: same envelope -> same outcome/reason
    assert (r2.outcome, r2.termination_reason) == (r1.outcome, r1.termination_reason)
    # Timestamps present and ordered
    assert r1.ended_at >= r1.started_at


def test_parse_result_defaults_to_ok():
    from testkit.mock_agent import MockAgent

    ag = MockAgent()
    r = ag.parse_result("", _envelope())  # no scenario in payload
    assert r.outcome == "ok"
    assert r.termination_reason == "goal_met"


def test_every_outcome_reachable():
    """All three outcomes are produced by some scenario."""
    from testkit.mock_agent import MockAgent

    ag = MockAgent()
    outcomes = {
        ag.parse_result("", _envelope(s)).outcome
        for s in ("ok", "contract_fail", "driver_error", "timeout", "transport_error")
    }
    assert outcomes == {"ok", "driver_failed", "infra_failed"}
