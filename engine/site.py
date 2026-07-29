"""Site Protocol + registry/loader.

A Site owns *where/how to reach a host* (transport, provisioning, health,
review submission, issue sourcing). It is paired at runtime with an Agent
(the *how to run the AI there* axis). Concrete sites (e.g. LocalSite) are
regular classes implementing this Protocol and registering on import.

Stdlib-only: uses typing.Protocol.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from engine.models import HealthReport, Issue, IssueQuery, Result

if TYPE_CHECKING:  # avoid import cycle (agent imports site imports agent)
    from engine.agent import Agent


@runtime_checkable
class Site(Protocol):
    """The site interface. Signatures are load-bearing."""

    name: str

    def discover_hosts(self) -> list[str]: ...

    def provision(self, host: str, base_ref: str) -> None: ...

    def health(self, host: str, agent: "Agent") -> HealthReport: ...

    def run_worker(self, host: str, envelope: dict, agent: "Agent") -> Result: ...

    def resource_classes(self) -> list[str]: ...

    def guarantees_no_ship(self) -> bool: ...

    def submit_for_review(self, host: str, change: dict) -> str: ...  # review URL; never lands

    def issue_source(self, query: IssueQuery) -> list[Issue]: ...


# --- registry ------------------------------------------------------------

_REGISTRY: dict[str, "Site"] = {}


def register(name: str, obj: "Site") -> None:
    """Register a site object under a name (last write wins)."""
    _REGISTRY[name] = obj


def load(name: str) -> "Site":
    """Resolve a registered site by name.

    Raises:
        KeyError: if no site is registered under `name`.
    """
    try:
        return _REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise KeyError(
            f"unknown site {name!r}; registered sites: {known}. "
            f"Import the module that registers it first."
        ) from None
