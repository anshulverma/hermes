# Hermes operability — implementation plan (sub-project 3)

Status: **draft**. Date: 2026-07-29. Spec: `docs/specs/operability.md` (hardened to
convergence, 7 passes, commit `514c2be`). Depends on: engine-core
(`docs/specs/engine-core.md`, `engine-core-plan.md`) and the `dexter` playbook +
`devserver` site (`docs/specs/dexter-playbook.md`, `dexter-playbook-plan.md`) —
**both already built** (`engine/`, `server/`, `sites/`, `agents/`, `playbooks/`,
`fleet/`, `testkit/`, `tests/` all present).

Vertical slices in dependency order. Each slice is independently testable, follows
**TDD** (write the failing test first, then the code), and ends GREEN before the
next begins. Every slice lists its **scope**, **files**, the **failing tests to
write first**, and its **DoD**. Operability is observation + lifecycle only: it
changes **no** engine methodology invariant (state machine, contracts, no-ship
guard, additive migrations).

Conventions: paths are under `hermes/`. "GREEN" = `scripts/run_tests.sh` passes
(pytest via `.venv`; `-m "not docker"` where Docker is absent). Commit after each
slice. Section references point at the operability spec and live
**only in this doc**, never in code (see Global constraints).

---

## Global constraints (apply to every slice)

- **(a) HARD — never log a secret.** The engine already keeps the bearer token in a
  0600 file (`server/auth.py`) and never emits its value; every slice preserves
  that posture. The enumerated leak surfaces, each of which a test must prove is
  never logged at any level:
  1. **WS `?token=`** — `websocket_endpoint` (`server/app.py:1247`) reads
     `token: str = Query(None)` **and** an `Authorization: Bearer` header
     (`server/app.py:1272`). Neither the query value nor the header may reach a log;
     request/WS logging strips/redacts the query string so `?token=…` never lands.
  2. **`index.html` token bootstrap** — `serve_spa` injects
     `<script>window.__HERMES_TOKEN__="…"` on loopback (`server/app.py:1366`). It is
     response HTML, never echoed to a log.
  3. **SSH identities** — `HERMES_SSH_IDENTITY_<host>` (`sites/ssh/site.py`) file
     paths/contents; sites log config **keys**, never identity contents.
  4. **Authorized-key env** — `HERMES_AUTHORIZED_KEY` (`fleet/*`) pubkey material.
  Enforcement: a single `engine/log.py::redact(mapping)` helper drops known secret
  keys (`token`, `api_token`, `authorized_key`, `identity`) before any structured
  `extra` is logged; request logging strips the query string; `hermes doctor` prints
  secrets only as `set`/`unset`. A dedicated test (Slice 1) greps captured records.
