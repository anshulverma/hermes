"""ResearchPlaybook — research a set of items with several agents, then report.

An item source supplies the things to research. Every item is fanned out to every
configured agent for an independent analysis, the per-agent views of one item are
merged into a single view, and the merged views become one report over the whole
set. Four phases: ``research`` (one ticket per item per agent), ``synthesize`` (one
ticket per item), ``report`` (one ticket), and ``complete`` (zero tickets — a
terminal sentinel, so the report reduction is a PRIOR-phase reduction by the time
``is_done`` runs).

Tickets reach a specific agent through ``resource_req`` (``agent:<name>``), which
only a serve loop whose site advertises exactly that class can claim. The merge
phases are served by the first configured agent.

Configuration (source, agents, limit) is read from ``run.config`` when present,
falling back to ``HERMES_RESEARCH_SOURCE``, ``HERMES_RESEARCH_AGENTS``
(comma-separated) and ``HERMES_RESEARCH_LIMIT``, then to the defaults: the built-in
``config`` source, one ``claude`` agent, and at most five items. The limit matters
because cost is items times agents.

Every agent returns its prose under ``payload["answer"]``; the key is the same for
all phases so the contract is uniform rather than per-phase.

Items are identified by the id carried in their ticket ids, so the set a phase
reduces is the set that was actually seeded, even when the source answers
differently in a later process.

Stdlib-only.
"""
from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any

from engine import playbook as _playbook
from engine.models import Driver, Finding, Reduction, Result, Run, Ticket
from playbooks.research import sources

if TYPE_CHECKING:  # avoid import cycle
    from engine.site import Site


DEFAULT_SOURCE = "config"
DEFAULT_AGENTS = ["claude"]
DEFAULT_LIMIT = 5

# Bound the per-run item cache to the last N runs to prevent unbounded growth.
_CACHE_MAX = 16

# Item id recovered from a research ticket id (``<run>/research-<item>-<agent>``).
# The item id is greedy, so it may contain dashes; an agent name may not.
_RESEARCH_ITEM_RE = re.compile(r"/research-(.+)-[^-/]+$")

# Item id recovered from a synthesize ticket id (``<run>/synthesize-<item>``).
_SYNTHESIZE_ITEM_RE = re.compile(r"/synthesize-(.+)$")

# Keys the goal prose renders itself; every other item key is rendered generically.
_RENDERED_KEYS = ("id", "title", "context")


def _text(value: Any) -> str:
    """Return a stripped string, or '' for anything that is not text."""
    return value.strip() if isinstance(value, str) else ""


