"""MockAgent — a scenario-table fake agent adapter (§8, §12).

Selected via HERMES_AGENT=mock. Ignores the real CLI: build_invocation returns
a trivial argv and parse_result returns a deterministic Result chosen by the
envelope's payload `scenario` field. Every outcome / termination_reason is
reachable, letting integration tests exercise the full pipeline with no real
`claude`, no SSH, and no Meta.

Stdlib-only.
"""
from __future__ import annotations

import time

from engine import agent as _agent
from engine import contracts
from engine.models import Check, Driver, Result

# scenario name -> (outcome, termination_reason)
SCENARIOS: dict[str, tuple[str, str]] = {
    "ok": ("ok", "goal_met"),
    "goal_met": ("ok", "goal_met"),
    "contract_fail": ("driver_failed", "contract_fail"),
    "driver_error": ("driver_failed", "driver_error"),
    "timeout": ("driver_failed", "timeout"),
    # transport_error: agent-REPORTED infra path (RETRY with penalty).
    # This is the agent's view of transport failure, NOT the transport layer's
    # host-lost no-penalty path (which transport/requeue_transport handles in later slices).
    "infra_failed": ("infra_failed", "transport_error"),
    "transport_error": ("infra_failed", "transport_error"),
}

DEFAULT_SCENARIO = "ok"


class MockAgent:
    """Deterministic fake agent driven by a scenario table (§8, §12)."""

    name = "mock"

    def __init__(self, healthy: bool = True, scenarios: dict | None = None):
        self.healthy = healthy
        self.scenarios = dict(SCENARIOS)
        if scenarios:
            self.scenarios.update(scenarios)

    def build_invocation(self, envelope: dict, driver: Driver) -> list[str]:
        """Return a trivial argv (real work is mocked)."""
        return ["mock-agent", envelope.get("ticket_id", "")]

    def _scenario_for(self, envelope: dict) -> str:
        payload = envelope.get("payload") or {}
        return payload.get("scenario", DEFAULT_SCENARIO)

    def parse_result(self, raw: str, envelope: dict) -> Result:
        """Return a deterministic Result for this envelope's scenario.

        Integrity first: recompute ``payload_sha256`` over the RECEIVED payload
        (§6) and, on mismatch, return ``driver_failed`` / ``contract_fail`` with
        no retry — mirroring what the real ClaudeAgent does when a payload is
        corrupted in transit.
        """
        now = time.time()
        expected = envelope.get("payload_sha256")
        actual = contracts.payload_sha256(envelope.get("payload") or {})
        if expected is not None and expected != actual:
            return Result(
                outcome="driver_failed",
                termination_reason="contract_fail",
                result_ref=None,
                error_summary=(
                    f"payload_sha256 mismatch: expected {expected}, got {actual}"
                ),
                started_at=now,
                ended_at=now,
                payload={},
                evidence_ref=None,
            )

        name = self._scenario_for(envelope)
        outcome, termination_reason = self.scenarios.get(
            name, self.scenarios[DEFAULT_SCENARIO]
        )
        if outcome == "ok":
            result_ref = f"result://{envelope.get('ticket_id', 'mock')}"
            error_summary = None
            # Populate payload from envelope payload (echo it back for testing)
            payload = envelope.get("payload", {})
            evidence_ref = f"evidence://{envelope.get('ticket_id', 'mock')}"
        else:
            result_ref = None
            error_summary = f"mock scenario {name!r}: {outcome}/{termination_reason}"
            payload = {}
            evidence_ref = None
        return Result(
            outcome=outcome,
            termination_reason=termination_reason,
            result_ref=result_ref,
            error_summary=error_summary,
            started_at=now,
            ended_at=now,
            payload=payload,
            evidence_ref=evidence_ref,
        )

    def health_checks(self, host: str, site) -> list[Check]:
        """Return agent_ok / auth_ok checks (passing unless constructed unhealthy)."""
        if self.healthy:
            return [
                Check("agent", True, "mock agent available"),
                Check("auth", True, "mock auth ok"),
            ]
        return [
            Check("agent", False, "mock agent unavailable"),
            Check("auth", False, "mock auth failed"),
        ]


# --- registration (import side-effect) -----------------------------------

_agent.register("mock", MockAgent())
