"""Tests for engine dataclasses and enums.

TDD: write tests first to ensure the dataclasses behave as intended.
"""
import pytest


def test_driver_has_command_args_loop():
    """Driver has command, args, loop (no goal field)."""
    from engine.models import Driver

    driver = Driver(
        command="/solve",
        args={"foo": "bar"},
        loop=None,
    )

    assert driver.command == "/solve"
    assert driver.args == {"foo": "bar"}
    assert driver.loop is None
    assert not hasattr(driver, "goal")  # Critical: no goal field


def test_goal_envelope_has_goal_driver_contract_guardrails():
    """GoalEnvelope has goal, driver, done_contract, guardrails."""
    from engine.models import GoalEnvelope, Driver

    driver = Driver(command="/solve", args={}, loop=None)
    envelope = GoalEnvelope(
        goal="Fix the bug",
        driver=driver,
        done_contract={"type": "object"},
        guardrails={"no_ship": True},
    )

    assert envelope.goal == "Fix the bug"
    assert envelope.driver == driver
    assert envelope.done_contract == {"type": "object"}
    assert envelope.guardrails == {"no_ship": True}


def test_result_has_all_fields():
    """Result has outcome, termination_reason, result_ref, error_summary, timestamps, payload, evidence_ref."""
    from engine.models import Result

    result = Result(
        outcome="ok",
        termination_reason="goal_met",
        result_ref="ref-123",
        error_summary=None,
        started_at=1234567890.0,
        ended_at=1234567900.0,
        payload={"result": "success"},
        evidence_ref="evidence://123",
    )

    assert result.outcome == "ok"
    assert result.termination_reason == "goal_met"
    assert result.result_ref == "ref-123"
    assert result.error_summary is None
    assert result.started_at == 1234567890.0
    assert result.ended_at == 1234567900.0
    assert result.payload == {"result": "success"}
    assert result.evidence_ref == "evidence://123"


def test_result_payload_defaults_to_empty_dict():
    """Result payload defaults to empty dict when not provided."""
    from engine.models import Result

    result = Result(
        outcome="ok",
        termination_reason="goal_met",
        result_ref="ref-123",
        error_summary=None,
        started_at=1234567890.0,
        ended_at=1234567900.0,
    )

    assert result.payload == {}


def test_result_evidence_ref_defaults_to_none():
    """Result evidence_ref defaults to None when not provided."""
    from engine.models import Result

    result = Result(
        outcome="ok",
        termination_reason="goal_met",
        result_ref="ref-123",
        error_summary=None,
        started_at=1234567890.0,
        ended_at=1234567900.0,
    )

    assert result.evidence_ref is None


def test_run_snapshot_has_required_fields():
    """Run snapshot has id, playbook, site, base_ref, config, phase, reductions."""
    from engine.models import Run

    run = Run(
        id="test-20260728-120000",
        playbook="example",
        site="local",
        base_ref="main",
        config={"key": "value"},
        phase="work",
        reductions=[],
    )

    assert run.id == "test-20260728-120000"
    assert run.playbook == "example"
    assert run.site == "local"
    assert run.base_ref == "main"
    assert run.config == {"key": "value"}
    assert run.phase == "work"
    assert run.reductions == []


def test_ticket_has_required_fields():
    """Ticket has id, run_id, phase, state, payload."""
    from engine.models import Ticket

    ticket = Ticket(
        id="run-1/t-0",
        run_id="run-1",
        phase="work",
        state="queued",
        resource_req="cpu",
        priority=0.0,
        attempts=0,
        payload={"task": "hello"},
    )

    assert ticket.id == "run-1/t-0"
    assert ticket.run_id == "run-1"
    assert ticket.phase == "work"
    assert ticket.state == "queued"
    assert ticket.resource_req == "cpu"
    assert ticket.payload == {"task": "hello"}


def test_health_report_has_checks_and_resources():
    """HealthReport has reachable, agent_ok, auth_ok, workspace_ready, guard_installed, resources, checks."""
    from engine.models import HealthReport, Check

    check = Check(name="test", ok=True, detail="OK")
    report = HealthReport(
        reachable=True,
        agent_ok=True,
        auth_ok=True,
        workspace_ready=True,
        guard_installed=True,
        resources={"cpu": 4},
        latency_ms=50,
        checks=[check],
    )

    assert report.reachable is True
    assert report.agent_ok is True
    assert report.resources == {"cpu": 4}
    assert report.latency_ms == 50
    assert len(report.checks) == 1
    assert report.checks[0].ok is True


