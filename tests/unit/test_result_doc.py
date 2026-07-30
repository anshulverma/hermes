"""Tests for agents._result_doc.parse_result_doc.

TDD: written FIRST, watched fail, then agents/_result_doc.py implemented.

Covers the shared result-doc parsing logic extracted from ClaudeAgent: payload
integrity check, doc parsing (empty/unparseable/valid), outcome/termination
mapping, detail/stack_trace capture.
"""
from __future__ import annotations

import hashlib
import json

import pytest


def _sha(payload: dict) -> str:
    """Canonical (sorted-key, no-whitespace) SHA-256 of a payload."""
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _envelope(payload=None, goal="do the thing"):
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
            "driver": {"command": "/echo-work", "args": {}, "loop": None},
            "done_contract": {"type": "object"},
            "guardrails": {"no_ship": True},
        },
    }


def test_ok_doc_maps_fields():
    from agents._result_doc import parse_result_doc
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
    result = parse_result_doc(raw, env)
    assert isinstance(result, Result)
    assert result.outcome == "ok"
    assert result.termination_reason == "goal_met"
    assert result.payload == payload
    assert result.result_ref == "file:///r"
    assert result.evidence_ref == "file:///e"


def test_driver_failed_doc_maps_fields():
    from agents._result_doc import parse_result_doc

    env = _envelope()
    raw = json.dumps(
        {
            "outcome": "driver_failed",
            "termination_reason": "driver_error",
            "error_summary": "boom",
        }
    )
    result = parse_result_doc(raw, env)
    assert result.outcome == "driver_failed"
    assert result.termination_reason == "driver_error"
    assert result.error_summary == "boom"


def test_payload_tamper_returns_contract_fail():
    from agents._result_doc import parse_result_doc

    env = _envelope(payload={"answer": 42})
    env["payload_sha256"] = "0" * 64  # tamper: no longer matches the payload
    raw = json.dumps({"outcome": "ok", "termination_reason": "goal_met", "payload": {}})
    result = parse_result_doc(raw, env)
    assert result.outcome == "driver_failed"
    assert result.termination_reason == "contract_fail"


def test_empty_output_returns_driver_error():
    from agents._result_doc import parse_result_doc

    env = _envelope()
    result = parse_result_doc("", env)
    assert result.outcome == "driver_failed"
    assert result.termination_reason == "driver_error"
    assert result.detail is None


def test_unparseable_output_captured_as_detail():
    from agents._result_doc import parse_result_doc

    env = _envelope()
    raw = "not json"
    result = parse_result_doc(raw, env)
    assert result.outcome == "driver_failed"
    assert result.termination_reason == "driver_error"
    assert result.detail == "not json"


def test_stack_trace_captured_as_detail():
    from agents._result_doc import parse_result_doc

    env = _envelope()
    raw = json.dumps(
        {
            "outcome": "driver_failed",
            "termination_reason": "driver_error",
            "error_summary": "boom",
            "stack_trace": "line1\nline2",
        }
    )
    result = parse_result_doc(raw, env)
    assert result.detail == "line1\nline2"
