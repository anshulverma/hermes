"""
tests.unit.test_crew — crew management (add, health-gate, heartbeat_sweep) tests.

`add` admits only healthy hosts (gate on HealthReport.ok), `heartbeat_sweep`
down-requeues (no penalty) in-flight tickets of unreachable/unhealthy hosts, recovers down
hosts, renews/reclaims leases, and unparks ready classes.

Uses fake Site/Agent whose `health` returns a controllable HealthReport (no real network).
"""
import json
import sqlite3
import tempfile
from unittest.mock import MagicMock

import pytest

from engine import crew, events, queue, leases
from engine.db.migrate import apply_migrations, connect
from engine.models import Check, HealthReport, Ticket


# --- Fake Site/Agent for tests (controllable health, no-op provision) -------

class FakeSite:
    """Fake Site whose health() returns a controllable HealthReport."""
    name = "fake"

    def __init__(self, health_report: HealthReport):
        self.health_report = health_report

    def provision(self, host: str, base_ref: str) -> None:
        """No-op provision."""
        pass

    def health(self, host: str, agent) -> HealthReport:
        """Return the controllable health report."""
        return self.health_report

    def resource_classes(self) -> list[str]:
        return ["cpu"]


class FakeAgent:
    """Fake Agent for health checks."""
    name = "fake"


# --- Test fixtures -----------------------------------------------------------

@pytest.fixture
def db_path():
    """Temp db file path."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        path = f.name
    yield path
    # Cleanup WAL files too
    for suffix in ("", "-shm", "-wal"):
        try:
            import os
            os.unlink(path + suffix)
        except FileNotFoundError:
            pass


@pytest.fixture
def conn(db_path):
    """SQLite connection with schema applied."""
    apply_migrations(db_path)
    connection = connect(db_path)
    yield connection
    connection.close()


def seed_run(conn: sqlite3.Connection, run_id: str = "test-run") -> None:
    """Helper: insert a minimal run row."""
    now = 1234567890.0
    conn.execute(
        """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                             phase, created_at, updated_at)
           VALUES (?, 'test', 'fake', 'main', '{}', 'running', 'phase0', ?, ?)""",
        (run_id, now, now),
    )
    conn.commit()


def seed_ticket(
    conn: sqlite3.Connection,
    ticket_id: str,
    run_id: str = "test-run",
    state: str = "queued",
    worker_host: str | None = None,
) -> None:
    """Helper: insert a minimal ticket."""
    now = 1234567890.0
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority,
                                attempts, available_at, worker_host, tried_hosts,
                                payload_json, created_at, updated_at)
           VALUES (?, ?, 'phase0', ?, 'cpu', 0, 0, ?, ?, '[]', '{}', ?, ?)""",
        (ticket_id, run_id, state, now, worker_host, now, now),
    )
    conn.commit()


# --- Tests: add (health-gate admission) -------------------------------------

def test_add_admits_healthy_host(conn):
    """add() admits a host whose health report is ok."""
    now = 1234567890.0
    healthy_report = HealthReport(
        reachable=True,
        agent_ok=True,
        auth_ok=True,
        workspace_ready=True,
        guard_installed=True,
        resources={"cpu": 8},
        latency_ms=50,
        checks=[
            Check(name="reachable", ok=True, detail="OK"),
            Check(name="agent", ok=True, detail="OK"),
        ],
    )
    site = FakeSite(healthy_report)
    agent = FakeAgent()

    crew.add(conn, site, agent, host="h1", base_ref="main", now=now)

    # Verify crew row created with state=idle
    row = conn.execute("SELECT id, site, state, resources_json FROM crew WHERE id='h1'").fetchone()
    assert row is not None
    assert row[0] == "h1"
    assert row[1] == "fake"
    assert row[2] == "idle"
    resources = json.loads(row[3])
    assert resources == {"cpu": 8}

    # Verify event emitted
    event = conn.execute("SELECT kind, host FROM events ORDER BY id DESC LIMIT 1").fetchone()
    assert event[0] == "crew_added"
    assert event[1] == "h1"


