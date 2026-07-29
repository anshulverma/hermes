"""Tests for engine.log module (operational diagnostics logging).

TDD: Written FIRST (failing until engine/log.py exists).
Tests the stdlib-logging operational diagnostics layer:
- configure() idempotent (exactly one handler)
- text and json formatters
- bind() context injection
- HERMES_DEBUG vs explicit HERMES_LOG_LEVEL precedence
- redact() masks secrets
- HARD: no secrets in logs (full LocalSite+MockAgent run + create_app + WS connect)
"""
import io
import json
import logging
import os
import secrets as stdlib_secrets
import subprocess
import threading
import time
from pathlib import Path

import pytest

from engine.db.migrate import apply_migrations, connect


@pytest.fixture
def source_repo(tmp_path, monkeypatch):
    """A real git repo with one commit, wired up as HERMES_REPO."""
    repo = tmp_path / "src"
    repo.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=env)
    (repo / "README").write_text("hi\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True, env=env)
    monkeypatch.setenv("HERMES_REPO", str(repo))
    return repo


@pytest.fixture(autouse=True)
def reset_logging():
    """Reset logging state before each test."""
    # Clear hermes logger
    hermes_logger = logging.getLogger("hermes")
    hermes_logger.handlers.clear()
    hermes_logger.setLevel(logging.NOTSET)

    # Import here to avoid import errors if log doesn't exist yet
    try:
        from engine import log
        log._configured = False
    except (ImportError, AttributeError):
        pass

    yield

    # Cleanup after test
    hermes_logger.handlers.clear()
    hermes_logger.setLevel(logging.NOTSET)
    try:
        from engine import log
        log._configured = False
    except (ImportError, AttributeError):
        pass


class CaptureHandler(logging.Handler):
    """In-memory capture handler for testing (single-threaded, no lock needed)."""
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def clear(self):
        self.records.clear()

    def get_messages(self):
        """Return all formatted messages."""
        return [self.format(rec) for rec in self.records]

    def get_records(self):
        """Return a copy of all records."""
        return self.records.copy()


def test_configure_is_idempotent(monkeypatch):
    """configure() called twice should install exactly one handler."""
    monkeypatch.delenv("HERMES_LOG_LEVEL", raising=False)
    monkeypatch.delenv("HERMES_LOG_FORMAT", raising=False)
    monkeypatch.delenv("HERMES_LOG_FILE", raising=False)

    from engine import log

    hermes_logger = logging.getLogger("hermes")

    log.configure()
    assert len(hermes_logger.handlers) == 1

    log.configure()
    assert len(hermes_logger.handlers) == 1, "configure() must be idempotent"


def test_text_formatter_shape(monkeypatch):
    """Text formatter produces expected shape with bound fields."""
    monkeypatch.delenv("HERMES_LOG_LEVEL", raising=False)
    monkeypatch.setenv("HERMES_LOG_FORMAT", "text")
    monkeypatch.delenv("HERMES_LOG_FILE", raising=False)

    from engine import log

    hermes_logger = logging.getLogger("hermes")

    capture = CaptureHandler()
    log.configure()
    # Replace the configured handler with our capture handler (copy filter and formatter)
    orig_handler = hermes_logger.handlers[0]
    capture.addFilter(log.BoundFieldsFilter())
    capture.setFormatter(orig_handler.formatter)
    hermes_logger.handlers.clear()
    hermes_logger.addHandler(capture)
    hermes_logger.setLevel(logging.DEBUG)

    logger = log.get_logger("test.module")
    with log.bind(run_id="r1", ticket_id="t1", host="h1"):
        logger.info("test message")

    messages = capture.get_messages()
    assert len(messages) == 1
    msg = messages[0]
    # Expected: "<ts> <level> <name> [run_id=r1 ticket_id=t1 host=h1] test message"
    assert "INFO" in msg
    assert "hermes.test.module" in msg
    assert "run_id=r1" in msg
    assert "ticket_id=t1" in msg
    assert "host=h1" in msg
    assert "test message" in msg


def test_json_formatter_shape(monkeypatch):
    """JSON formatter produces parseable JSON with expected keys."""
    monkeypatch.delenv("HERMES_LOG_LEVEL", raising=False)
    monkeypatch.setenv("HERMES_LOG_FORMAT", "json")
    monkeypatch.delenv("HERMES_LOG_FILE", raising=False)

    from engine import log

    hermes_logger = logging.getLogger("hermes")

    capture = CaptureHandler()
    log.configure()
    # Replace the configured handler with our capture handler (copy filter and formatter)
    orig_handler = hermes_logger.handlers[0]
    capture.addFilter(log.BoundFieldsFilter())
    capture.setFormatter(orig_handler.formatter)
    hermes_logger.handlers.clear()
    hermes_logger.addHandler(capture)
    hermes_logger.setLevel(logging.DEBUG)

    logger = log.get_logger("test.module")
    with log.bind(run_id="r1", ticket_id="t2"):
        logger.warning("json test", extra={"foo": "bar"})

    messages = capture.get_messages()
    assert len(messages) == 1
    msg = messages[0]

    # Parse JSON
    obj = json.loads(msg)
    assert "ts" in obj
    assert obj["level"] == "WARNING"
    assert obj["logger"] == "hermes.test.module"
    assert obj["msg"] == "json test"
    assert obj["run_id"] == "r1"
    assert obj["ticket_id"] == "t2"
    assert obj.get("host") is None  # not bound
    assert obj["foo"] == "bar"  # extra


def test_bind_attaches_fields_to_records(monkeypatch):
    """bind() contextmanager attaches run_id/ticket_id/host to records."""
    monkeypatch.delenv("HERMES_LOG_LEVEL", raising=False)
    monkeypatch.delenv("HERMES_LOG_FORMAT", raising=False)
    monkeypatch.delenv("HERMES_LOG_FILE", raising=False)

    from engine import log

    hermes_logger = logging.getLogger("hermes")

    capture = CaptureHandler()
    log.configure()
    # Replace the configured handler with our capture handler (copy filter)
    orig_handler = hermes_logger.handlers[0]
    capture.addFilter(log.BoundFieldsFilter())
    hermes_logger.handlers.clear()
    hermes_logger.addHandler(capture)
    hermes_logger.setLevel(logging.DEBUG)

    logger = log.get_logger("bind.test")

    # Log without bind
    logger.info("no bind")
    # Log with partial bind
    with log.bind(run_id="r1", host="h1"):
        logger.info("partial bind")
    # Log with full bind
    with log.bind(run_id="r2", ticket_id="t2", host="h2"):
        logger.info("full bind")

    records = capture.get_records()
    assert len(records) == 3

    # First record: no fields
    assert not hasattr(records[0], "run_id")
    assert not hasattr(records[0], "ticket_id")
    assert not hasattr(records[0], "host")

    # Second record: run_id and host
    assert getattr(records[1], "run_id", None) == "r1"
    assert not hasattr(records[1], "ticket_id")
    assert getattr(records[1], "host", None) == "h1"

    # Third record: all fields
    assert getattr(records[2], "run_id", None) == "r2"
    assert getattr(records[2], "ticket_id", None) == "t2"
    assert getattr(records[2], "host", None) == "h2"


def test_hermes_debug_sets_debug_level(monkeypatch):
    """HERMES_DEBUG=1 sets level to DEBUG."""
    monkeypatch.setenv("HERMES_DEBUG", "1")
    monkeypatch.delenv("HERMES_LOG_LEVEL", raising=False)
    monkeypatch.delenv("HERMES_LOG_FORMAT", raising=False)
    monkeypatch.delenv("HERMES_LOG_FILE", raising=False)

    from engine import log

    hermes_logger = logging.getLogger("hermes")

    log.configure()
    assert hermes_logger.level == logging.DEBUG


def test_explicit_log_level_wins_over_debug(monkeypatch):
    """Explicit HERMES_LOG_LEVEL wins over HERMES_DEBUG."""
    monkeypatch.setenv("HERMES_DEBUG", "1")
    monkeypatch.setenv("HERMES_LOG_LEVEL", "WARNING")
    monkeypatch.delenv("HERMES_LOG_FORMAT", raising=False)
    monkeypatch.delenv("HERMES_LOG_FILE", raising=False)

    from engine import log

    hermes_logger = logging.getLogger("hermes")

    log.configure()
    assert hermes_logger.level == logging.WARNING


def test_redact_masks_secrets_keeps_others():
    """redact() masks known secret keys, keeps non-secret keys."""
    from engine import log

    data = {
        "api_token": "s3cr3t",
        "token": "bearer123",
        "authorized_key": "ssh-rsa AAAA...",
        "identity": "/path/to/key",
        "host": "h1",
        "run_id": "r1",
    }

    redacted = log.redact(data)
    assert redacted["api_token"] == "***"
    assert redacted["token"] == "***"
    assert redacted["authorized_key"] == "***"
    assert redacted["identity"] == "***"
    assert redacted["host"] == "h1"
    assert redacted["run_id"] == "r1"
    # Original unchanged
    assert data["api_token"] == "s3cr3t"


def test_no_secrets_in_logs(tmp_path, source_repo, monkeypatch):
    """HARD: full LocalSite+MockAgent run + server WS connect must log NO secrets.

    REAL integration test the brief mandates:
    - Drives dispatch.master_loop against a real temp git repo + temp HERMES_HOME
    - Creates FastAPI app + TestClient + WebSocket connection with real api_token
    - Asserts NO secrets appear in captured logs (both getMessage() AND formatted output)
    - Includes positive control: asserts capture DID record some hermes.* logs
    """
    import subprocess

    # Set up HERMES_HOME
    hermes_home = tmp_path / "hermes-home"
    hermes_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    # Set secrets in env
    ssh_identity_path = "/tmp/secret_ssh_id_rsa_sentinel_12345"
    authorized_key_value = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC_SECRET_SENTINEL_KEY_67890"

    monkeypatch.setenv("HERMES_SSH_IDENTITY_testhost", ssh_identity_path)
    monkeypatch.setenv("HERMES_AUTHORIZED_KEY", authorized_key_value)

    # Configure logging with capture (use JSON format to see extra fields)
    monkeypatch.setenv("HERMES_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("HERMES_LOG_FORMAT", "json")
    monkeypatch.delenv("HERMES_LOG_FILE", raising=False)

    from engine import log
    from engine.db.migrate import apply_migrations, connect
    from engine.models import Run
    from engine import queue, dispatch, playbook, site, agent

    hermes_logger = logging.getLogger("hermes")

    # Install capture handler on root hermes logger (captures ALL hermes.* logs)
    capture = CaptureHandler()
    log.configure()
    orig_handler = hermes_logger.handlers[0]
    capture.addFilter(log.BoundFieldsFilter())
    capture.setFormatter(orig_handler.formatter)
    hermes_logger.handlers.clear()
    hermes_logger.addHandler(capture)
    hermes_logger.setLevel(logging.DEBUG)

    # (i) Drive a full LocalSite + MockAgent run via dispatch.master_loop
    # Import to register
    import sites.local.site
    import testkit.mock_agent

    pb = playbook.load("example")
    st = site.load("local")
    ag = agent.load("mock")

    # Set up DB
    db_path = str(hermes_home / "queue.db")
    apply_migrations(db_path)
    conn = connect(db_path)

    # Create run
    run_id = "test-run-1"
    now = time.time()
    conn.execute(
        """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                             phase, created_at, updated_at)
           VALUES (?, 'example', 'local', 'main', '{}', 'running', 'work', ?, ?)""",
        (run_id, now, now),
    )
    conn.commit()

    # Seed one ticket (minimal work to trigger logging)
    ticket_id = f"{run_id}/t-0"
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority,
                               attempts, available_at, payload_json, created_at, updated_at)
           VALUES (?, ?, 'work', 'queued', 'cpu', 100, 0, 0.0, '{}', ?, ?)""",
        (ticket_id, run_id, now, now),
    )
    conn.commit()

    # Drive master_loop (bounded, 1 cycle enough to trigger logging)
    dispatch.master_loop(
        conn=conn,
        run_id=run_id,
        playbook=pb,
        site=st,
        agent=ag,
        base_ref="main",
        hosts=["localhost"],
        now=now,
        max_cycles=1,
    )
    conn.close()

    # (ii) create_app() + TestClient; read the REAL api_token; WS connect
    from server.app import create_app
    from server.auth import read_token

    app = create_app(bind="127.0.0.1")
    real_token = read_token(hermes_home)
    assert real_token is not None, "api_token should have been created"

    # Use FastAPI TestClient to hit endpoints + WebSocket
    from fastapi.testclient import TestClient
    client = TestClient(app)

    # Hit a GET endpoint (should log request)
    response = client.get("/api/health")
    assert response.status_code == 200

    # WebSocket connect with token in query string
    with client.websocket_connect(f"/api/ws?token={real_token}") as websocket:
        data = websocket.receive_json()
        assert data["type"] == "hello"

    # Close client
    # (FastAPI TestClient auto-closes)

    # Collect all log output (both getMessage() and formatted output)
    all_records = capture.get_records()
    all_messages_raw = [rec.getMessage() for rec in all_records]
    all_messages_formatted = capture.get_messages()

    all_text_raw = "\n".join(all_messages_raw)
    all_text_formatted = "\n".join(all_messages_formatted)
    all_text = all_text_raw + "\n" + all_text_formatted

    # Assert NO secrets appear in logs
    secrets_to_check = [
        (real_token, "api_token value"),
        (f"token={real_token}", "?token= querystring"),
        (ssh_identity_path, "HERMES_SSH_IDENTITY path"),
        (authorized_key_value, "HERMES_AUTHORIZED_KEY value"),
    ]

    for secret, description in secrets_to_check:
        assert secret not in all_text, f"SECRET LEAKED: {description} found in logs"

    # Positive control: assert capture DID record some hermes.* logs
    assert len(all_records) > 0, "No logs captured (test has no teeth)"
    hermes_logs = [r for r in all_records if r.name.startswith("hermes.")]
    assert len(hermes_logs) > 0, "No hermes.* logs captured (test has no teeth)"
