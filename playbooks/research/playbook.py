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

Every ticket carries a one-line ``title`` for operators to read and a ``goal``
that instructs the agent and names, rather than inlines, the material it works
from; that material travels in the payload's own keys (``item``, ``analyses``,
``syntheses``).

Every agent returns its prose under ``payload["answer"]``; the key is the same for
all phases so the contract is uniform rather than per-phase.

Items are identified by the id carried in their ticket ids, so the set a phase
reduces is the set that was actually seeded, even when the source answers
differently in a later process.

Stdlib-only.
"""
from __future__ import annotations

import json as _json
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from engine import config as _config
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

# Legacy regexes: recover item id from old-format ticket ids for backward
# compatibility with runs in the database that predate the sidecar.

# Item id recovered from a research ticket id (``<run>/research-<item>-<agent>``).
# The item id is greedy, so it may contain dashes; an agent name may not.
_RESEARCH_ITEM_RE = re.compile(r"/research-(.+)-[^-/]+$")

# Item id recovered from a synthesize ticket id (``<run>/synthesize-<item>``).
_SYNTHESIZE_ITEM_RE = re.compile(r"/synthesize-(.+)$")


# --- per-run sidecar ---------------------------------------------------------
#
# A small JSON file written at seed time and read at reduce time.  It maps
# every ticket id the playbook has ever allocated (for a given run) to the item
# id it was seeded for, and caches a copy of each item dict so reduce can
# enrich results even when the item source is unavailable in a later process.
#
# Shape:
#   {
#     "next_number": <int>,          # next monotonic ticket number (1-based)
#     "phases": {                    # idempotency: ids already allocated per phase
#       "<phase>": ["<ticket_id>", ...]
#     },
#     "tickets": {                   # ticket_id -> item_id (None for report)
#       "<ticket_id>": "<item_id>" | null
#     },
#     "items": {                     # item_id -> item dict (as seeded)
#       "<item_id>": { ... }
#     }
#   }
#
# Written with a temp-file + os.replace so a crash mid-write leaves the
# previous version intact.  Allocation is idempotent: re-seeding a phase whose
# suffixes are unchanged returns the ids already allocated to it, without
# touching ``next_number``.


def _sidecar_path(run_id: str) -> Path:
    """Absolute path to the per-run ticket sidecar."""
    return _config.state_dir("runs", run_id) / "tickets.json"


def _load_sidecar(run_id: str) -> dict:
    """Load the sidecar, or return a fresh empty one if none exists yet."""
    path = _sidecar_path(run_id)
    if path.exists():
        return _json.loads(path.read_text(encoding="utf-8"))
    return {"next_number": 1, "phases": {}, "tickets": {}, "items": {}}


def _save_sidecar(run_id: str, sidecar: dict) -> None:
    """Atomically replace the sidecar (temp file + os.replace)."""
    path = _sidecar_path(run_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(_json.dumps(sidecar), encoding="utf-8")
    os.replace(str(tmp), str(path))


def _allocate_phase(
    run_id: str,
    phase: str,
    entries: list[tuple[str, str | None, dict | None]],
) -> list[str]:
    """Atomically allocate monotonic ticket numbers for ``phase``.

    ``entries`` is a list of ``(suffix, item_id, item_dict)`` tuples.
    ``item_id`` and ``item_dict`` may be ``None`` for phases that have no
    per-item meaning (the single report ticket).

    Idempotent: a master restart that re-seeds an unchanged phase gets back the
    ids it allocated the first time, without incrementing ``next_number``.

    Ids are only reused when the *suffixes* still line up, because a suffix is
    part of the id and reduce reads the agent back out of it -- reusing
    ``<run>/2-codex`` for a devmate ticket would misname it. Item ids are not
    part of that test: an item source is a live query (a time window, a limit),
    so a restart may legitimately answer with a different set, and the whole
    point of the sidecar is that the id no longer has to encode the item.

    Either way the map is rewritten from ``entries``, so it always describes the
    tickets being returned right now. A map that disagreed with a ticket's
    payload would make reduce credit one item's analysis to another and drop the
    odd one out of the report entirely.
    """
    sidecar = _load_sidecar(run_id)
    phases = sidecar.setdefault("phases", {})
    items_map = sidecar.setdefault("items", {})
    tickets_map = sidecar.setdefault("tickets", {})

    suffixes = [suffix for suffix, _item_id, _item in entries]
    allocated = phases.get(phase)
    reusable = (
        allocated is not None
        and len(allocated) == len(entries)
        and [tid.rsplit("-", 1)[-1] for tid in allocated] == suffixes
    )

    if reusable:
        ticket_ids = allocated
    else:
        n = sidecar["next_number"]
        ticket_ids = []
        for suffix in suffixes:
            ticket_ids.append(f"{run_id}/{n}-{suffix}")
            n += 1
        sidecar["next_number"] = n
        phases[phase] = ticket_ids

    for tid, (_suffix, item_id, item_dict) in zip(ticket_ids, entries):
        tickets_map[tid] = item_id
        if item_id and item_dict:
            items_map[item_id] = item_dict

    _save_sidecar(run_id, sidecar)
    return ticket_ids


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
        agents = self._agents(run)
        combos = [
            (item, agent) for item in self._items(run) for agent in agents
        ]
        entries = [(agent, item["id"], item) for item, agent in combos]
        ticket_ids = _allocate_phase(run.id, "research", entries)

        tickets: list[Ticket] = []
        for tid, (item, agent) in zip(ticket_ids, combos):
            tickets.append(Ticket(
                id=tid,
                run_id=run.id,
                phase="research",
                state="queued",
                resource_req=f"agent:{agent}",
                priority=float(len(tickets)),
                attempts=0,
                payload={
                    "title": _research_title(item),
                    "goal": _research_goal(item),
                    "agent": agent,
                    "item": item,
                },
            ))
        return tickets

    def _seed_synthesize(self, run: Run) -> list[Ticket]:
        resource = self._reducer_resource(run)
        valid = [
            r for r in run.reductions
            if r.kind == "item_analyses" and r.json.get("status") == "ok"
        ]
        if not valid:
            return []
        entries = [
            ("synthesize", r.json.get("item", {}).get("id"), r.json.get("item"))
            for r in valid
        ]
        ticket_ids = _allocate_phase(run.id, "synthesize", entries)

        tickets: list[Ticket] = []
        for tid, reduction in zip(ticket_ids, valid):
            item = reduction.json.get("item", {})
            analyses = reduction.json.get("analyses", [])
            failed_agents = reduction.json.get("failed_agents", [])
            tickets.append(Ticket(
                id=tid,
                run_id=run.id,
                phase="synthesize",
                state="queued",
                resource_req=resource,
                priority=float(len(tickets)),
                attempts=0,
                payload={
                    "title": _synthesize_title(item),
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
        ticket_ids = _allocate_phase(run.id, "report", [("report", None, None)])
        return [Ticket(
            id=ticket_ids[0],
            run_id=run.id,
            phase="report",
            state="queued",
            resource_req=self._reducer_resource(run),
            priority=0.0,
            attempts=0,
            payload={
                "title": _report_title(syntheses),
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
                "required": ["title", "goal", "agent", "item"],
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "goal": {"type": "string"},
                    "agent": {"type": "string"},
                    "item": {"type": "object"},
                },
            }
        if phase == "synthesize":
            return {
                "type": "object",
                "required": ["title", "goal", "item", "analyses", "failed_agents"],
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "goal": {"type": "string"},
                    "item": {"type": "object"},
                    "analyses": {"type": "array", "items": {"type": "object"}},
                    "failed_agents": {"type": "array", "items": {"type": "string"}},
                },
            }
        return {
            "type": "object",
            "required": ["title", "goal", "syntheses", "summary"],
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string"},
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
            return self._reduce_synthesize(run, findings)
        if phase == "report":
            return self._reduce_report(findings)
        return []

    def _reduce_research(self, run: Run, findings: list[Finding]) -> list[Reduction]:
        """One reduction per item, derived from the findings' ticket ids.

        The set of items to reduce is the set of item ids present in ``findings``'
        ticket ids, so the mapping stays correct even when the source answers with a
        different set in a later process (a master restart with a different limit,
        say). The source is consulted only to enrich an item with its metadata; an
        id it does not know falls back to items cached in the sidecar, then to a
        minimal stub. The source can never ADD an item that had no tickets.

        An item whose agents all failed (or returned no text) is recorded with
        ``status="failed"`` and seeds no synthesis; partial success proceeds with
        whatever arrived, naming the agents that did not deliver.

        Ticket-id to item mapping uses the sidecar (new format).  Old-format ids
        that pre-date the sidecar fall back to the legacy ``_RESEARCH_ITEM_RE``
        regex so existing runs in the database continue to reduce correctly.
        """
        agents = self._agents(run)

        # Load the sidecar; a missing sidecar means all tickets are old-format.
        try:
            sidecar = _load_sidecar(run.id)
        except Exception:
            sidecar = {"tickets": {}, "items": {}}

        # Build (item_id, agent) -> answer and record item_id order.
        answer_by_item_agent: dict[tuple[str, str], str] = {}
        item_ids: list[str] = []
        seen: set[str] = set()

        for finding in findings:
            doc = finding.json if isinstance(finding.json, dict) else {}
            answer = _text(doc.get("answer"))

            # New format: sidecar maps ticket_id -> item_id.
            item_id: str | None = sidecar.get("tickets", {}).get(finding.ticket_id)

            if item_id is None:
                # Legacy fallback: parse item_id from the old ticket id format.
                match = _RESEARCH_ITEM_RE.search(finding.ticket_id)
                if match:
                    item_id = match.group(1)

            if item_id is None:
                continue

            # Agent name is always the final dash-segment of the ticket id;
            # agent names may not contain dashes (per the old-format contract).
            agent = finding.ticket_id.rsplit("-", 1)[-1]
            answer_by_item_agent[(item_id, agent)] = answer

            if item_id not in seen:
                item_ids.append(item_id)
                seen.add(item_id)

        # Metadata enrichment: prefer live source, fall back to sidecar copy.
        try:
            by_id = {item["id"]: item for item in self._items(run)}
        except Exception:
            by_id = {}
        sidecar_items: dict[str, dict] = sidecar.get("items", {})

        reductions = []
        for item_id in item_ids:
            item = (
                by_id.get(item_id)
                or sidecar_items.get(item_id)
                or {"id": item_id, "title": item_id, "context": ""}
            )
            analyses = []
            succeeded = []
            failed = []
            for agent in agents:
                text = answer_by_item_agent.get((item_id, agent), "")
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

    def _reduce_synthesize(self, run: Run, findings: list[Finding]) -> list[Reduction]:
        """Fold every per-item synthesis into the single report input.

        The item id is recovered from the sidecar (new format) or from the legacy
        ``_SYNTHESIZE_ITEM_RE`` regex (old format), and stored alongside its
        synthesis so the report can cite real items rather than positions.
        """
        try:
            sidecar = _load_sidecar(run.id)
        except Exception:
            sidecar = {"tickets": {}}

        syntheses = []
        for finding in findings:
            doc = finding.json if isinstance(finding.json, dict) else {}
            text = _text(doc.get("answer"))
            if not text:
                continue

            # New format: look up item_id in the sidecar.
            item_id: str | None = sidecar.get("tickets", {}).get(finding.ticket_id)

            if item_id is None:
                # Legacy fallback: parse item_id from the old ticket id format.
                match = _SYNTHESIZE_ITEM_RE.search(finding.ticket_id)
                if match:
                    item_id = match.group(1)

            syntheses.append({
                "ticket_id": finding.ticket_id,
                "item_id": item_id,
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


# --- titles and goals -------------------------------------------------------
#
# A goal has to CARRY its material, not point at it.
#
# The ticket payload does not travel to the worker. The only channel to the
# process is argv, and every adapter builds its prompt from
# `goal_envelope.goal` plus the driver -- so whatever is not in the goal string
# does not exist as far as the model is concerned. These goals used to say "the
# item is in this ticket's payload under `item`", which was simply false: the
# worker got an id and nothing to read.
#
# So the material is inlined, but bounded. Unbounded inlining is what the
# pointer was overcorrecting for -- a goal is still an instruction, not a
# document, and it is stored in tickets.payload_json and re-read every master
# cycle. The caps below are load-bearing, not cosmetic.

# Enough to identify an item in one line without letting a long title run away.
_LABEL_MAX = 60

# How much of an item's own material a goal carries. Generous enough for a real
# summary, small enough that a pathological source cannot turn a goal into a
# document.
_CONTEXT_MAX = 4000

# How much of one upstream answer (an analysis, a synthesis) a later phase's
# goal carries. Lower than _CONTEXT_MAX because these are inlined N at a time.
_ANSWER_MAX = 2000

# How many item ids a report goal enumerates before summarising the remainder.
_REPORT_IDS_SHOWN = 10


def _clip(text: str, limit: int) -> str:
    """One line of at most ``limit`` characters, ellipsised when cut."""
    line = " ".join(text.split())
    if len(line) <= limit:
        return line
    return line[: limit - 1].rstrip() + "…"


def _block(text: Any, limit: int) -> str:
    """A multi-line block of at most ``limit`` characters.

    Unlike ``_clip`` this keeps line breaks: the material being carried is
    prose the model has to read, and collapsing a structured summary onto one
    line makes it markedly harder to follow. A cut is marked, so a truncated
    block never reads as a complete one.
    """
    body = _text(text)
    if not body:
        return "(no material was provided for this item)"
    if len(body) <= limit:
        return body
    return body[:limit].rstrip() + "\n… (truncated)"


def _item_label(item: dict) -> str:
    """A short one-line name for an item.

    Just the id: a ticket title has to stay scannable at ~10-15 words, and
    splicing the item's own title in pushed it past that and truncated it
    mid-word. The full item title travels in the payload instead.
    """
    return _clip(str(item.get("id", "?")), _LABEL_MAX)


def _research_title(item: dict) -> str:
    """The list heading for one agent's analysis of one item."""
    return (
        f"Research {_item_label(item)}: what it is, what it does, and which "
        "parts it touches"
    )


