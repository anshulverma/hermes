"""Dataclasses for Hermes engine core.

Stdlib-only: uses dataclasses, enum, typing.
Field names/types match the spec §3/§4/§8.
"""
from dataclasses import dataclass, field
from typing import Any


# §8 Driver model (command + args + loop; NO goal field)

@dataclass
class Driver:
    """Driver methodology: command, args, loop.

    The per-ticket goal lives on GoalEnvelope, NOT here.
    """
    command: str | None
    args: dict[str, Any]
    loop: str | None


# §6 GoalEnvelope (goal + driver + done_contract + guardrails)

@dataclass
class GoalEnvelope:
    """Goal envelope: goal, driver, done_contract, guardrails."""
    goal: str
    driver: Driver
    done_contract: dict[str, Any]
    guardrails: dict[str, Any]


# §6 Result (outcome + termination_reason + timestamps + refs + error_summary)

@dataclass
class Result:
    """Worker result: outcome, termination_reason, timestamps, refs."""
    outcome: str  # ok | driver_failed | infra_failed
    termination_reason: str  # goal_met | contract_fail | driver_error | timeout | transport_error
    result_ref: str | None
    error_summary: str | None
    started_at: float
    ended_at: float


# §3 HealthReport + Check

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


# §3 IssueQuery + Issue

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


# §4 Run snapshot (id, playbook, site, base_ref, config, phase, reductions)

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


# §4 Ticket

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


# §4 Attempt (append-only audit)

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


# §4 Finding

@dataclass
class Finding:
    """Finding: kind, json."""
    kind: str
    json: dict[str, Any]


# §4 Reduction

@dataclass
class Reduction:
    """Reduction: kind, json."""
    kind: str
    json: dict[str, Any]


# §4 Lease

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


# §4 CrewMember

@dataclass
class CrewMember:
    """CrewMember: id, site, capabilities, resources, state."""
    id: str
    site: str
    capabilities: list[str]
    resources: dict[str, int]
    state: str  # idle | busy | down | draining
