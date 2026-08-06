"""Agent Protocol: how to run the AI on a host.

An Agent renders a Driver and envelope into a concrete headless invocation, parses
raw output into a Result, and contributes agent_ok/auth_ok health checks. Paired at
runtime with a Site (the where/how to reach the host axis). Selected via HERMES_AGENT
(default "claude"). Stdlib-only.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from engine.models import Check, Driver, Result

if TYPE_CHECKING:  # avoid import cycle (site imports agent imports site)
    from engine.site import Site


@runtime_checkable
class Agent(Protocol):
    """The agent interface. Signatures are load-bearing.

    Optional capabilities an agent MAY also implement are declared separately
    (see ``TraceSource``) and discovered by duck-typing, so that adding one never
    un-conforms an existing adapter.
    """

    name: str  # "claude" | "codex" | "mock"

    def build_invocation(self, envelope: dict, driver: Driver) -> list[str]: ...

    def parse_result(self, raw: str, envelope: dict) -> Result: ...

    def health_checks(self, host: str, site: "Site") -> list[Check]: ...  # agent_ok, auth_ok


@runtime_checkable
class TraceSource(Protocol):
    """OPTIONAL: an agent that can say where its own trace lives on the host.

    A ``result_ref`` is opaque to the engine -- only the agent that minted it
    knows whether it names a file and where. An agent implementing this lets
    ``engine.trace`` pull the transcript back at result time, which is what makes
    it readable in the control plane afterwards (see ``engine/trace.py``).

    Return a host-side path, optionally a glob and optionally ``~``-relative, or
    None when this result has no trace to fetch. **The string may be expanded by
    a remote shell**, so an implementation must refuse a ref it cannot vouch for
    rather than trying to escape it.

    Not part of ``Agent``: an agent without it captures no traces and is in every
    other way a complete agent.
    """

    def trace_source(self, result: Result, envelope: dict) -> str | None: ...


# --- registry ------------------------------------------------------------

_REGISTRY: dict[str, "Agent"] = {}


def register(name: str, obj: "Agent") -> None:
    """Register an agent object under a name (last write wins)."""
    _REGISTRY[name] = obj


def load(name: str) -> "Agent":
    """Resolve a registered agent by name.

    Raises:
        KeyError: if no agent is registered under `name`.
    """
    try:
        return _REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise KeyError(
            f"unknown agent {name!r}; registered agents: {known}. "
            f"Import the module that registers it first."
        ) from None
