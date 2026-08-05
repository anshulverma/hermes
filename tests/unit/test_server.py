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


def _record_attempt(conn, ticket_id: str, attempt: int, outcome: str) -> None:
    """Append one row to the append-only attempts audit table."""
    import time
    now = time.time()
    conn.execute(
        """INSERT INTO attempts
           (ticket_id, phase, host, attempt, started_at, ended_at, outcome,
            termination_reason, result_ref, error_summary)
           VALUES (?, 'work', 'worker-1', ?, ?, ?, ?, ?, NULL, NULL)""",
        (
            ticket_id, attempt, now - 10, now, outcome,
            "goal_met" if outcome == "ok" else "driver_error",
        ),
    )
    conn.commit()


def test_tickets_attempts_field_counts_recorded_attempts(
    client: TestClient, seeded_run: str, temp_home: Path
):
    """The bulk list reports how many attempts actually ran, not the retry budget."""
    conn = sqlite3.connect(str(temp_home / "queue.db"))
    ticket_ids = [
        row[0] for row in conn.execute(
            "SELECT id FROM tickets WHERE run_id=? ORDER BY id", (seeded_run,)
        ).fetchall()
    ]
    assert len(ticket_ids) >= 3

    # One ticket ran once and succeeded; another ran twice; the third never ran.
    _record_attempt(conn, ticket_ids[0], 1, "ok")
    _record_attempt(conn, ticket_ids[1], 1, "driver_failed")
    _record_attempt(conn, ticket_ids[1], 2, "ok")

    # The infra-retry budget column stays where the engine left it (zero): the
    # API must not be reading it.
    budgets = conn.execute(
        "SELECT attempts FROM tickets WHERE run_id=?", (seeded_run,)
    ).fetchall()
    assert {b[0] for b in budgets} == {0}
    conn.close()

    tickets = client.get(f"/api/runs/{seeded_run}/tickets").json()
    by_id = {t["id"]: t for t in tickets}

    assert by_id[ticket_ids[0]]["attempts"] == 1
    assert by_id[ticket_ids[1]]["attempts"] == 2
    assert by_id[ticket_ids[2]]["attempts"] == 0


def test_ticket_detail_attempts_field_counts_recorded_attempts(
    client: TestClient, seeded_run: str, temp_home: Path
):
    """The detail endpoint agrees with its own attempt timeline."""
    conn = sqlite3.connect(str(temp_home / "queue.db"))
    ticket_id = conn.execute(
        "SELECT id FROM tickets WHERE run_id=? ORDER BY id LIMIT 1", (seeded_run,)
    ).fetchone()[0]
    _record_attempt(conn, ticket_id, 1, "ok")
    conn.close()

    data = client.get(f"/api/tickets/{ticket_id}").json()
    assert data["ticket"]["attempts"] == 1
    assert len(data["attempt_timeline"]) == 1


def test_ticket_detail_attempts_zero_without_attempts(
    client: TestClient, seeded_run: str, temp_home: Path
):
    """A ticket that never ran reports zero attempts."""
    conn = sqlite3.connect(str(temp_home / "queue.db"))
    ticket_id = conn.execute(
        "SELECT id FROM tickets WHERE run_id=? ORDER BY id LIMIT 1", (seeded_run,)
    ).fetchone()[0]
    conn.close()

    data = client.get(f"/api/tickets/{ticket_id}").json()
    assert data["ticket"]["attempts"] == 0


def test_tickets_subject_prefers_payload_title(
    client: TestClient, seeded_run: str, temp_home: Path
):
    """An explicit title wins over the goal, in both the list and the detail."""
    conn = sqlite3.connect(str(temp_home / "queue.db"))
    ticket_id = conn.execute(
        "SELECT id FROM tickets WHERE run_id=? ORDER BY id LIMIT 1", (seeded_run,)
    ).fetchone()[0]
    payload = json.loads(
        conn.execute(
            "SELECT payload_json FROM tickets WHERE id=?", (ticket_id,)
        ).fetchone()[0]
    )
    payload["title"] = "Research item widget-7 and report what it does"
    payload["goal"] = "Do the thing.\n" + ("x" * 9000)
    conn.execute(
        "UPDATE tickets SET payload_json=? WHERE id=?",
        (json.dumps(payload), ticket_id),
    )
    conn.commit()
    conn.close()

    listed = {
        t["id"]: t for t in client.get(f"/api/runs/{seeded_run}/tickets").json()
    }
    assert listed[ticket_id]["subject"] == "Research item widget-7 and report what it does"

    detail = client.get(f"/api/tickets/{ticket_id}").json()
    assert detail["ticket"]["subject"] == "Research item widget-7 and report what it does"


def test_tickets_subject_falls_back_to_a_capped_single_line_goal(
    client: TestClient, seeded_run: str, temp_home: Path
):
    """Without a title the goal is still used, but never as kilobytes of prose."""
    conn = sqlite3.connect(str(temp_home / "queue.db"))
    ticket_id = conn.execute(
        "SELECT id FROM tickets WHERE run_id=? ORDER BY id LIMIT 1", (seeded_run,)
    ).fetchone()[0]
    payload = json.loads(
        conn.execute(
            "SELECT payload_json FROM tickets WHERE id=?", (ticket_id,)
        ).fetchone()[0]
    )
    payload.pop("title", None)
    payload["goal"] = "Investigate the flaky cache " + ("blah " * 3000) + "\nsecond line"
    conn.execute(
        "UPDATE tickets SET payload_json=? WHERE id=?",
        (json.dumps(payload), ticket_id),
    )
    conn.commit()
    conn.close()

    listed = {
        t["id"]: t for t in client.get(f"/api/runs/{seeded_run}/tickets").json()
    }
    subject = listed[ticket_id]["subject"]
    assert subject.startswith("Investigate the flaky cache")
    assert "\n" not in subject
    assert len(subject) <= 200

    detail_subject = client.get(f"/api/tickets/{ticket_id}").json()["ticket"]["subject"]
    assert detail_subject == subject


def test_tickets_subject_placeholder_when_payload_has_neither(
    client: TestClient, seeded_run: str, temp_home: Path
):
    """A payload with no title and no goal still yields the em-dash placeholder."""
    conn = sqlite3.connect(str(temp_home / "queue.db"))
    ticket_id = conn.execute(
        "SELECT id FROM tickets WHERE run_id=? ORDER BY id LIMIT 1", (seeded_run,)
    ).fetchone()[0]
    conn.execute(
        "UPDATE tickets SET payload_json=? WHERE id=?", ('{"other": 1}', ticket_id)
    )
    conn.commit()
    conn.close()

    listed = {
        t["id"]: t for t in client.get(f"/api/runs/{seeded_run}/tickets").json()
    }
    assert listed[ticket_id]["subject"] == "—"


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


