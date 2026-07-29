"""Tests for playbooks.dexter.DexterPlaybook.

TDD: written first (Slice 2).
"""
import json
import tempfile
from pathlib import Path

import pytest

from engine import contracts
from engine.models import Driver, Finding, Issue, IssueQuery, Result, Run, Ticket


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    return tmp_path


def _run(config=None, phase="solve"):
    """Helper: construct a Run for testing."""
    return Run(
        id="dexter-20260729-000000",
        playbook="dexter",
        site="local",
        base_ref="main",
        config=config or {},
        phase=phase,
        reductions=[],
    )


def _ticket(tid, run_id, payload):
    """Helper: construct a Ticket for testing."""
    return Ticket(
        id=tid,
        run_id=run_id,
        phase="solve",
        state="running",
        resource_req="cpu",
        priority=0.0,
        attempts=0,
        payload=payload,
    )


def _result(payload, outcome="ok", termination_reason="goal_met"):
    """Helper: construct a Result for testing."""
    return Result(
        outcome=outcome,
        termination_reason=termination_reason,
        result_ref="r1",
        error_summary=None,
        started_at=1000.0,
        ended_at=2000.0,
        payload=payload,
        evidence_ref="e1",
    )


# --- identity / registration ---


def test_packages_importable():
    """Smoke test: playbooks and playbooks.dexter packages can be imported."""
    import playbooks  # noqa: F401
    import playbooks.dexter  # noqa: F401

    # Successfully imported if we reach here
    assert True


def test_name_and_phases():
    """DexterPlaybook has name='dexter', phases=['solve']."""
    from playbooks.dexter.playbook import DexterPlaybook

    pb = DexterPlaybook()
    assert pb.name == "dexter"
    assert pb.phases == ["solve"]


def test_registered_and_loadable():
    """DexterPlaybook is registered under 'dexter' and can be loaded."""
    from engine import playbook

    # Import to trigger registration
    import playbooks.dexter.playbook  # noqa: F401

    pb = playbook.load("dexter")
    assert pb.name == "dexter"


# --- seed from goals list ---


def test_seed_from_goals_list():
    """seed() from run.config['goals'] as list -> N tickets with exact fields."""
    from playbooks.dexter.playbook import DexterPlaybook

    pb = DexterPlaybook()
    goals = ["Fix bug X", "Investigate issue Y", "Debug error Z"]
    run = _run(config={"goals": goals})

    tickets = pb.seed(run, None)

    assert len(tickets) == 3
    for i, t in enumerate(tickets):
        assert t.id == f"{run.id}/solve-{i}"
        assert t.run_id == run.id
        assert t.phase == "solve"
        assert t.state == "queued"
        assert t.resource_req == "cpu"
        assert t.priority == 0.0
        assert t.attempts == 0
        # Payload keys ONLY: goal, issue_ref, context
        assert set(t.payload.keys()) == {"goal", "issue_ref", "context"}
        assert t.payload["goal"] == goals[i]
        assert t.payload["issue_ref"] is None
        assert isinstance(t.payload["context"], dict)


# --- seed from goals file path ---


def test_seed_from_goals_file():
    """seed() from run.config['goals'] as file path -> filters comments/blanks."""
    from playbooks.dexter.playbook import DexterPlaybook

    pb = DexterPlaybook()

    # Create a goals file with comments and blanks
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        f.write("# This is a comment\n")
        f.write("\n")
        f.write("   \n")
        f.write("Goal one\n")
        f.write("  # Another comment\n")
        f.write("Goal two  \n")
        f.write("\n")
        f.write("  Goal three  \n")
        goals_path = f.name

    try:
        run = _run(config={"goals": goals_path})
        tickets = pb.seed(run, None)

        assert len(tickets) == 3
        assert tickets[0].payload["goal"] == "Goal one"
        assert tickets[1].payload["goal"] == "Goal two"
        assert tickets[2].payload["goal"] == "Goal three"
    finally:
        Path(goals_path).unlink()


# --- seed from issue_source ---


