"""Tests for engine.leases — resource semaphore and lease lifecycle (§9, §4).

TDD: written FIRST, watched fail, then engine/leases.py implemented minimally
to spec. Covers capacity computation from crew rows, acquire semantics (grant
iff under capacity), release+unpark, wiring into queue (record_result/requeue/
requeue_transport), renew, and reclaim_expired.

Stdlib-only (sqlite3 + json + time). Crew ROWS are inserted directly (Slice 8
populates crew; this slice consumes it). Tests verify the semaphore never
over-issues and expired leases self-heal.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import time
from pathlib import Path

import pytest

from engine.db.migrate import apply_migrations, connect
from engine.models import Result, Ticket


# --- fixtures ------------------------------------------------------------

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


# --- helpers -------------------------------------------------------------

def _mk_run(conn, run_id="r1", state="running"):
    conn.execute(
        """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                             phase, created_at, updated_at)
           VALUES (?, 'stub', 'stub', 'main', '{}', ?, 'work', 0, 0)""",
        (run_id, state),
    )
    conn.commit()
    return run_id


def _mk_ticket(
    conn,
    ticket_id,
    run_id="r1",
    state="queued",
    resource_req="cpu",
    lease_id=None,
):
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority,
                                attempts, available_at, lease_id, tried_hosts,
                                payload_json, created_at, updated_at)
           VALUES (?, ?, 'work', ?, ?, 0, 0, 0, ?, '[]', '{}', 0, 0)""",
        (ticket_id, run_id, state, resource_req, lease_id),
    )
    conn.commit()
    return ticket_id


def _mk_crew(conn, host_id, resources, state="idle"):
    """Insert a crew member with the given resources_json and state.

    resources is a dict like {"cpu": 4, "gpu": 1}.
    """
    conn.execute(
        """INSERT INTO crew (id, site, capabilities, resources_json, state,
                             registered_at)
           VALUES (?, 'stub', '[]', ?, ?, 0)""",
        (host_id, json.dumps(resources), state),
    )
    conn.commit()


def _lease_count(conn, resource_class):
    """Count live (unexpired) leases for a resource class."""
    row = conn.execute(
        "SELECT COUNT(*) FROM leases WHERE resource_class=? AND expires_at > ?",
        (resource_class, time.time()),
    ).fetchone()
    return row[0]


def _capacity(conn, resource_class):
    """Compute class capacity from crew.resources_json (idle|busy only).

    This mirrors the leases.acquire logic to verify it.
    """
    rows = conn.execute(
        "SELECT resources_json FROM crew WHERE state IN ('idle','busy')"
    ).fetchall()
    total = 0
    for (rj,) in rows:
        res = json.loads(rj)
        total += res.get(resource_class, 0)
    return total


# --- test doubles --------------------------------------------------------

class StubPlaybook:
    """Minimal playbook double for queue wiring tests."""
    name = "stub"

    def verify(self, run, ticket, result, site):
        return True  # always pass


class StubSite:
    name = "stub"


# --- TESTS ---------------------------------------------------------------

def test_capacity_from_crew(conn):
    """Capacity = Σ resources_json[class] over idle|busy crew."""
    from engine import leases

    # No crew → capacity 0
    _mk_run(conn)
    cap = _capacity(conn, "cpu")
    assert cap == 0, "no crew → capacity 0"

    # Add 2 idle hosts with cpu:4 each → capacity 8
    _mk_crew(conn, "h1", {"cpu": 4}, state="idle")
    _mk_crew(conn, "h2", {"cpu": 4}, state="idle")
    cap = _capacity(conn, "cpu")
    assert cap == 8, "2 hosts × 4 cpu → capacity 8"

    # A down host does NOT contribute
    _mk_crew(conn, "h3", {"cpu": 4}, state="down")
    cap = _capacity(conn, "cpu")
    assert cap == 8, "down host ignored"

    # A busy host DOES contribute
    conn.execute("UPDATE crew SET state='busy' WHERE id='h1'")
    conn.commit()
    cap = _capacity(conn, "cpu")
    assert cap == 8, "busy host counted"


