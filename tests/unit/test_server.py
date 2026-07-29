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
