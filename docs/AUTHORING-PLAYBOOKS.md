# Authoring Playbooks

This guide shows how to write a **custom playbook** and run it on Hermes without
editing the engine. It is the AUTHORING companion to `docs/RUNBOOK.md` (operations)
and `docs/DESIGN.md` (architecture).

A worked reference lives in `playbooks/dexter/playbook.py`; a minimal one in
`testkit/example_playbook.py`. Read alongside this guide.

## 1. Overview

Hermes has four extension axes: **playbook** (the job — what work to do), **site**
(the environment — hosts, tools, issue source, no-ship guard), **agent** (the
worker runtime — `claude` or `codex`), and the **engine** (the generic core
you never touch). This guide covers the playbook axis.

Write a **playbook** when you have a new *kind of job*: how to turn inputs into
per-host tickets, how to verify a worker's result, and how to reduce many results
into a decision. Write a **site** instead when you only need a new *environment*
(new hosts, a different issue source, or different tooling) for jobs you already
have; write an **agent** when you need a different *worker runtime*. The playbook
is environment- and runtime-agnostic — it never SSHes, never shells out, and never
reads the queue database. It returns plain dataclasses; the engine does the rest.

## 2. The Playbook contract

A playbook is a plain class that structurally implements the `Playbook`
`typing.Protocol` in `engine/playbook.py`. **There is no base class to inherit** —
you just define the attributes and methods with the right signatures, then call
`register("<name>", instance)`. The signatures are load-bearing.

Two attributes and eight methods:

| Member | Signature | Engine calls it… |
| --- | --- | --- |
| `name` | `str` | to resolve the playbook (`playbook.load(name)`) and stamp it on the run |
| `phases` | `list[str]` | to order the run; the CLI seeds `phases[0]` first |
| `seed` | `(run: Run, site: Site) -> list[Ticket]` | at the start of each phase, to produce work |
| `payload_schema` | `(phase: str) -> dict` | to validate each ticket's `payload` before dispatch |
| `result_schema` | `(phase: str) -> dict` | to validate a worker's `ok` result payload |
| `driver` | `(phase: str) -> Driver` | to build the agent command for the phase |
| `verify` | `(run, ticket, result, site) -> bool` | once per `ok` result — the gate |
| `reduce` | `(run, phase, findings, site) -> list[Reduction]` | once per settled phase, to aggregate |
| `next_phase` | `(run: Run) -> str \| None` | to advance; `None` means no further phase |
| `is_done` | `(run: Run) -> bool` | to decide the run is complete |

The data shapes it produces and consumes (all in `engine/models.py`):

- **`Ticket`** (what `seed` returns): `id`, `run_id`, `phase`, `state`
  (seed with `"queued"`), `resource_req` (a resource class the site offers, e.g.
  `"cpu"`), `priority` (`float`), `attempts` (`0`), `payload` (`dict`). The
  `payload` must satisfy `payload_schema(phase)`.
- **`Driver`** (what `driver` returns): `command` (`str | None`, e.g.
  `"/review-code"`), `args` (`dict`), `loop` (`str | None`). The agent renders the
  per-ticket goal separately (see below); the driver carries only the methodology
  command. `args={}` means no `k=v` tail.
- **`Result`** (what `verify` receives, built by the agent): `outcome`
  (`ok | driver_failed | infra_failed`), `termination_reason`, `result_ref`,
  `error_summary`, `started_at`, `ended_at`, `payload` (`dict`), `evidence_ref`.
- **`Finding`** (what `reduce` receives): `run_id`, `ticket_id`, `kind`, `json`.
  The engine writes one finding per `ok` result, with `json` = the result payload.
  Findings are append-only and ordered by id ascending, so a ticket that ran twice
  contributes two findings — fold to the latest per `ticket_id` if you need one.
- **`Reduction`** (what `reduce` returns): `kind` (`str`), `json` (`dict`). The
  other fields (`id`, `run_id`, `phase`, `review_state`) default, so return a
  *light* `Reduction(kind=..., json=...)` — the queue hydrates the rest. To route
  tickets to a human, put a list under `json["needs_human_ticket_ids"]`.

**How the goal reaches the worker.** The per-ticket goal lives on the ticket
payload, not on the driver. `agents/claude/agent.py` renders the prompt as
`/goal <goal>` followed by the driver command and its sorted `k=v` args (omitted
when `args={}`). So `Driver("/review-code", {}, None)` with goal `"Audit auth.py"`
becomes:

```
/goal Audit auth.py /review-code
```

**The verify gate → reduce flow** (in `engine/queue.py`):