def test_acquire_under_capacity(conn):
    """acquire grants when live leases < capacity."""
    from engine import leases

    run_id = _mk_run(conn)
    _mk_crew(conn, "h1", {"cpu": 2}, state="idle")  # capacity = 2
    t1 = _mk_ticket(conn, "r1/t-1")
    t2 = _mk_ticket(conn, "r1/t-2")

    now = time.time()
    # First acquire succeeds
    lease1 = leases.acquire(conn, run_id, "cpu", t1, "h1", now=now)
    assert lease1 is not None, "1st acquire granted (1 < 2)"
    assert lease1.resource_class == "cpu"
    assert lease1.ticket_id == t1
    assert lease1.expires_at == now + 1800  # default ttl_s

    # Second acquire succeeds (2 ≤ 2)
    lease2 = leases.acquire(conn, run_id, "cpu", t2, "h1", now=now)
    assert lease2 is not None, "2nd acquire granted (2 <= 2)"

    # Third acquire fails (capacity exhausted)
    t3 = _mk_ticket(conn, "r1/t-3")
    lease3 = leases.acquire(conn, run_id, "cpu", t3, "h1", now=now)
    assert lease3 is None, "3rd acquire denied (at capacity)"


def test_acquire_at_capacity_denies(conn):
    """acquire returns None when at capacity (caller parks)."""
    from engine import leases

    run_id = _mk_run(conn)
    _mk_crew(conn, "h1", {"cpu": 1}, state="idle")  # capacity = 1
    t1 = _mk_ticket(conn, "r1/t-1")
    t2 = _mk_ticket(conn, "r1/t-2")

    now = time.time()
    lease1 = leases.acquire(conn, run_id, "cpu", t1, "h1", now=now)
    assert lease1 is not None, "1st granted"

    lease2 = leases.acquire(conn, run_id, "cpu", t2, "h1", now=now)
    assert lease2 is None, "2nd denied (at capacity)"


def test_release_frees_slot(conn):
    """release frees a lease; a subsequent acquire succeeds."""
    from engine import leases

    run_id = _mk_run(conn)
    _mk_crew(conn, "h1", {"cpu": 1}, state="idle")
    t1 = _mk_ticket(conn, "r1/t-1")
    t2 = _mk_ticket(conn, "r1/t-2")

    now = time.time()
    lease1 = leases.acquire(conn, run_id, "cpu", t1, "h1", now=now)
    assert lease1 is not None

    # At capacity: next acquire fails
    lease2 = leases.acquire(conn, run_id, "cpu", t2, "h1", now=now)
    assert lease2 is None, "at capacity"

    # Release the first lease
    leases.release(conn, lease1.id, now=now)

    # Now the slot is free
    lease2 = leases.acquire(conn, run_id, "cpu", t2, "h1", now=now)
    assert lease2 is not None, "slot freed by release"


def test_release_unparks_ticket(conn):
    """release calls unpark_ready; parked tickets return to queued."""
    from engine import leases, queue

    run_id = _mk_run(conn)
    _mk_crew(conn, "h1", {"cpu": 1}, state="idle")
    t1 = _mk_ticket(conn, "r1/t-1")
    t2_id = _mk_ticket(conn, "r1/t-2", state="parked")  # already parked

    now = time.time()
    lease1 = leases.acquire(conn, run_id, "cpu", t1, "h1", now=now)
    assert lease1 is not None

    # Verify t2 is parked
    state = conn.execute("SELECT state FROM tickets WHERE id=?", (t2_id,)).fetchone()[0]
    assert state == "parked"

    # Release the lease (which calls unpark_ready internally)
    leases.release(conn, lease1.id, now=now)

    # t2 should now be queued
    state = conn.execute("SELECT state FROM tickets WHERE id=?", (t2_id,)).fetchone()[0]
    assert state == "queued", "parked ticket unparked on release"


def test_renew_extends_expiry(conn):
    """renew extends expires_at by ttl_s."""
    from engine import leases

    run_id = _mk_run(conn)
    _mk_crew(conn, "h1", {"cpu": 1}, state="idle")
    t1 = _mk_ticket(conn, "r1/t-1")

    now = time.time()
    lease = leases.acquire(conn, run_id, "cpu", t1, "h1", now=now)
    assert lease is not None
    orig_expires = lease.expires_at

    # Renew 100s later
    now2 = now + 100
    leases.renew(conn, lease.id, now=now2)

    # Check the new expires_at
    row = conn.execute("SELECT expires_at FROM leases WHERE id=?", (lease.id,)).fetchone()
    new_expires = row[0]
    assert new_expires == now2 + 1800, "renew extends expires_at"
    assert new_expires > orig_expires


