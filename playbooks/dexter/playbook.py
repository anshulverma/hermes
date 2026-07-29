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
            sink: LearningSink for banking learnings (default DexterKbSink).
                  Tests inject a FakeSink.
        """
        if sink is None:
            from playbooks.dexter.sink import DexterKbSink
            sink = DexterKbSink()
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
        """Verify a solve result (§2.5: shape gate + D3 duck-type, fail-safe).

        Returns:
            True iff shape gate passes AND independent fix re-check confirms.
            False otherwise (malformed payload, re-check fails, or absent re-check).
        """
        from engine import contracts

        # 1. SHAPE GATE: reconstruct outer result dict and validate
        result_dict = {
            "outcome": result.outcome,
            "termination_reason": result.termination_reason,
            "result_ref": result.result_ref,
            "evidence_ref": result.evidence_ref,
            "started_at": result.started_at,
            "ended_at": result.ended_at,
            "error_summary": result.error_summary,
            "payload": result.payload,
        }

        try:
            contracts.validate_result(result_dict, self.result_schema("solve"))
        except contracts.ContractError:
            # Shape gate failed
            return False

        # 2. INDEPENDENT FIX RE-CHECK (D3, duck-typed)
        fn = getattr(site, "recheck_fix", None)
        if callable(fn):
            # Site provides recheck_fix: use it
            try:
                return bool(fn(result.payload))
            except Exception:
                return False  # D3 fail-safe: re-check could not run → do not admit
        else:
            # Site does NOT provide recheck_fix: fail safe
            # UNLESS verify_recheck_optional is set (test hook)
            if run.config.get("verify_recheck_optional"):
                return True  # Admit on shape gate alone (test hook)
            else:
                return False  # Never false pass (fail safe)

    def reduce(
        self, run: Run, phase: str, findings: list[Finding], site: "Site"
    ) -> list[Reduction]:
        """Reduce solve findings to clusters (§2.6).

        Behavior:
        1. FOLD-LATEST: collapse to last finding per ticket_id (append-only, id asc)
        2. CLUSTER by root_cause.signature
        3. Per cluster:
           - canonical = lowest NUMERIC ticket id (parse solve-<i>, not string min)
           - duplicates = other members
           - bank ONE learning via self.sink.bank (best-effort try/except)
        4. Return one light Reduction per cluster (kind="root_cause_cluster")

        MUST NEVER RAISE (best-effort banking; any exception → learning_error).

        Stale-finding note (protocol limit): reduce receives only findings + run + site,
        no ticket-state access. A ticket that returned ok once (finding written), then
        later went terminal-failed, still contributes a folded finding to a cluster.
        Mitigation: every cluster is routed to needs_human for human review; reject
        drops the cluster. Never silently banked-and-done.

        Returns:
            List of Reduction with needs_human_ticket_ids inside .json.
        """
        # 1. FOLD-LATEST: keep last finding per ticket_id
        latest_by_ticket: dict[str, Finding] = {}
        for f in findings:  # findings are ordered by id asc (queue.load_findings)
            latest_by_ticket[f.ticket_id] = f  # last write wins

        folded = list(latest_by_ticket.values())

        # 2. CLUSTER by signature
        # Guard: skip findings missing root_cause.signature (malformed)
        clusters: dict[str, list[Finding]] = {}
        skipped_malformed = 0
        for f in folded:
            try:
                sig = f.json["root_cause"]["signature"]
                if not sig:
                    # Empty signature is unclusterable
                    skipped_malformed += 1
                    continue
            except (KeyError, TypeError):
                # Missing root_cause or signature key → unclusterable
                skipped_malformed += 1
                continue
            clusters.setdefault(sig, []).append(f)

        # 3. Build one Reduction per cluster
        reductions = []
        for signature, members in clusters.items():
            # Pick canonical by NUMERIC id (parse solve-<i>)
            def _numeric_id(f: Finding) -> int:
                # f.ticket_id = "run-id/solve-123" -> extract 123
                suffix = f.ticket_id.split("/solve-")[-1]
                try:
                    return int(suffix)
                except ValueError:
                    return 0  # fallback (shouldn't happen)

            members.sort(key=_numeric_id)
            canonical = members[0]
            duplicates = members[1:]

            # Extract fields from canonical (with defensive defaults)
            cause_category = canonical.json.get("root_cause", {}).get("cause_category", "unknown")
            canonical_ticket_id = canonical.ticket_id
            canonical_diff_ref = canonical.json.get("fix", {}).get("diff_ref")

            # Build duplicate_diffs list
            duplicate_diffs = [
                {
                    "ticket_id": d.ticket_id,
                    "diff_ref": d.json["fix"].get("diff_ref"),
                }
                for d in duplicates
            ]

            # All member ticket ids
            member_ticket_ids = [m.ticket_id for m in members]

            # BANK learning (best-effort, MUST NOT RAISE)
            cluster_data = {
                "signature": signature,
                "cause_category": cause_category,
                "canonical_ticket_id": canonical_ticket_id,
                "canonical_diff_ref": canonical_diff_ref,
                "member_ticket_ids": member_ticket_ids,
            }

            learning_ref = None
            learning_error = None
            try:
                learning_ref = self.sink.bank(cluster_data)
            except Exception as exc:
                learning_error = str(exc)

            # Build Reduction (light: queue hydrates id/run_id/phase/review_state)
            reduction = Reduction(
                kind="root_cause_cluster",
                json={
                    "signature": signature,
                    "cause_category": cause_category,
                    "canonical_ticket_id": canonical_ticket_id,
                    "canonical_diff_ref": canonical_diff_ref,
                    "duplicate_diffs": duplicate_diffs,
                    "member_ticket_ids": member_ticket_ids,
                    "learning_ref": learning_ref,
                    "learning_error": learning_error,
                    "needs_human_ticket_ids": member_ticket_ids,  # ALL members
                },
            )
            reductions.append(reduction)

        return reductions

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
