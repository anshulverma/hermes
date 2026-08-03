"""Tests for engine.queue — the ticket + run state machine.

TDD: written FIRST, watched fail, then engine/queue.py implemented minimally.
Table-driven over transitions, plus a real-threads concurrency test for claim
atomicity, run-state edges, and reduction resolution.

No lease logic is exercised here. These tests only touch runs/tickets/attempts/
findings/reductions/events.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
from pathlib import Path

import pytest

from engine.db.migrate import apply_migrations, connect
from engine.models import Result, Reduction, Run, Ticket


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


# --- test doubles --------------------------------------------------------

class StubSite:
    """Minimal site double; verify/seed in StubPlaybook ignore it."""
    name = "stub"


class StubPlaybook:
    """Configurable playbook double.

    verify_return controls playbook.verify; seed_tickets returns preset tickets.
    """

    name = "stub"
    phases = ["work", "reduce"]

    def __init__(self, verify_return=True, seed_tickets=None):
        self._verify_return = verify_return
        self._seed_tickets = seed_tickets or []

    def seed(self, run: Run, site) -> list[Ticket]:
        return list(self._seed_tickets)

    def verify(self, run: Run, ticket: Ticket, result: Result, site) -> bool:
        return self._verify_return


# --- helpers -------------------------------------------------------------

def _mk_run(conn, run_id="r1", state="running", config=None, phase="work"):
    conn.execute(
        """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                             phase, created_at, updated_at)
           VALUES (?, 'stub', 'stub', 'main', ?, ?, ?, 0, 0)""",
        (run_id, json.dumps(config or {}), state, phase),
    )
    conn.commit()
    return run_id


def _mk_ticket(
    conn,
    ticket_id,
    run_id="r1",
    state="queued",
    resource_req="cpu",
    priority=0.0,
    attempts=0,
    available_at=0.0,
    worker_host=None,
    tried_hosts=None,
    reduction_id=None,
    payload=None,
    phase="work",
):
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority,
                                attempts, available_at, worker_host, tried_hosts,
                                reduction_id, payload_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)""",
        (
            ticket_id, run_id, phase, state, resource_req, priority, attempts,
            available_at, worker_host, json.dumps(tried_hosts or []),
            reduction_id, json.dumps(payload or {}),
        ),
    )
    conn.commit()
    return Ticket(
        id=ticket_id, run_id=run_id, phase=phase, state=state,
        resource_req=resource_req, priority=priority, attempts=attempts,
        payload=payload or {},
    )


def _ticket_row(conn, ticket_id):
    cur = conn.execute(
        """SELECT state, attempts, available_at, worker_host, tried_hosts,
                  reduction_id FROM tickets WHERE id=?""",
        (ticket_id,),
    )
    r = cur.fetchone()
    return {
        "state": r[0], "attempts": r[1], "available_at": r[2],
        "worker_host": r[3], "tried_hosts": json.loads(r[4]),
        "reduction_id": r[5],
    }


def _run_state(conn, run_id):
    return conn.execute("SELECT state FROM runs WHERE id=?", (run_id,)).fetchone()[0]


def _kinds(conn):
    return [
        r[0] for r in conn.execute("SELECT kind FROM events ORDER BY id").fetchall()
    ]


def _ok_result(payload=None):
    return Result(
        outcome="ok", termination_reason="goal_met", result_ref="ref://x",
        error_summary=None, started_at=1.0, ended_at=2.0,
        payload=payload if payload is not None else {"cluster": "parser"},
        evidence_ref="ev://x",
    )


def _fail_result(outcome, reason):
    return Result(
        outcome=outcome, termination_reason=reason, result_ref=None,
        error_summary="boom", started_at=1.0, ended_at=2.0, payload={},
        evidence_ref=None,
    )


# --- seed_tickets --------------------------------------------------------

def test_seed_tickets_inserts_queued_rows(conn):
    from engine import queue

    _mk_run(conn)
    tickets = [
        Ticket(id="r1/t-0", run_id="r1", phase="work", state="queued",
               resource_req="cpu", priority=1.0, attempts=0,
               payload={"issue": "A"}),
        Ticket(id="r1/t-1", run_id="r1", phase="work", state="queued",
               resource_req="cpu", priority=0.0, attempts=0,
               payload={"issue": "B"}),
    ]
    pb = StubPlaybook(seed_tickets=tickets)
    run = Run(id="r1", playbook="stub", site="stub", base_ref="main",
              config={}, phase="work", reductions=[])

    queue.seed_tickets(conn, run, pb, StubSite())

    rows = conn.execute(
        "SELECT id, state, payload_json FROM tickets ORDER BY id"
    ).fetchall()
    assert [r[0] for r in rows] == ["r1/t-0", "r1/t-1"]
    assert all(r[1] == "queued" for r in rows)
    assert json.loads(rows[0][2]) == {"issue": "A"}


