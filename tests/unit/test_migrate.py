"""
Unit tests for engine/db/migrate.py — idempotent migrations, connection setup, schema validation.

Per §4 spec: all tables + indexes from engine-core.md §4, PRAGMAs enforced, file mode 0600.
"""
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest


def test_apply_migrations_creates_all_tables(tmp_path):
    """On a fresh db, apply_migrations creates every table listed in spec §4."""
    from engine.db.migrate import apply_migrations

    db_path = tmp_path / "queue.db"
    apply_migrations(str(db_path))

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Query sqlite_master for all tables (excluding sqlite_sequence, an internal table)
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name != 'sqlite_sequence'
        ORDER BY name
    """)
    tables = [row[0] for row in cursor.fetchall()]

    expected_tables = [
        'attempts',
        'crew',
        'events',
        'findings',
        'leases',
        'reductions',
        'runs',
        'schema_migrations',
        'tickets',
    ]

    assert tables == expected_tables, f"Expected {expected_tables}, got {tables}"
    conn.close()


def test_apply_migrations_creates_all_indexes(tmp_path):
    """Assert all named indexes from spec §4 are created."""
    from engine.db.migrate import apply_migrations

    db_path = tmp_path / "queue.db"
    apply_migrations(str(db_path))

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Query sqlite_master for all indexes (excluding auto-created ones)
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='index' AND name NOT LIKE 'sqlite_autoindex_%'
        ORDER BY name
    """)
    indexes = [row[0] for row in cursor.fetchall()]

    expected_indexes = [
        'idx_attempts_ticket',
        'idx_events_stream',
        'idx_findings_run',
        'idx_tickets_dispatch',
        'idx_tickets_resource',
    ]

    assert indexes == expected_indexes, f"Expected {expected_indexes}, got {indexes}"
    conn.close()


def test_apply_migrations_is_idempotent(tmp_path):
    """Re-applying migrations is a no-op: no error, no duplicate rows."""
    from engine.db.migrate import apply_migrations

    db_path = tmp_path / "queue.db"

    # Apply once
    apply_migrations(str(db_path))

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM schema_migrations")
    count_after_first = cursor.fetchone()[0]
    conn.close()

    # Apply again
    apply_migrations(str(db_path))

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM schema_migrations")
    count_after_second = cursor.fetchone()[0]
    conn.close()

    assert count_after_first == count_after_second, "Migrations not idempotent"
    assert count_after_first > 0, "No migrations recorded"


def test_apply_migrations_records_version(tmp_path):
    """schema_migrations records the applied version(s)."""
    from engine.db.migrate import apply_migrations

    db_path = tmp_path / "queue.db"
    apply_migrations(str(db_path))

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT version, description FROM schema_migrations ORDER BY version")
    rows = cursor.fetchall()
    conn.close()

    assert len(rows) >= 1, "No migration versions recorded"
    # Version 1 is the initial schema
    assert rows[0][0] == 1, f"First version should be 1, got {rows[0][0]}"
    assert rows[0][1] is not None, "Description should be present"


def test_apply_migrations_applied_at_uses_wall_clock_epoch(tmp_path):
    """schema_migrations.applied_at uses wall-clock epoch (time.time(), not os.times().elapsed)."""
    import time
    from engine.db.migrate import apply_migrations

    db_path = tmp_path / "queue.db"
    before = time.time()
    apply_migrations(str(db_path))
    after = time.time()

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT applied_at FROM schema_migrations WHERE version = 1")
    applied_at = cursor.fetchone()[0]
    conn.close()

    # applied_at should be wall-clock epoch seconds, not process elapsed time
    assert before <= applied_at <= after, \
        f"applied_at {applied_at} not between {before} and {after} (wall-clock epoch)"


