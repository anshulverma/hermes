"""Tests for engine.transport (§6, §9).

TDD: written FIRST, watched fail, then engine/transport.py implemented.

Covers:
  - local_transport wraps the agent argv under a `timeout <timeout_s>` wrapper.
  - ssh_transport builds the scp/ssh/scp-back argv (subprocess mocked) and maps a
    non-zero ssh exit to a transport_error Result.
  - serve_once_for_host end-to-end on LocalSite + MockAgent (claim -> lease -> run
    -> record), the at-capacity park path, the penalty (envelope error) requeue,
    the no-penalty (transport error) requeue, and payload-tamper -> failed.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from engine.db.migrate import apply_migrations, connect
from engine.models import Result, Run, Ticket


def _sha(payload: dict) -> str:
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


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
    apply_migrations(db_path)
    connection = connect(db_path)
    yield connection
    connection.close()


@pytest.fixture
def playbook():
    import testkit  # noqa: F401  (registers "example")
    from engine import playbook as _pb

    return _pb.load("example")


@pytest.fixture
def local_site():
    import sites.local  # noqa: F401  (registers "local")
    from engine import site

    return site.load("local")


@pytest.fixture
def mock_agent():
    import testkit  # noqa: F401  (registers "mock")
    from engine import agent

    return agent.load("mock")


# --- db helpers ----------------------------------------------------------

def _mk_run(conn, run_id="r1", state="running", config=None, phase="work"):
    conn.execute(
        """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                             phase, created_at, updated_at)
           VALUES (?, 'example', 'local', 'main', ?, ?, ?, 0, 0)""",
        (run_id, json.dumps(config or {}), state, phase),
    )
    conn.commit()
    return Run(
        id=run_id, playbook="example", site="local", base_ref="main",
        config=config or {}, phase=phase, reductions=[],
    )


def _mk_ticket(conn, ticket_id="r1/t-0", run_id="r1", state="queued",
               resource_req="cpu", payload=None, phase="work"):
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority,
                                attempts, available_at, tried_hosts, payload_json,
                                created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 0, 0, 0, '[]', ?, 0, 0)""",
        (ticket_id, run_id, phase, state, resource_req, json.dumps(payload or {})),
    )
    conn.commit()
    return Ticket(
        id=ticket_id, run_id=run_id, phase=phase, state=state,
        resource_req=resource_req, priority=0.0, attempts=0, payload=payload or {},
    )


def _mk_crew(conn, host="h1", cpu=2, state="idle"):
    conn.execute(
        """INSERT INTO crew (id, site, capabilities, resources_json, state,
                             registered_at)
           VALUES (?, 'local', '[]', ?, ?, 0)""",
        (host, json.dumps({"cpu": cpu}), state),
    )
    conn.commit()


def _ticket_state(conn, ticket_id):
    return conn.execute(
        "SELECT state, attempts, lease_id FROM tickets WHERE id=?", (ticket_id,)
    ).fetchone()


def _live_leases(conn, ticket_id):
    """Count lease rows still held for a ticket (released leases are deleted)."""
    return conn.execute(
        "SELECT COUNT(*) FROM leases WHERE ticket_id=?", (ticket_id,)
    ).fetchone()[0]


# --- local_transport -----------------------------------------------------

def test_local_transport_wraps_with_timeout(local_site, mock_agent):
    """local_transport runs the agent argv under `timeout <timeout_s>`."""
    from engine import transport

    payload = {"scenario": "ok"}
    env = {
        "ticket_id": "r1/t-0", "run_id": "r1", "phase": "work",
        "resource_req": "cpu", "base_ref": "main", "payload": payload,
        "payload_sha256": _sha(payload), "timeout_s": 1234, "site_context": {},
        "goal_envelope": {
            "goal": "g",
            "driver": {"command": "/echo-work", "args": {}, "loop": None},
            "done_contract": {"type": "object"},
            "guardrails": {"no_ship": True},
        },
    }

    captured = {}

    def fake_run(argv, *a, **k):
        captured["argv"] = argv
        return subprocess_result(returncode=0, stdout="")

    with mock.patch("engine.transport.subprocess.run", side_effect=fake_run):
        result = transport.local_transport(env, "localhost", mock_agent)

    assert os.path.basename(captured["argv"][0]) == "timeout"
    assert captured["argv"][1] == "1234"
    assert "mock-agent" in captured["argv"]
    # mock agent recomputes sha (matches) and returns the "ok" scenario result
    assert result.outcome == "ok"


def subprocess_result(returncode=0, stdout="", stderr=""):
    cp = mock.Mock()
    cp.returncode = returncode
    cp.stdout = stdout
    cp.stderr = stderr
    return cp


