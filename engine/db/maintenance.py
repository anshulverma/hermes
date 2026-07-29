"""Database maintenance operations: prune, backup, vacuum.

Retention-safe pruning of unbounded-growth tables (events, attempts), WAL-aware
online backup, and vacuum for space reclamation. Operator-invoked only.

Presupposes an already-initialized DB (connects directly, not via cli._connect/apply_migrations).

Stdlib-only (sqlite3 only). PRUNE-SAFETY is paramount: never delete live/in-flight state.

Terminal ticket states: {done, failed} ONLY.
Terminal run states: {done, failed, stopped}.

Non-terminal ticket states (survive pruning): parked, needs_human, reducing, running, dispatched, queued.
"""
import os
import sqlite3
import sys
import time
from typing import Optional

from engine import log
from engine.db import migrate

logger = log.get_logger("db.maintenance")


def prune(
    db_path: str,
    events_older_than_days: int = 90,
    attempts_older_than_days: int = 90,
    run_id: Optional[str] = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Prune old events and attempts, safe from deleting live/in-flight state.

    One committed transaction. Per-row eligibility: deletable iff EVERY clause holds.

    Deletion rules:
    - attempts: ticket terminal AND run terminal AND ended_at NOT NULL AND ended_at < cutoff
    - events (non-null ticket_id): ticket terminal AND run terminal AND ts < cutoff
    - events (null ticket_id, non-null run_id): run terminal AND ts < cutoff
    - events (null run_id): ts < cutoff (fleet-wide events, age only)

    Terminal ticket = {done, failed}. Terminal run = {done, failed, stopped}.

    NEVER deletes:
    - Attempts on non-terminal tickets (parked, needs_human, reducing, running, dispatched, queued)
    - Attempts on non-terminal runs (running, paused)
    - Attempts with null ended_at (in-flight)
    - Events whose ticket_id/run_id no longer resolves (orphaned, conservative)

    Args:
        db_path: Path to queue.db
        events_older_than_days: Delete events older than this (default: 90)
        attempts_older_than_days: Delete attempts older than this (default: 90)
        run_id: Restrict to this run only (optional)
        dry_run: Report counts without deleting (default: False)

    Returns:
        Dict with keys {attempts, events} -> count deleted (or would-delete if dry_run)
    """
    conn = migrate.connect(db_path)
    try:
        events_cutoff = time.time() - (events_older_than_days * 86400)
        attempts_cutoff = time.time() - (attempts_older_than_days * 86400)

        # Build run filter clause
        run_filter = ""
        run_params = []
        if run_id:
            run_filter = " AND r.id = ?"
            run_params = [run_id]

        # --- Count/delete attempts ---
        # Clause: ticket terminal AND run terminal AND ended_at NOT NULL AND ended_at < cutoff
        attempts_select = f"""
            SELECT a.id FROM attempts a
            JOIN tickets t ON t.id = a.ticket_id
            JOIN runs r ON r.id = t.run_id
            WHERE t.state IN ('done', 'failed')
              AND r.state IN ('done', 'failed', 'stopped')
              AND a.ended_at IS NOT NULL
              AND a.ended_at < ?
              {run_filter}
        """

        params_attempts = [attempts_cutoff] + run_params
        attempts_ids = [row[0] for row in conn.execute(attempts_select, params_attempts).fetchall()]
        attempts_count = len(attempts_ids)

        if not dry_run and attempts_count > 0:
            placeholders = ",".join("?" for _ in attempts_ids)
            conn.execute(f"DELETE FROM attempts WHERE id IN ({placeholders})", attempts_ids)

        # --- Count/delete events ---
        # Four clauses:
        # (a) events with non-null ticket_id: ticket terminal AND run terminal AND ts < cutoff
        # (b) events with null ticket_id, non-null run_id: run terminal AND ts < cutoff
        # (c) events with null run_id: ts < cutoff

        # Clause (a): non-null ticket_id
        events_select_a = f"""
            SELECT e.id FROM events e
            JOIN tickets t ON t.id = e.ticket_id
            JOIN runs r ON r.id = t.run_id
            WHERE e.ticket_id IS NOT NULL
              AND t.state IN ('done', 'failed')
              AND r.state IN ('done', 'failed', 'stopped')
              AND e.ts < ?
              {run_filter}
        """
        params_events_a = [events_cutoff] + run_params
        events_ids_a = [row[0] for row in conn.execute(events_select_a, params_events_a).fetchall()]

        # Clause (b): null ticket_id, non-null run_id
        events_select_b = f"""
            SELECT e.id FROM events e
            JOIN runs r ON r.id = e.run_id
            WHERE e.ticket_id IS NULL
              AND e.run_id IS NOT NULL
              AND r.state IN ('done', 'failed', 'stopped')
              AND e.ts < ?
              {run_filter}
        """
        params_events_b = [events_cutoff] + run_params
        events_ids_b = [row[0] for row in conn.execute(events_select_b, params_events_b).fetchall()]

        # Clause (c): null run_id (fleet-wide)
        if run_id:
            # If run_id filter is active, skip null-run_id events
            events_ids_c = []
        else:
            events_select_c = "SELECT id FROM events WHERE run_id IS NULL AND ts < ?"
            events_ids_c = [row[0] for row in conn.execute(events_select_c, [events_cutoff]).fetchall()]

        # Combine all event IDs
        all_event_ids = set(events_ids_a) | set(events_ids_b) | set(events_ids_c)
        events_count = len(all_event_ids)

        if not dry_run and events_count > 0:
            placeholders = ",".join("?" for _ in all_event_ids)
            conn.execute(f"DELETE FROM events WHERE id IN ({placeholders})", list(all_event_ids))

        # Commit if not dry-run
        if not dry_run:
            conn.commit()

        # Log summary
        if dry_run:
            logger.info(
                "Prune dry-run: would delete %d attempts, %d events",
                attempts_count,
                events_count,
            )
        else:
            logger.info(
                "Pruned %d attempts, %d events",
                attempts_count,
                events_count,
            )

        return {"attempts": attempts_count, "events": events_count}

    finally:
        conn.close()


def backup(db_path: str, output_path: str) -> None:
    """Create an online backup of the database using SQLite backup API.

    Safe to run while the database is in use (WAL-aware). Output file is chmod 0600.

    Args:
        db_path: Path to source queue.db
        output_path: Path to backup file to create
    """
    source_conn = migrate.connect(db_path)
    try:
        # Create destination connection
        dest_conn = sqlite3.connect(output_path)
        try:
            # Perform online backup
            source_conn.backup(dest_conn)
            dest_conn.close()
        except Exception:
            dest_conn.close()
            raise

        # Ensure output is mode 0600
        os.chmod(output_path, 0o600)

        logger.info("Backup created: %s", output_path)

    finally:
        source_conn.close()


def vacuum(db_path: str) -> None:
    """Vacuum the database to reclaim space.

    Performs WAL checkpoint before VACUUM to ensure consistency.

    Args:
        db_path: Path to queue.db
    """
    conn = migrate.connect(db_path)
    try:
        # WAL checkpoint
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        # VACUUM (must be outside transaction)
        conn.isolation_level = None
        conn.execute("VACUUM")

        logger.info("Vacuum completed")

    finally:
        conn.close()


def cmd_db(args):
    """Handler for 'hermes db' subcommands (prune, backup, vacuum)."""
    from engine import config

    home = config.resolve_home()
    db_path = str(home / "queue.db")

    if args.db_action == "prune":
        events_days = getattr(args, "events_older_than", 90)
        attempts_days = getattr(args, "attempts_older_than", 90)
        run_id = getattr(args, "run", None)
        dry_run = getattr(args, "dry_run", False)

        counts = prune(
            db_path,
            events_older_than_days=events_days,
            attempts_older_than_days=attempts_days,
            run_id=run_id,
            dry_run=dry_run,
        )

        if dry_run:
            print(f"Dry-run: would delete {counts['attempts']} attempts, {counts['events']} events")
        else:
            print(f"Pruned {counts['attempts']} attempts, {counts['events']} events")

        return 0

    elif args.db_action == "backup":
        output_path = args.out
        backup(db_path, output_path)
        print(f"Backup created: {output_path}")
        return 0

    elif args.db_action == "vacuum":
        vacuum(db_path)
        print("Vacuum completed")
        return 0

    else:
        print(f"Unknown db action: {args.db_action}", file=sys.stderr)
        return 1
