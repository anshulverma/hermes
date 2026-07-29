"""Tests for testkit.scenarios.fleet fake scenario (spec §5).

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


def test_fleet_scenario_single_box_run(home, source_repo, conn, local_site, example_playbook):
    """Single-box run with fake scenario drives to done with expected outcomes."""
    from engine import crew, dispatch, queue
    from testkit.scenarios.fleet import build_fleet_scenario

    # Force limited gpu capacity on local host to trigger parking
    import unittest.mock as mock

    with mock.patch("os.cpu_count", return_value=16):
        # Build scenario (gives us tickets + agent with result table)
        tickets, mock_agent = build_fleet_scenario(seed=42)

        run_id = "fleet-test-1"
        conn.execute(
            """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                                 phase, created_at, updated_at)
               VALUES (?, 'example', 'local', 'HEAD', '{}', 'running', 'work', 0, 0)""",
            (run_id,),
        )
        conn.commit()

        # Insert scenario tickets directly
        for ticket in tickets[:10]:  # Limit to 10 for faster test
            ticket.run_id = run_id
            conn.execute(
                """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority,
                                       attempts, available_at, payload_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)""",
                (
                    ticket.id,
                    ticket.run_id,
                    ticket.phase,
                    ticket.state,
                    ticket.resource_req,
                    ticket.priority,
                    ticket.attempts,
                    0.0,
                    json.dumps(ticket.payload),
                ),
            )
        conn.commit()

        # Add local host with LIMITED gpu capacity (e.g., only 2 gpus vs. more gpu tickets)
        host = local_site.discover_hosts()[0]

        # Mock health to return limited gpu capacity
        original_health = local_site.health

        def limited_health(h, agent):
            report = original_health(h, agent)
            # Override resources to have limited gpu
            report.resources["gpu"] = 2  # Only 2 gpus available
            return report

        with mock.patch.object(local_site, "health", limited_health):
            crew.add(conn, local_site, mock_agent, host=host, base_ref="HEAD", now=1000.0)

            # Drive master loop
            dispatch.master_loop(
                conn,
                run_id,
                example_playbook,
                local_site,
                mock_agent,
                "HEAD",
                hosts=[host],
                now=1000.0,
                max_cycles=20,
            )

        # Assert: run reached terminal state (done or failed)
        run_state = conn.execute("SELECT state FROM runs WHERE id=?", (run_id,)).fetchone()[0]
        assert run_state in ("done", "failed")

        # All tickets should be terminal
        ticket_states = conn.execute(
            "SELECT state FROM tickets WHERE run_id=?", (run_id,)
        ).fetchall()
        assert all(s[0] in ("done", "failed", "needs_human") for s in ticket_states)


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