# --- ssh_transport -------------------------------------------------------

def test_ssh_transport_builds_scp_ssh_scp_argv(mock_agent):
    from engine import transport

    payload = {"scenario": "ok"}
    env = {
        "ticket_id": "r1/t-0", "run_id": "r1", "phase": "work",
        "resource_req": "cpu", "base_ref": "main", "payload": payload,
        "payload_sha256": _sha(payload), "timeout_s": 60, "site_context": {},
        "goal_envelope": {
            "goal": "g",
            "driver": {"command": None, "args": {}, "loop": None},
            "done_contract": {"type": "object"},
            "guardrails": {"no_ship": True},
        },
    }

    calls = []

    def fake_run(argv, *a, **k):
        calls.append(argv)
        # On scp-back (source is host:remote), materialize the local result file.
        if argv and argv[0] == "scp" and str(argv[1]).startswith("worker-1:"):
            Path(argv[2]).write_text(json.dumps({"scenario": "ok"}))
        return subprocess_result(returncode=0, stdout="")

    with mock.patch("engine.transport.subprocess.run", side_effect=fake_run):
        run = transport.ssh_transport("worker-1")
        result = run(env, mock_agent)

    programs = [c[0] for c in calls]
    assert programs.count("scp") == 2  # up + back
    assert "ssh" in programs
    # scp-up targets the host; ssh runs against the host
    scp_up = calls[0]
    assert scp_up[0] == "scp"
    assert str(scp_up[2]).startswith("worker-1:")
    ssh_call = next(c for c in calls if c[0] == "ssh")
    assert "worker-1" in ssh_call
    assert result.outcome == "ok"


def test_ssh_transport_nonzero_ssh_exit_is_transport_error(mock_agent):
    from engine import transport

    payload = {}
    env = {
        "ticket_id": "r1/t-0", "run_id": "r1", "phase": "work",
        "resource_req": "cpu", "base_ref": "main", "payload": payload,
        "payload_sha256": _sha(payload), "timeout_s": 60, "site_context": {},
        "goal_envelope": {
            "goal": "g",
            "driver": {"command": None, "args": {}, "loop": None},
            "done_contract": {"type": "object"},
            "guardrails": {"no_ship": True},
        },
    }

    def fake_run(argv, *a, **k):
        if argv and argv[0] == "ssh":
            return subprocess_result(returncode=255, stderr="ssh: connect failed")
        return subprocess_result(returncode=0, stdout="")

    with mock.patch("engine.transport.subprocess.run", side_effect=fake_run):
        run = transport.ssh_transport("worker-1")
        result = run(env, mock_agent)

    assert result.outcome == "infra_failed"
    assert result.termination_reason == "transport_error"


# --- serve_once_for_host -------------------------------------------------

def test_serve_once_end_to_end_claims_leases_runs_records(
    conn, local_site, mock_agent, playbook
):
    """One ticket: claim -> lease -> run -> record (LocalSite + MockAgent)."""
    from engine import transport

    run = _mk_run(conn)
    _mk_ticket(conn, payload={"scenario": "ok"})
    _mk_crew(conn, host="h1", cpu=2)

    result = transport.serve_once_for_host(
        conn, "h1", local_site, mock_agent, run, playbook, "main", now=1000.0
    )

    assert result is not None
    assert result.outcome == "ok"
    # ok + verify=True -> reducing; no attempt penalty; lease released on exit
    state, attempts, lease_id = _ticket_state(conn, "r1/t-0")
    assert state == "reducing"
    assert attempts == 0
    assert _live_leases(conn, "r1/t-0") == 0  # lease released on exit from running
    # an attempts audit row and a result_recorded event were written
    n_attempts = conn.execute(
        "SELECT COUNT(*) FROM attempts WHERE ticket_id='r1/t-0'"
    ).fetchone()[0]
    assert n_attempts == 1
    kinds = [r[0] for r in conn.execute("SELECT kind FROM events").fetchall()]
    assert "ticket_claimed" in kinds
    assert "result_recorded" in kinds


def test_serve_once_parks_at_capacity(conn, local_site, mock_agent, playbook):
    """acquire -> None (no crew capacity) parks the ticket, no dispatch, no penalty."""
    from engine import transport

    run = _mk_run(conn)
    _mk_ticket(conn, payload={"scenario": "ok"})
    # No crew rows -> capacity 0 -> acquire returns None -> park.

    result = transport.serve_once_for_host(
        conn, "h1", local_site, mock_agent, run, playbook, "main", now=1000.0
    )

    assert result is None
    state, attempts, lease_id = _ticket_state(conn, "r1/t-0")
    assert state == "parked"
    assert attempts == 0
    assert _live_leases(conn, "r1/t-0") == 0
    n_attempts = conn.execute(
        "SELECT COUNT(*) FROM attempts WHERE ticket_id='r1/t-0'"
    ).fetchone()[0]
    assert n_attempts == 0  # never executed
    kinds = [r[0] for r in conn.execute("SELECT kind FROM events").fetchall()]
    assert "ticket_parked" in kinds


