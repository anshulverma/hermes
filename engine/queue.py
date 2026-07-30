"""The central state machine for tickets and runs.

Owns every transition of tickets.state and runs.state. Each mutating function is one
atomic unit: row writes, event emission, and commit. claim_ticket runs under BEGIN
IMMEDIATE for concurrency safety. Does not directly touch leases (caller releases).
Stdlib-only.
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Iterable, Optional

from engine import events
from engine.models import Finding, Reduction, Result, Run, Ticket

# Backoff: available_at = now + min(BACKOFF_CAP_S, BACKOFF_BASE_S * 2**attempts)
# where ``attempts`` is the ticket's CURRENT (pre-increment) infra-failure count.
# This yields the conventional 30 / 60 / 120 s schedule for retries 1/2/3.
BACKOFF_BASE_S = 30
BACKOFF_CAP_S = 300
MAX_INFRA_ATTEMPTS = 3  # a 4th infra failure is terminal (→ failed)

# Legal run-state edges. (current, target) -> event kind emitted.
_RUN_EDGES: dict[tuple[str, str], str] = {
    ("running", "paused"): "run_paused",
    ("paused", "running"): "run_resumed",
    ("running", "stopped"): "run_stopped",
    ("paused", "stopped"): "run_stopped",
    ("running", "done"): "run_done",
    ("running", "failed"): "run_failed",
}


def _now(now: Optional[float]) -> float:
    """Resolve a ``now`` argument, defaulting to wall-clock ."""
    return time.time() if now is None else now


def _backoff(attempts: int) -> float:
    """Backoff seconds for the current (pre-increment) attempts count."""
    return float(min(BACKOFF_CAP_S, BACKOFF_BASE_S * (2 ** attempts)))


# --- seeding -------------------------------------------------------------

def seed_tickets(conn: sqlite3.Connection, run: Run, playbook, site) -> list[Ticket]:
    """Insert the tickets from ``playbook.seed(run, site)`` as ``queued``.

    Returns the seeded tickets. Commits once. (No per-ticket event is emitted:
    no ``ticket_seeded``/``ticket_queued`` kind — a ticket first
    surfaces on the feed via ``ticket_claimed``; a mid-unit invalid emit would
    only raise.)
    """
    now = time.time()
    tickets = list(playbook.seed(run, site))
    for t in tickets:
        conn.execute(
            """INSERT INTO tickets
                 (id, run_id, phase, state, resource_req, priority, attempts,
                  available_at, tried_hosts, payload_json, created_at, updated_at)
               VALUES (?, ?, ?, 'queued', ?, ?, ?, 0, '[]', ?, ?, ?)""",
            (
                t.id, t.run_id, t.phase, t.resource_req, t.priority, t.attempts,
                json.dumps(t.payload), now, now,
            ),
        )
    conn.commit()
    return tickets


# --- claim (atomic) ------------------------------------------------------

def claim_ticket(
    conn: sqlite3.Connection,
    host: str,
    resource_reqs: Iterable[str],
    now: Optional[float] = None,
) -> Optional[Ticket]:
    """Atomically claim the highest-priority claimable ticket for ``host``.

    Selects, under ``BEGIN IMMEDIATE``, the highest-priority ``queued`` ticket
    whose owning run is ``running``, whose ``resource_req`` the host serves
    (``resource_reqs``), and whose ``available_at <= now``; marks it
    ``dispatched`` + ``worker_host=host``, appends ``host`` to ``tried_hosts``,
    emits ``ticket_claimed``. Returns the claimed ``Ticket`` or ``None``.

    Two concurrent callers never get the same ticket: the second's
    ``BEGIN IMMEDIATE`` blocks on the write lock (``busy_timeout``), then its
    ``state='queued'`` filter excludes the just-dispatched row.
    """
    now = _now(now)
    reqs = list(resource_reqs)
    if not reqs:
        return None

    placeholders = ",".join("?" for _ in reqs)
    prev_iso = conn.isolation_level
    conn.isolation_level = None  # autocommit off only inside our explicit txn
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                f"""SELECT t.id, t.run_id, t.phase, t.resource_req, t.priority,
                           t.attempts, t.payload_json, t.tried_hosts
                    FROM tickets t
                    JOIN runs r ON r.id = t.run_id
                    WHERE t.state = 'queued'
                      AND r.state = 'running'
                      AND t.available_at <= ?
                      AND t.resource_req IN ({placeholders})
                    ORDER BY t.priority DESC, t.created_at ASC, t.id ASC
                    LIMIT 1""",
                (now, *reqs),
            ).fetchone()

            if row is None:
                conn.execute("COMMIT")
                return None

            (tid, run_id, phase, resource_req, priority, attempts,
             payload_json, tried_json) = row
            tried = json.loads(tried_json)
            tried.append(host)

            conn.execute(
                """UPDATE tickets
                   SET state='dispatched', worker_host=?, tried_hosts=?,
                       updated_at=?
                   WHERE id=?""",
                (host, json.dumps(tried), now, tid),
            )
            events.emit(
                conn, "ticket_claimed", run_id=run_id, ticket_id=tid, host=host,
                message=f"claimed by {host}",
                data={"resource_req": resource_req, "priority": priority},
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.isolation_level = prev_iso

    return Ticket(
        id=tid, run_id=run_id, phase=phase, state="dispatched",
        resource_req=resource_req, priority=priority, attempts=attempts,
        payload=json.loads(payload_json),
    )


# --- record_result: the running-exit state machine -----------------------

def record_result(
    conn: sqlite3.Connection,
    ticket: Ticket,
    host: str,
    result: Result,
    now,
    playbook,
    site,
) -> str:
    """Apply the ``running``-exit transition for ``result``. ONE atomic unit.

    Reads the authoritative ticket + run rows from the db (not the passed
    handle), appends an ``attempts`` audit row, applies the transition, inserts
    the result payload into ``findings`` on ``ok`` results, emits events, and
    commits exactly once. Any error rolls the whole unit back.

    Transitions:
      - ``ok`` & ``playbook.verify`` True  → ``reducing``
      - ``ok`` & ``playbook.verify`` False → ``needs_human`` (re-verify override)
      - ``driver_failed``                  → ``failed`` (terminal, no retry)
      - ``infra_failed`` & attempts<3      → ``queued`` (attempts+1, backoff)
      - ``infra_failed`` & attempts==3     → ``failed`` (4th failure terminal)

    Returns the new ticket state.
    """
    now = _now(now)
    try:
        trow = conn.execute(
            "SELECT run_id, phase, attempts FROM tickets WHERE id=?",
            (ticket.id,),
        ).fetchone()
        if trow is None:
            raise ValueError(f"unknown ticket {ticket.id!r}")
        run_id, phase, attempts = trow

        # Append the append-only attempts audit row. ``attempt`` is the
        # 1-based index of this execution among the ticket's tries.
        conn.execute(
            """INSERT INTO attempts
                 (ticket_id, phase, host, attempt, started_at, ended_at,
                  outcome, termination_reason, result_ref, error_summary)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ticket.id, phase, host, attempts + 1, result.started_at,
                result.ended_at, result.outcome, result.termination_reason,
                result.result_ref, result.error_summary,
            ),
        )

        # Decide the transition.
        new_state: str
        new_attempts = attempts
        new_available_at: Optional[float] = None
        clear_worker = False

        if result.outcome == "ok":
            run = load_run(conn, run_id)
            verified = playbook.verify(run, ticket, result, site)
            new_state = "reducing" if verified else "needs_human"
        elif result.outcome == "driver_failed":
            # Terminal on first occurrence (contract_fail / driver_error /
            # timeout all arrive as driver_failed) — no retry.
            new_state = "failed"
        elif result.outcome == "infra_failed":
            if attempts < MAX_INFRA_ATTEMPTS:
                new_state = "queued"
                new_available_at = now + _backoff(attempts)
                new_attempts = attempts + 1
                clear_worker = True
            else:
                new_state = "failed"  # 4th infra failure is terminal
        else:
            raise ValueError(f"unknown result outcome {result.outcome!r}")

        # On ``ok`` results, bank the playbook payload as a finding, stamping
        # run_id + ticket_id; used by ``playbook.reduce`` later.
        if result.outcome == "ok":
            conn.execute(
                """INSERT INTO findings (run_id, ticket_id, kind, json, created_at)
                   VALUES (?, ?, 'result', ?, ?)""",
                (run_id, ticket.id, json.dumps(result.payload), now),
            )

        # Apply the ticket-row transition.
        # Release the ticket's lease on leaving 'running' (every branch) so a
        # scarce class frees immediately rather than after backoff/TTL.
        lease_id_row = conn.execute(
            "SELECT lease_id FROM tickets WHERE id=?", (ticket.id,)
        ).fetchone()
        if lease_id_row and lease_id_row[0]:
            from engine import leases
            leases.release(conn, lease_id_row[0], now=now)

        if new_available_at is not None:
            conn.execute(
                """UPDATE tickets
                   SET state=?, attempts=?, available_at=?,
                       worker_host=CASE WHEN ? THEN NULL ELSE worker_host END,
                       updated_at=?
                   WHERE id=?""",
                (new_state, new_attempts, new_available_at, clear_worker,
                 now, ticket.id),
            )
        else:
            conn.execute(
                "UPDATE tickets SET state=?, attempts=?, updated_at=? WHERE id=?",
                (new_state, new_attempts, now, ticket.id),
            )

        # Emit events.
        events.emit(
            conn, "result_recorded", run_id=run_id, ticket_id=ticket.id,
            host=host,
            data={"outcome": result.outcome,
                  "termination_reason": result.termination_reason,
                  "new_state": new_state},
        )
        if new_state == "queued":
            events.emit(
                conn, "ticket_requeued", run_id=run_id, ticket_id=ticket.id,
                host=host, message="infra retry",
                data={"attempts": new_attempts, "available_at": new_available_at},
            )
        elif new_state == "needs_human":
            events.emit(conn, "needs_human", run_id=run_id, ticket_id=ticket.id,
                        message="re-verify override")
            events.emit(conn, "attention", run_id=run_id, ticket_id=ticket.id,
                        data={"reason": "needs_human"})
        elif new_state == "failed":
            events.emit(conn, "ticket_failed", run_id=run_id, ticket_id=ticket.id,
                        host=host,
                        data={"termination_reason": result.termination_reason})
            events.emit(conn, "attention", run_id=run_id, ticket_id=ticket.id,
                        data={"reason": "failed"})

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return new_state