def test_seed_from_issue_source():
    """seed() from run.config['issue_query'] -> calls site.issue_source, maps Issue to goal."""
    from playbooks.dexter.playbook import DexterPlaybook

    pb = DexterPlaybook()

    # Mock site with issue_source
    class FakeSite:
        def issue_source(self, query):
            assert isinstance(query, IssueQuery)
            assert query.kind == "incident"
            assert query.filters == {"severity": "high"}
            assert query.limit == 5
            return [
                Issue(id="I1", kind="incident", title="Server crash", ref="INC-001",
                      data={"priority": 10}),
                Issue(id="I2", kind="incident", title="Memory leak", ref="INC-002",
                      data={"priority": 5}),
                Issue(id="I3", kind="incident", title="CPU spike", ref="INC-003",
                      data={}),  # No priority
            ]

    run = _run(config={
        "issue_query": {
            "kind": "incident",
            "filters": {"severity": "high"},
            "limit": 5,
        }
    })

    tickets = pb.seed(run, FakeSite())

    assert len(tickets) == 3
    assert tickets[0].payload["goal"] == "Server crash"
    assert tickets[0].payload["issue_ref"] == "INC-001"
    assert tickets[0].priority == 10.0
    assert tickets[1].payload["goal"] == "Memory leak"
    assert tickets[1].payload["issue_ref"] == "INC-002"
    assert tickets[1].priority == 5.0
    assert tickets[2].payload["goal"] == "CPU spike"
    assert tickets[2].payload["issue_ref"] == "INC-003"
    assert tickets[2].priority == 0.0  # Default priority


# --- seed with no goals ---


def test_seed_with_no_goals():
    """seed() with no goals -> empty list."""
    from playbooks.dexter.playbook import DexterPlaybook

    pb = DexterPlaybook()
    run = _run(config={})

    tickets = pb.seed(run, None)

    assert tickets == []


# --- payload_schema validation ---


def test_payload_schema_accepts_valid_payload():
    """payload_schema accepts {goal, issue_ref, context}."""
    from playbooks.dexter.playbook import DexterPlaybook

    pb = DexterPlaybook()
    schema = pb.payload_schema("solve")

    # Valid payload
    payload = {
        "goal": "Fix the bug",
        "issue_ref": "BUG-123",
        "context": {"environment": "production"},
    }

    # Should not raise
    contracts.validate(payload, schema)


def test_payload_schema_accepts_null_issue_ref():
    """payload_schema accepts issue_ref=null."""
    from playbooks.dexter.playbook import DexterPlaybook

    pb = DexterPlaybook()
    schema = pb.payload_schema("solve")

    payload = {
        "goal": "Fix the bug",
        "issue_ref": None,
        "context": {},
    }

    # Should not raise
    contracts.validate(payload, schema)


def test_payload_schema_rejects_extra_key():
    """payload_schema rejects extra key (additionalProperties:false)."""
    from playbooks.dexter.playbook import DexterPlaybook

    pb = DexterPlaybook()
    schema = pb.payload_schema("solve")

    payload = {
        "goal": "Fix the bug",
        "issue_ref": None,
        "context": {},
        "extra_key": "should fail",
    }

    with pytest.raises(contracts.ContractError) as exc:
        contracts.validate(payload, schema)
    assert "extra_key" in str(exc.value)


def test_payload_schema_rejects_missing_goal():
    """payload_schema rejects missing 'goal' (required)."""
    from playbooks.dexter.playbook import DexterPlaybook

    pb = DexterPlaybook()
    schema = pb.payload_schema("solve")

    payload = {
        "issue_ref": None,
        "context": {},
    }

    with pytest.raises(contracts.ContractError) as exc:
        contracts.validate(payload, schema)
    assert "goal" in str(exc.value).lower()
    assert "required" in str(exc.value).lower()


# --- result_schema validation ---


def test_result_schema_accepts_valid_result():
    """result_schema accepts a valid §2.3 dexter finding doc."""
    from playbooks.dexter.playbook import DexterPlaybook

    pb = DexterPlaybook()
    schema = pb.result_schema("solve")

    # Valid §2.3 payload
    payload = {
        "reproduced": True,
        "root_cause": {
            "signature": "NPE-config-init-001",
            "culprit_symbol": "ConfigLoader.init",
            "cause_category": "null_pointer",
            "mechanism": "uninitialized config field",
        },
        "fix": {
            "verified": True,
            "diff_ref": "D123456",
            "ci_status": "passing",
        },
        "knowledge_entry": {
            "ref": "kb/2026-07-29-npe-config.md",
            "validated": True,
        },
        "evidence_ref": "cases/case-001/JOURNAL.md",
        "notes": "Reproduced locally and verified fix",
    }

    result_dict = {
        "outcome": "ok",
        "termination_reason": "goal_met",
        "result_ref": "r1",
        "evidence_ref": "e1",
        "started_at": 1000.0,
        "ended_at": 2000.0,
        "error_summary": None,
        "payload": payload,
    }

    # Should not raise
    contracts.validate_result(result_dict, schema)


