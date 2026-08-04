"""Tests for agents.claude.agent.ClaudeAgent.

TDD: written FIRST, watched fail, then agents/claude/agent.py implemented.

Covers build_invocation (prompt + permission mode + --output-format json,
methodology command present/omitted), parse_result (native --output-format json
envelope parsing, prose wrapping, structured result doc pass-through, is_error
handling, payload integrity, empty/garbage stdout), and health_checks shape.
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


def _claude_stdout(
    result: str = "PONG",
    is_error: bool = False,
    session_id: str = "sess-abc",
    uuid: str = "uuid-123",
    duration_ms: int = 1500,
    api_error_status=None,
) -> str:
    """Build a realistic claude --output-format json stdout with preamble."""
    preamble = (
        "Claude Code at Meta (https://www.meta.com)\n"
        "Using AI Gateway (Vertex upstream)\n"
    )
    envelope = {
        "is_error": is_error,
        "result": result,
        "subtype": "success" if not is_error else "error",
        "session_id": session_id,
        "uuid": uuid,
        "duration_ms": duration_ms,
        "duration_api_ms": duration_ms - 300,
        "total_cost_usd": 0.001,
        "usage": {"input_tokens": 100, "output_tokens": 5},
        "stop_reason": "end_turn",
        "terminal_reason": None,
        "api_error_status": api_error_status,
        "permission_denials": [],
        "num_turns": 1,
        "type": "result",
    }
    return preamble + json.dumps(envelope) + "\n"


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
    # native JSON output flag
    assert "--output-format" in argv
    assert argv[argv.index("--output-format") + 1] == "json"


def test_build_invocation_omits_methodology_when_null(claude):
    from engine.models import Driver

    driver = Driver(command=None, args={}, loop=None)
    argv = claude.build_invocation(_envelope(command=None), driver)
    prompt = argv[2]
    assert prompt.strip() == "/goal do the thing"
    assert "--permission-mode" in argv
    assert "--output-format" in argv
    assert argv[argv.index("--output-format") + 1] == "json"


def test_parse_result_exact_captured_stdout_ok(claude):
    """The exact live captured stdout (preamble + JSON line) -> ok, answer is PONG."""
    env = _envelope()
    raw = _claude_stdout(result="PONG", session_id="sess-abc", duration_ms=1500)
    result = claude.parse_result(raw, env)
    assert result.outcome == "ok"
    assert result.termination_reason == "goal_met"
    assert result.payload["answer"] == "PONG"
    assert result.result_ref == "claude:session:sess-abc"
    # started_at derived from duration_ms so it is before ended_at
    assert result.ended_at >= result.started_at
    assert result.ended_at - result.started_at >= 1.0  # at least 1500ms worth


def test_parse_result_is_error_true_is_driver_failed(claude):
    """is_error true -> driver_failed / driver_error with error_summary and raw in detail."""
    env = _envelope()
    raw = _claude_stdout(result="", is_error=True, api_error_status="401 Unauthorized")
    result = claude.parse_result(raw, env)
    assert result.outcome == "driver_failed"
    assert result.termination_reason == "driver_error"
    assert result.error_summary is not None
    assert "is_error" in result.error_summary
    # raw stdout captured in detail
    assert result.detail is not None
    assert "is_error" in result.detail


def test_parse_result_maps_worker_output(claude):
    """Successful claude stdout -> ok with correct payload."""
    from engine.models import Result

    env = _envelope()
    raw = _claude_stdout(result="the computed answer", session_id="sess-xyz")
    result = claude.parse_result(raw, env)
    assert isinstance(result, Result)
    assert result.outcome == "ok"
    assert result.termination_reason == "goal_met"
    assert result.payload["answer"] == "the computed answer"
    assert result.result_ref == "claude:session:sess-xyz"
    assert result.ended_at >= result.started_at


def test_parse_result_maps_driver_failure(claude):
    """is_error true in the native envelope -> driver_failed."""
    env = _envelope()
    raw = _claude_stdout(result="", is_error=True)
    result = claude.parse_result(raw, env)
    assert result.outcome == "driver_failed"
    assert result.termination_reason == "driver_error"
    assert result.error_summary is not None


def test_parse_result_contract_fail_on_payload_tamper(claude):
    """A digest mismatch (tampered payload) -> driver_failed/contract_fail, no retry."""
    env = _envelope(payload={"answer": 42})
    env["payload_sha256"] = "0" * 64  # tamper: no longer matches the payload
    raw = _claude_stdout(result="some answer")
    result = claude.parse_result(raw, env)
    assert result.outcome == "driver_failed"
    assert result.termination_reason == "contract_fail"


def test_parse_result_empty_output_is_driver_failure(claude):
    env = _envelope()
    result = claude.parse_result("", env)
    assert result.outcome == "driver_failed"
    assert result.termination_reason == "driver_error"


def test_parse_result_unparseable_output_captured_as_detail(claude):
    """Unparseable worker output is kept verbatim in ``detail`` for the operator."""
    env = _envelope()
    raw = "Traceback (most recent call last):\n  File ...\nValueError: nope"
    result = claude.parse_result(raw, env)
    assert result.outcome == "driver_failed"
    assert result.termination_reason == "driver_error"
    assert result.detail == raw  # the exact unparseable output, not just a summary


def test_parse_result_answer_is_hermes_result_doc_structured_path(claude):
    """When the answer text is itself a hermes result doc, the structured path wins."""
    payload = {"answer": 42}
    env = _envelope(payload=payload)
    # Build a hermes result doc as the answer text inside the claude envelope.
    result_doc = json.dumps({
        "outcome": "ok",
        "termination_reason": "goal_met",
        "payload": payload,
        "result_ref": "file:///r",
        "evidence_ref": "file:///e",
        "error_summary": None,
    })
    raw = (
        "Claude Code at Meta (https://www.meta.com)\n"
        + json.dumps({
            "is_error": False,
            "result": result_doc,
            "subtype": "success",
            "session_id": "sess-1",
            "uuid": "u-1",
            "duration_ms": 1000,
            "type": "result",
        }) + "\n"
    )
    result = claude.parse_result(raw, env)
    # The structured path honours outcome/payload from the result doc.
    assert result.outcome == "ok"
    assert result.termination_reason == "goal_met"
    assert result.payload == payload
    assert result.result_ref == "file:///r"
    assert result.evidence_ref == "file:///e"


def test_parse_result_worker_stack_trace_captured_as_detail(claude):
    """A worker-reported stack_trace/detail is surfaced on the Result when answer is a result doc."""
    env = _envelope()
    # The answer text is a hermes result doc containing a stack_trace.
    result_doc = json.dumps({
        "outcome": "driver_failed",
        "termination_reason": "driver_error",
        "error_summary": "boom",
        "stack_trace": "line 1\nline 2\nBoomError",
    })
    raw = (
        "Claude Code at Meta (https://www.meta.com)\n"
        + json.dumps({
            "is_error": False,
            "result": result_doc,
            "subtype": "success",
            "session_id": "sess-1",
            "uuid": "u-1",
            "duration_ms": 1000,
            "type": "result",
        }) + "\n"
    )
    result = claude.parse_result(raw, env)
    assert result.detail == "line 1\nline 2\nBoomError"


def test_parse_result_no_exception_on_garbage_input(claude):
    """Garbage stdout never raises — returns driver_error with detail."""
    env = _envelope()
    for raw in [None, "", "   ", "{not valid json}", '{"no_outcome":true}']:
        result = claude.parse_result(raw or "", env)
        assert result.outcome == "driver_failed"
        assert result.termination_reason in ("driver_error", "contract_fail")


def test_health_checks_returns_agent_and_auth(claude):
    import sites.local  # noqa: F401
    from engine import site
    from engine.models import Check

    checks = claude.health_checks("localhost", site.load("local"))
    assert all(isinstance(c, Check) for c in checks)
    names = {c.name for c in checks}
    assert "agent" in names
    assert "auth" in names
