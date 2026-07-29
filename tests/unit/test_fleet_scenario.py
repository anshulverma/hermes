"""Tests for testkit.scenarios.fleet fake scenario.

TDD: written FIRST. The deterministic scenario seeds a single-box run (LocalSite
+ MockAgent), drives master_loop to done, and asserts the expected rich outcome:
clustering, infra-retry-then-succeed, driver-failed terminal, both needs_human
routes exercised, parking contention.

The MockAgent extension keying by (ticket_id, attempt) is tested here.
"""
import json
import os
from pathlib import Path

import pytest

from engine.db.migrate import apply_migrations, connect
from engine.models import Run
from testkit import fixtures


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes-home"))
    return tmp_path


@pytest.fixture
def source_repo(tmp_path, monkeypatch):
    """A real git repo with one commit, wired up as HERMES_REPO."""
    import subprocess

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
    import sites.local  # noqa: F401
    from engine import site

    return site.load("local")


@pytest.fixture
def example_playbook():
    import testkit  # noqa: F401
    from engine import playbook as _pb

    return _pb.load("example")


def test_mock_agent_keyed_by_ticket_and_attempt():
    """MockAgent extended with (ticket_id, attempt) keying so retries yield different outcomes."""
    import hashlib
    from testkit.mock_agent import MockAgent

    # Scenario table keyed by (ticket_id, attempt)
    scenarios = {
        ("run-1/t-0", 1): ("infra_failed", "transport_error"),
        ("run-1/t-0", 2): ("ok", "goal_met"),
    }

    agent = MockAgent(scenarios=scenarios)

    # Compute correct payload_sha256 for each payload
    payload1 = {"attempt": 1}
    payload1_canon = json.dumps(payload1, sort_keys=True, separators=(",", ":"))
    payload1_sha256 = hashlib.sha256(payload1_canon.encode("utf-8")).hexdigest()

    payload2 = {"attempt": 2}
    payload2_canon = json.dumps(payload2, sort_keys=True, separators=(",", ":"))
    payload2_sha256 = hashlib.sha256(payload2_canon.encode("utf-8")).hexdigest()

    envelope1 = {
        "ticket_id": "run-1/t-0",
        "payload": payload1,
        "payload_sha256": payload1_sha256,
    }
    envelope2 = {
        "ticket_id": "run-1/t-0",
        "payload": payload2,
        "payload_sha256": payload2_sha256,
    }

    r1 = agent.parse_result("", envelope1)
    r2 = agent.parse_result("", envelope2)

    assert r1.outcome == "infra_failed"
    assert r2.outcome == "ok"


def test_fleet_scenario_generation():
    """build_fleet_scenario returns tickets and a MockAgent result table."""
    from testkit.scenarios.fleet import build_fleet_scenario

    tickets, agent = build_fleet_scenario(seed=42)

    # Should return ~40 tickets
    assert 35 <= len(tickets) <= 45

    # Tickets spread across cpu and gpu
    resource_reqs = {t.resource_req for t in tickets}
    assert "cpu" in resource_reqs
    assert "gpu" in resource_reqs

    # Agent has extended scenario table
    assert agent is not None
    assert hasattr(agent, "scenarios")


def _run_state(conn, run_id):
    return conn.execute("SELECT state FROM runs WHERE id=?", (run_id,)).fetchone()[0]


def _state_of(conn, ticket_id):
    return conn.execute(
        "SELECT state FROM tickets WHERE id=?", (ticket_id,)
    ).fetchone()[0]


def _settle_needs_human(conn, run_id, now):
    """Operator settle of needs_human tickets, by route.

    A verify-routed ticket (no linked reduction) is operator-requeued; a
    reduce-flagged ticket (linked to a pending reduction) is settled by accepting
    that reduction. Returns the set of routes settled this call.
    """
    from engine import queue

    routes = set()
    rows = conn.execute(
        "SELECT id, reduction_id FROM tickets WHERE run_id=? AND state='needs_human'",
        (run_id,),
    ).fetchall()
    for ticket_id, reduction_id in rows:
        if reduction_id is None:
            queue.requeue_needs_human(conn, ticket_id, now=now)
            routes.add("verify")
        else:
            review_state = conn.execute(
                "SELECT review_state FROM reductions WHERE id=?", (reduction_id,)
            ).fetchone()[0]
            if review_state == "pending":
                queue.accept_reduction(conn, reduction_id, now=now)
            routes.add("reduce")
    return routes


