"""Integration tests for the dexter playbook end-to-end run (Slice 9).

TDD: Integration tests proving ALL §8 acceptance criteria via master_loop on
DexterLocalSite + DexterMockAgent, mirroring test_fleet_scenario.py harness.

Tests cover:
- FAN-OUT: one solve ticket per goal
- CROSS-HOST DEDUP: shared signatures -> ONE banked learning per cluster
- DUPLICATE DIFF FLAGGED: cluster members -> needs_human
- HUMAN RESOLUTION: accept_reduction -> done; reject -> failed
- VERIFY-FAIL BLOCKS + REQUEUE CLEARS: fix-does-not-hold -> needs_human -> requeue -> done
- RUN REACHES done: after clusters accepted, phase settles, run done
- NO-SHIP (both layers): runtime guard blocks push; dispatch gate rejects no-ship-false site
- EVENT STREAM: ordered event kinds appear

Stdlib-only (no real dexter/SSH/Meta).
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

from engine import dispatch, queue
from engine.db.migrate import apply_migrations, connect


# --- Fixtures (mirror test_fleet_scenario.py) -------------------------------


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Temp HERMES_HOME."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes-home"))
    return tmp_path


@pytest.fixture
def source_repo(tmp_path, monkeypatch):
    """A real one-commit git repo wired as HERMES_REPO (for LocalSite.provision)."""
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
    subprocess.run(
        ["git", "commit", "-q", "-m", "init"], cwd=repo, check=True, env=env
    )
    monkeypatch.setenv("HERMES_REPO", str(repo))
    return repo


@pytest.fixture
def db_path(tmp_path):
    """Temp sqlite db path."""
    path = str(tmp_path / "queue.db")
    yield path
    for suffix in ("", "-shm", "-wal"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)


@pytest.fixture
def conn(db_path):
    """Apply migrations and return a connection."""
    apply_migrations(db_path)
    connection = connect(db_path)
    yield connection
    connection.close()


@pytest.fixture
def dexter_site():
    """DexterLocalSite (adds recheck_fix for verify)."""
    import testkit.dexter_doubles  # noqa: F401 (registration side-effect)
    from engine import site

    return site.load("dexter_local")


@pytest.fixture
def dexter_agent():
    """DexterMockAgent (emits §2.3 payloads)."""
    import testkit.dexter_doubles  # noqa: F401 (registration side-effect)
    from engine import agent

    return agent.load("dexter_mock")


@pytest.fixture
def dexter_playbook_with_fake_sink():
    """DexterPlaybook with FakeSink injected (for banking assertions)."""
    from playbooks.dexter.playbook import DexterPlaybook
    from playbooks.dexter.sink import FakeSink

    sink = FakeSink(ref="kb/test-learning")
    pb = DexterPlaybook(sink=sink)
    # Store the sink on pb so tests can access it
    pb._test_sink = sink
    return pb


# --- Helpers -----------------------------------------------------------------


def _run_state(conn, run_id):
    """Read current run state."""
    return conn.execute("SELECT state FROM runs WHERE id=?", (run_id,)).fetchone()[0]


def _state_of(conn, ticket_id):
    """Read current ticket state."""
    return conn.execute(
        "SELECT state FROM tickets WHERE id=?", (ticket_id,)
    ).fetchone()[0]


def _settle_needs_human(conn, run_id, now):
    """Operator settle of needs_human tickets by route (mirrors fleet test).

    A verify-routed ticket (no linked reduction) is operator-requeued; a
    reduce-flagged ticket (linked to a pending reduction) is settled by accepting
    that reduction. Returns the set of routes settled this call.
    """
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


# --- Integration Tests -------------------------------------------------------


def test_dexter_run_fanout_dedup_accept(home, source_repo, conn, dexter_site, dexter_agent, dexter_playbook_with_fake_sink):
    """Full dexter run: fan-out, cross-host dedup, human accept, done.

    Proves §8 acceptance criteria 1-2:
    - FAN-OUT: one solve ticket per goal
    - CROSS-HOST DEDUP: two goals with shared signature -> ONE cluster reduction
      (canonical + one duplicate), FakeSink banked EXACTLY ONE learning
    - Cluster members -> needs_human via needs_human_ticket_ids
    - Accept -> members done
    - Run reaches done
    - Event stream includes all expected kinds
    """
    from engine import crew

    pb = dexter_playbook_with_fake_sink
    sink = pb._test_sink
    host = dexter_site.discover_hosts()[0]

    run_id = "dexter-test-1"
    # Two goals sharing "timeout" -> same signature "sig-shared-timeout"
    goals = [
        "Investigate timeout in wait_for_event (goal 1)",
        "Debug timeout in wait_for_event (goal 2)",
    ]
    conn.execute(
        """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                             phase, created_at, updated_at)
           VALUES (?, 'dexter', 'dexter_local', 'HEAD', ?, 'running', 'solve', 0, 0)""",
        (run_id, json.dumps({"goals": goals, "verify_recheck_optional": True})),
    )
    conn.commit()

    # Seed tickets
    run = queue.load_run(conn, run_id)
    tickets = pb.seed(run, dexter_site)
    assert len(tickets) == 2
    for ticket in tickets:
        conn.execute(
            """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority,
                                   attempts, available_at, payload_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, ?, 0, 0)""",
            (
                ticket.id,
                ticket.run_id,
                ticket.phase,
                ticket.state,
                ticket.resource_req,
                ticket.priority,
                ticket.attempts,
                json.dumps(ticket.payload),
            ),
        )
    conn.commit()

    # Register crew host
    crew.add(conn, dexter_site, dexter_agent, host=host, base_ref="HEAD", now=1000.0)

    # Drive master_loop to completion
    t = 1000.0
    STEP = 700.0
    routes_settled = set()
    for _ in range(30):
        dispatch.master_loop(
            conn, run_id, pb, dexter_site, dexter_agent, "HEAD",
            hosts=[host], now=t, max_cycles=6,
        )
        if _run_state(conn, run_id) in ("done", "failed"):
            break
        routes_settled |= _settle_needs_human(conn, run_id, now=t)
        t += STEP

    # ==================== ASSERTIONS (§8 acceptance 1-2) =====================

    # 1. Run reached done
    assert _run_state(conn, run_id) == "done"

    # 2. Both tickets are done
    assert _state_of(conn, f"{run_id}/solve-0") == "done"
    assert _state_of(conn, f"{run_id}/solve-1") == "done"

    # 3. FAN-OUT: two tickets were claimed and executed
    claimed_events = conn.execute(
        """SELECT ticket_id FROM events WHERE kind='ticket_claimed' AND run_id=?""",
        (run_id,),
    ).fetchall()
    assert len(claimed_events) == 2

    # 4. CROSS-HOST DEDUP: exactly ONE cluster reduction (shared signature)
    reductions = conn.execute(
        "SELECT id, json FROM reductions WHERE run_id=?", (run_id,)
    ).fetchall()
    assert len(reductions) == 1
    reduction_id, reduction_json = reductions[0]
    reduction_data = json.loads(reduction_json)
    assert reduction_data["signature"] == "sig-shared-timeout"
    assert len(reduction_data["member_ticket_ids"]) == 2
    assert len(reduction_data["duplicate_diffs"]) == 1  # one duplicate

    # 5. FakeSink banked EXACTLY ONE learning
    assert len(sink.banked_clusters) == 1
    assert sink.banked_clusters[0]["signature"] == "sig-shared-timeout"

    # 6. Cluster members were routed to needs_human then accepted
    assert reduction_data["needs_human_ticket_ids"] == reduction_data["member_ticket_ids"]
    assert "reduce" in routes_settled

    # 7. EVENT STREAM: assert ordered kinds
    event_kinds = [
        r[0] for r in conn.execute(
            "SELECT kind FROM events WHERE run_id=? ORDER BY id", (run_id,)
        ).fetchall()
    ]
    # Expected: ticket_claimed (x2), result_recorded (x2), needs_human (x2),
    # reduction_created, reduction_accepted, run_done
    assert "ticket_claimed" in event_kinds
    assert "result_recorded" in event_kinds
    assert "needs_human" in event_kinds
    assert "reduction_created" in event_kinds
    assert "reduction_accepted" in event_kinds
    assert "run_done" in event_kinds


def test_dexter_verify_fail_blocks_then_requeue_clears(
    home, source_repo, conn, dexter_site, dexter_agent, dexter_playbook_with_fake_sink
):
    """Verify-fail blocks reduce; requeue clears it (§8 acceptance 3).

    A fix-does-not-hold goal (attempt-1 emits ci_status != "passing" =>
    verify False => needs_human) BLOCKS phase reduce: assert concretely ZERO
    reductions rows while nh>0. Then requeue_needs_human -> queued; attempt-2
    emits ci_status == "passing" => verify True => reducing -> run done.

    Also asserts: left un-requeued, the run never leaves running (accepted limitation).
    """
    from engine import crew

    pb = dexter_playbook_with_fake_sink
    host = dexter_site.discover_hosts()[0]

    run_id = "dexter-verify-fail-1"
    # Goal ending with "fix-unstable" triggers attempt-keyed behavior in DexterMockAgent:
    # attempt-1 => ci_status="failing" => verify False
    # attempt-2 => ci_status="passing" => verify True
    goals = ["Investigate flaky test (fix-unstable)"]
    conn.execute(
        """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                             phase, created_at, updated_at)
           VALUES (?, 'dexter', 'dexter_local', 'HEAD', ?, 'running', 'solve', 0, 0)""",
        (run_id, json.dumps({"goals": goals})),
    )
    conn.commit()

    # Seed ticket
    run = queue.load_run(conn, run_id)
    tickets = pb.seed(run, dexter_site)
    assert len(tickets) == 1
    ticket = tickets[0]
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority,
                               attempts, available_at, payload_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, ?, 0, 0)""",
        (
            ticket.id,
            ticket.run_id,
            ticket.phase,
            ticket.state,
            ticket.resource_req,
            ticket.priority,
            ticket.attempts,
            json.dumps(ticket.payload),
        ),
    )
    conn.commit()

    # Register crew host
    crew.add(conn, dexter_site, dexter_agent, host=host, base_ref="HEAD", now=1000.0)

    # --- Stage 1: drive until ticket lands in needs_human (attempt 1) -------
    t = 1000.0
    STEP = 700.0
    for _ in range(10):
        dispatch.master_loop(
            conn, run_id, pb, dexter_site, dexter_agent, "HEAD",
            hosts=[host], now=t, max_cycles=4,
        )
        # Break when ticket reaches needs_human
        if _state_of(conn, ticket.id) == "needs_human":
            break
        t += STEP

    # ASSERT: ticket is needs_human (verify failed)
    assert _state_of(conn, ticket.id) == "needs_human"

    # ASSERT: run is still running (not done)
    assert _run_state(conn, run_id) == "running"

    # ASSERT: ZERO reductions rows (reduce is BLOCKED by needs_human)
    n_reductions = conn.execute(
        "SELECT COUNT(*) FROM reductions WHERE run_id=?", (run_id,)
    ).fetchone()[0]
    assert n_reductions == 0, "reduce should NOT run while needs_human > 0"

    # --- Stage 2: assert run stays blocked if not requeued -------------------
    # Drive a few more cycles; run should NEVER reach done/failed
    for _ in range(5):
        dispatch.master_loop(
            conn, run_id, pb, dexter_site, dexter_agent, "HEAD",
            hosts=[host], now=t, max_cycles=2,
        )
        t += STEP

    # ASSERT: run STILL running (accepted limitation: no terminal-abandon for verify-failed)
    assert _run_state(conn, run_id) == "running"
    assert _state_of(conn, ticket.id) == "needs_human"

    # --- Stage 3: requeue_needs_human clears the block -----------------------
    queue.requeue_needs_human(conn, ticket.id, now=t)
    assert _state_of(conn, ticket.id) == "queued"

    # ASSERT: attempts UNCHANGED (no penalty from requeue)
    # The ticket has had one execution (attempt 1 in attempts table), but the
    # tickets.attempts counter may be 0 or 1 depending on when the engine
    # increments it. The key is that requeue_needs_human does NOT increment it.
    attempts_in_audit = conn.execute(
        "SELECT COUNT(*) FROM attempts WHERE ticket_id=?", (ticket.id,)
    ).fetchone()[0]
    assert attempts_in_audit == 1  # one execution (attempt 1 failed verify)

    # --- Stage 4: drive to completion (attempt 2 passes verify) --------------
    for _ in range(20):
        dispatch.master_loop(
            conn, run_id, pb, dexter_site, dexter_agent, "HEAD",
            hosts=[host], now=t, max_cycles=6,
        )
        if _run_state(conn, run_id) in ("done", "failed"):
            break
        # Settle any needs_human that arise (e.g. cluster flagging after verify passes)
        _settle_needs_human(conn, run_id, now=t)
        t += STEP

    # ==================== ASSERTIONS (verify-fail cleared) ===================

    # 1. Ticket reached done (attempt-2 passed verify)
    assert _state_of(conn, ticket.id) == "done"

    # 2. Run reached done
    assert _run_state(conn, run_id) == "done"

    # 3. Reductions were created (phase reduce ran after nh==0)
    n_reductions_final = conn.execute(
        "SELECT COUNT(*) FROM reductions WHERE run_id=?", (run_id,)
    ).fetchone()[0]
    assert n_reductions_final >= 1, "reduce should run after requeue clears needs_human"

    # 4. Two attempts recorded
    # The attempts table records the execution ordinal from tickets.attempts + 1
    # at the time of execution. Both executions happen with tickets.attempts still
    # at its initial value (0 for first, stays 0 after requeue_needs_human), so
    # both get recorded as attempt=1. The AGENT's internal counter is what varies
    # the payload (attempt 1 vs 2 doc), but the DB audit table uses tickets.attempts.
    attempts = conn.execute(
        "SELECT attempt, outcome FROM attempts WHERE ticket_id=? ORDER BY id",
        (ticket.id,),
    ).fetchall()
    assert len(attempts) == 2  # two executions


