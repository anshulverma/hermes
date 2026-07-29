"""Tests for engine.db.maintenance — prune/backup/vacuum.

TDD: written FIRST, watched fail, then engine/db/maintenance.py implemented.
Prune-safety is paramount: never delete live/in-flight state.

Terminal ticket = {done,failed} ONLY (parked/needs_human/reducing/running/dispatched/queued are NOT terminal).
Terminal run = {done,failed,stopped}.
"""
from __future__ import annotations

import json
import os
import sqlite3
import stat
import tempfile
import time
from pathlib import Path

import pytest

from engine import queue, events
from engine.db import maintenance, migrate
from engine.models import Result, Run, Ticket


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
    migrate.apply_migrations(db_path)
    connection = migrate.connect(db_path)
    yield connection
    connection.close()


# --- helpers -------------------------------------------------------------

def _mk_run(conn, run_id="r1", state="running", phase="work"):
    conn.execute(
        """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                             phase, created_at, updated_at)
           VALUES (?, 'stub', 'stub', 'main', '{}', ?, ?, 0, 0)""",
        (run_id, state, phase),
    )
    conn.commit()


def _mk_ticket(
    conn,
    ticket_id,
    run_id="r1",
    state="queued",
    phase="work",
):
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority,
                                attempts, available_at, tried_hosts,
                                payload_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'cpu', 0, 0, 0, '[]', '{}', 0, 0)""",
        (ticket_id, run_id, phase, state),
    )
    conn.commit()


def _mk_attempt(
    conn,
    ticket_id,
    phase="work",
    host="host1",
    attempt=1,
    started_at=None,
    ended_at=None,
    outcome="ok",
):
    conn.execute(
        """INSERT INTO attempts (ticket_id, phase, host, attempt, started_at,
                                 ended_at, outcome, termination_reason)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'goal_met')""",
        (ticket_id, phase, host, attempt, started_at, ended_at, outcome),
    )
    conn.commit()


def _mk_event(
    conn,
    ts,
    kind="ticket_claimed",
    run_id=None,
    ticket_id=None,
):
    conn.execute(
        """INSERT INTO events (ts, kind, run_id, ticket_id, data_json)
           VALUES (?, ?, ?, ?, '{}')""",
        (ts, kind, run_id, ticket_id),
    )
    conn.commit()


def _count_rows(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# --- prune tests ---------------------------------------------------------

def test_prune_deletes_only_fully_terminal_aged_rows(conn, db_path):
    """Prune deletes only rows whose run AND ticket are BOTH terminal and past cutoff."""
    now = time.time()
    old = now - 100 * 86400  # 100 days ago

    # Run1: done (terminal)
    _mk_run(conn, "r1", state="done")
    _mk_ticket(conn, "r1/t1", "r1", state="done")
    _mk_attempt(conn, "r1/t1", started_at=old, ended_at=old)
    _mk_event(conn, old, run_id="r1", ticket_id="r1/t1")

    # Run2: stopped (terminal)
    _mk_run(conn, "r2", state="stopped")
    _mk_ticket(conn, "r2/t1", "r2", state="failed")
    _mk_attempt(conn, "r2/t1", started_at=old, ended_at=old)
    _mk_event(conn, old, run_id="r2", ticket_id="r2/t1")

    # Run3: running (NOT terminal) - should NOT be deleted
    _mk_run(conn, "r3", state="running")
    _mk_ticket(conn, "r3/t1", "r3", state="done")
    _mk_attempt(conn, "r3/t1", started_at=old, ended_at=old)
    _mk_event(conn, old, run_id="r3", ticket_id="r3/t1")

    # Prune with 90-day cutoff
    maintenance.prune(db_path, events_older_than_days=90, attempts_older_than_days=90)

    # Verify: r1 and r2 (both terminal) should be pruned; r3 (running) should survive
    assert _count_rows(conn, "attempts") == 1  # r3/t1 survives
    assert _count_rows(conn, "events") == 1    # r3 event survives


def test_prune_never_deletes_non_terminal_ticket_rows(conn, db_path):
    """Prune NEVER deletes rows on non-terminal tickets (parked, needs_human, running, etc.)."""
    now = time.time()
    old = now - 100 * 86400

    # Run: done (terminal)
    _mk_run(conn, "r1", state="done")

    # Ticket states that are NOT terminal: parked, needs_human, reducing, running, dispatched, queued
    for state in ["parked", "needs_human", "reducing", "running", "dispatched", "queued"]:
        tid = f"r1/{state}"
        _mk_ticket(conn, tid, "r1", state=state)
        _mk_attempt(conn, tid, started_at=old, ended_at=old)
        _mk_event(conn, old, run_id="r1", ticket_id=tid)

    # Prune
    maintenance.prune(db_path, events_older_than_days=90, attempts_older_than_days=90)

    # All rows should survive (tickets are not terminal)
    assert _count_rows(conn, "attempts") == 6
    assert _count_rows(conn, "events") == 6


def test_prune_never_deletes_null_ended_at_attempts(conn, db_path):
    """Prune NEVER deletes attempts with null ended_at (in-flight)."""
    now = time.time()
    old = now - 100 * 86400

    # Run + ticket: both terminal
    _mk_run(conn, "r1", state="done")
    _mk_ticket(conn, "r1/t1", "r1", state="done")

    # Attempt with null ended_at (in-flight)
    _mk_attempt(conn, "r1/t1", started_at=old, ended_at=None)

    # Prune
    maintenance.prune(db_path, events_older_than_days=90, attempts_older_than_days=90)

    # Attempt should survive
    assert _count_rows(conn, "attempts") == 1


def test_prune_trap_stopped_run_with_running_ticket(conn, db_path):
    """TRAP: stopped run owning a still-running/dispatched ticket -> its rows SURVIVE."""
    now = time.time()
    old = now - 100 * 86400

    # Run: stopped (terminal)
    _mk_run(conn, "r1", state="stopped")

    # Ticket: still running (NOT terminal)
    _mk_ticket(conn, "r1/t1", "r1", state="running")
    _mk_attempt(conn, "r1/t1", started_at=old, ended_at=old)
    _mk_event(conn, old, run_id="r1", ticket_id="r1/t1")

    # Prune
    maintenance.prune(db_path, events_older_than_days=90, attempts_older_than_days=90)

    # All rows should survive (ticket is not terminal)
    assert _count_rows(conn, "attempts") == 1
    assert _count_rows(conn, "events") == 1


def test_prune_null_run_id_events_pruned_by_age_only(conn, db_path):
    """Events with null run_id (fleet-wide) are pruned purely by age."""
    now = time.time()
    old = now - 100 * 86400
    recent = now - 50 * 86400

    # Fleet-wide events (null run_id)
    _mk_event(conn, old, kind="crew_added", run_id=None, ticket_id=None)
    _mk_event(conn, recent, kind="crew_added", run_id=None, ticket_id=None)

    # Prune with 90-day cutoff
    maintenance.prune(db_path, events_older_than_days=90, attempts_older_than_days=90)

    # Old event deleted, recent survives
    assert _count_rows(conn, "events") == 1


def test_prune_run_scope_events_need_run_terminal(conn, db_path):
    """Events with non-null run_id, null ticket_id need run terminal."""
    now = time.time()
    old = now - 100 * 86400

    # Run: running (NOT terminal)
    _mk_run(conn, "r1", state="running")
    _mk_event(conn, old, kind="phase_advanced", run_id="r1", ticket_id=None)

    # Run: done (terminal)
    _mk_run(conn, "r2", state="done")
    _mk_event(conn, old, kind="phase_advanced", run_id="r2", ticket_id=None)

    # Prune
    maintenance.prune(db_path, events_older_than_days=90, attempts_older_than_days=90)

    # r1 event survives (run not terminal), r2 event deleted
    assert _count_rows(conn, "events") == 1
    remaining = conn.execute("SELECT run_id FROM events").fetchone()[0]
    assert remaining == "r1"


def test_prune_dry_run_deletes_nothing(conn, db_path):
    """Dry-run reports counts but deletes nothing."""
    now = time.time()
    old = now - 100 * 86400

    # Run + ticket: both terminal
    _mk_run(conn, "r1", state="done")
    _mk_ticket(conn, "r1/t1", "r1", state="done")
    _mk_attempt(conn, "r1/t1", started_at=old, ended_at=old)
    _mk_event(conn, old, run_id="r1", ticket_id="r1/t1")

    initial_attempts = _count_rows(conn, "attempts")
    initial_events = _count_rows(conn, "events")

    # Dry-run prune
    counts = maintenance.prune(db_path, events_older_than_days=90, attempts_older_than_days=90, dry_run=True)

    # Nothing deleted
    assert _count_rows(conn, "attempts") == initial_attempts
    assert _count_rows(conn, "events") == initial_events

    # But counts should reflect what would be deleted
    assert counts["attempts"] > 0 or counts["events"] > 0


def test_prune_run_scope_restricts_to_run(conn, db_path):
    """--run R restricts prune to that run only."""
    now = time.time()
    old = now - 100 * 86400

    # Run1: done
    _mk_run(conn, "r1", state="done")
    _mk_ticket(conn, "r1/t1", "r1", state="done")
    _mk_attempt(conn, "r1/t1", started_at=old, ended_at=old)
    _mk_event(conn, old, run_id="r1", ticket_id="r1/t1")

    # Run2: done
    _mk_run(conn, "r2", state="done")
    _mk_ticket(conn, "r2/t1", "r2", state="done")
    _mk_attempt(conn, "r2/t1", started_at=old, ended_at=old)
    _mk_event(conn, old, run_id="r2", ticket_id="r2/t1")

    # Prune only r1
    maintenance.prune(db_path, events_older_than_days=90, attempts_older_than_days=90, run_id="r1")

    # r1 deleted, r2 survives
    assert _count_rows(conn, "attempts") == 1
    assert _count_rows(conn, "events") == 1
    remaining = conn.execute("SELECT ticket_id FROM attempts").fetchone()[0]
    assert remaining == "r2/t1"


def test_prune_different_cutoffs_for_events_and_attempts(conn, db_path):
    """Different cutoffs for events and attempts."""
    now = time.time()
    old_events = now - 100 * 86400
    old_attempts = now - 50 * 86400

    # Run + ticket: both terminal
    _mk_run(conn, "r1", state="done")
    _mk_ticket(conn, "r1/t1", "r1", state="done")
    _mk_attempt(conn, "r1/t1", started_at=old_attempts, ended_at=old_attempts)
    _mk_event(conn, old_events, run_id="r1", ticket_id="r1/t1")

    # Prune with events_older_than=90, attempts_older_than=30
    maintenance.prune(db_path, events_older_than_days=90, attempts_older_than_days=30)

    # Event deleted (100 days > 90), attempt survives (50 days < 30 is false, so deleted)
    # Actually 50 > 30, so both deleted
    assert _count_rows(conn, "attempts") == 0
    assert _count_rows(conn, "events") == 0


def test_prune_events_whose_ticket_no_longer_exists_not_deleted(conn, db_path):
    """Events with ticket_id that no longer resolves (orphaned) are NOT deleted (conservative)."""
    now = time.time()
    old = now - 100 * 86400

    # Event with ticket_id that doesn't exist
    _mk_event(conn, old, run_id="r1", ticket_id="r1/orphan")

    # Prune
    maintenance.prune(db_path, events_older_than_days=90, attempts_older_than_days=90)

    # Event survives (conservative: no ticket match means no deletion)
    assert _count_rows(conn, "events") == 1


# --- backup tests --------------------------------------------------------

def test_backup_produces_valid_db(conn, db_path):
    """Backup produces a file that opens, has identical schema and row counts."""
    # Seed some data
    _mk_run(conn, "r1", state="done")
    _mk_ticket(conn, "r1/t1", "r1", state="done")
    _mk_attempt(conn, "r1/t1", started_at=0, ended_at=0)
    _mk_event(conn, 0, run_id="r1", ticket_id="r1/t1")

    # Get source row counts
    source_runs = _count_rows(conn, "runs")
    source_tickets = _count_rows(conn, "tickets")
    source_attempts = _count_rows(conn, "attempts")
    source_events = _count_rows(conn, "events")

    # Backup
    with tempfile.NamedTemporaryFile(delete=False, suffix="-backup.db") as f:
        backup_path = f.name

    try:
        maintenance.backup(db_path, backup_path)

        # Verify backup file exists and opens
        assert Path(backup_path).exists()
        backup_conn = migrate.connect(backup_path)

        # Verify schema (re-apply migrations should be NO-OP)
        initial_versions = set(
            r[0] for r in backup_conn.execute("SELECT version FROM schema_migrations").fetchall()
        )
        migrate.apply_migrations(backup_path)
        backup_conn.close()
        backup_conn = migrate.connect(backup_path)
        final_versions = set(
            r[0] for r in backup_conn.execute("SELECT version FROM schema_migrations").fetchall()
        )
        assert initial_versions == final_versions  # No new migrations applied

        # Verify identical row counts
        assert _count_rows(backup_conn, "runs") == source_runs
        assert _count_rows(backup_conn, "tickets") == source_tickets
        assert _count_rows(backup_conn, "attempts") == source_attempts
        assert _count_rows(backup_conn, "events") == source_events

        backup_conn.close()
    finally:
        for suffix in ("", "-shm", "-wal"):
            Path(f"{backup_path}{suffix}").unlink(missing_ok=True)


def test_backup_mode_0600(conn, db_path):
    """Backup output is mode 0600."""
    with tempfile.NamedTemporaryFile(delete=False, suffix="-backup.db") as f:
        backup_path = f.name

    try:
        maintenance.backup(db_path, backup_path)

        # Verify mode
        file_stat = Path(backup_path).stat()
        file_mode = stat.S_IMODE(file_stat.st_mode)
        assert file_mode == 0o600
    finally:
        for suffix in ("", "-shm", "-wal"):
            Path(f"{backup_path}{suffix}").unlink(missing_ok=True)


def test_backup_wal_safe_while_connection_open(conn, db_path):
    """Backup taken while a connection is open is WAL-safe."""
    # Write some data
    _mk_run(conn, "r1", state="running")

    # Backup while conn is still open
    with tempfile.NamedTemporaryFile(delete=False, suffix="-backup.db") as f:
        backup_path = f.name

    try:
        maintenance.backup(db_path, backup_path)

        # Verify backup has the data
        backup_conn = migrate.connect(backup_path)
        assert _count_rows(backup_conn, "runs") == 1
        backup_conn.close()
    finally:
        for suffix in ("", "-shm", "-wal"):
            Path(f"{backup_path}{suffix}").unlink(missing_ok=True)


# --- vacuum tests --------------------------------------------------------

def test_vacuum_runs_clean(conn, db_path):
    """Vacuum runs without error."""
    # Seed and delete some data to create free pages
    _mk_run(conn, "r1", state="done")
    _mk_ticket(conn, "r1/t1", "r1", state="done")
    conn.execute("DELETE FROM tickets WHERE id='r1/t1'")
    conn.commit()

    # Vacuum
    maintenance.vacuum(db_path)

    # Verify database still works
    assert _count_rows(conn, "runs") == 1