def test_result_schema_rejects_missing_root_cause():
    """result_schema rejects result missing 'root_cause' (required)."""
    from playbooks.dexter.playbook import DexterPlaybook

    pb = DexterPlaybook()
    schema = pb.result_schema("solve")

    # Missing root_cause
    payload = {
        "reproduced": True,
        "fix": {"verified": True},
        "knowledge_entry": {"validated": False},
        "evidence_ref": None,
    }

    result_dict = {
        "outcome": "ok",
        "termination_reason": "goal_met",
        "result_ref": "r1",
        "evidence_ref": None,
        "started_at": 1000.0,
        "ended_at": 2000.0,
        "error_summary": None,
        "payload": payload,
    }

    with pytest.raises(contracts.ContractError) as exc:
        contracts.validate_result(result_dict, schema)
    assert "root_cause" in str(exc.value).lower()


# --- driver ---


def test_driver_returns_exact_driver():
    """driver('solve') returns Driver('/dexter:solve', {}, None)."""
    from playbooks.dexter.playbook import DexterPlaybook

    pb = DexterPlaybook()
    driver = pb.driver("solve")

    assert isinstance(driver, Driver)
    assert driver.command == "/dexter:solve"
    assert driver.args == {}
    assert driver.loop is None


def test_driver_renders_to_exact_prompt():
    """Driver renders to '/goal <goal> /dexter:solve' with no k=v tail."""
    from playbooks.dexter.playbook import DexterPlaybook
    from agents.claude.agent import ClaudeAgent

    pb = DexterPlaybook()
    driver = pb.driver("solve")

    # Use ClaudeAgent._build_prompt (the renderer that matters)
    goal = "Fix memory leak in server"
    prompt = ClaudeAgent._build_prompt(goal, driver)

    assert prompt == "/goal Fix memory leak in server /dexter:solve"


# --- next_phase / is_done ---


def test_next_phase_returns_none():
    """next_phase() always returns None (single phase)."""
    from playbooks.dexter.playbook import DexterPlaybook

    pb = DexterPlaybook()
    run = _run(phase="solve")

    assert pb.next_phase(run) is None


def test_is_done_returns_true():
    """is_done() returns True when run.phase == 'solve'."""
    from playbooks.dexter.playbook import DexterPlaybook

    pb = DexterPlaybook()
    run = _run(phase="solve")

    assert pb.is_done(run) is True


# --- verify (Slice 3) ---


def test_verify_valid_payload_recheck_true():
    """verify() with valid §2.3 payload + recheck_fix→True ⇒ True."""
    from playbooks.dexter.playbook import DexterPlaybook

    pb = DexterPlaybook()
    run = _run()
    ticket = _ticket(f"{run.id}/solve-0", run.id, {"goal": "test"})

    # Valid §2.3 payload
    payload = {
        "reproduced": True,
        "root_cause": {
            "signature": "NPE-config-init-001",
            "cause_category": "null_pointer",
        },
        "fix": {"verified": True},
        "knowledge_entry": {"validated": False},
        "evidence_ref": None,
    }
    result = _result(payload)

    # Fake site with recheck_fix returning True
    class FakeSite:
        def recheck_fix(self, result_payload):
            return True

    verified = pb.verify(run, ticket, result, FakeSite())
    assert verified is True


def test_verify_valid_payload_recheck_false():
    """verify() with valid §2.3 payload + recheck_fix→False ⇒ False."""
    from playbooks.dexter.playbook import DexterPlaybook

    pb = DexterPlaybook()
    run = _run()
    ticket = _ticket(f"{run.id}/solve-0", run.id, {"goal": "test"})

    # Valid §2.3 payload
    payload = {
        "reproduced": True,
        "root_cause": {
            "signature": "NPE-config-init-001",
            "cause_category": "null_pointer",
        },
        "fix": {"verified": True},
        "knowledge_entry": {"validated": False},
        "evidence_ref": None,
    }
    result = _result(payload)

    # Fake site with recheck_fix returning False
    class FakeSite:
        def recheck_fix(self, result_payload):
            return False

    verified = pb.verify(run, ticket, result, FakeSite())
    assert verified is False


