# Spec: `research` playbook — multi-agent research over a set of items

## Goal

A generic playbook that researches a set of work items by fanning **each item out to every
configured agent independently**, synthesising the per-agent views into one view per item, and
then writing a single report over the whole set. It is agent-agnostic and item-agnostic: what
the items are, and which agents look at them, are both configuration.

Definition of done: `hermes run research --site fan-<agent> --agent <agent>` seeds one ticket
per (item × agent), each agent produces its own analysis, synthesis merges them per item, and a
report is produced — with no agent name or item source hardcoded in the playbook.

## Why this shape

Multiple AI tools disagree in useful ways. Running the same item through several independently
and then reconciling their answers produces a better result than trusting one — and it makes
the comparison itself visible (which tools agreed, which failed).

## Phases

`research → synthesize → report → complete`

- **research** — one ticket per (item × agent), routed to that agent by
  `resource_req = "agent:<name>"`. Each agent analyses one item on its own.
- **synthesize** — one ticket per item, merging that item's analyses; records which agents
  succeeded and which failed.
- **report** — one ticket turning all per-item syntheses into a single report.
- **complete** — a no-ticket sentinel. Required because a `Run` snapshot only carries the
  *prior* phase's reductions, so the run must advance past `report` before `is_done()` can
  observe the report it checks for.

The merge phases (`synthesize`, `report`) are served by the **first configured agent**, so
order the agent list with a dependable agent first.

## Item sources (the extension seam)

An item source supplies the things to research. It is a callable registered by name in
`playbooks/research/sources.py`, mirroring how playbooks/sites/agents register:

```python
def source(config: dict) -> list[dict]: ...
```

Each returned item is a dict with at least:
- `id` — stable, filesystem/ticket-id safe, unique within the run (used in ticket ids)
- `title` — short human label
- `context` — the text block describing the item, embedded in the agent's prompt

Extra keys are passed through untouched, so a source can carry whatever its report needs.

`sources.register(name, fn)` / `sources.load(name)`. A source module is discovered exactly like
any other adapter: it is imported for its registration side-effect (built-ins by the CLI,
private ones from `$HERMES_HOME/local`). Sources that shell out to host-specific tooling belong
in `$HERMES_HOME/local`, not in this repo.

**Built-in source `config`** (default): reads items from the run config / goals, so the playbook
is usable and testable without any external source. Each goal line becomes an item.

## Configuration

`{"source": <name>, "agents": [<agent names>], "limit": <int>, ...}` — read from the run config
when present, else from the environment (`HERMES_RESEARCH_SOURCE`, `HERMES_RESEARCH_AGENTS`,
`HERMES_RESEARCH_LIMIT`), because `hermes run` currently forwards only `--goals` into the run
config. Source-specific keys are passed through to the source. Defaults: source `config`,
agents `["claude"]`, limit `5`.

`limit` caps the number of items, because cost is items × agents.

## Fan-out routing (`sites/fan`)

Claim filtering and lease capacity are two different things:
- `site.resource_classes()` decides what a serve loop may **claim**.
- Lease **capacity** comes from the crew row, which is written from `health().resources`.

So a fan site must advertise its own single class from `resource_classes()` (routing) while
`health()` reports capacity for **every** registered fan agent — the fan processes share one
crew row, and a class with no capacity means the ticket is claimed and then parked forever.

`sites.fan.register_fan_site(agent_name)` registers a `fan-<agent>` site and adds the agent to
the shared capacity set. The built-in agents are registered at import; any other agent registers
its own fan site the same way.

## Failure policy

One agent failing must not sink the item: synthesis proceeds with whatever analyses succeeded
and records the failures. An item with **zero** successful analyses is a failure. `is_done()` is
true only when a report was actually produced — never merely because the phase advanced.

## Invariants

- No agent name, item source, or host-specific command hardcoded in the playbook.
- The set of items a phase reduces comes from what was actually **seeded** (recovered from the
  findings' ticket ids), never re-derived from a source that may answer differently in another
  process.
- Stdlib-only. Module docstrings. No doc references in code.
- Never fabricate an analysis or a report line; a missing/unparseable agent result is an honest
  failure.