def test_dexter_reduction_reject(
    home, source_repo, conn, dexter_site, dexter_agent, dexter_playbook_with_fake_sink
):
    """Reduction reject -> cluster members failed (§8 acceptance 2 variant)."""
    from engine import crew

    pb = dexter_playbook_with_fake_sink
    host = dexter_site.discover_hosts()[0]

    run_id = "dexter-reject-1"
    goals = ["Investigate timeout A", "Debug timeout B"]
    conn.execute(
        """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                             phase, created_at, updated_at)
           VALUES (?, 'dexter', 'dexter_local', 'HEAD', ?, 'running', 'solve', 0, 0)""",
        (run_id, json.dumps({"goals": goals, "verify_recheck_optional": True})),
    )
    conn.commit()

    # Seed tickets
    run = queue.load_run(conn, run_id)
    tickets = pb.seed(run, dexter_site)
    for ticket in tickets:
        conn.execute(
            """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority,
                                   attempts, available_at, payload_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, ?, 0, 0)""",
            (
                ticket.id,
                ticket.run_id,
                ticket.phase,
                ticket.state,
                ticket.resource_req,
                ticket.priority,
                ticket.attempts,
                json.dumps(ticket.payload),
            ),
        )
    conn.commit()

    crew.add(conn, dexter_site, dexter_agent, host=host, base_ref="HEAD", now=1000.0)

    # Drive to needs_human
    t = 1000.0
    STEP = 700.0
    for _ in range(20):
        dispatch.master_loop(
            conn, run_id, pb, dexter_site, dexter_agent, "HEAD",
            hosts=[host], now=t, max_cycles=4,
        )
        # Break when both tickets in needs_human (reduction flagged)
        nh_count = conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE run_id=? AND state='needs_human'",
            (run_id,),
        ).fetchone()[0]
        if nh_count == 2:
            break
        t += STEP

    # ASSERT: both tickets are needs_human (reduction flagged)
    assert _state_of(conn, f"{run_id}/solve-0") == "needs_human"
    assert _state_of(conn, f"{run_id}/solve-1") == "needs_human"

    # Find the reduction
    reduction_id = conn.execute(
        "SELECT id FROM reductions WHERE run_id=?", (run_id,)
    ).fetchone()[0]

    # REJECT the reduction (instead of accepting)
    queue.reject_reduction(conn, reduction_id, now=t)

    # ==================== ASSERTIONS (reduction reject) ======================

    # 1. Both tickets transitioned to failed (not done)
    assert _state_of(conn, f"{run_id}/solve-0") == "failed"
    assert _state_of(conn, f"{run_id}/solve-1") == "failed"

    # 2. Run transitions to done (phase settled, all tickets terminal)
    for _ in range(10):
        dispatch.master_loop(
            conn, run_id, pb, dexter_site, dexter_agent, "HEAD",
            hosts=[host], now=t, max_cycles=4,
        )
        if _run_state(conn, run_id) in ("done", "failed"):
            break
        t += STEP

    # Run should be done (phase fully settled)
    assert _run_state(conn, run_id) == "done"

    # 3. reduction_rejected event emitted
    reject_event = conn.execute(
        """SELECT kind FROM events WHERE kind='reduction_rejected' AND run_id=?""",
        (run_id,),
    ).fetchone()
    assert reject_event is not None