1. A worker returns a `Result`. On `outcome == "ok"`, `record_result` writes a
   finding and calls `verify`. `True` → ticket goes `reducing`; `False` → ticket
   goes `needs_human` (a human must requeue it). `driver_failed` → terminal
   `failed`; `infra_failed` → retried up to a cap.
2. When a phase has no un-settled tickets left, the master loop calls `reduce`
   over that phase's findings. Each returned `Reduction` is persisted by
   `record_reduction`; any ticket id in `json["needs_human_ticket_ids"]` that is
   still `reducing` is routed to `needs_human` and stamped with the reduction id
   (`review_state="pending"`).
3. `finish_phase_reductions` settles the remaining `reducing` tickets to `done`.
   A human `accept`s a reduction (its tickets → `done`) or `reject`s it (→
   `failed`). Then `next_phase`/`is_done` advance or complete the run.

## 3. Copy-paste skeleton

A minimal but complete single-phase playbook. Drop it at
`playbooks/reviewer/playbook.py`:

```python
"""ReviewerPlaybook — a minimal custom playbook.

One phase ('review'): fan a code-review goal across hosts, shape-gate each
result, then cluster the findings by category. Implements the engine Playbook
Protocol structurally (no base class). Stdlib-only.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from engine import contracts, playbook as _playbook
from engine.models import Driver, Finding, Reduction, Result, Run, Ticket

if TYPE_CHECKING:
    from engine.site import Site


class ReviewerPlaybook:
    name = "reviewer"
    phases = ["review"]

    # --- seeding: one ticket per goal ----------------------------------
    def seed(self, run: Run, site: "Site") -> list[Ticket]:
        # `hermes run --goals FILE` puts the parsed lines into config["goals"].
        goals = run.config.get("goals", [])
        return [
            Ticket(
                id=f"{run.id}/review-{i}",
                run_id=run.id,
                phase="review",
                state="queued",
                resource_req="cpu",
                priority=0.0,
                attempts=0,
                payload={"goal": goal, "issue_ref": None, "context": {}},
            )
            for i, goal in enumerate(goals)
        ]

    # --- schemas -------------------------------------------------------
    def payload_schema(self, phase: str) -> dict:
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
        return {
            "type": "object",
            "required": ["category", "summary"],
            "additionalProperties": False,
            "properties": {
                "category": {"type": "string"},
                "summary": {"type": "string"},
                "diff_ref": {"type": ["string", "null"]},
            },
        }

    # --- driver: renders to "/goal <goal> /review-code" ----------------
    def driver(self, phase: str) -> Driver:
        return Driver(command="/review-code", args={}, loop=None)

    # --- verify: the shape gate ----------------------------------------
    def verify(self, run: Run, ticket: Ticket, result: Result, site: "Site") -> bool:
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
            contracts.validate_result(result_dict, self.result_schema("review"))
        except contracts.ContractError:
            return False
        return True

    # --- reduce: cluster by category, flag all for human ---------------
    def reduce(
        self, run: Run, phase: str, findings: list[Finding], site: "Site"
    ) -> list[Reduction]:
        # Fold to the latest finding per ticket (append-only, id ascending).
        latest: dict[str, Finding] = {}
        for f in findings:
            latest[f.ticket_id] = f

        clusters: dict[str, list[str]] = {}
        for f in latest.values():
            category = f.json.get("category", "uncategorized")
            clusters.setdefault(category, []).append(f.ticket_id)

        return [
            Reduction(
                kind="review_cluster",
                json={
                    "category": category,
                    "member_ticket_ids": members,
                    "needs_human_ticket_ids": members,  # every cluster → human
                },
            )
            for category, members in clusters.items()
        ]

    # --- advancement / completion --------------------------------------
    def next_phase(self, run: Run) -> str | None:
        return None  # single phase

    def is_done(self, run: Run) -> bool:
        return run.phase == "review"


# Registration happens as an import side-effect.
_playbook.register("reviewer", ReviewerPlaybook())
```

Add a package `__init__.py` at `playbooks/reviewer/__init__.py` that re-exports the
module so importing the package triggers registration:

```python
"""The reviewer playbook. Importing this package registers it under 'reviewer'."""
from playbooks.reviewer import playbook as playbook  # noqa: F401
```

> This skeleton reads goals from `config["goals"]` (what `--goals` produces). For
> issue-driven seeding, call `site.issue_source(IssueQuery(...))` instead — see
> `playbooks/dexter/playbook.py`, which supports both.

## 4. Registering and running without editing the engine

