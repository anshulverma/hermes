"""The dispatch primitive: serve_once_for_host ties queue, leases, site, and agent together.

local_transport runs the worker on this box under timeout. ssh_transport scps the envelope
up, runs the worker over ssh, and scps the result back. serve_once_for_host claims one
ticket, acquires a lease, builds the envelope, dispatches the worker, and records the
result. Calls queue mutators (which commit); only commits the lease_id stamp itself.
Stdlib-only.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
from dataclasses import replace
from typing import Optional

from engine import config, contracts, leases, queue
from engine.models import Result, Run, Ticket

# The exit code GNU coreutils `timeout` uses when it kills the child.
_TIMEOUT_EXIT = 124

# Cap captured stderr so a chatty/looping worker can't bloat the db.
_DETAIL_LIMIT = 16384


class TransportError(Exception):
    """Host-lost / unreachable transport failure.

    Raised by ``local_transport`` (and, in production, an ssh site's
    ``run_worker``) when the worker could not be reached/launched at all — as
    distinct from a worker that ran and REPORTED an ``infra_failed`` result.
    ``serve_once_for_host`` routes this to the no-penalty ``requeue_transport``
    path (host lost), whereas an agent-reported ``infra_failed`` Result flows
    through ``record_result`` (penalty retry,).
    """


def _now(now: Optional[float]) -> float:
    return time.time() if now is None else now


def _driver_from_envelope(envelope: dict):
    """Reconstruct the ``Driver`` the agent needs from the envelope."""
    from engine.models import Driver

    d = envelope["goal_envelope"]["driver"]
    return Driver(command=d.get("command"), args=d.get("args", {}), loop=d.get("loop"))


# --- local transport -----------------------------------------------------

def local_transport(envelope: dict, host: str, agent, env: Optional[dict] = None) -> Result:
    """Run the worker on this box under a ``timeout`` wrapper.

    Builds ``agent.build_invocation(envelope, driver)``, wraps it with
    ``timeout <timeout_s>`` (when a ``timeout`` binary is available), runs it, and
    returns ``agent.parse_result(stdout, envelope)``. A ``timeout``-killed run
    (exit 124) short-circuits to a ``driver_failed`` / ``timeout`` Result. A
    failure to launch the process at all raises ``TransportError`` (host lost).

    ``env`` (when given) is the child process environment — the site passes one
    with its no-ship guard shim dir prepended to ``PATH`` so the worker cannot
    ``git push``/land. ``None`` inherits the parent environment.
    """
    driver = _driver_from_envelope(envelope)
    argv = agent.build_invocation(envelope, driver)

    timeout_s = int(envelope.get("timeout_s", 3600))
    timeout_bin = shutil.which("timeout")
    wrapped = [timeout_bin, str(timeout_s), *argv] if timeout_bin else list(argv)

    try:
        proc = subprocess.run(wrapped, capture_output=True, text=True, env=env)
    except OSError as exc:  # could not even launch -> treat as host lost
        raise TransportError(f"failed to launch worker on {host}: {exc}") from exc

    stderr_tail = (proc.stderr or "").strip()[-_DETAIL_LIMIT:] or None

    if proc.returncode == _TIMEOUT_EXIT:
        now = time.time()
        return Result(
            outcome="driver_failed",
            termination_reason="timeout",
            result_ref=None,
            error_summary=f"worker exceeded timeout_s={timeout_s}",
            started_at=now,
            ended_at=now,
            payload={},
            evidence_ref=None,
            detail=stderr_tail,
        )

    res = agent.parse_result(proc.stdout or "", envelope)
    # On a failure, surface stderr (where stack traces land) as the detail when
    # the parsed result carries none of its own.
    if res.outcome != "ok" and not res.detail and stderr_tail:
        res = replace(res, detail=stderr_tail)
    return res


# --- ssh transport -------------------------------------------------------

# Hardened, NON-INTERACTIVE ssh/scp options for automation against real hosts
# (future extension). No host-key prompts, no known_hosts pollution across ephemeral
# containers, no password fallback, and a bounded connect timeout so a lost host
# surfaces quickly as a transport failure rather than hanging the serve loop.
HARDENED_SSH_OPTS: list[str] = [
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=/dev/null",
    "-o", "BatchMode=yes",
]


def build_ssh_opts(
    *,
    identity: Optional[str] = None,
    port: Optional[int] = None,
    connect_timeout: Optional[int] = None,
    hardened: bool = True,
    extra: Optional[list] = None,
) -> list[str]:
    """Build the ``ssh`` option list (``-i/-p/-o …``) for a host.
    """
    opts = list(HARDENED_SSH_OPTS) if hardened else []
    if connect_timeout is not None:
        opts += ["-o", f"ConnectTimeout={int(connect_timeout)}"]
    if identity:
        opts += ["-i", str(identity)]
    if port is not None:
        opts += ["-p", str(port)]
    if extra:
        opts += list(extra)
    return opts


def build_scp_opts(
    *,
    identity: Optional[str] = None,
    port: Optional[int] = None,
    connect_timeout: Optional[int] = None,
    hardened: bool = True,
    extra: Optional[list] = None,
) -> list[str]:
    """Build the ``scp`` option list for a host.
    """
    opts = list(HARDENED_SSH_OPTS) if hardened else []
    if connect_timeout is not None:
        opts += ["-o", f"ConnectTimeout={int(connect_timeout)}"]
    if identity:
        opts += ["-i", str(identity)]
    if port is not None:
        opts += ["-P", str(port)]
    if extra:
        opts += list(extra)
    return opts


def ssh_transport(host: str, ssh_opts=None, scp_opts=None, user=None):
    """Return a callable ``(envelope, agent) -> Result`` that runs over ssh.

    The callable scps the envelope up, runs the worker over ssh, scps the result
    back, and parses it. A non-zero ssh exit (host unreachable / worker runner
    failed to start) maps to a ``transport_error`` Result. ``subprocess`` is
    mocked in tests (no real ssh).

    ``ssh_opts``/``scp_opts`` are the per-host connection options (see
    ``build_ssh_opts``/``build_scp_opts``); ``user`` (when given) targets
    ``user@host``. All default to none/empty so the mocked unit tests and any
    localhost caller keep the bare ``ssh <host> …`` form.
    """
    ssh_opts = list(ssh_opts or [])
    scp_opts = list(scp_opts or [])
    dest = f"{user}@{host}" if user else host

    def _run(envelope: dict, agent) -> Result:
        ticket_id = envelope.get("ticket_id", "ticket")
        safe = ticket_id.replace("/", "_")
        # Remote path: shell-expanded by the remote shell so HERMES_HOME is honoured.
        remote_dir = f"${{HERMES_HOME:-$HOME/.hermes}}/xfer/{safe}"
        remote_env = f"{remote_dir}/envelope.json"
        remote_result = f"{remote_dir}/result.json"

        with tempfile.TemporaryDirectory(prefix="hermes-ssh-", dir=config.state_dir("tmp")) as tmp:
            local_env = os.path.join(tmp, "envelope.json")
            local_result = os.path.join(tmp, "result.json")
            with open(local_env, "w") as fh:
                json.dump(envelope, fh)

            # 1) scp the envelope up.
            subprocess.run(
                ["scp", *scp_opts, local_env, f"{dest}:{remote_env}"],
                capture_output=True, text=True,
            )

            # 2) run the worker over ssh.
            timeout_s = int(envelope.get("timeout_s", 3600))
            ssh_proc = subprocess.run(
                [
                    "ssh", *ssh_opts, dest,
                    "hermes", "serve-once",
                    "--envelope", remote_env,
                    "--result", remote_result,
                    "--timeout", str(timeout_s),
                ],
                capture_output=True, text=True,
            )
            if ssh_proc.returncode != 0:
                # TODO(future extension): A real ssh site must signal host-lost by RAISING
                # TransportError (→ no-penalty requeue_transport), NOT by returning
                # an infra_failed Result (which record_result would penalize).
                now = time.time()
                return Result(
                    outcome="infra_failed",
                    termination_reason="transport_error",
                    result_ref=None,
                    error_summary=(
                        f"ssh to {host} failed (exit {ssh_proc.returncode}): "
                        f"{(ssh_proc.stderr or '').strip()}"
                    ),
                    started_at=now,
                    ended_at=now,
                    payload={},
                    evidence_ref=None,
                )

            # 3) scp the result/evidence back and parse it.
            subprocess.run(
                ["scp", *scp_opts, f"{dest}:{remote_result}", local_result],
                capture_output=True, text=True,
            )
            raw = ""
            if os.path.exists(local_result):
                with open(local_result) as fh:
                    raw = fh.read()
            return agent.parse_result(raw, envelope)

    return _run


# --- serve_once_for_host: the dispatch primitive -------------------------

def serve_once_for_host(
    conn: sqlite3.Connection,
    host: str,
    site,
    agent,
    run: Run,
    playbook,
    base_ref: str,
    now: Optional[float] = None,
) -> Optional[Result]:
    """Dispatch exactly one ticket for ``host``. The core serve step.

    Steps:
      1. ``queue.claim_ticket`` — nothing claimable ⇒ return ``None``.
      2. ``leases.acquire`` — at capacity (``None``) ⇒ ``queue.park_ticket`` and
         return ``None`` (no dispatch, no attempt penalty). On grant, stamp the
         ``lease_id`` onto the ticket (transport commits this one row).
      3. Build the dispatch envelope (payload + canonical ``payload_sha256`` +
         goal_envelope) and ``contracts.validate_envelope``. An envelope /
         validation error ⇒ ``queue.requeue`` (penalty) and return ``None``.
      4. ``site.run_worker(host, envelope, agent)``. A ``TransportError`` (host
         lost) ⇒ ``queue.requeue_transport`` (no penalty) and return ``None``.
      5. ``queue.record_result`` applies the running-exit transition. Return
         the Result.
    """
    now = _now(now)

    ticket = queue.claim_ticket(conn, host, site.resource_classes(), now)
    if ticket is None:
        return None

    lease = leases.acquire(conn, ticket.run_id, ticket.resource_req, ticket.id,
                           host, now=now)
    if lease is None:
        # Class at capacity: revert the claim to parked (no attempt penalty).
        queue.park_ticket(conn, ticket, now=now)
        return None

    # Stamp the acquired lease onto the ticket so the queue releases it on every
    # exit from running. leases.acquire does not commit, so transport commits it.
    conn.execute(
        "UPDATE tickets SET lease_id=?, updated_at=? WHERE id=?",
        (lease.id, now, ticket.id),
    )
    conn.commit()

    try:
        envelope = _build_envelope(ticket, run, playbook, base_ref, site, host)
        contracts.validate_envelope(envelope, playbook.payload_schema(ticket.phase))
    except contracts.ContractError as exc:
        # Deterministic contract failure (envelope validation): TERMINAL.
        # This will never succeed on retry (bad schema/payload mismatch).
        queue.fail_contract_violation(
            conn, ticket, host, f"envelope validation failed: {exc}", now=now
        )
        return None
    except ValueError as exc:
        # Deterministic no-ship guard violation (raised by _build_envelope):
        # TERMINAL. Site cannot guarantee no-ship but guardrails.no_ship=true.
        if "cannot guarantee no-ship" in str(exc):
            queue.fail_contract_violation(
                conn, ticket, host, f"no-ship guard violation: {exc}", now=now
            )
            return None
        # Other ValueErrors are unexpected bugs -> propagate
        raise

    try:
        result = site.run_worker(host, envelope, agent)
    except TransportError:
        # Host lost: no-penalty requeue (releases the lease); attempts unchanged.
        queue.requeue_transport(conn, ticket, now=now)
        return None

    queue.record_result(conn, ticket, host, result, now, playbook, site)
    return result


def _build_envelope(ticket: Ticket, run: Run, playbook, base_ref: str, site,
                    host: str) -> dict:
    """Assemble the dispatch envelope for a ticket.

    ``payload_sha256`` is stamped as the canonical digest of the payload; the
    agent recomputes it on the worker side and flags ``contract_fail`` on a
    mismatch. ``guardrails.no_ship`` is always true; if the site cannot guarantee
    no-ship that is a hard error (routed to a penalty requeue by the
    caller).
    """
    driver = playbook.driver(ticket.phase)
    payload = ticket.payload

    goal = payload.get("goal") or f"{ticket.phase}: {ticket.id}"
    no_ship = True
    if no_ship and not site.guarantees_no_ship():
        raise ValueError(
            f"site {getattr(site, 'name', '?')!r} cannot guarantee no-ship; "
            f"refusing dispatch of {ticket.id!r} with guardrails.no_ship=true"
        )

    timeout_s = run.config.get("timeout_s", 3600) if run is not None else 3600

    return {
        "ticket_id": ticket.id,
        "run_id": ticket.run_id,
        "phase": ticket.phase,
        "resource_req": ticket.resource_req,
        "base_ref": base_ref,
        "payload": payload,
        "payload_sha256": contracts.payload_sha256(payload),
        "timeout_s": timeout_s,
        "site_context": {"site": getattr(site, "name", ""), "host": host},
        "goal_envelope": {
            "goal": goal,
            "driver": {
                "command": driver.command,
                "args": driver.args,
                "loop": driver.loop,
            },
            "done_contract": playbook.result_schema(ticket.phase),
            "guardrails": {"no_ship": no_ship},
        },
    }