- **(b) `events` stays the domain/audit feed; logging is operational diagnostics.**
  `engine/events.py` (the append-only `EVENT_KINDS` frozenset of **24** kinds,
  emitted inside the caller's transaction) is the source of truth for *state
  history* and drives `hermes status`, `GET /api/events`, and the WS feed. Logging
  (`engine/log.py`) is line-oriented process diagnostics, never read back, no schema,
  no transaction. **No duplication**: an operability slice must not move any queryable
  state into logs, and must not stop emitting any existing event. Pruning (see the "Data lifecycle" section) emits
  **no** event (maintenance is not a domain event) but logs an INFO summary.
- **(c) Stdlib-only engine.** `engine/log.py`, the `db`/`doctor`/config helpers, and
  `engine/shutdown.py` import only stdlib (`logging`, `json`, `contextvars`,
  `sqlite3`, `os`, `signal`, `threading`, `argparse`). The existing
  `tests/unit/test_invariants.py::test_engine_core_imports_only_stdlib` (AST-scans
  `engine/`) keeps passing unchanged. FastAPI/uvicorn stay confined to the `server`
  extra and the control-plane image.
- **(d) Retention never deletes live/in-flight state (HARD, see the "Retention + hermes db subcommand" section).** `hermes db
  prune` deletes an `attempts` row or a ticket-scoped `events` row only when its run
  AND its ticket are both terminal and the row is past the age cutoff; `attempts`
  with a null `ended_at` are never pruned; `findings`/`reductions` and all current
  `runs`/`tickets`/`crew`/`leases` state are never pruned. Exact predicate in Slice 6.
- **(e) No-ship invariant unaffected.** Nothing here touches the guard shims
  (`sites/*`, `fleet/Dockerfile.worker:39-54`), `guarantees_no_ship`/
  `guard_installed`, or `Playbook.verify`. Slices that add a container/compose must
  keep the worker image's guard exactly as is.
- **(f) Code stays self-contained — NO doc references in code.** No section references,
  delta labels, slice numbers, `docs/*` path, or "per the spec/plan" text in any comment, docstring,
  string literal, log message, or identifier. Citations live only in this plan and
  the spec. (Log messages describe the process, e.g. `"graceful shutdown: stop
  requested"` — not referencing spec sections.)
- **No faked test data.** Tests drive the real engine writers (`queue.*`,
  `dispatch.*`, `events.emit`, `migrate.*`) against a temp `HERMES_HOME` via
  `testkit/fixtures.py`, and reuse the real one-commit-repo fixture pattern from
  `tests/unit/test_fleet_scenario.py` / `tests/integration/test_local_run.py` where a
  run must actually provision. The only doubles are the existing `MockAgent` /
  `LocalSite` / `DexterMockAgent` / `DexterLocalSite`. No monkey-patching of engine
  state.

### Top-risk designs (baked into the slices, from the hardening report)

- **D9 setuptools discovery + testkit decoupling + build-backend fix (Slice 0).**
  Three verified facts: (1) `sites/` has **no** `__init__.py` (PEP-420 namespace
  package) while `sites/local`, `sites/ssh`, `sites/devserver` each have one — plain
  `find_packages` silently drops all three site subpackages **and** `sites` itself
  (verified: with the exact globs below, discovery returns only
  `engine, engine.db, server, agents, agents.claude, playbooks, playbooks.dexter`
  until `sites/__init__.py` is added, after which all 11 production packages
  resolve and no test/web/infra dir leaks); (2) `_load_playbook_site_agent`
  (`engine/cli.py:31-32`) **unconditionally** imports `testkit.example_playbook` +
  `testkit.mock_agent`, so a testkit-excluded wheel breaks **every** `hermes run`
  (incl. `dexter`); (3) `pyproject.toml` declares `build-backend =
  "setuptools.build_backend"`, which **does not exist** (verified: `import
  setuptools.build_backend` → `ModuleNotFoundError`; the real backend is
  `setuptools.build_meta`) — so `python -m build` / `pip install .` fail on the
  backend *before* discovery even runs. Fix (recommended A): correct the
  build-backend, add empty `sites/__init__.py`, then the exact
  `[tool.setuptools.packages.find]` block below; **plus** make those two `testkit`
  imports conditional.
- **D5 SIGTERM single shared stop flag (Slice 5).** One process-global
  `threading.Event` in `engine/shutdown.py`, set by a SIGTERM+SIGINT handler
  installed **only** on the loop-driving entry paths (`cmd_run`, worker `cmd_serve
  --host`); `serve --api` installs none and defers to uvicorn (no handler conflict).
  The **same** object is checked at the top of `serve_loop`'s `while True:`
  (`dispatch.py:81`) and — critically — in `master_loop` **immediately after**
  `crew.heartbeat_sweep` (`dispatch.py:202`) and again after the per-host
  `serve_loop` fan-out (`dispatch.py:218`), so the sweep is always the *last* action
  before the master returns and the in-process co-loops on `local` stop together.
- **Prune-safety predicate (Slice 6).** Deletable iff every clause holds — terminal
  run ∈ {`done`,`failed`,`stopped`}, terminal ticket ∈ {`done`,`failed`},
  `ended_at`/`ts < cutoff`, null `ended_at` never pruned. WAL-aware: one committed
  transaction (durability automatic), space reclaimed by `db vacuum`.

---

## Slice 0 — D9: setuptools package discovery + testkit run-path decoupling

**Scope.** Make the flat multi-package layout `pip install`-able so a wheel carries
every production package (incl. the three `sites.*` subpackages) and excludes
test/web/infra dirs, and so a testkit-free wheel still runs `hermes run dexter`.
This is the **installability precondition** for D6/D10 (the control-plane image and
its pinned constraints). No behavior change to the running engine.

**Files.**
- `sites/__init__.py` (new, empty — the single missing `__init__.py`, turning the
  whole tree into regular packages).
- `pyproject.toml` (fix the invalid `build-backend`; add
  `[tool.setuptools.packages.find]`).
- `engine/cli.py::_load_playbook_site_agent` (make the two `testkit` imports
  conditional).

**Behavior to pin (see the "Build/publish flow" section of the spec, D9 exact).**
- **Fix the build backend (blocker, precedes discovery).** `pyproject.toml`
  currently has `build-backend = "setuptools.build_backend"` (line 24), a module
  that does not exist; change it to the canonical `build-backend =
  "setuptools.build_meta"`. Without this, no build/install succeeds regardless of
  discovery, so this is the true first fix in the slice. `requires =
  ["setuptools>=61.0"]` stays.
- Add the discovery block (recommended fix A — deterministic, one code line):
  ```toml
  [tool.setuptools.packages.find]
  where   = ["."]
  include = ["engine*", "server*", "agents*", "sites*", "playbooks*"]
  exclude = ["tests*", "testkit*", "web*", "fleet*", "scripts*",
             "integrations*", "docs*"]
  ```
  With every dir a regular package, `find_packages` deterministically discovers
  `engine`, `engine.db`, `server`, `agents`, `agents.claude`, `sites`,
  `sites.local`, `sites.ssh`, `sites.devserver`, `playbooks`, `playbooks.dexter`.
  (Alternative B, no code change: keep `sites/` a namespace package and set
  `namespaces = true` explicitly in the same block. The plan chooses A.)
- **Decouple `testkit` from the run path.** In `_load_playbook_site_agent`, import
  `testkit.example_playbook` **only** when `args.playbook == "example"` and
  `testkit.mock_agent` **only** when the resolved agent name is `"mock"`; the
  production `playbooks.dexter`, `sites.local.site`, `sites.devserver.site`,
  `agents.claude` imports stay unconditional. (The `serve-once` path is already
  conditional, `cli.py:522-526`; this brings the run path in line.) A testkit-free
  wheel then runs `hermes run dexter`; `hermes run example` remains a
  dev/editable-install path (README quickstart uses `pip install -e '.[dev,server]'`).

**Tests first (RED)** — `tests/unit/test_packaging.py` (new):
- **Build-backend valid** (fast, no build): parse `pyproject.toml`, assert
  `build-system.build-backend == "setuptools.build_meta"`, and assert the module
  imports (`importlib.import_module("setuptools.build_meta")`) — this catches the
  `setuptools.build_backend` typo without a full build.
- **Discovery** (fast, no build): call
  `setuptools.find_packages(where=".", include=[...], exclude=[...])` (or
  `find_namespace_packages` for B) with the exact globs and assert the returned set
  **contains** `sites.local`, `sites.ssh`, `sites.devserver` (the namespace trap),
  plus `engine.db`, `agents.claude`, `playbooks.dexter`, and **excludes** `tests`,
  `testkit`, `web`, `fleet`, `scripts`, `integrations`, `docs`.
- **Wheel build** (guarded `@pytest.mark.skipif` when `build`/network absent): run
  `python -m build --wheel` into a temp dir, unzip, and assert the `RECORD`/name
  list carries the same subpackages and omits `testkit`/`tests`/`web`.
- **testkit decoupling** — `_load_playbook_site_agent` with `playbook="dexter",
  site="local", agent="claude"` succeeds **without** `testkit` importable
  (simulate by asserting no `testkit.*` module entered `sys.modules` for that call,
  mirroring the invariants-test subprocess-import technique); `playbook="example"`
  still imports `testkit.example_playbook`; regression: `example`/`local`/`mock`
  still resolve.
- **Invariant regression** — `test_invariants.py::test_engine_core_imports_only_stdlib`
  still passes (no `engine/` third-party import added).

**DoD.** The build-backend is the valid `setuptools.build_meta`; `find_packages`
yields the full production set with the three `sites.*` subpackages and no
test/web/infra dirs; a wheel builds and installs; `hermes run dexter` no longer needs
`testkit`; `run_tests.sh` GREEN.

---

## Slice 1 — D1: `engine/log.py` + route diagnostics + no-secrets redaction

**Scope.** The second, orthogonal feed: stdlib-`logging` operational diagnostics,
layered beside (never duplicating) the `events` domain feed. Add `engine/log.py`;
call `configure()` once at each process entry; route the diagnostic/error `print()`s
in `engine/cli.py` and the raw `print(f"WebSocket error: {e}")` in `server/app.py`
through the logger; subsume `HERMES_DEBUG`; and prove no secret is ever logged.

**Files.**
- `engine/log.py` (new — stdlib only).
- `engine/cli.py` (call `log.configure()` at top of `main()`; route diagnostic/error
  prints; top-level `except` uses `logger.exception`; `HERMES_DEBUG` alias).
- `server/app.py` (call `log.configure()` in `create_app()`; replace the WS-error
  `print`; add a request-logging path that redacts the query string).

**Behavior to pin (see sections "The two feeds" through "HARD INVARIANT — never log the API token or secrets", D1).**
- `get_logger(name) -> logging.Logger` — namespaced child of the root `hermes`
  logger (`hermes.dispatch`, `hermes.transport`, `hermes.server`, …); never
  configures handlers.
- `configure(*, level=None, fmt=None, file=None, context=None) -> None` —
  **idempotent** one-time root config (guarded so repeated CLI/serve entry does not
  stack handlers); reads env defaults when args omitted (`HERMES_LOG_LEVEL=INFO`,
  `HERMES_LOG_FORMAT=text`, `HERMES_LOG_FILE` unset⇒stderr); installs exactly one
  handler (stderr, or `FileHandler(file)`), sets level, selects formatter.
- `bind(**fields)` — contextmanager pushing `run_id`/`ticket_id`/`host` onto a
  `contextvars` store; a `logging.Filter` injects the bound fields into every record.
- Two formatters: **text** (default) `"<ts> <level> <name> [run_id=… ticket_id=…
  host=…] message"` (bound fields omitted when unset); **json**
  (`HERMES_LOG_FORMAT=json`) one object per line with keys `ts,level,logger,msg,
  run_id,ticket_id,host` + any `extra`. Stdlib `json` only.
- `redact(mapping)` — returns a copy with known secret keys (`token`, `api_token`,
  `authorized_key`, `identity`) replaced by `"***"`; applied before any structured
  `extra` is logged.
- **`HERMES_DEBUG` subsumed** — truthy ⇒ level `DEBUG`, but **loses** to an explicit
  `HERMES_LOG_LEVEL`. The `main()` top-level handler (`cli.py:702-707`) logs via
  `logger.exception(...)` instead of `traceback.print_exc()`.
- **Routing rule.** User-facing CLI **result** output (status tables, `show`,
  dry-run listing) stays `print()` to stdout; **diagnostic/error** output
  (`Error: …` to stderr, the WS-error print, server start banner) moves to logging.
  Server startup logs bind+port+home and the token **location** — never the value.
- **Request/WS logging redaction.** The per-request/WS DEBUG line logs method + path
  with the **query string stripped**, so `?token=…` never appears.

**Tests first (RED)** — `tests/unit/test_log.py` (new) + extend `test_server.py`:
- `configure()` idempotent — call twice, assert the root `hermes` logger has exactly
  one handler.
- text and json formatters produce the documented shapes (parse the json line;
  assert keys); `bind(run_id=…, ticket_id=…, host=…)` attaches those fields to a
  captured record (`caplog` or an attached capture handler).
- `HERMES_DEBUG=1` ⇒ effective level `DEBUG`; with `HERMES_LOG_LEVEL=WARNING` set,
  level is `WARNING` (explicit wins).
- `redact({"api_token": "s3cr", "host": "h"})` ⇒ `api_token` masked, `host` intact.
- **HARD no-secrets test** (`test_log.py::test_no_secrets_in_logs`): with a capture
  handler on `hermes`, drive (i) a full `LocalSite`+`MockAgent` run via
  `master_loop` (real temp repo + `HERMES_HOME`, reusing the fleet-scenario
  fixtures), (ii) `create_app()` startup + a TestClient WS connect to
  `/api/ws?token=<real token>`, and assert the captured output contains **none** of:
  the `api_token` value (read from the 0600 file), the `?token=` value, an
  `HERMES_SSH_IDENTITY_*` path/contents, or `HERMES_AUTHORIZED_KEY`. Grep every
  record's `getMessage()` **and** rendered formatter output.

**DoD.** Both entry points configure logging once; diagnostics/errors flow through
`hermes.*` loggers; the no-secrets test passes; `events` emission is untouched;
`run_tests.sh` GREEN.

---

## Slice 2 — D2: config consolidation (typed accessors + known-var registry)

**Scope.** Make `engine/config.py` the single documentation-and-validation point for
the engine + server knobs currently read inline in `cli.py`/`server/app.py`, and add
a registry of known var names for `doctor`. Site-owned vars stay in their site
module (deploy-time-pluggable). Pure refactor — no behavior change.

**Files.** `engine/config.py` (new accessors + registry); `engine/cli.py` +
`server/app.py` (switch inline `os.environ.get` to `config.*`);
`engine/log.py::configure()` (read defaults via the new `config.log_*()` accessors).

**Behavior to pin (see the "Consolidation" section, D2).**
- Add typed accessors mirroring the existing `heartbeat_s()`/`site()`/`agent()`
  style: `bind() -> str` (default `127.0.0.1`), `ws_poll_s() -> float` (default
  `1.0`), `web_dist() -> str` (default `web/dist`), `log_level() -> str`,
  `log_format() -> str`, `log_file() -> str | None`, `debug() -> bool`.
- `cmd_serve_api` (`cli.py:415`) and `server/app.py` (`HERMES_WS_POLL_S`,
  `HERMES_WEB_DIST`) call `config.*` instead of `os.environ.get`. `HERMES_BIND`
  default resolution stays behaviorally identical.
- `engine/log.py::configure()` reads its three defaults from `config.log_level()/
  log_format()/log_file()` (folds the env reads into config; log.py still stdlib).
- Add `KNOWN_VARS: dict[str, str]` (var name → one-line description) covering the
  full env-var surface from the "Full env-var surface" section, incl. a note that `HERMES_SSH_{PORT,USER,HOSTNAME,IDENTITY,
  RESOURCES}_<host>` are dynamic per-host suffixes. `config.py` does **not** read
  site vars — the registry is descriptive metadata for `doctor` only.

**Tests first (RED)** — `tests/unit/test_config.py` (extend):
- Each accessor returns its documented default when the env var is unset, and the
  env value when set (`monkeypatch.setenv`), with correct type coercion
  (`ws_poll_s` float, `debug` bool truthiness).
- `KNOWN_VARS` contains every non-dynamic `HERMES_*`/`DEXTER_*`/`INVESTIGATIONS_DIR`
  name from the "Full env-var surface" section (assert the set membership) and each has a non-empty description.
- Regression: `resolve_home`, `heartbeat_s`, `site`, `agent` unchanged;
  `test_server.py` and `test_cli.py` still green after the inline→`config` switch.

**DoD.** `cli.py`/`server/app.py` no longer read those knobs inline; `configure()`
defaults come from `config`; `KNOWN_VARS` enumerates the surface; `run_tests.sh`
GREEN.

---

## Slice 3 — D4: `config.validate_startup()` fail-fast

**Scope.** Turn today's late/opaque failures (a bad heartbeat int raising deep in a
loop; a missing server extra discovered only at `serve --api` runtime) into one
early, actionable `ConfigError` at process entry.

