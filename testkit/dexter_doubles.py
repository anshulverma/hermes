"""DexterMockAgent + DexterLocalSite — test doubles for dexter integration.

These doubles emit dexter finding docs for testing the full dexter playbook
flow without real dexter, SSH, or Meta. They live in testkit (not production
adapters).

Stdlib-only.
"""
from __future__ import annotations

import time

from engine import agent as _agent
from engine import contracts
from engine import site as _site
from engine.models import Check, Result
from sites.local.site import LocalSite


class DexterMockAgent:
    """Dexter-aware mock agent emitting dexter finding payloads.

    Extends the stock MockAgent pattern with:
    - parse_result returns a dexter finding payload selected per (ticket_id, attempt)
      from a scenario map (not echoing the ticket payload, which is constrained
      by the solve-phase payload_schema).
    - Attempt-keying: (ticket_id, attempt) scenarios drive the fix-does-not-hold
      requeue path (attempt 1 emits a does-not-hold doc, attempt 2 emits a holds
      doc, both from the SAME ticket payload).
    - Honors payload_sha256 integrity (recompute over received envelope["payload"],
      contract_fail on mismatch).
    """

    name = "dexter_mock"

    def __init__(self):
        # Per-ticket execution counter (mirrors MockAgent._attempt_counts).
        # Each parse_result call for a ticket is one execution, yielding the
        # real 1-based attempt ordinal.
        self._attempt_counts: dict[str, int] = {}

    def build_invocation(self, envelope: dict, driver) -> list[str]:
        """Return a trivial SUCCESSFUL no-op argv (real work is mocked)."""
        return ["true"]

    def parse_result(self, raw: str, envelope: dict) -> Result:
        """Return a deterministic dexter finding Result for this envelope.

        Integrity first: recompute payload_sha256 over the RECEIVED payload
        and, on mismatch, return driver_failed/contract_fail with no retry.
        Otherwise emit a dexter finding doc selected per (ticket_id, attempt).
        """
        now = time.time()

        # INTEGRITY CHECK
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

        # SCENARIO SELECTION: (ticket_id, attempt) keying
        ticket_id = envelope.get("ticket_id")
        scenario_key = self._scenario_for(envelope)

        # Generate dexter finding payload
        payload = self._generate_dexter_payload(scenario_key, envelope)

        return Result(
            outcome="ok",
            termination_reason="goal_met",
            result_ref=f"result://{ticket_id}",
            error_summary=None,
            started_at=now,
            ended_at=now,
            payload=payload,
            evidence_ref=f"evidence://{ticket_id}",
        )

    def _scenario_for(self, envelope: dict) -> tuple:
        """Resolve the scenario key from an envelope.

        Derives the 1-based execution ordinal for this ticket by counting real
        parse_result calls. Returns (ticket_id, attempt) for keying into the
        scenario logic.
        """
        ticket_id = envelope.get("ticket_id", "unknown")
        attempt = self._attempt_counts.get(ticket_id, 0) + 1
        self._attempt_counts[ticket_id] = attempt
        return (ticket_id, attempt)

    def _generate_dexter_payload(self, scenario_key: tuple, envelope: dict) -> dict:
        """Generate a dexter finding doc.

        The scenario_key is (ticket_id, attempt). Uses goal from envelope to
        determine behavior (shared signatures, fix-does-not-hold, etc.).
        """
        ticket_id, attempt = scenario_key
        goal = envelope.get("payload", {}).get("goal", "")

        # DEFAULT SCENARIO: reproduced, fix holds
        reproduced = True
        signature = f"sig-{ticket_id}"
        culprit_symbol = "some_function"
        cause_category = "timing"
        mechanism = "race condition"
        verified = True
        diff_ref = f"D{hash(ticket_id) % 10000}"
        ci_status = "passing"
        kb_ref = f"kb-{ticket_id}"
        kb_validated = True

        # SHARED SIGNATURES: goals containing "timeout" share a signature
        if "timeout" in goal.lower():
            signature = "sig-shared-timeout"
            cause_category = "timing"
            mechanism = "timeout in wait_for_event"

        # FIX-DOES-NOT-HOLD SCENARIO: goal containing "fix-unstable"
        # Attempt 1 -> does not hold (ci_status != "passing")
        # Attempt 2 -> holds (ci_status == "passing")
        if "fix-unstable" in goal.lower():
            if attempt == 1:
                verified = False
                ci_status = "failing"
                kb_validated = False
            else:  # attempt >= 2
                verified = True
                ci_status = "passing"
                kb_validated = True

        # Build dexter finding doc
        return {
            "reproduced": reproduced,
            "root_cause": {
                "signature": signature,
                "culprit_symbol": culprit_symbol,
                "cause_category": cause_category,
                "mechanism": mechanism,
            },
            "fix": {
                "verified": verified,
                "diff_ref": diff_ref,
                "ci_status": ci_status,
            },
            "knowledge_entry": {
                "ref": kb_ref,
                "validated": kb_validated,
            },
            "evidence_ref": f"evidence://{ticket_id}",
            "notes": f"Generated for {goal}",
        }

    def health_checks(self, host: str, site) -> list[Check]:
        """Return agent_ok + auth_ok checks (passing)."""
        return [
            Check("agent", True, "dexter_mock agent available"),
            Check("auth", True, "dexter_mock auth ok"),
        ]


class DexterLocalSite(LocalSite):
    """LocalSite subclass adding recheck_fix for dexter verify.

    Adds the site extension method recheck_fix(payload) -> bool, which is a
    PURE FUNCTION of the emitted dexter finding payload (not site instance state). A
    "holds" doc => True (-> reducing), "does-not-hold" doc => False (-> needs_human).

    The verdict is payload-derived so the attempt-1-fails/attempt-2-passes flip
    comes purely from the agent's attempt-keyed doc.
    """

    name = "dexter_local"

    def recheck_fix(self, payload: dict) -> bool:
        """Independent fix re-check: pure function of the dexter finding payload.

        Returns:
            True iff payload indicates fix holds (ci_status == "passing").
            False otherwise.

        This is payload-derived (not instance state) so the agent's attempt-keyed
        doc drives the verdict flip across requeues.
        """
        # Read the ci_status field: "passing" => True, anything else => False
        ci_status = payload.get("fix", {}).get("ci_status")
        return ci_status == "passing"


# --- registration (import side-effect) -----------------------------------

_agent.register("dexter_mock", DexterMockAgent())
_site.register("dexter_local", DexterLocalSite())
