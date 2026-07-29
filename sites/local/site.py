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


class LocalSite:
    """Localhost + git + shell reference site (§8)."""

    name = "local"

    # --- discovery / provisioning ---------------------------------------

    def discover_hosts(self) -> list[str]:
        """Return the single local host."""
        return [socket.gethostname()]

    def _workspace(self, host: str) -> Path:
        return config.resolve_home() / "workspaces" / host

    def _source_repo(self) -> str:
        """The repo to worktree from: HERMES_REPO or the current directory."""
        return os.environ.get("HERMES_REPO", os.getcwd())

    def provision(self, host: str, base_ref: str) -> None:
        """Ensure a git worktree for `host` checked out at `base_ref`."""
        import subprocess

        workspace = self._workspace(host)
        if workspace.exists():
            return  # already provisioned (idempotent)
        workspace.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(workspace), base_ref],
            cwd=self._source_repo(),
            check=True,
            capture_output=True,
            text=True,
        )

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

        # no-ship is guaranteed by construction for the local site
        guard_installed = self.guarantees_no_ship()
        guard = Check("guard", guard_installed, "no-ship guaranteed by construction")

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
        the agent owns building the invocation and parsing the result. A host-lost
        failure surfaces as ``transport.TransportError`` for the serve loop to
        route to a no-penalty requeue.
        """
        from engine import transport

        return transport.local_transport(envelope, host, agent)

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