def test_events_endpoint_returns_events_ascending(client: TestClient, seeded_run: str, temp_home: Path):
    """GET /api/events returns events with id > since, ordered by id ascending with all fields."""
    # Seed some events directly in sqlite
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    import time
    now = time.time()

    # Insert events of different kinds
    conn.execute(
        """INSERT INTO events (ts, kind, run_id, ticket_id, host, message, data_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (now - 10, "ticket_claimed", seeded_run, f"{seeded_run}/t-0", "worker-1", "Claimed ticket", '{"priority": 10}'),
    )
    conn.execute(
        """INSERT INTO events (ts, kind, run_id, ticket_id, host, message, data_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (now - 5, "result_recorded", seeded_run, f"{seeded_run}/t-0", "worker-1", "Recorded result", '{"outcome": "done"}'),
    )
    conn.execute(
        """INSERT INTO events (ts, kind, run_id, ticket_id, host, message, data_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (now, "phase_advanced", seeded_run, None, None, "Advanced to reduce", '{"from": "work", "to": "reduce"}'),
    )
    conn.commit()

    # Get all events (since=0)
    response = client.get("/api/events")
    assert response.status_code == 200

    events = response.json()
    assert isinstance(events, list)
    assert len(events) >= 3  # At least our 3 events

    # Find our events
    claimed = next((e for e in events if e["kind"] == "ticket_claimed"), None)
    result = next((e for e in events if e["kind"] == "result_recorded"), None)
    phase = next((e for e in events if e["kind"] == "phase_advanced"), None)

    assert claimed is not None
    assert result is not None
    assert phase is not None

    # Verify all fields present
    assert "id" in claimed
    assert "ts" in claimed
    assert claimed["kind"] == "ticket_claimed"
    assert claimed["run_id"] == seeded_run
    assert claimed["ticket_id"] == f"{seeded_run}/t-0"
    assert claimed["host"] == "worker-1"
    assert claimed["message"] == "Claimed ticket"
    assert claimed["data"] == {"priority": 10}  # data should be parsed

    # Verify ascending id order
    ids = [e["id"] for e in events]
    assert ids == sorted(ids)

    conn.close()


def test_events_since_parameter(client: TestClient, seeded_run: str, temp_home: Path):
    """GET /api/events?since=N returns only events with id > N."""
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    import time
    now = time.time()

    # Insert 5 events
    for i in range(5):
        conn.execute(
            """INSERT INTO events (ts, kind, run_id, message, data_json)
               VALUES (?, ?, ?, ?, ?)""",
            (now + i, "attention", seeded_run, f"Event {i}", '{}'),
        )
    conn.commit()

    # Get event IDs
    event_ids = [row[0] for row in conn.execute("SELECT id FROM events ORDER BY id").fetchall()]

    conn.close()

    # Query events after the 2nd event
    response = client.get(f"/api/events?since={event_ids[1]}")
    assert response.status_code == 200

    events = response.json()
    # Should return events with id > event_ids[1]
    returned_ids = [e["id"] for e in events]

    # All returned ids should be greater than since
    assert all(eid > event_ids[1] for eid in returned_ids)


def test_events_kind_filter(client: TestClient, seeded_run: str, temp_home: Path):
    """GET /api/events?kind=X filters to that kind only."""
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    import time
    now = time.time()

    # Insert events of different kinds
    conn.execute(
        """INSERT INTO events (ts, kind, run_id, message, data_json)
           VALUES (?, ?, ?, ?, ?)""",
        (now, "ticket_claimed", seeded_run, "Claimed", '{}'),
    )
    conn.execute(
        """INSERT INTO events (ts, kind, run_id, message, data_json)
           VALUES (?, ?, ?, ?, ?)""",
        (now + 1, "result_recorded", seeded_run, "Recorded", '{}'),
    )
    conn.execute(
        """INSERT INTO events (ts, kind, run_id, message, data_json)
           VALUES (?, ?, ?, ?, ?)""",
        (now + 2, "ticket_claimed", seeded_run, "Claimed 2", '{}'),
    )
    conn.commit()
    conn.close()

    # Filter to ticket_claimed only
    response = client.get("/api/events?kind=ticket_claimed")
    assert response.status_code == 200

    events = response.json()
    # Should only return ticket_claimed events
    assert all(e["kind"] == "ticket_claimed" for e in events)

    # Should have at least our 2 ticket_claimed events
    claimed_events = [e for e in events if e["message"] in ["Claimed", "Claimed 2"]]
    assert len(claimed_events) == 2


def test_events_limit_parameter(client: TestClient, seeded_run: str, temp_home: Path):
    """GET /api/events?limit=N bounds the result count."""
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    import time
    now = time.time()

    # Insert 10 events
    for i in range(10):
        conn.execute(
            """INSERT INTO events (ts, kind, run_id, message, data_json)
               VALUES (?, ?, ?, ?, ?)""",
            (now + i, "attention", seeded_run, f"Event {i}", '{}'),
        )
    conn.commit()
    conn.close()

    # Query with limit=3
    response = client.get("/api/events?limit=3")
    assert response.status_code == 200

    events = response.json()
    # Should return at most 3 events
    assert len(events) <= 3


def test_events_kind_and_limit_together(client: TestClient, seeded_run: str, temp_home: Path):
    """GET /api/events?kind=X&limit=N: limit should bound matched rows."""
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    import time
    now = time.time()

    # Insert 10 events: 5 ticket_claimed, 5 result_recorded
    for i in range(5):
        conn.execute(
            """INSERT INTO events (ts, kind, run_id, message, data_json)
               VALUES (?, ?, ?, ?, ?)""",
            (now + i, "ticket_claimed", seeded_run, f"Claimed {i}", '{}'),
        )
        conn.execute(
            """INSERT INTO events (ts, kind, run_id, message, data_json)
               VALUES (?, ?, ?, ?, ?)""",
            (now + i + 0.5, "result_recorded", seeded_run, f"Recorded {i}", '{}'),
        )
    conn.commit()
    conn.close()

    # Query with kind=ticket_claimed and limit=2
    response = client.get("/api/events?kind=ticket_claimed&limit=2")
    assert response.status_code == 200

    events = response.json()
    # Should return at most 2 ticket_claimed events
    assert len(events) <= 2
    assert all(e["kind"] == "ticket_claimed" for e in events)


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


def test_crew_endpoint_returns_all_members(client: TestClient, temp_home: Path):
    """GET /api/crew returns all crew members with parsed resources, capabilities, and health."""
    import time
    now = time.time()
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    # Seed crew members with varied states and health
    members = [
        {
            "id": "host-1",
            "site": "local",
            "state": "idle",
            "capabilities": '["python", "gpu"]',
            "resources_json": '{"cpu": 8, "gpu": 2}',
            "health_json": json.dumps({
                "reachable": True,
                "agent_ok": True,
                "auth_ok": True,
                "workspace_ready": True,
                "guard_installed": True,
                "latency_ms": 42
            }),
            "current_ticket": None,
            "last_heartbeat": now - 10,
            "registered_at": now - 3600
        },
        {
            "id": "host-2",
            "site": "local",
            "state": "busy",
            "capabilities": '["python"]',
            "resources_json": '{"cpu": 4}',
            "health_json": json.dumps({
                "reachable": True,
                "agent_ok": False,
                "auth_ok": True,
                "workspace_ready": True,
                "guard_installed": True,
                "latency_ms": 150
            }),
            "current_ticket": "test-run/t-1",
            "last_heartbeat": now - 5,
            "registered_at": now - 7200
        },
        {
            "id": "host-3",
            "site": "local",
            "state": "down",
            "capabilities": '[]',
            "resources_json": '{"cpu": 16}',
            "health_json": None,  # Never set
            "current_ticket": None,
            "last_heartbeat": now - 600,
            "registered_at": now - 1800
        }
    ]

    for m in members:
        conn.execute(
            """INSERT INTO crew
               (id, site, state, capabilities, resources_json, health_json,
                current_ticket, last_heartbeat, registered_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (m["id"], m["site"], m["state"], m["capabilities"],
             m["resources_json"], m["health_json"], m["current_ticket"],
             m["last_heartbeat"], m["registered_at"])
        )
    conn.commit()

    # Fetch crew
    response = client.get("/api/crew")
    assert response.status_code == 200

    crew = response.json()
    assert len(crew) == 3

    # Verify against direct sqlite query
    db_crew = conn.execute(
        """SELECT id, site, state, capabilities, resources_json, health_json,
                  current_ticket, last_heartbeat
           FROM crew ORDER BY id"""
    ).fetchall()
    conn.close()

    # Sort both by id for comparison
    crew_sorted = sorted(crew, key=lambda x: x["id"])

    for c, db_row in zip(crew_sorted, db_crew):
        assert c["id"] == db_row[0]
        assert c["site"] == db_row[1]
        assert c["state"] == db_row[2]

        # Capabilities and resources should be parsed
        assert c["capabilities"] == json.loads(db_row[3])
        assert c["resources"] == json.loads(db_row[4])

        # Health should be parsed (or null)
        if db_row[5]:
            health = json.loads(db_row[5])
            assert c["health"]["reachable"] == health["reachable"]
            assert c["health"]["agent_ok"] == health["agent_ok"]
            assert c["health"]["auth_ok"] == health["auth_ok"]
            assert c["health"]["workspace_ready"] == health["workspace_ready"]
            assert c["health"]["guard_installed"] == health["guard_installed"]
            assert c["health"]["latency_ms"] == health["latency_ms"]
        else:
            assert c["health"] is None

        assert c["current_ticket"] == db_row[6]
        assert c["last_heartbeat"] == db_row[7]


def test_leases_endpoint_returns_only_live_leases(client: TestClient, seeded_run: str, temp_home: Path):
    """GET /api/leases returns only live (unexpired) leases with correct remaining_s."""
    import time
    now = time.time()
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    # Seed leases: some live, some expired
    leases = [
        {
            "id": "lease-1",
            "run_id": seeded_run,
            "resource_class": "cpu",
            "ticket_id": f"{seeded_run}/t-0",
            "host": "host-1",
            "acquired_at": now - 600,
            "ttl_s": 1800,
            "expires_at": now + 1200  # Live (expires in 20 min)
        },
        {
            "id": "lease-2",
            "run_id": seeded_run,
            "resource_class": "gpu",
            "ticket_id": f"{seeded_run}/t-1",
            "host": "host-2",
            "acquired_at": now - 3600,
            "ttl_s": 1800,
            "expires_at": now - 1800  # Expired 30 min ago
        },
        {
            "id": "lease-3",
            "run_id": seeded_run,
            "resource_class": "cpu",
            "ticket_id": f"{seeded_run}/t-2",
            "host": "host-1",
            "acquired_at": now - 300,
            "ttl_s": 1800,
            "expires_at": now + 1500  # Live (expires in 25 min)
        }
    ]

    for lease in leases:
        conn.execute(
            """INSERT INTO leases
               (id, run_id, resource_class, ticket_id, host, acquired_at, ttl_s, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (lease["id"], lease["run_id"], lease["resource_class"],
             lease["ticket_id"], lease["host"], lease["acquired_at"],
             lease["ttl_s"], lease["expires_at"])
        )
    conn.commit()

    # Fetch leases (should only return live ones)
    response = client.get("/api/leases")
    assert response.status_code == 200

    leases_resp = response.json()
    assert len(leases_resp) == 2  # Only lease-1 and lease-3 are live

    # Verify all returned leases are live
    for lease in leases_resp:
        assert lease["expires_at"] > now

        # Verify remaining_s is correct
        expected_remaining = max(0, lease["expires_at"] - now)
        # Allow 1s tolerance for timing
        assert abs(lease["remaining_s"] - expected_remaining) <= 1

    # Verify against direct sqlite query
    db_live_leases = conn.execute(
        """SELECT id, resource_class, ticket_id, host, acquired_at, ttl_s, expires_at
           FROM leases WHERE expires_at > ?
           ORDER BY id""",
        (now,)
    ).fetchall()
    conn.close()

    assert len(leases_resp) == len(db_live_leases)

    # Sort both by id for comparison
    leases_sorted = sorted(leases_resp, key=lambda x: x["id"])

    for lease, db_row in zip(leases_sorted, db_live_leases):
        assert lease["id"] == db_row[0]
        assert lease["resource_class"] == db_row[1]
        assert lease["ticket_id"] == db_row[2]
        assert lease["host"] == db_row[3]
        assert lease["acquired_at"] == db_row[4]
        assert lease["ttl_s"] == db_row[5]
        assert lease["expires_at"] == db_row[6]


def test_leases_endpoint_host_filter(client: TestClient, seeded_run: str, temp_home: Path):
    """GET /api/leases?host=<id> filters to that host's leases only."""
    import time
    now = time.time()
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    # Seed leases for different hosts
    leases = [
        {
            "id": "lease-h1-1",
            "run_id": seeded_run,
            "resource_class": "cpu",
            "ticket_id": f"{seeded_run}/t-0",
            "host": "host-1",
            "acquired_at": now - 300,
            "ttl_s": 1800,
            "expires_at": now + 1500
        },
        {
            "id": "lease-h2-1",
            "run_id": seeded_run,
            "resource_class": "gpu",
            "ticket_id": f"{seeded_run}/t-1",
            "host": "host-2",
            "acquired_at": now - 200,
            "ttl_s": 1800,
            "expires_at": now + 1600
        },
        {
            "id": "lease-h1-2",
            "run_id": seeded_run,
            "resource_class": "cpu",
            "ticket_id": f"{seeded_run}/t-2",
            "host": "host-1",
            "acquired_at": now - 100,
            "ttl_s": 1800,
            "expires_at": now + 1700
        }
    ]

    for lease in leases:
        conn.execute(
            """INSERT INTO leases
               (id, run_id, resource_class, ticket_id, host, acquired_at, ttl_s, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (lease["id"], lease["run_id"], lease["resource_class"],
             lease["ticket_id"], lease["host"], lease["acquired_at"],
             lease["ttl_s"], lease["expires_at"])
        )
    conn.commit()
    conn.close()

    # Fetch leases for host-1
    response = client.get("/api/leases?host=host-1")
    assert response.status_code == 200

    leases_resp = response.json()
    assert len(leases_resp) == 2  # lease-h1-1 and lease-h1-2

    # Verify all returned leases are for host-1
    for lease in leases_resp:
        assert lease["host"] == "host-1"

    # Verify IDs match
    lease_ids = {lease["id"] for lease in leases_resp}
    assert lease_ids == {"lease-h1-1", "lease-h1-2"}


def test_leases_endpoint_empty_when_all_expired(client: TestClient, seeded_run: str, temp_home: Path):
    """GET /api/leases returns empty list when all leases are expired."""
    import time
    now = time.time()
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    # Seed only expired leases
    conn.execute(
        """INSERT INTO leases
           (id, run_id, resource_class, ticket_id, host, acquired_at, ttl_s, expires_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("expired-lease", seeded_run, "cpu", f"{seeded_run}/t-0",
         "host-1", now - 3600, 1800, now - 1800)
    )
    conn.commit()
    conn.close()

    response = client.get("/api/leases")
    assert response.status_code == 200

    leases = response.json()
    assert len(leases) == 0


def test_event_kinds_endpoint_returns_distinct_sorted_kinds(client: TestClient, seeded_run: str, temp_home: Path):
    """GET /api/events/kinds returns DISTINCT event kinds sorted, matching SELECT DISTINCT kind."""
    # Seed events with ≥3 distinct kinds (with duplicates)
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    import time
    now = time.time()

    # Insert events: 3 distinct kinds with duplicates
    kinds_to_insert = [
        "ticket_claimed",
        "result_recorded",
        "ticket_claimed",  # duplicate
        "phase_advanced",
        "result_recorded",  # duplicate
        "ticket_claimed",  # duplicate
    ]

    for i, kind in enumerate(kinds_to_insert):
        conn.execute(
            """INSERT INTO events (ts, kind, run_id, message, data_json)
               VALUES (?, ?, ?, ?, ?)""",
            (now + i, kind, seeded_run, f"Event {i}", '{}'),
        )
    conn.commit()

    # Get expected kinds from direct SELECT DISTINCT query
    expected_kinds = [
        row[0] for row in conn.execute(
            "SELECT DISTINCT kind FROM events ORDER BY kind"
        ).fetchall()
    ]
    conn.close()

    # Endpoint should return the same
    response = client.get("/api/events/kinds")
    assert response.status_code == 200

    kinds = response.json()
    assert isinstance(kinds, list)

    # Should match the DISTINCT query result
    assert kinds == expected_kinds

    # Verify we got exactly 3 distinct kinds sorted
    assert len(kinds) == 3
    assert kinds == sorted(kinds)
    assert "phase_advanced" in kinds
    assert "result_recorded" in kinds
    assert "ticket_claimed" in kinds


def test_reductions_endpoint_returns_reductions_with_member_tickets(
    client: TestClient, seeded_run: str, temp_home: Path
):
    """GET /api/runs/{id}/reductions returns reductions with parsed json and member_tickets with real states."""
    import time
    now = time.time()
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    # Seed tickets with different states (for member tickets)
    ticket_ids = [f"{seeded_run}/t-100", f"{seeded_run}/t-101", f"{seeded_run}/t-102", f"{seeded_run}/t-999"]
    states = ["done", "needs_human", "failed", "nonexistent-placeholder"]  # t-999 won't exist

    for i, (tid, state) in enumerate(zip(ticket_ids[:3], states[:3])):
        conn.execute(
            """INSERT INTO tickets
               (id, run_id, phase, state, resource_req, priority, created_at, updated_at, payload_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (tid, seeded_run, "work", state, "cpu", 0, now, now, '{}'),
        )
    conn.commit()

    # Seed reductions with varied review_state and member tickets
    reductions = [
        {
            "run_id": seeded_run,
            "phase": "work",
            "kind": "duplicate_root_cause",
            "review_state": "pending",
            "json": json.dumps({
                "title": "Null pointer in module X",
                "member_ticket_ids": [f"{seeded_run}/t-100"],
                "needs_human_ticket_ids": [f"{seeded_run}/t-101", f"{seeded_run}/t-100"],  # Duplicate with member_ticket_ids
            }),
            "created_at": now - 300,
            "updated_at": now - 300,
        },
        {
            "run_id": seeded_run,
            "phase": "reduce",
            "kind": "test_flake",
            "review_state": "accepted",
            "json": json.dumps({
                "title": "Timeout in CI",
                "needs_human_ticket_ids": [f"{seeded_run}/t-102"],
            }),
            "created_at": now - 200,
            "updated_at": now - 100,
        },
        {
            "run_id": seeded_run,
            "phase": "work",
            "kind": "config_error",
            "review_state": "rejected",
            "json": json.dumps({
                "title": "Missing env var",
                "member_ticket_ids": [f"{seeded_run}/t-999"],  # Nonexistent ticket id
            }),
            "created_at": now - 100,
            "updated_at": now - 50,
        },
    ]

    for r in reductions:
        conn.execute(
            """INSERT INTO reductions
               (run_id, phase, kind, json, review_state, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (r["run_id"], r["phase"], r["kind"], r["json"], r["review_state"], r["created_at"], r["updated_at"]),
        )
    conn.commit()

    # Fetch reductions
    response = client.get(f"/api/runs/{seeded_run}/reductions")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 3

    # Verify first reduction (pending, de-duped union of member + needs_human)
    r0 = data[0]
    assert r0["kind"] == "duplicate_root_cause"
    assert r0["phase"] == "work"
    assert r0["review_state"] == "pending"
    assert isinstance(r0["json"], dict)  # Parsed
    assert r0["json"]["title"] == "Null pointer in module X"

    # member_ticket_ids should be de-duplicated union of member_ticket_ids + needs_human_ticket_ids
    assert "member_ticket_ids" in r0
    assert set(r0["member_ticket_ids"]) == {f"{seeded_run}/t-100", f"{seeded_run}/t-101"}
    # Order-stable: t-100 first (from member_ticket_ids), then t-101 (from needs_human, not already seen)
    assert r0["member_ticket_ids"] == [f"{seeded_run}/t-100", f"{seeded_run}/t-101"]

    # member_tickets should have real states from tickets table
    assert "member_tickets" in r0
    assert len(r0["member_tickets"]) == 2
    member_map = {m["id"]: m for m in r0["member_tickets"]}
    assert member_map[f"{seeded_run}/t-100"]["state"] == "done"
    assert member_map[f"{seeded_run}/t-100"]["phase"] == "work"
    assert member_map[f"{seeded_run}/t-101"]["state"] == "needs_human"
    assert member_map[f"{seeded_run}/t-101"]["phase"] == "work"

    # Verify second reduction (accepted, only needs_human)
    r1 = data[1]
    assert r1["kind"] == "test_flake"
    assert r1["phase"] == "reduce"
    assert r1["review_state"] == "accepted"
    assert r1["json"]["title"] == "Timeout in CI"
    assert r1["member_ticket_ids"] == [f"{seeded_run}/t-102"]
    assert len(r1["member_tickets"]) == 1
    assert r1["member_tickets"][0]["id"] == f"{seeded_run}/t-102"
    assert r1["member_tickets"][0]["state"] == "failed"
    assert r1["member_tickets"][0]["phase"] == "work"

    # Verify third reduction (rejected, nonexistent member ticket)
    r2 = data[2]
    assert r2["kind"] == "config_error"
    assert r2["review_state"] == "rejected"
    assert r2["member_ticket_ids"] == [f"{seeded_run}/t-999"]
    # member_tickets should be empty or represent unknown (implementation detail: can skip or mark unknown)
    # Per brief: "skip ids not found"
    assert len(r2["member_tickets"]) == 0

    # Verify order by id
    db_reductions = conn.execute(
        """SELECT id FROM reductions WHERE run_id=? ORDER BY id""",
        (seeded_run,),
    ).fetchall()
    assert len(data) == len(db_reductions)
    for i, db_row in enumerate(db_reductions):
        assert data[i]["id"] == db_row[0]

    conn.close()


def test_reductions_filter_by_phase(client: TestClient, seeded_run: str, temp_home: Path):
    """GET /api/runs/{id}/reductions?phase=work filters to that phase."""
    import time
    now = time.time()
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    # Seed reductions in different phases
    for phase in ["work", "reduce"]:
        conn.execute(
            """INSERT INTO reductions
               (run_id, phase, kind, json, review_state, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (seeded_run, phase, "test", '{}', "pending", now, now),
        )
    conn.commit()

    response = client.get(f"/api/runs/{seeded_run}/reductions?phase=work")
    assert response.status_code == 200

    data = response.json()
    assert all(r["phase"] == "work" for r in data)

    # Verify against sqlite
    work_count = conn.execute(
        """SELECT COUNT(*) FROM reductions WHERE run_id=? AND phase='work'""",
        (seeded_run,),
    ).fetchone()[0]
    conn.close()

    assert len(data) == work_count


def test_reductions_unknown_run_404(client: TestClient, temp_home: Path):
    """GET /api/runs/{unknown}/reductions returns 404."""
    response = client.get("/api/runs/unknown-run/reductions")
    assert response.status_code == 404


def test_websocket_hello_and_event_push(client: TestClient, seeded_run: str, temp_home: Path, monkeypatch):
    """WS /api/ws sends hello with cursor, then pushes new events inserted into real events table."""
    from server.auth import read_token

    # Set low poll interval so test completes quickly
    monkeypatch.setenv("HERMES_WS_POLL_S", "0.05")

    import time
    db_path = str(temp_home / "queue.db")

    token = read_token(temp_home)

    # Connect to websocket with since=0 (replay from start) and token
    with client.websocket_connect(f"/api/ws?since=0&token={token}") as websocket:
        # Should receive hello message with initial cursor
        hello = websocket.receive_json()
        assert hello["type"] == "hello"
        assert "last_id" in hello
        initial_cursor = hello["last_id"]

        # Insert a NEW event into the real events table
        conn = connect(db_path)
        from engine import events
        events.emit(
            conn,
            "ticket_claimed",
            run_id=seeded_run,
            ticket_id=f"{seeded_run}/new-ticket",
            host="test-worker",
            message="Live event test",
            data={"test": True}
        )
        conn.commit()

        # Get the event ID we just inserted
        new_event_id = conn.execute("SELECT MAX(id) FROM events").fetchone()[0]
        conn.close()

        # Should receive event message within bounded wait (poll is 0.05s, allow up to 1s)
        # TestClient's receive_json doesn't support timeout, so we'll use receive_json directly
        # (it will block until a message arrives; the poll loop should send within ~0.05s)
        event_msg = websocket.receive_json()
        assert event_msg["type"] == "event"
        assert "event" in event_msg

        # Verify the event fields match what we inserted
        event = event_msg["event"]
        assert event["id"] == new_event_id
        assert event["kind"] == "ticket_claimed"
        assert event["run_id"] == seeded_run
        assert event["ticket_id"] == f"{seeded_run}/new-ticket"
        assert event["host"] == "test-worker"
        assert event["message"] == "Live event test"
        assert event["data"]["test"] is True

        # Clean disconnect should not raise
        websocket.close()


def test_websocket_clean_disconnect(client: TestClient, temp_home: Path, monkeypatch):
    """WS /api/ws handles client disconnect cleanly without crashing the server."""
    from server.auth import read_token

    monkeypatch.setenv("HERMES_WS_POLL_S", "0.1")

    token = read_token(temp_home)

    # Connect and immediately disconnect
    with client.websocket_connect(f"/api/ws?token={token}") as websocket:
        hello = websocket.receive_json()
        assert hello["type"] == "hello"
        websocket.close()

    # Server should still be responsive
    response = client.get("/api/health")
    assert response.status_code == 200


# --- Auth (D1a) ---


def test_auth_token_load_or_create_generates_token_0600(temp_home: Path):
    """load_or_create_token generates a strong token with 0600 mode."""
    from server.auth import load_or_create_token
    import stat

    token = load_or_create_token(temp_home)

    # Token should be non-empty string
    assert isinstance(token, str)
    assert len(token) > 0

    # Token file should exist with mode 0600
    token_path = temp_home / "api_token"
    assert token_path.exists()

    # Check file mode
    mode = token_path.stat().st_mode
    assert stat.S_IMODE(mode) == 0o600


def test_auth_token_load_or_create_idempotent(temp_home: Path):
    """load_or_create_token is idempotent: returns same token if already exists."""
    from server.auth import load_or_create_token

    token1 = load_or_create_token(temp_home)
    token2 = load_or_create_token(temp_home)

    assert token1 == token2


def test_auth_token_rotate_changes_token(temp_home: Path):
    """rotate_token generates a new token, different from the old one."""
    from server.auth import load_or_create_token, rotate_token

    token1 = load_or_create_token(temp_home)
    token2 = rotate_token(temp_home)

    assert token1 != token2
    assert len(token2) > 0


def test_auth_token_rotate_preserves_0600(temp_home: Path):
    """rotate_token preserves mode 0600."""
    from server.auth import rotate_token
    import stat

    rotate_token(temp_home)

    token_path = temp_home / "api_token"
    mode = token_path.stat().st_mode
    assert stat.S_IMODE(mode) == 0o600


def test_auth_token_read_returns_token(temp_home: Path):
    """read_token returns the current token."""
    from server.auth import load_or_create_token, read_token

    expected = load_or_create_token(temp_home)
    actual = read_token(temp_home)

    assert actual == expected


def test_auth_token_read_returns_none_when_absent(temp_home: Path):
    """read_token returns None if token file doesn't exist."""
    from server.auth import read_token

    assert read_token(temp_home) is None


@pytest.fixture
def loopback_client(temp_home: Path):
    """TestClient for loopback (127.0.0.1) app."""
    app = create_app(bind="127.0.0.1")
    return TestClient(app)


@pytest.fixture
def nonloopback_client(temp_home: Path):
    """TestClient for non-loopback (0.0.0.0) app."""
    app = create_app(bind="0.0.0.0")
    return TestClient(app)


def test_auth_mutation_requires_token_on_loopback(loopback_client: TestClient, seeded_run: str, temp_home: Path):
    """POST /api/runs/{id}/pause with NO token on loopback => 401."""
    # Get a running run's ID
    response = loopback_client.post(f"/api/runs/{seeded_run}/pause")
    assert response.status_code == 401


def test_auth_mutation_rejects_wrong_token_on_loopback(loopback_client: TestClient, seeded_run: str, temp_home: Path):
    """POST /api/runs/{id}/pause with WRONG token on loopback => 401."""
    response = loopback_client.post(
        f"/api/runs/{seeded_run}/pause",
        headers={"Authorization": "Bearer wrong-token"}
    )
    assert response.status_code == 401


def test_auth_mutation_accepts_correct_token_on_loopback(loopback_client: TestClient, seeded_run: str, temp_home: Path):
    """POST /api/runs/{id}/pause with CORRECT token on loopback => 200."""
    from server.auth import read_token

    token = read_token(temp_home)
    assert token is not None

    response = loopback_client.post(
        f"/api/runs/{seeded_run}/pause",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200


def test_auth_get_open_on_loopback_without_token(loopback_client: TestClient, seeded_run: str, temp_home: Path):
    """GET /api/runs on loopback with NO token => 200 (open)."""
    response = loopback_client.get("/api/runs")
    assert response.status_code == 200


def test_auth_get_requires_token_on_nonloopback(nonloopback_client: TestClient, seeded_run: str, temp_home: Path):
    """GET /api/runs on non-loopback with NO token => 401."""
    response = nonloopback_client.get("/api/runs")
    assert response.status_code == 401


def test_auth_get_accepts_token_on_nonloopback(nonloopback_client: TestClient, seeded_run: str, temp_home: Path):
    """GET /api/runs on non-loopback with CORRECT token => 200."""
    from server.auth import read_token

    token = read_token(temp_home)
    assert token is not None

    response = nonloopback_client.get(
        "/api/runs",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200


# --- WebSocket Auth (D1a) ---


def test_websocket_auth_no_token_closes_4401(loopback_client: TestClient, temp_home: Path):
    """WS /api/ws with NO token => closed with code 4401."""
    from starlette.websockets import WebSocketDisconnect

    try:
        with loopback_client.websocket_connect("/api/ws") as websocket:
            # Try to receive - should get disconnect
            websocket.receive_json()
            pytest.fail("Should have been disconnected")
    except WebSocketDisconnect as e:
        assert e.code == 4401


def test_websocket_auth_wrong_token_closes_4401(loopback_client: TestClient, temp_home: Path):
    """WS /api/ws with WRONG token => closed with code 4401."""
    from starlette.websockets import WebSocketDisconnect

    try:
        with loopback_client.websocket_connect("/api/ws?token=wrong-token") as websocket:
            # Try to receive - should get disconnect
            websocket.receive_json()
            pytest.fail("Should have been disconnected")
    except WebSocketDisconnect as e:
        assert e.code == 4401


def test_run_detail_unregistered_playbook_derives_phases_from_tickets(
    client: TestClient, temp_home: Path
):
    """GET /api/runs/{id} for an unregistered playbook returns 200 with derived phases from tickets."""
    import time
    now = time.time()
    db_path = str(temp_home / "queue.db")
    conn = connect(db_path)

    # Create a run with a playbook name that is NOT registered
    run_id = "test-orphan-run"
    conn.execute(
        """INSERT INTO runs
           (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            run_id, "unknown_playbook", "local", "running", "analyze", "main",
            json.dumps({}), now, now
        ),
    )
    conn.commit()

    # Seed tickets in 3 distinct phases (analyze, investigate, report)
    # Order matters - we'll insert in mixed order to test sorting by first appearance
    tickets_data = [
        (f"{run_id}/t-0", "analyze", "queued", 10),
        (f"{run_id}/t-1", "investigate", "queued", 9),
        (f"{run_id}/t-2", "analyze", "done", 8),
        (f"{run_id}/t-3", "report", "queued", 7),
        (f"{run_id}/t-4", "investigate", "failed", 6),
    ]

    for tid, phase, state, priority in tickets_data:
        conn.execute(
            """INSERT INTO tickets
               (id, run_id, phase, state, resource_req, priority, created_at, updated_at, payload_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (tid, run_id, phase, state, "cpu", priority, now, now, '{"goal": "test"}'),
        )
    conn.commit()
    conn.close()

    # GET the run - should NOT 500, should return 200 with derived phases
    response = client.get(f"/api/runs/{run_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == run_id
    assert data["playbook"] == "unknown_playbook"
    assert data["phase"] == "analyze"

    # phases array should be derived from DISTINCT phases in tickets, ordered by first appearance
    assert "phases" in data
    phases = data["phases"]
    assert isinstance(phases, list)
    assert len(phases) == 3

    # Verify phase names in order of first appearance (analyze -> investigate -> report)
    assert phases[0]["name"] == "analyze"
    assert phases[1]["name"] == "investigate"
    assert phases[2]["name"] == "report"

    # Verify current flag
    assert phases[0]["current"] is True  # run.phase == "analyze"
    assert phases[1]["current"] is False
    assert phases[2]["current"] is False

    # Verify counts match the seeded tickets
    assert phases[0]["counts"]["queued"] == 1  # t-0
    assert phases[0]["counts"]["done"] == 1    # t-2
    assert phases[1]["counts"]["queued"] == 1  # t-1
    assert phases[1]["counts"]["failed"] == 1  # t-4
    assert phases[2]["counts"]["queued"] == 1  # t-3


def test_run_detail_unregistered_playbook_no_tickets_uses_current_phase(
    client: TestClient, temp_home: Path
):
    """GET /api/runs/{id} for unregistered playbook with no tickets derives phases from current_phase."""
    import time
    now = time.time()
    db_path = str(temp_home / "queue.db")
    conn = connect(db_path)

    # Create a run with NO tickets
    run_id = "test-orphan-no-tickets"
    conn.execute(
        """INSERT INTO runs
           (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            run_id, "unknown_playbook2", "local", "running", "init", "main",
            json.dumps({}), now, now
        ),
    )
    conn.commit()
    conn.close()

    # GET the run - should return 200 with at least current_phase
    response = client.get(f"/api/runs/{run_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == run_id

    # phases should have at least current_phase
    assert "phases" in data
    phases = data["phases"]
    assert len(phases) >= 1
    assert phases[0]["name"] == "init"
    assert phases[0]["current"] is True
    assert phases[0]["counts"] == {}  # No tickets


def test_run_detail_registered_playbook_uses_canonical_phases(
    client: TestClient, temp_home: Path
):
    """GET /api/runs/{id} for a registered playbook (dexter) uses canonical phase order."""
    import time
    now = time.time()
    db_path = str(temp_home / "queue.db")
    conn = connect(db_path)

    # Create a run with "dexter" playbook (which IS registered)
    run_id = "test-dexter-run"
    conn.execute(
        """INSERT INTO runs
           (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            run_id, "dexter", "local", "running", "solve", "main",
            json.dumps({}), now, now
        ),
    )
    conn.commit()

    # Seed a few tickets in the solve phase
    tickets_data = [
        (f"{run_id}/t-0", "solve", "queued", 10),
        (f"{run_id}/t-1", "solve", "done", 9),
    ]

    for tid, phase, state, priority in tickets_data:
        conn.execute(
            """INSERT INTO tickets
               (id, run_id, phase, state, resource_req, priority, created_at, updated_at, payload_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (tid, run_id, phase, state, "cpu", priority, now, now, '{"goal": "test"}'),
        )
    conn.commit()
    conn.close()

    # GET the run - should use the playbook's canonical phase order
    response = client.get(f"/api/runs/{run_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == run_id
    assert data["playbook"] == "dexter"

    # phases should match the dexter playbook's canonical order (just "solve")
    assert "phases" in data
    phases = data["phases"]
    assert len(phases) == 1
    assert phases[0]["name"] == "solve"
    assert phases[0]["current"] is True

    # Verify counts match the tickets we seeded
    assert phases[0]["counts"]["queued"] == 1
    assert phases[0]["counts"]["done"] == 1


def test_websocket_auth_correct_token_receives_hello(loopback_client: TestClient, temp_home: Path, monkeypatch):
    """WS /api/ws with CORRECT token => receives hello (C1 behavior preserved)."""
    from server.auth import read_token

    monkeypatch.setenv("HERMES_WS_POLL_S", "0.1")

    token = read_token(temp_home)
    assert token is not None

    with loopback_client.websocket_connect(f"/api/ws?token={token}") as websocket:
        hello = websocket.receive_json()
        assert hello["type"] == "hello"
        assert "last_id" in hello


# --- Run Control Endpoints (D1a) ---


def test_run_control_pause_running_run(loopback_client: TestClient, seeded_run: str, temp_home: Path):
    """POST /api/runs/{id}/pause on running run => 200 + state paused + event."""
    from server.auth import read_token
    import sqlite3

    token = read_token(temp_home)
    db_path = str(temp_home / "queue.db")

    # Verify run is running
    conn = sqlite3.connect(db_path)
    state = conn.execute("SELECT state FROM runs WHERE id=?", (seeded_run,)).fetchone()[0]
    assert state == "running"
    conn.close()

    # Pause the run
    response = loopback_client.post(
        f"/api/runs/{seeded_run}/pause",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200

    data = response.json()
    assert data["state"] == "paused"

    # Verify state in database
    conn = sqlite3.connect(db_path)
    new_state = conn.execute("SELECT state FROM runs WHERE id=?", (seeded_run,)).fetchone()[0]
    assert new_state == "paused"

    # Verify event was emitted
    event = conn.execute(
        """SELECT kind, run_id, message FROM events
           WHERE kind='run_paused' AND run_id=?
           ORDER BY id DESC LIMIT 1""",
        (seeded_run,)
    ).fetchone()
    assert event is not None
    assert event[0] == "run_paused"
    assert event[1] == seeded_run

    conn.close()


def test_run_control_resume_paused_run(loopback_client: TestClient, seeded_run: str, temp_home: Path):
    """POST /api/runs/{id}/resume on paused run => 200 + state running + event."""
    from server.auth import read_token
    import sqlite3

    token = read_token(temp_home)
    db_path = str(temp_home / "queue.db")

    # First pause the run
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE runs SET state='paused' WHERE id=?", (seeded_run,))
    conn.commit()
    conn.close()

    # Resume the run
    response = loopback_client.post(
        f"/api/runs/{seeded_run}/resume",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200

    data = response.json()
    assert data["state"] == "running"

    # Verify state in database
    conn = sqlite3.connect(db_path)
    new_state = conn.execute("SELECT state FROM runs WHERE id=?", (seeded_run,)).fetchone()[0]
    assert new_state == "running"

    # Verify event was emitted
    event = conn.execute(
        """SELECT kind, run_id FROM events
           WHERE kind='run_resumed' AND run_id=?
           ORDER BY id DESC LIMIT 1""",
        (seeded_run,)
    ).fetchone()
    assert event is not None
    assert event[0] == "run_resumed"

    conn.close()


def test_run_control_stop_running_run(loopback_client: TestClient, seeded_run: str, temp_home: Path):
    """POST /api/runs/{id}/stop on running run => 200 + state stopped + event."""
    from server.auth import read_token
    import sqlite3

    token = read_token(temp_home)
    db_path = str(temp_home / "queue.db")

    # Stop the run
    response = loopback_client.post(
        f"/api/runs/{seeded_run}/stop",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200

    data = response.json()
    assert data["state"] == "stopped"

    # Verify state in database
    conn = sqlite3.connect(db_path)
    new_state = conn.execute("SELECT state FROM runs WHERE id=?", (seeded_run,)).fetchone()[0]
    assert new_state == "stopped"

    # Verify event was emitted
    event = conn.execute(
        """SELECT kind, run_id FROM events
           WHERE kind='run_stopped' AND run_id=?
           ORDER BY id DESC LIMIT 1""",
        (seeded_run,)
    ).fetchone()
    assert event is not None

    conn.close()


def test_run_control_unknown_run_404(loopback_client: TestClient, temp_home: Path):
    """POST /api/runs/{unknown}/pause => 404."""
    from server.auth import read_token

    token = read_token(temp_home)

    response = loopback_client.post(
        "/api/runs/unknown-run-id/pause",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404


def test_run_control_illegal_transition_409(loopback_client: TestClient, seeded_run: str, temp_home: Path):
    """POST /api/runs/{id}/resume on stopped run => 409 (illegal transition)."""
    from server.auth import read_token
    import sqlite3

    token = read_token(temp_home)
    db_path = str(temp_home / "queue.db")

    # First stop the run
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE runs SET state='stopped' WHERE id=?", (seeded_run,))
    conn.commit()
    conn.close()

    # Try to resume a stopped run (illegal)
    response = loopback_client.post(
        f"/api/runs/{seeded_run}/resume",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 409
    assert "detail" in response.json()


def test_run_control_404_vs_409_separation(loopback_client: TestClient, seeded_run: str, temp_home: Path):
    """Run control correctly distinguishes 404 (unknown run) from 409 (illegal transition)."""
    from server.auth import read_token
    import sqlite3

    token = read_token(temp_home)
    db_path = str(temp_home / "queue.db")
    headers = {"Authorization": f"Bearer {token}"}

    # Test 404: unknown run
    response = loopback_client.post("/api/runs/nonexistent-run-id/pause", headers=headers)
    assert response.status_code == 404

    # Test 409: illegal transition (pause an already stopped run)
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE runs SET state='stopped' WHERE id=?", (seeded_run,))
    conn.commit()
    conn.close()

    response = loopback_client.post(f"/api/runs/{seeded_run}/pause", headers=headers)
    assert response.status_code == 409


# --- SPA Serving + Token Injection (D1a) ---


def test_spa_loopback_injects_token(loopback_client: TestClient, temp_home: Path):
    """GET / on loopback injects token bootstrap into index.html."""
    from server.auth import read_token

    # Create fake index.html
    dist_dir = temp_home / "web_dist"
    dist_dir.mkdir()
    index_html = dist_dir / "index.html"
    index_html.write_text("""<!DOCTYPE html>
<html>
<head>
    <title>Hermes</title>
</head>
<body>
    <div id="app"></div>
</body>
</html>""")

    # Point HERMES_WEB_DIST to temp dist dir
    import os
    os.environ["HERMES_WEB_DIST"] = str(dist_dir)

    # Create new client with dist dir env set
    app = create_app(bind="127.0.0.1")
    client = TestClient(app)

    token = read_token(temp_home)
    assert token is not None

    response = client.get("/")
    assert response.status_code == 200

    html = response.text
    # Should contain injected token bootstrap
    assert f'window.__HERMES_TOKEN__="{token}"' in html
    assert 'window.__HERMES_BIND__="loopback"' in html
    # Should still have the original content
    assert "<title>Hermes</title>" in html


def test_favicon_served_from_dist_root(temp_home: Path):
    """GET /favicon.svg serves the dist-root file as image/svg+xml (ungated)."""
    import os

    dist_dir = temp_home / "web_dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<html><head></head><body></body></html>")
    (dist_dir / "favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"></svg>'
    )
    os.environ["HERMES_WEB_DIST"] = str(dist_dir)

    app = create_app(bind="127.0.0.1")
    client = TestClient(app)

    resp = client.get("/favicon.svg")
    assert resp.status_code == 200
    assert "svg" in resp.headers["content-type"]
    assert "<svg" in resp.text


def test_gzip_middleware_registered():
    """The app compresses responses (GZipMiddleware) so the SPA/JSON transfer is small."""
    from fastapi.middleware.gzip import GZipMiddleware

    app = create_app(bind="127.0.0.1")
    assert any(m.cls is GZipMiddleware for m in app.user_middleware)


def test_spa_nonloopback_omits_token(nonloopback_client: TestClient, temp_home: Path):
    """GET / on non-loopback does NOT inject token (only bind marker)."""
    from server.auth import read_token

    # Create fake index.html
    dist_dir = temp_home / "web_dist"
    dist_dir.mkdir()
    index_html = dist_dir / "index.html"
    index_html.write_text("""<!DOCTYPE html>
<html>
<head>
    <title>Hermes</title>
</head>
<body>
    <div id="app"></div>
</body>
</html>""")

    # Point HERMES_WEB_DIST to temp dist dir
    import os
    os.environ["HERMES_WEB_DIST"] = str(dist_dir)

    # Create new client with dist dir env set
    app = create_app(bind="0.0.0.0")
    client = TestClient(app)

    token = read_token(temp_home)
    assert token is not None

    # Non-loopback GETs require auth, so provide token
    response = client.get("/", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

    html = response.text
    # Should NOT contain token
    assert "__HERMES_TOKEN__" not in html
    # Should contain remote bind marker
    assert 'window.__HERMES_BIND__="remote"' in html
    # Should still have the original content
    assert "<title>Hermes</title>" in html


# --- Crew Control Endpoints (D2a) ---


@pytest.fixture
def test_site_agent(temp_home: Path):
    """Register a test-only stub site + agent with controllable health reports."""
    from engine import site, agent
    from engine.models import HealthReport, Check

    class TestSite:
        """Stub site for testing crew endpoints with controllable health."""
        name = "test-site"
        _health_report = None

        def provision(self, host: str, base_ref: str) -> None:
            """No-op provisioning."""
            pass

        def health(self, host: str, agent_obj) -> HealthReport:
            """Return the controlled health report."""
            if self._health_report is None:
                # Default: all healthy
                return HealthReport(
                    reachable=True,
                    agent_ok=True,
                    auth_ok=True,
                    workspace_ready=True,
                    guard_installed=True,
                    resources={"cpu": 4},
                    latency_ms=10,
                    checks=[
                        Check(name="reachable", ok=True, detail="ok"),
                        Check(name="agent_ok", ok=True, detail="ok"),
                        Check(name="auth_ok", ok=True, detail="ok"),
                        Check(name="workspace_ready", ok=True, detail="ok"),
                        Check(name="guard_installed", ok=True, detail="ok"),
                    ]
                )
            return self._health_report

        def set_health(self, report: HealthReport):
            """Set the health report to return."""
            self._health_report = report

        def resource_classes(self) -> list[str]:
            return ["cpu"]

        def guarantees_no_ship(self) -> bool:
            return True

        def run_worker(self, host: str, envelope: dict, agent_obj) -> None:
            raise NotImplementedError("Test site does not support running workers")

        def submit_for_review(self, host: str, change: dict) -> str:
            raise NotImplementedError("Test site does not support reviews")

        def issue_source(self, query) -> list:
            return []

        def discover_hosts(self) -> list[str]:
            return []

    class TestAgent:
        """Stub agent for testing."""
        name = "test-agent"

        def build_invocation(self, envelope: dict, driver) -> list[str]:
            raise NotImplementedError("Test agent does not build invocations")

        def parse_result(self, raw: str, envelope: dict):
            raise NotImplementedError("Test agent does not parse results")

        def health_checks(self, host: str, site_obj) -> list[Check]:
            return [
                Check(name="agent_ok", ok=True, detail="ok"),
                Check(name="auth_ok", ok=True, detail="ok"),
            ]

    test_site_obj = TestSite()
    test_agent_obj = TestAgent()

    site.register("test-site", test_site_obj)
    agent.register("test-agent", test_agent_obj)

    yield test_site_obj, test_agent_obj

    # Cleanup: remove from registries
    from engine.site import _REGISTRY as site_registry
    from engine.agent import _REGISTRY as agent_registry
    site_registry.pop("test-site", None)
    agent_registry.pop("test-agent", None)


def test_crew_probe_healthy_host(loopback_client: TestClient, temp_home: Path, test_site_agent):
    """POST /api/crew/probe with healthy host => 200 + full checklist with ok=true."""
    from server.auth import read_token

    token = read_token(temp_home)
    test_site, _ = test_site_agent

    response = loopback_client.post(
        "/api/crew/probe",
        json={"host": "test-host-1", "site": "test-site", "agent": "test-agent"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200

    data = response.json()
    assert data["host"] == "test-host-1"
    assert data["ok"] is True
    assert data["reachable"] is True
    assert data["agent_ok"] is True
    assert data["auth_ok"] is True
    assert data["workspace_ready"] is True
    assert data["guard_installed"] is True
    assert data["latency_ms"] == 10
    assert data["resources"] == {"cpu": 4}

    # Check that all checks are present and passing
    assert len(data["checks"]) == 5
    for check in data["checks"]:
        assert check["ok"] is True
        assert check["name"] in ["reachable", "agent_ok", "auth_ok", "workspace_ready", "guard_installed"]


def test_crew_probe_unhealthy_host(loopback_client: TestClient, temp_home: Path, test_site_agent):
    """POST /api/crew/probe with unhealthy host => 200 + ok=false + failing checks named."""
    from server.auth import read_token
    from engine.models import HealthReport, Check

    token = read_token(temp_home)
    test_site, _ = test_site_agent

    # Set unhealthy report
    test_site.set_health(HealthReport(
        reachable=True,
        agent_ok=False,
        auth_ok=False,
        workspace_ready=True,
        guard_installed=True,
        resources={},
        latency_ms=100,
        checks=[
            Check(name="reachable", ok=True, detail="ok"),
            Check(name="agent_ok", ok=False, detail="agent not found"),
            Check(name="auth_ok", ok=False, detail="auth failed"),
            Check(name="workspace_ready", ok=True, detail="ok"),
            Check(name="guard_installed", ok=True, detail="ok"),
        ]
    ))

    response = loopback_client.post(
        "/api/crew/probe",
        json={"host": "test-host-2", "site": "test-site", "agent": "test-agent"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200

    data = response.json()
    assert data["ok"] is False
    assert data["agent_ok"] is False
    assert data["auth_ok"] is False

    # Check that failing checks are present
    failing_checks = [c for c in data["checks"] if not c["ok"]]
    assert len(failing_checks) == 2
    failing_names = {c["name"] for c in failing_checks}
    assert failing_names == {"agent_ok", "auth_ok"}


def test_crew_probe_unknown_site_404(loopback_client: TestClient, temp_home: Path):
    """POST /api/crew/probe with unknown site => 400/404."""
    from server.auth import read_token

    token = read_token(temp_home)

    response = loopback_client.post(
        "/api/crew/probe",
        json={"host": "test-host", "site": "unknown-site"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code in (400, 404)
    assert "unknown" in response.json()["detail"].lower() or "site" in response.json()["detail"].lower()


def test_crew_probe_requires_token(loopback_client: TestClient, temp_home: Path, test_site_agent):
    """POST /api/crew/probe with NO token => 401."""
    response = loopback_client.post(
        "/api/crew/probe",
        json={"host": "test-host", "site": "test-site"}
    )
    assert response.status_code == 401


def test_crew_add_healthy_host(loopback_client: TestClient, temp_home: Path, test_site_agent):
    """POST /api/crew with healthy host => 201/200 + crew row admitted."""
    from server.auth import read_token
    import sqlite3

    token = read_token(temp_home)
    db_path = str(temp_home / "queue.db")

    response = loopback_client.post(
        "/api/crew",
        json={"host": "test-host-add", "site": "test-site", "agent": "test-agent", "base_ref": "main"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code in (200, 201)

    data = response.json()
    assert data["id"] == "test-host-add"
    assert data["site"] == "test-site"
    assert data["state"] == "idle"
    assert data["resources"]["cpu"] == 4

    # Verify crew row exists in database
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT id, site, state FROM crew WHERE id=?", ("test-host-add",)).fetchone()
    assert row is not None
    assert row[0] == "test-host-add"
    assert row[1] == "test-site"
    assert row[2] == "idle"
    conn.close()


def test_crew_add_unhealthy_host_422_no_row(loopback_client: TestClient, temp_home: Path, test_site_agent):
    """POST /api/crew with unhealthy host => 422 + failing checks detail + NO crew row inserted."""
    from server.auth import read_token
    from engine.models import HealthReport, Check
    import sqlite3

    token = read_token(temp_home)
    test_site, _ = test_site_agent
    db_path = str(temp_home / "queue.db")

    # Set unhealthy report
    test_site.set_health(HealthReport(
        reachable=False,
        agent_ok=False,
        auth_ok=True,
        workspace_ready=True,
        guard_installed=False,
        resources={},
        latency_ms=1000,
        checks=[
            Check(name="reachable", ok=False, detail="host unreachable"),
            Check(name="agent_ok", ok=False, detail="agent missing"),
            Check(name="auth_ok", ok=True, detail="ok"),
            Check(name="workspace_ready", ok=True, detail="ok"),
            Check(name="guard_installed", ok=False, detail="guard not found"),
        ]
    ))

    response = loopback_client.post(
        "/api/crew",
        json={"host": "test-host-bad", "site": "test-site", "agent": "test-agent"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 422

    # Should contain failing check names in detail
    detail = response.json()["detail"]
    assert "reachable" in detail
    assert "agent_ok" in detail or "agent" in detail
    assert "guard_installed" in detail or "guard" in detail

    # Verify NO crew row was inserted
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT id FROM crew WHERE id=?", ("test-host-bad",)).fetchone()
    assert row is None
    conn.close()


def test_crew_add_requires_token(loopback_client: TestClient, temp_home: Path, test_site_agent):
    """POST /api/crew with NO token => 401."""
    response = loopback_client.post(
        "/api/crew",
        json={"host": "test-host", "site": "test-site"}
    )
    assert response.status_code == 401


def test_crew_reprobe_updates_health(loopback_client: TestClient, temp_home: Path, test_site_agent):
    """POST /api/crew/{host}/reprobe updates health_json + returns checklist."""
    from server.auth import read_token
    from engine.models import HealthReport, Check
    import sqlite3
    import json as json_module

    token = read_token(temp_home)
    test_site, _ = test_site_agent
    db_path = str(temp_home / "queue.db")

    # First add a crew member
    response = loopback_client.post(
        "/api/crew",
        json={"host": "test-host-reprobe", "site": "test-site", "agent": "test-agent"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code in (200, 201)

    # Get initial health_json
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT health_json, last_heartbeat FROM crew WHERE id=?", ("test-host-reprobe",)).fetchone()
    initial_health = row[0]
    initial_heartbeat = row[1]
    conn.close()

    # Change the health report
    test_site.set_health(HealthReport(
        reachable=True,
        agent_ok=True,
        auth_ok=True,
        workspace_ready=True,
        guard_installed=True,
        resources={"cpu": 8},  # Changed
        latency_ms=20,  # Changed
        checks=[
            Check(name="reachable", ok=True, detail="ok"),
            Check(name="agent_ok", ok=True, detail="ok"),
            Check(name="auth_ok", ok=True, detail="ok"),
            Check(name="workspace_ready", ok=True, detail="ok"),
            Check(name="guard_installed", ok=True, detail="ok"),
        ]
    ))

    # Reprobe
    import time
    time.sleep(0.01)  # Ensure timestamp changes
    response = loopback_client.post(
        f"/api/crew/test-host-reprobe/reprobe",
        json={"agent": "test-agent"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200

    data = response.json()
    assert data["host"] == "test-host-reprobe"
    assert data["ok"] is True
    assert data["latency_ms"] == 20

    # Verify health_json was updated in database
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT health_json, last_heartbeat FROM crew WHERE id=?", ("test-host-reprobe",)).fetchone()
    new_health = row[0]
    new_heartbeat = row[1]
    conn.close()

    assert new_health != initial_health
    health_obj = json_module.loads(new_health)
    assert health_obj["latency_ms"] == 20
    assert new_heartbeat > initial_heartbeat


def test_crew_reprobe_unknown_host_404(loopback_client: TestClient, temp_home: Path):
    """POST /api/crew/{unknown}/reprobe => 404."""
    from server.auth import read_token

    token = read_token(temp_home)

    response = loopback_client.post(
        "/api/crew/unknown-host/reprobe",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404


def test_crew_drain(loopback_client: TestClient, temp_home: Path, test_site_agent):
    """POST /api/crew/{host}/drain => state draining."""
    from server.auth import read_token
    import sqlite3

    token = read_token(temp_home)
    db_path = str(temp_home / "queue.db")

    # First add a crew member
    response = loopback_client.post(
        "/api/crew",
        json={"host": "test-host-drain", "site": "test-site", "agent": "test-agent"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code in (200, 201)

    # Drain the host
    response = loopback_client.post(
        f"/api/crew/test-host-drain/drain",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200

    data = response.json()
    assert data["state"] == "draining"

    # Verify state in database
    conn = sqlite3.connect(db_path)
    state = conn.execute("SELECT state FROM crew WHERE id=?", ("test-host-drain",)).fetchone()[0]
    assert state == "draining"
    conn.close()


def test_crew_drain_unknown_host_404(loopback_client: TestClient, temp_home: Path):
    """POST /api/crew/{unknown}/drain => 404."""
    from server.auth import read_token

    token = read_token(temp_home)

    response = loopback_client.post(
        "/api/crew/unknown-host/drain",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404


def test_crew_remove(loopback_client: TestClient, temp_home: Path, test_site_agent):
    """DELETE /api/crew/{host} removes the crew member."""
    from server.auth import read_token
    import sqlite3

    token = read_token(temp_home)
    db_path = str(temp_home / "queue.db")

    # First add a crew member
    response = loopback_client.post(
        "/api/crew",
        json={"host": "test-host-remove", "site": "test-site", "agent": "test-agent"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code in (200, 201)

    # Verify it exists
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT id FROM crew WHERE id=?", ("test-host-remove",)).fetchone()
    assert row is not None
    conn.close()

    # Remove the host
    response = loopback_client.delete(
        f"/api/crew/test-host-remove",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200

    # Verify it's gone
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT id FROM crew WHERE id=?", ("test-host-remove",)).fetchone()
    assert row is None
    conn.close()


def test_crew_remove_unknown_host_404(loopback_client: TestClient, temp_home: Path):
    """DELETE /api/crew/{unknown} => 404."""
    from server.auth import read_token

    token = read_token(temp_home)

    response = loopback_client.delete(
        "/api/crew/unknown-host",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404


# --- D3 Ticket Requeue Tests ---


def test_ticket_detail_includes_reduction_id(loopback_client: TestClient, temp_home: Path):
    """GET /api/tickets/{id} includes reduction_id (null and set cases)."""
    import sqlite3

    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    # Seed a run
    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('run-1', 'example', 'local', 'running', 'phase-1', 'main', '{}', 0, 0)"""
    )

    # Seed a guard-routed needs_human ticket (reduction_id NULL)
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                worker_host, reduction_id, payload_json, created_at, updated_at)
           VALUES ('ticket-guard', 'run-1', 'phase-1', 'needs_human', 'cpu', 100, 1,
                   NULL, NULL, '{"goal":"test"}', 0, 0)"""
    )

    # Seed a reduction-flagged needs_human ticket (reduction_id SET)
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                worker_host, reduction_id, payload_json, created_at, updated_at)
           VALUES ('ticket-reduction', 'run-1', 'phase-1', 'needs_human', 'cpu', 100, 1,
                   NULL, 42, '{"goal":"test"}', 0, 0)"""
    )

    conn.commit()
    conn.close()

    # Test guard-routed ticket (reduction_id should be null)
    response = loopback_client.get("/api/tickets/ticket-guard")
    assert response.status_code == 200
    data = response.json()
    assert data["ticket"]["id"] == "ticket-guard"
    assert data["ticket"]["reduction_id"] is None

    # Test reduction-flagged ticket (reduction_id should be 42)
    response = loopback_client.get("/api/tickets/ticket-reduction")
    assert response.status_code == 200
    data = response.json()
    assert data["ticket"]["id"] == "ticket-reduction"
    assert data["ticket"]["reduction_id"] == 42


def test_requeue_guard_routed_needs_human_ticket_200(loopback_client: TestClient, temp_home: Path):
    """POST /api/tickets/{id}/requeue on guard-routed needs_human ticket => 200 + state queued."""
    from server.auth import read_token
    import sqlite3

    token = read_token(temp_home)
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    # Seed a run
    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('run-requeue', 'example', 'local', 'running', 'phase-1', 'main', '{}', 0, 0)"""
    )

    # Seed a guard-routed needs_human ticket
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                worker_host, reduction_id, payload_json, created_at, updated_at)
           VALUES ('ticket-nh', 'run-requeue', 'phase-1', 'needs_human', 'cpu', 100, 2,
                   'worker-1', NULL, '{"goal":"test"}', 0, 0)"""
    )

    conn.commit()
    conn.close()

    # Requeue the ticket
    response = loopback_client.post(
        "/api/tickets/ticket-nh/requeue",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200

    data = response.json()
    assert data["state"] == "queued"

    # Verify in database: state=queued, worker_host=NULL, reduction_id=NULL, attempts unchanged
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT state, worker_host, reduction_id, attempts FROM tickets WHERE id='ticket-nh'"
    ).fetchone()
    assert row is not None
    state, worker_host, reduction_id, attempts = row
    assert state == "queued"
    assert worker_host is None
    assert reduction_id is None
    assert attempts == 2  # Unchanged

    # Verify ticket_requeued event was emitted
    event_row = conn.execute(
        "SELECT kind, ticket_id FROM events WHERE kind='ticket_requeued' AND ticket_id='ticket-nh'"
    ).fetchone()
    assert event_row is not None
    conn.close()


def test_requeue_non_needs_human_ticket_409(loopback_client: TestClient, temp_home: Path):
    """POST /api/tickets/{id}/requeue on non-needs_human ticket => 409."""
    from server.auth import read_token
    import sqlite3

    token = read_token(temp_home)
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    # Seed a run
    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('run-409', 'example', 'local', 'running', 'phase-1', 'main', '{}', 0, 0)"""
    )

    # Seed a queued ticket (not needs_human)
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                worker_host, reduction_id, payload_json, created_at, updated_at)
           VALUES ('ticket-queued', 'run-409', 'phase-1', 'queued', 'cpu', 100, 1,
                   NULL, NULL, '{"goal":"test"}', 0, 0)"""
    )

    conn.commit()
    conn.close()

    # Try to requeue the queued ticket
    response = loopback_client.post(
        "/api/tickets/ticket-queued/requeue",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 409

    # Should contain error detail naming the unavailable action + current state.
    data = response.json()
    assert "detail" in data
    assert "queued" in data["detail"]
    assert "requeue" in data["detail"]
    assert "not available" in data["detail"]


def test_requeue_unknown_ticket_404(loopback_client: TestClient, temp_home: Path):
    """POST /api/tickets/{unknown}/requeue => 404."""
    from server.auth import read_token

    token = read_token(temp_home)

    response = loopback_client.post(
        "/api/tickets/unknown-ticket/requeue",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404

    data = response.json()
    assert "detail" in data
    assert "unknown" in data["detail"].lower() or "not found" in data["detail"].lower()


def test_requeue_requires_auth(loopback_client: TestClient, temp_home: Path):
    """POST /api/tickets/{id}/requeue without token => 401."""
    import sqlite3

    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    # Seed a run and ticket
    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('run-auth', 'example', 'local', 'running', 'phase-1', 'main', '{}', 0, 0)"""
    )
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                worker_host, reduction_id, payload_json, created_at, updated_at)
           VALUES ('ticket-auth', 'run-auth', 'phase-1', 'needs_human', 'cpu', 100, 1,
                   NULL, NULL, '{"goal":"test"}', 0, 0)"""
    )
    conn.commit()
    conn.close()

    # Try to requeue without token
    response = loopback_client.post("/api/tickets/ticket-auth/requeue")
    assert response.status_code == 401


# --- Reduction Accept/Reject (D4) ---


def test_accept_reduction_success(loopback_client: TestClient, temp_home: Path):
    """POST /api/reductions/{id}/accept on pending reduction => 200, state=accepted, tickets done, event emitted."""
    import sqlite3
    from server.auth import read_token

    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    # Seed run
    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('run-acc', 'example', 'local', 'running', 'reduce', 'main', '{}', 0, 0)"""
    )

    # Seed tickets (some needs_human linked to reduction)
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                worker_host, reduction_id, payload_json, created_at, updated_at)
           VALUES ('t-1', 'run-acc', 'reduce', 'needs_human', 'cpu', 100, 1,
                   NULL, 1, '{"goal":"test-1"}', 0, 0)"""
    )
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                worker_host, reduction_id, payload_json, created_at, updated_at)
           VALUES ('t-2', 'run-acc', 'reduce', 'needs_human', 'cpu', 100, 1,
                   NULL, 1, '{"goal":"test-2"}', 0, 0)"""
    )
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                worker_host, reduction_id, payload_json, created_at, updated_at)
           VALUES ('t-3', 'run-acc', 'reduce', 'queued', 'cpu', 100, 0,
                   NULL, NULL, '{"goal":"test-3"}', 0, 0)"""
    )

    # Seed pending reduction
    conn.execute(
        """INSERT INTO reductions (id, run_id, phase, kind, json, review_state, created_at, updated_at)
           VALUES (1, 'run-acc', 'reduce', 'hypothesis', '{"title":"Test reduction"}', 'pending', 0, 0)"""
    )

    conn.commit()
    conn.close()

    token = read_token(temp_home)

    # Accept reduction
    response = loopback_client.post(
        "/api/reductions/1/accept",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200

    data = response.json()
    assert data["review_state"] == "accepted"

    # Verify via sqlite
    conn = sqlite3.connect(db_path)

    # Check reduction state
    row = conn.execute("SELECT review_state FROM reductions WHERE id=1").fetchone()
    assert row[0] == "accepted"

    # Check linked tickets are done
    ticket_states = conn.execute(
        "SELECT id, state FROM tickets WHERE reduction_id=1 ORDER BY id"
    ).fetchall()
    assert len(ticket_states) == 2
    assert ticket_states[0] == ("t-1", "done")
    assert ticket_states[1] == ("t-2", "done")

    # Check event emitted
    events = conn.execute(
        "SELECT kind, run_id FROM events WHERE kind='reduction_accepted' ORDER BY id"
    ).fetchall()
    assert len(events) >= 1
    assert events[-1][0] == "reduction_accepted"
    assert events[-1][1] == "run-acc"

    conn.close()


def test_reject_reduction_success(loopback_client: TestClient, temp_home: Path):
    """POST /api/reductions/{id}/reject on pending reduction => 200, state=rejected, tickets failed, events emitted."""
    import sqlite3
    from server.auth import read_token

    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    # Seed run
    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('run-rej', 'example', 'local', 'running', 'reduce', 'main', '{}', 0, 0)"""
    )

    # Seed tickets (some needs_human linked to reduction)
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                worker_host, reduction_id, payload_json, created_at, updated_at)
           VALUES ('t-4', 'run-rej', 'reduce', 'needs_human', 'cpu', 100, 1,
                   NULL, 2, '{"goal":"test-4"}', 0, 0)"""
    )
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                worker_host, reduction_id, payload_json, created_at, updated_at)
           VALUES ('t-5', 'run-rej', 'reduce', 'needs_human', 'cpu', 100, 1,
                   NULL, 2, '{"goal":"test-5"}', 0, 0)"""
    )

    # Seed pending reduction
    conn.execute(
        """INSERT INTO reductions (id, run_id, phase, kind, json, review_state, created_at, updated_at)
           VALUES (2, 'run-rej', 'reduce', 'hypothesis', '{"title":"Rejected reduction"}', 'pending', 0, 0)"""
    )

    conn.commit()
    conn.close()

    token = read_token(temp_home)

    # Reject reduction
    response = loopback_client.post(
        "/api/reductions/2/reject",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200

    data = response.json()
    assert data["review_state"] == "rejected"

    # Verify via sqlite
    conn = sqlite3.connect(db_path)

    # Check reduction state
    row = conn.execute("SELECT review_state FROM reductions WHERE id=2").fetchone()
    assert row[0] == "rejected"

    # Check linked tickets are failed
    ticket_states = conn.execute(
        "SELECT id, state FROM tickets WHERE reduction_id=2 ORDER BY id"
    ).fetchall()
    assert len(ticket_states) == 2
    assert ticket_states[0] == ("t-4", "failed")
    assert ticket_states[1] == ("t-5", "failed")

    # Check reduction_rejected event emitted
    events = conn.execute(
        "SELECT kind, run_id FROM events WHERE kind='reduction_rejected' ORDER BY id"
    ).fetchall()
    assert len(events) >= 1
    assert events[-1][0] == "reduction_rejected"
    assert events[-1][1] == "run-rej"

    # Check ticket_failed events emitted (one per ticket)
    ticket_failed_events = conn.execute(
        "SELECT kind, ticket_id FROM events WHERE kind='ticket_failed' ORDER BY id"
    ).fetchall()
    assert len(ticket_failed_events) >= 2
    # Check last 2 events are for our tickets
    assert ticket_failed_events[-2][1] == "t-4"
    assert ticket_failed_events[-1][1] == "t-5"

    conn.close()


def test_accept_reject_on_already_resolved_409(loopback_client: TestClient, temp_home: Path):
    """POST /api/reductions/{id}/accept|reject on already-resolved reduction => 409."""
    import sqlite3
    from server.auth import read_token

    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    # Seed run
    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('run-resolved', 'example', 'local', 'running', 'reduce', 'main', '{}', 0, 0)"""
    )

    # Seed already-accepted reduction
    conn.execute(
        """INSERT INTO reductions (id, run_id, phase, kind, json, review_state, created_at, updated_at)
           VALUES (3, 'run-resolved', 'reduce', 'hypothesis', '{"title":"Already accepted"}', 'accepted', 0, 0)"""
    )

    conn.commit()
    conn.close()

    token = read_token(temp_home)

    # Try to accept again
    response = loopback_client.post(
        "/api/reductions/3/accept",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 409
    data = response.json()
    assert "detail" in data
    assert "already resolved" in data["detail"]

    # Try to reject
    response = loopback_client.post(
        "/api/reductions/3/reject",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 409
    data = response.json()
    assert "detail" in data
    assert "already resolved" in data["detail"]


def test_accept_reject_unknown_reduction_404(loopback_client: TestClient, temp_home: Path):
    """POST /api/reductions/{unknown}/accept|reject => 404."""
    from server.auth import read_token

    token = read_token(temp_home)

    # Try to accept unknown reduction
    response = loopback_client.post(
        "/api/reductions/999/accept",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404

    # Try to reject unknown reduction
    response = loopback_client.post(
        "/api/reductions/999/reject",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404


def test_accept_reject_requires_auth(loopback_client: TestClient, temp_home: Path):
    """POST /api/reductions/{id}/accept|reject without token => 401."""
    import sqlite3

    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    # Seed run and pending reduction
    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('run-auth-red', 'example', 'local', 'running', 'reduce', 'main', '{}', 0, 0)"""
    )
    conn.execute(
        """INSERT INTO reductions (id, run_id, phase, kind, json, review_state, created_at, updated_at)
           VALUES (4, 'run-auth-red', 'reduce', 'hypothesis', '{"title":"Auth test"}', 'pending', 0, 0)"""
    )
    conn.commit()
    conn.close()

    # Try to accept without token
    response = loopback_client.post("/api/reductions/4/accept")
    assert response.status_code == 401

    # Try to reject without token
    response = loopback_client.post("/api/reductions/4/reject")
    assert response.status_code == 401


def test_run_metrics_endpoint_deterministic_buckets(loopback_client: TestClient, temp_home: Path):
    """GET /api/runs/{id}/metrics aggregates REAL time-bucketed metrics with deterministic range.

    Throughput = attempts ended in bucket; done/failed cumulative from terminal outcomes;
    error_rate = failed/total per bucket; crew_online tracks crew events.
    Buckets span from run.created_at to latest event/attempt ts (deterministic, no wall-clock).
    """
    import sqlite3

    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    # Create run at t=1000
    run_created = 1000.0
    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('metrics-run', 'example', 'local', 'running', 'work', 'main', '{}', ?, ?)""",
        (run_created, run_created)
    )

    # Create 2 tickets for the run
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts, payload_json, created_at, updated_at)
           VALUES ('metrics-run/t-1', 'metrics-run', 'work', 'done', 'cpu', 0, 1, '{}', ?, ?)""",
        (run_created, run_created)
    )
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts, payload_json, created_at, updated_at)
           VALUES ('metrics-run/t-2', 'metrics-run', 'work', 'failed', 'cpu', 0, 1, '{}', ?, ?)""",
        (run_created, run_created)
    )

    # Bucket width = 300s (5 minutes)
    # Create attempts in 3 buckets: [1000, 1300), [1300, 1600), [1600, 1900)

    # Bucket 0 [1000, 1300): 2 attempts ended (1 ok, 1 driver_failed)
    conn.execute(
        """INSERT INTO attempts (ticket_id, phase, host, attempt, started_at, ended_at, outcome, termination_reason)
           VALUES ('metrics-run/t-1', 'work', 'h1', 1, ?, ?, 'ok', 'goal_met')""",
        (1100.0, 1200.0)
    )
    conn.execute(
        """INSERT INTO attempts (ticket_id, phase, host, attempt, started_at, ended_at, outcome, termination_reason)
           VALUES ('metrics-run/t-2', 'work', 'h1', 1, ?, ?, 'driver_failed', 'contract_fail')""",
        (1150.0, 1250.0)
    )

    # Bucket 1 [1300, 1600): 1 attempt ended (ok)
    conn.execute(
        """INSERT INTO attempts (ticket_id, phase, host, attempt, started_at, ended_at, outcome, termination_reason)
           VALUES ('metrics-run/t-1', 'work', 'h2', 2, ?, ?, 'ok', 'goal_met')""",
        (1400.0, 1500.0)
    )

    # Bucket 2 [1600, 1900): 1 attempt ended (driver_failed)
    conn.execute(
        """INSERT INTO attempts (ticket_id, phase, host, attempt, started_at, ended_at, outcome, termination_reason)
           VALUES ('metrics-run/t-2', 'work', 'h2', 2, ?, ?, 'driver_failed', 'driver_error')""",
        (1700.0, 1800.0)
    )

    # Crew events: crew_added at t=1100 (online), crew_down at t=1500 (offline)
    conn.execute(
        """INSERT INTO events (ts, kind, run_id, host, message, data_json)
           VALUES (?, 'crew_added', 'metrics-run', 'h1', 'Crew h1 added', '{}')""",
        (1100.0,)
    )
    conn.execute(
        """INSERT INTO events (ts, kind, run_id, host, message, data_json)
           VALUES (?, 'crew_added', 'metrics-run', 'h2', 'Crew h2 added', '{}')""",
        (1200.0,)
    )
    conn.execute(
        """INSERT INTO events (ts, kind, run_id, host, message, data_json)
           VALUES (?, 'crew_down', 'metrics-run', 'h1', 'Crew h1 down', '{}')""",
        (1500.0,)
    )

    conn.commit()
    conn.close()

    # Request metrics (bucket_s defaults to 300)
    response = loopback_client.get("/api/runs/metrics-run/metrics?bucket_s=300")
    assert response.status_code == 200

    data = response.json()
    assert data["run_id"] == "metrics-run"
    assert data["bucket_s"] == 300

    buckets = data["buckets"]
    # Latest event/attempt ts = 1800, so range [1000, 1900) = 3 buckets
    assert len(buckets) == 3

    # Bucket 0 [1000, 1300): throughput=2, done_cum=1, failed_cum=1, error_rate=0.5 (1/2), crew_online=2
    b0 = buckets[0]
    assert b0["t_start"] == 1000.0
    assert b0["throughput"] == 2  # 2 attempts ended
    assert b0["done_cumulative"] == 1  # 1 ok
    assert b0["failed_cumulative"] == 1  # 1 failed
    assert abs(b0["error_rate"] - 0.5) < 0.01  # 1/2
    assert b0["crew_online"] == 2  # h1+h2 online by end of bucket

    # Bucket 1 [1300, 1600): throughput=1, done_cum=2, failed_cum=1, error_rate=0 (1 ok), crew_online=1 (h1 down at 1500)
    b1 = buckets[1]
    assert b1["t_start"] == 1300.0
    assert b1["throughput"] == 1
    assert b1["done_cumulative"] == 2  # cumulative: 1+1
    assert b1["failed_cumulative"] == 1  # cumulative: still 1
    assert abs(b1["error_rate"] - 0.0) < 0.01  # 0/1
    assert b1["crew_online"] == 1  # only h2 by end of bucket

    # Bucket 2 [1600, 1900): throughput=1, done_cum=2, failed_cum=2, error_rate=1.0 (1 failed), crew_online=1
    b2 = buckets[2]
    assert b2["t_start"] == 1600.0
    assert b2["throughput"] == 1
    assert b2["done_cumulative"] == 2  # cumulative: still 2
    assert b2["failed_cumulative"] == 2  # cumulative: 1+1
    assert abs(b2["error_rate"] - 1.0) < 0.01  # 1/1
    assert b2["crew_online"] == 1


def test_run_metrics_empty_run(loopback_client: TestClient, temp_home: Path):
    """GET /api/runs/{id}/metrics for a run with no events/attempts => empty buckets."""
    import sqlite3

    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('empty-run', 'example', 'local', 'running', 'work', 'main', '{}', 1000, 1000)"""
    )
    conn.commit()
    conn.close()

    response = loopback_client.get("/api/runs/empty-run/metrics")
    assert response.status_code == 200

    data = response.json()
    assert data["run_id"] == "empty-run"
    assert data["buckets"] == []  # Truthful empty


def test_run_metrics_unknown_run_404(loopback_client: TestClient, temp_home: Path):
    """GET /api/runs/{unknown}/metrics => 404."""
    response = loopback_client.get("/api/runs/unknown/metrics")
    assert response.status_code == 404


# --- Ticket Detail Enrichments (history / reason / reduction / available_actions) ---

def test_ticket_detail_includes_history(loopback_client: TestClient, temp_home: Path):
    """GET /api/tickets/{id} includes event history."""
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    # Create run and ticket
    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('r1', 'stub', 'stub', 'running', 'work', 'main', '{}', 0, 0)"""
    )
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                available_at, tried_hosts, payload_json, created_at, updated_at)
           VALUES ('r1/t-0', 'r1', 'work', 'queued', 'cpu', 0, 0, 0, '[]', '{"goal": "test"}', 0, 0)"""
    )
    # Add events
    conn.execute(
        """INSERT INTO events (ts, kind, run_id, ticket_id, host, message, data_json)
           VALUES (100, 'ticket_claimed', 'r1', 'r1/t-0', 'host-A', 'claimed', '{}')"""
    )
    conn.execute(
        """INSERT INTO events (ts, kind, run_id, ticket_id, host, message, data_json)
           VALUES (200, 'ticket_started', 'r1', 'r1/t-0', 'host-A', 'started', '{"attempt": 1}')"""
    )
    conn.commit()
    conn.close()

    response = loopback_client.get("/api/tickets/r1%2Ft-0")
    assert response.status_code == 200

    data = response.json()
    assert "history" in data
    assert len(data["history"]) == 2
    assert data["history"][0]["kind"] == "ticket_claimed"
    assert data["history"][1]["kind"] == "ticket_started"


def test_ticket_detail_reason_needs_human_with_reduction(loopback_client: TestClient, temp_home: Path):
    """GET /api/tickets/{id} derives reason for needs_human with reduction_id."""
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    # Create run, ticket, and reduction
    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('r1', 'stub', 'stub', 'running', 'work', 'main', '{}', 0, 0)"""
    )
    conn.execute(
        """INSERT INTO reductions (run_id, phase, kind, review_state, json, created_at, updated_at)
           VALUES ('r1', 'work', 'cluster', 'pending',
                   '{"cause_category": "parser", "signature": "type error"}', 0, 0)"""
    )
    rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                available_at, tried_hosts, reduction_id, payload_json, created_at, updated_at)
           VALUES ('r1/t-0', 'r1', 'work', 'needs_human', 'cpu', 0, 0, 0, '[]', ?, '{"goal": "test"}', 0, 0)""",
        (rid,)
    )
    conn.commit()
    conn.close()

    response = loopback_client.get("/api/tickets/r1%2Ft-0")
    assert response.status_code == 200

    data = response.json()
    assert "reason" in data
    assert data["reason"] is not None
    assert "reduction #" in data["reason"].lower()
    assert "parser" in data["reason"].lower() or "type error" in data["reason"].lower()


def test_ticket_detail_reason_failed(loopback_client: TestClient, temp_home: Path):
    """GET /api/tickets/{id} derives reason for failed ticket from latest attempt."""
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    # Create run and ticket
    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('r1', 'stub', 'stub', 'running', 'work', 'main', '{}', 0, 0)"""
    )
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                available_at, tried_hosts, payload_json, created_at, updated_at)
           VALUES ('r1/t-0', 'r1', 'work', 'failed', 'cpu', 0, 1, 0, '[]', '{"goal": "test"}', 0, 0)"""
    )
    # Add failed attempt
    conn.execute(
        """INSERT INTO attempts (ticket_id, phase, host, attempt, started_at, ended_at,
                                 outcome, termination_reason, result_ref, error_summary)
           VALUES ('r1/t-0', 'work', 'host-A', 1, 0, 100, 'driver_failed', 'driver_error', NULL, 'empty output')"""
    )
    conn.commit()
    conn.close()

    response = loopback_client.get("/api/tickets/r1%2Ft-0")
    assert response.status_code == 200

    data = response.json()
    assert "reason" in data
    assert data["reason"] is not None
    assert "driver_error" in data["reason"].lower()


def test_ticket_detail_available_actions_queued(loopback_client: TestClient, temp_home: Path):
    """GET /api/tickets/{id} includes correct available_actions for queued ticket."""
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('r1', 'stub', 'stub', 'running', 'work', 'main', '{}', 0, 0)"""
    )
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                available_at, tried_hosts, payload_json, created_at, updated_at)
           VALUES ('r1/t-0', 'r1', 'work', 'queued', 'cpu', 0, 0, 0, '[]', '{"goal": "test"}', 0, 0)"""
    )
    conn.commit()
    conn.close()

    response = loopback_client.get("/api/tickets/r1%2Ft-0")
    assert response.status_code == 200

    data = response.json()
    assert "available_actions" in data
    assert set(data["available_actions"]) == {"reprioritize", "abandon"}


def test_ticket_detail_available_actions_failed(loopback_client: TestClient, temp_home: Path):
    """GET /api/tickets/{id} includes correct available_actions for failed ticket."""
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('r1', 'stub', 'stub', 'running', 'work', 'main', '{}', 0, 0)"""
    )
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                available_at, tried_hosts, payload_json, created_at, updated_at)
           VALUES ('r1/t-0', 'r1', 'work', 'failed', 'cpu', 0, 0, 0, '[]', '{"goal": "test"}', 0, 0)"""
    )
    conn.commit()
    conn.close()

    response = loopback_client.get("/api/tickets/r1%2Ft-0")
    assert response.status_code == 200

    data = response.json()
    assert "available_actions" in data
    assert data["available_actions"] == ["retry"]


def _seed_finding_ticket(temp_home: Path, state: str, finding_json: str | None) -> None:
    """Seed run 'r1' + ticket 'r1/t-0' in ``state``, optionally with a finding row."""
    conn = sqlite3.connect(str(temp_home / "queue.db"))
    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('r1', 'stub', 'stub', 'running', 'work', 'main', '{}', 0, 0)"""
    )
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                available_at, tried_hosts, payload_json, created_at, updated_at)
           VALUES ('r1/t-0', 'r1', 'work', ?, 'cpu', 0, 1, 0, '[]', '{"goal": "test"}', 0, 0)""",
        (state,),
    )
    if finding_json is not None:
        conn.execute(
            """INSERT INTO findings (run_id, ticket_id, kind, json, created_at)
               VALUES ('r1', 'r1/t-0', 'result', ?, 100)""",
            (finding_json,),
        )
    conn.commit()
    conn.close()


def test_ticket_detail_includes_finding_answer(loopback_client: TestClient, temp_home: Path):
    """GET /api/tickets/{id} surfaces the finding doc and its answer prose."""
    answer = "The consumer pool was pinned to one region; rebalancing restored 4200 msg/s."
    _seed_finding_ticket(temp_home, "done", json.dumps({"answer": answer, "sources": 3}))

    response = loopback_client.get("/api/tickets/r1%2Ft-0")
    assert response.status_code == 200

    data = response.json()
    assert data["answer"] == answer
    assert data["finding"]["kind"] == "result"
    assert data["finding"]["created_at"] == 100
    assert data["finding"]["json"] == {"answer": answer, "sources": 3}


def test_ticket_detail_finding_without_answer_prose(loopback_client: TestClient, temp_home: Path):
    """A structured finding with no 'answer' string yields the doc and a null answer."""
    doc = {"reproduced": True, "root_cause": {"signature": "off-by-one in cursor"}}
    _seed_finding_ticket(temp_home, "done", json.dumps(doc))

    response = loopback_client.get("/api/tickets/r1%2Ft-0")
    assert response.status_code == 200

    data = response.json()
    assert data["answer"] is None
    assert data["finding"]["json"] == doc


def test_ticket_detail_returns_latest_finding(loopback_client: TestClient, temp_home: Path):
    """With several findings (retried ticket), the newest one is returned."""
    _seed_finding_ticket(temp_home, "done", json.dumps({"answer": "first pass"}))
    conn = sqlite3.connect(str(temp_home / "queue.db"))
    conn.execute(
        """INSERT INTO findings (run_id, ticket_id, kind, json, created_at)
           VALUES ('r1', 'r1/t-0', 'result', ?, 200)""",
        (json.dumps({"answer": "second pass"}),),
    )
    conn.commit()
    conn.close()

    data = loopback_client.get("/api/tickets/r1%2Ft-0").json()
    assert data["answer"] == "second pass"


def test_ticket_detail_no_finding(loopback_client: TestClient, temp_home: Path):
    """A ticket with no finding row reports null finding and null answer."""
    _seed_finding_ticket(temp_home, "queued", None)

    data = loopback_client.get("/api/tickets/r1%2Ft-0").json()
    assert data["finding"] is None
    assert data["answer"] is None


def test_ticket_detail_blank_answer_is_null(loopback_client: TestClient, temp_home: Path):
    """A whitespace-only answer is reported as null, not as empty prose."""
    _seed_finding_ticket(temp_home, "done", json.dumps({"answer": "   "}))

    data = loopback_client.get("/api/tickets/r1%2Ft-0").json()
    assert data["answer"] is None
    assert data["finding"]["json"] == {"answer": "   "}


# --- Ticket Control Endpoints (abandon / retry / priority) ---

def test_abandon_ticket_endpoint(loopback_client: TestClient, temp_home: Path):
    """POST /api/tickets/{id}/abandon transitions to failed."""
    from server.auth import read_token

    token = read_token(temp_home)
    assert token is not None

    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('r1', 'stub', 'stub', 'running', 'work', 'main', '{}', 0, 0)"""
    )
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                available_at, tried_hosts, payload_json, created_at, updated_at)
           VALUES ('r1/t-0', 'r1', 'work', 'queued', 'cpu', 0, 0, 0, '[]', '{"goal": "test"}', 0, 0)"""
    )
    conn.commit()
    conn.close()

    response = loopback_client.post(
        "/api/tickets/r1%2Ft-0/abandon",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200

    data = response.json()
    assert data["state"] == "failed"

    # Verify via sqlite
    conn = sqlite3.connect(db_path)
    state = conn.execute("SELECT state FROM tickets WHERE id=?", ("r1/t-0",)).fetchone()[0]
    assert state == "failed"
    conn.close()


def test_abandon_ticket_endpoint_404(loopback_client: TestClient, temp_home: Path):
    """POST /api/tickets/{unknown}/abandon returns 404."""
    from server.auth import read_token

    token = read_token(temp_home)
    response = loopback_client.post(
        "/api/tickets/unknown/abandon",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404


def test_abandon_ticket_endpoint_409_terminal(loopback_client: TestClient, temp_home: Path):
    """POST /api/tickets/{id}/abandon returns 409 for terminal ticket."""
    from server.auth import read_token

    token = read_token(temp_home)
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('r1', 'stub', 'stub', 'running', 'work', 'main', '{}', 0, 0)"""
    )
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                available_at, tried_hosts, payload_json, created_at, updated_at)
           VALUES ('r1/t-0', 'r1', 'work', 'done', 'cpu', 0, 0, 0, '[]', '{"goal": "test"}', 0, 0)"""
    )
    conn.commit()
    conn.close()

    response = loopback_client.post(
        "/api/tickets/r1%2Ft-0/abandon",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 409


def test_retry_ticket_endpoint(loopback_client: TestClient, temp_home: Path):
    """POST /api/tickets/{id}/retry transitions failed -> queued."""
    from server.auth import read_token

    token = read_token(temp_home)
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('r1', 'stub', 'stub', 'running', 'work', 'main', '{}', 0, 0)"""
    )
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                available_at, tried_hosts, payload_json, created_at, updated_at)
           VALUES ('r1/t-0', 'r1', 'work', 'failed', 'cpu', 0, 0, 0, '[]', '{"goal": "test"}', 0, 0)"""
    )
    conn.commit()
    conn.close()

    response = loopback_client.post(
        "/api/tickets/r1%2Ft-0/retry",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200

    data = response.json()
    assert data["state"] == "queued"

    # Verify via sqlite
    conn = sqlite3.connect(db_path)
    state = conn.execute("SELECT state FROM tickets WHERE id=?", ("r1/t-0",)).fetchone()[0]
    assert state == "queued"
    conn.close()


def test_retry_ticket_endpoint_404(loopback_client: TestClient, temp_home: Path):
    """POST /api/tickets/{unknown}/retry returns 404."""
    from server.auth import read_token

    token = read_token(temp_home)
    response = loopback_client.post(
        "/api/tickets/unknown/retry",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404


def test_retry_ticket_endpoint_409_not_failed(loopback_client: TestClient, temp_home: Path):
    """POST /api/tickets/{id}/retry returns 409 for non-failed ticket."""
    from server.auth import read_token

    token = read_token(temp_home)
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('r1', 'stub', 'stub', 'running', 'work', 'main', '{}', 0, 0)"""
    )
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                available_at, tried_hosts, payload_json, created_at, updated_at)
           VALUES ('r1/t-0', 'r1', 'work', 'queued', 'cpu', 0, 0, 0, '[]', '{"goal": "test"}', 0, 0)"""
    )
    conn.commit()
    conn.close()

    response = loopback_client.post(
        "/api/tickets/r1%2Ft-0/retry",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 409


def test_set_priority_endpoint(loopback_client: TestClient, temp_home: Path):
    """POST /api/tickets/{id}/priority updates priority."""
    from server.auth import read_token

    token = read_token(temp_home)
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('r1', 'stub', 'stub', 'running', 'work', 'main', '{}', 0, 0)"""
    )
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                available_at, tried_hosts, payload_json, created_at, updated_at)
           VALUES ('r1/t-0', 'r1', 'work', 'queued', 'cpu', 5.0, 0, 0, '[]', '{"goal": "test"}', 0, 0)"""
    )
    conn.commit()
    conn.close()

    response = loopback_client.post(
        "/api/tickets/r1%2Ft-0/priority",
        json={"priority": 10.0},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200

    data = response.json()
    assert data["state"] == "queued"

    # Verify via sqlite
    conn = sqlite3.connect(db_path)
    priority = conn.execute("SELECT priority FROM tickets WHERE id=?", ("r1/t-0",)).fetchone()[0]
    assert priority == 10.0
    conn.close()


def test_set_priority_endpoint_404(loopback_client: TestClient, temp_home: Path):
    """POST /api/tickets/{unknown}/priority returns 404."""
    from server.auth import read_token

    token = read_token(temp_home)
    response = loopback_client.post(
        "/api/tickets/unknown/priority",
        json={"priority": 10.0},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404


def test_set_priority_endpoint_409_terminal(loopback_client: TestClient, temp_home: Path):
    """POST /api/tickets/{id}/priority returns 409 for terminal ticket."""
    from server.auth import read_token

    token = read_token(temp_home)
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('r1', 'stub', 'stub', 'running', 'work', 'main', '{}', 0, 0)"""
    )
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                available_at, tried_hosts, payload_json, created_at, updated_at)
           VALUES ('r1/t-0', 'r1', 'work', 'done', 'cpu', 0, 0, 0, '[]', '{"goal": "test"}', 0, 0)"""
    )
    conn.commit()
    conn.close()

    response = loopback_client.post(
        "/api/tickets/r1%2Ft-0/priority",
        json={"priority": 10.0},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 409


def test_ticket_detail_reason_needs_human_guard_routed(loopback_client: TestClient, temp_home: Path):
    """A guard-routed (no-reduction) needs_human ticket explains the review, not 'goal_met'.

    The re-verify override path records an 'ok'/'goal_met' attempt but routes the
    ticket to needs_human. The derived reason must reflect the review need (from the
    needs_human event), never echo the misleading success token.
    """
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('r1', 'stub', 'stub', 'running', 'work', 'main', '{}', 0, 0)"""
    )
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                available_at, tried_hosts, reduction_id, payload_json, created_at, updated_at)
           VALUES ('r1/t-0', 'r1', 'work', 'needs_human', 'cpu', 0, 1, 0, '[]', NULL, '{"goal": "test"}', 0, 0)"""
    )
    # The re-verify override attempt is a *success* result.
    conn.execute(
        """INSERT INTO attempts (ticket_id, phase, host, attempt, started_at, ended_at,
                                 outcome, termination_reason, result_ref, error_summary)
           VALUES ('r1/t-0', 'work', 'host-A', 1, 0, 100, 'ok', 'goal_met', 's3://r', NULL)"""
    )
    conn.execute(
        """INSERT INTO events (ts, kind, run_id, ticket_id, message, data_json)
           VALUES (100, 'needs_human', 'r1', 'r1/t-0', 're-verify override', '{}')"""
    )
    conn.commit()
    conn.close()

    response = loopback_client.get("/api/tickets/r1%2Ft-0")
    assert response.status_code == 200
    data = response.json()
    assert data["reason"] is not None
    # Never surface the misleading success token as the reason.
    assert data["reason"] != "goal_met"
    assert "goal_met" not in data["reason"]
    assert "re-verify" in data["reason"].lower() or "review" in data["reason"].lower()


def test_ticket_detail_reason_parked(loopback_client: TestClient, temp_home: Path):
    """A parked ticket's reason names the resource it is waiting on."""
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('r1', 'stub', 'stub', 'running', 'work', 'main', '{}', 0, 0)"""
    )
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                available_at, tried_hosts, payload_json, created_at, updated_at)
           VALUES ('r1/t-0', 'r1', 'work', 'parked', 'gpu', 0, 0, 0, '[]', '{"goal": "test"}', 0, 0)"""
    )
    conn.commit()
    conn.close()

    response = loopback_client.get("/api/tickets/r1%2Ft-0")
    assert response.status_code == 200
    data = response.json()
    assert data["reason"] is not None
    assert "capacity" in data["reason"].lower()
    assert "gpu" in data["reason"]