def test_reclaim_expired_requeues_non_terminal(conn):
    """reclaim_expired frees expired leases and requeues still-non-terminal tickets."""
    from engine import leases

    run_id = _mk_run(conn)
    _mk_crew(conn, "h1", {"cpu": 2}, state="idle")
    t1 = _mk_ticket(conn, "r1/t-1", state="running")
    t2 = _mk_ticket(conn, "r1/t-2", state="done")  # terminal

    now = time.time()
    lease1 = leases.acquire(conn, run_id, "cpu", t1, "h1", now=now)
    lease2 = leases.acquire(conn, run_id, "cpu", t2, "h1", now=now)

    # Update tickets to reference their leases
    conn.execute("UPDATE tickets SET lease_id=? WHERE id=?", (lease1.id, t1))
    conn.execute("UPDATE tickets SET lease_id=? WHERE id=?", (lease2.id, t2))
    conn.commit()

    # Advance time past expiry
    now_future = now + 1801
    leases.reclaim_expired(conn, now=now_future)

    # Both leases freed
    count = conn.execute("SELECT COUNT(*) FROM leases").fetchone()[0]
    assert count == 0, "expired leases freed"

    # t1 (was running) requeued, no penalty
    state1 = conn.execute("SELECT state, attempts FROM tickets WHERE id=?", (t1,)).fetchone()
    assert state1[0] == "queued", "running ticket requeued"
    assert state1[1] == 0, "no attempt penalty"

    # t2 (was done) NOT requeued
    state2 = conn.execute("SELECT state FROM tickets WHERE id=?", (t2,)).fetchone()[0]
    assert state2 == "done", "terminal ticket not requeued"


def test_reclaim_expired_unparks(conn):
    """reclaim_expired calls unpark_ready after freeing slots."""
    from engine import leases

    run_id = _mk_run(conn)
    _mk_crew(conn, "h1", {"cpu": 1}, state="idle")
    t1 = _mk_ticket(conn, "r1/t-1", state="running")
    t2 = _mk_ticket(conn, "r1/t-2", state="parked")

    now = time.time()
    lease1 = leases.acquire(conn, run_id, "cpu", t1, "h1", now=now)
    conn.execute("UPDATE tickets SET lease_id=? WHERE id=?", (lease1.id, t1))
    conn.commit()

    # Advance past expiry
    now_future = now + 1801
    leases.reclaim_expired(conn, now=now_future)

    # t2 should be unparked
    state2 = conn.execute("SELECT state FROM tickets WHERE id=?", (t2,)).fetchone()[0]
    assert state2 == "queued", "parked ticket unparked on reclaim"


def test_wiring_record_result_releases_on_reducing(conn):
    """record_result releases the lease on running→reducing."""
    from engine import leases, queue

    run_id = _mk_run(conn)
    _mk_crew(conn, "h1", {"cpu": 1}, state="idle")
    t1_id = _mk_ticket(conn, "r1/t-1", state="running")

    now = time.time()
    lease = leases.acquire(conn, run_id, "cpu", t1_id, "h1", now=now)
    conn.execute("UPDATE tickets SET lease_id=? WHERE id=?", (lease.id, t1_id))
    conn.commit()

    # Build a ticket handle
    t1 = Ticket(
        id=t1_id, run_id=run_id, phase="work", state="running",
        resource_req="cpu", priority=0, attempts=0, payload={}
    )

    # Record an ok result (→ reducing via verify=True)
    result = Result(
        outcome="ok",
        termination_reason="goal_met",
        result_ref=None,
        error_summary=None,
        started_at=now,
        ended_at=now + 10,
        payload={}
    )

    playbook = StubPlaybook()
    site = StubSite()
    new_state = queue.record_result(conn, t1, "h1", result, now, playbook, site)

    assert new_state == "reducing", "ticket moved to reducing"

    # The lease should be released
    lease_count = conn.execute("SELECT COUNT(*) FROM leases WHERE id=?", (lease.id,)).fetchone()[0]
    assert lease_count == 0, "lease released on running→reducing"


