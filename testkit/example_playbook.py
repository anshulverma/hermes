"""EchoPlaybook — a minimal but multi-ticket-capable example playbook (§8, §12).

Registered as "example" (matching acceptance criterion 2's `hermes run example`).
Phases: ["work", "reduce"]. `seed` reads a canned issue file (via the site's
issue_source) and yields one ticket per issue; `reduce` clusters findings by a
field and, when `run.config` requests it, emits a reduction carrying
`needs_human_ticket_ids`; `verify` returns True by default and False under a
config flag.

Stdlib-only.
"""
from __future__ import annotations

from engine import playbook as _playbook
from engine.models import (
    Driver,
    Finding,
    IssueQuery,
    Reduction,
    Result,
    Run,
    Ticket,
)

PHASES = ["work", "reduce"]


class EchoPlaybook:
    """Trivial echo playbook for tests/demos (§8, §12)."""

    name = "example"
    phases = list(PHASES)

    # --- seeding --------------------------------------------------------

    def seed(self, run: Run, site) -> list[Ticket]:
        """Yield one queued ticket per canned issue (phase 0) or per prior
        reduction (later phases)."""
        phase = run.phase or self.phases[0]
        if phase == self.phases[0]:
            query = IssueQuery(
                kind=run.config.get("issue_kind", "bug"),
                filters=run.config.get("issue_filters", {}),
                limit=run.config.get("issue_limit", 100),
            )
            issues = site.issue_source(query)
            return [
                Ticket(
                    id=f"{run.id}/t-{i}",
                    run_id=run.id,
                    phase=phase,
                    state="queued",
                    resource_req="cpu",
                    priority=0.0,
                    attempts=0,
                    payload={
                        "issue_id": issue.id,
                        "title": issue.title,
                        "cluster": issue.data.get("cluster", "default"),
                    },
                )
                for i, issue in enumerate(issues)
            ]
        # Later phases: one ticket per prior-phase reduction (multi-ticket capable).
        return [
            Ticket(
                id=f"{run.id}/{phase}-t-{i}",
                run_id=run.id,
                phase=phase,
                state="queued",
                resource_req="cpu",
                priority=0.0,
                attempts=0,
                payload={"reduction_kind": red.kind, **red.json},
            )
            for i, red in enumerate(run.reductions)
        ]

    # --- schemas / driver ----------------------------------------------

    def payload_schema(self, phase: str) -> dict:
        return {"type": "object"}

    def result_schema(self, phase: str) -> dict:
        return {"type": "object"}

    def driver(self, phase: str) -> Driver:
        return Driver(command=f"/echo-{phase}", args={"phase": phase}, loop=None)

    # --- reduce / verify -----------------------------------------------

    def reduce(
        self, run: Run, phase: str, findings: list[Finding], site
    ) -> list[Reduction]:
        """Cluster findings by their `cluster` field; optionally flag for human."""
        clusters: dict[str, list[str]] = {}
        for f in findings:
            key = f.json.get("cluster", "default")
            clusters.setdefault(key, []).append(f.json.get("ticket_id"))

        json_doc: dict = {"phase": phase, "clusters": clusters}

        if run.config.get("needs_human"):
            ids = run.config.get("needs_human_ticket_ids")
            if not ids:
                ids = [f.json.get("ticket_id") for f in findings if f.json.get("ticket_id")]
            json_doc["needs_human_ticket_ids"] = ids

        return [Reduction(kind="cluster", json=json_doc)]

    def verify(self, run: Run, ticket: Ticket, result: Result, site) -> bool:
        """True by default; False when run.config requests a re-verify failure."""
        return not bool(run.config.get("verify_fail"))

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
        """Done once the run has reached (and settled) the final phase."""
        return run.phase == self.phases[-1]


# --- registration (import side-effect) -----------------------------------

_playbook.register("example", EchoPlaybook())
