"""
tests.unit.test_server — FastAPI control-plane server (read endpoints).

TestClient against a real seeded run in a temp HERMES_HOME. No mocks.
"""
import json
import os
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.config import resolve_home
from engine.db.migrate import apply_migrations, connect
from engine.models import Run
from engine.queue import seed_tickets

# Import will fail initially — that's TDD
from server.app import create_app


@pytest.fixture
def temp_home(tmp_path: Path, monkeypatch):
    """A temp HERMES_HOME with migrations applied."""
    home = tmp_path / "hermes-test"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    # Apply migrations
    db_path = str(home / "queue.db")
    apply_migrations(db_path)
    yield home
    monkeypatch.delenv("HERMES_HOME", raising=False)


@pytest.fixture
def seeded_run(temp_home: Path):
    """A seeded run with real tickets in queue.db."""
    # Create canned issues for the EchoPlaybook
    from testkit import fixtures
    issues_dir = temp_home / "issues"
    issues_dir.mkdir(parents=True, exist_ok=True)
    fixtures.write_canned_issues(issues_dir / "bug.json")

    # Load local site
    from engine import site
    import sites.local  # noqa: F401
    local_site = site.load("local")

    db_path = str(temp_home / "queue.db")
    conn = connect(db_path)

    # Create a run
    run_id = "test-run-123"
    config = {"issue_kind": "bug"}
    conn.execute(
        """INSERT INTO runs
           (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            run_id, "example", "local", "running", "work", "main",
            json.dumps(config), "2026-07-29T00:00:00Z", "2026-07-29T00:00:00Z"
        ),
    )
    conn.commit()

    # Load the run and seed tickets
    run = Run(
        id=run_id, playbook="example", site="local",
        base_ref="main", config=config, phase="work", reductions=[]
    )

    # Load the EchoPlaybook to seed tickets
    from testkit.example_playbook import EchoPlaybook
    playbook = EchoPlaybook()

    # Seed tickets
    seed_tickets(conn, run, playbook, local_site)
    conn.close()

    return run_id


@pytest.fixture
def client(temp_home: Path):
    """TestClient for the FastAPI app."""
    app = create_app()
    return TestClient(app)


def test_health_endpoint(client: TestClient, temp_home: Path):
    """GET /api/health returns ok status with version and home."""
    response = client.get("/api/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert data["home"] == str(temp_home)
    # queue.db should exist after seeding
    assert (temp_home / "queue.db").exists()


def test_runs_list(client: TestClient, seeded_run: str, temp_home: Path):
    """GET /api/runs lists runs with ticket counts."""
    response = client.get("/api/runs")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1

    run = data[0]
    assert run["id"] == seeded_run
    assert run["playbook"] == "example"
    assert run["site"] == "local"
    assert run["state"] == "running"
    assert run["phase"] == "work"
    assert run["base_ref"] == "main"
    assert "created_at" in run

    # Ticket counts by state
    assert "tickets" in run
    tickets = run["tickets"]
    assert isinstance(tickets, dict)
    # EchoPlaybook seeds 3 tickets, all start as "queued"
    assert tickets.get("queued", 0) == 3
    assert sum(tickets.values()) == 3


def test_run_detail_phases_array(client: TestClient, seeded_run: str, temp_home: Path):
    """GET /api/runs/{id} returns phases as array in playbook order with real counts."""
    response = client.get(f"/api/runs/{seeded_run}")
    assert response.status_code == 200

    data = response.json()

    # Phases should be an array from the playbook's ordered phases
    assert "phases" in data
    phases = data["phases"]
    assert isinstance(phases, list)

    # EchoPlaybook has phases ["work", "reduce"]
    assert len(phases) == 2
    assert phases[0]["name"] == "work"
    assert phases[1]["name"] == "reduce"

    # Current phase should be marked
    assert phases[0]["current"] is True  # run.phase == "work"
    assert phases[1]["current"] is False

    # Counts should match sqlite query
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    # Work phase has 3 queued tickets
    work_counts = conn.execute(
        """SELECT state, COUNT(*) FROM tickets
           WHERE run_id=? AND phase='work' GROUP BY state""",
        (seeded_run,),
    ).fetchall()
    expected_work = {state: count for state, count in work_counts}

    assert "counts" in phases[0]
    assert phases[0]["counts"] == expected_work
    assert phases[0]["counts"]["queued"] == 3

    # Reduce phase has no tickets yet
    reduce_counts = conn.execute(
        """SELECT state, COUNT(*) FROM tickets
           WHERE run_id=? AND phase='reduce' GROUP BY state""",
        (seeded_run,),
    ).fetchall()
    expected_reduce = {state: count for state, count in reduce_counts}

    assert "counts" in phases[1]
    assert phases[1]["counts"] == expected_reduce
    # Should be empty since no tickets in reduce phase yet
    assert len(phases[1]["counts"]) == 0

    conn.close()


def test_run_detail_not_found(client: TestClient, temp_home: Path):
    """GET /api/runs/{unknown} returns 404."""
    response = client.get("/api/runs/unknown-run-id")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data


def test_health_with_empty_db(client: TestClient, temp_home: Path):
    """Health endpoint works even with no runs."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_runs_list_empty(client: TestClient, temp_home: Path):
    """GET /api/runs returns empty list when no runs exist."""
    response = client.get("/api/runs")
    assert response.status_code == 200
    assert response.json() == []


def test_tickets_endpoint_returns_tickets(client: TestClient, seeded_run: str, temp_home: Path):
    """GET /api/runs/{id}/tickets returns real tickets from queue.db."""
    response = client.get(f"/api/runs/{seeded_run}/tickets")
    assert response.status_code == 200

    tickets = response.json()
    assert isinstance(tickets, list)
    assert len(tickets) == 3  # EchoPlaybook seeds 3 tickets

    # Each ticket should have the required fields
    ticket = tickets[0]
    assert "id" in ticket
    assert "run_id" in ticket
    assert ticket["run_id"] == seeded_run
    assert "state" in ticket
    assert "phase" in ticket
    assert "subject" in ticket
    assert "resource_req" in ticket
    assert "host" in ticket
    assert "attempts" in ticket
    assert "elapsed_s" in ticket
    assert "priority" in ticket

    # Verify against direct sqlite query
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)
    db_tickets = conn.execute(
        """SELECT id, state, phase, resource_req, worker_host, attempts, priority
           FROM tickets WHERE run_id=? ORDER BY id""",
        (seeded_run,),
    ).fetchall()
    conn.close()

    assert len(tickets) == len(db_tickets)
    for t, db_row in zip(tickets, db_tickets):
        assert t["id"] == db_row[0]
        assert t["state"] == db_row[1]
        assert t["phase"] == db_row[2]
        assert t["resource_req"] == db_row[3]
        assert t["host"] == db_row[4]
        assert t["attempts"] == db_row[5]
        assert t["priority"] == db_row[6]