def test_fleet_scenario_single_box_run(home, source_repo, conn):
    """Drive the FULL fleet scenario to ``done`` on ONE box and assert every path.

    Mirrors the fleet harness convergence procedure without Docker: seed the
    full scenario, register a crew host with ample cpu but zero-then-limited gpu
    (forcing parking), drive ``dispatch.master_loop`` in a bounded controlled
    loop, settle both needs_human routes via the operator paths, and continue to
    completion. Then assert the rich outcome against the REAL db state.
    """
    from engine import crew, dispatch, queue
    from testkit.scenarios.fleet import build_fleet_scenario
    from testkit.scenarios.fleet_playbook import FleetPlaybook, GpuLimitedLocalSite

    tickets, mock_agent = build_fleet_scenario(seed=42)
    pb = FleetPlaybook()
    gpu_site = GpuLimitedLocalSite(gpu_capacity=0, cpu_capacity=16)
    host = gpu_site.discover_hosts()[0]

    run_id = "fleet-test-1"
    conn.execute(
        """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                             phase, created_at, updated_at)
           VALUES (?, 'fleet', 'local', 'HEAD', '{}', 'running', 'work', 0, 0)""",
        (run_id,),
    )
    # Insert ALL scenario tickets (no truncation). available_at=0 -> claimable now.
    for ticket in tickets:
        ticket.run_id = run_id
        conn.execute(
            """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority,
                                   attempts, available_at, payload_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, ?, 0, 0)""",
            (ticket.id, ticket.run_id, ticket.phase, ticket.state,
             ticket.resource_req, ticket.priority, ticket.attempts,
             json.dumps(ticket.payload)),
        )
    conn.commit()

    reverify_id = next(t.id for t in tickets if t.payload.get("needs_reverify"))
    reduce_review_id = next(t.id for t in tickets if t.payload.get("needs_reduce_review"))
    n_tickets = len(tickets)

    # Register the crew host (ample cpu, gpu capacity 0 -> gpu tickets will park).
    crew.add(conn, gpu_site, mock_agent, host=host, base_ref="HEAD", now=1000.0)

    # --- Stage 1: gpu capacity 0 forces parking; process everything else. -----
    # Advancing ``now`` between calls clears the infra retry backoff so the
    # infra-failed tickets can be re-claimed and succeed on attempt 2.
    t = 1000.0
    STEP = 700.0
    for _ in range(4):
        dispatch.master_loop(
            conn, run_id, pb, gpu_site, mock_agent, "HEAD",
            hosts=[host], now=t, max_cycles=4,
        )
        t += STEP

    # Dispatch has quiesced with gpu tickets genuinely parked (contention) and
    # the verify-routed ticket blocked in needs_human; the run is still running.
    assert _run_state(conn, run_id) == "running"
    parked_now = conn.execute(
        "SELECT COUNT(*) FROM tickets WHERE run_id=? AND state='parked'", (run_id,)
    ).fetchone()[0]
    assert parked_now > 0, "gpu tickets should be parked under zero gpu capacity"

    # --- Stage 2: regain gpu capacity and unpark the parked gpu tickets. ------
    gpu_site.gpu_capacity = 2
    queue.unpark_ready(conn, "gpu", now=t)
    conn.commit()

    # --- Stage 3: drive to completion, settling needs_human via operator paths.
    routes_settled = set()
    for _ in range(30):
        dispatch.master_loop(
            conn, run_id, pb, gpu_site, mock_agent, "HEAD",
            hosts=[host], now=t, max_cycles=6,
        )
        if _run_state(conn, run_id) in ("done", "failed"):
            break
        routes_settled |= _settle_needs_human(conn, run_id, now=t)
        t += STEP

    # ==================== RICH OUTCOME ASSERTIONS (real db) ==================

    # 1. The run reached ``done`` (not merely a terminal-or-running set).
    assert _run_state(conn, run_id) == "done"

    # 2. Every ticket is terminal (done/failed), and none were truncated.
    states = [
        r[0] for r in conn.execute(
            "SELECT state FROM tickets WHERE run_id=?", (run_id,)
        ).fetchall()
    ]
    assert len(states) == n_tickets == 40
    assert set(states) <= {"done", "failed"}, sorted(set(states))

    # 3. The engine produced ONE reductions row per distinct root_cause.signature
    #    among the findings it actually banked (real clustering, not a fixture claim).
    finding_sigs = [
        (json.loads(j).get("root_cause") or {}).get("signature", "unknown")
        for (j,) in conn.execute(
            "SELECT json FROM findings WHERE run_id=?", (run_id,)
        ).fetchall()
    ]
    distinct_sigs = set(finding_sigs)
    n_reductions = conn.execute(
        "SELECT COUNT(*) FROM reductions WHERE run_id=?", (run_id,)
    ).fetchone()[0]
    assert n_reductions == len(distinct_sigs), (n_reductions, sorted(distinct_sigs))
    assert n_reductions >= 2, "expected multiple signature clusters"
    # At least one cluster actually deduplicated several tickets (e.g. the gpu class).
    from collections import Counter
    assert max(Counter(finding_sigs).values()) > 1, "expected a multi-ticket cluster"

    # 4. At least one ticket shows attempt 1 infra_failed then attempt 2 ok, and
    #    that retry-then-succeed ticket is terminal ``done``.
    retried = conn.execute(
        """SELECT a1.ticket_id FROM attempts a1
           JOIN attempts a2 ON a2.ticket_id = a1.ticket_id
           WHERE a1.attempt=1 AND a1.outcome='infra_failed'
             AND a2.attempt=2 AND a2.outcome='ok'"""
    ).fetchall()
    assert retried, "expected an infra-retry-then-succeed ticket"
    assert _state_of(conn, retried[0][0]) == "done"

    # 5. At least one driver_failed ticket is terminal ``failed``.
    driver_failed = conn.execute(
        """SELECT t.id FROM tickets t JOIN attempts a ON a.ticket_id=t.id
           WHERE a.outcome='driver_failed' AND t.state='failed'"""
    ).fetchall()
    assert driver_failed, "expected a driver_failed terminal ticket"

    # 6. BOTH needs_human routes were REACHED (distinct emit sites) AND RESOLVED.
    verify_route = conn.execute(
        """SELECT COUNT(*) FROM events
           WHERE kind='needs_human' AND ticket_id=? AND message='re-verify override'""",
        (reverify_id,),
    ).fetchone()[0]
    assert verify_route >= 1, "verify=False needs_human route not reached"
    reduce_route = conn.execute(
        """SELECT COUNT(*) FROM events
           WHERE kind='needs_human' AND ticket_id=? AND message='reduction flagged for human'""",
        (reduce_review_id,),
    ).fetchone()[0]
    assert reduce_route >= 1, "reduction-flag needs_human route not reached"
    assert routes_settled == {"verify", "reduce"}, routes_settled
    assert _state_of(conn, reverify_id) in {"done", "failed"}
    assert _state_of(conn, reduce_review_id) in {"done", "failed"}

    # 7. At least one ticket was parked (gpu contention) and later reached ``done``.
    parked_events = conn.execute(
        """SELECT DISTINCT ticket_id FROM events
           WHERE kind='ticket_parked' AND run_id=?""",
        (run_id,),
    ).fetchall()
    assert parked_events, "expected at least one ticket_parked event"
    parked_ticket = parked_events[0][0]
    assert _state_of(conn, parked_ticket) == "done"
    parked_req = conn.execute(
        "SELECT resource_req FROM tickets WHERE id=?", (parked_ticket,)
    ).fetchone()[0]
    assert parked_req == "gpu"


