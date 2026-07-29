"""Unit tests for DexterMockAgent + DexterLocalSite test doubles.

These doubles emit §2.3-shaped payloads for dexter integration testing,
with attempt-aware scenario keying to drive the fix-does-not-hold requeue path.
"""
import pytest

from engine import contracts
from playbooks.dexter.playbook import DexterPlaybook


def test_dexter_mock_agent_parse_result_emits_valid_solve_doc():
    """DexterMockAgent.parse_result yields a valid §2.3 doc per scenario."""
    from testkit.dexter_doubles import DexterMockAgent

    agent = DexterMockAgent()
    playbook = DexterPlaybook()
    result_schema = playbook.result_schema("solve")

    # Scenario: reproduced, fix holds
    envelope = {
        "ticket_id": "run-1/solve-0",
        "payload": {"goal": "fix flaky test", "issue_ref": None, "context": {}},
        "payload_sha256": contracts.payload_sha256(
            {"goal": "fix flaky test", "issue_ref": None, "context": {}}
        ),
    }

    result = agent.parse_result("", envelope)

    assert result.outcome == "ok"
    assert result.termination_reason == "goal_met"

    # Validate §2.3 shape via contracts.validate_result
    result_dict = {
        "outcome": result.outcome,
        "termination_reason": result.termination_reason,
        "result_ref": result.result_ref,
        "evidence_ref": result.evidence_ref,
        "started_at": result.started_at,
        "ended_at": result.ended_at,
        "error_summary": result.error_summary,
        "payload": result.payload,
    }

    # MUST NOT RAISE
    contracts.validate_result(result_dict, result_schema)

    # Check §2.3 required fields are present
    assert "reproduced" in result.payload
    assert "root_cause" in result.payload
    assert "signature" in result.payload["root_cause"]
    assert "cause_category" in result.payload["root_cause"]
    assert "fix" in result.payload
    assert "verified" in result.payload["fix"]
    assert "knowledge_entry" in result.payload
    assert "evidence_ref" in result.payload


def test_dexter_mock_agent_two_goals_share_signature():
    """Two goals can share the same root_cause.signature (clustering)."""
    from testkit.dexter_doubles import DexterMockAgent

    agent = DexterMockAgent()

    # Two different tickets with scenarios that share a signature
    envelope1 = {
        "ticket_id": "run-1/solve-0",
        "payload": {"goal": "fix timeout in test_A", "issue_ref": None, "context": {}},
        "payload_sha256": contracts.payload_sha256(
            {"goal": "fix timeout in test_A", "issue_ref": None, "context": {}}
        ),
    }

    envelope2 = {
        "ticket_id": "run-1/solve-1",
        "payload": {"goal": "fix timeout in test_B", "issue_ref": None, "context": {}},
        "payload_sha256": contracts.payload_sha256(
            {"goal": "fix timeout in test_B", "issue_ref": None, "context": {}}
        ),
    }

    result1 = agent.parse_result("", envelope1)
    result2 = agent.parse_result("", envelope2)

    # Both succeed
    assert result1.outcome == "ok"
    assert result2.outcome == "ok"

    # Both share the same root_cause.signature
    sig1 = result1.payload["root_cause"]["signature"]
    sig2 = result2.payload["root_cause"]["signature"]
    assert sig1 == sig2
    assert sig1 != ""  # non-empty


def test_dexter_mock_agent_attempt_keying_does_not_hold_then_holds():
    """Attempt-keying: does-not-hold ticket yields False on attempt 1, True on attempt 2."""
    from testkit.dexter_doubles import DexterMockAgent

    # Agent with a fix-does-not-hold scenario keyed by (ticket_id, attempt)
    agent = DexterMockAgent()

    # Goal containing "fix-unstable" triggers the attempt-keyed behavior
    # Same envelope used twice (engine reuses payload across requeue)
    envelope = {
        "ticket_id": "run-1/solve-0",
        "payload": {
            "goal": "Investigate flaky test (fix-unstable)",
            "issue_ref": None,
            "context": {},
        },
        "payload_sha256": contracts.payload_sha256(
            {"goal": "Investigate flaky test (fix-unstable)", "issue_ref": None, "context": {}}
        ),
    }

    # ATTEMPT 1: parse_result increments attempt counter
    result1 = agent.parse_result("", envelope)
    assert result1.outcome == "ok"

    # The payload should indicate fix does NOT hold (for recheck_fix)
    # e.g., ci_status != "passing"
    assert result1.payload["fix"]["ci_status"] != "passing"

    # ATTEMPT 2: same envelope, next execution
    result2 = agent.parse_result("", envelope)
    assert result2.outcome == "ok"

    # Now the payload should indicate fix HOLDS
    assert result2.payload["fix"]["ci_status"] == "passing"


