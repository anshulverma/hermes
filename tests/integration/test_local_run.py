"""Integration tests for the dispatch loops.

TDD: written FIRST, watched fail, then engine/dispatch.py + the LocalSite
no-ship guard implemented.

The full pipeline runs on LocalSite + MockAgent (HERMES_AGENT=mock) + EchoPlaybook
with NO real claude, NO SSH, NO Meta — the mock agent's build_invocation is a
trivial successful no-op (``true``) so local_transport executes cleanly.

Covers:
  - full multi-phase run driven to ``done`` (event stream, reductions, phase-1
    seed receiving phase-0 reductions);
  - pause / stop halt all progression (only heartbeat housekeeping); resume
    reaches ``done``;
  - a stuck run (no actionable tickets, next_phase None, not done) → ``failed``;
  - the no-ship guard genuinely blocks ``git push`` in a provisioned workspace;
  - a contract violation (bad envelope AND a bad result) NO-GOs the ticket to a
    terminal ``failed`` with no infinite loop.
"""
from __future__ import annotations

import os
import socket
import subprocess
import tempfile
from pathlib import Path

import pytest

from engine.db.migrate import apply_migrations, connect
from engine.models import Driver, Ticket
from testkit import fixtures


# --- fixtures ------------------------------------------------------------

@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes-home"))
    return tmp_path


@pytest.fixture
def source_repo(tmp_path, monkeypatch):
    """A real git repo with one commit, wired up as HERMES_REPO."""
    repo = tmp_path / "src"
    repo.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=env)
    (repo / "README").write_text("hi\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True, env=env)
    monkeypatch.setenv("HERMES_REPO", str(repo))
    return repo


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "queue.db")
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
def local_site():
    import sites.local  # noqa: F401  (registers "local")
    from engine import site

    return site.load("local")


@pytest.fixture
def mock_agent():
    import testkit  # noqa: F401  (registers "mock")
    from engine import agent

    return agent.load("mock")


@pytest.fixture
def example_playbook():
    import testkit  # noqa: F401  (registers "example")
    from engine import playbook as _pb

    return _pb.load("example")


# --- helpers -------------------------------------------------------------

def _mk_run(conn, run_id, *, playbook="example", config=None, phase="work",
            state="running", base_ref="HEAD"):
    import json

    conn.execute(
        """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                             phase, created_at, updated_at)
           VALUES (?, ?, 'local', ?, ?, ?, ?, 0, 0)""",
        (run_id, playbook, base_ref, json.dumps(config or {}), state, phase),
    )
    conn.commit()


def _ticket_states(conn, run_id):
    return {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT id, state FROM tickets WHERE run_id=? ORDER BY id", (run_id,)
        ).fetchall()
    }


def _run_state(conn, run_id):
    return conn.execute("SELECT state FROM runs WHERE id=?", (run_id,)).fetchone()[0]


def _event_kinds(conn, run_id):
    return [
        r[0]
        for r in conn.execute(
            "SELECT kind FROM events WHERE run_id=? OR run_id IS NULL ORDER BY id",
            (run_id,),
        ).fetchall()
    ]


def _first_index(seq, value):
    return seq.index(value) if value in seq else -1


TERMINAL = {"done", "failed"}


# --- full pipeline -> done ----------------------------------------------

