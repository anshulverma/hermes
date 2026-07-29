"""Playbook Protocol (§8) + registry/loader.

A Playbook defines the phases of a run, seeds tickets, supplies per-phase
payload/result schemas and drivers, reduces findings into reductions, verifies
worker results, and decides phase advancement / completion.

Stdlib-only: uses typing.Protocol. Concrete playbooks (e.g. the testkit
EchoPlaybook) are regular classes that implement this Protocol and register
themselves on import.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from engine.models import Driver, Finding, Reduction, Result, Run, Ticket

if TYPE_CHECKING:  # avoid import cycle (site imports agent imports site)
    from engine.site import Site


@runtime_checkable
class Playbook(Protocol):
    """The playbook interface (§8). Signatures are load-bearing for later slices."""

    name: str
    phases: list[str]

    def seed(self, run: Run, site: "Site") -> list[Ticket]: ...

    def payload_schema(self, phase: str) -> dict: ...

    def result_schema(self, phase: str) -> dict: ...

    def driver(self, phase: str) -> Driver: ...

    def reduce(
        self, run: Run, phase: str, findings: list[Finding], site: "Site"
    ) -> list[Reduction]: ...

    def verify(self, run: Run, ticket: Ticket, result: Result, site: "Site") -> bool: ...

    def next_phase(self, run: Run) -> str | None: ...

    def is_done(self, run: Run) -> bool: ...


# --- registry ------------------------------------------------------------

_REGISTRY: dict[str, "Playbook"] = {}


def register(name: str, obj: "Playbook") -> None:
    """Register a playbook object under a name (last write wins)."""
    _REGISTRY[name] = obj


def load(name: str) -> "Playbook":
    """Resolve a registered playbook by name.

    Raises:
        KeyError: if no playbook is registered under `name`.
    """
    try:
        return _REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise KeyError(
            f"unknown playbook {name!r}; registered playbooks: {known}. "
            f"Import the module that registers it first."
        ) from None