def test_check_has_name_ok_detail():
    """Check has name, ok, detail."""
    from engine.models import Check

    check = Check(name="transport", ok=False, detail="Host unreachable")

    assert check.name == "transport"
    assert check.ok is False
    assert check.detail == "Host unreachable"


def test_issue_query_has_kind_filters_limit():
    """IssueQuery has kind, filters, limit."""
    from engine.models import IssueQuery

    query = IssueQuery(kind="bug", filters={"severity": "high"}, limit=50)

    assert query.kind == "bug"
    assert query.filters == {"severity": "high"}
    assert query.limit == 50


def test_issue_has_id_kind_title_ref_data():
    """Issue has id, kind, title, ref, data."""
    from engine.models import Issue

    issue = Issue(
        id="BUG-123",
        kind="bug",
        title="Fix null pointer",
        ref="https://example.com/BUG-123",
        data={"priority": "P0"},
    )

    assert issue.id == "BUG-123"
    assert issue.kind == "bug"
    assert issue.title == "Fix null pointer"
    assert issue.ref == "https://example.com/BUG-123"
    assert issue.data == {"priority": "P0"}


def test_reduction_has_kind_json():
    """Reduction has kind, json."""
    from engine.models import Reduction

    reduction = Reduction(kind="summary", json={"count": 5})

    assert reduction.kind == "summary"
    assert reduction.json == {"count": 5}


def test_reduction_carries_persistence_fields():
    """Reduction carries id, run_id, phase, kind, json, review_state."""
    from engine.models import Reduction

    # Persistence fields default so playbook-produced Reductions stay light.
    light = Reduction(kind="cluster", json={"x": 1})
    assert light.id is None
    assert light.run_id is None
    assert light.phase is None
    assert light.review_state == "pending"

    # A fully-hydrated Reduction (as loaded from the reductions table).
    full = Reduction(
        id=7,
        run_id="run-1",
        phase="work",
        kind="cluster",
        json={"clusters": {}},
        review_state="accepted",
    )
    assert full.id == 7
    assert full.run_id == "run-1"
    assert full.phase == "work"
    assert full.kind == "cluster"
    assert full.json == {"clusters": {}}
    assert full.review_state == "accepted"


def test_finding_has_run_id_ticket_id_kind_json():
    """Finding has run_id, ticket_id, kind, json."""
    from engine.models import Finding

    finding = Finding(
        run_id="run-1",
        ticket_id="run-1/t-0",
        kind="result",
        json={"answer": 42}
    )

    assert finding.run_id == "run-1"
    assert finding.ticket_id == "run-1/t-0"
    assert finding.kind == "result"
    assert finding.json == {"answer": 42}


def test_lease_has_required_fields():
    """Lease has id, run_id, resource_class, ticket_id, host, acquired_at, ttl_s, expires_at."""
    from engine.models import Lease

    lease = Lease(
        id="lease-1",
        run_id="run-1",
        resource_class="cpu",
        ticket_id="run-1/t-0",
        host="host-1",
        acquired_at=1234567890.0,
        ttl_s=1800,
        expires_at=1234569690.0,
    )

    assert lease.id == "lease-1"
    assert lease.run_id == "run-1"
    assert lease.resource_class == "cpu"
    assert lease.ticket_id == "run-1/t-0"
    assert lease.host == "host-1"
    assert lease.ttl_s == 1800


def test_crew_member_has_required_fields():
    """CrewMember has id, site, capabilities, resources, state."""
    from engine.models import CrewMember

    member = CrewMember(
        id="host-1",
        site="local",
        capabilities=["cpu"],
        resources={"cpu": 4},
        state="idle",
    )

    assert member.id == "host-1"
    assert member.site == "local"
    assert member.capabilities == ["cpu"]
    assert member.resources == {"cpu": 4}
    assert member.state == "idle"


def test_attempt_has_required_fields():
    """Attempt has ticket_id, phase, host, attempt, outcome, termination_reason."""
    from engine.models import Attempt

    attempt = Attempt(
        ticket_id="run-1/t-0",
        phase="work",
        host="host-1",
        attempt=1,
        started_at=1234567890.0,
        ended_at=1234567900.0,
        outcome="ok",
        termination_reason="goal_met",
        result_ref="ref-123",
        error_summary=None,
    )

    assert attempt.ticket_id == "run-1/t-0"
    assert attempt.phase == "work"
    assert attempt.host == "host-1"
    assert attempt.attempt == 1
    assert attempt.outcome == "ok"
    assert attempt.termination_reason == "goal_met"