def test_full_pipeline_reaches_done(
    home, source_repo, conn, local_site, mock_agent, example_playbook
):
    """seed -> master_loop -> done; every ticket terminal; ordered event stream;
    a reduction is created; the phase-1 seed carries the phase-0 reductions."""
    import json

    from engine import crew, dispatch, queue
    from engine.models import Run

    host = local_site.discover_hosts()[0]

    # Canned issues drive the phase-0 seed (3 issues -> 3 work tickets).
    issues_path = home / "issues.json"
    fixtures.write_canned_issues(issues_path)

    run_id = "example-1"
    config = {"issue_filters": {"path": str(issues_path)}}
    _mk_run(conn, run_id, config=config, phase="work")

    run = Run(id=run_id, playbook="example", site="local", base_ref="HEAD",
              config=config, phase="work", reductions=[])
    seeded = queue.seed_tickets(conn, run, example_playbook, local_site)
    assert len(seeded) == len(fixtures.CANNED_ISSUES)

    # Register the local host so claims/leases have capacity.
    crew.add(conn, local_site, mock_agent, host=host, base_ref="HEAD", now=1000.0)

    dispatch.master_loop(
        conn, run_id, example_playbook, local_site, mock_agent, "HEAD",
        hosts=[host], now=1000.0, max_cycles=10,
    )

    # Run reached done; every ticket is terminal.
    assert _run_state(conn, run_id) == "done"
    states = _ticket_states(conn, run_id)
    assert states, "expected tickets"
    assert all(s in TERMINAL for s in states.values()), states

    # A reduction was created (>=1), stamped with its phase.
    reductions = conn.execute(
        "SELECT phase, json FROM reductions WHERE run_id=? ORDER BY id", (run_id,)
    ).fetchall()
    assert len(reductions) >= 1
    phases_reduced = {r[0] for r in reductions}
    assert "work" in phases_reduced

    # Ordered event stream: claim -> result -> reduction_created -> phase_advanced
    kinds = _event_kinds(conn, run_id)
    for k in ("ticket_claimed", "result_recorded", "reduction_created",
              "phase_advanced", "run_done"):
        assert k in kinds, f"missing {k} in {kinds}"
    assert _first_index(kinds, "ticket_claimed") < _first_index(kinds, "result_recorded")
    assert _first_index(kinds, "result_recorded") < _first_index(kinds, "reduction_created")
    assert _first_index(kinds, "reduction_created") < _first_index(kinds, "phase_advanced")

    # The phase-1 ("reduce") tickets were seeded FROM the phase-0 reductions:
    # their payload carries the reduction kind + clustered output.
    reduce_tickets = conn.execute(
        "SELECT payload_json FROM tickets WHERE run_id=? AND phase='reduce'",
        (run_id,),
    ).fetchall()
    assert reduce_tickets, "expected phase-1 (reduce) tickets seeded from reductions"
    for (pj,) in reduce_tickets:
        payload = json.loads(pj)
        assert payload.get("reduction_kind") == "cluster"
        assert "clusters" in payload


# --- pause / stop halt progression --------------------------------------

@pytest.mark.parametrize("halt_state", ["paused", "stopped"])
def test_pause_or_stop_halts_all_progression(
    home, source_repo, conn, local_site, mock_agent, example_playbook, halt_state
):
    """A paused/stopped run does NO claim/reduce/advance/seed; only housekeeping."""
    from engine import crew, dispatch, queue
    from engine.models import Run

    host = local_site.discover_hosts()[0]
    issues_path = home / "issues.json"
    fixtures.write_canned_issues(issues_path)

    run_id = "example-halt"
    config = {"issue_filters": {"path": str(issues_path)}}
    _mk_run(conn, run_id, config=config, phase="work", state=halt_state)

    run = Run(id=run_id, playbook="example", site="local", base_ref="HEAD",
              config=config, phase="work", reductions=[])
    queue.seed_tickets(conn, run, example_playbook, local_site)
    crew.add(conn, local_site, mock_agent, host=host, base_ref="HEAD", now=1000.0)

    dispatch.master_loop(
        conn, run_id, example_playbook, local_site, mock_agent, "HEAD",
        hosts=[host], now=1000.0, max_cycles=3,
    )

    # No progression: run state unchanged, no dispatch, no reductions.
    assert _run_state(conn, run_id) == halt_state
    states = _ticket_states(conn, run_id)
    assert all(s == "queued" for s in states.values()), states
    n_reductions = conn.execute(
        "SELECT COUNT(*) FROM reductions WHERE run_id=?", (run_id,)
    ).fetchone()[0]
    assert n_reductions == 0
    n_attempts = conn.execute(
        """SELECT COUNT(*) FROM attempts a JOIN tickets t ON t.id=a.ticket_id
           WHERE t.run_id=?""",
        (run_id,),
    ).fetchone()[0]
    assert n_attempts == 0  # nothing was ever dispatched


