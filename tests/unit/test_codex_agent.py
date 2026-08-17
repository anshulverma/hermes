"""Tests for agents.codex.agent.CodexAgent.

TDD: written FIRST, watched fail, then agents/codex/agent.py implemented.

Covers build_invocation (prompt + --dangerously-bypass-approvals-and-sandbox +
--json + -o flags, methodology command present/omitted), parse_result (native
JSONL event parsing, answer-file reading, prose wrapping, structured result doc
pass-through, failure on missing turn.completed, empty/garbage stdout), and
health_checks shape.
"""
from __future__ import annotations

import hashlib
import json
import os
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


def _codex_jsonl(
    thread_id: str = "thread-xyz",
    answer: str = "PONG",
    include_completed: bool = True,
    include_failed: bool = False,
) -> str:
    """Build realistic codex --json JSONL stdout with preamble."""
    lines = [
        '# Codex CLI\n',  # non-JSON preamble
        json.dumps({"type": "thread.started", "thread_id": thread_id}),
        json.dumps({"type": "turn.started"}),
        json.dumps({
            "type": "item.completed",
            "item": {"id": "item_0", "type": "agent_message", "text": answer},
        }),
    ]
    if include_failed:
        lines.append(json.dumps({"type": "turn.failed", "message": "agent error"}))
    if include_completed:
        lines.append(json.dumps({
            "type": "turn.completed",
            "usage": {"input_tokens": 12117, "output_tokens": 6},
        }))
    return "\n".join(lines) + "\n"


@pytest.fixture
def codex():
    import agents.codex  # noqa: F401  (registers "codex")
    from engine import agent

    return agent.load("codex")