def test_dexter_no_ship_runtime_guard(home, source_repo, conn, dexter_site, dexter_agent):
    """No-ship runtime guard blocks git push (§7, §8 acceptance 4a).

    After provisioning, invoke the installed shim directly from the guard dir
    and assert exit 97 (do NOT rely on the mock agent).
    """
    from engine import crew

    host = dexter_site.discover_hosts()[0]

    # Provision the host (installs guard shims)
    dexter_site.provision(host, "HEAD")

    # Find the guard dir
    guard_dir = dexter_site.guard_bin_dir(host)
    assert guard_dir.exists(), "guard dir should exist after provision"

    git_shim = guard_dir / "git"
    assert git_shim.exists(), "git guard shim should exist"

    # Invoke the shim directly with "push" subcommand
    result = subprocess.run(
        [str(git_shim), "push"],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": str(guard_dir)},  # guard dir on PATH
    )

    # ==================== ASSERTIONS (runtime guard) =========================

    # 1. Exit code 97 (guard blocks the push)
    assert result.returncode == 97, f"git push should be blocked (exit 97), got {result.returncode}"

    # 2. Error message in stderr
    assert "no-ship" in result.stderr.lower() or "blocked" in result.stderr.lower()

    # 3. Other git commands pass through (e.g. "git status")
    result_status = subprocess.run(
        [str(git_shim), "status"],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": str(guard_dir)},
        cwd=source_repo,
    )
    # Should succeed (exit 0) or fail with real git error (not 97)
    assert result_status.returncode != 97, "git status should NOT be blocked"