def test_ticket_detail_reason_abandoned(loopback_client: TestClient, temp_home: Path):
    """A ticket failed via operator abandon explains that, even with no attempts."""
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('r1', 'stub', 'stub', 'running', 'work', 'main', '{}', 0, 0)"""
    )
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                available_at, tried_hosts, payload_json, created_at, updated_at)
           VALUES ('r1/t-0', 'r1', 'work', 'failed', 'cpu', 0, 0, 0, '[]', '{"goal": "test"}', 0, 0)"""
    )
    conn.execute(
        """INSERT INTO events (ts, kind, run_id, ticket_id, data_json)
           VALUES (100, 'ticket_abandoned', 'r1', 'r1/t-0', '{"reason": "operator_abandoned"}')"""
    )
    conn.commit()
    conn.close()

    response = loopback_client.get("/api/tickets/r1%2Ft-0")
    assert response.status_code == 200
    data = response.json()
    assert data["reason"] is not None
    assert "abandon" in data["reason"].lower()


def _seed_run_and_ticket(conn, run_state: str, ticket_state: str, ticket_id: str = "r1/t-0"):
    """Seed one run + one ticket in the given states."""
    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('r1', 'stub', 'stub', ?, 'work', 'main', '{}', 0, 0)""",
        (run_state,),
    )
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                available_at, tried_hosts, payload_json, created_at, updated_at)
           VALUES (?, 'r1', 'work', ?, 'cpu', 0, 1, 0, '[]', '{"goal": "test"}', 0, 0)""",
        (ticket_id, ticket_state),
    )
    conn.commit()