def test_verify_malformed_payload_recheck_true():
    """verify() with malformed payload (missing root_cause) + recheck_fix→True ⇒ False (shape gate wins)."""
    from playbooks.dexter.playbook import DexterPlaybook

    pb = DexterPlaybook()
    run = _run()
    ticket = _ticket(f"{run.id}/solve-0", run.id, {"goal": "test"})

    # Malformed payload: missing root_cause
    payload = {
        "reproduced": True,
        "fix": {"verified": True},
        "knowledge_entry": {"validated": False},
        "evidence_ref": None,
    }
    result = _result(payload)

    # Fake site with recheck_fix returning True
    class FakeSite:
        def recheck_fix(self, result_payload):
            return True

    verified = pb.verify(run, ticket, result, FakeSite())
    assert verified is False


def test_verify_no_recheck_fix_fails_safe():
    """verify() with site without recheck_fix ⇒ False (fail-safe)."""
    from playbooks.dexter.playbook import DexterPlaybook

    pb = DexterPlaybook()
    run = _run()
    ticket = _ticket(f"{run.id}/solve-0", run.id, {"goal": "test"})

    # Valid §2.3 payload
    payload = {
        "reproduced": True,
        "root_cause": {
            "signature": "NPE-config-init-001",
            "cause_category": "null_pointer",
        },
        "fix": {"verified": True},
        "knowledge_entry": {"validated": False},
        "evidence_ref": None,
    }
    result = _result(payload)

    # Site without recheck_fix
    class BareSite:
        pass

    verified = pb.verify(run, ticket, result, BareSite())
    assert verified is False


def test_verify_no_recheck_fix_optional_admits():
    """verify() with site without recheck_fix ⇒ True when run.config['verify_recheck_optional'] set."""
    from playbooks.dexter.playbook import DexterPlaybook

    pb = DexterPlaybook()
    run = _run(config={"verify_recheck_optional": True})
    ticket = _ticket(f"{run.id}/solve-0", run.id, {"goal": "test"})

    # Valid §2.3 payload
    payload = {
        "reproduced": True,
        "root_cause": {
            "signature": "NPE-config-init-001",
            "cause_category": "null_pointer",
        },
        "fix": {"verified": True},
        "knowledge_entry": {"validated": False},
        "evidence_ref": None,
    }
    result = _result(payload)

    # Site without recheck_fix
    class BareSite:
        pass

    verified = pb.verify(run, ticket, result, BareSite())
    assert verified is True


def test_verify_ignores_payload_verified_field():
    """verify() ignores fix.verified=true, uses recheck_fix (no-trust rule)."""
    from playbooks.dexter.playbook import DexterPlaybook

    pb = DexterPlaybook()
    run = _run()
    ticket = _ticket(f"{run.id}/solve-0", run.id, {"goal": "test"})

    # Payload with fix.verified=true (should be ignored)
    payload = {
        "reproduced": True,
        "root_cause": {
            "signature": "NPE-config-init-001",
            "cause_category": "null_pointer",
        },
        "fix": {"verified": True},
        "knowledge_entry": {"validated": False},
        "evidence_ref": None,
    }
    result = _result(payload)

    # Fake site with recheck_fix returning False (independent check fails)
    class FakeSite:
        def recheck_fix(self, result_payload):
            return False

    verified = pb.verify(run, ticket, result, FakeSite())
    # Even though fix.verified=true, verify returns False because recheck_fix→False
    assert verified is False


def test_verify_recheck_fix_raises_fails_safe():
    """verify() with recheck_fix raising exception ⇒ False (D3 fail-safe), does not propagate."""
    from playbooks.dexter.playbook import DexterPlaybook

    pb = DexterPlaybook()
    run = _run()
    ticket = _ticket(f"{run.id}/solve-0", run.id, {"goal": "test"})

    # Valid §2.3 payload
    payload = {
        "reproduced": True,
        "root_cause": {
            "signature": "NPE-config-init-001",
            "cause_category": "null_pointer",
        },
        "fix": {"verified": True},
        "knowledge_entry": {"validated": False},
        "evidence_ref": None,
    }
    result = _result(payload)

    # Fake site with recheck_fix raising an exception
    class FakeSite:
        def recheck_fix(self, result_payload):
            raise RuntimeError("probe failed")

    # verify should return False (fail-safe), NOT propagate the exception
    verified = pb.verify(run, ticket, result, FakeSite())
    assert verified is False


def test_reduce_raises_not_implemented():
    """reduce() raises NotImplementedError (stub for Slice 4)."""
    from playbooks.dexter.playbook import DexterPlaybook

    pb = DexterPlaybook()
    run = _run()
    findings = [
        Finding(run_id=run.id, ticket_id=f"{run.id}/solve-0", kind="result", json={}),
    ]

    with pytest.raises(NotImplementedError):
        pb.reduce(run, "solve", findings, None)
