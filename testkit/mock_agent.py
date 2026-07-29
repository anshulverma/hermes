"""Mock agent adapter driven by scenario tables. Returns deterministic outcomes without running real Claude or SSH."""
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
    # host-lost no-penalty path (which transport/requeue_transport handles).
    "infra_failed": ("infra_failed", "transport_error"),
    "transport_error": ("infra_failed", "transport_error"),
}

DEFAULT_SCENARIO = "ok"


class MockAgent:
    """Deterministic fake agent driven by a scenario table.

    Extended to support (ticket_id, attempt) keying so retries can yield
    different outcomes (e.g., infra_failed on attempt 1, ok on attempt 2).
    """

    name = "mock"

    def __init__(self, healthy: bool = True, scenarios: dict | None = None):
        self.healthy = healthy
        # Support both simple string keys (backward compat) and (ticket_id, attempt) tuple keys
        self.scenarios = dict(SCENARIOS)
        if scenarios:
            self.scenarios.update(scenarios)
        # Per-ticket execution counter. The engine reuses the SAME payload across
        # retries (it increments tickets.attempts, not the payload), so the only
        # honest way to key a scenario by "attempt" is to count actual worker
        # executions per ticket. Each parse_result call for a ticket is one
        # execution, so this yields the real 1-based attempt ordinal.
        self._attempt_counts: dict[str, int] = {}

    def build_invocation(self, envelope: dict, driver: Driver) -> list[str]:
        """Return a trivial SUCCESSFUL no-op argv (real work is mocked).

        Uses ``true`` (a coreutils no-op that always exits 0) so
        ``local_transport`` runs cleanly end-to-end without depending on a
        missing ``mock-agent`` binary; ``parse_result`` supplies the actual
        deterministic ``Result`` from the scenario table.
        """
        return ["true"]

    def _scenario_for(self, envelope: dict):
        """Resolve the scenario key from an envelope.

        Derives the 1-based execution ordinal for this ticket by counting real
        parse_result calls (payloads are static across engine retries, so a
        payload ``attempt`` field would never advance). If ``(ticket_id, attempt)``
        is in the scenario table it wins (letting a retry yield a different
        outcome, e.g. infra_failed on attempt 1 then ok on attempt 2); otherwise
        we fall back to the payload's ``scenario`` string.
        """
        ticket_id = envelope.get("ticket_id")
        payload = envelope.get("payload") or {}

        if ticket_id is not None:
            attempt = self._attempt_counts.get(ticket_id, 0) + 1
            self._attempt_counts[ticket_id] = attempt
            key = (ticket_id, attempt)
            if key in self.scenarios:
                # Return the tuple key itself for the outcome lookup.
                return key

        # Fall back to scenario name from payload
        return payload.get("scenario", DEFAULT_SCENARIO)

    def parse_result(self, raw: str, envelope: dict) -> Result:
        """Return a deterministic Result for this envelope's scenario.

        Integrity first: recompute ``payload_sha256`` over the RECEIVED payload
        and, on mismatch, return ``driver_failed`` / ``contract_fail`` with
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

        key = self._scenario_for(envelope)
        # Handle both string keys and tuple keys
        if isinstance(key, tuple):
            outcome, termination_reason = self.scenarios.get(
                key, self.scenarios[DEFAULT_SCENARIO]
            )
        else:
            outcome, termination_reason = self.scenarios.get(
                key, self.scenarios[DEFAULT_SCENARIO]
            )

        # For error messages, convert key to string
        name = str(key) if isinstance(key, tuple) else key
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
