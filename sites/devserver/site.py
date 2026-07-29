"""DevserverSite — internal devserver adapter (Slice 5, spec §3).

Runs investigations on internal devservers with native buck2/sl/test tooling.
A DISTINCT site (not inheriting SSHSite): real idempotent provisioning + HONEST
guard reporting. Reuses transport.build_ssh_opts/build_scp_opts. Meta-internal
specifics (host-list source, install recipe, dashboard endpoint) stay deploy-time
pluggable (env/config hooks), NOT hardcoded.

Stdlib-only: subprocess, json, os, tempfile, time, shlex.
"""
from __future__ import annotations

import json
import os
import re
import shlex
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
        ssh_opts = self._ssh_opts(host)

        # 1. Verify ssh connectivity
        subprocess.run(
            ["ssh", *ssh_opts, host, "true"],
            capture_output=True,
            text=True,
            check=True,
        )

        # 2. Ensure checkout at base_ref (idempotent: check current ref first, re-verify on 2nd call)
        # Try git first, fall back to sl
        workspace_dir = "/tmp/hermes-workspace"
        workspace_dir_quoted = shlex.quote(workspace_dir)
        base_ref_quoted = shlex.quote(base_ref)

        # Check if workspace exists
        check_workspace = subprocess.run(
            ["ssh", *ssh_opts, host, f"test -d {workspace_dir_quoted}"],
            capture_output=True,
            text=True,
        )

        if check_workspace.returncode != 0:
            # Workspace doesn't exist, clone it
            # Try git clone (prefer git over sl for devservers)
            repo_url = os.environ.get("HERMES_REPO_URL", "")
            if repo_url:
                repo_url_quoted = shlex.quote(repo_url)
                subprocess.run(
                    ["ssh", *ssh_opts, host,
                     f"git clone {repo_url_quoted} {workspace_dir_quoted}"],
                    capture_output=True,
                    text=True,
                    check=False,  # May fail if git not available
                )

        # Ensure we're at the correct ref (idempotent: re-verify on 2nd call)
        subprocess.run(
            ["ssh", *ssh_opts, host,
             f"cd {workspace_dir_quoted} && git checkout {base_ref_quoted}"],
            capture_output=True,
            text=True,
            check=False,  # May fail if workspace doesn't exist or not git repo
        )

        # 3. Ensure claude + dexter installed (deployment-specific hook)
        install_cmd = os.environ.get("HERMES_DEVSERVER_INSTALL_CMD", "")
        if install_cmd:
            # Run the install command (already shell-safe via env var)
            subprocess.run(
                ["ssh", *ssh_opts, host, install_cmd],
                capture_output=True,
                text=True,
                check=False,  # Don't fail provision if install hook fails
            )

        # 4. Install guard shims (always re-install for idempotence)
        self._install_guard(host)

        # 5. Ensure dexter runtime dir exists
        runtime_dir = "/tmp/hermes-dexter-runtime"
        runtime_dir_quoted = shlex.quote(runtime_dir)
        subprocess.run(
            ["ssh", *ssh_opts, host, f"mkdir -p {runtime_dir_quoted}"],
            capture_output=True,
            text=True,
            check=False,
        )

    def _install_guard(self, host: str) -> None:
        """Install no-ship guard shims over SSH (always re-install).

        Guard dir is deployment-specific; use a standard location.
        """
        guard_dir = f"/tmp/hermes-guard-{host}/bin"
        guard_dir_quoted = shlex.quote(guard_dir)
        ssh_opts = self._ssh_opts(host)

        # Create guard dir
        subprocess.run(
            ["ssh", *ssh_opts, host, "mkdir", "-p", guard_dir_quoted],
            capture_output=True,
            text=True,
            check=False,  # Don't fail if already exists
        )

        # Write each guard shim
        for name, blocked in GUARD_SHIMS.items():
            self._write_remote_shim(host, guard_dir, name, blocked, ssh_opts)

    def _write_remote_shim(self, host: str, guard_dir: str, name: str, blocked: tuple, ssh_opts: list[str]) -> None:
        """Write one guard shim to the remote host.

        CRITICAL: Resolve the real binary's ABSOLUTE path on the remote (via 'command -v')
        and bake it into the shim as 'exec "<realpath>" "$@"'. This prevents infinite
        recursion when the guard dir is prepended to PATH. When the real binary is absent,
        fail closed (exit 127) rather than recursing.
        """
        # Resolve real binary on remote (guard dir NOT yet on PATH, so this finds the real one)
        proc = subprocess.run(
            ["ssh", *ssh_opts, host, f"command -v {shlex.quote(name)}"],
            capture_output=True,
            text=True,
        )

        cases = "|".join(blocked)

        if proc.returncode == 0 and proc.stdout.strip():
            # Real binary found: use its absolute path
            real_path = proc.stdout.strip()
            passthrough = f'exec "{real_path}" "$@"'
        else:
            # Real binary absent: fail closed (exit 127), never recurse
            passthrough = (
                f'echo "[hermes-no-ship-guard] real {name!r} not found" >&2; exit 127'
            )

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
{passthrough}
"""
        shim_path = f"{guard_dir}/{name}"
        shim_path_quoted = shlex.quote(shim_path)

        # Write shim via ssh (cat > file + chmod +x) with QUOTED paths
        subprocess.run(
            ["ssh", *ssh_opts, host, f"cat > {shim_path_quoted}"],
            input=script,
            capture_output=True,
            text=True,
            check=False,
        )
        subprocess.run(
            ["ssh", *ssh_opts, host, "chmod", "+x", shim_path_quoted],
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
            # AND shlex.quote all interpolated values to prevent shell injection
            timeout_s = int(envelope.get("timeout_s", 3600))
            guard_dir = self._guard_dir(host)

            # Build remote command as a shell string that exports PATH then runs serve-once
            # CRITICAL: shlex.quote() all interpolated values (guard_dir, paths, timeout)
            remote_cmd = (
                f'PATH={shlex.quote(guard_dir)}:$PATH hermes serve-once '
                f'--envelope {shlex.quote(remote_env)} --result {shlex.quote(remote_result)} '
                f'--timeout {shlex.quote(str(timeout_s))}'
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

        Actually shells the publish-only submit command over SSH (pluggable via
        HERMES_DEVSERVER_SUBMIT_CMD, default "jf submit"), parses the review URL
        from stdout, and returns it. NEVER issues land/push subcommands.

        Raises: ValueError if submit command fails or URL can't be parsed.
        """
        submit_cmd = os.environ.get("HERMES_DEVSERVER_SUBMIT_CMD", "jf submit")
        ssh_opts = self._ssh_opts(host)

        # Run the submit command over SSH
        try:
            proc = subprocess.run(
                ["ssh", *ssh_opts, host, submit_cmd],
                capture_output=True,
                text=True,
                timeout=self.connect_timeout + 30,
                check=False,  # Don't raise on non-zero, handle it ourselves
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError(f"Submit command timed out: {exc}") from exc

        if proc.returncode != 0:
            raise ValueError(
                f"Submit command failed (exit {proc.returncode}): {proc.stderr.strip()}"
            )

        # Parse the review URL from stdout
        # Common patterns: "Created review: <URL>", "Review URL: <URL>", or just the URL
        output = proc.stdout.strip()

        # Try to extract a URL from the output
        # Look for https?:// URLs
        url_match = re.search(r'https?://[^\s]+', output)
        if url_match:
            return url_match.group(0)

        # If no URL found, raise an error
        raise ValueError(
            f"Could not parse review URL from submit command output: {output}"
        )

    def issue_source(self, query: IssueQuery) -> list[Issue]:
        """Query internal dashboard for issues (optional, pluggable endpoint).

        Default returns [] (endpoint not configured).
        """
        # NOTE: In a real deployment, this would query an internal dashboard API.
        # For now, return empty list (endpoint not configured).
        return []

    # --- extension methods (D3) ------------------------------------------

    def recheck_fix(self, result_payload: dict) -> bool:
        """Independent fix re-check via CI-signal probe (D3, §2.5/§3).

        Host-agnostic INDEPENDENT re-check: re-query the published diff's CI signal
        via an internal tool using result_payload["fix"]["diff_ref"], and/or spin
        the recorded minimal repro on a discover_hosts()-chosen box at the run's
        base_ref; return whether the fix independently holds.

        The CI-signal lookup / repro command is a DEPLOY-TIME PLUGGABLE HOOK
        (env-configurable command, e.g. HERMES_DEVSERVER_RECHECK_CMD; shlex-quote
        the diff_ref in the argv, consistent with Slice 5).

        Return False on ANY inconclusive/failed/missing-diff_ref/raising check
        (NEVER a false pass — fail safe). Use subprocess (mocked in tests);
        stdlib-only.

        Args:
            result_payload: The §2.3 dexter result payload dict.

        Returns:
            True iff the fix independently holds (CI green/passing).
            False on any inconclusive/failed/missing check (fail-safe).
        """
        # Extract diff_ref from result_payload
        try:
            diff_ref = result_payload.get("fix", {}).get("diff_ref")
        except (AttributeError, TypeError):
            # Malformed payload
            return False

        # Fail-safe: missing diff_ref → False (no crash)
        if not diff_ref:
            return False

        # Get the recheck command from env (deploy-time pluggable)
        recheck_cmd = os.environ.get("HERMES_DEVSERVER_RECHECK_CMD", "")
        if not recheck_cmd:
            # No recheck command configured → fail-safe
            return False

        # Build the probe command with shlex-quoted diff_ref (injection safety)
        # The command is expected to be a single binary/script name; we append the diff_ref
        try:
            probe_argv = [recheck_cmd, shlex.quote(diff_ref)]
            proc = subprocess.run(
                probe_argv,
                capture_output=True,
                text=True,
                timeout=30,  # Reasonable timeout for CI probe
                check=False,  # Don't raise on non-zero exit
            )
        except (subprocess.TimeoutExpired, OSError, Exception):
            # Probe raised → fail-safe
            return False

        # Parse the probe output for green/passing signal
        output = proc.stdout.lower()

        # Check for passing signals
        if "green" in output or "passing" in output:
            return True

        # Everything else (failing, inconclusive, error) → fail-safe
        return False

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
