"""Lease-based resource semaphore: enforces capacity, issues leases, reclaims expired.

Capacity is computed from crew.resources_json (sum over idle/busy hosts). acquire
grants only when live leases are under capacity. Leases are released on every exit
from running. Caller owns the transaction. Stdlib-only.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Optional

from engine.models import Lease


DEFAULT_TTL_S = 1800


def _now(now: Optional[float]) -> float:
    """Resolve a ``now`` argument, defaulting to wall-clock time."""
    return time.time() if now is None else now


def _compute_capacity(conn: sqlite3.Connection, resource_class: str) -> int:
    """Compute class capacity from crew.resources_json (idle|busy only).

    Capacity = Σ resources_json[resource_class] over crew members currently
    idle|busy. Down and draining hosts do NOT contribute.
    """
    rows = conn.execute(
        "SELECT resources_json FROM crew WHERE state IN ('idle', 'busy')"
    ).fetchall()
    total = 0
    for (rj,) in rows:
        res = json.loads(rj)
        total += res.get(resource_class, 0)
    return total


def _count_live_leases(conn: sqlite3.Connection, resource_class: str, now: float) -> int:
    """Count live (unexpired) leases for the given resource class."""
    row = conn.execute(
        "SELECT COUNT(*) FROM leases WHERE resource_class=? AND expires_at > ?",
        (resource_class, now),
    ).fetchone()
    return row[0]


def acquire(
    conn: sqlite3.Connection,
    run_id: str,
    resource_class: str,
    ticket_id: str,
    host: str,
    now: Optional[float] = None,
    ttl_s: int = DEFAULT_TTL_S,
) -> Optional[Lease]:
    """Grant a lease iff live leases < capacity, else return None.

    Capacity = Σ crew.resources_json[resource_class] over idle|busy crew.
    On grant: insert a leases row with ttl_s, acquired_at, expires_at=now+ttl_s.
    Returns the Lease or None (caller parks).

    Does NOT commit — caller owns the transaction.
    """
    now = _now(now)
    capacity = _compute_capacity(conn, resource_class)
    live = _count_live_leases(conn, resource_class, now)

    if live >= capacity:
        return None  # at capacity; caller parks

    # Grant the lease
    lease_id = str(uuid.uuid4())
    expires_at = now + ttl_s
    conn.execute(
        """INSERT INTO leases (id, run_id, resource_class, ticket_id, host,
                               acquired_at, ttl_s, expires_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (lease_id, run_id, resource_class, ticket_id, host, now, ttl_s, expires_at),
    )

    # Emit lease_acquired event (future extension)
    from engine import events
    events.emit(
        conn, "lease_acquired", run_id=run_id, ticket_id=ticket_id, host=host,
        message=f"Lease acquired for {resource_class}",
        data={"lease_id": lease_id, "resource_class": resource_class}
    )

    return Lease(
        id=lease_id,
        run_id=run_id,
        resource_class=resource_class,
        ticket_id=ticket_id,
        host=host,
        acquired_at=now,
        ttl_s=ttl_s,
        expires_at=expires_at,
    )


def release(conn: sqlite3.Connection, lease_id: str, now: Optional[float] = None) -> None:
    """Free a lease (delete) and unpark any waiting tickets for the class.

    Does NOT commit — caller owns the transaction. After freeing, calls
    unpark_ready for the class so parked tickets can claim the freed slot.
    """
    now = _now(now)
    # Read the resource_class before deleting
    row = conn.execute(
        "SELECT resource_class FROM leases WHERE id=?", (lease_id,)
    ).fetchone()
    if row is None:
        # Lease already freed or never existed; idempotent
        return
    resource_class = row[0]

    conn.execute("DELETE FROM leases WHERE id=?", (lease_id,))

    # Import here to avoid circular dependency at module load
    from engine import queue
    queue.unpark_ready(conn, resource_class, now=now)


def renew(conn: sqlite3.Connection, lease_id: str, now: Optional[float] = None) -> None:
    """Extend expires_at = now + ttl_s.

    Does NOT commit — caller owns the transaction.
    """
    now = _now(now)
    row = conn.execute("SELECT ttl_s FROM leases WHERE id=?", (lease_id,)).fetchone()
    if row is None:
        # Lease already gone; no-op
        return
    ttl_s = row[0]
    expires_at = now + ttl_s
    conn.execute(
        "UPDATE leases SET expires_at=? WHERE id=?",
        (expires_at, lease_id),
    )


def reclaim_expired(conn: sqlite3.Connection, now: Optional[float] = None) -> None:
    """Free every expired lease and requeue only still-non-terminal tickets.

    A lease whose ticket is dispatched|running is requeued (no attempt penalty);
    a lease whose ticket is already terminal (done|failed|needs_human) or gone
    is simply freed, never requeued. After freeing slots, calls unpark_ready
    for each affected class.

    Does NOT commit — caller owns the transaction.
    """
    now = _now(now)
    # Find all expired leases
    expired = conn.execute(
        "SELECT id, resource_class, ticket_id FROM leases WHERE expires_at <= ?",
        (now,),
    ).fetchall()

    if not expired:
        return

    # Import here to avoid circular dependency
    from engine import queue

    # Collect classes to unpark
    affected_classes = set()

    for lease_id, resource_class, ticket_id in expired:
        affected_classes.add(resource_class)

        # Fetch run_id for event emission before deleting
        lease_run_id = None
        if ticket_id:
            row = conn.execute(
                "SELECT run_id FROM leases WHERE id=?", (lease_id,)
            ).fetchone()
            if row:
                lease_run_id = row[0]

        # Delete the lease
        conn.execute("DELETE FROM leases WHERE id=?", (lease_id,))

        # Emit lease_reclaimed event (future extension)
        if lease_run_id:
            from engine import events
            events.emit(
                conn, "lease_reclaimed", run_id=lease_run_id, ticket_id=ticket_id,
                message=f"Lease reclaimed (expired)",
                data={"lease_id": lease_id, "resource_class": resource_class}
            )

        if ticket_id:
            # Check ticket state: requeue only if still non-terminal
            trow = conn.execute(
                "SELECT run_id, state, attempts FROM tickets WHERE id=?",
                (ticket_id,),
            ).fetchone()
            if trow is None:
                # Ticket gone; lease is freed, nothing to requeue
                continue
            run_id, state, attempts = trow

            # Non-terminal states: queued, dispatched, running, parked, reducing
            # Terminal: done, failed, needs_human
            # We only requeue dispatched|running (the ones that were in flight)
            if state in ("dispatched", "running"):
                # Requeue with no penalty
                conn.execute(
                    """UPDATE tickets SET state='queued', available_at=?,
                           worker_host=NULL, lease_id=NULL, updated_at=?
                       WHERE id=?""",
                    (now, now, ticket_id),
                )
                # Emit event
                from engine import events
                events.emit(
                    conn, "ticket_requeued", run_id=run_id, ticket_id=ticket_id,
                    message="lease reclaimed (expired)",
                    data={"no_penalty": True, "lease_id": lease_id},
                )

    # Unpark tickets for each affected class
    for resource_class in affected_classes:
        queue.unpark_ready(conn, resource_class, now=now)