class ResearchPlaybook:
    """The multi-agent research playbook: research → synthesize → report → complete."""

    name = "research"

    def __init__(self):
        """Initialize the playbook with per-instance state."""
        # Instance attributes (not class attributes) so mutation stays isolated.
        self.phases = ["research", "synthesize", "report", "complete"]
        self._items_by_run: dict[str, list[dict]] = {}

    # --- run config -----------------------------------------------------

    def _source_name(self, run: Run) -> str:
        """The name of the item source this run reads from."""
        configured = run.config.get("source")
        if not configured:
            configured = os.environ.get("HERMES_RESEARCH_SOURCE") or DEFAULT_SOURCE
        return str(configured)

    def _agents(self, run: Run) -> list[str]:
        """The agents to fan out to, in the order the run configured them."""
        configured = run.config.get("agents")
        if not configured:
            env = os.environ.get("HERMES_RESEARCH_AGENTS")
            configured = [a.strip() for a in env.split(",") if a.strip()] if env else None
        return [str(a) for a in (configured or DEFAULT_AGENTS)]

    def _limit(self, run: Run) -> int:
        """The maximum number of items to research."""
        configured = run.config.get("limit")
        if configured is None:
            configured = os.environ.get("HERMES_RESEARCH_LIMIT", DEFAULT_LIMIT)
        try:
            return int(configured)
        except (TypeError, ValueError):
            return DEFAULT_LIMIT

    def _items(self, run: Run) -> list[dict]:
        """The run's items, fetched from its source and cached per run.

        Source-specific configuration keys are handed to the source untouched; the
        resolved limit rides along so a source can push it down, and is enforced
        here regardless.
        """
        cached = self._items_by_run.get(run.id)
        if cached is None:
            source_config = dict(run.config)
            source_config["limit"] = self._limit(run)
            raw = sources.load(self._source_name(run))(source_config)
            cached = self._normalize(raw, self._limit(run))
            self._items_by_run[run.id] = cached
            # Evict the oldest entry when the cache exceeds the bound.
            if len(self._items_by_run) > _CACHE_MAX:
                oldest = next(iter(self._items_by_run))
                del self._items_by_run[oldest]
        return cached

    @staticmethod
    def _normalize(raw: Any, limit: int) -> list[dict]:
        """Coerce a source's answer into safely-identified, unique, capped items."""
        items: list[dict] = []
        seen: set[str] = set()
        for index, entry in enumerate(raw or [], start=1):
            if not isinstance(entry, dict):
                continue
            item = dict(entry)
            item["id"] = sources.safe_id(item.get("id"), f"item-{index}")
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            item.setdefault("title", item["id"])
            item.setdefault("context", "")
            items.append(item)
            if len(items) >= limit:
                break
        return items

    def _reducer_resource(self, run: Run) -> str:
        """Resource class for the merge phases: the first configured agent."""
        return f"agent:{self._agents(run)[0]}"

    # --- seeding --------------------------------------------------------

    def seed(self, run: Run, site: "Site") -> list[Ticket]:
        """Seed the current phase's tickets.

        ``research`` seeds from the item source (one ticket per item per agent);
        ``synthesize`` and ``report`` seed from the previous phase's reductions,
        which the run snapshot carries. ``complete`` seeds nothing.
        """
        phase = run.phase or self.phases[0]
        if phase == "research":
            return self._seed_research(run)
        if phase == "synthesize":
            return self._seed_synthesize(run)
        if phase == "report":
            return self._seed_report(run)
        return []

    def _seed_research(self, run: Run) -> list[Ticket]:
        tickets: list[Ticket] = []
        agents = self._agents(run)
        for item in self._items(run):
            for agent in agents:
                tickets.append(Ticket(
                    id=f"{run.id}/research-{item['id']}-{agent}",
                    run_id=run.id,
                    phase="research",
                    state="queued",
                    resource_req=f"agent:{agent}",
                    priority=float(len(tickets)),
                    attempts=0,
                    payload={
                        "goal": _research_goal(item),
                        "agent": agent,
                        "item": item,
                    },
                ))
        return tickets

    def _seed_synthesize(self, run: Run) -> list[Ticket]:
        tickets: list[Ticket] = []
        resource = self._reducer_resource(run)
        for reduction in run.reductions:
            if reduction.kind != "item_analyses":
                continue
            if reduction.json.get("status") != "ok":
                continue
            item = reduction.json.get("item", {})
            analyses = reduction.json.get("analyses", [])
            failed_agents = reduction.json.get("failed_agents", [])
            tickets.append(Ticket(
                id=f"{run.id}/synthesize-{item.get('id', len(tickets))}",
                run_id=run.id,
                phase="synthesize",
                state="queued",
                resource_req=resource,
                priority=float(len(tickets)),
                attempts=0,
                payload={
                    "goal": _synthesize_goal(item, analyses, failed_agents),
                    "item": item,
                    "analyses": analyses,
                    "failed_agents": failed_agents,
                },
            ))
        return tickets

    def _seed_report(self, run: Run) -> list[Ticket]:
        syntheses: list[dict] = []
        for reduction in run.reductions:
            if reduction.kind == "item_syntheses":
                syntheses = reduction.json.get("syntheses", [])
        if not syntheses:
            return []
        return [Ticket(
            id=f"{run.id}/report-0",
            run_id=run.id,
            phase="report",
            state="queued",
            resource_req=self._reducer_resource(run),
            priority=0.0,
            attempts=0,
            payload={
                "goal": _report_goal(syntheses),
                "syntheses": syntheses,
                "summary": {"item_count": len(syntheses)},
            },
        )]

    # --- schemas --------------------------------------------------------

    def payload_schema(self, phase: str) -> dict:
        """Return the ticket-payload schema for a phase."""
        if phase == "research":
            return {
                "type": "object",
                "required": ["goal", "agent", "item"],
                "additionalProperties": False,
                "properties": {
                    "goal": {"type": "string"},
                    "agent": {"type": "string"},
                    "item": {"type": "object"},
                },
            }
        if phase == "synthesize":
            return {
                "type": "object",
                "required": ["goal", "item", "analyses", "failed_agents"],
                "additionalProperties": False,
                "properties": {
                    "goal": {"type": "string"},
                    "item": {"type": "object"},
                    "analyses": {"type": "array", "items": {"type": "object"}},
                    "failed_agents": {"type": "array", "items": {"type": "string"}},
                },
            }
        return {
            "type": "object",
            "required": ["goal", "syntheses", "summary"],
            "additionalProperties": False,
            "properties": {
                "goal": {"type": "string"},
                "syntheses": {"type": "array", "items": {"type": "object"}},
                "summary": {"type": "object"},
            },
        }

    def result_schema(self, phase: str) -> dict:
        """Return the worker-result schema for a phase.

        Every agent returns its prose under ``answer``; the key is the same for
        all phases so the contract is uniform and not per-phase.
        """
        return {
            "type": "object",
            "required": ["answer"],
            "additionalProperties": True,
            "properties": {"answer": {"type": "string"}},
        }

    # --- driver ---------------------------------------------------------

    def driver(self, phase: str) -> Driver:
        """Return the phase driver: no methodology command, goal-only prompts."""
        return Driver(command=None, args={}, loop=None)

    # --- verify ---------------------------------------------------------

    def verify(self, run: Run, ticket: Ticket, result: Result, site: "Site") -> bool:
        """Admit a result only when it carries non-empty text under ``answer``."""
        return bool(_text(result.payload.get("answer")))

    # --- reduce ---------------------------------------------------------

    def reduce(
        self, run: Run, phase: str, findings: list[Finding], site: "Site"
    ) -> list[Reduction]:
        """Fold a settled phase's findings into the next phase's input."""
        if phase == "research":
            return self._reduce_research(run, findings)
        if phase == "synthesize":
            return self._reduce_synthesize(findings)
        if phase == "report":
            return self._reduce_report(findings)
        return []

    def _reduce_research(self, run: Run, findings: list[Finding]) -> list[Reduction]:
        """One reduction per item, derived from the findings' ticket ids.

        The set of items to reduce is the set of item ids present in ``findings``'
        ticket ids, so the mapping stays correct even when the source answers with a
        different set in a later process (a master restart with a different limit,
        say). The source is consulted only to enrich an item with its metadata; an
        id it does not know falls back to a minimal item, and a source that fails
        outright enriches nothing. The source can never ADD an item that had no
        tickets.

        An item whose agents all failed (or returned no text) is recorded with
        ``status="failed"`` and seeds no synthesis; partial success proceeds with
        whatever arrived, naming the agents that did not deliver.
        """
        agents = self._agents(run)

        answer_by_ticket: dict[str, str] = {}
        item_ids: list[str] = []
        seen: set[str] = set()
        for finding in findings:
            doc = finding.json if isinstance(finding.json, dict) else {}
            answer_by_ticket[finding.ticket_id] = _text(doc.get("answer"))
            match = _RESEARCH_ITEM_RE.search(finding.ticket_id)
            if match and match.group(1) not in seen:
                item_ids.append(match.group(1))
                seen.add(match.group(1))

        # Metadata enrichment only; a source that fails enriches nothing.
        try:
            by_id = {item["id"]: item for item in self._items(run)}
        except Exception:
            by_id = {}

        reductions = []
        for item_id in item_ids:
            item = by_id.get(item_id, {"id": item_id, "title": item_id, "context": ""})
            analyses = []
            succeeded = []
            failed = []
            for agent in agents:
                text = answer_by_ticket.get(f"{run.id}/research-{item_id}-{agent}", "")
                if text:
                    analyses.append({"agent": agent, "analysis": text})
                    succeeded.append(agent)
                else:
                    failed.append(agent)
            reductions.append(Reduction(
                kind="item_analyses",
                json={
                    "item": item,
                    "analyses": analyses,
                    "succeeded_agents": succeeded,
                    "failed_agents": failed,
                    "status": "ok" if analyses else "failed",
                },
            ))
        return reductions

    @staticmethod
    def _reduce_synthesize(findings: list[Finding]) -> list[Reduction]:
        """Fold every per-item synthesis into the single report input.

        The item id is recovered from the ticket id and stored alongside its
        synthesis, so the report can cite real items rather than positions.
        """
        syntheses = []
        for finding in findings:
            doc = finding.json if isinstance(finding.json, dict) else {}
            text = _text(doc.get("answer"))
            if not text:
                continue
            match = _SYNTHESIZE_ITEM_RE.search(finding.ticket_id)
            syntheses.append({
                "ticket_id": finding.ticket_id,
                "item_id": match.group(1) if match else None,
                "synthesis": text,
            })
        if not syntheses:
            return []
        return [Reduction(
            kind="item_syntheses",
            json={"syntheses": syntheses, "item_count": len(syntheses)},
        )]

    @staticmethod
    def _reduce_report(findings: list[Finding]) -> list[Reduction]:
        """Bank the final report."""
        for finding in findings:
            doc = finding.json if isinstance(finding.json, dict) else {}
            text = _text(doc.get("answer"))
            if text:
                return [Reduction(
                    kind="research_report",
                    json={"report": text, "ticket_id": finding.ticket_id},
                )]
        return []

    # --- advancement / completion ---------------------------------------

    def next_phase(self, run: Run) -> str | None:
        """Return the phase after the run's current one, or None at the end."""
        try:
            index = self.phases.index(run.phase)
        except ValueError:
            return self.phases[0]
        if index + 1 < len(self.phases):
            return self.phases[index + 1]
        return None

    def is_done(self, run: Run) -> bool:
        """True only in the final phase AND when a non-empty report was produced.

        The sentinel phase exists so the engine reloads the report phase's
        reductions as prior-phase data before this runs. Being in an earlier phase,
        or reaching the sentinel without a real report (every synthesis failed),
        both return False so the run correctly fails.
        """
        if run.phase != self.phases[-1]:
            return False
        return any(
            isinstance(r.json, dict) and bool(_text(r.json.get("report")))
            for r in run.reductions
            if r.kind == "research_report"
        )