def test_dexter_mock_agent_honors_payload_integrity():
    """DexterMockAgent honors payload_sha256 integrity check."""
    from testkit.dexter_doubles import DexterMockAgent

    agent = DexterMockAgent()

    payload = {"goal": "test", "issue_ref": None, "context": {}}
    envelope = {
        "ticket_id": "run-1/solve-0",
        "payload": payload,
        "payload_sha256": "deadbeef",  # WRONG
    }

    result = agent.parse_result("", envelope)

    # MUST contract_fail on mismatch
    assert result.outcome == "driver_failed"
    assert result.termination_reason == "contract_fail"
    assert "payload_sha256 mismatch" in result.error_summary


def test_dexter_mock_agent_health_checks_pass():
    """DexterMockAgent.health_checks returns passing checks."""
    from testkit.dexter_doubles import DexterMockAgent

    agent = DexterMockAgent()
    checks = agent.health_checks("localhost", None)

    assert len(checks) >= 2
    agent_check = next((c for c in checks if c.name == "agent"), None)
    auth_check = next((c for c in checks if c.name == "auth"), None)

    assert agent_check is not None
    assert agent_check.ok is True
    assert auth_check is not None
    assert auth_check.ok is True


def test_dexter_local_site_recheck_fix_payload_derived():
    """DexterLocalSite.recheck_fix returns verdict derived from payload."""
    from testkit.dexter_doubles import DexterLocalSite

    site = DexterLocalSite()

    # Payload with fix.verified=True and ci_status="passing" -> True
    payload_holds = {
        "reproduced": True,
        "root_cause": {"signature": "sig-1", "cause_category": "timing"},
        "fix": {"verified": True, "ci_status": "passing", "diff_ref": "D123"},
        "knowledge_entry": {"ref": "kb-1", "validated": True},
        "evidence_ref": "evidence://1",
    }

    assert site.recheck_fix(payload_holds) is True

    # Payload with ci_status != "passing" -> False
    payload_does_not_hold = {
        "reproduced": True,
        "root_cause": {"signature": "sig-1", "cause_category": "timing"},
        "fix": {"verified": False, "ci_status": "failing", "diff_ref": "D124"},
        "knowledge_entry": {"ref": None, "validated": False},
        "evidence_ref": "evidence://2",
    }

    assert site.recheck_fix(payload_does_not_hold) is False


def test_dexter_local_site_recheck_fix_composes_with_verify():
    """DexterLocalSite.recheck_fix composes with dexter verify."""
    from engine.models import Result, Run, Ticket
    from playbooks.dexter.playbook import DexterPlaybook
    from testkit.dexter_doubles import DexterLocalSite

    playbook = DexterPlaybook()
    site = DexterLocalSite()

    run = Run(
        id="run-1",
        playbook="dexter",
        site="dexter_local",
        base_ref="main",
        phase="solve",
        config={"verify_recheck_optional": False},  # recheck is REQUIRED
        reductions=[],
    )

    ticket = Ticket(
        id="run-1/solve-0",
        run_id="run-1",
        phase="solve",
        state="running",
        resource_req="cpu",
        priority=0.0,
        attempts=1,
        payload={"goal": "test", "issue_ref": None, "context": {}},
    )

    # Result with a "holds" payload
    payload_holds = {
        "reproduced": True,
        "root_cause": {"signature": "sig-1", "cause_category": "timing"},
        "fix": {"verified": True, "ci_status": "passing", "diff_ref": "D123"},
        "knowledge_entry": {"ref": "kb-1", "validated": True},
        "evidence_ref": "evidence://1",
    }

    result_holds = Result(
        outcome="ok",
        termination_reason="goal_met",
        result_ref="result://1",
        error_summary=None,
        started_at=1.0,
        ended_at=2.0,
        payload=payload_holds,
        evidence_ref="evidence://1",
    )

    # verify should return True (shape gate + recheck_fix)
    assert playbook.verify(run, ticket, result_holds, site) is True

    # Result with a "does-not-hold" payload
    payload_does_not_hold = {
        "reproduced": True,
        "root_cause": {"signature": "sig-1", "cause_category": "timing"},
        "fix": {"verified": False, "ci_status": "failing", "diff_ref": "D124"},
        "knowledge_entry": {"ref": None, "validated": False},
        "evidence_ref": "evidence://2",
    }

    result_does_not_hold = Result(
        outcome="ok",
        termination_reason="goal_met",
        result_ref="result://2",
        error_summary=None,
        started_at=1.0,
        ended_at=2.0,
        payload=payload_does_not_hold,
        evidence_ref="evidence://2",
    )

    # verify should return False (recheck_fix says no)
    assert playbook.verify(run, ticket, result_does_not_hold, site) is False


def test_dexter_doubles_register_and_resolve():
    """DexterMockAgent and DexterLocalSite register and resolve via registries."""
    from engine import agent, site

    # Import doubles to trigger registration
    from testkit import dexter_doubles  # noqa: F401

    # Resolve via registries (use 'load', not 'resolve')
    resolved_agent = agent.load("dexter_mock")
    resolved_site = site.load("dexter_local")

    assert resolved_agent is not None
    assert resolved_agent.name == "dexter_mock"

    assert resolved_site is not None
    assert resolved_site.name == "dexter_local"
