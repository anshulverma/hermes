"""Unit tests for engine.cli (§10).

Tests CLI subcommands via main([...]) against a temp HERMES_HOME.
"""
import json
import os
import sqlite3
import sys
import time
from io import StringIO
from pathlib import Path

import pytest

from engine import agent, config, playbook, site
from engine.cli import main
from engine.db import migrate
from testkit.fixtures import temp_hermes_home, write_canned_issues


def _conn():
    """Connect to queue.db in current HERMES_HOME (applying migrations)."""
    home = config.resolve_home()
    db_path = home / "queue.db"
    migrate.apply_migrations(str(db_path))
    return migrate.connect(str(db_path))


# --- fixtures ------------------------------------------------------------

@pytest.fixture
def setup_testkit():
    """Import testkit modules to register example/local/mock."""
    import testkit.example_playbook
    import testkit.mock_agent
    import sites.local.site
    # Return None; just ensure they're imported


# --- run --dry-run -------------------------------------------------------

def test_run_dry_run_seeds_no_dispatch(setup_testkit, capsys):
    """dry-run seeds tickets + prints report WITHOUT dispatching."""
    with temp_hermes_home() as home:
        # Seed the canned issues in the default location for kind=bug
        issues_path = home / "issues" / "bug.json"
        write_canned_issues(issues_path)

        # CLI: hermes run example --site local --agent mock --dry-run
        exit_code = main([
            "run", "example",
            "--site", "local",
            "--agent", "mock",
            "--dry-run",
        ])

        assert exit_code == 0, "dry-run should exit 0"

        # Check the DB: run created, tickets seeded, no attempts
        conn = _conn()
        runs = conn.execute("SELECT id, state FROM runs").fetchall()
        assert len(runs) == 1
        run_id, state = runs[0]
        assert state == "running"

        tickets = conn.execute("SELECT id, state FROM tickets WHERE run_id=?", (run_id,)).fetchall()
        assert len(tickets) == 3, "EchoPlaybook seeds 3 tickets from canned issues"
        for tid, tstate in tickets:
            assert tstate == "queued"

        attempts = conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
        assert attempts == 0, "dry-run should not dispatch (no attempts)"

        conn.close()

        # stdout should mention the seeded tickets
        captured = capsys.readouterr()
        assert "3" in captured.out or "tickets" in captured.out.lower()


# --- run (local, no dry-run) --------------------------------------------

def test_run_local_reaches_terminal(setup_testkit, capsys):
    """run (local, mock agent) drives to terminal state."""
    with temp_hermes_home() as home:
        issues_path = home / "issues" / "bug.json"
        write_canned_issues(issues_path)

        # CLI: hermes run example --site local --agent mock
        exit_code = main([
            "run", "example",
            "--site", "local",
            "--agent", "mock",
        ])

        assert exit_code == 0

        # Check: run terminal (done or failed), tickets processed
        conn = _conn()
        runs = conn.execute("SELECT id, state FROM runs").fetchall()
        assert len(runs) == 1
        run_id, state = runs[0]

        # Debug: check ticket states
        if state not in ("done", "failed"):
            tickets = conn.execute(
                "SELECT id, state FROM tickets WHERE run_id=?",
                (run_id,)
            ).fetchall()
            print(f"\nDEBUG: Run state={state}, tickets={tickets}")

        assert state in ("done", "failed"), f"expected terminal state, got {state}"

        # At least some tickets should be done
        done_tickets = conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE run_id=? AND state='done'",
            (run_id,)
        ).fetchone()[0]
        assert done_tickets > 0, "at least one ticket should be done"

        conn.close()


# --- run control (pause/resume/stop) ------------------------------------

def test_run_pause_resume_stop(setup_testkit, capsys):
    """run control actions change runs.state correctly."""
    with temp_hermes_home() as home:
        conn = _conn()
        now = time.time()
        # Insert a running run
        conn.execute(
            """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                                 phase, created_at, updated_at)
               VALUES (?, 'example', 'local', 'main', '{}', 'running', 'work', ?, ?)""",
            ("r1", now, now),
        )
        conn.commit()
        conn.close()

        # pause
        exit_code = main(["run", "pause", "r1"])
        assert exit_code == 0
        conn = _conn()
        state = conn.execute("SELECT state FROM runs WHERE id='r1'").fetchone()[0]
        assert state == "paused"
        conn.close()
        captured = capsys.readouterr()
        assert "paused" in captured.out.lower()

        # resume
        exit_code = main(["run", "resume", "r1"])
        assert exit_code == 0
        conn = _conn()
        state = conn.execute("SELECT state FROM runs WHERE id='r1'").fetchone()[0]
        assert state == "running"
        conn.close()
        captured = capsys.readouterr()
        assert "running" in captured.out.lower()

        # stop
        exit_code = main(["run", "stop", "r1"])
        assert exit_code == 0
        conn = _conn()
        state = conn.execute("SELECT state FROM runs WHERE id='r1'").fetchone()[0]
        assert state == "stopped"
        conn.close()
        captured = capsys.readouterr()
        assert "stopped" in captured.out.lower()