def test_tickets_filter_by_state(client: TestClient, seeded_run: str, temp_home: Path):
    """GET /api/runs/{id}/tickets?state=queued filters by state."""
    response = client.get(f"/api/runs/{seeded_run}/tickets?state=queued")
    assert response.status_code == 200

    tickets = response.json()
    assert all(t["state"] == "queued" for t in tickets)

    # Verify against sqlite
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)
    queued_count = conn.execute(
        """SELECT COUNT(*) FROM tickets WHERE run_id=? AND state='queued'""",
        (seeded_run,),
    ).fetchone()[0]
    conn.close()

    assert len(tickets) == queued_count
    assert len(tickets) == 3  # All seeded tickets start as queued


def test_tickets_filter_by_phase(client: TestClient, seeded_run: str, temp_home: Path):
    """GET /api/runs/{id}/tickets?phase=work filters by phase."""
    response = client.get(f"/api/runs/{seeded_run}/tickets?phase=work")
    assert response.status_code == 200

    tickets = response.json()
    assert all(t["phase"] == "work" for t in tickets)

    # Verify against sqlite
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)
    work_count = conn.execute(
        """SELECT COUNT(*) FROM tickets WHERE run_id=? AND phase='work'""",
        (seeded_run,),
    ).fetchone()[0]
    conn.close()

    assert len(tickets) == work_count


