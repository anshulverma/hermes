"""Scenario-aware playbook + gpu-limited site for the fleet scenario.

The stock ``EchoPlaybook`` cannot express two hooks the fleet scenario needs to
PROVE the engine's needs_human routing:

- ``verify`` must fail for exactly ONE ticket (the re-verify-marked ticket) and
  only on its FIRST execution, so an operator requeue lets attempt 2 pass. Echo's
  ``verify`` is a single per-run config flag, so it cannot target one ticket.
- ``reduce`` must cluster findings by ``root_cause.signature`` (one reduction row
  per distinct signature) and flag ONLY the cluster containing the
  reduce-review-marked ticket to ``needs_human``.

``GpuLimitedLocalSite`` is a ``LocalSite`` whose gpu capacity is a mutable knob so
a single-box test can force gpu parking (capacity 0) and later regain it
(capacity N) to exercise the park -> unpark -> done path deterministically.

Stdlib-only.
"""
from __future__ import annotations

from engine.models import Driver, Finding, Reduction, Result, Run, Ticket
from sites.local.site import LocalSite

PHASES = ["work"]


def _signature(doc: dict) -> str:
    """Extract the clustering key ``root_cause.signature`` from a finding doc."""
    root_cause = doc.get("root_cause") or {}
    return root_cause.get("signature", "unknown")


class FleetPlaybook:
    """Single-phase playbook that drives the fleet scenario's rich outcomes."""

    name = "fleet"
    phases = list(PHASES)

    def __init__(self) -> None:
        # Tickets whose first verify has already been failed. A re-verify-marked
        # ticket fails verify on attempt 1 (-> needs_human) and passes on the
        # operator-requeued attempt 2. Instance state keeps this deterministic.
        self._reverify_failed_once: set[str] = set()

    # --- seeding (unused: fleet tickets are pre-inserted) ----------------

    def seed(self, run: Run, site) -> list[Ticket]:
        return []

    # --- schemas / driver ----------------------------------------------

    def payload_schema(self, phase: str) -> dict:
        return {"type": "object"}

    def result_schema(self, phase: str) -> dict:
        return {"type": "object"}

    def driver(self, phase: str) -> Driver:
        return Driver(command=f"/fleet-{phase}", args={"phase": phase}, loop=None)

    # --- reduce / verify -----------------------------------------------

    def reduce(
        self, run: Run, phase: str, findings: list[Finding], site
    ) -> list[Reduction]:
        """Cluster findings by ``root_cause.signature``: ONE reduction per signature.

        The cluster containing a ``needs_reduce_review``-marked finding is flagged
        to ``needs_human`` (via ``needs_human_ticket_ids``), routing the whole
        cluster to human review.
        """
        clusters: dict[str, list[Finding]] = {}
        for f in findings:
            clusters.setdefault(_signature(f.json), []).append(f)

        reductions: list[Reduction] = []
        for sig in sorted(clusters):
            group = clusters[sig]
            ticket_ids = [f.ticket_id for f in group]
            doc: dict = {
                "phase": phase,
                "signature": sig,
                "ticket_ids": ticket_ids,
                "size": len(ticket_ids),
            }
            if any(f.json.get("needs_reduce_review") for f in group):
                doc["needs_human_ticket_ids"] = ticket_ids
            reductions.append(Reduction(kind="cluster", json=doc))
        return reductions

    def verify(self, run: Run, ticket: Ticket, result: Result, site) -> bool:
        """True except the re-verify-marked ticket's FIRST execution.

        First execution of the marked ticket -> False (routes to needs_human);
        after an operator requeue, the second execution -> True.
        """
        if ticket.payload.get("needs_reverify"):
            if ticket.id not in self._reverify_failed_once:
                self._reverify_failed_once.add(ticket.id)
                return False
        return True

    # --- advancement / completion --------------------------------------

    def next_phase(self, run: Run) -> str | None:
        current = run.phase
        if current is None:
            return self.phases[0]
        try:
            idx = self.phases.index(current)
        except ValueError:
            return None
        if idx + 1 < len(self.phases):
            return self.phases[idx + 1]
        return None

    def is_done(self, run: Run) -> bool:
        """Done once the single work phase has settled."""
        return run.phase == self.phases[-1]


class GpuLimitedLocalSite(LocalSite):
    """A LocalSite serving cpu+gpu with a mutable gpu capacity knob.

    Everything (provision, run_worker, no-ship guard, review) is inherited from
    LocalSite; only the resource picture is overridden so a single box can model
    a scarce gpu class. ``gpu_capacity`` is read on every health probe, so the
    heartbeat re-probe picks up capacity changes made mid-run.
    """

    def __init__(self, gpu_capacity: int = 0, cpu_capacity: int = 16) -> None:
        self.gpu_capacity = gpu_capacity
        self.cpu_capacity = cpu_capacity

    def resource_classes(self) -> list[str]:
        return ["cpu", "gpu"]

    def health(self, host: str, agent):
        report = super().health(host, agent)
        # Override the resource picture with the scenario's fixed capacities so
        # gpu contention is deterministic regardless of the real machine.
        report.resources = {"cpu": self.cpu_capacity, "gpu": self.gpu_capacity}
        return report
