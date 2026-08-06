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
    """The site interface. Signatures are load-bearing.

    Optional capabilities a site MAY also implement are declared separately (see
    ``FileFetcher``) and discovered by duck-typing, so that adding one never
    un-conforms an existing adapter.
    """

    name: str

    def discover_hosts(self) -> list[str]: ...

    def provision(self, host: str, base_ref: str) -> None: ...

    def health(self, host: str, agent: "Agent") -> HealthReport: ...

    def run_worker(self, host: str, envelope: dict, agent: "Agent") -> Result: ...

    def resource_classes(self) -> list[str]: ...

    def guarantees_no_ship(self) -> bool: ...

    def submit_for_review(self, host: str, change: dict) -> str: ...  # review URL; never lands

    def issue_source(self, query: IssueQuery) -> list[Issue]: ...


@runtime_checkable
class FileFetcher(Protocol):
    """OPTIONAL: a site that can copy one file back off a worker host.

    The site owns the transport, so it is the only thing that knows how to reach
    a host's filesystem -- a copy locally, an scp over ssh, whatever the site
    does. ``engine.trace`` uses this to bring a finished worker's transcript back
    to ``HERMES_HOME`` while the host is still up.

    ``source`` may be a glob and may start with ``~``; when several files match,
    the newest is the right one. Return True only if ``dest`` was written.
    Return False -- never raise -- for an ordinary miss.

    Not part of ``Site``: a site without it captures no traces and is in every
    other way a complete site.
    """

    def fetch_file(self, host: str, source: str, dest) -> bool: ...


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