def test_serve_once_envelope_error_requeues_with_penalty(
    conn, local_site, mock_agent
):
    """A bad envelope (validation error) -> penalty requeue (attempts+1)."""
    from engine import transport

    run = _mk_run(conn)
    _mk_ticket(conn, payload={"scenario": "ok"})
    _mk_crew(conn, host="h1", cpu=2)

    # A playbook whose payload_schema rejects the ticket payload -> ContractError.
    class BadSchemaPlaybook:
        name = "bad"
        phases = ["work"]

        def payload_schema(self, phase):
            return {"type": "object", "required": ["must_have"]}

        def result_schema(self, phase):
            return {"type": "object"}

        def driver(self, phase):
            from engine.models import Driver
            return Driver(command=None, args={}, loop=None)

    result = transport.serve_once_for_host(
        conn, "h1", local_site, mock_agent, run, BadSchemaPlaybook(), "main",
        now=1000.0,
    )

    assert result is None
    state, attempts, lease_id = _ticket_state(conn, "r1/t-0")
    assert state == "queued"
    assert attempts == 1  # penalty applied
    assert _live_leases(conn, "r1/t-0") == 0  # lease released on requeue


def test_serve_once_transport_error_requeues_without_penalty(
    conn, mock_agent, playbook
):
    """A transport error (host lost) -> no-penalty requeue (attempts unchanged)."""
    from engine import transport

    run = _mk_run(conn)
    _mk_ticket(conn, payload={"scenario": "ok"})
    _mk_crew(conn, host="h1", cpu=2)

    class LostHostSite:
        name = "local"

        def resource_classes(self):
            return ["cpu"]

        def guarantees_no_ship(self):
            return True

        def run_worker(self, host, envelope, agent):
            raise transport.TransportError("host lost")

    result = transport.serve_once_for_host(
        conn, "h1", LostHostSite(), mock_agent, run, playbook, "main", now=1000.0
    )

    assert result is None
    state, attempts, lease_id = _ticket_state(conn, "r1/t-0")
    assert state == "queued"
    assert attempts == 0  # NO penalty for transport/host-lost
    assert _live_leases(conn, "r1/t-0") == 0


def test_serve_once_stamps_matching_payload_sha256(
    conn, mock_agent, playbook
):
    """serve computes payload_sha256 as the canonical digest of the payload."""
    from engine import transport

    run = _mk_run(conn)
    payload = {"scenario": "ok", "k": "v"}
    _mk_ticket(conn, payload=payload)
    _mk_crew(conn, host="h1", cpu=2)

    seen = {}

    class CapturingSite:
        name = "local"

        def resource_classes(self):
            return ["cpu"]

        def guarantees_no_ship(self):
            return True

        def run_worker(self, host, envelope, agent):
            seen["envelope"] = envelope
            return agent.parse_result("", envelope)

    transport.serve_once_for_host(
        conn, "h1", CapturingSite(), mock_agent, run, playbook, "main", now=1000.0
    )

    assert seen["envelope"]["payload_sha256"] == _sha(payload)


def test_serve_once_payload_tamper_fails_ticket_no_retry(
    conn, mock_agent, playbook
):
    """A tampered payload (digest mismatch at the worker) -> contract_fail -> failed."""
    from engine import transport

    run = _mk_run(conn)
    _mk_ticket(conn, payload={"scenario": "ok"})
    _mk_crew(conn, host="h1", cpu=2)

    class TamperSite:
        name = "local"

        def resource_classes(self):
            return ["cpu"]

        def guarantees_no_ship(self):
            return True

        def run_worker(self, host, envelope, agent):
            tampered = dict(envelope)
            tampered["payload_sha256"] = "0" * 64  # corrupt in transit
            return agent.parse_result("", tampered)

    result = transport.serve_once_for_host(
        conn, "h1", TamperSite(), mock_agent, run, playbook, "main", now=1000.0
    )

    assert result.outcome == "driver_failed"
    assert result.termination_reason == "contract_fail"
    state, attempts, lease_id = _ticket_state(conn, "r1/t-0")
    assert state == "failed"  # driver_failed is terminal, no retry
    assert _live_leases(conn, "r1/t-0") == 0
