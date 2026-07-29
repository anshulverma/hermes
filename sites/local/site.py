"""LocalSite — the reference site that runs everything on localhost (§8).

Everything is real except `run_worker`, which is deferred to Slice 7. The site
owns transport/provisioning/health/review/issue-sourcing; the paired Agent owns
how to run the AI. LocalSite guarantees no-ship by construction.

Stdlib-only: subprocess/os for git, socket for the host id.
"""
from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path

from engine import config, site as _site
from engine.models import Check, HealthReport, Issue, IssueQuery, Result

# No-ship guard shims (§11): each shim shadows a real binary and refuses the
# land/push subcommands (log + non-zero exit), passing everything else through to
# the real binary. Maps shim name -> the subcommands it BLOCKS.
GUARD_SHIMS: dict[str, tuple[str, ...]] = {
    "git": ("push",),
    "sl": ("push", "land"),
    "hg": ("push",),
    "jf": ("land",),
    "arc": ("land",),
}

# Non-zero exit code a guard shim uses when it blocks a land/push (§11).
_GUARD_BLOCK_EXIT = 97


class LocalSite:
    """Localhost + git + shell reference site (§8)."""

    name = "local"

    # --- discovery / provisioning ---------------------------------------

    def discover_hosts(self) -> list[str]:
        """Return the single local host."""
        return [socket.gethostname()]

    def _workspace(self, host: str) -> Path:
        return config.resolve_home() / "workspaces" / host

    def guard_bin_dir(self, host: str) -> Path:
        """The per-host directory holding the no-ship guard shims (§11)."""
        return config.resolve_home() / "guard" / host / "bin"

    def _source_repo(self) -> str:
        """The repo to worktree from: HERMES_REPO or the current directory."""
        return os.environ.get("HERMES_REPO", os.getcwd())

    def provision(self, host: str, base_ref: str) -> None:
        """Ensure a git worktree for `host` at `base_ref` + install guard shims.

        Idempotent: skips an existing worktree but always (re)installs the no-ship
        guard shims (§11), so a host provisioned by an older build gains them.
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

    # --- no-ship guard (§11) --------------------------------------------

    def _install_guard(self, host: str) -> None:
        """Write the PATH guard shims that block `git push` / land (§11)."""
        import shutil

        gdir = self.guard_bin_dir(host)
        gdir.mkdir(parents=True, exist_ok=True)
        for name, blocked in GUARD_SHIMS.items():
            real = shutil.which(name)  # guard dir is not on PATH yet -> real bin
            self._write_shim(gdir / name, name, blocked, real)

    def _write_shim(self, path: Path, name: str, blocked, real) -> None:
        """Write one executable POSIX-sh guard shim."""
        import stat

        cases = "|".join(blocked)
        if real:
            passthrough = f'exec "{real}" "$@"'
        else:
            # Real binary absent: never recurse back into the shim; fail closed.
            passthrough = (
                f'echo "[hermes-no-ship-guard] real {name!r} not found" >&2; exit 127'
            )
        script = f"""#!/bin/sh
# hermes no-ship guard shim for {name!r} (§11): blocks {cases}
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
        path.write_text(script)
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def _guard_installed(self, host: str) -> bool:
        """True iff every guard shim exists and is executable (§11)."""
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

        # no-ship guard: reflect whether the PATH shims are ACTUALLY present (§11),
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
        """Execute the configured agent on localhost via local_transport (§8, §9).

        The site owns the transport (here: this box, under a ``timeout`` wrapper);
        the agent owns building the invocation and parsing the result. The worker
        runs with the no-ship guard shim dir prepended to ``PATH`` (§11), so any
        ``git push``/land it attempts is blocked by construction. A host-lost
        failure surfaces as ``transport.TransportError`` for the serve loop to
        route to a no-penalty requeue.
        """
        from engine import transport

        env = dict(os.environ)
        guard_dir = str(self.guard_bin_dir(host))
        env["PATH"] = guard_dir + os.pathsep + env.get("PATH", "")
        return transport.local_transport(envelope, host, agent, env=env)

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
                    kind=query.kind,  # echoes the query's kind (§8)
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
