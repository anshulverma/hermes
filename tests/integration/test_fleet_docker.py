"""Fleet integration harness — Docker/podman convergence test (spec §6, §7).

The flagship distributed-integration slice: it stands up SEVERAL worker nodes as
REAL containers and drives them, over REAL SSH, through one shared run (the
deterministic ``build_fleet_scenario``) until the fleet converges — proving the
distributed machinery the single-box tier cannot: the real ``ssh_transport``,
multi-host distribution with no double-claim (the driver here is synchronous
round-robin, so this proves distribution + no-double-claim, not concurrent claim-race
atomicity — that is covered by the queue unit tests), and host-down requeue.

Gated behind ``@pytest.mark.docker`` so ``pytest -m "not docker"`` skips it and
CI runs it only where Docker/podman is available. Approach (harness §3): host-as-
master with published ports. The TEST PROCESS is the master (queue.db on the
host); it seeds the scenario, configures an ``SSHSite`` pointing at the worker
containers (``localhost:220NN``), and drives the serve + reduce/advance loops
in-process, which ssh into the containers to run ``hermes serve-once --agent mock``.

Containers are ALWAYS torn down (try/finally: ``podman rm -f``).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.docker

# Prefer podman; fall back to docker. None -> skip.
_ENGINE = shutil.which("podman") or shutil.which("docker")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_IMAGE = "hermes-fleet-worker:pytest"
_NAME_PREFIX = "hermes-fleet-pytest"

# Logical host id -> (published host port, resources). All reachable at localhost.
_WORKERS = {
    "cpu-1": (22051, {"cpu": 4}),
    "cpu-2": (22052, {"cpu": 4}),
    "gpu-1": (22053, {"cpu": 4, "gpu": 2}),
}


# --- podman helpers ------------------------------------------------------

def _sh(*args, check=True, timeout=300):
    return subprocess.run(
        list(args), capture_output=True, text=True, check=check, timeout=timeout
    )


def _container_name(host: str) -> str:
    return f"{_NAME_PREFIX}-{host}"


def _rm_all():
    for host in _WORKERS:
        subprocess.run(
            [_ENGINE, "rm", "-f", _container_name(host)],
            capture_output=True, text=True,
        )


def _ssh_ready(port: int, identity: Path, attempts=60, delay=0.5) -> bool:
    opts = [
        "-i", str(identity), "-p", str(port),
        "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
        "-o", "BatchMode=yes", "-o", "ConnectTimeout=3",
    ]
    for _ in range(attempts):
        proc = subprocess.run(
            ["ssh", *opts, "root@localhost", "true"],
            capture_output=True, text=True,
        )
        if proc.returncode == 0:
            return True
        time.sleep(delay)
    return False


# --- db / driver helpers -------------------------------------------------

def _run_state(conn, run_id):
    return conn.execute("SELECT state FROM runs WHERE id=?", (run_id,)).fetchone()[0]


def _state_of(conn, tid):
    return conn.execute("SELECT state FROM tickets WHERE id=?", (tid,)).fetchone()[0]


def _settle_needs_human(conn, run_id, now):
    """Operator settle of needs_human tickets by route (harness §6)."""
    from engine import queue

    routes = set()
    rows = conn.execute(
        "SELECT id, reduction_id FROM tickets WHERE run_id=? AND state='needs_human'",
        (run_id,),
    ).fetchall()
    for tid, reduction_id in rows:
        if reduction_id is None:
            queue.requeue_needs_human(conn, tid, now=now)
            routes.add("verify")
        else:
            review_state = conn.execute(
                "SELECT review_state FROM reductions WHERE id=?", (reduction_id,)
            ).fetchone()[0]
            if review_state == "pending":
                queue.accept_reduction(conn, reduction_id, now=now)
            routes.add("reduce")
    return routes


@pytest.mark.skipif(_ENGINE is None, reason="podman/docker not available")
def test_fleet_docker_convergence(tmp_path, monkeypatch):
    from engine import crew, dispatch, queue
    from engine.db.migrate import apply_migrations, connect
    from engine.transport import serve_once_for_host
    from sites.ssh.site import SSHSite
    from testkit.scenarios.fleet import build_fleet_scenario
    from testkit.scenarios.fleet_playbook import FleetPlaybook

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))

    # Throwaway keypair (hermetic auth).
    identity = tmp_path / "id_ed25519"
    _sh("ssh-keygen", "-t", "ed25519", "-N", "", "-f", str(identity), "-q")
    pub = (tmp_path / "id_ed25519.pub").read_text().strip()

    # Build the worker image (host networking so apt reaches mirrors).
    _sh(_ENGINE, "build", "--network=host", "-f",
        str(_REPO_ROOT / "fleet" / "Dockerfile.worker"),
        "-t", _IMAGE, str(_REPO_ROOT), timeout=600)

    _rm_all()
    started: list[str] = []
    try:
        # Launch each worker publishing sshd on its distinct host port.
        for host, (port, resources) in _WORKERS.items():
            _sh(_ENGINE, "run", "-d", "--name", _container_name(host),
                "-p", f"{port}:22",
                "-e", f"HERMES_AUTHORIZED_KEY={pub}",
                "-e", f"HERMES_SSH_RESOURCES={json.dumps(resources)}",
                _IMAGE)
            started.append(host)

        for host, (port, _res) in _WORKERS.items():
            assert _ssh_ready(port, identity), f"sshd never came up on {host}:{port}"

        # --- master: db, scenario, ssh site config -----------------------
        db_path = str(tmp_path / "queue.db")
        apply_migrations(db_path)
        conn = connect(db_path)

        host_config = {
            host: {
                "hostname": "localhost", "port": port, "user": "root",
                "identity": str(identity), "resources": resources,
            }
            for host, (port, resources) in _WORKERS.items()
        }
        site = SSHSite(host_config=host_config, connect_timeout=8)
        pb = FleetPlaybook()
        tickets, agent = build_fleet_scenario(seed=42)

        run_id = "fleet-docker-1"
        conn.execute(
            """INSERT INTO runs (id, playbook, site, base_ref, config_json, state,
                                 phase, created_at, updated_at)
               VALUES (?, 'fleet', 'ssh', 'HEAD', '{}', 'running', 'work', 0, 0)""",
            (run_id,),
        )
        for tk in tickets:
            tk.run_id = run_id
            conn.execute(
                """INSERT INTO tickets (id, run_id, phase, state, resource_req,
                       priority, attempts, available_at, payload_json,
                       created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, ?, 0, 0)""",
                (tk.id, tk.run_id, tk.phase, tk.state, tk.resource_req,
                 tk.priority, tk.attempts, json.dumps(tk.payload)),
            )
        conn.commit()
        n_tickets = len(tickets)
        reverify_id = next(t.id for t in tickets if t.payload.get("needs_reverify"))
        reduce_review_id = next(
            t.id for t in tickets if t.payload.get("needs_reduce_review"))

        # Admit all hosts (real ssh provision + health gate).
        hosts = list(_WORKERS.keys())
        for host in hosts:
            crew.add(conn, site, agent, host=host, base_ref="HEAD", now=1000.0)

        # --- drive: round-robin one claim per host per cycle so work spreads
        # across distinct hosts (a per-host drain would let the first host take
        # everything). Real ssh into the containers happens inside serve_once. --
        t = 1000.0
        STEP = 700.0
        deadline = time.monotonic() + 240
        routes_settled: set[str] = set()
        stopped_host = "cpu-2"
        stop_done = False
        transport_requeue_after_stop = False
        events_before_stop = 0

        def _events_count(kind, msg=None, after_id=0):
            if msg is None:
                return conn.execute(
                    "SELECT COUNT(*) FROM events WHERE kind=? AND id>?",
                    (kind, after_id)).fetchone()[0]
            return conn.execute(
                "SELECT COUNT(*) FROM events WHERE kind=? AND message=? AND id>?",
                (kind, msg, after_id)).fetchone()[0]

        cycle = 0
        while _run_state(conn, run_id) not in ("done", "failed"):
            assert time.monotonic() < deadline, "fleet did not converge in time"
            cycle += 1

            # Heartbeat: re-probe health (marks a stopped host down + requeues).
            crew.heartbeat_sweep(conn, site, agent, now=t)

            run = queue.load_run(conn, run_id)
            for host in hosts:
                # up to 2 claims/host/cycle: keeps distribution while draining faster.
                for _ in range(2):
                    if serve_once_for_host(
                        conn, host, site, agent, run, pb, "HEAD", now=t
                    ) is None:
                        break

            routes_settled |= _settle_needs_human(conn, run_id, now=t)
            dispatch._reduce_and_advance(conn, run_id, pb, site, now=t)

            # --- host-down injection: after some progress on >=2 hosts, stop a
            # worker mid-run and keep driving; its ticket must requeue no-penalty
            # to a survivor and the run must still converge. -------------------
            if not stop_done and cycle >= 2:
                distinct = conn.execute(
                    "SELECT COUNT(DISTINCT host) FROM attempts WHERE outcome='ok'"
                ).fetchone()[0]
                remaining = conn.execute(
                    """SELECT COUNT(*) FROM tickets WHERE run_id=?
                       AND state IN ('queued','parked','dispatched','running')""",
                    (run_id,),
                ).fetchone()[0]
                if distinct >= 2 and remaining > 5:
                    events_before_stop = conn.execute(
                        "SELECT COALESCE(MAX(id),0) FROM events"
                    ).fetchone()[0]
                    _sh(_ENGINE, "stop", "-t", "2", _container_name(stopped_host))
                    stop_done = True

            if stop_done and not transport_requeue_after_stop:
                if _events_count(
                    "ticket_requeued", "requeue (transport, no penalty)",
                    after_id=events_before_stop
                ) > 0:
                    transport_requeue_after_stop = True

            t += STEP

        # ======================= CONVERGENCE ASSERTIONS ==================

        # 1. Run reached done; every ticket terminal; none truncated.
        assert _run_state(conn, run_id) == "done"
        states = [
            r[0] for r in conn.execute(
                "SELECT state FROM tickets WHERE run_id=?", (run_id,)).fetchall()
        ]
        assert len(states) == n_tickets == 40
        assert set(states) <= {"done", "failed"}, sorted(set(states))

        # 2. Distribution: work ran on >=2 distinct hosts, no double-claim.
        attempts = conn.execute(
            "SELECT ticket_id, attempt, host, outcome FROM attempts"
        ).fetchall()
        ok_hosts = {a[2] for a in attempts if a[3] == "ok"}
        assert len(ok_hosts) >= 2, f"successful work only ran on {ok_hosts}"
        # No double-claim: walking the ordered event stream, a ticket is never
        # claimed while already in-flight — every ``ticket_claimed`` is consumed
        # (result/park/requeue/fail) before the next claim of that ticket.
        _consume = {"result_recorded", "ticket_parked", "ticket_requeued",
                    "ticket_failed"}
        in_flight: dict[str, bool] = {}
        for tid, kind in conn.execute(
            """SELECT ticket_id, kind FROM events
               WHERE run_id=? AND ticket_id IS NOT NULL ORDER BY id""",
            (run_id,),
        ).fetchall():
            if kind == "ticket_claimed":
                assert not in_flight.get(tid), f"double-claim of {tid}"
                in_flight[tid] = True
            elif kind in _consume:
                in_flight[tid] = False

        # 3. Host-down requeue: the stopped worker's in-flight ticket requeued
        #    with NO penalty (transport path) and the run still reached done.
        assert stop_done, "host-down was never injected"
        assert transport_requeue_after_stop, (
            "no no-penalty transport requeue observed after stopping a worker")
        # The stopped host was marked down by the heartbeat sweep.
        down_state = conn.execute(
            "SELECT state FROM crew WHERE id=?", (stopped_host,)).fetchone()[0]
        assert down_state == "down", f"stopped host state={down_state}"

        # 4. Reduce/clustering: one reduction per distinct root_cause.signature.
        finding_sigs = [
            (json.loads(j).get("root_cause") or {}).get("signature", "unknown")
            for (j,) in conn.execute(
                "SELECT json FROM findings WHERE run_id=?", (run_id,)).fetchall()
        ]
        n_reductions = conn.execute(
            "SELECT COUNT(*) FROM reductions WHERE run_id=?", (run_id,)
        ).fetchone()[0]
        assert n_reductions == len(set(finding_sigs)) >= 2

        # 5. Infra-retry-then-succeed: attempt 1 infra_failed, attempt 2 ok, done.
        retried = conn.execute(
            """SELECT a1.ticket_id FROM attempts a1 JOIN attempts a2
               ON a2.ticket_id=a1.ticket_id
               WHERE a1.attempt=1 AND a1.outcome='infra_failed'
                 AND a2.attempt=2 AND a2.outcome='ok'"""
        ).fetchall()
        assert retried, "expected an infra-retry-then-succeed ticket"
        assert _state_of(conn, retried[0][0]) == "done"

        # 6. Driver-failed terminal (no retry).
        driver_failed = conn.execute(
            """SELECT t.id FROM tickets t JOIN attempts a ON a.ticket_id=t.id
               WHERE a.outcome='driver_failed' AND t.state='failed'"""
        ).fetchall()
        assert driver_failed, "expected a driver_failed terminal ticket"

        # 7. Both needs_human routes reached AND resolved via operator paths.
        assert routes_settled == {"verify", "reduce"}, routes_settled
        assert _state_of(conn, reverify_id) in {"done", "failed"}
        assert _state_of(conn, reduce_review_id) in {"done", "failed"}

        conn.close()
    finally:
        _rm_all()
