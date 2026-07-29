"""
engine.crew — crew management (register, add, health-gate, heartbeat, drain, remove).

From docs/specs/engine-core.md §7, §9. Stdlib-only (sqlite3 + json + time).

Crew functions own their commit boundary (like queue mutators).
"""
import json
import sqlite3
import time
from typing import Optional

from engine import events, leases, queue
from engine.models import CrewMember, HealthReport


def _now(now: Optional[float] = None) -> float:
    """Return now (default time.time())."""
    return now if now is not None else time.time()


def add(
    conn: sqlite3.Connection,
    site,
    agent,
    host: str,
    base_ref: str,
    now: Optional[float] = None,
) -> None:
    """Provision and health-gate a host; admit only if healthy (§7, §9).

    Calls site.provision(host, base_ref), then site.health(host, agent).
    Admits (INSERT/UPDATE crew row) ONLY if report.ok; otherwise raises
    ValueError listing the failing checks. Emits crew_added / crew_health.

    Args:
        conn: SQLite connection
        site: Site implementing provision + health
        agent: Agent for health checks
        host: Host identifier
        base_ref: Base ref for provisioning
        now: Timestamp (default time.time())

    Raises:
        ValueError: If health report is not ok (lists failing checks)
    """
    now = _now(now)

    try:
        # Provision the host
        site.provision(host, base_ref)

        # Health-gate: probe the host
        report: HealthReport = site.health(host, agent)

        if not report.ok:
            # Collect failing checks
            failing = [c for c in report.checks if not c.ok]
            names = ", ".join(c.name for c in failing)
            raise ValueError(
                f"Host {host!r} failed health checks ({names}). "
                f"Cannot admit unhealthy host."
            )

        # Admit: INSERT or UPDATE crew row
        capabilities = json.dumps([])
        resources_json = json.dumps(report.resources)
        health_json = json.dumps({
            "reachable": report.reachable,
            "agent_ok": report.agent_ok,
            "auth_ok": report.auth_ok,
            "workspace_ready": report.workspace_ready,
            "guard_installed": report.guard_installed,
            "latency_ms": report.latency_ms,
        })

        # Check if host exists
        existing = conn.execute("SELECT id FROM crew WHERE id=?", (host,)).fetchone()

        if existing:
            # Update existing crew member (recovery)
            conn.execute(
                """UPDATE crew SET site=?, capabilities=?, resources_json=?,
                   state='idle', health_json=?, last_heartbeat=?
                   WHERE id=?""",
                (site.name, capabilities, resources_json, health_json, now, host),
            )
        else:
            # Insert new crew member
            conn.execute(
                """INSERT INTO crew (id, site, capabilities, resources_json, state,
                                     health_json, last_heartbeat, registered_at)
                   VALUES (?, ?, ?, ?, 'idle', ?, ?, ?)""",
                (host, site.name, capabilities, resources_json, health_json, now, now),
            )

        # Emit crew_added event
        events.emit(
            conn, "crew_added", host=host,
            message=f"Host {host} admitted (healthy)",
            data={"resources": report.resources},
        )

        conn.commit()

    except Exception:
        conn.rollback()
        raise


def list(conn: sqlite3.Connection) -> list[CrewMember]:
    """Return all crew members with parsed health/resources (§7, §9)."""
    rows = conn.execute(
        """SELECT id, site, capabilities, resources_json, state
           FROM crew ORDER BY id"""
    ).fetchall()

    members = []
    for row in rows:
        member = CrewMember(
            id=row[0],
            site=row[1],
            capabilities=json.loads(row[2]),
            resources=json.loads(row[3]),
            state=row[4],
        )
        members.append(member)

    return members


