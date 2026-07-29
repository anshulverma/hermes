# Hermes operability — spec

Status: **draft**. Date: 2026-07-29. Parent: `docs/DESIGN.md`.
Depends on: engine-core (`docs/specs/engine-core.md`), and touches the
control-plane server (`server/`) and the `dexter` playbook + `devserver` site
(`docs/specs/dexter-playbook.md`) only where operability crosses them.

This spec covers the **operability sub-project**: packaging, operational
management, logging/observability, configuration management, and data lifecycle
for Hermes as it is **actually built today** (`engine/`, `server/`, `sites/`,
`agents/`, `playbooks/`, `fleet/`). It makes Hermes deployable and operable
without changing any engine methodology invariant.

**Grounding note.** Every requirement below is anchored to code that exists now.
Where a capability is missing, it is labeled an explicit **DELTA** (§7) — not
assumed to exist. Nothing here is implemented by this spec; it is a build target.

---

## 1. Scope

**In scope**
- **Operational logging** — a new stdlib-`logging`-based `engine/log.py`: levels,
  optional JSON formatter, context fields, env configuration; routing the existing
  `print()` calls (63 in `engine/cli.py`, 1 in `server/app.py`) through it (§2).
- **Configuration management** — consolidate and document the full env-var surface
  (§3 table), add fail-fast startup validation, and a `hermes doctor` /
  `hermes config check` command (§3).
- **Process lifecycle & deploy** — graceful SIGTERM shutdown for the long-running
  `hermes serve --api` (`engine/cli.py::cmd_serve_api`) and the per-host / master
  loops (`engine/dispatch.py::serve_loop`, `master_loop`); a control-plane
  container image + compose alongside `fleet/`; a service-unit example; documented
  run topology and migrate-on-deploy (§4).
- **Data lifecycle** — retention for the append-only `events` and `attempts`
  tables; `hermes db prune|backup|vacuum`; WAL-aware backup/restore of `queue.db`
  (§5).
- **Packaging & release** — build/publish flow off the existing `pyproject.toml`
  (setuptools, console script `hermes=engine.cli:main`, `dev`/`server` extras),
  pinned constraints for the `server` extra, a refreshed `README.md` (currently
  says "Design phase"), install/quickstart, and an operations runbook (§6).

**Out of scope (kept future/pluggable — infra that does not exist here)**
- **Metrics-backend integration.** No Prometheus/StatsD/ODS exporter. The
  existing `GET /api/runs/{id}/metrics` endpoint and the `events` feed
  (`engine/events.py`) remain the only metrics surface; `engine/log.py`'s JSON
  formatter is shaped so a future log-shipper can consume it, but shipping is not
  built.
- **Secrets manager.** The API bearer token stays a 0600 file at
  `$HERMES_HOME/api_token` (`server/auth.py`); no Vault/KMS integration. A
  non-loopback deployment still relies on a trusted proxy (DESIGN §10).
