"""Tests for lease event emission.

TDD: written FIRST to drive lease event emission in leases.py.
"""
import json
import sqlite3
import tempfile
import time
from pathlib import Path

import pytest

from engine.db.migrate import apply_migrations, connect
from engine import leases


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        path = f.name
    yield path
    for suffix in ("", "-shm", "-wal"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)


@pytest.fixture
def conn(db_path):
    apply_migrations(db_path)
    connection = connect(db_path)
    yield connection
    connection.close()


def _mk_run(conn, run_id="r1"):
    conn.execute(
        """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                             phase, created_at, updated_at)
           VALUES (?, 'test', 'local', 'main', '{}', 'running', 'work', 0, 0)""",
        (run_id,),
    )
    conn.commit()


def _mk_ticket(conn, ticket_id, run_id="r1", state="queued"):
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority,
                                attempts, available_at, tried_hosts, payload_json,
                                created_at, updated_at)
           VALUES (?, ?, 'work', ?, 'cpu', 0.0, 0, 0.0, '[]', '{}', 0, 0)""",
        (ticket_id, run_id, state),
    )
    conn.commit()


def _mk_crew(conn, host_id, resources=None):
    if resources is None:
        resources = {"cpu": 2}
    now = time.time()
    conn.execute(
        """INSERT INTO crew (id, site, capabilities, resources_json, state,
                             health_json, last_heartbeat, registered_at)
           VALUES (?, 'local', '[]', ?, 'idle', '{}', ?, ?)""",
        (host_id, json.dumps(resources), now, now),
    )
    conn.commit()


def test_acquire_emits_lease_acquired_event(conn):
    """leases.acquire emits a lease_acquired event."""
    run_id = "r1"
    _mk_run(conn, run_id)
    _mk_crew(conn, "host1")

    # Acquire should succeed and emit event
    now = time.time()
    lease = leases.acquire(conn, run_id, "cpu", "r1/t-1", "host1", now=now)
    conn.commit()

    assert lease is not None

    # Check event was emitted
    events_list = conn.execute(
        """SELECT kind, ticket_id, data_json FROM events
           WHERE kind='lease_acquired' AND run_id=?""",
        (run_id,)
    ).fetchall()

    assert len(events_list) == 1
    kind, ticket_id, data_json = events_list[0]
    assert kind == "lease_acquired"
    assert ticket_id == "r1/t-1"
    data = json.loads(data_json)
    assert data.get("lease_id") == lease.id
    assert data.get("resource_class") == "cpu"


def test_acquire_no_event_when_at_capacity(conn):
    """leases.acquire does NOT emit when it returns None (at capacity)."""
    run_id = "r1"
    _mk_run(conn, run_id)
    _mk_crew(conn, "host1", resources={"cpu": 1})  # Capacity = 1

    now = time.time()
    # First acquire succeeds
    lease1 = leases.acquire(conn, run_id, "cpu", "r1/t-1", "host1", now=now)
    assert lease1 is not None
    conn.commit()

    # Second acquire fails (at capacity)
    lease2 = leases.acquire(conn, run_id, "cpu", "r1/t-2", "host1", now=now)
    assert lease2 is None
    conn.commit()

    # Only one event (from the first acquire)
    events_list = conn.execute(
        """SELECT COUNT(*) FROM events WHERE kind='lease_acquired' AND run_id=?""",
        (run_id,)
    ).fetchone()
    assert events_list[0] == 1


def test_reclaim_expired_emits_lease_reclaimed_event(conn):
    """leases.reclaim_expired emits lease_reclaimed for each reclaimed lease."""
    run_id = "r1"
    _mk_run(conn, run_id)
    _mk_ticket(conn, "r1/t-1", run_id, state="running")
    _mk_crew(conn, "host1")

    # Acquire a lease with short TTL
    now = time.time()
    lease = leases.acquire(conn, run_id, "cpu", "r1/t-1", "host1", now=now, ttl_s=10)
    assert lease is not None
    conn.commit()

    # Clear events to isolate reclaim event
    conn.execute("DELETE FROM events WHERE kind='lease_acquired'")
    conn.commit()

    # Reclaim after expiry
    leases.reclaim_expired(conn, now=now + 20)
    conn.commit()

    # Check event was emitted
    events_list = conn.execute(
        """SELECT kind, ticket_id, data_json FROM events
           WHERE kind='lease_reclaimed' AND run_id=?""",
        (run_id,)
    ).fetchall()

    assert len(events_list) == 1
    kind, ticket_id, data_json = events_list[0]
    assert kind == "lease_reclaimed"
    assert ticket_id == "r1/t-1"
    data = json.loads(data_json)
    assert data.get("lease_id") == lease.id
