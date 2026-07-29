"""Agent Protocol (§8) + registry/loader — the worker-runtime axis.

An Agent owns *how to run the AI on a host*: it renders a Driver + envelope
into a concrete headless invocation and parses the raw output into a Result,
and contributes the agent_ok / auth_ok health checks. It is paired at runtime
with a Site (the *where/how to reach the host* axis).

Selected via HERMES_AGENT (default "claude"). Concrete agents (ClaudeAgent,
MockAgent) are regular classes implementing this Protocol and registering on
import.

Stdlib-only: uses typing.Protocol.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from engine.models import Check, Driver, Result

if TYPE_CHECKING:  # avoid import cycle (site imports agent imports site)
    from engine.site import Site


@runtime_checkable
class Agent(Protocol):
    """The agent interface (§8). Signatures are load-bearing for later slices."""

    name: str  # "claude" | "codex" | "mock"

    def build_invocation(self, envelope: dict, driver: Driver) -> list[str]: ...

    def parse_result(self, raw: str, envelope: dict) -> Result: ...

    def health_checks(self, host: str, site: "Site") -> list[Check]: ...  # agent_ok, auth_ok


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