def drain(conn: sqlite3.Connection, host: str, now: Optional[float] = None) -> None:
    """Set a crew member's state to draining (§7, §9)."""
    now = _now(now)
    try:
        conn.execute(
            "UPDATE crew SET state='draining' WHERE id=?",
            (host,),
        )
        events.emit(
            conn, "crew_drained", host=host,
            message=f"Host {host} draining",
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def remove(conn: sqlite3.Connection, host: str) -> None:
    """Delete a crew member (§7, §9)."""
    try:
        conn.execute("DELETE FROM crew WHERE id=?", (host,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def heartbeat_sweep(
    conn: sqlite3.Connection,
    site,
    agent,
    now: Optional[float] = None,
) -> None:
    """Re-probe every crew member's health and apply transitions (§7, §9).

    For every crew member:
    - Re-probe site.health(host, agent)
    - Update health_json / last_heartbeat
    - Unreachable/unhealthy → state=down + requeue in-flight tickets (no penalty)
    - Previously-down + now healthy → re-admit (state=idle)
    - Renew live leases (leases.renew)
    - Reclaim expired leases (leases.reclaim_expired)
    - Un-park tickets of any class that regained capacity (queue.unpark_ready)

    Emits crew_health / crew_down as appropriate.

    Args:
        conn: SQLite connection
        site: Site implementing health
        agent: Agent for health checks
        now: Timestamp (default time.time())
    """
    now = _now(now)

    try:
        # Get all crew members
        rows = conn.execute(
            "SELECT id, state FROM crew ORDER BY id"
        ).fetchall()

        affected_classes = set()

        for host, old_state in rows:
            # Re-probe health
            report: HealthReport = site.health(host, agent)

            # Update health_json and last_heartbeat
            health_json = json.dumps({
                "reachable": report.reachable,
                "agent_ok": report.agent_ok,
                "auth_ok": report.auth_ok,
                "workspace_ready": report.workspace_ready,
                "guard_installed": report.guard_installed,
                "latency_ms": report.latency_ms,
            })
            resources_json = json.dumps(report.resources)

            # Determine new state
            if not report.ok:
                # Unreachable/unhealthy → down
                if old_state != "down":
                    # Transition to down
                    conn.execute(
                        """UPDATE crew SET state='down', health_json=?,
                           resources_json=?, last_heartbeat=? WHERE id=?""",
                        (health_json, resources_json, now, host),
                    )

                    # Requeue in-flight tickets (no penalty)
                    in_flight = conn.execute(
                        """SELECT id FROM tickets
                           WHERE worker_host=? AND state IN ('dispatched', 'running')""",
                        (host,),
                    ).fetchall()

                    for (ticket_id,) in in_flight:
                        # Load ticket for requeue_transport
                        ticket_row = conn.execute(
                            """SELECT id, run_id, phase, state, resource_req, priority,
                               attempts, payload_json FROM tickets WHERE id=?""",
                            (ticket_id,),
                        ).fetchone()
                        from engine.models import Ticket
                        ticket = Ticket(
                            id=ticket_row[0],
                            run_id=ticket_row[1],
                            phase=ticket_row[2],
                            state=ticket_row[3],
                            resource_req=ticket_row[4],
                            priority=ticket_row[5],
                            attempts=ticket_row[6],
                            payload=json.loads(ticket_row[7]),
                        )
                        # NO-commit helper: the whole sweep is one transaction
                        # committed once at the end. Calling the self-committing
                        # queue.requeue_transport here would flush earlier
                        # uncommitted sweep writes and break the rollback contract.
                        queue._requeue_transport_nocommit(conn, ticket, now=now)

                    # Mark class affected (for unpark_ready)
                    for res_class in site.resource_classes():
                        affected_classes.add(res_class)

                    # Emit crew_down event
                    events.emit(
                        conn, "crew_down", host=host,
                        message=f"Host {host} down (unreachable/unhealthy)",
                        data={"old_state": old_state},
                    )
                else:
                    # Already down; just update health
                    conn.execute(
                        """UPDATE crew SET health_json=?, resources_json=?,
                           last_heartbeat=? WHERE id=?""",
                        (health_json, resources_json, now, host),
                    )
            else:
                # Healthy
                if old_state == "down":
                    # Recovery: re-admit to idle
                    conn.execute(
                        """UPDATE crew SET state='idle', health_json=?,
                           resources_json=?, last_heartbeat=? WHERE id=?""",
                        (health_json, resources_json, now, host),
                    )

                    # Mark class affected (capacity regained)
                    for res_class in site.resource_classes():
                        affected_classes.add(res_class)

                    # Emit crew_health event (recovery)
                    events.emit(
                        conn, "crew_health", host=host,
                        message=f"Host {host} recovered (down → idle)",
                        data={"resources": report.resources},
                    )
                else:
                    # Already healthy; just update health
                    conn.execute(
                        """UPDATE crew SET health_json=?, resources_json=?,
                           last_heartbeat=? WHERE id=?""",
                        (health_json, resources_json, now, host),
                    )

        # Renew live leases
        live_leases = conn.execute(
            "SELECT id FROM leases WHERE expires_at > ?", (now,)
        ).fetchall()
        for (lease_id,) in live_leases:
            leases.renew(conn, lease_id, now=now)

        # Reclaim expired leases (also calls unpark_ready per class)
        leases.reclaim_expired(conn, now=now)

        # Un-park ready tickets for affected classes (capacity regained)
        for res_class in affected_classes:
            queue.unpark_ready(conn, res_class, now=now)

        conn.commit()

    except Exception:
        conn.rollback()
        raise
