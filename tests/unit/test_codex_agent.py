"""Tests for agents.codex.agent.CodexAgent.

TDD: written FIRST, watched fail, then agents/codex/agent.py implemented.

Covers build_invocation (prompt + dangerously-bypass flag, methodology command
present/omitted), parse_result (worker output -> Result mapping), and
health_checks shape.
"""
from __future__ import annotations

import hashlib
import json

import pytest


def _sha(payload: dict) -> str:
    """Canonical (sorted-key, no-whitespace) SHA-256 of a payload."""
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _envelope(payload=None, command="/echo-work", args=None, goal="do the thing"):
    payload = {} if payload is None else payload
    return {
        "ticket_id": "run-1/t-0",
        "run_id": "run-1",
        "phase": "work",
        "resource_req": "cpu",
        "base_ref": "main",
        "payload": payload,
        "payload_sha256": _sha(payload),
        "timeout_s": 3600,
        "site_context": {},
        "goal_envelope": {
            "goal": goal,
            "driver": {"command": command, "args": args or {}, "loop": None},
            "done_contract": {"type": "object"},
            "guardrails": {"no_ship": True},
        },
    }


@pytest.fixture
def codex():
    import agents.codex  # noqa: F401  (registers "codex")
    from engine import agent

    return agent.load("codex")


def test_name_and_registration(codex):
    from agents.codex.agent import CodexAgent

    assert codex.name == "codex"
    assert isinstance(codex, CodexAgent)


def test_build_invocation_sets_goal_and_bypass_flag(codex):
    from engine.models import Driver

    driver = Driver(command="/echo-work", args={"phase": "work"}, loop=None)
    argv = codex.build_invocation(_envelope(), driver)

    assert argv[0] == "codex"
    assert argv[1] == "exec"
    prompt = argv[2]
    assert prompt.startswith("/goal do the thing")
    # methodology command appended when present
    assert "/echo-work" in prompt
    assert "phase=work" in prompt
    # bypass flag present, no --max-turns
    assert argv[-1] == "--dangerously-bypass-approvals-and-sandbox"
    assert "--max-turns" not in argv


def test_build_invocation_sorts_args(codex):
    from engine.models import Driver

    driver = Driver(command="investigate", args={"b": 2, "a": 1}, loop=None)
    argv = codex.build_invocation(_envelope(command="investigate", args={"b": 2, "a": 1}), driver)
    prompt = argv[2]
    # args sorted alphabetically
    assert "investigate a=1 b=2" in prompt


def test_build_invocation_omits_methodology_when_null(codex):
    from engine.models import Driver

    driver = Driver(command=None, args={}, loop=None)
    argv = codex.build_invocation(_envelope(command=None), driver)
    prompt = argv[2]
    assert prompt.strip() == "/goal do the thing"
    assert argv[-1] == "--dangerously-bypass-approvals-and-sandbox"


def test_parse_result_maps_worker_output(codex):
    from engine.models import Result

    payload = {"answer": 42}
    env = _envelope(payload=payload)
    raw = json.dumps(
        {
            "outcome": "ok",
            "termination_reason": "goal_met",
            "payload": payload,
            "result_ref": "file:///r",
            "evidence_ref": "file:///e",
            "error_summary": None,
        }
    )
    result = codex.parse_result(raw, env)
    assert isinstance(result, Result)
    assert result.outcome == "ok"
    assert result.termination_reason == "goal_met"
    assert result.payload == payload
    assert result.result_ref == "file:///r"
    assert result.evidence_ref == "file:///e"
    assert result.ended_at >= result.started_at


def test_parse_result_empty_output_is_driver_failure(codex):
    env = _envelope()
    result = codex.parse_result("", env)
    assert result.outcome == "driver_failed"
    assert result.termination_reason == "driver_error"


def test_parse_result_unparseable_output_captured_as_detail(codex):
    """Unparseable worker output is kept verbatim in detail for the operator."""
    env = _envelope()
    raw = "not json"
    result = codex.parse_result(raw, env)
    assert result.outcome == "driver_failed"
    assert result.termination_reason == "driver_error"
    assert result.detail == raw


def test_health_checks_returns_agent_and_auth(codex):
    import sites.local  # noqa: F401
    from engine import site
    from engine.models import Check

    checks = codex.health_checks("localhost", site.load("local"))
    assert all(isinstance(c, Check) for c in checks)
    names = {c.name for c in checks}
    assert "agent" in names
    assert "auth" in names


def test_health_checks_agent_ok_when_binary_found(monkeypatch):
    import agents.codex.agent as codex_module

    monkeypatch.setattr(codex_module.shutil, "which", lambda _: "/usr/bin/codex")

    from agents.codex.agent import CodexAgent
    import sites.local  # noqa: F401
    from engine import site

    agent = CodexAgent()
    checks = agent.health_checks("localhost", site.load("local"))
    agent_check = next(c for c in checks if c.name == "agent")
    assert agent_check.ok is True
    assert "/usr/bin/codex" in agent_check.detail


def test_health_checks_agent_not_ok_when_binary_missing(monkeypatch):
    import agents.codex.agent as codex_module

    monkeypatch.setattr(codex_module.shutil, "which", lambda _: None)

    from agents.codex.agent import CodexAgent
    import sites.local  # noqa: F401
    from engine import site

    agent = CodexAgent()
    checks = agent.health_checks("localhost", site.load("local"))
    agent_check = next(c for c in checks if c.name == "agent")
    assert agent_check.ok is False
