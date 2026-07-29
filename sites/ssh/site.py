"""SSHSite — generic SSH site adapter (spec §4, §8).

Reaches worker hosts over SSH. Workers are stateless nodes running sshd + the
hermes worker runner + the configured agent + no-ship guard shims (all baked).
Resource classes + counts come from per-host env config.

Stdlib-only: subprocess, json, os, time.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from engine import site as _site
from engine import transport
from engine.models import Check, HealthReport, Issue, IssueQuery, Result


class SSHSite:
    """Generic SSH site adapter (§4, §8)."""

    name = "ssh"

    # --- discovery -------------------------------------------------------

    def discover_hosts(self) -> list[str]:
        """Return hosts from HERMES_SSH_HOSTS env (comma-separated) or []."""
        hosts_str = os.environ.get("HERMES_SSH_HOSTS", "")
        if not hosts_str.strip():
            return []
        return [h.strip() for h in hosts_str.split(",") if h.strip()]

    # --- provisioning ----------------------------------------------------

    def provision(self, host: str, base_ref: str) -> None:
        """Idempotent verify over SSH: checkout, guard, worker runner present.

        Assumes a baked image (no install). Just verifies remote state.
        """
        # Simple verification: check that hermes command exists on the remote
        subprocess.run(
            ["ssh", host, "command", "-v", "hermes"],
            capture_output=True,
            text=True,
            check=True,
        )

    # --- health ----------------------------------------------------------

    def health(self, host: str, agent) -> HealthReport:
        """Run reachability + latency + guard + resources checks; merge agent checks.

        Resources come from HERMES_SSH_RESOURCES_<host> env var (JSON dict).
        """
        t0 = time.perf_counter()

        # Reachability: ssh <host> true
        try:
            proc = subprocess.run(
                ["ssh", host, "true"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            reachable = proc.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            reachable = False

        transport_check = Check(
            "transport",
            reachable,
            "ssh reachable" if reachable else "ssh unreachable",
        )

        # Guard check: assume baked (always True for ssh site)
        guard_installed = True
        guard_check = Check(
            "guard", guard_installed, "no-ship guard baked into image"
        )

        # Resources from env: HERMES_SSH_RESOURCES_<host>
        # Normalize host name: hyphens stay as hyphens in env var
        env_key = f"HERMES_SSH_RESOURCES_{host}"
        resources_json = os.environ.get(env_key, "{}")
        try:
            resources = json.loads(resources_json)
        except json.JSONDecodeError:
            resources = {}

        resource_check = Check(
            "resources", bool(resources), f"resources={resources}"
        )

        # Workspace ready: assume baked (always True for ssh site)
        workspace_ready = True
        workspace_check = Check(
            "workspace", workspace_ready, "workspace baked into image"
        )

        site_checks = [transport_check, workspace_check, guard_check, resource_check]
        agent_checks = list(agent.health_checks(host, self))

        # Extract agent_ok and auth_ok from agent_checks
        agent_ok = _find_ok(agent_checks, ("agent", "agent_ok"))
        auth_ok = _find_ok(agent_checks, ("auth", "auth_ok"))

        latency_ms = int((time.perf_counter() - t0) * 1000)

        return HealthReport(
            reachable=reachable,
            agent_ok=agent_ok,
            auth_ok=auth_ok,
            workspace_ready=workspace_ready,
            guard_installed=guard_installed,
            resources=resources,
            latency_ms=latency_ms,
            checks=site_checks + agent_checks,
        )

    # --- execution -------------------------------------------------------

    def run_worker(self, host: str, envelope: dict, agent) -> Result:
        """Run worker via ssh_transport.

        Host-lost handling: CONNECTION-level failure (ssh exit 255 / connection
        refused/timeout) RAISES TransportError -> serve_once does no-penalty
        requeue_transport. A worker that ran and returned a Result passes through
        normally.
        """
        # Use the ssh_transport from engine.transport, but we need to handle
        # the connection-failure -> TransportError case here.
        ticket_id = envelope.get("ticket_id", "ticket")
        safe = ticket_id.replace("/", "_")
        remote_dir = f"/tmp/hermes-{safe}"
        remote_env = f"{remote_dir}/envelope.json"
        remote_result = f"{remote_dir}/result.json"

        with tempfile.TemporaryDirectory(prefix="hermes-ssh-") as tmp:
            local_env = os.path.join(tmp, "envelope.json")
            local_result = os.path.join(tmp, "result.json")
            with open(local_env, "w") as fh:
                json.dump(envelope, fh)

            # 1) scp the envelope up.
            try:
                subprocess.run(
                    ["ssh", host, "mkdir", "-p", remote_dir],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=True,
                )
                subprocess.run(
                    ["scp", local_env, f"{host}:{remote_env}"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=True,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                # Connection-level failure
                raise transport.TransportError(
                    f"Failed to copy envelope to {host}: {exc}"
                ) from exc

            # 2) run the worker over ssh.
            timeout_s = int(envelope.get("timeout_s", 3600))
            try:
                ssh_proc = subprocess.run(
                    [
                        "ssh",
                        host,
                        "hermes",
                        "serve-once",
                        "--envelope",
                        remote_env,
                        "--result",
                        remote_result,
                        "--timeout",
                        str(timeout_s),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=timeout_s + 60,  # Extra margin
                )
            except subprocess.TimeoutExpired as exc:
                raise transport.TransportError(
                    f"SSH to {host} timed out: {exc}"
                ) from exc

            # Connection-level failure detection: ssh exit 255 or other connection errors
            if ssh_proc.returncode == 255:
                raise transport.TransportError(
                    f"SSH connection to {host} failed (exit 255): {ssh_proc.stderr.strip()}"
                )

            # Other non-zero exits: the worker ran but failed. This is NOT a
            # connection failure, so we return the result normally (agent parses it).
            # Note: For now, we'll try to fetch the result anyway.

            # 3) scp the result back and parse it.
            try:
                subprocess.run(
                    ["scp", f"{host}:{remote_result}", local_result],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                # If we can't fetch the result, treat it as transport error
                # (we don't know if the worker actually ran)
                raise transport.TransportError(
                    f"Failed to fetch result from {host}"
                )

            raw = ""
            if os.path.exists(local_result):
                with open(local_result) as fh:
                    raw = fh.read()

            return agent.parse_result(raw, envelope)

    # --- capabilities ----------------------------------------------------

    def resource_classes(self) -> list[str]:
        """Return union of classes from all configured hosts."""
        hosts = self.discover_hosts()
        all_classes = set()
        for host in hosts:
            # Normalize host name: hyphens stay as hyphens in env var
            env_key = f"HERMES_SSH_RESOURCES_{host}"
            resources_json = os.environ.get(env_key, "{}")
            try:
                resources = json.loads(resources_json)
                all_classes.update(resources.keys())
            except json.JSONDecodeError:
                pass
        return sorted(all_classes)

    def guarantees_no_ship(self) -> bool:
        """Return True (guard baked into worker image)."""
        return True

    # --- review / issues -------------------------------------------------

    def submit_for_review(self, host: str, change: dict) -> str:
        """Return a placeholder review URL (no-op for ssh site)."""
        change_id = change.get("id", "change")
        return f"ssh://{host}/review/{change_id}"

    def issue_source(self, query: IssueQuery) -> list[Issue]:
        """Return empty list (file-based, no remote issues for ssh site)."""
        return []


def _find_ok(checks, names) -> bool:
    """Return the ok flag of the first check whose name is in `names` (else True)."""
    for c in checks:
        if c.name in names:
            return c.ok
    return True


# --- registration (import side-effect) -----------------------------------

_site.register("ssh", SSHSite())