# --- claim_ticket --------------------------------------------------------

def test_claim_returns_highest_priority_running_run_only(conn):
    from engine import queue

    _mk_run(conn, "r1", state="running")
    _mk_run(conn, "r2", state="paused")
    # p0 is highest priority (lowest number first).
    _mk_ticket(conn, "r1/t-hi", run_id="r1", priority=0.0)  # p0 = highest
    _mk_ticket(conn, "r1/t-lo", run_id="r1", priority=5.0)  # higher number = lower priority
    _mk_ticket(conn, "r2/t-x", run_id="r2", priority=0.0)  # paused run: ignored

    t = queue.claim_ticket(conn, "host-A", {"cpu"}, now=100.0)

    assert t is not None
    assert t.id == "r1/t-hi"  # p0 is highest priority among running-run queued tickets
    row = _ticket_row(conn, "r1/t-hi")
    assert row["state"] == "dispatched"
    assert row["worker_host"] == "host-A"
    assert row["tried_hosts"] == ["host-A"]
    assert "ticket_claimed" in _kinds(conn)


def test_claim_respects_resource_req_and_available_at(conn):
    from engine import queue

    _mk_run(conn, "r1")
    _mk_ticket(conn, "r1/gpu", resource_req="gpu", priority=9.0)
    _mk_ticket(conn, "r1/future", resource_req="cpu", priority=9.0,
               available_at=1000.0)
    _mk_ticket(conn, "r1/ready", resource_req="cpu", priority=1.0,
               available_at=0.0)

    # host only serves cpu; only r1/ready is available now
    t = queue.claim_ticket(conn, "host-A", {"cpu"}, now=100.0)
    assert t.id == "r1/ready"


def test_claim_returns_none_when_nothing_claimable(conn):
    from engine import queue

    _mk_run(conn, "r1")
    _mk_ticket(conn, "r1/gpu", resource_req="gpu")
    assert queue.claim_ticket(conn, "host-A", {"cpu"}, now=100.0) is None
    assert queue.claim_ticket(conn, "host-A", set(), now=100.0) is None


def test_tried_hosts_accumulate_across_claims(conn):
    from engine import queue

    _mk_run(conn, "r1")
    _mk_ticket(conn, "r1/t-0")

    queue.claim_ticket(conn, "host-A", {"cpu"}, now=1.0)
    # simulate worker start (dispatched->running) then a transport requeue
    conn.execute("UPDATE tickets SET state='running' WHERE id='r1/t-0'")
    conn.commit()
    queue.requeue_transport(conn, _mk_ticket_ref("r1/t-0", "r1"), now=2.0)
    assert _ticket_row(conn, "r1/t-0")["tried_hosts"] == ["host-A"]

    queue.claim_ticket(conn, "host-B", {"cpu"}, now=3.0)
    assert _ticket_row(conn, "r1/t-0")["tried_hosts"] == ["host-A", "host-B"]


def _mk_ticket_ref(ticket_id, run_id):
    """A bare Ticket handle (queue funcs re-read authoritative state from db)."""
    return Ticket(id=ticket_id, run_id=run_id, phase="work", state="running",
                  resource_req="cpu", priority=0.0, attempts=0, payload={})