- **Meta-internal deploy specifics.** Meta-isms stay in the `meta`/`devserver`
  site adapters and their `HERMES_DEVSERVER_*` / `INVESTIGATIONS_DIR` / `DEXTER_KB_PY`
  env vars, injected at deploy time (DESIGN goal #6). This spec documents them but
  hardcodes none.
- **Log rotation daemon.** `HERMES_LOG_FILE` writes a single append file; rotation
  is delegated to the OS (`logrotate`) or the container runtime, documented in the
  runbook (§6), not implemented in-process.
- Any change to the ticket/run state machine, contracts, or the no-ship guard.

**Non-goals**
- The engine **core** (`engine/`) stays strictly stdlib-only at runtime
  (`pyproject.toml` `dependencies = []`). `logging` is stdlib, so `engine/log.py`
  preserves this (engine-core §1 non-goal, AC5).
- No new third-party runtime dependency for the CLI path. FastAPI/uvicorn stay
  isolated to the `server` extra (DESIGN §14 "RESOLVED — FastAPI dependency").

---

## 2. Logging & diagnostics

### 2.1 The two feeds — domain/audit vs. operational (CRUCIAL DISTINCTION)

Hermes already has **one** structured feed, and it is a *domain/audit* feed, not
operational diagnostics:

- **`events` table** (`engine/events.py`, DDL in engine-core §4; `EVENT_KINDS`
  frozenset of 23 kinds) — the append-only **domain/audit** record: what happened
  to runs/tickets/crew/leases/reductions, consumed by `hermes status`, the API
  (`GET /api/events`), and the websocket feed. **This stays exactly as is.** It is
  the source of truth for *state history* and drives the UI. It is emitted inside
  the caller's transaction (`emit()` does not commit) so it is atomic with the
  state change it describes.

This sub-project adds the **second, orthogonal** feed:

- **Python `logging` (`engine/log.py`, new — DELTA D1)** — **operational
  diagnostics**: how the *process* is behaving (loop iterations, subprocess
  invocations, transport timings, exceptions with stack traces, config resolution,
  shutdown). It is line-oriented, goes to stderr/file, is never read back by the
  engine, and carries no schema or transactional guarantee.

**How they relate (must be spec'd explicitly):**
- A **domain event** (e.g. `ticket_failed`) is emitted to the `events` table for
  the audit trail **and** may be accompanied by an operational log line at the
  appropriate level for the operator tailing logs. They are complementary, never a
  substitute for each other. Code that emits an event does **not** have to log, and
  code that logs does **not** emit an event unless the state change warrants it.
- **No operational state lives in logs.** Anything an operator or the UI must
  *query* (counts, banners, history) remains in `events`/tables. Logs are for
  *debugging a process*, not for reconstructing state.
- The existing `HERMES_DEBUG` env var (`engine/cli.py:740`, currently the *only*
  diagnostic knob — it toggles a `traceback.print_exc()` on a top-level CLI
  exception) is **subsumed**: `HERMES_DEBUG=1` becomes an alias for
  `HERMES_LOG_LEVEL=DEBUG` (§2.4), and the top-level handler logs the exception via
  `logger.exception(...)` instead of `traceback.print_exc()`.

### 2.2 `engine/log.py` API (DELTA D1)

A small stdlib-only module:

- `get_logger(name: str) -> logging.Logger` — returns a namespaced child of the
  root `hermes` logger (e.g. `hermes.dispatch`, `hermes.transport`,
  `hermes.server`). Never configures handlers itself.
- `configure(*, level: str|None=None, fmt: str|None=None, file: str|None=None,
  context: dict|None=None) -> None` — idempotent one-time root configuration
  (guarded so repeated CLI/serve entry does not stack handlers). Reads env
  defaults (§2.4) when args are omitted. Installs exactly one handler
  (stderr, or a `FileHandler` at `file`), sets the level, and selects the
  formatter.
- `bind(**fields) -> contextmanager` — pushes context fields (`run_id`,
  `ticket_id`, `host`) onto a `contextvars`-backed store so nested calls inherit
  them without threading a logger through every signature. A `logging.Filter`
  injects the current bound fields into every record.

Two formatters:
- **text** (default) — `"<ts> <level> <name> [run_id=… ticket_id=… host=…] message"`;
  bound fields omitted when unset. Human-readable for a terminal / `podman logs`.
- **json** (`HERMES_LOG_FORMAT=json`) — one JSON object per line with keys
  `ts, level, logger, msg, run_id, ticket_id, host` plus any `extra`. Shaped for a
  future log-shipper (§1 out-of-scope). Stdlib `json` only.

`configure()` is called once per process entry point: at the top of `main()` in
`engine/cli.py` (covers `run`, `serve`, `serve-once`, all CLI commands) and inside
`create_app()` in `server/app.py`.

### 2.3 What each layer logs, and at which level

| Layer (module) | INFO | WARNING | ERROR/EXCEPTION | DEBUG |
|---|---|---|---|---|
| **master loop** (`engine/dispatch.py::master_loop`) | run start/finish, phase advance, reduce ran (n reductions) | attention conditions surfaced (parked ratio, no-progress, all-crew-down), a run marked `failed`/stuck | uncaught cycle exception (with stack) — but note `reduce` must still never raise (dexter §2.6) | per-cycle sweep summary, claim/reduce/advance decisions |
| **serve loop** (`engine/dispatch.py::serve_loop`, `transport.serve_once_for_host`) | ticket claimed/started/recorded, lease acquired, ticket parked (no lease) | envelope/contract validation NO-GO → requeue-with-penalty; transport error → no-penalty requeue + host→down | subprocess launch failure | argv built, envelope path, timeout wrapper used, `payload_sha256` |
| **worker-runner** (`engine/cli.py::cmd_serve_once`) | one line: agent, timeout, exit code | non-zero worker exit | failed to read envelope / write result | full argv, stdout length |
| **API** (`server/app.py`, `engine/cli.py::cmd_serve_api`) | server bind+port+home on start, token *location* (never value), graceful shutdown | 4xx that indicates operator error (unknown site/agent on `/api/crew`) | 5xx / unhandled endpoint exception; replace the raw `print(f"WebSocket error: {e}")` (`server/app.py:1327`) with `logger.exception` | per-request method+path+status, WS connect/disconnect, WS poll cursor |
| **sites/transport** (`sites/*/site.py`, `engine/transport.py`) | provision start/done, health verdict (ok + failing check names) | a failing health `Check`, reachability loss, guard-not-installed | ssh/scp non-zero exits mapped to `TransportError` | full ssh/scp argv, connect timeout, per-host cfg *keys* (never identity contents) |

Guidance baked into the spec: **INFO = the normal operational narrative**
(safe to run at in prod), **WARNING = something an operator should notice but the
system handled**, **ERROR/EXCEPTION = a failure with a stack trace**, **DEBUG =
verbose developer detail** (argv, digests, cursors).

### 2.4 Env configuration

| Var | Meaning | Default |
|---|---|---|
| `HERMES_LOG_LEVEL` | Root `hermes` logger level (`DEBUG`/`INFO`/`WARNING`/`ERROR`). | `INFO` |
| `HERMES_LOG_FORMAT` | `text` or `json`. | `text` |
| `HERMES_LOG_FILE` | If set, append logs to this path instead of stderr. Must obey the same networked-FS / local-storage discipline as `HERMES_HOME`; defaults under `$HERMES_HOME/logs/` are natural but not required (see §5 note on the unused `logs/` dir). | unset (stderr) |
| `HERMES_DEBUG` | Back-compat alias: truthy ⇒ level `DEBUG`. Loses to an explicit `HERMES_LOG_LEVEL`. | unset |

### 2.5 HARD INVARIANT — never log the API token or secrets

Ties to `server/auth.py` and `server/app.py`:
- The bearer token (`app_token`, `load_or_create_token`/`rotate_token`) must
  **never** appear in a log line. Server startup logs the token **location**
  (`home / "api_token"`) exactly as `cmd_serve_api` already prints it — never the
  value. `rotate_token` logs "token rotated" with no value.
- The websocket handler currently reads `?token=` and an `Authorization: Bearer`
  header (`server/app.py:1247`, `:1272`). Neither the query string nor the header
  may be logged. The per-request DEBUG log (§2.3) logs **method + path with the
  query string stripped/redacted** so `?token=…` never lands in a log.
- The token-bootstrap `<script>window.__HERMES_TOKEN__="…"` injection
  (`server/app.py:1366`) is response HTML, not a log; it must never be echoed to a
  log at any level.
- SSH identities: sites log per-host config **keys**, never identity file contents
  or `HERMES_AUTHORIZED_KEY` (`fleet/*`) values.
- A single redaction helper in `engine/log.py` (`redact(mapping)` dropping known
  secret keys: `token`, `api_token`, `authorized_key`, `identity`) is applied
  before any structured `extra` is logged, as defense in depth.

This invariant is verified by a test (§8).

---

## 3. Configuration management

### 3.1 Full env-var surface (enumerated from the code)

Every `HERMES_*` / `DEXTER_*` / `INVESTIGATIONS_DIR` reference across `engine/`,
`server/`, `sites/`, `agents/`, `playbooks/`, `fleet/`, `testkit/`:

| Var | Read by | Meaning | Default |
|---|---|---|---|
| `HERMES_HOME` | `engine/config.py`, `server/auth.py`, `server/app.py`, `sites/local/site.py`, `testkit/fixtures.py` | Runtime-data root (queue.db, api_token, workspaces, guard shims, logs). Refused on a networked/synced mount. | `~/.hermes` |
| `HERMES_NETWORKED_PREFIXES` | `engine/config.py` | Comma-separated mount-prefix denylist for the networked-FS guard. | `/mnt/fuse,/mnt/nfs` |
| `HERMES_SITE` | `engine/config.py` | Default site name when `--site` omitted. | `local` |
| `HERMES_AGENT` | `engine/config.py`, `engine/cli.py`, `engine/agent.py`, `agents/claude/agent.py`, `testkit/mock_agent.py`, `fleet/*` | Worker-runtime adapter to load. | `claude` |
| `HERMES_HEARTBEAT_S` | `engine/config.py`, `engine/dispatch.py` | Crew-health / lease-renew heartbeat + no-progress window (seconds). | `30` |
| `HERMES_DEBUG` | `engine/cli.py` | Print tracebacks on CLI error (→ subsumed by `HERMES_LOG_LEVEL`, §2.1). | unset |
| `HERMES_BIND` | `engine/cli.py`, `server/app.py` | API bind address; non-loopback gates all GETs on the token. | `127.0.0.1` |
| `HERMES_WS_POLL_S` | `server/app.py` | Websocket event-poll interval (seconds). | `1.0` |
| `HERMES_WEB_DIST` | `server/app.py` | SPA `dist/` directory to serve. | `web/dist` |
| `HERMES_LOG_LEVEL` | `engine/log.py` (**DELTA D1**) | Operational log level. | `INFO` |
| `HERMES_LOG_FORMAT` | `engine/log.py` (**DELTA D1**) | `text`/`json`. | `text` |
| `HERMES_LOG_FILE` | `engine/log.py` (**DELTA D1**) | Log file path (else stderr). | unset |
| `HERMES_REPO` | `sites/local/site.py` | Source repo the `local` site worktrees from. | cwd |
| `HERMES_SSH_HOSTS` | `sites/ssh/site.py` | Comma-separated host list for the `ssh` site. | `[]` |
| `HERMES_SSH_PORT_<host>` | `sites/ssh/site.py` | Per-host ssh port. | 22 |
| `HERMES_SSH_USER_<host>` | `sites/ssh/site.py` | Per-host login user. | current user |
| `HERMES_SSH_HOSTNAME_<host>` | `sites/ssh/site.py` | Per-host ssh address override (logical host ≠ address). | host id |
| `HERMES_SSH_IDENTITY_<host>` | `sites/ssh/site.py` | Per-host private-key path (**secret — never logged**). | none |
| `HERMES_SSH_RESOURCES_<host>` | `sites/ssh/site.py` | Per-host resources JSON, e.g. `{"cpu":4}`. | `{}` |
| `HERMES_SSH_RESOURCES` | `fleet/Dockerfile.worker`, `fleet/docker-compose.fleet.yml` | Worker-image resource label (informational). | `{"cpu":4}` |
| `HERMES_AUTHORIZED_KEY` | `fleet/entrypoint.sh`, `fleet/Dockerfile.worker`, `fleet/docker-compose.fleet.yml` | Throwaway pubkey injected into a worker's `authorized_keys` (**secret**). | unset |
| `HERMES_DEVSERVER_HOSTS` | `sites/devserver/site.py` | Devserver host list. | `[]` |
| `HERMES_REPO_URL` | `sites/devserver/site.py` | Repo URL the devserver site checks out. | `""` |
| `HERMES_DEVSERVER_INSTALL_CMD` | `sites/devserver/site.py` | Command to install `claude`/`dexter` on a devserver. | `""` |
| `HERMES_DEVSERVER_SUBMIT_CMD` | `sites/devserver/site.py` | Publish-only submit command (never lands). | `jf submit` |
| `HERMES_DEVSERVER_RECHECK_CMD` | `sites/devserver/site.py` | CI/repro re-check command for `verify` (delta D3 in dexter spec). | `""` |
| `DEXTER_KB_PY` | `playbooks/dexter/sink.py` | Path to dexter's `kb.py` for banking learnings (master-side). | `""` |
| `INVESTIGATIONS_DIR` | `playbooks/dexter/sink.py` | Dexter runtime-data dir for banked learnings. | `""` |

**Note on `<host>`-suffixed vars.** `HERMES_SSH_{PORT,USER,HOSTNAME,IDENTITY,RESOURCES}_<host>`
are dynamic (per-host suffix); `hermes doctor` (§3.3) enumerates them per
configured host rather than as fixed names.

### 3.2 Consolidation (DELTA D2)

Today env access is scattered: `engine/config.py` owns the core five
(`HERMES_HOME`, `HERMES_SITE`, `HERMES_AGENT`, `HERMES_HEARTBEAT_S`,
`HERMES_NETWORKED_PREFIXES`), while `HERMES_BIND`/`HERMES_WS_POLL_S`/
`HERMES_WEB_DIST`/`HERMES_DEBUG` are read inline in `cli.py`/`server/app.py`, and
each site reads its own. This spec:
- Adds typed accessors to `engine/config.py` for the **engine + server** knobs it
  does not yet expose (`bind()`, `ws_poll_s()`, `web_dist()`, `log_level()`,
  `log_format()`, `log_file()`, and `debug()`), so `cli.py`/`server/app.py` call
  `config.*` rather than `os.environ.get` inline. This is the single
  documentation-and-validation point for those knobs.
- **Site-owned vars stay in their site module** (they are deploy-time-pluggable per
  DESIGN goal #6). `config.py` gains a registry of *known* var names + one-line
  descriptions (used by `hermes doctor`) but does not read site vars itself.

### 3.3 `hermes doctor` / `hermes config check` (DELTA D3)

A new CLI subcommand (both spellings; `config check` is an alias) that **reports
resolved configuration + problems and exits non-zero on any hard problem** — the
operability analogue of `kb.py validate`. It does **not** mutate state.

Reports:
- Resolved `HERMES_HOME` (and whether it passed the networked-FS guard), the
  `queue.db` path + whether it exists + its file mode (expect 0600) + applied
  schema-migration version(s) (`schema_migrations`), the `api_token` path + mode
  (never the value).
- Resolved site/agent/heartbeat/bind/log settings, and every relevant
  `HERMES_*`/`DEXTER_*`/`INVESTIGATIONS_DIR` var with its effective value
  (**secrets shown as `set`/`unset`, never the value** — ties to §2.5).
- For the selected `--site`/`--agent`: whether the adapter registers/loads.
- Server extra: whether `fastapi`/`uvicorn` import (so an operator learns *before*
  `serve --api` that the extra is missing — today `cmd_serve_api` only discovers
  this at run time, `engine/cli.py:402`).

Exit codes: `0` all-clear, `1` at least one **hard problem** (e.g. `HERMES_HOME`
on a networked mount, `queue.db` unreadable, requested site/agent unresolvable),
with a per-problem line like `kb.py validate`.

### 3.4 Fail-fast startup validation (DELTA D4)

`engine/config.py` gains `validate_startup()` invoked once at process entry
(`main()` and `create_app()`), which runs the subset of `doctor`'s checks that are
**preconditions to running** and raises `ConfigError` (already defined in
`config.py`) with a clear message on failure:
- `HERMES_HOME` resolves and passes the networked-FS guard (already enforced lazily
  by `resolve_home()`; make it explicit at startup).
- `HERMES_LOG_LEVEL`/`HERMES_LOG_FORMAT` are valid enum values.
- `HERMES_HEARTBEAT_S` / `HERMES_WS_POLL_S` parse as positive numbers (today
  `int(os.environ[...])` would raise an opaque `ValueError` deep in a loop).
- For `serve --api`: the `server` extra imports; else a precise install hint
  (reuse the existing message in `cmd_serve_api`).

This turns today's late/opaque failures into one early, actionable error.

---

## 4. Process lifecycle & deploy

### 4.1 Graceful shutdown (SIGTERM) (DELTA D5)

**Current reality:** there is **no** signal handling anywhere
(`grep` finds no `signal`/`SIGTERM`/`KeyboardInterrupt` in `engine/` or
`server/`). `serve_loop`/`master_loop` (`engine/dispatch.py`) are bounded by
`max_cycles` and otherwise run to completion; `uvicorn.run(...)`
(`cmd_serve_api`) handles its own signals but the engine wraps nothing around it.

Requirements:
- **Master / serve loops.** Install a SIGTERM (and SIGINT) handler that sets a
  cooperative stop flag the loop checks **at cycle boundaries**
  (`dispatch.py:59`, `:174`). On signal: finish the in-flight cycle iteration
  (do not abandon a claim mid-`record_result`, which is transactional), stop
  claiming new tickets, run one final lease-renew/heartbeat housekeeping pass so
  no lease is left dangling, log a graceful-shutdown INFO line, close the DB
  connection, and exit `0`. A ticket already `dispatched`/`running` on a worker is
  left for the reclaim path (lease TTL / heartbeat down-requeue, engine-core §9) —
  **no ticket is lost or double-run**, because the state machine already treats a
  host lost mid-run as a no-penalty requeue.
- **API server.** `cmd_serve_api` lets uvicorn own SIGTERM (uvicorn drains
  in-flight requests and closes websockets). Hermes adds a startup/shutdown log
  line via FastAPI lifespan hooks; no engine loop runs inside the API process, so
  there is nothing else to drain. Websocket clients already tolerate disconnect
  (`server/app.py:1322`).
- **Idempotent restart.** Because all state is in `queue.db` and the loops are
  restartable, a killed-then-restarted `serve`/`master` process resumes correctly;
  the spec requires the shutdown path leave the DB in a consistent, restartable
  state (no half-written attempt row — guaranteed by the existing
  transaction-per-`record_result` discipline).

### 4.2 Control-plane container image + compose (DELTA D6)

**Current reality:** `fleet/` has only a **worker** image
(`Dockerfile.worker`, sshd + worker-runner + MockAgent + guard) and a worker-only
compose. There is **no** control-plane container and **no** service unit.

Add, alongside `fleet/`:
- **`fleet/Dockerfile.control-plane`** — an image that installs Hermes with the
  `server` extra (`pip install -e '.[server]'`, or a wheel from §6) and runs
  `hermes serve --api`. Unlike the worker image (which deliberately avoids
  `pip install` and uses `PYTHONPATH` + a thin wrapper to dodge flat-layout
  auto-discovery, `Dockerfile.worker:26-37`), the control plane installs the
  package properly so FastAPI/uvicorn resolve. It bind-mounts `HERMES_HOME` as a
  volume (queue.db + api_token must persist and stay on local, non-networked
  storage — §3.4 guard) and exposes the API port (default 8080). Applies migrations
  on start (§4.4).
- **`fleet/docker-compose.control-plane.yml`** (or a merge into the existing
  compose) — brings up the control plane bound to `127.0.0.1` by default
  (DESIGN §10), with `HERMES_BIND`, `HERMES_LOG_FORMAT=json`, and a persistent
  `HERMES_HOME` volume. Documents the non-loopback path (bind `0.0.0.0` only behind
  a trusted proxy that supplies auth) as commented config, matching the auth model
  in `server/app.py` (`is_loopback`, GET-gating, token bootstrap disabled on
  non-loopback).

### 4.3 Service-unit example (DELTA D7)

A documented **systemd** unit example (in the runbook, §6, and as a sample file
under `fleet/`) for running `hermes serve --api` and/or a per-host
`hermes serve --host` as a managed service: `Type=simple`,
`ExecStart=/usr/local/bin/hermes serve --api`, `Environment=HERMES_HOME=…
HERMES_LOG_FORMAT=json`, `Restart=on-failure`, `TimeoutStopSec` long enough for
the graceful-shutdown pass (§4.1), `KillSignal=SIGTERM`. Marked as an example, not
a Meta-specific deploy artifact.

### 4.4 Run topology & migrate-on-deploy

Documented in the runbook (§6):
- **Topology.** One **control-plane process** (`hermes serve --api`) + one
  **master loop** (`hermes run …` drives `master_loop`; on the `local` site it also
  runs in-process serve loops, `engine/cli.py:159`) + N **worker serve loops**
  (`hermes serve --host` on each remote box, or the in-process loops for `local`).
  All share **one `queue.db`** on the master host; workers are reached over the
  site transport (SSH), holding **no** shared DB (matches DESIGN §15 "no shared
  DB" and the fleet model).
- **Migrate-on-deploy.** `engine/db/migrate.py::apply_migrations` is idempotent and
  additive-only; every process entry already calls it via `cli._connect()`, and the
  control-plane image runs it on start. The runbook states: **deploy = pull new
  code, restart processes; migrations apply automatically and safely** (additive,
  WAL, tracked in `schema_migrations`). No manual migration step.

---

## 5. Data lifecycle

### 5.1 Unbounded-growth reality

Two tables grow without bound and are never trimmed today:
- **`events`** (`engine/events.py`, append-only by design; `emit()` only inserts).
- **`attempts`** (engine-core §4, append-only audit; one row per execution).

`findings`/`reductions` also only grow but are semantically load-bearing (a
reduction is never deleted, only `superseded` — DESIGN §5), so they are **retained
by default** and out of routine pruning.

### 5.2 Retention + `hermes db` subcommand (DELTA D8)

A new `hermes db {prune|backup|vacuum}` CLI command group:

- **`hermes db prune [--events-older-than DAYS] [--attempts-older-than DAYS]
  [--run R] [--dry-run]`** — delete `events` and/or `attempts` rows older than a
  cutoff. **HARD SAFETY RULE (§9): never delete live/in-flight state.** Concretely:
  - Only rows whose owning **run is terminal** (`done`/`failed`/`stopped`) are
    eligible; rows for a `running`/`paused` run are never pruned.
  - An `attempts` row is eligible only if its ticket is in a **terminal** state
    (`done`/`failed`); never for a ticket still `queued`/`dispatched`/`running`/
    `reducing`/`parked`/`needs_human`.
  - `events` with a null `run_id` (fleet-wide crew events) are pruned purely by age
    against the cutoff.
  - `--dry-run` reports counts without deleting. Default cutoffs are conservative
    (e.g. 90 days) and configurable per invocation; no automatic/background pruning
    (operator-invoked or cron'd via the runbook).
  - Emits nothing to `events` (pruning is maintenance, not a domain event) but logs
    an INFO summary (rows deleted per table).
- **`hermes db vacuum`** — run SQLite `VACUUM` to reclaim space after a prune
  (WAL-aware: checkpoint then vacuum). Documented as the follow-up to `prune`.
- **`hermes db backup --out PATH`** — WAL-aware backup (§5.3).

### 5.3 Backup / restore of `queue.db` (WAL-aware)

`queue.db` runs in **WAL mode** (`migrate.py::connect` sets
`journal_mode=WAL`), so a naive file copy can miss committed pages still in the
`-wal` file. Requirements:
- **`hermes db backup --out PATH`** uses SQLite's **online backup API**
  (`sqlite3.Connection.backup(...)`, stdlib) to produce a single consistent
  `PATH` file safe to take while a master/serve loop is running — no need to stop
  the fleet. The backup file is written with mode 0600 (matching the source).
- **Restore** is documented (runbook, §6): stop all Hermes processes, replace
  `$HERMES_HOME/queue.db` with the backup (and remove any stale `-wal`/`-shm`),
  restart. `apply_migrations` on restart is a no-op if the backup is current.
- The runbook also documents the alternative `VACUUM INTO` and the plain
  copy-with-checkpoint approaches, but the built command uses the backup API.

---

## 6. Packaging & release

### 6.1 Build/publish flow

Off the existing `pyproject.toml` (setuptools ≥61, `build-backend =
setuptools.build_backend`, console script `hermes=engine.cli:main`):
- **Build** with `python -m build` → sdist + wheel. Document that the repo is a
  **flat multi-package layout** (`engine/`, `server/`, `agents/`, `sites/`,
  `playbooks/`, `testkit/`), so `pyproject.toml` must declare explicit packages
  (setuptools `find` config) — the current `[project]` has no `[tool.setuptools]`
  package discovery block, which the worker image sidesteps with `PYTHONPATH`
  (`Dockerfile.worker:26`). **DELTA D9:** add an explicit
  `[tool.setuptools.packages.find]` (or `packages`) block so `pip install .`
  installs all runtime packages (`engine`, `server`, `agents`, `sites`,
  `playbooks`) — excluding `tests`/`testkit`/`web` from the wheel. Without this the
  `server` extra and the control-plane image cannot reliably `pip install`.
- **Versioning.** `version = "0.1.0"` in `pyproject.toml` is the single source;
  bump on release, tag `v<version>`.
- **Publish target.** The runbook documents building a wheel and installing it in
  the control-plane image / target host; no public PyPI publish is assumed (this
  is a personal/internal tool). `install.sh` remains the Claude-Code-plugin
  activation path (symlinks `integrations/claude-code`), unchanged.

### 6.2 Pinned constraints for the `server` extra (DELTA D10)

The `server` extra is currently floor-pinned only (`fastapi>=0.115.0`,
`uvicorn[standard]>=0.32.0`) and `dev` has `httpx>=0.27.0` — and there is already a
Starlette/httpx deprecation warning being suppressed in `pyproject.toml`
(`filterwarnings`), i.e. version drift is already biting. Add a
**`constraints.txt`** (or a `server` lock) capturing a known-good, tested set of
pinned versions for `fastapi`/`uvicorn`/`starlette`/`httpx`, referenced by the
control-plane image build (`pip install -e '.[server]' -c constraints.txt`) so
control-plane deploys are reproducible. The floor pins in `pyproject.toml` stay;
the constraints file is the reproducible-deploy overlay.

### 6.3 Refreshed README + quickstart + runbook (DELTA D11)

- **`README.md`** currently says **"Status: Design phase"** (`README.md:24-26`) —
  stale now that the engine core, dexter playbook, `local`/`ssh`/`devserver` sites,
  and the control-plane server are built. Rewrite Status to reflect what runs
  today, and add an **install/quickstart**: create a venv, `pip install -e
  '.[dev,server]'`, `hermes run example --site local` (engine-core AC2),
  `hermes serve --api`, then `hermes doctor`.
- **Operations runbook** (new `docs/RUNBOOK.md` — the one doc file this
  sub-project may create, since it is operator documentation, not a report):
  deploy/upgrade steps (migrate-on-deploy, §4.4), the run topology (§4.4), starting
  the control plane + workers, graceful shutdown/restart (§4.1), token
  rotation/loss recovery (`hermes serve --api --rotate-token`, and the
  non-loopback caveat), log configuration + rotation (`logrotate`), backup/restore
  (§5.3), pruning/vacuum cadence (§5.2), and `hermes doctor` as the first
  diagnostic step.

---

## 7. Explicit DELTAS

Each is new work this sub-project introduces, so the plan can slice them. None
changes the engine state machine, contracts, or the no-ship guard.

- **D1 — `engine/log.py` (new module).** Stdlib `logging` wrapper: `get_logger`,
  `configure`, `bind`, text+JSON formatters, `redact` helper; `configure()` called
  in `cli.main()` and `server.create_app()`; the 63 `print()`s in `engine/cli.py`
  and the 1 in `server/app.py:1327` routed through it (user-facing CLI *result*
  output — status tables, `show`, dry-run listing — may stay as `print` to stdout;
  *diagnostic/error* output moves to logging). New env vars `HERMES_LOG_LEVEL`,
  `HERMES_LOG_FORMAT`, `HERMES_LOG_FILE`; `HERMES_DEBUG` aliased to level DEBUG.
- **D2 — config consolidation (`engine/config.py`).** New typed accessors
  `bind()`, `ws_poll_s()`, `web_dist()`, `log_level()`, `log_format()`,
  `log_file()`, `debug()`, and a known-var registry; `cli.py`/`server/app.py`
  switch from inline `os.environ.get` to these.
- **D3 — `hermes doctor` / `hermes config check` (CLI).** New subcommand: reports
  resolved config + secrets-as-set/unset + adapter loadability + server-extra
  presence + db mode/migration version; exits non-zero on hard problems. New
  `cmd_doctor` + subparser in `engine/cli.py`.
- **D4 — `config.validate_startup()` (fail-fast).** Called at `main()` and
  `create_app()` entry; raises `ConfigError` on invalid `HERMES_HOME`/log/heartbeat
  settings or missing server extra.
- **D5 — SIGTERM/SIGINT graceful shutdown.** Cooperative stop flag checked at cycle
  boundaries in `dispatch.serve_loop`/`master_loop`; final housekeeping pass;
  FastAPI lifespan log lines. No new dependency.
- **D6 — `fleet/Dockerfile.control-plane` + `fleet/docker-compose.control-plane.yml`.**
  Control-plane image (installs `server` extra, runs `hermes serve --api`,
  persistent `HERMES_HOME` volume, migrate-on-start, loopback bind default).
- **D7 — service-unit example** (systemd) for `serve --api` / `serve --host`.
- **D8 — `hermes db {prune|backup|vacuum}` (CLI + `engine/` helper).**
  Retention-safe prune of terminal `events`/`attempts` (never live/in-flight),
  online-backup-API backup, WAL-aware vacuum. New `cmd_db` + subparser.
- **D9 — setuptools package discovery in `pyproject.toml`.** Explicit
  `[tool.setuptools.packages.find]` so `pip install .` installs all runtime
  packages and excludes tests/testkit/web — a precondition for D6/D10.
- **D10 — `constraints.txt` for the `server` extra.** Pinned known-good
  fastapi/uvicorn/starlette/httpx for reproducible control-plane builds.
- **D11 — refreshed `README.md` + new `docs/RUNBOOK.md`.** De-stale the status,
  add install/quickstart, write the operations runbook.

---

## 8. Testing strategy (no real infra)

Everything is testable on one box with the existing `pytest` dev dep and
`scripts/run_tests.sh`; no metrics backend, no real SSH, no Docker required.

- **Logging (D1).** Use `pytest`'s `caplog` / a `logging` capture handler:
  assert levels/records per layer (§2.3), that `configure()` is idempotent (no
  duplicate handlers), that text and JSON formatters produce the documented shape,
  and that `bind()` context fields (`run_id`/`ticket_id`/`host`) attach to records.
  **Secret-redaction test (§2.5, §9):** drive a full `LocalSite` + `MockAgent`
  integration run *and* server startup + a websocket connect with `?token=`, and
  assert the captured log output contains **neither** the `api_token` value nor any
  `?token=`/identity/`HERMES_AUTHORIZED_KEY` value (grep the captured records).
- **Config validation (D2/D3/D4).** Unit-test `validate_startup()` accept/reject
  (bad log level, non-numeric heartbeat, networked-mount `HERMES_HOME` via the
  injectable `is_networked` hook already in `config.resolve_home`), and
  `hermes doctor` exit codes + that it never prints a secret value (asserts
  `set`/`unset`). Reuse `testkit/fixtures.py`'s temp `HERMES_HOME`.
- **SIGTERM handling (D5).** Unit-test the cooperative stop flag: inject a stop
  signal after N cycles and assert the loop exits at a cycle boundary with the DB
  consistent (no half-written attempt, no dangling lease past the final
  housekeeping pass, no ticket lost — a dispatched ticket remains reclaimable).
  Send an actual `SIGTERM` to a subprocess-launched `serve` loop in one integration
  test and assert exit 0 + a graceful-shutdown log line.
- **Data lifecycle (D8).** Against a temp `queue.db` seeded with terminal and
  live runs/tickets: assert `db prune` deletes only terminal-run/terminal-ticket
  `events`/`attempts` and **never** rows tied to a `running`/`paused` run or a
  non-terminal ticket (the §9 invariant); `--dry-run` deletes nothing; `db backup`
  produces a file that opens, passes `apply_migrations` as a no-op, and contains
  the same row counts (online-backup-API correctness under WAL); `db vacuum` runs
  clean.
- **Packaging (D9/D10).** A test that builds the wheel (or introspects
  `setuptools` discovery) and asserts `engine`, `server`, `agents`, `sites`,
  `playbooks` are included and `tests`/`testkit`/`web` excluded; assert the
  engine-core import-purity test (engine-core AC5) still passes — `engine/log.py`
  imports only stdlib.
- Wire all of the above into `scripts/run_tests.sh` (unit + integration), keeping
  the suite green and infra-free.

---

## 9. Safety / invariants

- **No secrets in logs (HARD, §2.5).** The API bearer token, `?token=` query
  values, SSH identities, and `HERMES_AUTHORIZED_KEY` never appear in any log line
  at any level; only *locations* / `set`/`unset` are logged. Enforced by the
  `redact` helper, query-string stripping in request logging, and a dedicated
  test (§8). This preserves the `server/auth.py` posture (token is a 0600 file, no
  value ever emitted).
- **No-ship unaffected.** Nothing in this sub-project touches the PATH guard shims
  (`sites/*`, `fleet/Dockerfile.worker:39-54`, `engine/guard`), the
  `guarantees_no_ship`/`guard_installed` gates, or `Playbook.verify`. Operability
  is observation + lifecycle only; the no-land-by-construction invariant (DESIGN
  §11) holds untouched.
- **Stdlib-only engine.** `engine/log.py` uses only stdlib `logging`/`json`/
  `contextvars`; `hermes db`/`doctor`/config helpers use only stdlib
  (`sqlite3`, `os`, `argparse`). The engine-core runtime-third-party-free invariant
  (engine-core AC5) survives. FastAPI/uvicorn stay confined to the `server` extra
  and the control-plane image (D6/D10).
- **Retention never deletes live/in-flight state (HARD, §5.2).** `hermes db prune`
  only touches `events`/`attempts` for **terminal** runs and **terminal** tickets;
  `findings`/`reductions` are retained; `runs`/`tickets`/`crew`/`leases` current
  state is never pruned. `queue.db` stays local, non-networked (§3.4 guard) and
  0600 (`migrate.connect`), including backup outputs.
- **Additive, restartable, idempotent.** Migrations stay additive-only
  (`migrate.py`); graceful shutdown leaves a consistent, restartable DB; all
  operability commands are safe to re-run.

---

## 10. Open items (non-blocking)

- **In-process serve loops on `local`.** `hermes run --site local` runs master +
  serve loops in one process (`cli.py:159`); SIGTERM (D5) must stop them together —
  a single stop flag shared by both loops in that process. Spec'd; implementation
  detail deferred.
- **The `logs/` dir.** engine-core §3 reserves `$HERMES_HOME/logs/` but nothing
  writes it today. `HERMES_LOG_FILE` (D1) makes it the natural default location if
  an operator opts into file logging; whether `configure()` should default the file
  there vs. stderr is left to implementation (spec default is stderr).
- **Automatic/background pruning.** This build keeps `db prune` operator-invoked
  (or cron'd via the runbook). A future in-master periodic prune could hang off the
  heartbeat sweep, but is deferred (no background mutation of the audit trail
  without an explicit operator cadence).
- **Metrics export.** If a real metrics backend ever exists, the JSON log
  formatter (D1) and the existing `/api/runs/{id}/metrics` + `events` feed are the
  seams to export from; not built here (§1 out-of-scope).