def test_add_rejects_unhealthy_host(conn):
    """add() rejects an unhealthy host and lists failing checks."""
    now = 1234567890.0
    unhealthy_report = HealthReport(
        reachable=True,
        agent_ok=False,
        auth_ok=False,
        workspace_ready=True,
        guard_installed=True,
        resources={"cpu": 4},
        latency_ms=100,
        checks=[
            Check(name="reachable", ok=True, detail="OK"),
            Check(name="agent", ok=False, detail="agent not found"),
            Check(name="auth", ok=False, detail="auth failed"),
        ],
    )
    site = FakeSite(unhealthy_report)
    agent = FakeAgent()

    with pytest.raises(ValueError) as exc_info:
        crew.add(conn, site, agent, host="h2", base_ref="main", now=now)

    error_msg = str(exc_info.value)
    assert "h2" in error_msg
    assert "agent" in error_msg
    assert "auth" in error_msg

    # Verify NO crew row was created
    row = conn.execute("SELECT id FROM crew WHERE id='h2'").fetchone()
    assert row is None


def test_add_updates_existing_healthy_host(conn):
    """add() can re-admit an existing host if it becomes healthy again."""
    now = 1234567890.0
    # Insert a down host
    conn.execute(
        """INSERT INTO crew (id, site, capabilities, resources_json, state,
                             health_json, last_heartbeat, registered_at)
           VALUES ('h1', 'fake', '[]', '{"cpu": 4}', 'down', '{}', ?, ?)""",
        (now - 100, now - 100),
    )
    conn.commit()

    healthy_report = HealthReport(
        reachable=True,
        agent_ok=True,
        auth_ok=True,
        workspace_ready=True,
        guard_installed=True,
        resources={"cpu": 8},
        latency_ms=50,
        checks=[Check(name="reachable", ok=True, detail="OK")],
    )
    site = FakeSite(healthy_report)
    agent = FakeAgent()

    crew.add(conn, site, agent, host="h1", base_ref="main", now=now)

    # Verify crew row updated to idle with new resources
    row = conn.execute("SELECT state, resources_json FROM crew WHERE id='h1'").fetchone()
    assert row[0] == "idle"
    resources = json.loads(row[1])
    assert resources == {"cpu": 8}


# --- Tests: heartbeat_sweep --------------------------------------------------

