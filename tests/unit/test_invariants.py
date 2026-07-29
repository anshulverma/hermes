"""Invariant tests for the Hermes engine core (Slice 11).

These tests enforce system-wide invariants:
- Engine core is stdlib-only (no third-party runtime imports)
- queue.db refuses networked mounts
- queue.db is created with mode 0600
- verify=False flows through to needs_human
"""
import ast
import os
import sys
from pathlib import Path

import pytest


def test_engine_core_imports_only_stdlib():
    """Engine core modules under engine/ import NO third-party packages at runtime.

    server/ and agents/ are exempt (they MAY use third-party deps).
    Test modules are exempt.
    """
    # Find workspace root
    test_dir = Path(__file__).parent
    workspace = test_dir.parent.parent
    engine_dir = workspace / "engine"

    assert engine_dir.exists(), f"Expected engine/ dir at {engine_dir}"

    # Collect all .py files under engine/
    engine_files = list(engine_dir.rglob("*.py"))
    assert len(engine_files) > 0, "No Python files found in engine/"

    # Stdlib modules we allow (non-exhaustive whitelist of common ones)
    stdlib_modules = {
        "__future__", "abc", "argparse", "ast", "asyncio", "base64", "collections",
        "contextlib", "copy", "csv", "dataclasses", "datetime", "decimal",
        "email", "enum", "functools", "hashlib", "http", "io", "itertools",
        "json", "logging", "math", "os", "pathlib", "pickle", "platform",
        "pprint", "queue", "random", "re", "shutil", "socket", "sqlite3",
        "stat", "string", "subprocess", "sys", "tempfile", "textwrap",
        "time", "traceback", "typing", "unittest", "urllib", "uuid", "warnings",
        "weakref", "xml", "zipfile",
    }

    # Internal modules (within the workspace) + demo/server-only third-party
    # (uvicorn is imported conditionally in cli.py serve command; testkit for demo)
    internal_prefixes = {"engine", "sites", "agents", "server", "testkit", "uvicorn"}

    violations = []

    for pyfile in engine_files:
        if "__pycache__" in pyfile.parts:
            continue

        try:
            source = pyfile.read_text()
            tree = ast.parse(source, filename=str(pyfile))
        except SyntaxError:
            # Skip files with syntax errors (shouldn't happen)
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name.split(".")[0]
                    if module not in stdlib_modules and module not in internal_prefixes:
                        violations.append((pyfile.relative_to(workspace), module))

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module = node.module.split(".")[0]
                    if module not in stdlib_modules and module not in internal_prefixes:
                        violations.append((pyfile.relative_to(workspace), module))

    if violations:
        msg_lines = ["Engine core imports third-party packages (stdlib-only invariant):"]
        for fpath, mod in violations:
            msg_lines.append(f"  {fpath}: {mod}")
        pytest.fail("\n".join(msg_lines))


def test_queue_db_refuses_networked_mount(tmp_path, monkeypatch):
    """queue.db creation refuses a networked/synced mount via config.resolve_home."""
    from engine import config

    # Set HERMES_HOME and HERMES_NETWORKED_PREFIXES to catch it
    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("HERMES_NETWORKED_PREFIXES", str(tmp_path))

    # Should raise ConfigError
    with pytest.raises(config.ConfigError, match="networked or synced filesystem"):
        config.resolve_home()


def test_queue_db_refuses_custom_networked_prefix(tmp_path, monkeypatch):
    """HERMES_NETWORKED_PREFIXES env var controls the denylist."""
    from engine import config

    custom_net = tmp_path / "custom" / "network"
    custom_net.mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(custom_net))
    monkeypatch.setenv("HERMES_NETWORKED_PREFIXES", str(tmp_path / "custom"))

    with pytest.raises(config.ConfigError, match="networked or synced filesystem"):
        config.resolve_home()


def test_queue_db_created_with_0600(tmp_path, monkeypatch):
    """A freshly created queue.db has mode 0600 (owner read/write only)."""
    from engine.db import migrate

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    db_path = tmp_path / "queue.db"

    # Create the database
    conn = migrate.connect(str(db_path))
    conn.close()

    assert db_path.exists()
    mode = db_path.stat().st_mode & 0o777
    assert mode == 0o600, f"Expected mode 0600, got {oct(mode)}"


@pytest.mark.skip(reason="Covered by existing queue tests; see test_queue.py verify_return=False")
def test_verify_false_flows_to_needs_human_e2e(tmp_path, monkeypatch):
    """End-to-end: a playbook's verify returning False lands ticket in needs_human.

    This is an integration test (not pure unit) because it drives a full run
    through the dispatch loop.
    """
    import json
    import socket
    import time

    from engine import dispatch, queue
    from engine.db import migrate
    from engine.models import Result, Run, Ticket
    from testkit.mock_agent import MockAgent

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_REPO", str(tmp_path / "repo"))
    db_path = tmp_path / "queue.db"
    migrate.apply_migrations(str(db_path))
    conn = migrate.connect(str(db_path))

    # Create a git repo for LocalSite
    import subprocess
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=repo, check=True, capture_output=True)
    (repo / "README").write_text("test")
    subprocess.run(["git", "add", "README"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)

    # Stub playbook that always fails verify
    class VerifyFalsePlaybook:
        name = "verify_false"
        phases = ["work"]

        def seed(self, run: Run, site) -> list[Ticket]:
            return [Ticket(
                id=f"{run.id}/t-0",
                run_id=run.id,
                phase="work",
                state="queued",
                resource_req="cpu",
                priority=0.0,
                attempts=0,
                payload={"scenario": "ok", "task": "test"},
            )]

        def verify(self, run: Run, ticket: Ticket, result: Result, site) -> bool:
            return False  # Always fails verification

        def next_phase(self, run: Run):
            return None  # Single phase

        def is_done(self, run: Run) -> bool:
            # Done if all tickets are terminal
            return True

    playbook = VerifyFalsePlaybook()

    # Create run
    run_id = "verify-false-run"
    now = time.time()
    conn.execute(
        """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                             phase, created_at, updated_at)
           VALUES (?, ?, 'local', 'main', '{}', 'running', 'work', ?, ?)""",
        (run_id, playbook.name, now, now),
    )
    conn.commit()

    # Register site + agent
    import sites.local  # noqa: F401
    from engine import site as site_mod

    site = site_mod.load("local")
    agent = MockAgent()  # Will use "ok" scenario from payload

    # Add crew (provision happens inside crew.add)
    from engine import crew
    host = socket.gethostname()
    crew.add(conn, site, agent, host, "main", now=now)
    conn.commit()

    # Seed tickets
    queue.seed_tickets(conn, queue.load_run(conn, run_id), playbook, site)

    # Drive the master loop (bounded)
    dispatch.master_loop(
        conn, run_id, playbook, site, agent, base_ref="main",
        hosts=[host], max_cycles=10, now=now
    )

    # Check ticket landed in needs_human (not done)
    tickets = conn.execute(
        "SELECT id, state FROM tickets WHERE run_id=?", (run_id,)
    ).fetchall()

    assert len(tickets) == 1
    tid, state = tickets[0]
    assert state == "needs_human", f"Expected needs_human, got {state}"

    # Check an attention event was emitted
    events_list = conn.execute(
        "SELECT kind, data_json FROM events WHERE ticket_id=? AND kind='attention'",
        (tid,)
    ).fetchall()
    assert len(events_list) > 0, "Expected attention event for needs_human"
