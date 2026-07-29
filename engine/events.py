"""
engine.events — append-only event feed.



Stdlib-only (sqlite3 + json + time). Events are append-only, monotonic by id.
"""
import json
import sqlite3
import time
from typing import Any, Optional


# Event kinds the engine emits
EVENT_KINDS = frozenset({
    "run_started", "run_paused", "run_resumed", "run_stopped", "run_done", "run_failed",
    "ticket_claimed", "ticket_started", "result_recorded", "ticket_requeued",
    "ticket_parked", "ticket_failed", "needs_human", "phase_advanced",
    "reduction_created", "reduction_accepted", "reduction_rejected",
    "crew_added", "crew_health", "crew_down", "crew_drained",
    "lease_acquired", "lease_reclaimed", "attention",
})


def emit(
    conn: sqlite3.Connection,
    kind: str,
    *,
    run_id: Optional[str] = None,
    ticket_id: Optional[str] = None,
    host: Optional[str] = None,
    message: Optional[str] = None,
    data: Optional[dict] = None,
) -> None:
    """
    Append one event to the events table within the caller's transaction.

    The CALLER owns commit. This is critical for atomicity: the queue
    runs claim_ticket under BEGIN IMMEDIATE and treats record_result as one
    atomic unit that emits multiple events. A mid-unit commit breaks atomicity.

    Args:
        conn: SQLite connection
        kind: Event kind (must be in EVENT_KINDS)
        run_id: Optional run ID
        ticket_id: Optional ticket ID
        host: Optional host identifier
        message: Optional human-readable message
        data: Optional dict; serialized to data_json (defaults to {})

    Raises:
        ValueError: If kind is not in EVENT_KINDS
    """
    # Validate kind
    if kind not in EVENT_KINDS:
        raise ValueError(f"unknown event kind: {kind!r}")

    # Set ts (wall-clock epoch seconds)
    ts = time.time()

    # Serialize data (default to empty dict)
    if data is None:
        data = {}
    data_json = json.dumps(data, separators=(',', ':'), sort_keys=True)

    # Insert event (caller owns commit)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO events (ts, kind, run_id, ticket_id, host, message, data_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (ts, kind, run_id, ticket_id, host, message, data_json),
    )


def since(conn: sqlite3.Connection, after_id: int, limit: int = 200, kind: Optional[str] = None) -> list[dict]:
    """
    Return events with id > after_id, ordered by id ascending.

    For polling the feed.

    Args:
        conn: SQLite connection
        after_id: Return only events with id > after_id
        limit: Max number of rows to return (default 200)
        kind: Optional event kind filter (default None = all kinds)

    Returns:
        List of event dicts with data deserialized from data_json.
        Each dict has keys: id, ts, kind, run_id, ticket_id, host, message, data.
    """
    cursor = conn.cursor()

    # Build parametrized query with optional kind filter
    if kind is None:
        cursor.execute(
            """
            SELECT id, ts, kind, run_id, ticket_id, host, message, data_json
            FROM events
            WHERE id > ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (after_id, limit),
        )
    else:
        cursor.execute(
            """
            SELECT id, ts, kind, run_id, ticket_id, host, message, data_json
            FROM events
            WHERE id > ? AND kind = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (after_id, kind, limit),
        )

    rows = []
    for row in cursor.fetchall():
        event = {
            "id": row[0],
            "ts": row[1],
            "kind": row[2],
            "run_id": row[3],
            "ticket_id": row[4],
            "host": row[5],
            "message": row[6],
            "data": json.loads(row[7]) if row[7] else {},
        }
        rows.append(event)

    return rows


def tail(conn: sqlite3.Connection, n: int) -> list[dict]:
    """
    Return the last n events (for the CLI).

    Args:
        conn: SQLite connection
        n: Number of events to return

    Returns:
        List of event dicts with data deserialized from data_json.
        Each dict has keys: id, ts, kind, run_id, ticket_id, host, message, data.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, ts, kind, run_id, ticket_id, host, message, data_json
        FROM events
        ORDER BY id DESC
        LIMIT ?
        """,
        (n,),
    )

    # Reverse to get chronological order (oldest to newest)
    rows = []
    for row in reversed(cursor.fetchall()):
        event = {
            "id": row[0],
            "ts": row[1],
            "kind": row[2],
            "run_id": row[3],
            "ticket_id": row[4],
            "host": row[5],
            "message": row[6],
            "data": json.loads(row[7]) if row[7] else {},
        }
        rows.append(event)

    return rows