# --- goal prose -----------------------------------------------------------

def _item_heading(item: dict) -> str:
    """Render one item: its label, its extra keys, then its context block."""
    lines = [f"Item {item.get('id', '?')}: {item.get('title', '')}"]
    for key in sorted(item):
        if key in _RENDERED_KEYS:
            continue
        value = item[key]
        if isinstance(value, (str, int, float, bool)):
            lines.append(f"{key}: {value}")
    context = _text(item.get("context"))
    if context:
        lines.append("")
        lines.append(context)
    return "\n".join(lines)


def _research_goal(item: dict) -> str:
    """The per-agent analysis goal for one item."""
    return (
        "Research one item and report what you find.\n\n"
        f"{_item_heading(item)}\n\n"
        "Cover what the item is, what it does, which parts of the system it "
        "touches, and anything notable about it. Ground every claim in what you "
        "can actually read; say so plainly where the material does not tell you. "
        "Do not modify, land or ship anything: this is read-only research."
    )


def _synthesize_goal(item: dict, analyses: list, failed_agents: list) -> str:
    """The merge goal for one item's independent analyses."""
    blocks = "\n\n".join(
        f"Analysis from {a.get('agent', '?')}:\n{a.get('analysis', '')}"
        for a in analyses
    )
    missing = (
        f"\n\nNo analysis arrived from: {', '.join(failed_agents)}. Work with the "
        "analyses you have and note the gap."
        if failed_agents else ""
    )
    return (
        "Merge several independent analyses of one item into a single view.\n\n"
        f"{_item_heading(item)}\n\n"
        f"{blocks}{missing}\n\n"
        "Produce one account of the item: where the analyses agree, where they "
        "disagree (and which reading the material supports), and what the item "
        "amounts to. Do not invent detail that no analysis reports."
    )


def _report_goal(syntheses: list) -> str:
    """The final report goal over every per-item synthesis."""
    blocks = "\n\n".join(
        f"Synthesis for {s.get('item_id') or '?'}:\n{s.get('synthesis', '')}"
        for s in syntheses
    )
    return (
        f"Write one report over {len(syntheses)} researched items, from their "
        "syntheses.\n\n"
        f"{blocks}\n\n"
        "Group the items into themes, state what each theme adds up to, and call "
        "out the throughlines and the loose ends. Every line must trace back to a "
        "synthesis above; add nothing that is not there."
    )


# --- registration (import side-effect) -----------------------------------

_playbook.register(ResearchPlaybook.name, ResearchPlaybook())