def _research_goal(item: dict) -> str:
    """The per-agent analysis goal for one item, carrying the item's material."""
    return (
        f"Research {_item_label(item)} and report what you find.\n\n"
        f"--- the item ---\n{_block(item.get('context'), _CONTEXT_MAX)}\n"
        "--- end of item ---\n\n"
        "Cover what the item is, what it does, which parts of the system it "
        "touches, and anything notable about it. Ground every claim in the "
        "material above; say so plainly where it does not tell you. "
        "Do not modify, land or ship anything: this is read-only research."
    )


def _synthesize_title(item: dict) -> str:
    """The list heading for the merge of one item's analyses."""
    return (
        f"Merge the independent analyses of {_item_label(item)} into one "
        "agreed view"
    )


def _synthesize_goal(item: dict, analyses: list, failed_agents: list) -> str:
    """The merge goal for one item's independent analyses."""
    missing = (
        f" No analysis arrived from "
        f"{_clip(', '.join(str(a) for a in failed_agents), _LABEL_MAX)}; work "
        "with the ones you have and note the gap."
        if failed_agents else ""
    )
    rendered = "\n\n".join(
        f"--- analysis {n} (from {a.get('agent', '?')}) ---\n"
        f"{_block(a.get('analysis'), _ANSWER_MAX)}"
        for n, a in enumerate(analyses, start=1)
    )
    return (
        f"Merge {len(analyses)} independent analyses of {_item_label(item)} into "
        f"a single view.{missing}\n\n"
        f"--- the item ---\n{_block(item.get('context'), _CONTEXT_MAX)}\n"
        f"--- end of item ---\n\n{rendered}\n\n"
        "Produce one account of the item: where the analyses agree, where they "
        "disagree (and which reading the material supports), and what the item "
        "amounts to. Do not invent detail that no analysis reports."
    )


def _report_title(syntheses: list) -> str:
    """The list heading for the run's single report ticket."""
    return (
        f"Write the final report over {len(syntheses)} researched items, "
        "grouped into themes with throughlines"
    )


def _report_goal(syntheses: list) -> str:
    """The final report goal over every per-item synthesis."""
    ids = [str(s.get("item_id") or "?") for s in syntheses]
    shown = ", ".join(ids[:_REPORT_IDS_SHOWN])
    remainder = len(ids) - _REPORT_IDS_SHOWN
    if remainder > 0:
        shown = f"{shown} and {remainder} more"
    rendered = "\n\n".join(
        f"--- {s.get('item_id') or '?'} ---\n{_block(s.get('synthesis'), _ANSWER_MAX)}"
        for s in syntheses
    )
    return (
        f"Write one report over {len(syntheses)} researched items, from their "
        f"syntheses: {_clip(shown, 400)}.\n\n{rendered}\n\n"
        "Group the items into themes, state what each theme adds up to, and call "
        "out the throughlines and the loose ends. Every line must trace back to a "
        "synthesis above; add nothing that is not there."
    )


# --- registration (import side-effect) -----------------------------------

_playbook.register(ResearchPlaybook.name, ResearchPlaybook())