def test_wiring_record_result_releases_on_failed(conn):
    """record_result releases the lease on running→failed."""
    from engine import leases, queue

    run_id = _mk_run(conn)
    _mk_crew(conn, "h1", {"cpu": 1}, state="idle")
    t1_id = _mk_ticket(conn, "r1/t-1", state="running")

    now = time.time()
    lease = leases.acquire(conn, run_id, "cpu", t1_id, "h1", now=now)
    conn.execute("UPDATE tickets SET lease_id=? WHERE id=?", (lease.id, t1_id))
    conn.commit()

    t1 = Ticket(
        id=t1_id, run_id=run_id, phase="work", state="running",
        resource_req="cpu", priority=0, attempts=0, payload={}
    )

    # Driver failed result (→ failed terminal)
    result = Result(
        outcome="driver_failed",
        termination_reason="contract_fail",
        result_ref=None,
        error_summary="bad payload",
        started_at=now,
        ended_at=now + 10,
        payload={}
    )

    playbook = StubPlaybook()
    site = StubSite()
    new_state = queue.record_result(conn, t1, "h1", result, now, playbook, site)

    assert new_state == "failed"

    # Lease released
    lease_count = conn.execute("SELECT COUNT(*) FROM leases WHERE id=?", (lease.id,)).fetchone()[0]
    assert lease_count == 0, "lease released on running→failed"


def test_wiring_record_result_releases_on_infra_requeue(conn):
    """record_result releases the lease on running→queued (infra retry)."""
    from engine import leases, queue

    run_id = _mk_run(conn)
    _mk_crew(conn, "h1", {"cpu": 1}, state="idle")
    t1_id = _mk_ticket(conn, "r1/t-1", state="running")

    now = time.time()
    lease = leases.acquire(conn, run_id, "cpu", t1_id, "h1", now=now)
    conn.execute("UPDATE tickets SET lease_id=? WHERE id=?", (lease.id, t1_id))
    conn.commit()

    t1 = Ticket(
        id=t1_id, run_id=run_id, phase="work", state="running",
        resource_req="cpu", priority=0, attempts=0, payload={}
    )

    # Infra failed result (→ queued with attempts++)
    result = Result(
        outcome="infra_failed",
        termination_reason="transport_error",
        result_ref=None,
        error_summary="ssh timeout",
        started_at=now,
        ended_at=now + 10,
        payload={}
    )

    playbook = StubPlaybook()
    site = StubSite()
    new_state = queue.record_result(conn, t1, "h1", result, now, playbook, site)

    assert new_state == "queued", "infra retry → queued"

    # Lease released
    lease_count = conn.execute("SELECT COUNT(*) FROM leases WHERE id=?", (lease.id,)).fetchone()[0]
    assert lease_count == 0, "lease released on running→queued (infra)"


def test_wiring_requeue_releases_lease(conn):
    """requeue() releases the ticket's lease."""
    from engine import leases, queue

    run_id = _mk_run(conn)
    _mk_crew(conn, "h1", {"cpu": 1}, state="idle")
    t1_id = _mk_ticket(conn, "r1/t-1", state="running")

    now = time.time()
    lease = leases.acquire(conn, run_id, "cpu", t1_id, "h1", now=now)
    conn.execute("UPDATE tickets SET lease_id=? WHERE id=?", (lease.id, t1_id))
    conn.commit()

    t1 = Ticket(
        id=t1_id, run_id=run_id, phase="work", state="running",
        resource_req="cpu", priority=0, attempts=0, payload={}
    )

    queue.requeue(conn, t1, now=now)

    # Lease released
    lease_count = conn.execute("SELECT COUNT(*) FROM leases WHERE id=?", (lease.id,)).fetchone()[0]
    assert lease_count == 0, "requeue releases lease"


def test_wiring_requeue_transport_releases_lease(conn):
    """requeue_transport() releases the ticket's lease."""
    from engine import leases, queue

    run_id = _mk_run(conn)
    _mk_crew(conn, "h1", {"cpu": 1}, state="idle")
    t1_id = _mk_ticket(conn, "r1/t-1", state="running")

    now = time.time()
    lease = leases.acquire(conn, run_id, "cpu", t1_id, "h1", now=now)
    conn.execute("UPDATE tickets SET lease_id=? WHERE id=?", (lease.id, t1_id))
    conn.commit()

    t1 = Ticket(
        id=t1_id, run_id=run_id, phase="work", state="running",
        resource_req="cpu", priority=0, attempts=0, payload={}
    )

    queue.requeue_transport(conn, t1, now=now)

    # Lease released
    lease_count = conn.execute("SELECT COUNT(*) FROM leases WHERE id=?", (lease.id,)).fetchone()[0]
    assert lease_count == 0, "requeue_transport releases lease"