def test_tickets_filter_by_resource(client: TestClient, seeded_run: str, temp_home: Path):
    """GET /api/runs/{id}/tickets?resource=cpu filters by resource_req."""
    response = client.get(f"/api/runs/{seeded_run}/tickets?resource=cpu")
    assert response.status_code == 200

    tickets = response.json()
    assert all(t["resource_req"] == "cpu" for t in tickets)

    # Verify against sqlite
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)
    cpu_count = conn.execute(
        """SELECT COUNT(*) FROM tickets WHERE run_id=? AND resource_req='cpu'""",
        (seeded_run,),
    ).fetchone()[0]
    conn.close()

    assert len(tickets) == cpu_count


def test_tickets_filter_by_host(client: TestClient, seeded_run: str, temp_home: Path):
    """GET /api/runs/{id}/tickets?host=localhost filters by worker_host."""
    # First, update a ticket to have a host
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)
    # Get first ticket id
    ticket_id = conn.execute(
        "SELECT id FROM tickets WHERE run_id=? ORDER BY id LIMIT 1",
        (seeded_run,),
    ).fetchone()[0]
    conn.execute(
        "UPDATE tickets SET worker_host='localhost' WHERE id=?",
        (ticket_id,),
    )
    conn.commit()
    conn.close()

    response = client.get(f"/api/runs/{seeded_run}/tickets?host=localhost")
    assert response.status_code == 200

    tickets = response.json()
    assert all(t["host"] == "localhost" for t in tickets)
    assert len(tickets) == 1


def test_tickets_filter_by_search(client: TestClient, seeded_run: str, temp_home: Path):
    """GET /api/runs/{id}/tickets?search=t-0 searches id and subject."""
    response = client.get(f"/api/runs/{seeded_run}/tickets?search=t-0")
    assert response.status_code == 200

    tickets = response.json()
    # Should match ticket id containing 't-0'
    assert any("t-0" in t["id"] for t in tickets)


def test_tickets_multiple_filters(client: TestClient, seeded_run: str, temp_home: Path):
    """GET /api/runs/{id}/tickets with multiple filters combines with AND."""
    response = client.get(f"/api/runs/{seeded_run}/tickets?state=queued&phase=work")
    assert response.status_code == 200

    tickets = response.json()
    assert all(t["state"] == "queued" and t["phase"] == "work" for t in tickets)

    # Verify against sqlite
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)
    count = conn.execute(
        """SELECT COUNT(*) FROM tickets
           WHERE run_id=? AND state='queued' AND phase='work'""",
        (seeded_run,),
    ).fetchone()[0]
    conn.close()

    assert len(tickets) == count


def test_tickets_unknown_run_404(client: TestClient, temp_home: Path):
    """GET /api/runs/{unknown}/tickets returns 404."""
    response = client.get("/api/runs/unknown-run/tickets")
    assert response.status_code == 404


