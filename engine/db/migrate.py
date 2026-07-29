"""
engine.db.migrate — idempotent additive migration runner + connect().

Stdlib-only (sqlite3 only). Migrations are additive-only, tracked in schema_migrations.
File mode enforced to 0600. PRAGMAs from spec §4.
"""
import os
import sqlite3
from pathlib import Path
from typing import Optional


def connect(path: str) -> sqlite3.Connection:
    """
    Open a SQLite connection with spec §4 PRAGMAs and ensure file mode 0600.

    PRAGMAs: journal_mode=WAL, synchronous=NORMAL, busy_timeout=5000, foreign_keys=ON.
    Creates the file if it doesn't exist, then chmods to 0600.

    Args:
        path: Path to the SQLite db file

    Returns:
        Open connection with PRAGMAs set
    """
    # Create parent directory if needed
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Touch file if it doesn't exist (so we can chmod it)
    if not db_path.exists():
        db_path.touch()

    # Ensure mode 0600
    os.chmod(db_path, 0o600)

    # Open connection
    conn = sqlite3.connect(str(db_path))

    # Set PRAGMAs (spec §4)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA foreign_keys=ON")

    return conn


def apply_migrations(path: str) -> None:
    """
    Apply all pending migrations idempotently.

    On a fresh db, creates all tables + indexes and records version 1.
    Re-applying is a no-op (checks schema_migrations).
    Ensures file mode 0600.

    Args:
        path: Path to the SQLite db file
    """
    conn = connect(path)
    cursor = conn.cursor()

    try:
        # Check if schema_migrations table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='schema_migrations'
        """)
        migrations_table_exists = cursor.fetchone() is not None

        if not migrations_table_exists:
            # Fresh db - create schema_migrations first
            cursor.execute("""
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at REAL,
                    description TEXT
                )
            """)
            conn.commit()

        # Check what versions are already applied
        cursor.execute("SELECT version FROM schema_migrations ORDER BY version")
        applied_versions = {row[0] for row in cursor.fetchall()}

        # Migration 1: initial schema from spec §4
        if 1 not in applied_versions:
            _apply_migration_1(conn)
            cursor.execute("""
                INSERT INTO schema_migrations (version, applied_at, description)
                VALUES (1, ?, 'Initial schema from engine-core.md §4')
            """, (float(os.times().elapsed),))
            conn.commit()

    finally:
        conn.close()

    # Ensure file mode 0600 after migrations
    os.chmod(path, 0o600)


def _apply_migration_1(conn: sqlite3.Connection) -> None:
    """
    Apply migration 1: full initial schema from spec §4.

    Reads schema.sql and executes it. The file includes all tables,
    CHECK constraints, FKs, and indexes.
    """
    # Load schema.sql relative to this module
    schema_path = Path(__file__).parent / "schema.sql"
    schema_sql = schema_path.read_text()

    cursor = conn.cursor()

    # Split by semicolons and execute each statement
    # (executescript doesn't work well with our setup, so we parse manually)
    statements = []
    current = []
    for line in schema_sql.splitlines():
        stripped = line.strip()

        # Skip comments and empty lines
        if not stripped or stripped.startswith('--'):
            continue

        current.append(line)

        # Statement ends with semicolon
        if stripped.endswith(';'):
            stmt = '\n'.join(current)
            statements.append(stmt)
            current = []

    # Execute all statements
    for stmt in statements:
        # Skip schema_migrations table creation (we already created it)
        if 'CREATE TABLE schema_migrations' in stmt:
            continue
        cursor.execute(stmt)

    conn.commit()