def test_claim_atomic_under_real_threads(db_path):
    """N threads claiming concurrently on a real WAL db never double-claim."""
    from engine import queue

    apply_migrations(db_path)
    setup = connect(db_path)
    _mk_run(setup, "r1")
    n_tickets = 60
    for i in range(n_tickets):
        _mk_ticket(setup, f"r1/t-{i}", priority=float(i))
    setup.close()

    claimed: list[str] = []
    lock = threading.Lock()
    barrier = threading.Barrier(8)

    def worker(name):
        c = connect(db_path)
        barrier.wait()
        while True:
            t = queue.claim_ticket(c, name, {"cpu"}, now=1000.0)
            if t is None:
                break
            with lock:
                claimed.append(t.id)
        c.close()

    threads = [threading.Thread(target=worker, args=(f"h{i}",)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Every ticket claimed exactly once (no double-claim, none lost)
    assert len(claimed) == n_tickets
    assert len(set(claimed)) == n_tickets


# --- record_result: ticket state machine (table-driven) ------------------

def test_record_result_ok_verify_true_to_reducing(conn):
    from engine import queue

    _mk_run(conn, "r1")
    t = _mk_ticket(conn, "r1/t-0", state="running")
    pb = StubPlaybook(verify_return=True)

    queue.record_result(conn, t, "host-A", _ok_result(), 100.0, pb, StubSite())

    assert _ticket_row(conn, "r1/t-0")["state"] == "reducing"
    assert "result_recorded" in _kinds(conn)


def test_record_result_ok_verify_false_to_needs_human(conn):
    from engine import queue

    _mk_run(conn, "r1")
    t = _mk_ticket(conn, "r1/t-0", state="running")
    pb = StubPlaybook(verify_return=False)

    queue.record_result(conn, t, "host-A", _ok_result(), 100.0, pb, StubSite())

    assert _ticket_row(conn, "r1/t-0")["state"] == "needs_human"
    kinds = _kinds(conn)
    assert "needs_human" in kinds
    assert "attention" in kinds


def test_record_result_driver_failed_terminal_no_retry(conn):
    from engine import queue

    _mk_run(conn, "r1")
    t = _mk_ticket(conn, "r1/t-0", state="running", attempts=0)
    pb = StubPlaybook()

    queue.record_result(
        conn, t, "host-A", _fail_result("driver_failed", "driver_error"),
        100.0, pb, StubSite(),
    )

    row = _ticket_row(conn, "r1/t-0")
    assert row["state"] == "failed"
    assert row["attempts"] == 0  # no retry penalty on driver failures
    assert "ticket_failed" in _kinds(conn)


@pytest.mark.parametrize(
    "start_attempts,expected_attempts,expected_backoff",
    [
        (0, 1, 30.0),   # 30 * 2**0
        (1, 2, 60.0),   # 30 * 2**1
        (2, 3, 120.0),  # 30 * 2**2
    ],
)
def test_record_result_infra_failed_retries_with_backoff(
    conn, start_attempts, expected_attempts, expected_backoff
):
    from engine import queue

    _mk_run(conn, "r1")
    t = _mk_ticket(conn, "r1/t-0", state="running", attempts=start_attempts)
    pb = StubPlaybook()

    queue.record_result(
        conn, t, "host-A", _fail_result("infra_failed", "transport_error"),
        100.0, pb, StubSite(),
    )

    row = _ticket_row(conn, "r1/t-0")
    assert row["state"] == "queued"
    assert row["attempts"] == expected_attempts
    assert row["available_at"] == 100.0 + expected_backoff
    assert "ticket_requeued" in _kinds(conn)


def test_record_result_infra_failed_caps_at_3_then_failed(conn):
    from engine import queue

    _mk_run(conn, "r1")
    t = _mk_ticket(conn, "r1/t-0", state="running", attempts=3)
    pb = StubPlaybook()

    queue.record_result(
        conn, t, "host-A", _fail_result("infra_failed", "transport_error"),
        100.0, pb, StubSite(),
    )

    row = _ticket_row(conn, "r1/t-0")
    assert row["state"] == "failed"
    assert row["attempts"] == 3  # unchanged; the 4th failure is terminal
    assert "ticket_failed" in _kinds(conn)


def test_record_result_appends_attempts_audit_row(conn):
    from engine import queue

    _mk_run(conn, "r1")
    t = _mk_ticket(conn, "r1/t-0", state="running")
    pb = StubPlaybook()

    queue.record_result(conn, t, "host-A", _ok_result(), 100.0, pb, StubSite())

    row = conn.execute(
        """SELECT ticket_id, host, outcome, termination_reason, started_at,
                  ended_at FROM attempts WHERE ticket_id='r1/t-0'"""
    ).fetchone()
    assert row is not None
    assert row[0] == "r1/t-0"
    assert row[1] == "host-A"
    assert row[2] == "ok"
    assert row[3] == "goal_met"
    assert row[4] == 1.0 and row[5] == 2.0


def test_record_result_inserts_finding_with_run_and_ticket_id(conn):
    from engine import queue

    _mk_run(conn, "r1")
    t = _mk_ticket(conn, "r1/t-0", state="running")
    pb = StubPlaybook(verify_return=True)

    queue.record_result(
        conn, t, "host-A", _ok_result(payload={"cluster": "parser", "x": 1}),
        100.0, pb, StubSite(),
    )

    row = conn.execute(
        "SELECT run_id, ticket_id, json FROM findings WHERE ticket_id='r1/t-0'"
    ).fetchone()
    assert row is not None
    assert row[0] == "r1"
    assert row[1] == "r1/t-0"
    assert json.loads(row[2]) == {"cluster": "parser", "x": 1}


def test_record_result_is_atomic_single_commit(conn):
    """A failure mid-record_result rolls back transition+attempts+finding+events."""
    from engine import queue

    _mk_run(conn, "r1")
    t = _mk_ticket(conn, "r1/t-0", state="running")

    class BoomPlaybook(StubPlaybook):
        def verify(self, run, ticket, result, site):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        queue.record_result(
            conn, t, "host-A", _ok_result(), 100.0, BoomPlaybook(), StubSite()
        )

    # nothing persisted: ticket still running, no attempts/findings/events rows
    assert _ticket_row(conn, "r1/t-0")["state"] == "running"
    assert conn.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM findings").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM events").fetchone()[0] == 0


# --- requeue / requeue_transport -----------------------------------------

def test_requeue_penalty_increments_attempts_and_backs_off(conn):
    from engine import queue

    _mk_run(conn, "r1")
    _mk_ticket(conn, "r1/t-0", state="running", attempts=1, worker_host="host-A",
               tried_hosts=["host-A"])

    queue.requeue(conn, _mk_ticket_ref("r1/t-0", "r1"), now=100.0)

    row = _ticket_row(conn, "r1/t-0")
    assert row["state"] == "queued"
    assert row["attempts"] == 2  # penalty
    assert row["available_at"] == 100.0 + 60.0  # 30 * 2**1
    assert row["worker_host"] is None
    assert row["tried_hosts"] == ["host-A"]  # preserved
    assert "ticket_requeued" in _kinds(conn)


def test_requeue_transport_no_penalty(conn):
    from engine import queue

    _mk_run(conn, "r1")
    _mk_ticket(conn, "r1/t-0", state="running", attempts=2, worker_host="host-A",
               tried_hosts=["host-A"])

    queue.requeue_transport(conn, _mk_ticket_ref("r1/t-0", "r1"), now=100.0)

    row = _ticket_row(conn, "r1/t-0")
    assert row["state"] == "queued"
    assert row["attempts"] == 2  # NO penalty
    assert row["worker_host"] is None
    assert row["tried_hosts"] == ["host-A"]  # preserved for a fresh claim elsewhere
    assert "ticket_requeued" in _kinds(conn)


# --- park_ticket ---------------------------------------------------------

def test_park_ticket_reverts_dispatched(conn):
    from engine import queue

    _mk_run(conn, "r1")
    _mk_ticket(conn, "r1/t-0", state="dispatched", attempts=2,
               worker_host="host-A", tried_hosts=["host-A"])

    queue.park_ticket(conn, _mk_ticket_ref("r1/t-0", "r1"), now=100.0)

    row = _ticket_row(conn, "r1/t-0")
    assert row["state"] == "parked"
    assert row["worker_host"] is None
    assert row["tried_hosts"] == []  # just-appended host removed
    assert row["attempts"] == 2  # unchanged
    assert "ticket_parked" in _kinds(conn)


# --- set_run_state: run state machine ------------------------------------

@pytest.mark.parametrize(
    "start,target,event",
    [
        ("running", "paused", "run_paused"),
        ("paused", "running", "run_resumed"),
        ("running", "stopped", "run_stopped"),
        ("paused", "stopped", "run_stopped"),
        ("running", "done", "run_done"),
        ("running", "failed", "run_failed"),
    ],
)
def test_set_run_state_legal_edges(conn, start, target, event):
    from engine import queue

    _mk_run(conn, "r1", state=start)
    queue.set_run_state(conn, "r1", target, now=100.0)
    assert _run_state(conn, "r1") == target
    assert event in _kinds(conn)


@pytest.mark.parametrize(
    "start,target",
    [
        ("stopped", "running"),   # resume a terminal run
        ("done", "running"),
        ("failed", "running"),
        ("done", "paused"),
        ("paused", "done"),       # done only from running
        ("running", "running"),   # no-op is illegal
    ],
)
def test_set_run_state_illegal_edges_raise(conn, start, target):
    from engine import queue

    _mk_run(conn, "r1", state=start)
    with pytest.raises(ValueError):
        queue.set_run_state(conn, "r1", target, now=100.0)
    assert _run_state(conn, "r1") == start  # unchanged


def test_set_run_state_unknown_run_raises(conn):
    from engine import queue

    with pytest.raises(ValueError):
        queue.set_run_state(conn, "nope", "paused", now=100.0)


# --- reduction resolution ------------------------------------------------

def _mk_reduction(conn, run_id="r1", kind="cluster", json_doc=None,
                  review_state="pending"):
    cur = conn.execute(
        """INSERT INTO reductions (run_id, kind, json, review_state,
                                   created_at, updated_at)
           VALUES (?, ?, ?, ?, 0, 0)""",
        (run_id, kind, json.dumps(json_doc or {}), review_state),
    )
    conn.commit()
    return cur.lastrowid


def test_accept_reduction_settles_needs_human_to_done(conn):
    from engine import queue

    _mk_run(conn, "r1")
    rid = _mk_reduction(conn)
    _mk_ticket(conn, "r1/t-0", state="needs_human", reduction_id=rid)
    _mk_ticket(conn, "r1/t-1", state="needs_human", reduction_id=rid)
    _mk_ticket(conn, "r1/other", state="reducing", reduction_id=None)

    queue.accept_reduction(conn, rid, now=100.0)

    assert conn.execute(
        "SELECT review_state FROM reductions WHERE id=?", (rid,)
    ).fetchone()[0] == "accepted"
    assert _ticket_row(conn, "r1/t-0")["state"] == "done"
    assert _ticket_row(conn, "r1/t-1")["state"] == "done"
    assert _ticket_row(conn, "r1/other")["state"] == "reducing"  # untouched
    assert "reduction_accepted" in _kinds(conn)


def test_reject_reduction_settles_needs_human_to_failed(conn):
    from engine import queue

    _mk_run(conn, "r1")
    rid = _mk_reduction(conn)
    _mk_ticket(conn, "r1/t-0", state="needs_human", reduction_id=rid)

    queue.reject_reduction(conn, rid, now=100.0)

    assert conn.execute(
        "SELECT review_state FROM reductions WHERE id=?", (rid,)
    ).fetchone()[0] == "rejected"
    assert _ticket_row(conn, "r1/t-0")["state"] == "failed"
    assert "reduction_rejected" in _kinds(conn)


@pytest.mark.parametrize("review_state", ["accepted", "rejected", "superseded"])
def test_resolve_non_pending_reduction_raises(conn, review_state):
    from engine import queue

    _mk_run(conn, "r1")
    rid = _mk_reduction(conn, review_state=review_state)

    with pytest.raises(ValueError):
        queue.accept_reduction(conn, rid, now=100.0)
    with pytest.raises(ValueError):
        queue.reject_reduction(conn, rid, now=100.0)


def test_requeue_needs_human_back_to_queued_no_penalty(conn):
    from engine import queue

    _mk_run(conn, "r1")
    _mk_ticket(conn, "r1/t-0", state="needs_human", attempts=2,
               worker_host="host-A", reduction_id=None)

    queue.requeue_needs_human(conn, "r1/t-0", now=100.0)

    row = _ticket_row(conn, "r1/t-0")
    assert row["state"] == "queued"
    assert row["attempts"] == 2  # UNCHANGED
    assert "ticket_requeued" in _kinds(conn)


def test_requeue_needs_human_rejects_non_needs_human(conn):
    from engine import queue

    _mk_run(conn, "r1")
    _mk_ticket(conn, "r1/t-0", state="reducing")
    with pytest.raises(ValueError):
        queue.requeue_needs_human(conn, "r1/t-0", now=100.0)


# --- abandon_ticket / retry_ticket / set_ticket_priority -----------------

def test_abandon_ticket_non_terminal_to_failed(conn):
    from engine import queue

    _mk_run(conn, "r1")
    for state in ["queued", "dispatched", "running", "reducing", "parked", "needs_human"]:
        tid = f"r1/t-{state}"
        _mk_ticket(conn, tid, state=state, worker_host="host-A")
        queue.abandon_ticket(conn, tid, now=100.0)
        row = _ticket_row(conn, tid)
        assert row["state"] == "failed"
        assert row["worker_host"] is None

    kinds = _kinds(conn)
    assert kinds.count("ticket_abandoned") == 6


def test_abandon_ticket_releases_lease(conn):
    from engine import queue
    from engine import leases

    _mk_run(conn, "r1")
    _mk_ticket(conn, "r1/t-0", state="running")

    # Add crew capacity for cpu
    conn.execute(
        """INSERT INTO crew (id, site, state, capabilities, resources_json, last_heartbeat, registered_at)
           VALUES ('host-A', 'stub', 'idle', '[]', '{"cpu": 1}', 0, 0)"""
    )
    conn.commit()

    # Acquire a lease for the ticket
    lease = leases.acquire(conn, run_id="r1", resource_class="cpu", ticket_id="r1/t-0", host="host-A", now=100.0)
    assert lease is not None
    conn.execute("UPDATE tickets SET lease_id=? WHERE id=?", (lease.id, "r1/t-0"))
    conn.commit()

    # Abandon should release the lease
    queue.abandon_ticket(conn, "r1/t-0", now=200.0)

    # Verify lease no longer exists
    lease_row = conn.execute("SELECT id FROM leases WHERE id=?", (lease.id,)).fetchone()
    assert lease_row is None


def test_abandon_ticket_raises_on_terminal(conn):
    from engine import queue

    _mk_run(conn, "r1")
    _mk_ticket(conn, "r1/t-done", state="done")
    _mk_ticket(conn, "r1/t-failed", state="failed")

    with pytest.raises(ValueError):
        queue.abandon_ticket(conn, "r1/t-done", now=100.0)

    with pytest.raises(ValueError):
        queue.abandon_ticket(conn, "r1/t-failed", now=100.0)


def test_abandon_ticket_raises_on_unknown(conn):
    from engine import queue

    _mk_run(conn, "r1")
    with pytest.raises(ValueError):
        queue.abandon_ticket(conn, "r1/t-unknown", now=100.0)


def test_retry_ticket_failed_to_queued(conn):
    from engine import queue

    _mk_run(conn, "r1")
    # Seed a ticket that reached 'failed' carrying a reduction link and a stale
    # lease_id, so the retry genuinely exercises the clearing (not a no-op).
    conn.execute(
        """INSERT INTO reductions (run_id, phase, kind, review_state, json, created_at, updated_at)
           VALUES ('r1', 'work', 'cluster', 'rejected', '{}', 0, 0)"""
    )
    rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    _mk_ticket(conn, "r1/t-0", state="failed", attempts=3, worker_host="host-A", reduction_id=rid)
    conn.execute("UPDATE tickets SET lease_id='stale-lease' WHERE id='r1/t-0'")
    conn.commit()

    queue.retry_ticket(conn, "r1/t-0", now=100.0)

    row = _ticket_row(conn, "r1/t-0")
    assert row["state"] == "queued"
    assert row["attempts"] == 3  # UNCHANGED
    assert row["worker_host"] is None
    assert row["reduction_id"] is None  # cleared from 42
    lease_id = conn.execute("SELECT lease_id FROM tickets WHERE id='r1/t-0'").fetchone()[0]
    assert lease_id is None  # stale lease cleared
    assert "ticket_requeued" in _kinds(conn)


def test_retry_ticket_raises_on_non_failed(conn):
    from engine import queue

    _mk_run(conn, "r1")
    _mk_ticket(conn, "r1/t-0", state="queued")

    with pytest.raises(ValueError):
        queue.retry_ticket(conn, "r1/t-0", now=100.0)


def test_retry_ticket_raises_on_unknown(conn):
    from engine import queue

    _mk_run(conn, "r1")
    with pytest.raises(ValueError):
        queue.retry_ticket(conn, "r1/t-unknown", now=100.0)


# --- never strand a ticket under a run that can no longer dispatch ---------
#
# claim_ticket only selects tickets whose run is 'running'. Moving a ticket back
# to 'queued' under a terminal run would make it permanently unclaimable.

@pytest.mark.parametrize("run_state", ["done", "stopped", "failed"])
def test_retry_ticket_raises_when_run_terminal(conn, run_state):
    from engine import queue

    _mk_run(conn, "r1", state=run_state)
    _mk_ticket(conn, "r1/t-0", state="failed", attempts=1)

    with pytest.raises(ValueError):
        queue.retry_ticket(conn, "r1/t-0", now=100.0)

    assert _ticket_row(conn, "r1/t-0")["state"] == "failed"  # unchanged


@pytest.mark.parametrize("run_state", ["done", "stopped", "failed"])
def test_requeue_needs_human_raises_when_run_terminal(conn, run_state):
    from engine import queue

    _mk_run(conn, "r1", state=run_state)
    _mk_ticket(conn, "r1/t-0", state="needs_human")

    with pytest.raises(ValueError):
        queue.requeue_needs_human(conn, "r1/t-0", now=100.0)

    assert _ticket_row(conn, "r1/t-0")["state"] == "needs_human"  # unchanged


def test_retry_ticket_allowed_when_run_paused(conn):
    """A paused run is resumable, so requeueing is legitimate."""
    from engine import queue

    _mk_run(conn, "r1", state="paused")
    _mk_ticket(conn, "r1/t-0", state="failed", attempts=1)

    queue.retry_ticket(conn, "r1/t-0", now=100.0)

    assert _ticket_row(conn, "r1/t-0")["state"] == "queued"


def test_abandon_ticket_allowed_when_run_terminal(conn):
    """Abandon stays available so an operator can clear a stranded ticket."""
    from engine import queue

    _mk_run(conn, "r1", state="done")
    _mk_ticket(conn, "r1/t-0", state="queued")

    queue.abandon_ticket(conn, "r1/t-0", now=100.0)

    assert _ticket_row(conn, "r1/t-0")["state"] == "failed"


def test_set_ticket_priority_updates_priority_and_emits(conn):
    from engine import queue

    _mk_run(conn, "r1")
    _mk_ticket(conn, "r1/t-0", state="queued", priority=5.0)

    queue.set_ticket_priority(conn, "r1/t-0", priority=10.0, now=100.0)

    new_priority = conn.execute("SELECT priority FROM tickets WHERE id=?", ("r1/t-0",)).fetchone()[0]
    assert new_priority == 10.0
    assert "ticket_reprioritized" in _kinds(conn)


def test_set_ticket_priority_raises_on_terminal(conn):
    from engine import queue

    _mk_run(conn, "r1")
    _mk_ticket(conn, "r1/t-done", state="done")
    _mk_ticket(conn, "r1/t-failed", state="failed")

    with pytest.raises(ValueError):
        queue.set_ticket_priority(conn, "r1/t-done", priority=10.0, now=100.0)

    with pytest.raises(ValueError):
        queue.set_ticket_priority(conn, "r1/t-failed", priority=10.0, now=100.0)


def test_set_ticket_priority_raises_on_unknown(conn):
    from engine import queue

    _mk_run(conn, "r1")
    with pytest.raises(ValueError):
        queue.set_ticket_priority(conn, "r1/t-unknown", priority=10.0, now=100.0)


# --- master-side reduce/advance writers ----------------------------------

def _mk_finding(conn, run_id, ticket_id, kind="result", json_doc=None):
    conn.execute(
        """INSERT INTO findings (run_id, ticket_id, kind, json, created_at)
           VALUES (?, ?, ?, ?, 0)""",
        (run_id, ticket_id, kind, json.dumps(json_doc or {})),
    )
    conn.commit()


def test_load_findings_scopes_by_phase(conn):
    from engine import queue

    _mk_run(conn, "r1", phase="work")
    _mk_ticket(conn, "r1/t-0", phase="work", state="reducing")
    _mk_ticket(conn, "r1/t-1", phase="work", state="reducing")
    _mk_ticket(conn, "r1/r-0", phase="reduce", state="reducing")
    _mk_finding(conn, "r1", "r1/t-0", json_doc={"cluster": "parser"})
    _mk_finding(conn, "r1", "r1/t-1", json_doc={"cluster": "io"})
    _mk_finding(conn, "r1", "r1/r-0", json_doc={"cluster": "other"})

    findings = queue.load_findings(conn, "r1", "work")

    assert {f.ticket_id for f in findings} == {"r1/t-0", "r1/t-1"}
    assert all(f.run_id == "r1" for f in findings)
    by_id = {f.ticket_id: f.json for f in findings}
    assert by_id["r1/t-0"] == {"cluster": "parser"}


def test_record_reduction_inserts_row_and_routes_needs_human(conn):
    from engine import queue

    _mk_run(conn, "r1", phase="work")
    _mk_ticket(conn, "r1/t-0", phase="work", state="reducing")
    _mk_ticket(conn, "r1/t-1", phase="work", state="reducing")
    red = Reduction(
        kind="cluster",
        json={"clusters": {"parser": ["r1/t-0"]},
              "needs_human_ticket_ids": ["r1/t-0"]},
    )

    rid = queue.record_reduction(conn, "r1", "work", red, now=100.0)

    row = conn.execute(
        "SELECT run_id, phase, kind, review_state FROM reductions WHERE id=?",
        (rid,),
    ).fetchone()
    assert row == ("r1", "work", "cluster", "pending")

    # Flagged ticket routed reducing -> needs_human with reduction_id stamped.
    t0 = _ticket_row(conn, "r1/t-0")
    assert t0["state"] == "needs_human"
    assert t0["reduction_id"] == rid
    # Un-flagged ticket stays reducing (finish_phase_reductions handles it).
    assert _ticket_row(conn, "r1/t-1")["state"] == "reducing"

    kinds = _kinds(conn)
    assert "reduction_created" in kinds
    assert "needs_human" in kinds
    assert "attention" in kinds


def test_record_reduction_without_flags_only_creates_row(conn):
    from engine import queue

    _mk_run(conn, "r1", phase="work")
    _mk_ticket(conn, "r1/t-0", phase="work", state="reducing")
    red = Reduction(kind="cluster", json={"clusters": {"parser": ["r1/t-0"]}})

    rid = queue.record_reduction(conn, "r1", "work", red, now=100.0)

    assert _ticket_row(conn, "r1/t-0")["state"] == "reducing"
    kinds = _kinds(conn)
    assert "reduction_created" in kinds
    assert "needs_human" not in kinds
    assert conn.execute(
        "SELECT phase FROM reductions WHERE id=?", (rid,)
    ).fetchone()[0] == "work"


def test_finish_phase_reductions_settles_remaining_reducing_to_done(conn):
    from engine import queue

    _mk_run(conn, "r1", phase="work")
    _mk_ticket(conn, "r1/t-0", phase="work", state="needs_human")  # flagged earlier
    _mk_ticket(conn, "r1/t-1", phase="work", state="reducing")
    _mk_ticket(conn, "r1/t-2", phase="work", state="reducing")
    _mk_ticket(conn, "r1/r-0", phase="reduce", state="reducing")  # other phase

    queue.finish_phase_reductions(conn, "r1", "work", now=100.0)

    assert _ticket_row(conn, "r1/t-0")["state"] == "needs_human"  # untouched
    assert _ticket_row(conn, "r1/t-1")["state"] == "done"
    assert _ticket_row(conn, "r1/t-2")["state"] == "done"
    assert _ticket_row(conn, "r1/r-0")["state"] == "reducing"  # other phase untouched


def test_set_run_phase_is_sole_phase_writer_and_emits(conn):
    from engine import queue

    _mk_run(conn, "r1", phase="work")

    queue.set_run_phase(conn, "r1", "reduce", now=100.0)

    assert conn.execute(
        "SELECT phase FROM runs WHERE id=?", ("r1",)
    ).fetchone()[0] == "reduce"
    assert "phase_advanced" in _kinds(conn)


def test_phase_ticket_counts_by_state(conn):
    from engine import queue

    _mk_run(conn, "r1", phase="work")
    _mk_ticket(conn, "r1/t-0", phase="work", state="reducing")
    _mk_ticket(conn, "r1/t-1", phase="work", state="reducing")
    _mk_ticket(conn, "r1/t-2", phase="work", state="done")
    _mk_ticket(conn, "r1/t-3", phase="work", state="failed")
    _mk_ticket(conn, "r1/r-0", phase="reduce", state="queued")  # other phase

    counts = queue.phase_ticket_counts(conn, "r1", "work")

    assert counts == {"reducing": 2, "done": 1, "failed": 1}


def test_record_reduction_producer_for_accept_reduction(conn):
    """End-to-end: record_reduction produces a pending reduction linked to a
    needs_human ticket that accept_reduction then settles to done (accept/reject
    are no longer dead code)."""
    from engine import queue

    _mk_run(conn, "r1", phase="work")
    _mk_ticket(conn, "r1/t-0", phase="work", state="reducing")
    red = Reduction(
        kind="cluster",
        json={"needs_human_ticket_ids": ["r1/t-0"]},
    )

    rid = queue.record_reduction(conn, "r1", "work", red, now=100.0)
    assert _ticket_row(conn, "r1/t-0")["state"] == "needs_human"
    assert _ticket_row(conn, "r1/t-0")["reduction_id"] == rid

    queue.accept_reduction(conn, rid, now=200.0)

    assert _ticket_row(conn, "r1/t-0")["state"] == "done"
    assert conn.execute(
        "SELECT review_state FROM reductions WHERE id=?", (rid,)
    ).fetchone()[0] == "accepted"


def test_load_run_loads_prior_phase_reductions(conn):
    from engine import queue

    # Run currently on the 'reduce' phase; prior phase is 'work'.
    _mk_run(conn, "r1", phase="reduce")
    # Prior-phase (work) reductions -> should be loaded into the snapshot.
    conn.execute(
        """INSERT INTO reductions (run_id, phase, kind, json, review_state,
                                   created_at, updated_at)
           VALUES ('r1', 'work', 'cluster', ?, 'pending', 0, 0)""",
        (json.dumps({"clusters": {"parser": []}}),),
    )
    # A current-phase (reduce) reduction -> must NOT be in the snapshot.
    conn.execute(
        """INSERT INTO reductions (run_id, phase, kind, json, review_state,
                                   created_at, updated_at)
           VALUES ('r1', 'reduce', 'summary', '{}', 'pending', 0, 0)""",
    )
    conn.commit()

    run = queue.load_run(conn, "r1")

    assert len(run.reductions) == 1
    assert run.reductions[0].phase == "work"
    assert run.reductions[0].kind == "cluster"
    assert run.reductions[0].json == {"clusters": {"parser": []}}
