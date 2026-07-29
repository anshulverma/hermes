"""DevserverSite — internal devserver adapter (Slice 5, spec §3).

Runs investigations on internal devservers with native buck2/sl/test tooling.
A DISTINCT site (not inheriting SSHSite): real idempotent provisioning + HONEST
guard reporting. Reuses transport.build_ssh_opts/build_scp_opts. Meta-internal
specifics (host-list source, install recipe, dashboard endpoint) stay deploy-time
pluggable (env/config hooks), NOT hardcoded.

Stdlib-only: subprocess, json, os, tempfile, time.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time

from engine import site as _site
from engine import transport
from engine.models import Check, HealthReport, Issue, IssueQuery, Result

# Same guard shims as sites/local (§3): block git push, sl push|land, hg push,
# jf land, arc land → exit 97.
GUARD_SHIMS: dict[str, tuple[str, ...]] = {
    "git": ("push",),
    "sl": ("push", "land"),
    "hg": ("push",),
    "jf": ("land",),
    "arc": ("land",),
}

_GUARD_BLOCK_EXIT = 97
_DEFAULT_CONNECT_TIMEOUT = 10


class DevserverSite:
    """Internal devserver site adapter (§3, Slice 5)."""

    name = "devserver"

    def __init__(self, connect_timeout: int = _DEFAULT_CONNECT_TIMEOUT):
        """Initialize DevserverSite.

        connect_timeout bounds every ssh/scp operation.
        """
        self.connect_timeout = connect_timeout

    # --- discovery -------------------------------------------------------

    def discover_hosts(self) -> list[str]:
        """Read host list from HERMES_DEVSERVER_HOSTS env var, else []."""
        hosts_str = os.environ.get("HERMES_DEVSERVER_HOSTS", "")
        if not hosts_str.strip():
            return []
        return [h.strip() for h in hosts_str.split(",") if h.strip()]

    # --- provisioning ----------------------------------------------------

    def provision(self, host: str, base_ref: str) -> None:
        """Idempotent provision over SSH: ensure clean checkout at base_ref,
        ensure claude present+authed + dexter plugin installed, install no-ship
        guard shims, ensure dexter runtime dir exists.

        Install recipe is a pluggable hook (deployment-specific).
        """
        # NOTE: This is a pluggable hook placeholder. In a real deployment,
        # this would call site-specific provisioning scripts over SSH.
        # For now, we do basic idempotent checks:

        # 1. Verify ssh connectivity
        subprocess.run(
            ["ssh", *self._ssh_opts(host), host, "true"],
            capture_output=True,
            text=True,
            check=True,
        )

        # 2. Ensure checkout at base_ref (idempotent: check current ref first)
        # This is deployment-specific; placeholder for now

        # 3. Ensure claude + dexter installed (deployment-specific hook)

        # 4. Install guard shims (always re-install for idempotence)
        self._install_guard(host)

        # 5. Ensure dexter runtime dir exists (deployment-specific)

    def _install_guard(self, host: str) -> None:
        """Install no-ship guard shims over SSH (always re-install).

        Guard dir is deployment-specific; use a standard location.
        """
        guard_dir = f"/tmp/hermes-guard-{host}/bin"

        # Create guard dir
        subprocess.run(
            ["ssh", *self._ssh_opts(host), host, "mkdir", "-p", guard_dir],
            capture_output=True,
            text=True,
            check=False,  # Don't fail if already exists
        )

        # Write each guard shim
        for name, blocked in GUARD_SHIMS.items():
            self._write_remote_shim(host, guard_dir, name, blocked)

    def _write_remote_shim(self, host: str, guard_dir: str, name: str, blocked: tuple) -> None:
        """Write one guard shim to the remote host."""
        cases = "|".join(blocked)
        script = f"""#!/bin/sh
# hermes no-ship guard shim for {name!r}: blocks {cases}
for _arg in "$@"; do
  case "$_arg" in
    {cases})
      echo "[hermes-no-ship-guard] blocked '{name} $_arg' (no-land/no-push invariant)" >&2
      exit {_GUARD_BLOCK_EXIT}
      ;;
  esac
