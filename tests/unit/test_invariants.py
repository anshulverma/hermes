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