def test_fleet_scenario_has_clustering():
    """Scenario includes tickets that share root_cause.signature for clustering."""
    from testkit.scenarios.fleet import build_fleet_scenario

    tickets, agent = build_fleet_scenario(seed=42)

    # Check that some tickets share a common field for clustering
    # (implementation detail: scenario should set up some duplicate signatures)
    signatures = [t.payload.get("signature") for t in tickets if "signature" in t.payload]
    assert len(signatures) > 0, "scenario should include clusterable tickets"

    # Should have some duplicates
    unique = len(set(signatures))
    total = len(signatures)
    assert unique < total, "scenario should have some duplicate signatures for clustering"


def test_fleet_scenario_has_failures():
    """Scenario includes both driver_failed and infra_failed tickets."""
    from testkit.scenarios.fleet import build_fleet_scenario

    tickets, agent = build_fleet_scenario(seed=42)

    # Check agent scenario table has failures
    scenarios_list = list(agent.scenarios.values())
    outcomes = [s[0] for s in scenarios_list]

    assert "driver_failed" in outcomes or any(
        "driver_error" in str(s) for s in scenarios_list
    ), "scenario should include driver failures"
    assert "infra_failed" in outcomes or any(
        "transport_error" in str(s) for s in scenarios_list
    ), "scenario should include infra failures"


def test_fleet_scenario_has_gpu_contention():
    """Scenario includes more gpu tickets than typical gpu capacity to force parking."""
    from testkit.scenarios.fleet import build_fleet_scenario

    tickets, agent = build_fleet_scenario(seed=42)

    gpu_tickets = [t for t in tickets if t.resource_req == "gpu"]
    # Should have enough gpu tickets to cause contention (> 2-4 typical gpu slots)
    assert len(gpu_tickets) > 4, "scenario should have enough gpu tickets to force parking"