@pytest.fixture
def codex_agent(monkeypatch, tmp_path):
    """A fresh adapter whose per-ticket answer files land under a controlled HERMES_HOME."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    import agents.codex.agent as mod
    return mod.CodexAgent()


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
    assert "--dangerously-bypass-approvals-and-sandbox" in argv
    assert "--max-turns" not in argv
    # native JSON output flags
    assert "--json" in argv
    assert "-o" in argv
    o_idx = argv.index("-o")
    assert os.path.isabs(argv[o_idx + 1])


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
    assert "--dangerously-bypass-approvals-and-sandbox" in argv
    assert "--json" in argv
    assert "-o" in argv


def test_build_invocation_sanitises_ticket_id_into_one_filename(codex_agent, tmp_path):
    from engine.models import Driver

    env = _envelope()
    env["ticket_id"] = "r-1/work/t:0"
    argv = codex_agent.build_invocation(env, Driver(command=None, args={}, loop=None))
    out_path = argv[argv.index("-o") + 1]
    assert os.path.isabs(out_path)
    assert "/" not in os.path.basename(out_path)
    assert ":" not in os.path.basename(out_path)


def test_build_invocation_clears_stale_answer_file(codex_agent):
    from engine.models import Driver

    env = _envelope()
    argv = codex_agent.build_invocation(env, Driver(command=None, args={}, loop=None))
    out_path = argv[argv.index("-o") + 1]
    # Write a stale file and verify a second call clears it.
    with open(out_path, "w") as fh:
        fh.write("stale")
    codex_agent.build_invocation(env, Driver(command=None, args={}, loop=None))
    assert not os.path.exists(out_path)


def test_parse_result_exact_captured_jsonl_ok(codex_agent, tmp_path):
    """The exact live captured JSONL + -o file -> ok, answer is PONG."""
    from engine.models import Driver

    env = _envelope()
    argv = codex_agent.build_invocation(env, Driver(command=None, args={}, loop=None))
    out_path = argv[argv.index("-o") + 1]

    # Write the answer file (what codex -o produces).
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("PONG")

    raw = _codex_jsonl(thread_id="thread-xyz", answer="PONG")
    result = codex_agent.parse_result(raw, env)

    assert result.outcome == "ok"
    assert result.termination_reason == "goal_met"
    assert result.payload["answer"] == "PONG"
    assert result.result_ref == "codex:thread:thread-xyz"
    assert result.ended_at >= result.started_at


def test_parse_result_maps_worker_output(codex_agent, tmp_path):
    """Successful JSONL + answer file -> ok with correct payload."""
    from engine.models import Driver, Result

    env = _envelope()
    argv = codex_agent.build_invocation(env, Driver(command=None, args={}, loop=None))
    out_path = argv[argv.index("-o") + 1]

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("the computed answer")

    raw = _codex_jsonl(thread_id="thread-abc", answer="the computed answer")
    result = codex_agent.parse_result(raw, env)

    assert isinstance(result, Result)
    assert result.outcome == "ok"
    assert result.termination_reason == "goal_met"
    assert result.payload["answer"] == "the computed answer"
    assert result.result_ref == "codex:thread:thread-abc"
    assert result.ended_at >= result.started_at


def test_parse_result_no_turn_completed_is_driver_failed(codex_agent, tmp_path):
    """JSONL events with no turn.completed -> driver_failed, raw captured in detail."""
    from engine.models import Driver

    env = _envelope()
    codex_agent.build_invocation(env, Driver(command=None, args={}, loop=None))

    raw = _codex_jsonl(include_completed=False)
    result = codex_agent.parse_result(raw, env)

    assert result.outcome == "driver_failed"
    assert result.termination_reason == "driver_error"
    assert result.detail is not None


def test_parse_result_turn_failed_event_is_driver_failed(codex_agent, tmp_path):
    """A turn.failed event -> driver_failed even if turn.completed also present."""
    from engine.models import Driver

    env = _envelope()
    codex_agent.build_invocation(env, Driver(command=None, args={}, loop=None))

    raw = _codex_jsonl(include_failed=True, include_completed=False)
    result = codex_agent.parse_result(raw, env)

    assert result.outcome == "driver_failed"
    assert result.termination_reason == "driver_error"
    assert "agent error" in (result.error_summary or "")


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


def test_parse_result_answer_is_hermes_result_doc_structured_path(codex_agent, tmp_path):
    """When the answer text is itself a hermes result doc, the structured path wins."""
    from engine.models import Driver

    payload = {"answer": 42}
    env = _envelope(payload=payload)
    argv = codex_agent.build_invocation(env, Driver(command=None, args={}, loop=None))
    out_path = argv[argv.index("-o") + 1]

    result_doc = json.dumps({
        "outcome": "ok",
        "termination_reason": "goal_met",
        "payload": payload,
        "result_ref": "file:///r",
        "evidence_ref": "file:///e",
        "error_summary": None,
    })
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(result_doc)

    raw = _codex_jsonl(answer=result_doc)
    result = codex_agent.parse_result(raw, env)

    assert result.outcome == "ok"
    assert result.termination_reason == "goal_met"
    assert result.payload == payload
    assert result.result_ref == "file:///r"
    assert result.evidence_ref == "file:///e"


def test_parse_result_no_exception_on_garbage_input(codex):
    """Garbage stdout never raises — returns driver_error with detail."""
    env = _envelope()
    for raw in [None, "", "   ", "not json at all"]:
        result = codex.parse_result(raw or "", env)
        assert result.outcome == "driver_failed"
        assert result.termination_reason == "driver_error"


def test_parse_result_cleans_up_answer_file_on_success(codex_agent, tmp_path):
    """Answer file is removed after a successful parse."""
    from engine.models import Driver

    env = _envelope()
    argv = codex_agent.build_invocation(env, Driver(command=None, args={}, loop=None))
    out_path = argv[argv.index("-o") + 1]

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("done")

    codex_agent.parse_result(_codex_jsonl(), env)
    assert not os.path.exists(out_path)


def test_parse_result_cleans_up_answer_file_on_failure(codex_agent, tmp_path):
    """Answer file is removed even when parse fails."""
    from engine.models import Driver

    env = _envelope()
    argv = codex_agent.build_invocation(env, Driver(command=None, args={}, loop=None))
    out_path = argv[argv.index("-o") + 1]

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("partial")

    codex_agent.parse_result(_codex_jsonl(include_completed=False), env)
    assert not os.path.exists(out_path)


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


# --- trace_source: pointing the engine at the rollout transcript ---------

def _ok_result(ref):
    from engine.models import Result
    return Result(
        outcome="ok", termination_reason="goal_met", result_ref=ref,
        error_summary=None, started_at=1.0, ended_at=2.0,
        payload={"answer": "x"}, evidence_ref=None,
    )


def test_trace_source_globs_the_rollout_for_the_thread(codex):
    """Codex files a rollout under a dated directory whose name also carries a
    timestamp -- neither of which the master knows, so both are globbed."""
    tid = "019fd272-a8be-78f0-a43c-4247ec7b0064"

    source = codex.trace_source(_ok_result(f"codex:thread:{tid}"), {})

    assert source == f"~/.codex/sessions/*/*/*/rollout-*-{tid}.jsonl"


def test_trace_source_declines_a_foreign_ref(codex):
    assert codex.trace_source(_ok_result("claude:session:abc"), {}) is None
    assert codex.trace_source(_ok_result(None), {}) is None


@pytest.mark.parametrize("hostile", [
    "abc; rm -rf ~", "../../etc/passwd", "abc$(id)", "abc*", "abc`id`", "a b", "",
])
def test_trace_source_refuses_anything_not_a_thread_id(codex, hostile):
    """Expanded by a remote shell on an ssh site: refuse, do not escape."""
    assert codex.trace_source(_ok_result(f"codex:thread:{hostile}"), {}) is None


def test_trace_source_never_raises(codex):
    for ref in [None, "", "codex:thread:", "codex:", ":::", "codex:thread"]:
        assert codex.trace_source(_ok_result(ref), {}) is None
