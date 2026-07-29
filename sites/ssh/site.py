"""SSHSite — generic SSH site adapter (spec §4, §8; Slice 12 real-host support).

Reaches worker hosts over SSH. Workers are stateless nodes running sshd + the
hermes worker runner + the configured agent + no-ship guard shims (all baked).
Resource classes + counts come from per-host config.

Per-host connection config (Slice 12) — ``host -> {port, user, identity,
resources}`` — is supplied either programmatically via ``SSHSite(host_config=…)``
(used by the in-process fleet master) or from env vars for the registry singleton:

- ``HERMES_SSH_HOSTS``            comma-separated host list
- ``HERMES_SSH_PORT_<host>``      ssh port (default: none -> 22)
- ``HERMES_SSH_USER_<host>``      login user (default: none -> current user)
- ``HERMES_SSH_IDENTITY_<host>``  private key path
- ``HERMES_SSH_RESOURCES_<host>`` JSON resources dict, e.g. ``{"cpu":4}``

Every ssh/scp invocation carries the hardened non-interactive options
(``StrictHostKeyChecking=no``, ``UserKnownHostsFile=/dev/null``, ``BatchMode=yes``,
``ConnectTimeout``) plus the per-host identity/port/user, so the site works against
real (container) hosts, not just mocks.

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

# Default bounded connect timeout (seconds) so a lost host surfaces fast.
_DEFAULT_CONNECT_TIMEOUT = 10


class SSHSite:
    """Generic SSH site adapter (§4, §8; Slice 12 real-host connection options)."""

    name = "ssh"

    def __init__(self, host_config: dict | None = None,
                 connect_timeout: int = _DEFAULT_CONNECT_TIMEOUT):
        """``host_config``: ``{host: {port, user, identity, resources}}``.

        When omitted, per-host config is sourced from the ``HERMES_SSH_*`` env
        vars (registry singleton path). ``connect_timeout`` bounds every ssh/scp.
        """
        self._host_config = dict(host_config or {})
        self.connect_timeout = connect_timeout

    # --- per-host config -------------------------------------------------

    def _host_cfg(self, host: str) -> dict:
        """Merge programmatic host_config with ``HERMES_SSH_*`` env fallbacks."""
        cfg = dict(self._host_config.get(host, {}))
        if "resources" not in cfg:
            raw = os.environ.get(f"HERMES_SSH_RESOURCES_{host}")
            if raw:
                try:
                    cfg["resources"] = json.loads(raw)
                except json.JSONDecodeError:
                    pass
        if "port" not in cfg:
            p = os.environ.get(f"HERMES_SSH_PORT_{host}")
            if p:
                cfg["port"] = int(p)
        if "user" not in cfg:
            u = os.environ.get(f"HERMES_SSH_USER_{host}")
            if u:
                cfg["user"] = u
        if "hostname" not in cfg:
            h = os.environ.get(f"HERMES_SSH_HOSTNAME_{host}")
            if h:
                cfg["hostname"] = h
        if "identity" not in cfg:
            i = os.environ.get(f"HERMES_SSH_IDENTITY_{host}")
            if i:
                cfg["identity"] = i
        return cfg

    def _resources(self, host: str) -> dict:
        return self._host_cfg(host).get("resources", {}) or {}

    def _dest(self, host: str) -> str:
        """The ssh target ``[user@]address``.

        The logical host id (crew id / worker_host) can differ from the ssh
        address: a ``hostname`` in the per-host config (e.g. ``localhost`` with a
        distinct published port) overrides it, so several logical hosts can share
        an address but claim/lease as distinct crew members.
        """
        cfg = self._host_cfg(host)
        addr = cfg.get("hostname", host)
        user = cfg.get("user")
        return f"{user}@{addr}" if user else addr

    def _ssh_opts(self, host: str) -> list[str]:
        cfg = self._host_cfg(host)
        return transport.build_ssh_opts(
            identity=cfg.get("identity"), port=cfg.get("port"),
            connect_timeout=self.connect_timeout,
        )

    def _scp_opts(self, host: str) -> list[str]:
        cfg = self._host_cfg(host)
        return transport.build_scp_opts(
            identity=cfg.get("identity"), port=cfg.get("port"),
            connect_timeout=self.connect_timeout,
        )

    # --- discovery -------------------------------------------------------

    def discover_hosts(self) -> list[str]:
        """Return configured hosts (host_config keys) or HERMES_SSH_HOSTS env."""
        if self._host_config:
            return list(self._host_config.keys())
        hosts_str = os.environ.get("HERMES_SSH_HOSTS", "")
        if not hosts_str.strip():
            return []
        return [h.strip() for h in hosts_str.split(",") if h.strip()]

    # --- provisioning ----------------------------------------------------

    def provision(self, host: str, base_ref: str) -> None:
        """Idempotent verify over SSH: the ``hermes`` CLI is present on the host.

        Assumes a baked image (no install). Just verifies remote state.
        """
        subprocess.run(
            ["ssh", *self._ssh_opts(host), self._dest(host), "command", "-v", "hermes"],
            capture_output=True,
            text=True,
            check=True,
        )

    # --- health ----------------------------------------------------------

    def health(self, host: str, agent) -> HealthReport:
        """Run reachability + latency + guard + resources checks; merge agent checks.

        Resources come from per-host config (or ``HERMES_SSH_RESOURCES_<host>``).
        """
        t0 = time.perf_counter()

        # Reachability: ssh <opts> <dest> true
        try:
            proc = subprocess.run(
                ["ssh", *self._ssh_opts(host), self._dest(host), "true"],
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

        # Guard check: assume baked (always True for ssh site)
        guard_installed = True
        guard_check = Check(
            "guard", guard_installed, "no-ship guard baked into image"
        )

        resources = self._resources(host)
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
        """Run the worker over ssh with the per-host connection options.

        Host-lost handling: CONNECTION-level failure (ssh exit 255 / connection
        refused/timeout, or a failed scp) RAISES TransportError -> serve_once does
        a no-penalty ``requeue_transport``. A worker that RAN and returned a Result
        (even a non-zero worker exit) passes through to ``agent.parse_result``.
        """
        ssh_opts = self._ssh_opts(host)
        scp_opts = self._scp_opts(host)
        dest = self._dest(host)

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

            # 1) ensure remote dir + scp the envelope up.
            try:
                subprocess.run(
                    ["ssh", *ssh_opts, dest, "mkdir", "-p", remote_dir],
                    capture_output=True,
                    text=True,
                    timeout=self.connect_timeout + 5,
                    check=True,
                )
                subprocess.run(
                    ["scp", *scp_opts, local_env, f"{dest}:{remote_env}"],
                    capture_output=True,
                    text=True,
                    timeout=self.connect_timeout + 20,
                    check=True,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                raise transport.TransportError(
                    f"Failed to copy envelope to {host}: {exc}"
                ) from exc

            # 2) run the worker over ssh.
            timeout_s = int(envelope.get("timeout_s", 3600))
            try:
                ssh_proc = subprocess.run(
                    [
                        "ssh", *ssh_opts, dest,
                        "hermes", "serve-once",
                        "--envelope", remote_env,
                        "--result", remote_result,
                        "--timeout", str(timeout_s),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=timeout_s + 60,  # extra margin
                )
            except subprocess.TimeoutExpired as exc:
                raise transport.TransportError(
                    f"SSH to {host} timed out: {exc}"
                ) from exc

            # ssh exit 255 = ssh's own connection-error code (refused/unreachable):
            # a transport-level failure -> raise for no-penalty requeue.
            if ssh_proc.returncode == 255:
                raise transport.TransportError(
                    f"SSH connection to {host} failed (exit 255): "
                    f"{ssh_proc.stderr.strip()}"
                )
            # Other non-zero exits: the worker RAN but failed; pass through and
            # let the agent parse the worker's outcome.

            # 3) scp the result back and parse it. check=True so a nonzero scp
            #    (host died between serve-once and the fetch) RAISES -> TransportError
            #    -> no-penalty requeue_transport (matches this method's contract),
            #    rather than silently returning raw="" (which would penalize).
            try:
                subprocess.run(
                    ["scp", *scp_opts, f"{dest}:{remote_result}", local_result],
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
        """Return union of resource classes across all configured hosts."""
        all_classes: set[str] = set()
        for host in self.discover_hosts():
            all_classes.update(self._resources(host).keys())
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