def test_run_resume_terminal_errors(setup_testkit, capsys):
    """resume of a terminal run exits non-zero."""
    with temp_hermes_home() as home:
        conn = _conn()
        now = time.time()
        conn.execute(
            """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                                 phase, created_at, updated_at)
               VALUES (?, 'example', 'local', 'main', '{}', 'done', 'work', ?, ?)""",
            ("r1", now, now),
        )
        conn.commit()
        conn.close()

        exit_code = main(["run", "resume", "r1"])
        assert exit_code != 0, "resume of terminal run should fail"
        captured = capsys.readouterr()
        # Error should be on stderr
        combined = (captured.out + captured.err).lower()
        assert "error" in combined or "illegal" in combined


# --- reduction accept/reject --------------------------------------------

def test_reduction_accept_reject(setup_testkit, capsys):
    """reduction accept/reject settle the reduction + needs_human tickets."""
    with temp_hermes_home() as home:
        conn = _conn()
        now = time.time()
        # run
        conn.execute(
            """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                                 phase, created_at, updated_at)
               VALUES (?, 'example', 'local', 'main', '{}', 'running', 'reduce', ?, ?)""",
            ("r1", now, now),
        )
        # reduction pending
        conn.execute(
            """INSERT INTO reductions (id, run_id, kind, json, review_state, created_at, updated_at)
               VALUES (1, 'r1', 'test', '{}', 'pending', ?, ?)""",
            (now, now),
        )
        # needs_human ticket linked to the reduction
        conn.execute(
            """INSERT INTO tickets
                 (id, run_id, phase, state, resource_req, priority, attempts,
                  available_at, tried_hosts, payload_json, reduction_id, created_at, updated_at)
               VALUES ('t1', 'r1', 'work', 'needs_human', 'cpu', 0, 0, 0, '[]', '{}', 1, ?, ?)""",
            (now, now),
        )
        conn.commit()
        conn.close()

        # accept
        exit_code = main(["reduction", "accept", "1"])
        assert exit_code == 0
        conn = _conn()
        red_state = conn.execute(
            "SELECT review_state FROM reductions WHERE id=1"
        ).fetchone()[0]
        assert red_state == "accepted"
        ticket_state = conn.execute("SELECT state FROM tickets WHERE id='t1'").fetchone()[0]
        assert ticket_state == "done", "accept should settle ticket to done"
        conn.close()
        captured = capsys.readouterr()
        assert "accept" in captured.out.lower()

        # reset to test reject
        conn = _conn()
        conn.execute("UPDATE reductions SET review_state='pending' WHERE id=1")
        conn.execute("UPDATE tickets SET state='needs_human' WHERE id='t1'")
        conn.commit()
        conn.close()

        # reject
        exit_code = main(["reduction", "reject", "1"])
        assert exit_code == 0
        conn = _conn()
        red_state = conn.execute(
            "SELECT review_state FROM reductions WHERE id=1"
        ).fetchone()[0]
        assert red_state == "rejected"
        ticket_state = conn.execute("SELECT state FROM tickets WHERE id='t1'").fetchone()[0]
        assert ticket_state == "failed", "reject should settle ticket to failed"
        conn.close()


# --- ticket requeue -----------------------------------------------------

def test_ticket_requeue(setup_testkit, capsys):
    """ticket requeue returns a needs_human ticket to queued."""
    with temp_hermes_home() as home:
        conn = _conn()
        now = time.time()
        conn.execute(
            """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                                 phase, created_at, updated_at)
               VALUES (?, 'example', 'local', 'main', '{}', 'running', 'work', ?, ?)""",
            ("r1", now, now),
        )
        # needs_human ticket (guard-routed, no reduction_id)
        conn.execute(
            """INSERT INTO tickets
                 (id, run_id, phase, state, resource_req, priority, attempts,
                  available_at, tried_hosts, payload_json, created_at, updated_at)
               VALUES ('t1', 'r1', 'work', 'needs_human', 'cpu', 0, 2, 0, '[]', '{}', ?, ?)""",
            (now, now),
        )
        conn.commit()
        conn.close()

        exit_code = main(["ticket", "requeue", "t1"])
        assert exit_code == 0

        conn = _conn()
        state = conn.execute("SELECT state FROM tickets WHERE id='t1'").fetchone()[0]
        assert state == "queued"
        # attempts should not be penalized (stays 2)
        attempts = conn.execute("SELECT attempts FROM tickets WHERE id='t1'").fetchone()[0]
        assert attempts == 2
        conn.close()


