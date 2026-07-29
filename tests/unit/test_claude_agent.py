"""Tests for agents.claude.agent.ClaudeAgent (§6, §8).

TDD: written FIRST, watched fail, then agents/claude/agent.py implemented.

Covers build_invocation (prompt + permission mode, methodology command present/
omitted), parse_result (worker output -> Result mapping), the payload_sha256
recompute -> contract_fail on tamper, and health_checks shape.
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
def claude():
    import agents.claude  # noqa: F401  (registers "claude")
    from engine import agent

    return agent.load("claude")


def test_name_and_registration(claude):
    from agents.claude.agent import ClaudeAgent

    assert claude.name == "claude"
    assert isinstance(claude, ClaudeAgent)


def test_build_invocation_sets_goal_and_permission_mode(claude):
    from engine.models import Driver

    driver = Driver(command="/echo-work", args={"phase": "work"}, loop=None)
    argv = claude.build_invocation(_envelope(), driver)

    assert argv[0] == "claude"
    assert argv[1] == "-p"
    prompt = argv[2]
    assert "/goal do the thing" in prompt
    # methodology command appended when present
    assert "/echo-work" in prompt
    assert "phase=work" in prompt
    # permission mode present, no --max-turns
    assert "--permission-mode" in argv
    assert argv[argv.index("--permission-mode") + 1] == "bypassPermissions"
    assert "--max-turns" not in argv


def test_build_invocation_omits_methodology_when_null(claude):
    from engine.models import Driver

    driver = Driver(command=None, args={}, loop=None)
    argv = claude.build_invocation(_envelope(command=None), driver)
    prompt = argv[2]
    assert prompt.strip() == "/goal do the thing"
    assert "--permission-mode" in argv


def test_parse_result_maps_worker_output(claude):
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
    result = claude.parse_result(raw, env)
    assert isinstance(result, Result)
    assert result.outcome == "ok"
    assert result.termination_reason == "goal_met"
    assert result.payload == payload
    assert result.result_ref == "file:///r"
    assert result.evidence_ref == "file:///e"
    assert result.ended_at >= result.started_at


def test_parse_result_maps_driver_failure(claude):
    env = _envelope()
    raw = json.dumps(
        {
            "outcome": "driver_failed",
            "termination_reason": "driver_error",
            "error_summary": "boom",
        }
    )
    result = claude.parse_result(raw, env)
    assert result.outcome == "driver_failed"
    assert result.termination_reason == "driver_error"
    assert result.error_summary == "boom"


def test_parse_result_contract_fail_on_payload_tamper(claude):
    """A digest mismatch (tampered payload) -> driver_failed/contract_fail, no retry."""
    env = _envelope(payload={"answer": 42})
    env["payload_sha256"] = "0" * 64  # tamper: no longer matches the payload
    raw = json.dumps({"outcome": "ok", "termination_reason": "goal_met", "payload": {}})
    result = claude.parse_result(raw, env)
    assert result.outcome == "driver_failed"
    assert result.termination_reason == "contract_fail"


def test_parse_result_empty_output_is_driver_failure(claude):
    env = _envelope()
    result = claude.parse_result("", env)
    assert result.outcome == "driver_failed"
    assert result.termination_reason == "driver_error"


def test_health_checks_returns_agent_and_auth(claude):
    import sites.local  # noqa: F401
    from engine import site
    from engine.models import Check

    checks = claude.health_checks("localhost", site.load("local"))
    assert all(isinstance(c, Check) for c in checks)
    names = {c.name for c in checks}
    assert "agent" in names
    assert "auth" in names