def test_retry_endpoint_reopens_terminal_run(loopback_client: TestClient, temp_home: Path):
    """Retrying a ticket in a finished run reopens the run so it can actually run."""
    from server.auth import read_token

    token = read_token(temp_home)
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)
    _seed_run_and_ticket(conn, run_state="done", ticket_state="failed")
    conn.close()

    response = loopback_client.post(
        "/api/tickets/r1%2Ft-0/retry",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200

    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT state FROM tickets WHERE id=?", ("r1/t-0",)).fetchone()[0] == "queued"
    assert conn.execute("SELECT state FROM runs WHERE id='r1'").fetchone()[0] == "running"
    conn.close()


def test_retry_available_for_failed_ticket_in_terminal_run(loopback_client: TestClient, temp_home: Path):
    """Retry is offered (it reopens the run), not hidden."""
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)
    _seed_run_and_ticket(conn, run_state="done", ticket_state="failed")
    conn.close()

    data = loopback_client.get("/api/tickets/r1%2Ft-0").json()
    assert "retry" in data["available_actions"]


def test_stranded_queued_ticket_explains_and_points_at_reopen(loopback_client: TestClient, temp_home: Path):
    """A queued ticket under a finished run says why nothing is dispatching it."""
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)
    _seed_run_and_ticket(conn, run_state="done", ticket_state="queued")
    conn.close()

    data = loopback_client.get("/api/tickets/r1%2Ft-0").json()
    assert data["reason"] is not None
    assert "done" in data["reason"] and "reopen" in data["reason"].lower()


