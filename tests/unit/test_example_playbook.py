"""Tests for testkit.example_playbook.EchoPlaybook.

TDD: written first.
"""
import json

import pytest

from testkit import fixtures


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def canned(home):
    """Write a canned issue file the local site can read for kind=bug."""
    issues_dir = home / "issues"
    issues_dir.mkdir(parents=True, exist_ok=True)
    path = issues_dir / "bug.json"
    fixtures.write_canned_issues(path)
    return path


def _run(config=None, phase="work"):
    from engine.models import Run

    return Run(
        id="example-20260728-000000",
        playbook="example",
        site="local",
        base_ref="main",
        config=config or {},
        phase=phase,
        reductions=[],
    )


def test_name_and_phases():
    from testkit.example_playbook import EchoPlaybook

    pb = EchoPlaybook()
    assert pb.name == "example"
    assert pb.phases[0] == "work"
    assert len(pb.phases) >= 1


def test_seed_yields_one_ticket_per_canned_issue(home, canned):
    from testkit.example_playbook import EchoPlaybook
    from engine import site
    import sites.local  # noqa: F401

    st = site.load("local")
    pb = EchoPlaybook()
    run = _run(config={"issue_kind": "bug"})

    tickets = pb.seed(run, st)

    n_issues = len(fixtures.CANNED_ISSUES)
    assert len(tickets) == n_issues
    # Each ticket belongs to the run and is queued in the seeding phase
    for t in tickets:
        assert t.run_id == run.id
        assert t.state == "queued"
        assert t.phase == "work"
    # Distinct ticket ids
    assert len({t.id for t in tickets}) == n_issues


def test_payload_and_result_schemas_are_dicts():
    from testkit.example_playbook import EchoPlaybook

    pb = EchoPlaybook()
    for phase in pb.phases:
        assert isinstance(pb.payload_schema(phase), dict)
        assert isinstance(pb.result_schema(phase), dict)


def test_driver_returns_driver():
    from testkit.example_playbook import EchoPlaybook
    from engine.models import Driver

    pb = EchoPlaybook()
    d = pb.driver("work")
    assert isinstance(d, Driver)


def test_verify_true_by_default_false_under_config():
    from testkit.example_playbook import EchoPlaybook
    from engine.models import Ticket, Result

    pb = EchoPlaybook()
    ticket = Ticket(
        id="example-20260728-000000/t-0", run_id="example-20260728-000000",
        phase="work", state="running", resource_req="cpu", priority=0.0,
        attempts=0, payload={},
    )
    result = Result(
        outcome="ok", termination_reason="goal_met", result_ref="r",
        error_summary=None, started_at=0.0, ended_at=1.0,
    )

    assert pb.verify(_run(), ticket, result, None) is True
    assert pb.verify(_run(config={"verify_fail": True}), ticket, result, None) is False


def test_reduce_clusters_findings():
    from testkit.example_playbook import EchoPlaybook
    from engine.models import Finding, Reduction

    pb = EchoPlaybook()
    findings = [
        Finding(kind="echo", json={"ticket_id": "t-0", "cluster": "a"}),
        Finding(kind="echo", json={"ticket_id": "t-1", "cluster": "a"}),
        Finding(kind="echo", json={"ticket_id": "t-2", "cluster": "b"}),
    ]
    reductions = pb.reduce(_run(phase="reduce"), "reduce", findings, None)
    assert len(reductions) >= 1
    assert all(isinstance(r, Reduction) for r in reductions)


def test_reduce_emits_needs_human_when_configured():
    from testkit.example_playbook import EchoPlaybook

    pb = EchoPlaybook()
    findings_ids = ["t-0", "t-1"]
    from engine.models import Finding

    findings = [Finding(kind="echo", json={"ticket_id": tid, "cluster": "a"})
                for tid in findings_ids]
    run = _run(phase="reduce", config={"needs_human": True})

    reductions = pb.reduce(run, "reduce", findings, None)
    # At least one reduction carries needs_human_ticket_ids
    flagged = [r for r in reductions if r.json.get("needs_human_ticket_ids")]
    assert flagged
    assert set(flagged[0].json["needs_human_ticket_ids"]) == set(findings_ids)


def test_next_phase_and_is_done():
    from testkit.example_playbook import EchoPlaybook

    pb = EchoPlaybook()
    # First phase advances to the next
    assert pb.next_phase(_run(phase=pb.phases[0])) == pb.phases[1] if len(pb.phases) > 1 else True
    # Last phase -> None
    assert pb.next_phase(_run(phase=pb.phases[-1])) is None
    assert pb.is_done(_run(phase=pb.phases[-1])) is True