# --- crew add (health-gate) ---------------------------------------------

def test_crew_add_healthy_admits(setup_testkit, capsys):
    """crew add admits a healthy host."""
    with temp_hermes_home() as home:
        # local site's health always passes for the local host
        exit_code = main(["crew", "add", "localhost", "--site", "local", "--agent", "mock"])
        assert exit_code == 0

        conn = _conn()
        crew = conn.execute("SELECT id, state FROM crew WHERE id='localhost'").fetchone()
        assert crew is not None
        assert crew[1] == "idle"
        conn.close()

        captured = capsys.readouterr()
        assert "healthy" in captured.out.lower() or "admitted" in captured.out.lower()


# --- crew list ----------------------------------------------------------

def test_crew_list(setup_testkit, capsys):
    """crew list shows crew members."""
    with temp_hermes_home() as home:
        conn = _conn()
        now = time.time()
        conn.execute(
            """INSERT INTO crew (id, site, capabilities, resources_json, state, registered_at)
               VALUES ('h1', 'local', '[]', '{"cpu":2}', 'idle', ?)""",
            (now,),
        )
        conn.commit()
        conn.close()

        exit_code = main(["crew", "list", "--site", "local"])
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "h1" in captured.out


# --- status -------------------------------------------------------------

def test_status(setup_testkit, capsys):
    """status renders run/ticket/crew/lease summary from queue.db."""
    with temp_hermes_home() as home:
        conn = _conn()
        now = time.time()
        # seed a run + tickets
        conn.execute(
            """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                                 phase, created_at, updated_at)
               VALUES (?, 'example', 'local', 'main', '{}', 'running', 'work', ?, ?)""",
            ("r1", now, now),
        )
        conn.execute(
            """INSERT INTO tickets
                 (id, run_id, phase, state, resource_req, priority, attempts,
                  available_at, tried_hosts, payload_json, created_at, updated_at)
               VALUES ('t1', 'r1', 'work', 'queued', 'cpu', 0, 0, 0, '[]', '{}', ?, ?)""",
            (now, now),
        )
        conn.commit()
        conn.close()

        exit_code = main(["status"])
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "r1" in captured.out
        assert "running" in captured.out.lower()


def test_status_with_run_filter(setup_testkit, capsys):
    """status --run R filters to that run."""
    with temp_hermes_home() as home:
        conn = _conn()
        now = time.time()
        conn.execute(
            """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                                 phase, created_at, updated_at)
               VALUES (?, 'example', 'local', 'main', '{}', 'running', 'work', ?, ?)""",
            ("r1", now, now),
        )
        conn.execute(
            """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                                 phase, created_at, updated_at)
               VALUES (?, 'example', 'local', 'main', '{}', 'paused', 'work', ?, ?)""",
            ("r2", now, now),
        )
        conn.commit()
        conn.close()

        exit_code = main(["status", "--run", "r1"])
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "r1" in captured.out
        # r2 should not appear
        assert "r2" not in captured.out


# --- show ---------------------------------------------------------------

def test_show_ticket(setup_testkit, capsys):
    """show prints envelope/result/attempts for a ticket."""
    with temp_hermes_home() as home:
        conn = _conn()
        now = time.time()
        conn.execute(
            """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                                 phase, created_at, updated_at)
               VALUES (?, 'example', 'local', 'main', '{}', 'running', 'work', ?, ?)""",
            ("r1", now, now),
        )
        payload = {"test": "data"}
        conn.execute(
            """INSERT INTO tickets
                 (id, run_id, phase, state, resource_req, priority, attempts,
                  available_at, tried_hosts, payload_json, created_at, updated_at)
               VALUES ('t1', 'r1', 'work', 'done', 'cpu', 0, 1, 0, '["h1"]', ?, ?, ?)""",
            (json.dumps(payload), now, now),
        )
        # add an attempt
        conn.execute(
            """INSERT INTO attempts
                 (ticket_id, phase, host, attempt, started_at, ended_at,
                  outcome, termination_reason, result_ref, error_summary)
               VALUES ('t1', 'work', 'h1', 1, ?, ?, 'ok', 'goal_met', NULL, NULL)""",
            (now, now + 1),
        )
        conn.commit()
        conn.close()

        exit_code = main(["show", "t1"])
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "t1" in captured.out
        assert "done" in captured.out.lower()
        assert "h1" in captured.out