def test_reopen_endpoint_puts_finished_run_back_to_running(loopback_client: TestClient, temp_home: Path):
    from server.auth import read_token

    token = read_token(temp_home)
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)
    _seed_run_and_ticket(conn, run_state="done", ticket_state="queued")
    conn.close()

    response = loopback_client.post(
        "/api/runs/r1/reopen", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["state"] == "running"


def test_reopen_endpoint_409_when_run_not_finished(loopback_client: TestClient, temp_home: Path):
    from server.auth import read_token

    token = read_token(temp_home)
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)
    _seed_run_and_ticket(conn, run_state="running", ticket_state="queued")
    conn.close()

    response = loopback_client.post(
        "/api/runs/r1/reopen", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 409


def test_reopen_endpoint_requires_auth(loopback_client: TestClient, temp_home: Path):
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)
    _seed_run_and_ticket(conn, run_state="done", ticket_state="queued")
    conn.close()

    assert loopback_client.post("/api/runs/r1/reopen").status_code == 401


def test_ticket_detail_includes_failure_detail(loopback_client: TestClient, temp_home: Path):
    """GET /api/tickets/{id} surfaces the captured raw failure output (result + timeline)."""
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('r1', 'stub', 'stub', 'running', 'work', 'main', '{}', 0, 0)"""
    )
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                available_at, tried_hosts, payload_json, created_at, updated_at)
           VALUES ('r1/t-0', 'r1', 'work', 'failed', 'cpu', 0, 1, 0, '[]', '{"goal": "test"}', 0, 0)"""
    )
    raw = "Traceback (most recent call last):\n  File x\nValueError: nope"
    conn.execute(
        """INSERT INTO attempts (ticket_id, phase, host, attempt, started_at, ended_at,
                                 outcome, termination_reason, result_ref, error_summary, error_detail)
           VALUES ('r1/t-0', 'work', 'host-A', 1, 0, 100, 'driver_failed', 'driver_error', NULL, 'empty output', ?)""",
        (raw,),
    )
    conn.commit()
    conn.close()

    response = loopback_client.get("/api/tickets/r1%2Ft-0")
    assert response.status_code == 200
    data = response.json()
    assert data["result"]["detail"] == raw
    assert data["attempt_timeline"][-1]["detail"] == raw


