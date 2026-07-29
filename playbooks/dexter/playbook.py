"""DexterPlaybook — forensic investigation methodology over goals.

Implements the engine-core Playbook protocol (§2.1–2.7). Single worker phase
('solve') fans out /dexter:solve across hosts, then reduces (clusters by
root_cause.signature, banks learnings, flags duplicates for human review).

Stdlib-only.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from engine import playbook as _playbook
from engine.models import Driver, Finding, IssueQuery, Reduction, Result, Run, Ticket

if TYPE_CHECKING:
    from engine.site import Site


class DexterPlaybook:
    """The dexter forensic investigator playbook (§2)."""

    name = "dexter"
    phases = ["solve"]

    def __init__(self, sink=None):
        """Initialize playbook with an optional learning sink.

        Args:
            sink: LearningSink for banking learnings (default deferred to Slice 4).
                  Tests inject a FakeSink.
        """
        self.sink = sink

    # --- seeding (§2.1) -------------------------------------------------

    def seed(self, run: Run, site: "Site") -> list[Ticket]:
        """Yield one ticket per goal (§2.1).

        Goals from either:
        - run.config["goals"]: list[str] (direct) or str path (read with §2.1a filter)
        - run.config["issue_query"]: call site.issue_source(IssueQuery(**...))

        Returns:
            List of Ticket with exact fields per §2.1.
        """
        goals_data = []

        # Source 1: explicit goals (list or file path)
        if "goals" in run.config:
            goals_raw = run.config["goals"]
            if isinstance(goals_raw, list):
                # Direct list
                goals_data = [{"goal": g, "issue_ref": None, "priority": 0.0}
                              for g in goals_raw]
            else:
                # File path: read with §2.1a filtering
                goals_list = self._load_goals_file(goals_raw)
                goals_data = [{"goal": g, "issue_ref": None, "priority": 0.0}
                              for g in goals_list]

        # Source 2: issue_source (overrides goals if both present)
        if "issue_query" in run.config:
            query = IssueQuery(**run.config["issue_query"])
            issues = site.issue_source(query)
            goals_data = [
                {
                    "goal": issue.title,
                    "issue_ref": issue.ref,
                    "priority": issue.data.get("priority", 0.0),
                }
                for issue in issues
            ]

        # Build tickets
        tickets = []
        for i, data in enumerate(goals_data):
            ticket = Ticket(
                id=f"{run.id}/solve-{i}",
                run_id=run.id,
                phase="solve",
                state="queued",
                resource_req="cpu",
                priority=float(data["priority"]),
                attempts=0,
                payload={
                    "goal": data["goal"],
                    "issue_ref": data["issue_ref"],
                    "context": {},
                },
            )
            tickets.append(ticket)

        return tickets

    @staticmethod
    def _load_goals_file(path: str) -> list[str]:
        """Load goals from file (§2.1a format).

        Format:
        - One goal per line
        - Skip blank lines
        - Skip lines whose first non-space char is '#'
        - Strip surrounding whitespace on each kept line

        Returns:
            list[str]: Parsed goals in order (empty list if file doesn't exist)
        """
        goals = []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    if stripped[0] == '#':
                        continue
                    goals.append(stripped)
        except FileNotFoundError:
            pass
        return goals

    # --- schemas (§2.2, §2.3) -------------------------------------------

    def payload_schema(self, phase: str) -> dict:
        """Return the solve-phase payload schema (§2.2).

        Required: ["goal"]
        Properties: goal (string), issue_ref (string|null), context (object)
        additionalProperties: false
        """
        return {
            "type": "object",
            "required": ["goal"],
            "additionalProperties": False,
            "properties": {
                "goal": {"type": "string"},
                "issue_ref": {"type": ["string", "null"]},
                "context": {"type": "object"},
            },
        }

    def result_schema(self, phase: str) -> dict:
        """Return the solve-phase result schema (§2.3 dexter finding doc)."""
        return {
            "type": "object",
            "required": ["reproduced", "root_cause", "fix", "knowledge_entry", "evidence_ref"],
            "additionalProperties": False,
            "properties": {
                "reproduced": {"type": "boolean"},
                "root_cause": {
                    "type": "object",
                    "required": ["signature", "cause_category"],
                    "properties": {
                        "signature": {"type": "string"},
                        "culprit_symbol": {"type": ["string", "null"]},
                        "cause_category": {"type": "string"},
                        "mechanism": {"type": ["string", "null"]},
                    },
                },
                "fix": {
                    "type": "object",
                    "required": ["verified"],
                    "properties": {
                        "verified": {"type": "boolean"},
                        "diff_ref": {"type": ["string", "null"]},
                        "ci_status": {"type": ["string", "null"]},
                    },
                },
                "knowledge_entry": {
                    "type": "object",
                    "properties": {
                        "ref": {"type": ["string", "null"]},
                        "validated": {"type": "boolean"},
                    },
                },
                "evidence_ref": {"type": ["string", "null"]},
                "notes": {"type": ["string", "null"]},
            },
        }

    # --- driver (§2.4) --------------------------------------------------

    def driver(self, phase: str) -> Driver:
        """Return the solve-phase driver (§2.4).

        Driver("/dexter:solve", {}, None)
        args={} is deliberate: the goal reaches the worker via /goal, not args.
        """
        return Driver(command="/dexter:solve", args={}, loop=None)

    # --- verify / reduce (stubs for Slices 3-4) -------------------------

    def verify(self, run: Run, ticket: Ticket, result: Result, site: "Site") -> bool:
        """Verify a solve result (stub for Slice 3).

        Raises:
            NotImplementedError: Filled in Slice 3.
        """
        raise NotImplementedError("verify() is a stub; filled in Slice 3")

    def reduce(
        self, run: Run, phase: str, findings: list[Finding], site: "Site"
    ) -> list[Reduction]:
        """Reduce solve findings to clusters (stub for Slice 4).

        Raises:
            NotImplementedError: Filled in Slice 4.
        """
        raise NotImplementedError("reduce() is a stub; filled in Slice 4")

    # --- advancement / completion (§2.7) --------------------------------

    def next_phase(self, run: Run) -> str | None:
        """Return the next phase after the current phase (§2.7).

        Returns:
            None: Single phase; no next phase.
        """
        return None

    def is_done(self, run: Run) -> bool:
        """Return whether the run is done (§2.7).

        Returns:
            True iff run.phase == "solve" (the only phase).
        """
        return run.phase == "solve"


# --- registration (import side-effect) -----------------------------------

_playbook.register("dexter", DexterPlaybook())