The CLI loader in `engine/cli.py` imports the built-in adapters directly, then
imports any modules named in three env vars for their **registration side-effect**
(from `engine/config.py` `KNOWN_VARS`):

- `HERMES_PLAYBOOK_MODULES` — comma-separated dotted module paths for playbooks.
- `HERMES_SITE_MODULES` — same, for custom sites.
- `HERMES_AGENT_MODULES` — same, for custom agents.

Point the variable at your module (the one that calls `register`) and it loads
with **no `cli.py` edit**. Built-in adapters (`local`/`devserver` sites, `dexter`
playbook, `claude`/`codex` agents) are imported by the loader already; custom ones use the
env vars. If a listed module fails to import, the CLI raises `ConfigError` naming
the module.

Your module must be importable from the working directory (or on `PYTHONPATH`).
With the layout above, `playbooks.reviewer` is importable from the repo root.

**Goals file** — one goal per line; blank lines and lines whose first non-space
character is `#` are skipped; surrounding whitespace is stripped (see
`_load_goals_file` in `engine/cli.py`):

```
# goals.txt — one review target per line
Audit auth.py for injection risks
Review the new rate-limiter for race conditions

Check error handling in the payment webhook
```

**Run it:**

```bash
# 1. Point the loader at your module (registration side-effect).
export HERMES_PLAYBOOK_MODULES=playbooks.reviewer

# 2. Confirm it loads (doctor imports the env-var modules; bad module => error).
hermes doctor

# 3. Dry-run: seed only, print tickets, no dispatch.
hermes run reviewer --site local --agent claude --goals goals.txt --dry-run

# 4. Execute for real (drop --dry-run).
hermes run reviewer --site local --agent claude --goals goals.txt
```

`--dry-run` seeds and prints the tickets without dispatching — the fastest check
that `seed` and `payload_schema` are correct. Dropping it drives the run to a
terminal state through the master loop.

## 5. Verify, no-ship, and reduce semantics (the safety model)

Hermes **never ships automatically** — no playbook can land code. Three layers
enforce this:

- **`verify` is the gate.** Nothing an `ok` worker returns is trusted until
  `verify` returns `True`. A `False` routes the ticket to `needs_human` rather
  than into the reduction; a human must requeue it. Keep `verify` fail-safe:
  return `False` when you cannot independently confirm the result (the dexter
  playbook re-runs an independent site check and returns `False` if it is absent
  or raises).
- **`reduce` aggregates and routes.** It folds a phase's findings into
  `Reduction`s. Any ticket listed in `json["needs_human_ticket_ids"]` waits for a
  human `accept` (→ `done`) or `reject` (→ `failed`) before the run can complete.
- **The site's no-ship guard.** Sites install runtime guards and a dispatch-time
  `guarantees_no_ship()` check; a submit goes through `submit_for_review` (a review
  URL, never a land). This is a site concern, not a playbook one — but it is why a
  playbook never needs to police shipping itself.

See `playbooks/dexter/playbook.py` for the worked version: a shape gate plus an
independent fix re-check in `verify`, cross-host clustering in `reduce`, and
best-effort learning-banking that never raises.

## 6. Testing your playbook

Two layers, mirroring the dexter tests:

- **Unit** (`tests/unit/test_dexter_playbook.py`): construct the playbook directly
  and assert each method in isolation — `seed` field-by-field, schemas via
  `contracts.validate` / `contracts.validate_result`, `driver` rendering through
  `ClaudeAgent._build_prompt`, and `reduce` clustering. No database needed.
- **Integration** (`tests/integration/test_dexter_run.py`): seed tickets, run
  `dispatch.master_loop` against the testkit doubles, and assert the end-to-end
  outcome (tickets `done`, one reduction, event stream). The doubles in
  `testkit/` — `dexter_doubles.py` (a site with `recheck_fix` + a mock agent that
  emits result payloads) and `mock_agent.py` — let you drive a full run with no
  real hosts, SSH, or agent process.

Run the suite (Docker-tagged tests excluded):

```bash
./.venv/bin/python -m pytest -m "not docker" -q
```

## 7. Local / private playbooks (this host only)

When you need playbooks or sites that **must stay on this host** and never be
committed — for example, code that references internal/Meta infra (hostnames,
dashboards, buck2/sl/testinfra wiring, `jf submit`) that isn't public — use
Hermes' **local adapter auto-discovery**.

### When to use

- Playbooks or sites that must remain private to this machine.
- Code that references internal infra and should never appear in shared repos.
- Host-specific prototypes or one-off investigations.

### Zero-config drop-in (recommended)