**Files.** `engine/config.py` (add `validate_startup()`); `engine/cli.py::main()` and
`server/app.py::create_app()` (call it at entry).

**Behavior to pin (see the "Fail-fast startup validation" section, D4).** `validate_startup(*, is_networked=None,
require_server=False)` runs the preconditions-to-running subset of `doctor`'s checks
and raises `ConfigError` (already defined in `config.py`) on the first failure:
- `resolve_home()` succeeds and passes the networked-FS guard (make the existing lazy
  guard explicit at startup; reuse the injectable `is_networked` hook).
- `log_level()` ∈ {DEBUG,INFO,WARNING,ERROR}; `log_format()` ∈ {text,json}.
- `heartbeat_s()` and `ws_poll_s()` parse as **positive** numbers (today
  `int(os.environ[...])` would raise an opaque `ValueError`).
- When `require_server=True` (the `serve --api` path): `fastapi`/`uvicorn` import,
  else a precise install hint (reuse the message already in `cmd_serve_api`).

**Tests first (RED)** — `tests/unit/test_config.py` (extend):
- Accepts a clean env (no raise). Rejects: `HERMES_LOG_LEVEL=loud`,
  `HERMES_LOG_FORMAT=xml`, `HERMES_HEARTBEAT_S=0`/`-1`/`abc`, `HERMES_WS_POLL_S=0`,
  and a networked-mount `HERMES_HOME` (via the injectable `is_networked` hook) —
  each raising `ConfigError` with a message naming the offending var.
