"""
engine.queue — the ticket + run state machine (spec §5, §9).

This is the central state-machine module. It owns every transition of
``tickets.state`` and is the SOLE transitioner of ``runs.state``
(``set_run_state``). It also resolves reductions (accept/reject) and the
operator requeue of ``needs_human`` tickets.

Transaction discipline (critical):
- ``events.emit`` does NOT commit — the queue owns the transaction. Every
  mutating callable here is ONE atomic unit: it performs its row writes + emits
  its events + commits exactly once at the end (or rolls back on error).
- ``claim_ticket`` runs under an explicit ``BEGIN IMMEDIATE`` so two concurrent
  callers can never claim the same ticket (the second blocks on the write lock,
  then sees the row already ``dispatched``).

Lease handling is Slice 6. This module deliberately does NOT read or mutate the
``leases`` table. Where a lease would be released ("on leaving running") a
``# SLICE-6 LEASE SEAM`` comment marks the hook point.

Stdlib-only (sqlite3 + json + time).
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Iterable, Optional

from engine import events
from engine.models import Result, Run, Ticket

# Backoff: available_at = now + min(BACKOFF_CAP_S, BACKOFF_BASE_S * 2**attempts)
# where ``attempts`` is the ticket's CURRENT (pre-increment) infra-failure count.
# This yields the conventional 30 / 60 / 120 s schedule for retries 1/2/3 (§5).
BACKOFF_BASE_S = 30
BACKOFF_CAP_S = 300
MAX_INFRA_ATTEMPTS = 3  # a 4th infra failure is terminal (→ failed)

# Legal run-state edges (§5). (current, target) -> event kind emitted.
_RUN_EDGES: dict[tuple[str, str], str] = {
    ("running", "paused"): "run_paused",
    ("paused", "running"): "run_resumed",
    ("running", "stopped"): "run_stopped",
    ("paused", "stopped"): "run_stopped",
    ("running", "done"): "run_done",
    ("running", "failed"): "run_failed",
}


def _now(now: Optional[float]) -> float:
    """Resolve a ``now`` argument, defaulting to wall-clock (§ ambiguity)."""
    return time.time() if now is None else now


def _backoff(attempts: int) -> float:
    """Backoff seconds for the current (pre-increment) attempts count (§5)."""
    return float(min(BACKOFF_CAP_S, BACKOFF_BASE_S * (2 ** attempts)))


# --- seeding -------------------------------------------------------------

def seed_tickets(conn: sqlite3.Connection, run: Run, playbook, site) -> list[Ticket]:
    """Insert the tickets from ``playbook.seed(run, site)`` as ``queued`` (§9).

    Returns the seeded tickets. Commits once. (No per-ticket event is emitted:
    §7 defines no ``ticket_seeded``/``ticket_queued`` kind — a ticket first
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
    """Atomically claim the highest-priority claimable ticket for ``host`` (§9).

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
    """Apply the §5 ``running``-exit transition for ``result`` (§9). ONE atomic unit.

    Reads the authoritative ticket + run rows from the db (not the passed
    handle), appends an ``attempts`` audit row, applies the transition, inserts
    the result payload into ``findings`` on ``ok`` results, emits events, and
    commits exactly once. Any error rolls the whole unit back.

    Transitions (§5):
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

        # Append the append-only attempts audit row (§4). ``attempt`` is the
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
            run = _load_run(conn, run_id)
            verified = playbook.verify(run, ticket, result, site)
            new_state = "reducing" if verified else "needs_human"
        elif result.outcome == "driver_failed":
            # Terminal on first occurrence (contract_fail / driver_error /
            # timeout all arrive as driver_failed) — no retry (§5).
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
        # run_id + ticket_id (§9); used by ``playbook.reduce`` later.
        if result.outcome == "ok":
            conn.execute(
                """INSERT INTO findings (run_id, ticket_id, kind, json, created_at)
                   VALUES (?, ?, 'result', ?, ?)""",
                (run_id, ticket.id, json.dumps(result.payload), now),
            )

        # Apply the ticket-row transition.
        # Release the ticket's lease on leaving 'running' (every branch) so a
        # scarce class frees immediately rather than after backoff/TTL (§9).
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
    """Penalty (infra) ``running → queued`` requeue (§9).

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
        # Release the ticket's lease here (leaving running) (§9).
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
    """Terminal ``running → failed`` for deterministic contract violations (§11).

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

        # Release the ticket's lease (leaving running) (§9).
        if lease_id:
            from engine import leases
            leases.release(conn, lease_id, now=now)

        # Append the append-only attempts audit row (§4).
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


def requeue_transport(conn: sqlite3.Connection, ticket: Ticket, now=None) -> None:
    """No-penalty (transport host-lost) ``running → queued`` requeue (§5, §9).

    ``attempts`` is UNCHANGED and the ticket is available immediately. Clears
    ``worker_host`` (the host was lost); ``tried_hosts`` is preserved so a fresh
    claim lands elsewhere. (Marking the host ``down`` is crew's job, Slice 6.)
    """
    now = _now(now)
    try:
        row = conn.execute(
            "SELECT run_id, lease_id FROM tickets WHERE id=?", (ticket.id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown ticket {ticket.id!r}")
        run_id, lease_id = row
        # Release the ticket's lease here (leaving running) (§9).
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
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# --- park ----------------------------------------------------------------

def park_ticket(conn: sqlite3.Connection, ticket: Ticket, now=None) -> None:
    """Revert a just-claimed ``dispatched`` ticket to ``parked`` (§5, §9).

    Clears ``worker_host``, drops the host just appended to ``tried_hosts`` (it
    never executed), leaves ``attempts`` unchanged, and emits ``ticket_parked``.
    Callers decide *when* to park (capacity/leases are Slice 6).
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
    """Return ``parked`` tickets of ``resource_class`` to ``queued`` (§9).

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
    """The SOLE transitioner of ``runs.state`` (§5, §9).

    Applies a legal §5 run edge (running↔paused, running|paused→stopped,
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
    ``done`` (§9)."""
    _resolve_reduction(conn, reduction_id, decision="accepted",
                       ticket_state="done", event="reduction_accepted", now=now)


def reject_reduction(conn: sqlite3.Connection, reduction_id: int, now=None) -> None:
    """Reject a ``pending`` reduction, settling its ``needs_human`` tickets to
    ``failed`` (§9)."""
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

        # Settle every needs_human ticket this reduction routed (§4/§9 link).
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
            # Per-ticket transition event: only 'failed' has a §7 kind; a
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
    """Operator requeue of a re-verify/guard-routed ``needs_human`` ticket (§9).

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


# --- helpers -------------------------------------------------------------

def _load_run(conn: sqlite3.Connection, run_id: str) -> Run:
    """Load a read-only ``Run`` snapshot for ``playbook.verify`` (§9).

    ``reductions`` is empty here (verify does not consume prior reductions; the
    master loop supplies them to ``seed``/``reduce`` in Slice 7)."""
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
        config=json.loads(config_json), phase=phase, reductions=[],
    )