def test_resume_lets_a_paused_run_reach_done(
    home, source_repo, conn, local_site, mock_agent, example_playbook
):
    """A paused run makes no progress; after resume the master loop drives it done."""
    from engine import crew, dispatch, queue
    from engine.models import Run

    host = local_site.discover_hosts()[0]
    issues_path = home / "issues.json"
    fixtures.write_canned_issues(issues_path)

    run_id = "example-resume"
    config = {"issue_filters": {"path": str(issues_path)}}
    _mk_run(conn, run_id, config=config, phase="work", state="paused")

    run = Run(id=run_id, playbook="example", site="local", base_ref="HEAD",
              config=config, phase="work", reductions=[])
    queue.seed_tickets(conn, run, example_playbook, local_site)
    crew.add(conn, local_site, mock_agent, host=host, base_ref="HEAD", now=1000.0)

    # While paused: no progress.
    dispatch.master_loop(
        conn, run_id, example_playbook, local_site, mock_agent, "HEAD",
        hosts=[host], now=1000.0, max_cycles=2,
    )
    assert _run_state(conn, run_id) == "paused"

    # Resume, then drive to done.
    queue.set_run_state(conn, run_id, "running", now=1000.0)
    dispatch.master_loop(
        conn, run_id, example_playbook, local_site, mock_agent, "HEAD",
        hosts=[host], now=1000.0, max_cycles=10,
    )
    assert _run_state(conn, run_id) == "done"


# --- stuck run -> failed -------------------------------------------------

class _StuckPlaybook:
    """A single-phase playbook that can never advance or complete: seeds tickets
    that all deterministically fail, next_phase()==None, is_done()==False."""

    name = "stuck"
    phases = ["only"]

    def seed(self, run, site):
        n = run.config.get("n", 2)
        scenario = run.config.get("scenario", "driver_error")
        return [
            Ticket(id=f"{run.id}/t-{i}", run_id=run.id, phase="only",
                   state="queued", resource_req="cpu", priority=0.0, attempts=0,
                   payload={"scenario": scenario})
            for i in range(n)
        ]

    def payload_schema(self, phase):
        return {"type": "object"}

    def result_schema(self, phase):
        return {"type": "object"}

    def driver(self, phase):
        return Driver(command=None, args={}, loop=None)

    def reduce(self, run, phase, findings, site):
        return []

    def verify(self, run, ticket, result, site):
        return True

    def next_phase(self, run):
        return None

    def is_done(self, run):
        return False


def test_stuck_run_transitions_to_failed(
    home, source_repo, conn, local_site, mock_agent
):
    """No actionable tickets + next_phase None + not is_done -> run failed."""
    from engine import crew, dispatch, queue
    from engine.models import Run

    host = local_site.discover_hosts()[0]
    pb = _StuckPlaybook()

    run_id = "stuck-1"
    _mk_run(conn, run_id, playbook="stuck", config={"n": 2}, phase="only")
    run = Run(id=run_id, playbook="stuck", site="local", base_ref="HEAD",
              config={"n": 2}, phase="only", reductions=[])
    queue.seed_tickets(conn, run, pb, local_site)
    crew.add(conn, local_site, mock_agent, host=host, base_ref="HEAD", now=1000.0)

    dispatch.master_loop(
        conn, run_id, pb, local_site, mock_agent, "HEAD",
        hosts=[host], now=1000.0, max_cycles=5,
    )

    assert _run_state(conn, run_id) == "failed"
    states = _ticket_states(conn, run_id)
    assert all(s == "failed" for s in states.values()), states


# --- no-ship guard genuinely blocks a push ------------------------------

def test_no_ship_guard_blocks_git_push(home, source_repo, local_site):
    """After provision, `git push` with the guard shims on PATH exits non-zero and
    the real git never runs (no push performed)."""
    host = local_site.discover_hosts()[0]
    local_site.provision(host, "HEAD")

    # The guard shim dir must be real + reflected by health.
    guard_dir = Path(local_site.guard_bin_dir(host))
    assert guard_dir.is_dir()
    for shim in ("git", "sl", "jf", "arc", "hg"):
        p = guard_dir / shim
        assert p.exists() and os.access(p, os.X_OK), f"missing guard shim {shim}"

    report = local_site.health(host, __import__("testkit").mock_agent.MockAgent())
    assert report.guard_installed is True

    # Run `git push` inside the provisioned workspace with the guard on PATH.
    workspace = home  # cwd doesn't matter; a git repo makes it realistic
    env = {**os.environ, "PATH": str(guard_dir) + os.pathsep + os.environ["PATH"]}
    proc = subprocess.run(
        ["git", "push", "origin", "HEAD"],
        cwd=str(source_repo), env=env, capture_output=True, text=True,
    )
    assert proc.returncode != 0, "guard must make `git push` fail"
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert "no-ship" in combined.lower() or "guard" in combined.lower(), combined
    # The real git never ran, so we should NOT see git's own push diagnostics.
    assert "does not appear to be a git repository" not in combined