# --- serve (out of scope for unit tests, tested via integration) -------
# The serve command runs a blocking serve_loop; we won't test it in unit tests
# because it's an integration concern (tested in test_e2e.py).


# --- run --hosts parsing ------------------------------------------------

def test_run_hosts_parsed_and_used(setup_testkit, capsys):
    """run --hosts parses the comma-separated list and passes to master_loop."""
    with temp_hermes_home() as home:
        issues_path = home / "issues" / "bug.json"
        write_canned_issues(issues_path)

        # Two local hosts (both localhost entries, for simplicity)
        exit_code = main([
            "run", "example",
            "--site", "local",
            "--agent", "mock",
            "--hosts", "localhost,localhost",
            "--dry-run",
        ])

        assert exit_code == 0

        # The --hosts arg should be parsed; in dry-run mode we don't dispatch,
        # but we can check that the arg is accepted (no argparse error)
        captured = capsys.readouterr()
        assert "error" not in captured.out.lower()


# --- serve --host -------------------------------------------------------

def test_serve_processes_available_work(setup_testkit, capsys):
    """serve --host processes the claimable tickets for a run."""
    with temp_hermes_home() as home:
        # Seed a run + ticket manually
        conn = _conn()
        now = time.time()
        run_id = f"run-{int(now * 1000)}"
        conn.execute(
            """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                                 phase, created_at, updated_at)
               VALUES (?, 'example', 'local', 'main', '{}', 'running', 'work', ?, ?)""",
            (run_id, now, now),
        )
        # Add a queued ticket
        conn.execute(
            """INSERT INTO tickets
                 (id, run_id, phase, state, resource_req, priority, attempts,
                  available_at, tried_hosts, payload_json, created_at, updated_at)
               VALUES ('t1', ?, 'work', 'queued', 'cpu', 0, 0, 0, '[]', '{}', ?, ?)""",
            (run_id, now, now),
        )
        conn.commit()
        conn.close()

        # Add the host to crew
        main(["crew", "add", "localhost", "--site", "local", "--agent", "mock"])

        # Now serve for that host + run
        exit_code = main([
            "serve",
            "--host", "localhost",
            "--site", "local",
            "--agent", "mock",
            "--run", run_id,
        ])

        assert exit_code == 0, "serve should exit 0 on success"

        # Check that the ticket was processed (moved out of queued)
        conn = _conn()
        state = conn.execute("SELECT state FROM tickets WHERE id='t1'").fetchone()[0]
        # It should be in a terminal-ish state (done/failed) or reducing
        assert state != "queued", f"ticket should have been processed, got {state}"

        # An attempt should exist
        attempts = conn.execute(
            "SELECT COUNT(*) FROM attempts WHERE ticket_id='t1'"
        ).fetchone()[0]
        assert attempts > 0, "serve should have created at least one attempt"

        conn.close()


# --- traceback gating (HERMES_DEBUG) ------------------------------------

def test_error_traceback_gated_by_debug_env(setup_testkit, capsys, monkeypatch):
    """Top-level exception prints just the message unless HERMES_DEBUG=1."""
    with temp_hermes_home() as home:
        monkeypatch.delenv("HERMES_DEBUG", raising=False)

        # Force an exception by corrupting the database file
        db_path = config.resolve_home() / "queue.db"
        db_path.write_text("corrupted data")

        # This will trigger a database error that reaches the top-level handler
        exit_code = main(["status"])
        assert exit_code != 0

        captured = capsys.readouterr()
        combined = captured.out + captured.err
        # Should have "Error:" but NOT a full traceback (no "Traceback")
        assert "error" in combined.lower()
        assert "traceback" not in combined.lower(), "should not print traceback without HERMES_DEBUG"


def test_error_traceback_shown_with_debug_env(setup_testkit, capsys, monkeypatch):
    """With HERMES_DEBUG=1, exceptions print a full traceback."""
    with temp_hermes_home() as home:
        monkeypatch.setenv("HERMES_DEBUG", "1")

        # Force an exception by corrupting the database file
        db_path = config.resolve_home() / "queue.db"
        db_path.write_text("corrupted data")

        # This will trigger a database error that reaches the top-level handler
        exit_code = main(["status"])
        assert exit_code != 0

        captured = capsys.readouterr()
        combined = captured.out + captured.err
        # Should have both "Error:" and a traceback
        assert "error" in combined.lower()
        assert "traceback" in combined.lower(), "should print traceback with HERMES_DEBUG=1"
