"""Tests for run-level attention event detection (Slice 11, §7).

TDD: Written FIRST to drive check_attention implementation.
"""
import json
import sqlite3
import tempfile
import time
from pathlib import Path

import pytest

from engine import events
from engine.db.migrate import apply_migrations, connect


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        path = f.name
    yield path
    for suffix in ("", "-shm", "-wal"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)


@pytest.fixture
def conn(db_path):
    apply_migrations(db_path)
    connection = connect(db_path)
    yield connection
    connection.close()


def _mk_run(conn, run_id="r1", state="running", phase="work"):
    conn.execute(
        """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                             phase, created_at, updated_at)
           VALUES (?, 'test', 'local', 'main', '{}', ?, ?, 0, 0)""",
        (run_id, state, phase),
    )
    conn.commit()


def _mk_ticket(conn, ticket_id, run_id="r1", state="queued", phase="work"):
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority,
                                attempts, available_at, tried_hosts, payload_json,
                                created_at, updated_at)
           VALUES (?, ?, ?, ?, 'cpu', 0.0, 0, 0.0, '[]', '{}', 0, 0)""",
        (ticket_id, run_id, phase, state),
    )
    conn.commit()


def _mk_crew(conn, host_id, state="idle", resources=None):
    if resources is None:
        resources = {"cpu": 1}
    now = time.time()
    conn.execute(
        """INSERT INTO crew (id, site, capabilities, resources_json, state,
                             health_json, last_heartbeat, registered_at)
           VALUES (?, 'local', '[]', ?, ?, '{}', ?, ?)""",
        (host_id, json.dumps(resources), state, now, now),
    )
    conn.commit()


def _get_attention_events(conn, run_id):
    """Return all attention events for run_id with their reason."""
    rows = conn.execute(
        """SELECT ts, data_json FROM events
           WHERE kind='attention' AND run_id=?
           ORDER BY id""",
        (run_id,)
    ).fetchall()
    return [(ts, json.loads(data_json).get("reason")) for ts, data_json in rows]


def test_check_attention_emits_parked_ratio(conn):
    """check_attention emits attention when >50% of tickets are parked."""
    from engine.dispatch import check_attention

    run_id = "r1"
    _mk_run(conn, run_id)
    # 2 parked, 1 queued -> 2/3 = 66% parked
    _mk_ticket(conn, "r1/t1", run_id, state="parked")
    _mk_ticket(conn, "r1/t2", run_id, state="parked")
    _mk_ticket(conn, "r1/t3", run_id, state="queued")

    now = time.time()
    check_attention(conn, run_id, now=now)
    conn.commit()

    attn = _get_attention_events(conn, run_id)
    assert len(attn) == 1
    assert attn[0][1] == "parked_ratio_high"


def test_check_attention_emits_all_crew_down(conn):
    """check_attention emits when all crew members are down."""
    from engine.dispatch import check_attention

    run_id = "r1"
    _mk_run(conn, run_id)
    _mk_crew(conn, "host1", state="down")
    _mk_crew(conn, "host2", state="down")

    now = time.time()
    check_attention(conn, run_id, now=now)
    conn.commit()

    attn = _get_attention_events(conn, run_id)
    assert len(attn) == 1
    assert attn[0][1] == "all_crew_down"


def test_check_attention_emits_no_progress(conn):
    """check_attention emits when no events for >1800s."""
    from engine.dispatch import check_attention

    run_id = "r1"
    _mk_run(conn, run_id)

    # Emit a run_started event 2000s ago
    old_ts = time.time() - 2000
    conn.execute(
        """INSERT INTO events (ts, kind, run_id, ticket_id, host, message, data_json)
           VALUES (?, 'run_started', ?, NULL, NULL, NULL, '{}')""",
        (old_ts, run_id),
    )
    conn.commit()

    now = time.time()
    check_attention(conn, run_id, now=now)
    conn.commit()

    attn = _get_attention_events(conn, run_id)
    assert len(attn) == 1
    assert attn[0][1] == "no_progress"


def test_check_attention_deduplicates_within_window(conn, monkeypatch):
    """check_attention does NOT re-emit the same reason within the heartbeat window."""
    from engine import config
    from engine.dispatch import check_attention

    monkeypatch.setenv("HERMES_HEARTBEAT_S", "30")

    run_id = "r1"
    _mk_run(conn, run_id)
    _mk_crew(conn, "host1", state="down")

    now = time.time()
    # First call: emits
    check_attention(conn, run_id, now=now)
    conn.commit()

    attn = _get_attention_events(conn, run_id)
    assert len(attn) == 1
    assert attn[0][1] == "all_crew_down"

    # Second call 10s later (within 30s window): does NOT re-emit
    check_attention(conn, run_id, now=now + 10)
    conn.commit()

    attn = _get_attention_events(conn, run_id)
    assert len(attn) == 1  # Still only 1

    # Third call 40s later (outside window): re-emits
    check_attention(conn, run_id, now=now + 40)
    conn.commit()

    attn = _get_attention_events(conn, run_id)
    assert len(attn) == 2  # New event
    assert attn[1][1] == "all_crew_down"


def test_check_attention_multiple_conditions(conn):
    """check_attention can emit multiple attention events for different reasons."""
    from engine.dispatch import check_attention

    run_id = "r1"
    _mk_run(conn, run_id)
    # All crew down
    _mk_crew(conn, "host1", state="down")
    # >50% parked
    _mk_ticket(conn, "r1/t1", run_id, state="parked")
    _mk_ticket(conn, "r1/t2", run_id, state="parked")
    _mk_ticket(conn, "r1/t3", run_id, state="queued")

    now = time.time()
    check_attention(conn, run_id, now=now)
    conn.commit()

    attn = _get_attention_events(conn, run_id)
    reasons = {a[1] for a in attn}
    assert "all_crew_down" in reasons
    assert "parked_ratio_high" in reasons