# --- running -> queued requeue paths -------------------------------------

def requeue(conn: sqlite3.Connection, ticket: Ticket, now=None) -> None:
    """Penalty (infra) ``running → queued`` requeue.

    Increments ``attempts`` and applies exponential backoff (the caller uses
    this for envelope/validation errors detected outside a Result). Clears
    ``worker_host`` (fresh claim reassigns); ``tried_hosts`` is preserved.
    """
    now = _now(now)
    try:
        row = conn.execute(
            "SELECT run_id, attempts, lease_id FROM tickets WHERE id=?", (ticket.id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown ticket {ticket.id!r}")
        run_id, attempts, lease_id = row
        # Release the ticket's lease here (leaving running).
        if lease_id:
            from engine import leases
            leases.release(conn, lease_id, now=now)
        new_attempts = attempts + 1
        available_at = now + _backoff(attempts)
        conn.execute(
            """UPDATE tickets SET state='queued', attempts=?, available_at=?,
                   worker_host=NULL, updated_at=? WHERE id=?""",
            (new_attempts, available_at, now, ticket.id),
        )
        events.emit(
            conn, "ticket_requeued", run_id=run_id, ticket_id=ticket.id,
            message="requeue (penalty)",
            data={"attempts": new_attempts, "available_at": available_at},
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def fail_contract_violation(
    conn: sqlite3.Connection,
    ticket: Ticket,
    host: str,
    error_summary: str,
    now=None,
) -> None:
    """Terminal ``running → failed`` for deterministic contract violations.

    Used for envelope validation errors (ContractError) and no-ship guard
    violations. These are DETERMINISTIC failures that will never succeed on retry,
    so the ticket goes straight to ``failed`` with ``termination_reason =
    contract_fail``. No ``attempts`` penalty is applied (this is not an infra
    retry). The lease is released. An ``attempts`` audit row is written.
    """
    now = _now(now)
    try:
        row = conn.execute(
            "SELECT run_id, phase, attempts, lease_id FROM tickets WHERE id=?",
            (ticket.id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown ticket {ticket.id!r}")
        run_id, phase, attempts, lease_id = row

        # Release the ticket's lease (leaving running).
        if lease_id:
            from engine import leases
            leases.release(conn, lease_id, now=now)

        # Append the append-only attempts audit row.
        conn.execute(
            """INSERT INTO attempts
                 (ticket_id, phase, host, attempt, started_at, ended_at,
                  outcome, termination_reason, result_ref, error_summary)
               VALUES (?, ?, ?, ?, ?, ?, 'driver_failed', 'contract_fail', NULL, ?)""",
            (ticket.id, phase, host, attempts + 1, now, now, error_summary),
        )

        # Transition to failed (terminal, no retry).
        conn.execute(
            "UPDATE tickets SET state='failed', updated_at=? WHERE id=?",
            (now, ticket.id),
        )

        # Emit events.
        events.emit(
            conn, "ticket_failed", run_id=run_id, ticket_id=ticket.id, host=host,
            data={"termination_reason": "contract_fail"},
        )
        events.emit(
            conn, "attention", run_id=run_id, ticket_id=ticket.id,
            data={"reason": "failed"},
        )

        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _requeue_transport_nocommit(
    conn: sqlite3.Connection, ticket: Ticket, now=None
) -> None:
    """No-penalty transport ``running → queued`` requeue WITHOUT committing.

    Shared body of the transport requeue. It performs only row writes + an
    ``events.emit`` (which also does not commit), so a CALLER that is itself one
    atomic unit — e.g. ``crew.heartbeat_sweep``, which requeues several down
    hosts' tickets and must commit exactly once — can invoke it mid-transaction
    without flushing earlier uncommitted writes. ``requeue_transport`` wraps this
    for standalone callers (serve loop).
    """
    now = _now(now)
    row = conn.execute(
        "SELECT run_id, lease_id FROM tickets WHERE id=?", (ticket.id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown ticket {ticket.id!r}")
    run_id, lease_id = row
    # Release the ticket's lease here (leaving running).
    if lease_id:
        from engine import leases
        leases.release(conn, lease_id, now=now)
    conn.execute(
        """UPDATE tickets SET state='queued', available_at=?,
               worker_host=NULL, updated_at=? WHERE id=?""",
        (now, now, ticket.id),
    )
    events.emit(
        conn, "ticket_requeued", run_id=run_id, ticket_id=ticket.id,
        message="requeue (transport, no penalty)",
        data={"no_penalty": True},
    )


def requeue_transport(conn: sqlite3.Connection, ticket: Ticket, now=None) -> None:
    """No-penalty (transport host-lost) ``running → queued`` requeue.

    ``attempts`` is UNCHANGED and the ticket is available immediately. Clears
    ``worker_host`` (the host was lost); ``tried_hosts`` is preserved so a fresh
    claim lands elsewhere. (Marking the host ``down`` is crew's job.)
    Standalone atomic unit: wraps ``_requeue_transport_nocommit`` + commits.
    """
    try:
        _requeue_transport_nocommit(conn, ticket, now=now)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# --- park ----------------------------------------------------------------

def park_ticket(conn: sqlite3.Connection, ticket: Ticket, now=None) -> None:
    """Revert a just-claimed ``dispatched`` ticket to ``parked``.

    Clears ``worker_host``, drops the host just appended to ``tried_hosts`` (it
    never executed), leaves ``attempts`` unchanged, and emits ``ticket_parked``.
    Callers decide *when* to park (capacity/leases).
    """
    now = _now(now)
    try:
        row = conn.execute(
            "SELECT run_id, worker_host, tried_hosts FROM tickets WHERE id=?",
            (ticket.id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown ticket {ticket.id!r}")
        run_id, worker_host, tried_json = row
        tried = json.loads(tried_json)
        # Drop the just-appended host (the one that claimed but never executed).
        if worker_host is not None and tried and tried[-1] == worker_host:
            tried.pop()
        elif worker_host in tried:
            tried.remove(worker_host)
        conn.execute(
            """UPDATE tickets SET state='parked', worker_host=NULL,
                   tried_hosts=?, updated_at=? WHERE id=?""",
            (json.dumps(tried), now, ticket.id),
        )
        events.emit(conn, "ticket_parked", run_id=run_id, ticket_id=ticket.id,
                    message="parked (no lease)")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def unpark_ready(conn: sqlite3.Connection, resource_class: str, now=None) -> None:
    """Return ``parked`` tickets of ``resource_class`` to ``queued``.

    Called when the class regains capacity (lease freed, crew added). Moves
    parked tickets back to queued (fresh claim, no penalty). Does NOT commit —
    caller owns the transaction (like events.emit).
    """
    now = _now(now)
    # Find all parked tickets for this resource class
    rows = conn.execute(
        """SELECT id, run_id FROM tickets
           WHERE state='parked' AND resource_req=?""",
        (resource_class,),
    ).fetchall()

    for ticket_id, run_id in rows:
        conn.execute(
            """UPDATE tickets SET state='queued', available_at=?, updated_at=?
               WHERE id=?""",
            (now, now, ticket_id),
        )
        events.emit(
            conn, "ticket_requeued", run_id=run_id, ticket_id=ticket_id,
            message="unparked (capacity regained)",
            data={"no_penalty": True, "resource_class": resource_class},
        )


# --- run state machine (sole runs.state transitioner) --------------------

def set_run_state(conn: sqlite3.Connection, run_id: str, new_state: str, now=None) -> None:
    """The SOLE transitioner of ``runs.state``.

    Applies a legal run edge (running↔paused, running|paused→stopped,
    running→done, running→failed) and emits the matching ``run_*`` event; raises
    ``ValueError`` on an illegal edge (e.g. resuming a terminal run) or an
    unknown run.
    """
    now = _now(now)
    try:
        row = conn.execute(
            "SELECT state FROM runs WHERE id=?", (run_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown run {run_id!r}")
        current = row[0]
        event_kind = _RUN_EDGES.get((current, new_state))
        if event_kind is None:
            raise ValueError(
                f"illegal run transition {current!r} -> {new_state!r} "
                f"for run {run_id!r}"
            )
        conn.execute(
            "UPDATE runs SET state=?, updated_at=? WHERE id=?",
            (new_state, now, run_id),
        )
        events.emit(conn, event_kind, run_id=run_id,
                    message=f"{current} -> {new_state}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# --- reduction resolution ------------------------------------------------

def accept_reduction(conn: sqlite3.Connection, reduction_id: int, now=None) -> None:
    """Accept a ``pending`` reduction, settling its ``needs_human`` tickets to
    ``done``."""
    _resolve_reduction(conn, reduction_id, decision="accepted",
                       ticket_state="done", event="reduction_accepted", now=now)


def reject_reduction(conn: sqlite3.Connection, reduction_id: int, now=None) -> None:
    """Reject a ``pending`` reduction, settling its ``needs_human`` tickets to
    ``failed``."""
    _resolve_reduction(conn, reduction_id, decision="rejected",
                       ticket_state="failed", event="reduction_rejected", now=now)


def _resolve_reduction(conn, reduction_id, decision, ticket_state, event, now):
    """Shared accept/reject machinery. ONE atomic unit."""
    now = _now(now)
    try:
        row = conn.execute(
            "SELECT run_id, review_state FROM reductions WHERE id=?",
            (reduction_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown reduction {reduction_id!r}")
        run_id, review_state = row
        if review_state != "pending":
            raise ValueError(
                f"reduction {reduction_id!r} is {review_state!r}, not 'pending'; "
                f"already resolved"
            )

        conn.execute(
            "UPDATE reductions SET review_state=?, updated_at=? WHERE id=?",
            (decision, now, reduction_id),
        )

        # Settle every needs_human ticket this reduction routed.
        ticket_ids = [
            r[0] for r in conn.execute(
                """SELECT id FROM tickets
                   WHERE reduction_id=? AND state='needs_human'""",
                (reduction_id,),
            ).fetchall()
        ]
        for tid in ticket_ids:
            conn.execute(
                "UPDATE tickets SET state=?, updated_at=? WHERE id=?",
                (ticket_state, now, tid),
            )
            # Per-ticket transition event: only 'failed' has a defined kind; a
            # settled 'done' ticket is reflected in the reduction event's data.
            if ticket_state == "failed":
                events.emit(conn, "ticket_failed", run_id=run_id, ticket_id=tid,
                            data={"reason": "reduction_rejected"})

        events.emit(
            conn, event, run_id=run_id,
            data={"reduction_id": reduction_id, "settled_ticket_ids": ticket_ids},
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def requeue_needs_human(conn: sqlite3.Connection, ticket_id: str, now=None) -> None:
    """Operator requeue of a re-verify/guard-routed ``needs_human`` ticket.

    ``needs_human → queued`` as a fresh attempt: ``attempts`` UNCHANGED, the
    ticket is available immediately, ``worker_host`` and any ``reduction_id``
    link cleared. Raises if the ticket is not in ``needs_human``.
    """
    now = _now(now)
    try:
        row = conn.execute(
            "SELECT run_id, state FROM tickets WHERE id=?", (ticket_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown ticket {ticket_id!r}")
        run_id, state = row
        if state != "needs_human":
            raise ValueError(
                f"ticket {ticket_id!r} is {state!r}, not 'needs_human'; "
                f"cannot operator-requeue"
            )
        conn.execute(
            """UPDATE tickets SET state='queued', available_at=?,
                   worker_host=NULL, reduction_id=NULL, updated_at=?
               WHERE id=?""",
            (now, now, ticket_id),
        )
        events.emit(conn, "ticket_requeued", run_id=run_id, ticket_id=ticket_id,
                    message="operator requeue (needs_human)",
                    data={"no_penalty": True})
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def abandon_ticket(conn: sqlite3.Connection, ticket_id: str, now=None) -> None:
    """Operator abandon: non-terminal ticket → failed.

    Transitions any non-terminal state (queued/dispatched/running/reducing/parked/
    needs_human) to ``failed``. Releases the ticket's live lease if present, clears
    ``worker_host``, and emits ``ticket_abandoned``. Raises ``ValueError`` if the
    ticket is already terminal (done/failed) or unknown.
    """
    now = _now(now)
    try:
        row = conn.execute(
            "SELECT run_id, state, lease_id FROM tickets WHERE id=?", (ticket_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown ticket {ticket_id!r}")
        run_id, state, lease_id = row

        # Terminal states cannot be abandoned
        if state in ("done", "failed"):
            raise ValueError(
                f"ticket {ticket_id!r} is {state!r} (terminal); cannot abandon"
            )

        # Release the ticket's lease if present
        if lease_id:
            from engine import leases
            leases.release(conn, lease_id, now=now)

        # Transition to failed and clear worker_host
        conn.execute(
            """UPDATE tickets SET state='failed', worker_host=NULL, updated_at=?
               WHERE id=?""",
            (now, ticket_id),
        )

        # Emit event
        events.emit(
            conn, "ticket_abandoned", run_id=run_id, ticket_id=ticket_id,
            data={"reason": "operator_abandoned"},
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def retry_ticket(conn: sqlite3.Connection, ticket_id: str, now=None) -> None:
    """Operator retry: failed ticket → queued.

    Transitions a ``failed`` ticket to ``queued`` (available immediately), clearing
    ``worker_host``, ``lease_id``, and ``reduction_id``. Attempts count is UNCHANGED
    (no penalty). Emits ``ticket_requeued``. Raises ``ValueError`` if the ticket is
    not in ``failed`` state or unknown.
    """
    now = _now(now)
    try:
        row = conn.execute(
            "SELECT run_id, state FROM tickets WHERE id=?", (ticket_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown ticket {ticket_id!r}")
        run_id, state = row

        if state != "failed":
            raise ValueError(
                f"ticket {ticket_id!r} is {state!r}, not 'failed'; cannot retry"
            )

        conn.execute(
            """UPDATE tickets SET state='queued', available_at=?,
                   worker_host=NULL, reduction_id=NULL, updated_at=?
               WHERE id=?""",
            (now, now, ticket_id),
        )

        events.emit(
            conn, "ticket_requeued", run_id=run_id, ticket_id=ticket_id,
            message="operator retry",
            data={"reason": "operator_retry"},
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def set_ticket_priority(
    conn: sqlite3.Connection, ticket_id: str, priority: float, now=None
) -> None:
    """Operator reprioritize: update a non-terminal ticket's priority.

    Updates the ``priority`` field for a non-terminal ticket and emits
    ``ticket_reprioritized``. Raises ``ValueError`` if the ticket is terminal
    (done/failed) or unknown.
    """
    now = _now(now)
    try:
        row = conn.execute(
            "SELECT run_id, state FROM tickets WHERE id=?", (ticket_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown ticket {ticket_id!r}")
        run_id, state = row

        # Terminal states cannot be reprioritized
        if state in ("done", "failed"):
            raise ValueError(
                f"ticket {ticket_id!r} is {state!r} (terminal); cannot reprioritize"
            )

        conn.execute(
            "UPDATE tickets SET priority=?, updated_at=? WHERE id=?",
            (priority, now, ticket_id),
        )

        events.emit(
            conn, "ticket_reprioritized", run_id=run_id, ticket_id=ticket_id,
            data={"priority": priority},
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# --- master-side reduce / advance writers ---------------------------
#
# These are the SEAM the master loop (dispatch.py) drives: dispatch.py
# ORCHESTRATES (calls playbook.reduce / next_phase / is_done and decides what to
# do), while every ``tickets.state`` / ``runs.phase`` write for the reduce+advance
# step happens HERE, keeping the queue the sole owner of state transitions. Each
# callable below is one atomic unit (owns its commit; ``events.emit`` does not).


def load_findings(
    conn: sqlite3.Connection, run_id: str, phase: str
) -> list[Finding]:
    """Read the ``findings`` rows for a phase, as ``Finding`` models.

    Scopes by ``tickets.phase`` via a ``findings→tickets`` join on ``ticket_id``
    (findings carry no phase of their own). Read-only; no commit. Feeds the
    master loop's ``playbook.reduce(run, phase, findings, site)``.
    """
    rows = conn.execute(
        """SELECT f.run_id, f.ticket_id, f.kind, f.json
           FROM findings f
           JOIN tickets t ON t.id = f.ticket_id
           WHERE f.run_id = ? AND t.phase = ?
           ORDER BY f.id""",
        (run_id, phase),
    ).fetchall()
    return [
        Finding(run_id=r[0], ticket_id=r[1], kind=r[2], json=json.loads(r[3]))
        for r in rows
    ]


def record_reduction(
    conn: sqlite3.Connection,
    run_id: str,
    phase: str,
    reduction: Reduction,
    now: Optional[float] = None,
) -> int:
    """Persist one ``Reduction`` for a phase and route its flagged tickets.

    INSERTs one ``reductions`` row (run_id, phase, kind, json,
    review_state='pending'); for every ticket id in the reduction's
    ``needs_human_ticket_ids`` (carried in ``reduction.json``) that is currently
    ``reducing``, routes it ``reducing → needs_human`` and stamps
    ``tickets.reduction_id`` to the new reduction id, emitting ``needs_human`` +
    ``attention`` per ticket. Emits ``reduction_created`` once. Returns the new
    reduction id. ONE atomic unit (single commit).
    """
    now = _now(now)
    try:
        cur = conn.execute(
            """INSERT INTO reductions
                 (run_id, phase, kind, json, review_state, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
            (run_id, phase, reduction.kind, json.dumps(reduction.json), now, now),
        )
        reduction_id = cur.lastrowid

        # Route the flagged, still-reducing tickets to needs_human.
        flagged = reduction.json.get("needs_human_ticket_ids") or []
        for tid in flagged:
            trow = conn.execute(
                "SELECT state FROM tickets WHERE id=? AND run_id=?",
                (tid, run_id),
            ).fetchone()
            if trow is None or trow[0] != "reducing":
                continue  # only reducing tickets are flag-routable
            conn.execute(
                """UPDATE tickets SET state='needs_human', reduction_id=?,
                       updated_at=? WHERE id=?""",
                (reduction_id, now, tid),
            )
            events.emit(conn, "needs_human", run_id=run_id, ticket_id=tid,
                        message="reduction flagged for human",
                        data={"reduction_id": reduction_id})
            events.emit(conn, "attention", run_id=run_id, ticket_id=tid,
                        data={"reason": "needs_human"})

        events.emit(conn, "reduction_created", run_id=run_id,
                    message=f"reduction recorded for phase {phase!r}",
                    data={"reduction_id": reduction_id, "phase": phase,
                          "kind": reduction.kind})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return reduction_id


def finish_phase_reductions(
    conn: sqlite3.Connection, run_id: str, phase: str, now: Optional[float] = None
) -> None:
    """Settle a phase's remaining ``reducing`` tickets to ``done``.

    Called by the master loop after every reduction for ``phase`` is recorded:
    every phase ticket STILL in ``reducing`` (i.e. not flagged to ``needs_human``
    by ``record_reduction``) transitions ``reducing → done``. A settled ``done``
    ticket has no per-ticket kind (mirrors ``accept_reduction``); it surfaces
    via the phase's reduction/advance events. ONE atomic unit (single commit).
    """
    now = _now(now)
    try:
        conn.execute(
            """UPDATE tickets SET state='done', updated_at=?
               WHERE run_id=? AND phase=? AND state='reducing'""",
            (now, run_id, phase),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def set_run_phase(
    conn: sqlite3.Connection, run_id: str, phase: str, now: Optional[float] = None
) -> None:
    """The SOLE writer of ``runs.phase``.

    Updates ``runs.phase`` and emits ``phase_advanced``. Raises on an unknown
    run. ONE atomic unit (single commit).
    """
    now = _now(now)
    try:
        row = conn.execute(
            "SELECT phase FROM runs WHERE id=?", (run_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown run {run_id!r}")
        old_phase = row[0]
        conn.execute(
            "UPDATE runs SET phase=?, updated_at=? WHERE id=?",
            (phase, now, run_id),
        )
        events.emit(conn, "phase_advanced", run_id=run_id,
                    message=f"{old_phase} -> {phase}",
                    data={"from": old_phase, "to": phase})
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def phase_ticket_counts(
    conn: sqlite3.Connection, run_id: str, phase: str
) -> dict[str, int]:
    """Counts of phase-N tickets by ``state``.

    Read-only helper for the master loop's advance/stuck decision (only phases
    whose tickets have all settled out of the active states may advance).
    """
    rows = conn.execute(
        """SELECT state, COUNT(*) FROM tickets
           WHERE run_id=? AND phase=? GROUP BY state""",
        (run_id, phase),
    ).fetchall()
    return {state: count for state, count in rows}


# --- helpers -------------------------------------------------------------

def _load_prior_reductions(
    conn: sqlite3.Connection, run_id: str, current_phase
) -> list[Reduction]:
    """Load the PRIOR phase's reductions for a ``Run`` snapshot.

    ``seed`` builds phase-N tickets from phase-(N-1) reductions, so the snapshot
    must carry the immediately-preceding phase's reductions. The playbook's phase
    ORDER is not stored in the db, so we use creation order instead: reductions
    are stamped with their phase when recorded (FIX 3) and phases are reduced in
    order, so the newest reductions whose phase differs from ``current_phase``
    belong to the immediately-preceding phase. Empty for phase 0.
    """
    row = conn.execute(
        """SELECT phase FROM reductions
           WHERE run_id=? AND (phase IS NULL OR phase != ?)
           ORDER BY id DESC LIMIT 1""",
        (run_id, current_phase),
    ).fetchone()
    if row is None:
        return []
    prior_phase = row[0]
    if prior_phase is None:
        rows = conn.execute(
            """SELECT id, run_id, phase, kind, json, review_state
               FROM reductions WHERE run_id=? AND phase IS NULL ORDER BY id""",
            (run_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT id, run_id, phase, kind, json, review_state
               FROM reductions WHERE run_id=? AND phase=? ORDER BY id""",
            (run_id, prior_phase),
        ).fetchall()
    return [
        Reduction(id=r[0], run_id=r[1], phase=r[2], kind=r[3],
                  json=json.loads(r[4]), review_state=r[5])
        for r in rows
    ]


def load_run(conn: sqlite3.Connection, run_id: str) -> Run:
    """Load a read-only ``Run`` snapshot.

    ``reductions`` carries the PRIOR phase's reductions (loaded from the db via
    ``_load_prior_reductions``), so ``seed``/``reduce`` can build phase-N work
    from phase-(N-1) output (and a paused run can reload it). ``verify`` ignores
    them; the master loop consumes them."""
    row = conn.execute(
        """SELECT id, playbook, site, base_ref, config_json, phase
           FROM runs WHERE id=?""",
        (run_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown run {run_id!r}")
    rid, pb, site, base_ref, config_json, phase = row
    return Run(
        id=rid, playbook=pb, site=site, base_ref=base_ref,
        config=json.loads(config_json), phase=phase,
        reductions=_load_prior_reductions(conn, run_id, phase),
    )