def test_connect_sets_file_mode_0600(tmp_path):
    """connect() ensures the db file is mode 0600."""
    from engine.db.migrate import connect

    db_path = tmp_path / "queue.db"
    conn = connect(str(db_path))
    conn.close()

    mode = os.stat(db_path).st_mode & 0o777
    assert mode == 0o600, f"Expected mode 0600, got {oct(mode)}"


def test_connect_sets_pragmas(tmp_path):
    """connect() sets the required PRAGMAs from spec §4."""
    from engine.db.migrate import connect

    db_path = tmp_path / "queue.db"
    conn = connect(str(db_path))
    cursor = conn.cursor()

    # journal_mode=WAL
    cursor.execute("PRAGMA journal_mode")
    journal_mode = cursor.fetchone()[0].lower()
    assert journal_mode == "wal", f"Expected WAL, got {journal_mode}"

    # synchronous=NORMAL
    cursor.execute("PRAGMA synchronous")
    synchronous = cursor.fetchone()[0]
    assert synchronous == 1, f"Expected 1 (NORMAL), got {synchronous}"

    # foreign_keys=ON
    cursor.execute("PRAGMA foreign_keys")
    foreign_keys = cursor.fetchone()[0]
    assert foreign_keys == 1, f"Expected 1 (ON), got {foreign_keys}"

    # busy_timeout=5000
    cursor.execute("PRAGMA busy_timeout")
    busy_timeout = cursor.fetchone()[0]
    assert busy_timeout == 5000, f"Expected 5000, got {busy_timeout}"

    conn.close()


def test_apply_migrations_sets_file_mode_0600(tmp_path):
    """apply_migrations ensures the db file is mode 0600."""
    from engine.db.migrate import apply_migrations

    db_path = tmp_path / "queue.db"
    apply_migrations(str(db_path))

    mode = os.stat(db_path).st_mode & 0o777
    assert mode == 0o600, f"Expected mode 0600, got {oct(mode)}"


def test_tickets_table_has_reduction_id_fk(tmp_path):
    """tickets.reduction_id is an INTEGER FK to reductions.id (spec §4)."""
    from engine.db.migrate import apply_migrations

    db_path = tmp_path / "queue.db"
    apply_migrations(str(db_path))

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Check tickets schema includes reduction_id
    cursor.execute("PRAGMA table_info(tickets)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}  # name: type

    assert 'reduction_id' in columns, "tickets.reduction_id column missing"
    assert columns['reduction_id'].upper() == 'INTEGER', \
        f"reduction_id should be INTEGER, got {columns['reduction_id']}"

    # Check FK constraint exists
    cursor.execute("PRAGMA foreign_key_list(tickets)")
    fks = cursor.fetchall()
    reduction_fk = [fk for fk in fks if fk[3] == 'reduction_id']

    assert len(reduction_fk) == 1, "tickets.reduction_id FK constraint missing"
    assert reduction_fk[0][2] == 'reductions', \
        f"reduction_id should reference reductions, got {reduction_fk[0][2]}"

    conn.close()


def test_state_check_constraints_enforced(tmp_path):
    """CHECK constraints on state columns reject invalid values."""
    from engine.db.migrate import apply_migrations

    db_path = tmp_path / "queue.db"
    apply_migrations(str(db_path))

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Insert a valid run
    cursor.execute("""
        INSERT INTO runs (id, playbook, site, base_ref, state, created_at, updated_at)
        VALUES ('test-run', 'test', 'local', 'main', 'running', 0, 0)
    """)

    # Try to insert a ticket with invalid state
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute("""
            INSERT INTO tickets (id, run_id, phase, state, created_at, updated_at)
            VALUES ('test-run/t-1', 'test-run', 'work', 'invalid_state', 0, 0)
        """)

    # Try to insert a run with invalid state
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute("""
            INSERT INTO runs (id, playbook, site, base_ref, state, created_at, updated_at)
            VALUES ('test-run-2', 'test', 'local', 'main', 'invalid_state', 0, 0)
        """)

    conn.close()