- `require_server=True` with `fastapi` importable ⇒ no raise; simulate absence and
  assert the install-hint `ConfigError`.
- Wiring: `main()` calling `validate_startup()` returns a clean nonzero + logged
  error on a bad env rather than a traceback.

**DoD.** Invalid config fails fast at entry with a named `ConfigError`;
`serve --api` reports a missing extra before binding; `run_tests.sh` GREEN.

---

## Slice 4 — D3: `hermes doctor` / `hermes config check`

**Scope.** The operability analogue of `kb.py validate`: a read-only subcommand
(both spellings) that reports resolved configuration + problems and exits non-zero on
any hard problem. Mutates no state; prints no secret value.

**Files.** `engine/cli.py` (`cmd_doctor` + `doctor` subparser and a `config check`
alias). No engine-state writes.

**Behavior to pin (see the "hermes doctor / hermes config check" section, D3).** Reports:
- Resolved `HERMES_HOME` + whether it passed the networked-FS guard; the `queue.db`
  path + existence + file mode (expect 0600) + applied `schema_migrations`
  version(s); the `api_token` path + mode (**never** the value).
- Resolved site/agent/heartbeat/bind/log settings; every relevant
  `HERMES_*`/`DEXTER_*`/`INVESTIGATIONS_DIR` var (from `config.KNOWN_VARS`) with its
  effective value — **secrets shown as `set`/`unset`** (`HERMES_SSH_IDENTITY_*`,
  `HERMES_AUTHORIZED_KEY`, `api_token`), never the value.
