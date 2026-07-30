"""Dataclasses for Hermes engine core.

Stdlib-only: uses dataclasses, enum, typing.

"""
from dataclasses import dataclass, field
from typing import Any


# Driver model (command + args + loop; NO goal field)

@dataclass
class Driver:
    """Driver methodology: command, args, loop.

    The per-ticket goal lives on GoalEnvelope, NOT here.
    """
    command: str | None
    args: dict[str, Any]
    loop: str | None


# GoalEnvelope (goal + driver + done_contract + guardrails)

@dataclass
class GoalEnvelope:
    """Goal envelope: goal, driver, done_contract, guardrails."""
    goal: str
    driver: Driver
    done_contract: dict[str, Any]
    guardrails: dict[str, Any]


# Result (outcome + termination_reason + timestamps + refs + error_summary + payload + evidence_ref)

@dataclass
class Result:
    """Worker result: outcome, termination_reason, timestamps, refs, payload, evidence."""
    outcome: str  # ok | driver_failed | infra_failed
    termination_reason: str  # goal_met | contract_fail | driver_error | timeout | transport_error
    result_ref: str | None
    error_summary: str | None
    started_at: float
    ended_at: float
    payload: dict = field(default_factory=dict)
    evidence_ref: str | None = None
    detail: str | None = None  # raw output / stderr / stack trace captured on failure


# HealthReport + Check

@dataclass
class Check:
    """Health check result: name, ok, detail."""
    name: str
    ok: bool
    detail: str


@dataclass
class HealthReport:
    """Site health report: reachable, agent_ok, auth_ok, workspace_ready, guard_installed, resources, checks."""
    reachable: bool
    agent_ok: bool
    auth_ok: bool
    workspace_ready: bool
    guard_installed: bool
    resources: dict[str, int]
    latency_ms: int
    checks: list[Check]

    @property
    def ok(self) -> bool:
        """True iff every Check passed. Vacuously True with no checks."""
        return all(c.ok for c in self.checks)


# IssueQuery + Issue

@dataclass
class IssueQuery:
    """Issue query: kind, filters, limit."""
    kind: str
    filters: dict[str, Any] = field(default_factory=dict)
    limit: int = 100


@dataclass
class Issue:
    """Issue: id, kind, title, ref, data."""
    id: str
    kind: str
    title: str
    ref: str
    data: dict[str, Any]


# Run snapshot (id, playbook, site, base_ref, config, phase, reductions)

@dataclass
class Run:
    """Run snapshot: id, playbook, site, base_ref, config, phase, reductions."""
    id: str
    playbook: str
    site: str
    base_ref: str
    config: dict[str, Any]
    phase: str | None
    reductions: list['Reduction']


# Ticket

@dataclass
class Ticket:
    """Ticket: id, run_id, phase, state, resource_req, priority, attempts, payload."""
    id: str
    run_id: str
    phase: str
    state: str  # queued | dispatched | running | reducing | done | parked | failed | needs_human
    resource_req: str
    priority: float
    attempts: int
    payload: dict[str, Any]


# Attempt (append-only audit)

@dataclass
class Attempt:
    """Attempt audit: ticket_id, phase, host, attempt, timestamps, outcome, termination_reason, refs."""
    ticket_id: str
    phase: str
    host: str
    attempt: int
    started_at: float | None
    ended_at: float | None
    outcome: str | None
    termination_reason: str | None
    result_ref: str | None
    error_summary: str | None


# Finding

@dataclass
class Finding:
    """Finding: run_id, ticket_id, kind, json (matching the findings table DDL)."""
    run_id: str
    ticket_id: str
    kind: str
    json: dict[str, Any]


# Reduction

@dataclass
class Reduction:
    """Reduction: id, run_id, phase, kind, json, review_state (matching the
    reductions table DDL).

    The persistence fields (``id``, ``run_id``, ``phase``, ``review_state``)
    default so a playbook's ``reduce`` can return a light ``Reduction(kind=...,
    json=...)`` while the queue hydrates them fully when loading from / writing to
    the reductions table (pause/resume reload needs the phase scope)."""
    kind: str
    json: dict[str, Any]
    id: int | None = None
    run_id: str | None = None
    phase: str | None = None
    review_state: str = "pending"


# Lease

@dataclass
class Lease:
    """Lease: id, run_id, resource_class, ticket_id, host, acquired_at, ttl_s, expires_at."""
    id: str
    run_id: str
    resource_class: str
    ticket_id: str | None
    host: str | None
    acquired_at: float
    ttl_s: int
    expires_at: float


# CrewMember

@dataclass
class CrewMember:
    """CrewMember: id, site, capabilities, resources, state."""
    id: str
    site: str
    capabilities: list[str]
    resources: dict[str, int]
    state: str  # idle | busy | down | draining