def test_ticket_detail_with_attempts(client: TestClient, seeded_run: str, temp_home: Path):
    """GET /api/tickets/{id} returns full ticket detail with payload, result, attempts, evidence."""
    # Get a ticket id from the seeded run
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    ticket_id = conn.execute(
        "SELECT id FROM tickets WHERE run_id=? ORDER BY id LIMIT 1",
        (seeded_run,),
    ).fetchone()[0]

    # Insert multiple attempts for this ticket
    import time
    now = time.time()

    # Attempt 1: failed
    conn.execute(
        """INSERT INTO attempts
           (ticket_id, phase, host, attempt, started_at, ended_at, outcome,
            termination_reason, result_ref, error_summary)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            ticket_id, "work", "worker-1", 1,
            now - 300, now - 280,
            "driver_failed", "driver_error",
            None, "timeout in phase 1"
        ),
    )

    # Attempt 2: succeeded (this is the LATEST)
    conn.execute(
        """INSERT INTO attempts
           (ticket_id, phase, host, attempt, started_at, ended_at, outcome,
            termination_reason, result_ref, error_summary)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            ticket_id, "work", "worker-2", 2,
            now - 100, now - 50,
            "ok", "goal_met",
            "s3://results/ticket-1.json", None
        ),
    )

    conn.commit()

    # Fetch the ticket detail
    response = client.get(f"/api/tickets/{ticket_id}")
    assert response.status_code == 200

    data = response.json()

    # Should have ticket fields
    assert "ticket" in data
    ticket = data["ticket"]
    assert ticket["id"] == ticket_id
    assert ticket["run_id"] == seeded_run
    assert ticket["phase"] == "work"
    assert ticket["state"] == "queued"
    assert "resource_req" in ticket
    assert "priority" in ticket
    assert "attempts" in ticket
    assert "host" in ticket
    assert "subject" in ticket
    assert "created_at" in ticket
    assert "updated_at" in ticket

    # Should have parsed payload
    assert "payload" in data
    payload = data["payload"]
    assert isinstance(payload, dict)
    # Verify it's actually the parsed JSON, not a string (seeded data has issue_id/title)
    assert len(payload) > 0  # Non-empty dict means it was parsed

    # Should have result (strict latest = max id attempt)
    assert "result" in data
    result = data["result"]
    assert result is not None

    # Result should match attempt 2 (the max id attempt)
    latest_attempt = conn.execute(
        """SELECT outcome, termination_reason, result_ref, error_summary,
                  started_at, ended_at
           FROM attempts WHERE ticket_id=? ORDER BY id DESC LIMIT 1""",
        (ticket_id,),
    ).fetchone()

    assert result["outcome"] == latest_attempt[0]
    assert result["termination_reason"] == latest_attempt[1]
    assert result["result_ref"] == latest_attempt[2]
    assert result["error_summary"] == latest_attempt[3]
    assert result["started_at"] == latest_attempt[4]
    assert result["ended_at"] == latest_attempt[5]

    # Should have attempt_timeline (all attempts, ordered)
    assert "attempt_timeline" in data
    timeline = data["attempt_timeline"]
    assert len(timeline) == 2

    # Verify timeline order (oldest first)
    assert timeline[0]["attempt"] == 1
    assert timeline[0]["host"] == "worker-1"
    assert timeline[0]["outcome"] == "driver_failed"
    assert timeline[0]["termination_reason"] == "driver_error"
    assert timeline[0]["result_ref"] is None
    assert timeline[0]["error_summary"] == "timeout in phase 1"

    assert timeline[1]["attempt"] == 2
    assert timeline[1]["host"] == "worker-2"
    assert timeline[1]["outcome"] == "ok"
    assert timeline[1]["termination_reason"] == "goal_met"
    assert timeline[1]["result_ref"] == "s3://results/ticket-1.json"
    assert timeline[1]["error_summary"] is None

    # Should have evidence (non-null result_refs)
    assert "evidence" in data
    evidence = data["evidence"]
    assert len(evidence) == 1
    assert evidence[0]["attempt"] == 2
    assert evidence[0]["ref"] == "s3://results/ticket-1.json"

    conn.close()


def test_ticket_detail_no_attempts(client: TestClient, seeded_run: str, temp_home: Path):
    """GET /api/tickets/{id} returns null result when no attempts exist."""
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    ticket_id = conn.execute(
        "SELECT id FROM tickets WHERE run_id=? ORDER BY id LIMIT 1",
        (seeded_run,),
    ).fetchone()[0]

    conn.close()

    # No attempts inserted, so result should be null
    response = client.get(f"/api/tickets/{ticket_id}")
    assert response.status_code == 200

    data = response.json()
    assert "result" in data
    assert data["result"] is None

    assert "attempt_timeline" in data
    assert len(data["attempt_timeline"]) == 0

    assert "evidence" in data
    assert len(data["evidence"]) == 0


def test_ticket_detail_not_found(client: TestClient, temp_home: Path):
    """GET /api/tickets/{unknown} returns 404."""
    response = client.get("/api/tickets/unknown-ticket-id")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