- For the selected `--site`/`--agent`: whether the adapter registers/loads.
- Server extra: whether `fastapi`/`uvicorn` import.
- Exit `0` all-clear; `1` on ≥1 hard problem (networked-mount `HERMES_HOME`,
  unreadable `queue.db`, unresolvable requested site/agent, missing server extra when
  asked), one problem-line each like `kb.py validate`.

**Tests first (RED)** — `tests/unit/test_cli.py` (extend) or `test_doctor.py`:
- On a clean temp `HERMES_HOME` (via `testkit/fixtures.py`): `cmd_doctor` exits `0`
  and its stdout reports the resolved home, `queue.db` mode `0600`, migration
  version(s), and each site adapter loads.
- Hard-problem exits `1`: networked-mount `HERMES_HOME` (injected `is_networked`);
  an unresolvable `--site nope`.
- **Secret redaction**: with `HERMES_SSH_IDENTITY_h1=/k`, `HERMES_AUTHORIZED_KEY=ssh-…`,
  and a created `api_token`, assert the output contains `set`/`unset` markers and
  **not** any of those values (grep).
- `config check` is accepted as an alias and behaves identically.

**DoD.** `hermes doctor` reports resolved config + problems, exits non-zero on hard
problems, prints secrets only as `set`/`unset`; `run_tests.sh` GREEN.

---

## Slice 5 — D5: SIGTERM/SIGINT graceful shutdown (single shared stop flag)

**Scope.** Add cooperative shutdown to the long-running loops so a SIGTERM finishes
the in-flight cycle, runs one final housekeeping pass, and exits `0` with a
consistent, restartable DB — with the in-process master+serve co-loops on `local`
stopping **together** via one shared flag. The API path defers to uvicorn.

**Files.**
- `engine/shutdown.py` (new — the process-global `threading.Event` + install helper).
- `engine/dispatch.py` (`serve_loop`, `master_loop` consult the flag).
- `engine/cli.py` (`cmd_run` and worker `cmd_serve --host` install the handler;
  `cmd_serve_api` does **not**).
- `server/app.py` (FastAPI lifespan start/stop log lines only).

**Behavior to pin (see the "Graceful shutdown (SIGTERM)" section, D5 exact).**
- `engine/shutdown.py` exposes a module-global `stop_event = threading.Event()`
  (created once at import, **never reassigned**) plus `install_handlers()` that
  registers a SIGTERM **and** SIGINT handler which does nothing but
  `stop_event.set()` (no I/O in a signal handler). The loops take an optional
  `stop_event=None` param and resolve it **at call time** (`ev = stop_event or
  shutdown.stop_event`) — never capturing the global as a def-time default (which
  would freeze a stale object) — so a test-injected `Event` and the process-global
  are one shared object.
- `serve_loop` checks `ev.is_set()` at the **top** of its `while True:`
  (`dispatch.py:81`) and returns the count processed so far.
- `master_loop` places its checks so `crew.heartbeat_sweep` is always the final
  housekeeping pass before return:
  - **after `crew.heartbeat_sweep` (`dispatch.py:202`)** (between `heartbeat_sweep`
    and the progression block, ~`:205`): if set, `return` the run state — the sweep
    just ran, so this is the clean between-cycles exit and the final pass.
  - **after the per-host `serve_loop` fan-out (`dispatch.py:218`), before
    `_reduce_and_advance` (`:221`)**: if set, `continue` (skip reduce/advance so
    shutdown seeds no new work); the next iteration re-runs `heartbeat_sweep`
    (`:202`, now reflecting the just-stopped fan-out) and exits via the first check.
  This guarantees exactly one final sweep *after* the last fan-out with no
  mid-transaction abort. `master_loop` **forwards its resolved `ev`** to each
  `serve_loop(...)` call (`dispatch.py:218`, add `stop_event=ev`) so a test-injected
  flag is genuinely shared by the co-loops (otherwise the inner `serve_loop` would
  re-resolve to the module global and miss the injected object).
- **On signal:** finish the in-flight cycle (checks are only at loop tops/boundaries,
  never mid-`record_result`), stop claiming new tickets (the `serve_loop` top check),
  run **one** final `crew.heartbeat_sweep` (`dispatch.py:202`, guaranteed last per
  the placement above) so leases are renewed/reclaimed and none dangles, log a
  graceful-shutdown INFO line, close the DB, exit `0`. A ticket already
  `dispatched`/`running` on a worker is left for the reclaim path (lease TTL /
  heartbeat down-requeue) — no loss, no double-run.
- Handler installed **only** on `cmd_run` and worker `cmd_serve --host`;
  `cmd_serve_api` installs none (uvicorn owns SIGTERM and drains requests/WS).
  `create_app()` adds a FastAPI lifespan start/stop log line; WS clients already
  tolerate disconnect (`server/app.py:1322`, `except WebSocketDisconnect`).

**Tests first (RED)** — `tests/unit/test_shutdown.py` (new) + one integration test:
- **Unit (injected flag).** Seed a run with several tickets on `LocalSite`+`MockAgent`;
  inject a `threading.Event` subclass whose `is_set()` returns `True` only after its
  Nth call (a deterministic "stop after N boundary checks" double, no real signals),
  and assert: `master_loop`/`serve_loop` exit at a **cycle boundary**; no `attempts`
  row has a null-then-abandoned `ended_at` mid-transaction; a `heartbeat_sweep` ran
  as the last housekeeping action so no lease dangles; a still-`dispatched` ticket
  remains reclaimable (not lost, not double-run). Also test the pre-set-flag path
  (immediate clean exit at the first boundary).
