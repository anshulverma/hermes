"""LocalSite — the reference site that runs everything on localhost.

The site owns transport/provisioning/health/review/issue-sourcing; the paired
Agent owns how to run the AI. LocalSite guarantees no-ship by construction.

Stdlib-only: subprocess/os for git, socket for the host id.
"""
from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path

from engine import config, site as _site
from engine.guard import GUARD_SHIMS, GUARD_BLOCK_EXIT, render_shim_script
from engine.models import Check, HealthReport, Issue, IssueQuery, Result


class LocalSite:
    """Localhost + git + shell reference site."""

    name = "local"

    # --- discovery / provisioning ---------------------------------------

    def discover_hosts(self) -> list[str]:
        """Return the single local host."""
        return [socket.gethostname()]

    def _workspace(self, host: str) -> Path:
        return config.resolve_home() / "workspaces" / host

    def guard_bin_dir(self, host: str) -> Path:
        """The per-host directory holding the no-ship guard shims."""
        return config.resolve_home() / "guard" / host / "bin"

    def _source_repo(self) -> str:
        """The repo to worktree from: HERMES_REPO or the current directory."""
        return os.environ.get("HERMES_REPO", os.getcwd())

    def provision(self, host: str, base_ref: str) -> None:
        """Ensure a git worktree for `host` at `base_ref` + install guard shims.

        Idempotent: skips an existing worktree but always (re)installs the no-ship
        guard shims, so a host provisioned by an older build gains them.
        """
        import subprocess

        workspace = self._workspace(host)
        if not workspace.exists():
            workspace.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "worktree", "add", "--detach", str(workspace), base_ref],
                cwd=self._source_repo(),
                check=True,
                capture_output=True,
                text=True,
            )
        self._install_guard(host)

    # --- no-ship guard --------------------------------------------------

    def _install_guard(self, host: str) -> None:
        """Write the PATH guard shims that block `git push` / land."""
        import shutil

        gdir = self.guard_bin_dir(host)
        gdir.mkdir(parents=True, exist_ok=True)
        for name, blocked in GUARD_SHIMS.items():
            real = shutil.which(name)  # guard dir is not on PATH yet -> real bin
            self._write_shim(gdir / name, name, blocked, real)

    def _write_shim(self, path: Path, name: str, blocked, real) -> None:
        """Write one executable POSIX-sh guard shim."""
        import stat

        script = render_shim_script(name, blocked, real)
        path.write_text(script)
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def _guard_installed(self, host: str) -> bool:
        """True iff every guard shim exists and is executable."""
        gdir = self.guard_bin_dir(host)
        for name in GUARD_SHIMS:
            shim = gdir / name
            if not (shim.exists() and os.access(shim, os.X_OK)):
                return False
        return True

    # --- health ---------------------------------------------------------

    def health(self, host: str, agent) -> HealthReport:
        """Run transport/workspace/guard/resource checks + merge agent checks."""
        t0 = time.perf_counter()

        # Compute reachable correctly (no tautology)
        reachable = host in (socket.gethostname(), "localhost", "127.0.0.1")
        transport = Check("transport", reachable, "localhost reachable")

        workspace_ready = self._workspace(host).exists()
        workspace = Check(
            "workspace",
            workspace_ready,
            "worktree provisioned" if workspace_ready
            else "workspace not provisioned (run provision)",
        )

        # no-ship guard: reflect whether the PATH shims are ACTUALLY present,
        # not a hardcoded True — health must not lie about the guard.
        guard_installed = self._guard_installed(host)
        guard = Check(
            "guard",
            guard_installed,
            "no-ship guard shims installed" if guard_installed
            else "no-ship guard shims missing (run provision)",
        )

        cpu = os.cpu_count() or 1
        resources = {"cpu": cpu}
        resource = Check("resources", cpu > 0, f"cpu={cpu}")

        site_checks = [transport, workspace, guard, resource]
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

    # --- execution ------------------------------------------------------

    def run_worker(self, host: str, envelope: dict, agent) -> Result:
        """Execute the configured agent on localhost via local_transport.

        The site owns the transport (here: this box, under a ``timeout`` wrapper);
        the agent owns building the invocation and parsing the result. The worker
        runs with the no-ship guard shim dir prepended to ``PATH``, so any
        ``git push``/land it attempted is blocked by construction. A host-lost
        failure surfaces as ``transport.TransportError`` for the serve loop to
        route to a no-penalty requeue.

        Guard self-defense: if the guard dir is absent, install it (preferred)
        or raise — never run unguarded.
        """
        from engine import transport

        guard_dir_path = self.guard_bin_dir(host)

        # Guard self-defense: ensure guard is installed before running
        if not self._guard_installed(host):
            # Attempt to install the guard
            try:
                self._install_guard(host)
            except Exception as e:
                raise RuntimeError(
                    f"No-ship guard missing for {host} and auto-install failed: {e}. "
                    f"Refusing to run unguarded."
                ) from e

            # Re-check after install
            if not self._guard_installed(host):
                raise RuntimeError(
                    f"No-ship guard missing for {host} after install. Refusing to run unguarded."
                )

        env = dict(os.environ)
        guard_dir = str(guard_dir_path)
        env["PATH"] = guard_dir + os.pathsep + env.get("PATH", "")
        return transport.local_transport(envelope, host, agent, env=env)

    # --- file retrieval ---------------------------------------------------

    def fetch_file(self, host: str, source: str, dest) -> bool:
        """Copy one file off the host. Here the host *is* this box, so it is a copy.

        ``source`` may be a glob and may start with ``~`` -- an agent naming its
        own trace generally cannot know the exact directory (see
        ``engine.trace``). When several files match, the newest wins: that is the
        one belonging to the session that just finished.

        Returns False rather than raising for every ordinary miss -- nothing
        matched, the match is a directory, the file cannot be read. The caller
        treats a missing trace as normal.
        """
        import glob as _glob
        import shutil as _shutil

        try:
            matches = _glob.glob(os.path.expanduser(source))
            files = [m for m in matches if os.path.isfile(m)]
            if not files:
                return False
            newest = max(files, key=lambda p: os.stat(p).st_mtime)
            _shutil.copyfile(newest, dest)
            return True
        except OSError:
            return False

    # --- capabilities ---------------------------------------------------

    def resource_classes(self) -> list[str]:
        return ["cpu"]

    def guarantees_no_ship(self) -> bool:
        return True

    # --- review / issues ------------------------------------------------

    def submit_for_review(self, host: str, change: dict) -> str:
        """Create a local branch and return a file:// review ref. Never pushes."""
        import subprocess

        workspace = self._workspace(host)
        branch = change.get("branch") or f"hermes-review/{change.get('id', 'change')}"
        if workspace.exists():
            # Best-effort local branch at the current worktree HEAD; NEVER push/land.
            subprocess.run(
                ["git", "branch", "-f", branch, "HEAD"],
                cwd=workspace,
                check=False,
                capture_output=True,
                text=True,
            )
            return f"file://{workspace}#{branch}"
        return f"file://{workspace}#{branch}"

    def issue_source(self, query: IssueQuery) -> list[Issue]:
        """Read a canned JSON file named by the query (test/demo source).

        The file path is `filters['path']` if given, else
        `$HERMES_HOME/issues/<kind>.json`. Each entry becomes an Issue whose
        `kind` echoes the query's kind. Honors `query.limit`.
        """
        path = query.filters.get("path")
        if path is None:
            path = config.resolve_home() / "issues" / f"{query.kind}.json"
        else:
            path = Path(path)

        entries = json.loads(Path(path).read_text())

        issues: list[Issue] = []
        for entry in entries[: query.limit]:
            issues.append(
                Issue(
                    id=entry["id"],
                    kind=query.kind,  # echoes the query's kind
                    title=entry.get("title", ""),
                    ref=entry.get("ref", str(path)),
                    data=entry.get("data", {}),
                )
            )
        return issues


def _find_ok(checks, names) -> bool:
    """Return the ok flag of the first check whose name is in `names` (else True)."""
    for c in checks:
        if c.name in names:
            return c.ok
    return True


# --- registration (import side-effect) -----------------------------------

_site.register("local", LocalSite())