def test_set_priority_endpoint_409_running(loopback_client: TestClient, temp_home: Path):
    """Reprioritize is not offered for in-flight tickets, so the endpoint 409s (matches available_actions)."""
    from server.auth import read_token

    token = read_token(temp_home)
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('r1', 'stub', 'stub', 'running', 'work', 'main', '{}', 0, 0)"""
    )
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                available_at, tried_hosts, payload_json, created_at, updated_at)
           VALUES ('r1/t-0', 'r1', 'work', 'running', 'cpu', 0, 0, 0, '[]', '{"goal": "test"}', 0, 0)"""
    )
    conn.commit()
    conn.close()

    response = loopback_client.post(
        "/api/tickets/r1%2Ft-0/priority",
        json={"priority": 10.0},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 409
    # Endpoint legality agrees with the advertised available_actions.
    detail = loopback_client.get("/api/tickets/r1%2Ft-0").json()["available_actions"]
    assert "reprioritize" not in detail


def test_requeue_reduction_flagged_409(loopback_client: TestClient, temp_home: Path):
    """Requeue is not offered for a reduction-flagged needs_human ticket, so the endpoint 409s."""
    from server.auth import read_token

    token = read_token(temp_home)
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('r1', 'stub', 'stub', 'running', 'work', 'main', '{}', 0, 0)"""
    )
    conn.execute(
        """INSERT INTO reductions (run_id, phase, kind, review_state, json, created_at, updated_at)
           VALUES ('r1', 'work', 'cluster', 'pending', '{"cause_category": "x", "signature": "y"}', 0, 0)"""
    )
    rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                available_at, tried_hosts, reduction_id, payload_json, created_at, updated_at)
           VALUES ('r1/t-0', 'r1', 'work', 'needs_human', 'cpu', 0, 0, 0, '[]', ?, '{"goal": "test"}', 0, 0)""",
        (rid,),
    )
    conn.commit()
    conn.close()

    response = loopback_client.post(
        "/api/tickets/r1%2Ft-0/requeue",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 409


def test_abandon_ticket_requires_auth(loopback_client: TestClient, temp_home: Path):
    """POST /api/tickets/{id}/abandon without token => 401."""
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('r1', 'stub', 'stub', 'running', 'work', 'main', '{}', 0, 0)"""
    )
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                available_at, tried_hosts, payload_json, created_at, updated_at)
           VALUES ('r1/t-0', 'r1', 'work', 'queued', 'cpu', 0, 0, 0, '[]', '{"goal": "test"}', 0, 0)"""
    )
    conn.commit()
    conn.close()

    response = loopback_client.post("/api/tickets/r1%2Ft-0/abandon")
    assert response.status_code == 401