- **Same-flag co-stop.** Assert the master and its in-process serve loops read the
  identical `Event` object (set it once ⇒ both stop).
- **Integration** (`tests/integration/`): launch `hermes serve --host` (or `run`) in
  a subprocess against a seeded temp `HERMES_HOME` **with enough in-flight work for
  the signal to land mid-loop** (many seeded tickets and/or a `MockAgent` with a
  small per-invocation sleep, so the loop is demonstrably still cycling), send a real
  `SIGTERM`, assert exit `0` and a graceful-shutdown log line in captured stderr, and
  that the DB re-opens cleanly (`apply_migrations` no-op).

**DoD.** SIGTERM/SIGINT stop the loops cleanly at a boundary; the shared flag stops
`local` co-loops together; the API path is unchanged (uvicorn-owned); DB stays
restartable; `run_tests.sh` GREEN.

---

## Slice 6 — D8: `hermes db {prune|backup|vacuum}`

**Scope.** Bound the unbounded-growth tables (`events`, `attempts`) with a
retention-**safe** prune that never deletes live/in-flight state, a WAL-aware online
backup, and a vacuum to reclaim space. Operator-invoked (no background pruning).

**Files.** `engine/db/maintenance.py` (new — `prune`, `backup`, `vacuum` helpers,
stdlib `sqlite3` only); `engine/cli.py` (`cmd_db` + `db` subparser group).

