# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state: design-phase, no code yet

This repo contains **only specs and design docs** — no `engine/`, `server/`, `web/`,
`tests/`, `pyproject.toml`, or `run_tests.sh` exist yet. The layout in `README.md`
describes the *target* structure to be built, not what's on disk. Before assuming a
module/command exists, check the filesystem.

The authoritative documents (read these before implementing anything):

- `docs/DESIGN.md` — umbrella design (hardened). Vocabulary, architecture, data
  model, state machines, safety invariants. Section numbers (§3, §5, §11…) are
  cross-referenced everywhere; treat them as the contract.
- `docs/specs/engine-core.md` — sub-project 1 spec (the **build target**): DDL,
  interfaces, contracts, ticket/run state machines, CLI surface, acceptance criteria.
- `docs/specs/engine-core-plan.md` — the TDD build plan: **Slices 0–11** in strict
  dependency order, each independently testable and GREEN before the next.
- `docs/specs/dexter-playbook.md` — sub-project 2 (first real playbook + `devserver` site).
- `docs/specs/federation-future.md` — deferred; **do not build**. Only the cheap
  "federation-ready seams" are in scope.
- `web/UI_BRIEF.md` — control-plane SPA brief (fed to Claude Design).
- `docs/auto-plan/reports/` — the hardening/convergence reports behind the specs.

## What Hermes is

A **standalone engine** (its own repo, **not** a Claude Code plugin) that fans
multi-agent work across a fleet of remote hosts, where each worker is a headless AI
coding agent (Claude Code today; Codex later). It hands out **tickets** to a **crew**
of hosts and drives them to a verified result. **Nothing ever auto-ships** — this is
enforced by construction (§11), not by prompt trust.

## The four extension axes (the core mental model)

Everything is organized around separating four concerns fused together in the
predecessor (`test-fix-harness`). The **engine is generic** — it contains zero
test/SEV/Meta/agent-specific concepts. All specialization lives behind three small
Protocol interfaces (each a one-file plugin, unit-testable in isolation):

- **Engine** (`engine/`) — generic core: queue, dispatch, transport, crew+health,
  leases, contracts, events, CLI. **Stdlib-only at runtime** (this is a hard
  invariant, asserted by an import-scan test — see acceptance criterion 5).
- **Playbook** (`playbooks/*`, `engine/playbook.py`) — *what* job: `seed` tickets,
  per-phase `payload`/`result` schemas, the `driver` per phase, master-side
  `reduce`, independent `verify`, `next_phase`, `is_done`. Site-agnostic — never
  calls `buck2`/`sl`/`testx` directly.
- **Site** (`sites/*`, `engine/site.py`) — *where/how*: host discovery/provision,
  remote-exec transport, health probes, resource classes, no-ship guard,
  issue sources. **The only place Meta-isms live.** `local` = localhost+git+shell
  (reference, ships in-repo); `meta`/`devserver` = the internal reality.
- **Agent** (`agents/*`, `engine/agent.py`) — *what AI runs the worker*:
  `build_invocation` (renders a Driver into a headless CLI argv) + `parse_result` +
  `health_checks`. `claude` (v1) builds
  `claude -p "/goal …" --permission-mode bypassPermissions`.

Selected at deploy time via env: `HERMES_SITE` (default `local`),
`HERMES_AGENT` (default `claude`). Runtime data lives **outside the repo** under
`HERMES_HOME` (default `~/.hermes`) — `queue.db`, logs, ticket payloads. The engine
owns all reads/writes; nothing hardcodes a user path.

## Non-obvious architecture rules (read the spec sections before touching these)

- **The driver model** (DESIGN §8): Hermes is a *goal dispatcher, not a prompt
  templater*. It hands each worker a `GoalEnvelope` = a completion condition
  (`/goal <condition>`) + a methodology driver (a high-level slash command like
  `/dexter:solve`, `/ci-autopilot`, `/auto-research`). The engine treats
  `driver.command` as **opaque** — the catalog grows without engine changes.
- **No turn budget.** This build has no `--max-turns`; the *only* worker budget is
  the envelope's wall-clock `timeout_s` (default 3600), enforced by a `timeout`
  wrapper at the transport layer. No `max_turns` field exists anywhere.
- **Two failure classes, resolved distinctly** (DESIGN §5, engine-core §5):
  `driver_failed` (contract_fail / driver_error / timeout) is **terminal on first
  occurrence, no retry**; `infra_failed` is **retried up to 3×** (`attempts`
  counts only these). A host lost mid-run is a **no-penalty requeue** (never
  produced a Result).
- **No-trust invariant** (§3, §11): every `ok`/`goal_met` result gets an
  independent master-side `playbook.verify()` that re-checks the claim *through the
  site*. A contradicting verdict routes the ticket to `needs_human` — the only path
  by which an `ok` result does not reach `done`.
- **No-ship by construction** (§11): sites install PATH guard shims shadowing
  land/push (`git push`, `sl`/`jf`/`arc`/`hg` land), workers use a submit-only
  identity, `submit_for_review` returns a review URL and can never land.
  `guard_installed` is an admission-gating health check. The master rejects a
  `no_ship:true` envelope if `site.guarantees_no_ship()` is false.
- **Ticket state machine** is the heart of `queue.py` — states `queued ·
  dispatched · running · reducing · done · parked · failed · needs_human`.
  `set_run_state` is the *only* writer of `runs.state`; `accept_reduction`/
  `reject_reduction`/`requeue_needs_human` are the *only* resolvers of
  `needs_human`. Study engine-core §5 (both machines) before editing.
- **Schema stays generic** (§5): playbook-specific structure never grows the core
  DB schema — it lives as namespaced `findings`/`reductions` JSON docs. SQLite,
  WAL, mode 0600, **additive-only migrations**.
- **The `server/` FastAPI dependency is isolated** to the control plane. `engine/`
  imports zero third-party packages at runtime — a CLI-only deployment never
  imports FastAPI.

## Building it (planned — nothing exists to run yet)

Follow `docs/specs/engine-core-plan.md` **slice by slice, TDD, GREEN before
advancing, commit after each slice**. The plan defines these targets:

- Tests: `pytest` (dev-only dep), under `tests/unit` and `tests/integration`.
- Test runner: `scripts/run_tests.sh` — runs both suites, prints ALL GREEN / failures.
- **Every test runs with no Meta / no SSH / no real `claude`**: the `local` site +
  `testkit/mock_agent.py` (`MockAgent`, selected via `HERMES_AGENT=mock`) provide
  full pipeline coverage. Preserve this — it's a first-class requirement.
- CLI entrypoint: `hermes` (see engine-core §10) — `run`, `run {pause|resume|stop}`,
  `reduction {accept|reject}`, `ticket requeue`, `serve`, `crew`, `status`, `show`,
  `--dry-run`.

## Conventions ported from the predecessor (keep the discipline)

- Contracts use `additionalProperties:false` strictly; the validator is
  dependency-free (ported verbatim). A contract mismatch either direction is a hard
  error (dry-run NO-GO gate).
- `queue.db` must **never** live on a networked/synced filesystem — `config`
  refuses such a `HERMES_HOME` with a clear error.
- Append-only discipline: `attempts`, `events`, `findings` are never mutated;
  `reductions` are `superseded`, never deleted.