def test_retry_ticket_requires_auth(loopback_client: TestClient, temp_home: Path):
    """POST /api/tickets/{id}/retry without token => 401."""
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('r1', 'stub', 'stub', 'running', 'work', 'main', '{}', 0, 0)"""
    )
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                available_at, tried_hosts, payload_json, created_at, updated_at)
           VALUES ('r1/t-0', 'r1', 'work', 'failed', 'cpu', 0, 0, 0, '[]', '{"goal": "test"}', 0, 0)"""
    )
    conn.commit()
    conn.close()

    response = loopback_client.post("/api/tickets/r1%2Ft-0/retry")
    assert response.status_code == 401


def test_set_priority_requires_auth(loopback_client: TestClient, temp_home: Path):
    """POST /api/tickets/{id}/priority without token => 401."""
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES ('r1', 'stub', 'stub', 'running', 'work', 'main', '{}', 0, 0)"""
    )
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                available_at, tried_hosts, payload_json, created_at, updated_at)
           VALUES ('r1/t-0', 'r1', 'work', 'queued', 'cpu', 0, 0, 0, '[]', '{"goal": "test"}', 0, 0)"""
    )
    conn.commit()
    conn.close()

    response = loopback_client.post("/api/tickets/r1%2Ft-0/priority", json={"priority": 3.0})
    assert response.status_code == 401