**Behavior to pin (see sections "Retention + hermes db subcommand" and "Backup / restore of queue.db", D8 exact, HARD).**
- **`hermes db prune [--events-older-than DAYS] [--attempts-older-than DAYS]
  [--run R] [--dry-run]`** — one committed transaction (WAL durability automatic),
  per-row eligibility (deletable iff **every** clause holds), terminal run ∈
  {`done`,`failed`,`stopped`}, terminal ticket ∈ {`done`,`failed`}:
  - **`attempts` row** — ticket terminal AND run terminal AND `ended_at IS NOT NULL
    AND ended_at < cutoff`. (A ticket can be `done` while its run is still
    `running`; the run-terminal clause protects a live run's audit.)
    ```sql
    DELETE FROM attempts WHERE id IN (
      SELECT a.id FROM attempts a
      JOIN tickets t ON t.id = a.ticket_id
      JOIN runs   r ON r.id = t.run_id
      WHERE t.state IN ('done','failed')
        AND r.state IN ('done','failed','stopped')
        AND a.ended_at IS NOT NULL AND a.ended_at < :cutoff);
    ```
  - **`events` with non-null `ticket_id`** — ticket terminal AND run terminal AND
    `ts < cutoff`. (A `stopped` run can own a `running`/`dispatched` ticket whose
    reclaim is in flight; keying off run-terminal alone would delete live audit.)
    `events` has **no** foreign keys (schema.sql), so the eligibility JOINs are
    plain inner joins on the id strings — an event whose `ticket_id`/`run_id` no
    longer resolves simply fails the join and is **not** deleted (conservative):
    ```sql
    DELETE FROM events WHERE id IN (
      SELECT e.id FROM events e
      JOIN tickets t ON t.id = e.ticket_id
      JOIN runs    r ON r.id = t.run_id
      WHERE e.ticket_id IS NOT NULL
        AND t.state IN ('done','failed')
        AND r.state IN ('done','failed','stopped')
        AND e.ts < :cutoff);
    ```
  - **`events` with null `ticket_id`, non-null `run_id`** — run terminal AND
    `ts < cutoff`:
    ```sql
    DELETE FROM events WHERE id IN (
      SELECT e.id FROM events e
      JOIN runs r ON r.id = e.run_id
      WHERE e.ticket_id IS NULL AND e.run_id IS NOT NULL
        AND r.state IN ('done','failed','stopped')
        AND e.ts < :cutoff);
    ```
  - **`events` with null `run_id`** (fleet-wide crew/lease events) — `ts < cutoff`
    (`DELETE FROM events WHERE run_id IS NULL AND ts < :cutoff`).
  - `--run R` restricts every clause to that run. `--dry-run` reports counts, deletes
    nothing. Default cutoffs conservative (90 days). Emits **no** event; logs an INFO
    row-count summary per table.
- **`hermes db vacuum`** — WAL checkpoint then `VACUUM` (reclaim freed pages).
- **`hermes db backup --out PATH`** — SQLite **online backup API**
  (`sqlite3.Connection.backup(dest)`, stdlib), safe while a loop runs; output written
  0600 (matching the source via `os.chmod`).

**Tests first (RED)** — `tests/unit/test_db_maintenance.py` (new): seed a temp
`queue.db` (via real `migrate` + `queue`/`events` writers) with a mix:
- **Deletes** only rows whose run AND ticket are both terminal and past the cutoff.
- **Never** deletes: an `attempts` row on a `running`/`paused` run; a row on a
  non-terminal ticket (incl. `parked`/`needs_human`, which are *waiting*, not
  terminal); an `attempts` row with null `ended_at`.
- **Trap case** — a **`stopped` run owning a still-`running`/`dispatched` ticket**:
  its `events`/`attempts` **survive** (keying off run-terminal alone would wrongly
  delete them).
- Null-`run_id` events pruned purely by age; run-scope (null `ticket_id`) events
  need run-terminal.
- `--dry-run` deletes nothing but reports the same would-delete counts. `--run R`
  scopes correctly.
- `db backup` produces a file that opens, re-`apply_migrations` as a **no-op**, has
  **identical** row counts to the source (correctness under WAL, backup taken while a
  connection is open), and is mode `0600`. `db vacuum` runs clean.

**DoD.** Prune deletes only fully-terminal, aged rows and never live/in-flight state;
backup is WAL-safe and 0600; vacuum reclaims; `run_tests.sh` GREEN.

---

## Slice 7 — D6: control-plane container image + compose

**Scope.** Add a control-plane image (installs the `server` extra properly, runs
`hermes serve --api`, migrates on start, persistent `HERMES_HOME`, loopback bind
default) alongside the existing worker-only `fleet/`. Depends on D9 (installability).

**Files.** `fleet/Dockerfile.control-plane` (new);
`fleet/docker-compose.control-plane.yml` (new). Worker image + guard untouched.

**Behavior to pin (see the "Control-plane container image + compose" section, D6).**
- **`Dockerfile.control-plane`** — unlike `Dockerfile.worker` (which uses
  `PYTHONPATH` + a thin wrapper to dodge flat-layout discovery, `worker:26-37`), the
  control plane `pip install`s the package with the `server` extra (`pip install .[server]`
  or a built wheel from D10), so FastAPI/uvicorn resolve. Runs `hermes serve --api`.
  Bind-mounts `HERMES_HOME` as a volume (queue.db + api_token persist on local,
  non-networked storage — the "Fail-fast startup validation" guard). Exposes the API port (default 8080).
  Migrations apply on start (every process entry calls `apply_migrations` via
  `cli._connect()`).
- **`docker-compose.control-plane.yml`** — brings the control plane up bound to
  `127.0.0.1` by default, with `HERMES_BIND`, `HERMES_LOG_FORMAT=json`, and a
  persistent `HERMES_HOME` volume. Documents the non-loopback path (bind `0.0.0.0`
  only behind a trusted proxy that supplies auth) as **commented** config, matching
  `server/app.py`'s `is_loopback`/GET-gating/token-bootstrap-disabled model.

**Tests first (RED)** — `tests/integration/test_control_plane_image.py` (new,
`@pytest.mark.docker`, skips cleanly where Docker/podman absent — mirror
`test_fleet_docker.py`):
- Build the image; start it with a temp `HERMES_HOME` volume; `GET /api/health`
  returns 200 on the bound loopback port; `queue.db` appears in the volume with the
  migration table populated.
- Static assertions (no Docker needed, in a plain unit test): the compose file binds
  `127.0.0.1` by default, sets `HERMES_LOG_FORMAT=json`, and mounts a named
  `HERMES_HOME` volume; the Dockerfile `pip install`s the `server` extra (grep the
  build files) — so the "resolves fastapi/uvicorn" contract is checkable without a
  live build.

**DoD.** A control-plane image builds, installs the `server` extra, serves the API on
loopback with a persistent migrated `HERMES_HOME`; compose defaults to loopback +
json logs; `run_tests.sh -m "not docker"` GREEN, docker test green where available.

---

## Slice 8 — D7: systemd service-unit example

**Scope.** A documented systemd unit example for running `hermes serve --api` and/or
a per-host `hermes serve --host` as a managed service, with a stop timeout long
enough for the graceful-shutdown pass (D5). An example artifact, not a Meta-specific
deploy file.

**Files.** `fleet/hermes-control-plane.service` (new sample unit); referenced from
the runbook (D11, Slice 10).

**Behavior to pin (see the "Service-unit example" section, D7).** `Type=simple`,
`ExecStart=/usr/local/bin/hermes serve --api`, `Environment=HERMES_HOME=…
HERMES_LOG_FORMAT=json`, `Restart=on-failure`, `KillSignal=SIGTERM`, and
`TimeoutStopSec` comfortably above the final-housekeeping duration so SIGTERM's
graceful pass (D5) completes before SIGKILL. A commented worker variant
(`ExecStart=… serve --host …`).

**Tests first (RED)** — `tests/unit/test_service_unit.py` (new, static file
assertions): parse the unit file and assert `KillSignal=SIGTERM`,
`Restart=on-failure`, a `TimeoutStopSec` present and numeric, `HERMES_LOG_FORMAT=json`
in the environment, and `ExecStart` invoking `hermes serve --api`. (No systemd
needed; the file is a documented artifact whose shape is the contract.)

**DoD.** A valid, self-consistent example unit exists and its shape is asserted;
`run_tests.sh` GREEN.

---

## Slice 9 — D10: pinned `constraints.txt` for the `server` extra

**Scope.** A reproducible-deploy overlay: a `constraints.txt` capturing a known-good,
tested pin set for `fastapi`/`uvicorn`/`starlette`/`httpx`, referenced by the
control-plane image build. The floor pins in `pyproject.toml` stay; constraints are
the reproducible overlay. Depends on D6 (the image that consumes it).

**Files.** `constraints.txt` (new, repo root); `fleet/Dockerfile.control-plane`
(build step uses `-c constraints.txt`).

**Behavior to pin (see the "Pinned constraints for the server extra" section, D10).** Pin exact versions known to work together (resolve
them against the current floor pins and the existing Starlette/httpx
deprecation-warning already suppressed in `pyproject.toml`'s `filterwarnings`). The
control-plane build runs `pip install .[server] -c constraints.txt` so deploys are
reproducible.

**Tests first (RED)** — `tests/unit/test_constraints.py` (new, static): assert
`constraints.txt` exists and pins (with `==`) at least `fastapi`, `uvicorn`,
`starlette`, `httpx`; assert every version there is `>=` the corresponding
`pyproject.toml` floor (parse both), so the overlay can never resolve below the
declared floors. Assert the Dockerfile references `constraints.txt` in its install
step (grep).

**DoD.** A pinned constraints file exists, is floor-consistent, and is wired into the
control-plane build; `run_tests.sh` GREEN.

---

## Slice 10 — D11: refreshed README + operations runbook

**Scope.** De-stale the README ("Status: Design phase" is wrong now that the engine
core, dexter playbook, sites, and control-plane server are built) and add the one
operator doc this sub-project may create, `docs/RUNBOOK.md`. Documentation slice;
lands last so it can cite the finished commands.

**Files.** `README.md` (rewrite Status + add install/quickstart); `docs/RUNBOOK.md`
(new).

**Behavior to pin (see the "Refreshed README + quickstart + runbook" section, D11).**
- **README** — Status reflects what runs today; add a quickstart: create a venv,
  `pip install -e '.[dev,server]'`, `hermes run example --site local`,
  `hermes serve --api`, then `hermes doctor`.
- **`docs/RUNBOOK.md`** — deploy/upgrade (migrate-on-deploy: pull code, restart;
  migrations apply automatically, additive/WAL/`schema_migrations`), run topology
  (one control-plane process + one master loop + N worker serve loops sharing one
  `queue.db` on the master; workers reached over the site transport, no shared DB),
  starting the control plane + workers, graceful shutdown/restart (D5 + the systemd
  `TimeoutStopSec`), token rotation/loss recovery (`hermes serve --api
  --rotate-token`, non-loopback caveat), log configuration + OS log rotation
  (`logrotate`/container runtime; in-process rotation is out of scope), backup/restore
  (online-backup API; restore = stop all processes, replace `queue.db`, remove stale
  `-wal`/`-shm`, restart), prune/vacuum cadence, and `hermes doctor` as the first
  diagnostic step.

**Tests first (RED)** — `tests/unit/test_docs.py` (new, static): assert `README.md`
no longer contains "Design phase" and does contain the quickstart commands
(`pip install -e '.[dev,server]'`, `hermes run example`, `hermes serve --api`,
`hermes doctor`); assert `docs/RUNBOOK.md` exists and its section headers cover
deploy/topology/shutdown/backup-restore/prune/token-rotation/doctor.

**DoD.** README reflects reality with a working quickstart; the runbook covers every
operability lifecycle; `run_tests.sh` GREEN. All acceptance criteria from the "Acceptance criteria" section (AC1–AC8)
are now covered across the slices.

---

## Dependency graph

```
0 (D9 install) ─┬─────────────────────────────────────────────▶ 7 (D6 image) ─▶ 9 (D10 constraints)
                │                                                     │                    │
1 (D1 log) ─▶ 2 (D2 config) ─▶ 3 (D4 validate) ─▶ 4 (D3 doctor)      │                    │
                │                                                     │                    │
                └▶ 5 (D5 SIGTERM)                                     │                    │
                └▶ 6 (D8 db)                                          │                    │
                                                          8 (D7 unit) ┘                    │
                                                                                           ▼
                                                                          10 (D11 README + RUNBOOK)
```

- **D9 (Slice 0) leads** — it is the installability precondition for the
  control-plane image (D6) and its pinned constraints (D10); it is otherwise
  independent, so the logging/config chain can proceed in parallel after it.
- **D1→D2→D3→D4** is the config chain: logging first (its `configure()` is the entry
  hook), then config consolidation (which `configure()` then reads defaults from),
  then fail-fast `validate_startup` (uses the D2 accessors + D1 log enums), then
  `doctor` (uses the D2 registry + the same checks as `validate_startup`).
- **D5 (SIGTERM)** and **D8 (db)** depend only on the engine + D1 logging (both log
  an operational summary) and can follow the config chain in parallel.
- **D6 (image)** needs D9; **D7 (unit)** references D5's stop timeout; **D10
  (constraints)** needs D6; **D11 (docs)** lands last, citing every finished command.

## Test tooling

`pytest` (dev-only) under `tests/unit/` and `tests/integration/`, run via
`scripts/run_tests.sh` (`.venv`). No metrics backend, no real SSH, no real `claude`,
no Meta. Log assertions use `caplog` / an attached capture handler; config/prune/
backup/shutdown run against a temp `HERMES_HOME` (`testkit/fixtures.py`) and, where a
run must provision, the real one-commit-repo fixture pattern from
`test_fleet_scenario.py` / `test_local_run.py`. Docker-dependent slices (D6 image)
use `@pytest.mark.docker` and skip cleanly where Docker/podman is absent (mirroring
`test_fleet_docker.py`); their non-Docker contracts are also asserted statically.

## Deferred (not implemented here; recorded, per spec "Scope" out-of-scope and "Open items")

- **Metrics-backend export** (Prometheus/StatsD/ODS). The JSON log formatter (D1),
  `GET /api/runs/{id}/metrics`, and the `events` feed are the seams; shipping is not
  built.
- **Secrets manager** (Vault/KMS). The bearer token stays a 0600 file; non-loopback
  relies on a trusted proxy.
- **In-process log rotation.** `HERMES_LOG_FILE` writes a single append file;
  rotation is delegated to `logrotate` / the container runtime (documented in the
  runbook).
- **Automatic/background pruning.** `db prune` stays operator-invoked (or cron'd via
  the runbook); a heartbeat-driven periodic prune is deferred.
- **Meta-internal deploy specifics.** Meta-isms stay in the `meta`/`devserver` site
  adapters and their env vars, injected at deploy time; documented, never hardcoded.
- **Defaulting `HERMES_LOG_FILE` under `$HERMES_HOME/logs/`.** The reserved `logs/`
  dir is a natural default if file logging is opted into; the spec default stays
  stderr and the choice is left open.