def test_heartbeat_sweep_marks_unreachable_host_down(conn):
    """heartbeat_sweep sets state=down when a host becomes unreachable."""
    now = 1234567890.0
    seed_run(conn)

    # Add a healthy host
    conn.execute(
        """INSERT INTO crew (id, site, capabilities, resources_json, state,
                             health_json, last_heartbeat, registered_at)
           VALUES ('h1', 'fake', '[]', '{"cpu": 4}', 'idle', '{}', ?, ?)""",
        (now - 10, now - 100),
    )
    conn.commit()

    # Site now reports unreachable
    unreachable_report = HealthReport(
        reachable=False,
        agent_ok=False,
        auth_ok=False,
        workspace_ready=False,
        guard_installed=False,
        resources={},
        latency_ms=0,
        checks=[Check(name="reachable", ok=False, detail="timeout")],
    )
    site = FakeSite(unreachable_report)
    agent = FakeAgent()

    crew.heartbeat_sweep(conn, site, agent, now=now)

    # Verify host marked down
    row = conn.execute("SELECT state FROM crew WHERE id='h1'").fetchone()
    assert row[0] == "down"

    # Verify crew_down event
    event = conn.execute(
        "SELECT kind, host FROM events WHERE kind='crew_down' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert event is not None
    assert event[1] == "h1"


def test_heartbeat_sweep_requeues_in_flight_ticket_no_penalty(conn):
    """heartbeat_sweep requeues a down host's in-flight ticket with NO attempt penalty."""
    now = 1234567890.0
    seed_run(conn)

    # Add a busy host with an in-flight ticket
    conn.execute(
        """INSERT INTO crew (id, site, capabilities, resources_json, state,
                             health_json, last_heartbeat, registered_at)
           VALUES ('h1', 'fake', '[]', '{"cpu": 4}', 'busy', '{}', ?, ?)""",
        (now - 10, now - 100),
    )
    seed_ticket(conn, "test-run/t-1", state="running", worker_host="h1")
    conn.commit()

    # Site now reports unreachable
    unreachable_report = HealthReport(
        reachable=False,
        agent_ok=False,
        auth_ok=False,
        workspace_ready=False,
        guard_installed=False,
        resources={},
        latency_ms=0,
        checks=[Check(name="reachable", ok=False, detail="timeout")],
    )
    site = FakeSite(unreachable_report)
    agent = FakeAgent()

    crew.heartbeat_sweep(conn, site, agent, now=now)

    # Verify ticket requeued with attempts UNCHANGED
    row = conn.execute(
        "SELECT state, attempts, worker_host FROM tickets WHERE id='test-run/t-1'"
    ).fetchone()
    assert row[0] == "queued"
    assert row[1] == 0  # attempts unchanged (no penalty)
    assert row[2] is None  # worker_host cleared

    # Verify host marked down
    host_row = conn.execute("SELECT state FROM crew WHERE id='h1'").fetchone()
    assert host_row[0] == "down"


def test_heartbeat_sweep_recovers_down_host(conn):
    """heartbeat_sweep re-admits a down host that becomes healthy."""
    now = 1234567890.0
    seed_run(conn)

    # Add a down host
    conn.execute(
        """INSERT INTO crew (id, site, capabilities, resources_json, state,
                             health_json, last_heartbeat, registered_at)
           VALUES ('h1', 'fake', '[]', '{"cpu": 4}', 'down', '{}', ?, ?)""",
        (now - 100, now - 200),
    )
    conn.commit()

    # Site now reports healthy
    healthy_report = HealthReport(
        reachable=True,
        agent_ok=True,
        auth_ok=True,
        workspace_ready=True,
        guard_installed=True,
        resources={"cpu": 8},
        latency_ms=50,
        checks=[Check(name="reachable", ok=True, detail="OK")],
    )
    site = FakeSite(healthy_report)
    agent = FakeAgent()

    crew.heartbeat_sweep(conn, site, agent, now=now)

    # Verify host re-admitted to idle
    row = conn.execute("SELECT state, resources_json FROM crew WHERE id='h1'").fetchone()
    assert row[0] == "idle"
    resources = json.loads(row[1])
    assert resources == {"cpu": 8}

    # Verify crew_health event (recovery)
    event = conn.execute(
        "SELECT kind, host FROM events WHERE kind='crew_health' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert event is not None
    assert event[1] == "h1"


def test_heartbeat_sweep_renews_live_leases(conn):
    """heartbeat_sweep renews live (unexpired) leases."""
    now = 1234567890.0
    seed_run(conn)

    # Add a healthy host
    conn.execute(
        """INSERT INTO crew (id, site, capabilities, resources_json, state,
                             health_json, last_heartbeat, registered_at)
           VALUES ('h1', 'fake', '[]', '{"cpu": 4}', 'idle', '{}', ?, ?)""",
        (now - 10, now - 100),
    )

    # Add a live lease
    conn.execute(
        """INSERT INTO leases (id, run_id, resource_class, ticket_id, host,
                               acquired_at, ttl_s, expires_at)
           VALUES ('lease-1', 'test-run', 'cpu', 't1', 'h1', ?, 1800, ?)""",
        (now - 100, now + 1000),
    )
    conn.commit()

    healthy_report = HealthReport(
        reachable=True,
        agent_ok=True,
        auth_ok=True,
        workspace_ready=True,
        guard_installed=True,
        resources={"cpu": 4},
        latency_ms=50,
        checks=[Check(name="reachable", ok=True, detail="OK")],
    )
    site = FakeSite(healthy_report)
    agent = FakeAgent()

    old_expires = now + 1000
    crew.heartbeat_sweep(conn, site, agent, now=now)

    # Verify lease renewed (expires_at extended)
    row = conn.execute("SELECT expires_at FROM leases WHERE id='lease-1'").fetchone()
    new_expires = row[0]
    assert new_expires > old_expires  # extended


def test_heartbeat_sweep_reclaims_expired_leases(conn):
    """heartbeat_sweep reclaims expired leases and requeues non-terminal tickets."""
    now = 1234567890.0
    seed_run(conn)

    # Add a healthy host
    conn.execute(
        """INSERT INTO crew (id, site, capabilities, resources_json, state,
                             health_json, last_heartbeat, registered_at)
           VALUES ('h1', 'fake', '[]', '{"cpu": 4}', 'idle', '{}', ?, ?)""",
        (now - 10, now - 100),
    )

    # Add an expired lease with a running ticket
    seed_ticket(conn, "test-run/t-1", state="running", worker_host="h1")
    conn.execute(
        """INSERT INTO leases (id, run_id, resource_class, ticket_id, host,
                               acquired_at, ttl_s, expires_at)
           VALUES ('lease-1', 'test-run', 'cpu', 'test-run/t-1', 'h1', ?, 1800, ?)""",
        (now - 2000, now - 100),  # expired
    )
    conn.commit()

    healthy_report = HealthReport(
        reachable=True,
        agent_ok=True,
        auth_ok=True,
        workspace_ready=True,
        guard_installed=True,
        resources={"cpu": 4},
        latency_ms=50,
        checks=[Check(name="reachable", ok=True, detail="OK")],
    )
    site = FakeSite(healthy_report)
    agent = FakeAgent()

    crew.heartbeat_sweep(conn, site, agent, now=now)

    # Verify lease freed
    lease_row = conn.execute("SELECT id FROM leases WHERE id='lease-1'").fetchone()
    assert lease_row is None  # reclaimed

    # Verify ticket requeued (no penalty)
    ticket_row = conn.execute(
        "SELECT state, attempts FROM tickets WHERE id='test-run/t-1'"
    ).fetchone()
    assert ticket_row[0] == "queued"
    assert ticket_row[1] == 0  # no penalty


def test_heartbeat_sweep_unparks_ready_tickets(conn):
    """heartbeat_sweep unparks tickets when a class regains capacity (via reclaimed lease)."""
    now = 1234567890.0
    seed_run(conn)

    # Add one host with capacity 1
    conn.execute(
        """INSERT INTO crew (id, site, capabilities, resources_json, state,
                             health_json, last_heartbeat, registered_at)
           VALUES ('h1', 'fake', '[]', '{"cpu": 1}', 'idle', '{}', ?, ?)""",
        (now - 10, now - 100),
    )

    # Add an EXPIRED lease consuming the capacity (this will be reclaimed)
    conn.execute(
        """INSERT INTO leases (id, run_id, resource_class, ticket_id, host,
                               acquired_at, ttl_s, expires_at)
           VALUES ('lease-1', 'test-run', 'cpu', NULL, 'h1', ?, 1800, ?)""",
        (now - 2000, now - 100),  # expired
    )

    # Add a parked ticket (was parked because capacity was at limit)
    seed_ticket(conn, "test-run/t-1", state="parked")
    conn.commit()

    healthy_report = HealthReport(
        reachable=True,
        agent_ok=True,
        auth_ok=True,
        workspace_ready=True,
        guard_installed=True,
        resources={"cpu": 1},
        latency_ms=50,
        checks=[Check(name="reachable", ok=True, detail="OK")],
    )
    site = FakeSite(healthy_report)
    agent = FakeAgent()

    crew.heartbeat_sweep(conn, site, agent, now=now)

    # Verify parked ticket unparked (capacity regained via reclaimed lease)
    t1_row = conn.execute("SELECT state FROM tickets WHERE id='test-run/t-1'").fetchone()
    assert t1_row[0] == "queued"

    # Verify lease was reclaimed
    lease_row = conn.execute("SELECT id FROM leases WHERE id='lease-1'").fetchone()
    assert lease_row is None


def test_heartbeat_sweep_is_atomic_no_partial_commit(conn):
    """A site.health raising for a LATER host rolls back the WHOLE sweep.

    Regression for the requeue_transport mid-sweep self-commit: an earlier host
    going down (marking it down + requeuing its in-flight ticket) must NOT be
    persisted if a subsequent host's health probe raises. The sweep is one
    transaction that commits exactly once.
    """
    now = 1234567890.0
    seed_run(conn)

    # h1 (down candidate, with an in-flight ticket) probed first; h2 raises.
    conn.execute(
        """INSERT INTO crew (id, site, capabilities, resources_json, state,
                             health_json, last_heartbeat, registered_at)
           VALUES ('h1', 'fake', '[]', '{"cpu": 4}', 'busy', '{}', ?, ?)""",
        (now - 10, now - 100),
    )
    conn.execute(
        """INSERT INTO crew (id, site, capabilities, resources_json, state,
                             health_json, last_heartbeat, registered_at)
           VALUES ('h2', 'fake', '[]', '{"cpu": 4}', 'idle', '{}', ?, ?)""",
        (now - 10, now - 100),
    )
    seed_ticket(conn, "test-run/t-1", state="running", worker_host="h1")
    conn.commit()

    unreachable_report = HealthReport(
        reachable=False, agent_ok=False, auth_ok=False, workspace_ready=False,
        guard_installed=False, resources={}, latency_ms=0,
        checks=[Check(name="reachable", ok=False, detail="timeout")],
    )

    class RaiseOnSecondSite:
        """health() returns unreachable for h1, then raises for h2."""
        name = "fake"

        def __init__(self):
            self.calls = 0

        def health(self, host, agent):
            self.calls += 1
            if host == "h2":
                raise RuntimeError("probe blew up for h2")
            return unreachable_report

        def resource_classes(self):
            return ["cpu"]

    site = RaiseOnSecondSite()
    agent = FakeAgent()

    with pytest.raises(RuntimeError):
        crew.heartbeat_sweep(conn, site, agent, now=now)

    # NOTHING from h1's processing is persisted: h1 still busy, ticket still
    # running (no partial commit from the mid-sweep requeue).
    assert conn.execute("SELECT state FROM crew WHERE id='h1'").fetchone()[0] == "busy"
    trow = conn.execute(
        "SELECT state, worker_host FROM tickets WHERE id='test-run/t-1'"
    ).fetchone()
    assert trow[0] == "running"
    assert trow[1] == "h1"
    # No crew_down event leaked through a mid-sweep commit.
    assert conn.execute(
        "SELECT COUNT(*) FROM events WHERE kind='crew_down'"
    ).fetchone()[0] == 0


# --- Tests: list, drain, remove ----------------------------------------------

def test_list_returns_crew_members(conn):
    """list() returns all crew members with parsed health/resources."""
    now = 1234567890.0
    conn.execute(
        """INSERT INTO crew (id, site, capabilities, resources_json, state,
                             health_json, last_heartbeat, registered_at)
           VALUES ('h1', 'fake', '[]', '{"cpu": 4}', 'idle', '{"ok": true}', ?, ?)""",
        (now - 10, now - 100),
    )
    conn.execute(
        """INSERT INTO crew (id, site, capabilities, resources_json, state,
                             health_json, last_heartbeat, registered_at)
           VALUES ('h2', 'fake', '[]', '{"cpu": 8}', 'busy', '{"ok": true}', ?, ?)""",
        (now - 10, now - 100),
    )
    conn.commit()

    members = crew.list(conn)
    assert len(members) == 2
    assert members[0].id in ("h1", "h2")
    assert members[0].resources in ({"cpu": 4}, {"cpu": 8})


def test_drain_sets_state_draining(conn):
    """drain() sets a crew member's state to draining."""
    now = 1234567890.0
    conn.execute(
        """INSERT INTO crew (id, site, capabilities, resources_json, state,
                             health_json, last_heartbeat, registered_at)
           VALUES ('h1', 'fake', '[]', '{"cpu": 4}', 'idle', '{}', ?, ?)""",
        (now - 10, now - 100),
    )
    conn.commit()

    crew.drain(conn, "h1", now=now)

    row = conn.execute("SELECT state FROM crew WHERE id='h1'").fetchone()
    assert row[0] == "draining"

    # Verify crew_drained event
    event = conn.execute(
        "SELECT kind, host FROM events WHERE kind='crew_drained' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert event is not None
    assert event[1] == "h1"


def test_remove_deletes_crew_member(conn):
    """remove() deletes a crew member."""
    now = 1234567890.0
    conn.execute(
        """INSERT INTO crew (id, site, capabilities, resources_json, state,
                             health_json, last_heartbeat, registered_at)
           VALUES ('h1', 'fake', '[]', '{"cpu": 4}', 'draining', '{}', ?, ?)""",
        (now - 10, now - 100),
    )
    conn.commit()

    crew.remove(conn, "h1")

    row = conn.execute("SELECT id FROM crew WHERE id='h1'").fetchone()
    assert row is None