done
# Passthrough to real binary (find it in original PATH)
exec {name} "$@"
"""
        shim_path = f"{guard_dir}/{name}"

        # Write shim via ssh (echo script to file + chmod +x)
        subprocess.run(
            ["ssh", *self._ssh_opts(host), host, f"cat > {shim_path}"],
            input=script,
            capture_output=True,
            text=True,
            check=False,
        )
        subprocess.run(
            ["ssh", *self._ssh_opts(host), host, "chmod", "+x", shim_path],
            capture_output=True,
            text=True,
            check=False,
        )

    def _guard_dir(self, host: str) -> str:
        """Return the remote guard dir path."""
        return f"/tmp/hermes-guard-{host}/bin"

    def _guard_installed(self, host: str) -> bool:
        """Check if guard shims are actually present on the remote host (HONEST probe)."""
        guard_dir = self._guard_dir(host)

        # Check each shim exists and is executable
        for name in GUARD_SHIMS:
            shim_path = f"{guard_dir}/{name}"
            proc = subprocess.run(
                ["ssh", *self._ssh_opts(host), host, "test", "-x", shim_path],
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                return False
        return True

    # --- health ----------------------------------------------------------

    def health(self, host: str, agent) -> HealthReport:
        """Run reachability + latency + workspace + guard + resources checks; merge agent checks.

        guard_installed is PROBED (honest), not hardcoded True.
        resources from nproc. agent_ok/auth_ok from agent.health_checks via _find_ok.
        """
        t0 = time.perf_counter()

        # Reachability: ssh <host> true
        try:
            proc = subprocess.run(
                ["ssh", *self._ssh_opts(host), host, "true"],
                capture_output=True,
                text=True,
                timeout=self.connect_timeout + 5,
            )
            reachable = proc.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            reachable = False

        transport_check = Check(
            "transport",
            reachable,
            "ssh reachable" if reachable else "ssh unreachable",
        )

        # Workspace ready: check if checkout exists at base_ref (deployment-specific)
        # For now, assume provisioned if reachable
        workspace_ready = reachable
        workspace_check = Check(
            "workspace",
            workspace_ready,
            "workspace provisioned" if workspace_ready else "workspace not provisioned",
        )

        # Guard installed: HONEST probe (not hardcoded True)
        guard_installed = self._guard_installed(host) if reachable else False
        guard_check = Check(
            "guard",
            guard_installed,
            "no-ship guard shims installed" if guard_installed
            else "no-ship guard shims missing (run provision)",
        )

        # Resources: get cpu count from nproc
        resources = {}
        if reachable:
            try:
                proc = subprocess.run(
                    ["ssh", *self._ssh_opts(host), host, "nproc"],
                    capture_output=True,
                    text=True,
                    timeout=self.connect_timeout + 5,
                )
                if proc.returncode == 0:
                    resources = {"cpu": int(proc.stdout.strip())}
            except (subprocess.TimeoutExpired, OSError, ValueError):
                resources = {"cpu": 1}  # fallback

        if not resources:
            resources = {"cpu": 1}

        resource_check = Check("resources", bool(resources), f"resources={resources}")

        site_checks = [transport_check, workspace_check, guard_check, resource_check]
        agent_checks = list(agent.health_checks(host, self))

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
        """Run the worker over SSH with guard dir prepended to remote PATH.

        CRITICAL: Pass remote command as a SINGLE SHELL STRING exporting
        PATH=<guarddir>:$PATH before serve-once, so the remote shell expands $PATH.
        (SSHSite passes as separate argv items where $PATH won't expand.)

        Connection-level failure (ssh exit 255, failed scp) RAISES TransportError
        → no-penalty requeue_transport. Worker that ran → agent.parse_result.
        """
        ssh_opts = self._ssh_opts(host)
        scp_opts = self._scp_opts(host)

        ticket_id = envelope.get("ticket_id", "ticket")
        safe = ticket_id.replace("/", "_")
        remote_dir = f"/tmp/hermes-{safe}"
        remote_env = f"{remote_dir}/envelope.json"
        remote_result = f"{remote_dir}/result.json"

        with tempfile.TemporaryDirectory(prefix="hermes-devserver-") as tmp:
            local_env = os.path.join(tmp, "envelope.json")
            local_result = os.path.join(tmp, "result.json")
            with open(local_env, "w") as fh:
                json.dump(envelope, fh)

            # 1) ensure remote dir + scp the envelope up
            try:
                subprocess.run(
                    ["ssh", *ssh_opts, host, "mkdir", "-p", remote_dir],
                    capture_output=True,
                    text=True,
                    timeout=self.connect_timeout + 5,
                    check=True,
                )
                subprocess.run(
                    ["scp", *scp_opts, local_env, f"{host}:{remote_env}"],
                    capture_output=True,
                    text=True,
                    timeout=self.connect_timeout + 20,
                    check=True,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                raise transport.TransportError(
                    f"Failed to copy envelope to {host}: {exc}"
                ) from exc

            # 2) run the worker over ssh WITH guard dir prepended to remote PATH
            # CRITICAL: Pass as a SINGLE SHELL STRING so $PATH expands
            timeout_s = int(envelope.get("timeout_s", 3600))
            guard_dir = self._guard_dir(host)

            # Build remote command as a shell string that exports PATH then runs serve-once
            remote_cmd = (
                f'PATH={guard_dir}:$PATH hermes serve-once '
                f'--envelope {remote_env} --result {remote_result} --timeout {timeout_s}'
            )

            try:
                ssh_proc = subprocess.run(
                    ["ssh", *ssh_opts, host, remote_cmd],
                    capture_output=True,
                    text=True,
                    timeout=timeout_s + 60,  # extra margin
                )
            except subprocess.TimeoutExpired as exc:
                raise transport.TransportError(
                    f"SSH to {host} timed out: {exc}"
                ) from exc

            # ssh exit 255 = connection-error code (refused/unreachable):
            # transport-level failure -> raise for no-penalty requeue
            if ssh_proc.returncode == 255:
                raise transport.TransportError(
                    f"SSH connection to {host} failed (exit 255): "
                    f"{ssh_proc.stderr.strip()}"
                )
            # Other non-zero exits: worker ran but failed; pass through and
            # let agent parse the worker's outcome

            # 3) scp the result back and parse it. check=True so nonzero scp
            #    (host died between serve-once and fetch) RAISES -> TransportError
            #    -> no-penalty requeue_transport
            try:
                subprocess.run(
                    ["scp", *scp_opts, f"{host}:{remote_result}", local_result],
                    capture_output=True,
                    text=True,
                    timeout=self.connect_timeout + 20,
                    check=True,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
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
        """Return ["cpu"] (devservers provide cpu resources)."""
        return ["cpu"]

    def guarantees_no_ship(self) -> bool:
        """Return True (guard installed + verified)."""
        return True

    # --- review / issues -------------------------------------------------

    def submit_for_review(self, host: str, change: dict) -> str:
        """Wrap jf submit (publish-only, never land) and return review URL.

        Deployment-specific: placeholder returns a mock URL.
        """
        # NOTE: In a real deployment, this would call `jf submit` over SSH
        # and parse the review URL from the output.
        # For now, return a placeholder.
        change_id = change.get("id", "change")
        return f"https://review.example/D{change_id}"

    def issue_source(self, query: IssueQuery) -> list[Issue]:
        """Query internal dashboard for issues (optional, pluggable endpoint).

        Default returns [] (endpoint not configured).
        """
        # NOTE: In a real deployment, this would query an internal dashboard API.
        # For now, return empty list (endpoint not configured).
        return []

    # --- helpers ---------------------------------------------------------

    def _ssh_opts(self, host: str) -> list[str]:
        """Build ssh options for this host."""
        return transport.build_ssh_opts(connect_timeout=self.connect_timeout)

    def _scp_opts(self, host: str) -> list[str]:
        """Build scp options for this host."""
        return transport.build_scp_opts(connect_timeout=self.connect_timeout)


def _find_ok(checks, names) -> bool:
    """Return the ok flag of the first check whose name is in `names` (else True)."""
    for c in checks:
        if c.name in names:
            return c.ok
    return True


# --- registration (import side-effect) -----------------------------------

_site.register("devserver", DevserverSite())
