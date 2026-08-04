"""Fan-out sites: one site per agent, each advertising a single resource class.

A fan site behaves exactly like the built-in local site — transport,
provisioning, health, review and issue sourcing all delegate to it — but
advertises exactly one ``agent:<name>`` resource class. A serve loop bound to
one agent therefore claims only the tickets addressed to that agent.

Claim filtering and lease capacity are two different things. ``resource_classes()``
decides what a serve loop may claim; lease capacity comes from the crew row,
which is written from ``health().resources``. A site that reported only its own
class would leave every other ``agent:*`` class at capacity zero, and a ticket
in a class with no capacity is claimed and then parked forever. Because the fan
processes are keyed by host they share one crew row, so ``health()`` reports
capacity for *every* registered fan agent and whichever fan site last wrote the
row leaves correct capacity for all of them.

The local-site delegate is resolved lazily on first use, so a failure to import
it cannot prevent importing this module or running unrelated commands.

Stdlib-only; conforms to the Site protocol structurally (no inheritance).
"""
from __future__ import annotations

from engine import site as _site
from engine.models import HealthReport, Issue, IssueQuery, Result

# Every agent with a registered fan site. Shared by all fan sites in this
# process so that health() can advertise capacity for all of them.
_FAN_AGENTS: set[str] = set()

# Concurrent leases advertised per agent class. One is enough: the fan
# architecture runs one serve loop per agent.
_CAPACITY_PER_AGENT = 1


def _local_site():
    """Return the registered built-in local site."""
    import sites.local  # noqa: F401  (import side-effect: registers "local")

    return _site.load("local")


class FanSite:
    """A local site restricted to one agent's resource class."""

    def __init__(self, name: str, resource_class: str, delegate=None) -> None:
        self.name = name
        self._resource_class = resource_class
        # An explicit delegate wins; otherwise it is resolved on first use.
        self._delegate_override = delegate
        self._delegate_cache = None

    @property
    def _delegate(self):
        """The delegate site, resolved lazily to avoid import-time failures."""
        if self._delegate_override is not None:
            return self._delegate_override
        if self._delegate_cache is None:
            self._delegate_cache = _local_site()
        return self._delegate_cache

    # --- discovery / provisioning ---------------------------------------

    def discover_hosts(self) -> list[str]:
        return self._delegate.discover_hosts()

    def provision(self, host: str, base_ref: str) -> None:
        self._delegate.provision(host, base_ref)

    # --- health ---------------------------------------------------------

    def health(self, host: str, agent) -> HealthReport:
        """Return the delegate's health report with agent-class lease capacity.

        The ``resources`` dict is replaced with the capacity map covering every
        registered fan agent, so no fan-routed ticket is claimed into a class
        with zero capacity.
        """
        report = self._delegate.health(host, agent)
        return HealthReport(
            reachable=report.reachable,
            agent_ok=report.agent_ok,
            auth_ok=report.auth_ok,
            workspace_ready=report.workspace_ready,
            guard_installed=report.guard_installed,
            resources=capacity_map(),
            latency_ms=report.latency_ms,
            checks=report.checks,
        )

    # --- execution ------------------------------------------------------

    def run_worker(self, host: str, envelope: dict, agent) -> Result:
        return self._delegate.run_worker(host, envelope, agent)

    # --- capabilities ---------------------------------------------------

    def resource_classes(self) -> list[str]:
        """Advertise this site's single agent class (used for ticket routing)."""
        return [self._resource_class]

    def guarantees_no_ship(self) -> bool:
        return self._delegate.guarantees_no_ship()

    # --- review / issues ------------------------------------------------

    def submit_for_review(self, host: str, change: dict) -> str:
        return self._delegate.submit_for_review(host, change)

    def issue_source(self, query: IssueQuery) -> list[Issue]:
        return self._delegate.issue_source(query)


def capacity_map() -> dict[str, int]:
    """Lease capacity for the agent class of every registered fan agent."""
    return {f"agent:{name}": _CAPACITY_PER_AGENT for name in sorted(_FAN_AGENTS)}


def register_fan_site(agent_name: str) -> None:
    """Register a ``fan-<agent_name>`` site and give that agent lease capacity."""
    _FAN_AGENTS.add(agent_name)
    name = f"fan-{agent_name}"
    # No delegate is passed, so it is resolved lazily on first use.
    _site.register(name, FanSite(name, f"agent:{agent_name}"))
