"""Tests for the append-only event feed (engine.events).

TDD: write these FIRST, watch them fail for the expected reason,
then implement engine/events.py minimally.
"""
import json
import sqlite3
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def db_path():
    """Temporary db path for each test."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        path = f.name
    yield path
    # Cleanup
    Path(path).unlink(missing_ok=True)
    Path(f"{path}-shm").unlink(missing_ok=True)
    Path(f"{path}-wal").unlink(missing_ok=True)


@pytest.fixture
def conn(db_path):
    """Connection with migrations applied (real events table)."""
    from engine.db.migrate import apply_migrations, connect

    apply_migrations(db_path)
    connection = connect(db_path)
    yield connection
    connection.close()


def test_event_kinds_exposed():
    """EVENT_KINDS constant is exposed with the defined event kinds."""
    from engine.events import EVENT_KINDS

    # The engine emits these kinds
    expected_kinds = {
        "run_started", "run_paused", "run_resumed", "run_stopped", "run_done", "run_failed",
        "run_reopened",
        "ticket_claimed", "ticket_started", "result_recorded", "ticket_requeued",
        "ticket_parked", "ticket_failed", "ticket_abandoned", "ticket_reprioritized",
        "needs_human", "phase_advanced",
        "reduction_created", "reduction_accepted", "reduction_rejected",
        "crew_added", "crew_health", "crew_down", "crew_drained",
        "lease_acquired", "lease_reclaimed", "attention",
    }

    assert isinstance(EVENT_KINDS, (frozenset, set))
    assert expected_kinds == set(EVENT_KINDS)


def test_emit_appends_event_with_all_fields(conn):
    """emit appends one row with all fields set (caller owns commit)."""
    from engine.events import emit

    # Emit an event with all optional fields populated
    emit(
        conn,
        "ticket_claimed",
        run_id="run-123",
        ticket_id="run-123/t-0",
        host="worker-01",
        message="Claimed for processing",
        data={"priority": 10, "resource": "cpu"},
    )
    # Caller owns commit (emit does NOT commit)
    conn.commit()

    # Verify row inserted
    cursor = conn.cursor()
    cursor.execute("SELECT id, kind, run_id, ticket_id, host, message, data_json FROM events")
    row = cursor.fetchone()

    assert row is not None
    assert row[0] == 1  # id (autoincrement)
    assert row[1] == "ticket_claimed"
    assert row[2] == "run-123"
    assert row[3] == "run-123/t-0"
    assert row[4] == "worker-01"
    assert row[5] == "Claimed for processing"

    # data round-trips: dict → data_json → dict
    data_json = row[6]
    assert json.loads(data_json) == {"priority": 10, "resource": "cpu"}


def test_emit_appends_event_with_minimal_fields(conn):
    """emit appends event with only required fields (kind), rest None (caller owns commit)."""
    from engine.events import emit

    emit(conn, "run_started")
    conn.commit()

    cursor = conn.cursor()
    cursor.execute("SELECT kind, run_id, ticket_id, host, message, data_json FROM events")
    row = cursor.fetchone()

    assert row[0] == "run_started"
    assert row[1] is None  # run_id
    assert row[2] is None  # ticket_id
    assert row[3] is None  # host
    assert row[4] is None  # message
    # data_json defaults to '{}'
    assert json.loads(row[5]) == {}


def test_emit_sets_timestamp(conn):
    """emit sets ts (wall-clock epoch seconds, caller owns commit)."""
    import time
    from engine.events import emit

    before = time.time()
    emit(conn, "attention", message="test")
    conn.commit()
    after = time.time()

    cursor = conn.cursor()
    cursor.execute("SELECT ts FROM events")
    row = cursor.fetchone()

    # ts should be between before and after
    assert before <= row[0] <= after


def test_emit_data_defaults_to_empty_dict(conn):
    """emit with data=None stores '{}' in data_json (caller owns commit)."""
    from engine.events import emit

    emit(conn, "crew_added", data=None)
    conn.commit()

    cursor = conn.cursor()
    cursor.execute("SELECT data_json FROM events")
    row = cursor.fetchone()

    assert json.loads(row[0]) == {}


def test_emit_validates_kind_against_known_kinds(conn):
    """emit raises on unknown event kind."""
    from engine.events import emit

    # Should raise on an unknown kind
    with pytest.raises(ValueError, match="unknown.*kind"):
        emit(conn, "invalid_unknown_kind")


def test_since_returns_events_after_id_ascending(conn):
    """since returns events with id > after_id, ordered by id ascending (caller owns commit)."""
    from engine.events import emit, since

    # Insert 5 events
    for i in range(5):
        emit(conn, "run_started", run_id=f"run-{i}", message=f"Event {i}")
    conn.commit()

    # Query events after id=2
    rows = since(conn, after_id=2)

    # Should return events with id > 2 (i.e. id 3, 4, 5)
    assert len(rows) == 3
    assert rows[0]["id"] == 3
    assert rows[1]["id"] == 4
    assert rows[2]["id"] == 5

    # Verify ordering by id ascending
    ids = [r["id"] for r in rows]
    assert ids == sorted(ids)


def test_since_respects_limit(conn):
    """since respects the limit parameter (caller owns commit)."""
    from engine.events import emit, since

    # Insert 10 events
    for i in range(10):
        emit(conn, "run_started", message=f"Event {i}")
    conn.commit()

    # Query with limit=3
    rows = since(conn, after_id=0, limit=3)

    assert len(rows) == 3
    # First 3 events after id=0
    assert rows[0]["id"] == 1
    assert rows[1]["id"] == 2
    assert rows[2]["id"] == 3


def test_since_default_limit_200(conn):
    """since defaults to limit=200 (caller owns commit)."""
    from engine.events import emit, since

    # Insert 250 events
    for i in range(250):
        emit(conn, "attention")
    conn.commit()

    # Query without explicit limit
    rows = since(conn, after_id=0)

    # Should cap at default limit=200
    assert len(rows) == 200


def test_since_returns_rows_with_deserialized_data(conn):
    """since returns rows with data deserialized from data_json (caller owns commit)."""
    from engine.events import emit, since

    emit(conn, "ticket_claimed", data={"priority": 5, "attempts": 1})
    emit(conn, "run_started", data=None)
    conn.commit()

    rows = since(conn, after_id=0)

    assert len(rows) == 2
    # data field is deserialized dict
    assert rows[0]["data"] == {"priority": 5, "attempts": 1}
    assert rows[1]["data"] == {}


def test_tail_returns_last_n_events(conn):
    """tail returns the last n events (caller owns commit)."""
    from engine.events import emit, tail

    # Insert 10 events
    for i in range(10):
        emit(conn, "run_started", message=f"Event {i}")
    conn.commit()

    # Get last 3 events
    rows = tail(conn, n=3)

    assert len(rows) == 3
    # Last 3 events: id 8, 9, 10
    assert rows[0]["id"] == 8
    assert rows[1]["id"] == 9
    assert rows[2]["id"] == 10


def test_tail_handles_n_greater_than_total(conn):
    """tail handles n greater than total events (returns all, caller owns commit)."""
    from engine.events import emit, tail

    # Insert 3 events
    for i in range(3):
        emit(conn, "run_started")
    conn.commit()

    # Request last 10 events
    rows = tail(conn, n=10)

    # Should return all 3 events
    assert len(rows) == 3


def test_tail_returns_rows_with_deserialized_data(conn):
    """tail returns rows with data deserialized from data_json (caller owns commit)."""
    from engine.events import emit, tail

    emit(conn, "ticket_failed", data={"error": "timeout"})
    conn.commit()

    rows = tail(conn, n=1)

    assert len(rows) == 1
    assert rows[0]["data"] == {"error": "timeout"}


def test_events_feed_is_append_only_monotonic(conn):
    """Events feed is append-only and monotonic by id (caller owns commit)."""
    from engine.events import emit, since

    # Insert events
    emit(conn, "run_started")
    emit(conn, "ticket_claimed")
    emit(conn, "ticket_started")
    conn.commit()

    # Verify monotonic ordering
    rows = since(conn, after_id=0)
    ids = [r["id"] for r in rows]

    # IDs should be strictly increasing
    assert ids == [1, 2, 3]
    assert ids == sorted(ids)


def test_row_object_has_expected_fields(conn):
    """Rows returned by since/tail have expected fields from schema (caller owns commit)."""
    from engine.events import emit, since

    emit(
        conn,
        "crew_health",
        run_id="run-1",
        ticket_id=None,
        host="worker-1",
        message="Health check",
        data={"ok": True},
    )
    conn.commit()

    rows = since(conn, after_id=0)
    row = rows[0]

    # Verify all expected fields per schema
    assert "id" in row
    assert "ts" in row
    assert "kind" in row
    assert "run_id" in row
    assert "ticket_id" in row
    assert "host" in row
    assert "message" in row
    assert "data" in row  # deserialized from data_json

    # Verify values
    assert row["kind"] == "crew_health"
    assert row["run_id"] == "run-1"
    assert row["ticket_id"] is None
    assert row["host"] == "worker-1"
    assert row["message"] == "Health check"
    assert row["data"] == {"ok": True}


def test_since_with_kind_filter(conn):
    """since with kind parameter filters to that kind (caller owns commit)."""
    from engine.events import emit, since

    # Insert events of different kinds
    emit(conn, "ticket_claimed", run_id="run-1", message="Event 1")
    emit(conn, "result_recorded", run_id="run-1", message="Event 2")
    emit(conn, "ticket_claimed", run_id="run-1", message="Event 3")
    emit(conn, "phase_advanced", run_id="run-1", message="Event 4")
    emit(conn, "ticket_claimed", run_id="run-1", message="Event 5")
    conn.commit()

    # Query with kind filter
    rows = since(conn, after_id=0, kind="ticket_claimed")

    # Should only return ticket_claimed events
    assert len(rows) == 3
    assert all(r["kind"] == "ticket_claimed" for r in rows)
    assert rows[0]["message"] == "Event 1"
    assert rows[1]["message"] == "Event 3"
    assert rows[2]["message"] == "Event 5"


def test_since_kind_none_returns_all_kinds(conn):
    """since with kind=None returns all kinds (default behavior, caller owns commit)."""
    from engine.events import emit, since

    # Insert events of different kinds
    emit(conn, "ticket_claimed", message="Event 1")
    emit(conn, "result_recorded", message="Event 2")
    emit(conn, "phase_advanced", message="Event 3")
    conn.commit()

    # Query without kind filter (default None)
    rows = since(conn, after_id=0, kind=None)

    # Should return all events
    assert len(rows) == 3


def test_since_kind_with_limit(conn):
    """since with kind + limit bounds matched rows only (caller owns commit)."""
    from engine.events import emit, since

    # Insert 10 events: 5 ticket_claimed, 5 result_recorded (interleaved)
    for i in range(5):
        emit(conn, "ticket_claimed", message=f"Claimed {i}")
        emit(conn, "result_recorded", message=f"Recorded {i}")
    conn.commit()

    # Query with kind filter and limit
    rows = since(conn, after_id=0, kind="ticket_claimed", limit=2)

    # Should return at most 2 ticket_claimed events
    assert len(rows) == 2
    assert all(r["kind"] == "ticket_claimed" for r in rows)