The simplest approach: **drop your adapter module into `$HERMES_HOME/local/`**
(default `~/.hermes/local/`) and it auto-loads on every `hermes` invocation with
**no env vars and no engine edit**.

The auto-discovery mechanism (see `engine/cli.py::_import_registration_modules`)
imports built-in adapters first, then all top-level modules in
`config.local_dir()` (default `$HERMES_HOME/local`, overridable via
`HERMES_LOCAL_DIR`). Files starting with `_` and `__pycache__` are skipped. A
broken local module raises a `ConfigError` naming the file; a missing directory
is a no-op.

**How to use it:**

1. Create your playbook/site adapter in `~/.hermes/local/<name>.py` (or as a
   package at `~/.hermes/local/<name>/__init__.py`). Each module must call
   `playbook.register()`, `site.register()`, or `agent.register()` on import.
2. Verify it loads:
   ```bash
   hermes doctor
   ```
3. Run a dry-run to confirm seeding:
   ```bash
   hermes run <name> --site <site> --agent claude --goals goals.txt --dry-run
   ```
4. Execute:
   ```bash
   hermes run <name> --site <site> --agent claude --goals goals.txt
   ```

**Files starting with `_` are ignored** by auto-discovery. Use `_templates.py` or
`_helpers.py` for shared utilities that shouldn't auto-import.

**Override the local directory:**

Set `HERMES_LOCAL_DIR` to a custom location if you don't want to use
`~/.hermes/local/`:

```bash
export HERMES_LOCAL_DIR=/path/to/my/private-adapters
hermes doctor
```

### Alternative: code living elsewhere

If your adapter code lives in a separate directory structure (e.g., a private
repo or a project-specific path), **point `PYTHONPATH` at the parent directory**
and list the module in the appropriate env var:

- `HERMES_PLAYBOOK_MODULES` — comma-separated dotted module paths for playbooks.
- `HERMES_SITE_MODULES` — same, for custom sites.
- `HERMES_AGENT_MODULES` — same, for custom agents.

Both sources (env-var modules and the local dir) are imported and **compose**
with each other. A bad module in either source raises a `ConfigError` naming it.

**Example:**

```bash
# Your adapter lives at /home/user/my-work/internal/adapters/my_playbook.py
export PYTHONPATH=/home/user/my-work/internal/adapters:$PYTHONPATH
export HERMES_PLAYBOOK_MODULES=my_playbook

hermes doctor
hermes run my_playbook --site devserver --agent claude --goals goals.txt
```

### Private SITE with internal infra

When writing a private **site** adapter that shells to internal tooling (e.g.,
buck2, jf, sl), **copy `sites/devserver/site.py` as your starting point**:

- It provides idempotent provisioning over SSH (`provision`).
- It includes the **no-ship guard** (install shims + `guarantees_no_ship()` →
  `True`).
- It shows how to run workers with the guard dir prepended to `PATH`.
- Deploy-time hooks (install cmd, submit cmd, recheck cmd) are pluggable via env
  vars, not hardcoded.

For operational details on provisioning and running workers on devserver-style
sites, see `docs/RUNBOOK.md`.

### Guardrails (so nothing leaks)

Keep your private code **outside the shared Hermes repo**. The `$HERMES_HOME/local/`
directory (default `~/.hermes/local/`) is **outside the repo** by design — good.

**Checklist:**

- **Never commit/push private adapters** to a shared repo.
- **Read tokens/keys from env**, never hardcode them. The logging layer already
  redacts known secret keys (`HERMES_SSH_IDENTITY`, `HERMES_AUTHORIZED_KEY`,
  `api_token`), and `hermes doctor` shows secret vars as `set` or `unset` (never
  the value).
- **The no-ship guard still applies** (for sites that `guarantees_no_ship()` →
  `True`). Install the guard shims during `provision` and prepend the guard dir
  to worker `PATH` in `run_worker`.

Cross-reference: `docs/AUTHORING-PLAYBOOKS.md` for the main authoring steps,
`docs/RUNBOOK.md` for operations.

## 8. Where to go next

- `docs/DESIGN.md` — the umbrella architecture (the four axes, the queue, the
  dispatch and reduction model, the safety invariants).
- `docs/RUNBOOK.md` — operations: deploy, run topology (control plane + master
  loop + worker serve loops), backup, and monitoring.
- `playbooks/dexter/playbook.py` — the full worked playbook.
- `engine/playbook.py`, `engine/models.py` — the Protocol and the exact dataclass
  shapes (the source of truth for signatures).
</content>
</invoke>