def test_guard_reflects_reality_before_provision(home, source_repo, local_site):
    """Before provision the shims are absent, so guard_installed is False."""
    host = "not-provisioned-host"
    from testkit.mock_agent import MockAgent

    report = local_site.health(host, MockAgent())
    assert report.guard_installed is False
    guard_check = next(c for c in report.checks if c.name == "guard")
    assert guard_check.ok is False


# --- contract violation NO-GO -------------------------------------------

class _BadSchemaPlaybook:
    """Its payload_schema rejects the seeded payload -> envelope ContractError."""

    name = "bad"
    phases = ["only"]

    def seed(self, run, site):
        return [
            Ticket(id=f"{run.id}/t-0", run_id=run.id, phase="only", state="queued",
                   resource_req="cpu", priority=0.0, attempts=0, payload={})
        ]

    def payload_schema(self, phase):
        return {"type": "object", "required": ["must_have"]}

    def result_schema(self, phase):
        return {"type": "object"}

    def driver(self, phase):
        return Driver(command=None, args={}, loop=None)

    def reduce(self, run, phase, findings, site):
        return []

    def verify(self, run, ticket, result, site):
        return True

    def next_phase(self, run):
        return None

    def is_done(self, run):
        return False


def test_malformed_envelope_nogos_ticket_terminally(
    home, source_repo, conn, local_site, mock_agent
):
    """A ticket that fails envelope validation aborts as contract_fail (terminal),
    with no infinite loop."""
    from engine import crew, dispatch, queue
    from engine.models import Run

    host = local_site.discover_hosts()[0]
    pb = _BadSchemaPlaybook()

    run_id = "bad-1"
    _mk_run(conn, run_id, playbook="bad", phase="only")
    run = Run(id=run_id, playbook="bad", site="local", base_ref="HEAD",
              config={}, phase="only", reductions=[])
    queue.seed_tickets(conn, run, pb, local_site)
    crew.add(conn, local_site, mock_agent, host=host, base_ref="HEAD", now=1000.0)

    dispatch.master_loop(
        conn, run_id, pb, local_site, mock_agent, "HEAD",
        hosts=[host], now=1000.0, max_cycles=5,
    )

    states = _ticket_states(conn, run_id)
    assert states == {"bad-1/t-0": "failed"}, states
    reason = conn.execute(
        "SELECT termination_reason FROM attempts WHERE ticket_id='bad-1/t-0'"
    ).fetchone()[0]
    assert reason == "contract_fail"
    # Run terminated (no hang): stuck -> failed.
    assert _run_state(conn, run_id) == "failed"


def test_malformed_result_nogos_ticket_terminally(
    home, source_repo, conn, local_site, mock_agent
):
    """A deterministically contract-failing RESULT (mock scenario) aborts the
    ticket as driver_failed/contract_fail (terminal), no infinite loop."""
    from engine import crew, dispatch, queue
    from engine.models import Run

    host = local_site.discover_hosts()[0]
    pb = _StuckPlaybook()  # single phase, never advances/completes

    run_id = "cfail-1"
    config = {"n": 1, "scenario": "contract_fail"}
    _mk_run(conn, run_id, playbook="stuck", config=config, phase="only")
    run = Run(id=run_id, playbook="stuck", site="local", base_ref="HEAD",
              config=config, phase="only", reductions=[])
    queue.seed_tickets(conn, run, pb, local_site)
    crew.add(conn, local_site, mock_agent, host=host, base_ref="HEAD", now=1000.0)

    dispatch.master_loop(
        conn, run_id, pb, local_site, mock_agent, "HEAD",
        hosts=[host], now=1000.0, max_cycles=5,
    )

    states = _ticket_states(conn, run_id)
    assert states == {"cfail-1/t-0": "failed"}, states
    row = conn.execute(
        "SELECT outcome, termination_reason FROM attempts WHERE ticket_id='cfail-1/t-0'"
    ).fetchone()
    assert row == ("driver_failed", "contract_fail"), row
    assert _run_state(conn, run_id) == "failed"