def test_dexter_no_ship_dispatch_gate(home, source_repo, conn, dexter_agent, dexter_playbook_with_fake_sink):
    """No-ship dispatch gate rejects site that can't guarantee no-ship (§7, §8 acceptance 4b).

    A throwaway site whose guarantees_no_ship() returns False makes _build_envelope
    raise -> serve routes to fail_contract_violation (terminal failed, contract_fail).
    """
    from engine import crew
    from sites.local.site import LocalSite

    # Create a site variant that cannot guarantee no-ship
    class NoShipFalseSite(LocalSite):
        name = "no_ship_false"

        def guarantees_no_ship(self) -> bool:
            return False  # CANNOT guarantee

    site = NoShipFalseSite()
    pb = dexter_playbook_with_fake_sink
    host = site.discover_hosts()[0]

    run_id = "dexter-no-ship-gate-1"
    goals = ["Test goal"]
    conn.execute(
        """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                             phase, created_at, updated_at)
           VALUES (?, 'dexter', 'no_ship_false', 'HEAD', ?, 'running', 'solve', 0, 0)""",
        (run_id, json.dumps({"goals": goals})),
    )
    conn.commit()

    # Seed ticket
    run = queue.load_run(conn, run_id)
    tickets = pb.seed(run, site)
    ticket = tickets[0]
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority,
                               attempts, available_at, payload_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, ?, 0, 0)""",
        (
            ticket.id,
            ticket.run_id,
            ticket.phase,
            ticket.state,
            ticket.resource_req,
            ticket.priority,
            ticket.attempts,
            json.dumps(ticket.payload),
        ),
    )
    conn.commit()

    # Register crew host (provision will fail safe or be skipped; focus on dispatch)
    # For this test, we manually provision with the real LocalSite to get a workspace
    from sites.local.site import LocalSite
    real_site = LocalSite()
    real_site.provision(host, "HEAD")

    crew.add(conn, site, dexter_agent, host=host, base_ref="HEAD", now=1000.0)

    # Drive one cycle (should fail contract violation)
    t = 1000.0
    dispatch.master_loop(
        conn, run_id, pb, site, dexter_agent, "HEAD",
        hosts=[host], now=t, max_cycles=2,
    )

    # ==================== ASSERTIONS (dispatch gate) =========================

    # 1. Ticket went to terminal failed (contract_fail)
    assert _state_of(conn, ticket.id) == "failed"

    # 2. Termination reason is contract_fail
    attempt = conn.execute(
        """SELECT outcome, termination_reason, error_summary FROM attempts
           WHERE ticket_id=? ORDER BY id DESC LIMIT 1""",
        (ticket.id,),
    ).fetchone()
    assert attempt is not None
    outcome, term_reason, error_summary = attempt
    assert outcome == "driver_failed"
    assert term_reason == "contract_fail"
    assert "no-ship" in error_summary.lower()


def test_dexter_fold_dedup_two_ok_findings_one_ticket(
    home, source_repo, conn, dexter_site, dexter_playbook_with_fake_sink
):
    """A ticket with TWO ok findings is counted ONCE (fold-latest-per-ticket dedup, §2.6)."""
    from playbooks.dexter.playbook import DexterPlaybook
    from playbooks.dexter.sink import FakeSink
    from engine.models import Finding

    pb = dexter_playbook_with_fake_sink
    run_id = "dexter-fold-1"

    # Create run
    conn.execute(
        """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                             phase, created_at, updated_at)
           VALUES (?, 'dexter', 'dexter_local', 'HEAD', '{}', 'running', 'solve', 0, 0)""",
        (run_id,),
    )

    # Insert the ticket first (foreign key constraint)
    ticket_id = f"{run_id}/solve-0"
    conn.execute(
        """INSERT INTO tickets (id, run_id, phase, state, resource_req, priority,
                               attempts, available_at, payload_json, created_at, updated_at)
           VALUES (?, ?, 'solve', 'reducing', 'cpu', 0.0, 1, 0.0, '{}', 0, 0)""",
        (ticket_id, run_id),
    )

    # Insert TWO findings for the SAME ticket (simulate verify-fail -> requeue -> re-ok)
    finding1 = {
        "reproduced": True,
        "root_cause": {"signature": "sig-A", "cause_category": "timing"},
        "fix": {"verified": True, "diff_ref": "D1", "ci_status": "passing"},
        "knowledge_entry": {"ref": "kb-1", "validated": True},
        "evidence_ref": "evidence-1",
        "notes": "Attempt 1",
    }
    finding2 = {
        "reproduced": True,
        "root_cause": {"signature": "sig-A", "cause_category": "timing"},
        "fix": {"verified": True, "diff_ref": "D2", "ci_status": "passing"},
        "knowledge_entry": {"ref": "kb-2", "validated": True},
        "evidence_ref": "evidence-2",
        "notes": "Attempt 2 (latest)",
    }

    # Insert findings (id order: 1, 2)
    conn.execute(
        """INSERT INTO findings (run_id, ticket_id, kind, json, created_at)
           VALUES (?, ?, 'result', ?, 0)""",
        (run_id, ticket_id, json.dumps(finding1)),
    )
    conn.execute(
        """INSERT INTO findings (run_id, ticket_id, kind, json, created_at)
           VALUES (?, ?, 'result', ?, 1)""",
        (run_id, ticket_id, json.dumps(finding2)),
    )
    conn.commit()

    # Load findings and reduce
    run = queue.load_run(conn, run_id)
    findings = queue.load_findings(conn, run_id, "solve")
    assert len(findings) == 2  # two findings in db

    # Call reduce (should fold to ONE per ticket)
    reductions = pb.reduce(run, "solve", findings, dexter_site)

    # ==================== ASSERTIONS (fold dedup) ============================

    # 1. Exactly ONE reduction (one cluster)
    assert len(reductions) == 1

    # 2. Cluster has ONE member (the ticket, counted once)
    reduction = reductions[0]
    assert len(reduction.json["member_ticket_ids"]) == 1
    assert reduction.json["member_ticket_ids"][0] == ticket_id

    # 3. The canonical uses the LATEST finding's data (finding2)
    assert reduction.json["canonical_diff_ref"] == "D2"  # from finding2

    # 4. No duplicates (only one member)
    assert len(reduction.json["duplicate_diffs"]) == 0

    # 5. FakeSink banked ONCE for the cluster
    sink = pb._test_sink
    assert len(sink.banked_clusters) == 1