def test_metrics_totals_and_retry_and_mean(client: TestClient, temp_home: Path):
    """GET /api/runs/{id}/metrics computes totals, retry_rate, mean_time_to_result_s from real attempts."""
    import time
    now = time.time()
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    # Seed a run with tickets and attempts as specified in the brief
    run_id = "metrics-test-run"
    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (run_id, "stub", "stub", "running", "work", "main", '{}', now, now)
    )

    # Seed tickets
    ticket_a = f"{run_id}/ticket-A"
    ticket_b = f"{run_id}/ticket-B"
    ticket_c = f"{run_id}/ticket-C"

    for tid in [ticket_a, ticket_b, ticket_c]:
        conn.execute(
            """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                    available_at, tried_hosts, payload_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (tid, run_id, "work", "queued", "cpu", 0, 0, now, '[]', '{"goal": "test"}', now, now)
        )
    conn.commit()

    # Seed attempts exactly as specified in the brief
    # ticket A, phase "work", attempt 1, outcome ok, started 0 ended 10
    # ticket A, phase "work", attempt 2, outcome ok, started 20 ended 50
    # ticket B, phase "work", attempt 1, outcome driver_failed, started 0 ended 4
    # ticket C, phase "reduce", attempt 1, outcome ok, started 0 ended 6
    attempts_data = [
        (ticket_a, "work", 1, now, now + 10, "ok"),
        (ticket_a, "work", 2, now + 20, now + 50, "ok"),
        (ticket_b, "work", 1, now, now + 4, "driver_failed"),
        (ticket_c, "reduce", 1, now, now + 6, "ok"),
    ]

    for tid, phase, attempt_num, started, ended, outcome in attempts_data:
        conn.execute(
            """INSERT INTO attempts (ticket_id, phase, host, attempt, started_at, ended_at, outcome,
                                     termination_reason, result_ref, error_summary, error_detail)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (tid, phase, "test-host", attempt_num, started, ended, outcome, "reason", None, None, None)
        )
    conn.commit()
    conn.close()

    # Fetch metrics
    response = client.get(f"/api/runs/{run_id}/metrics")
    assert response.status_code == 200

    data = response.json()

    # Verify totals: {attempts:4, done:3, failed:1, results:4, tickets:3}
    assert "totals" in data
    totals = data["totals"]
    assert totals["attempts"] == 4
    assert totals["done"] == 3
    assert totals["failed"] == 1
    assert totals["results"] == 4
    assert totals["tickets"] == 3

    # Verify retry_rate: 1/3 (ticket A has max attempt > 1, out of 3 tickets)
    assert "retry_rate" in data
    assert data["retry_rate"] == pytest.approx(1.0 / 3.0)

    # Verify mean_time_to_result_s: (10+30+4+6)/4 = 12.5
    assert "mean_time_to_result_s" in data
    assert data["mean_time_to_result_s"] == pytest.approx(12.5)


def test_metrics_by_phase(client: TestClient, temp_home: Path):
    """GET /api/runs/{id}/metrics computes by_phase stats with correct ordering and values."""
    import time
    now = time.time()
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    # Seed a run with tickets and attempts
    run_id = "metrics-phase-run"
    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (run_id, "stub", "stub", "running", "work", "main", '{}', now, now)
    )

    # Seed tickets
    ticket_a = f"{run_id}/ticket-A"
    ticket_b = f"{run_id}/ticket-B"
    ticket_c = f"{run_id}/ticket-C"

    for tid in [ticket_a, ticket_b, ticket_c]:
        conn.execute(
            """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority, attempts,
                                    available_at, tried_hosts, payload_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (tid, run_id, "work", "queued", "cpu", 0, 0, now, '[]', '{"goal": "test"}', now, now)
        )
    conn.commit()

    # Seed attempts (same as above) - ordered by id to ensure phase ordering
    attempts_data = [
        (ticket_a, "work", 1, now, now + 10, "ok"),
        (ticket_a, "work", 2, now + 20, now + 50, "ok"),
        (ticket_b, "work", 1, now, now + 4, "driver_failed"),
        (ticket_c, "reduce", 1, now, now + 6, "ok"),
    ]

    for tid, phase, attempt_num, started, ended, outcome in attempts_data:
        conn.execute(
            """INSERT INTO attempts (ticket_id, phase, host, attempt, started_at, ended_at, outcome,
                                     termination_reason, result_ref, error_summary, error_detail)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (tid, phase, "test-host", attempt_num, started, ended, outcome, "reason", None, None, None)
        )
    conn.commit()
    conn.close()

    # Fetch metrics
    response = client.get(f"/api/runs/{run_id}/metrics")
    assert response.status_code == 200

    data = response.json()

    # Verify by_phase is exactly two entries in order
    assert "by_phase" in data
    by_phase = data["by_phase"]
    assert len(by_phase) == 2

    # First entry: work phase
    work = by_phase[0]
    assert work["phase"] == "work"
    assert work["tickets"] == 2  # ticket A and B
    # mean_time_s: (10+30+4)/3 = 44/3 = 14.666...
    assert work["mean_time_s"] == pytest.approx((10 + 30 + 4) / 3.0)
    # failure_pct: 1 failed out of 3 attempts = 100/3 = 33.333...
    assert work["failure_pct"] == pytest.approx(100.0 / 3.0)

    # Second entry: reduce phase
    reduce = by_phase[1]
    assert reduce["phase"] == "reduce"
    assert reduce["tickets"] == 1  # ticket C
    assert reduce["mean_time_s"] == pytest.approx(6.0)
    assert reduce["failure_pct"] == pytest.approx(0.0)


def test_metrics_empty_run_aggregates(client: TestClient, temp_home: Path):
    """GET /api/runs/{id}/metrics for a run with no attempts returns correct empty aggregates."""
    import time
    now = time.time()
    db_path = str(temp_home / "queue.db")
    conn = sqlite3.connect(db_path)

    # Seed a run with NO attempts
    run_id = "empty-run"
    conn.execute(
        """INSERT INTO runs (id, playbook, site, state, phase, base_ref, config_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (run_id, "stub", "stub", "running", "work", "main", '{}', now, now)
    )
    conn.commit()
    conn.close()

    # Fetch metrics
    response = client.get(f"/api/runs/{run_id}/metrics")
    assert response.status_code == 200

    data = response.json()

    # Verify totals all 0
    assert "totals" in data
    totals = data["totals"]
    assert totals["attempts"] == 0
    assert totals["done"] == 0
    assert totals["failed"] == 0
    assert totals["results"] == 0
    assert totals["tickets"] == 0

    # Verify retry_rate is 0.0
    assert "retry_rate" in data
    assert data["retry_rate"] == 0.0

    # Verify mean_time_to_result_s is None
    assert "mean_time_to_result_s" in data
    assert data["mean_time_to_result_s"] is None

    # Verify by_phase is empty list
    assert "by_phase" in data
    assert data["by_phase"] == []

    # Verify buckets is still present (and empty)
    assert "buckets" in data
    assert data["buckets"] == []
