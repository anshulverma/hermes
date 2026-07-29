# Hermes `dexter` playbook + `devserver` site — implementation plan (sub-project 2)

Status: **draft**. Date: 2026-07-29. Spec: `docs/specs/dexter-playbook.md`
(hardened to convergence, commit `2693e1c`). Depends on: engine-core
(`docs/specs/engine-core.md`, `docs/specs/engine-core-plan.md`) — **already built**.

Vertical slices in dependency order. Each slice is independently testable, follows
**TDD** (write the failing test first, then the code), and ends GREEN before the
next begins. Every slice lists its **scope**, **files**, the **failing tests to
write first**, and its **DoD**. Engine core stays **stdlib-only at runtime**;
adapters (`sites/devserver`) may shell out via `subprocess`. `pytest` is dev-only.

Conventions: paths are under `hermes/`. "GREEN" = `scripts/run_tests.sh` passes.
Commit after each slice. Section references (`§2.3`, `D1`…) point at the spec.

---

## Global constraints (apply to every slice)

- **Stdlib-only engine.** No third-party runtime import anywhere the engine loads
  (`engine/*`, `playbooks/*`, `sites/*`, `agents/*`). The devserver site may use
  `subprocess`/`shutil`/`os`/`json`/`tempfile` only (mirrors `sites/ssh`). The
  existing `tests/unit/test_invariants.py` import-scan must keep passing; extend it
  to cover `playbooks.dexter` and `sites.devserver.site`.
- **Match the engine's real protocol signatures — do not re-invent them.** The
  playbook implements `engine/playbook.py`'s `Playbook` Protocol exactly
  (`seed(run, site)`, `payload_schema(phase)`, `result_schema(phase)`,
  `driver(phase)`, `reduce(run, phase, findings, site)`,
  `verify(run, ticket, result, site)`, `next_phase(run)`, `is_done(run)`); the
  site implements `engine/site.py`'s `Site` Protocol exactly (`discover_hosts`,
  `provision`, `health`, `run_worker`, `resource_classes`, `guarantees_no_ship`,
  `submit_for_review`, `issue_source`). `recheck_fix` is an **extension** method,
  NOT added to the Protocol (D3).
- **No-ship invariant (two layers, §7).** `devserver.guarantees_no_ship()` returns
  `True` only because `provision` installs and `health` honestly reports the guard
  shims; `run_worker` prepends the per-host guard dir to the remote `PATH`.
  `reduce` lands nothing. Every slice that touches dispatch/exec must preserve both
  layers; the integration slice asserts a worker `git push`/land is blocked
  (exit `97`).
- **No faked test data.** Tests use real engine writers (`queue.*`, `dispatch.*`)
  against a temp `HERMES_HOME` (via `testkit/fixtures.py`), real
  `contracts.validate_result`, and real §2.3-shaped payloads. The only doubles are
  `DexterMockAgent` (emits §2.3 docs, no real `claude`/SSH), `DexterLocalSite`
  (adds `recheck_fix` on localhost), and `FakeSink` (in-memory learning sink). No
  monkey-patching of engine state; drive everything through the public writers.
- **Registration by import side-effect.** Each adapter module registers its
  singleton at import (`playbook.register("dexter", DexterPlaybook())`,
  `site.register("devserver", DevserverSite())`), matching
  `sites/local/site.py` and `agents/claude/agent.py`. Package `__init__.py`
  re-exports for the loader (mirrors `agents/claude/__init__.py`).
- **Directory layout mirrors the repo.** New code lives in `playbooks/dexter/`,
  `sites/devserver/`, `agents/claude` (reused, unchanged), `testkit/`, with tests
  under `tests/unit/` and `tests/integration/`.

### Top-risk decisions (baked into the slices, from the hardening report)

- **Blocked-run risk (no terminal-abandon for a re-verify `needs_human` ticket).**
  Decision: **do NOT add a new engine delta.** The documented operator path is the
  existing `hermes ticket requeue <id>` (`queue.requeue_needs_human`), which the
  integration slice (Slice 9) exercises end-to-end. The absence of a terminal
  `ticket abandon` is recorded as an **accepted limitation** (spec §9) and asserted
  as a behavior (a never-re-verifiable fix keeps the phase blocked until requeued).
  Promoting `recheck_fix` to the core Protocol and adding `ticket abandon` are
  explicitly deferred; noted in the plan's Deferred section, not implemented here.
- **Stale-finding risk (reduce has no ticket-state access).** Decision: handle via
  **fold-latest-per-ticket + verify gating** in Slice 4. Because `verify` fails a
  malformed/unconfirmed `ok` to `needs_human` (which blocks reduce until cleared),
  every finding that reaches a cluster came from a verified ticket. The residual
  ok-then-terminal-`failed` edge (a ticket that returned `ok`, wrote a finding,
  then later went `failed`) is an **accepted limitation** mitigated by the
  mandatory human review of every cluster (reject drops it); Slice 4 has an
  explicit unit test for the fold and a documented note for the residual edge.

---

## Slice 0 — Scaffold (packages + test skeleton)

**Scope.** Create the empty, importable package skeleton for the two adapters and
their tests so later slices only add behavior. No behavior yet.

**Files.**
- `playbooks/__init__.py`, `playbooks/dexter/__init__.py` (docstring; will
  re-export `playbook` on the module once it exists, like `agents/claude/__init__.py`).
- `sites/devserver/__init__.py` (re-exports `site` once it exists).
- `tests/unit/test_dexter_playbook.py`, `tests/unit/test_devserver_site.py`,
  `tests/integration/test_dexter_run.py` — skeletons with a single
  `import`-smoke test each (xfail/placeholder until the module lands).

**Tests first (RED).** A trivial `test_packages_importable` asserting
`import playbooks` / `import sites.devserver` succeed (initially failing: dirs
absent).

**DoD.** `run_tests.sh` green; the three new test modules collect; packages import
cleanly. No engine files changed yet.

---

## Slice 1 — Delta D1: `hermes run … --goals FILE` (CLI + run.config seam)

**Scope.** The only functional CLI change. Add `--goals PATH` to the `run`
subparser; make `cmd_run` build `run_config["goals"]` from it (replacing the
hardcoded `run_config = {}` at `engine/cli.py:64`). Goals-file format per §2.1a.

**Files.** `engine/cli.py` (run subparser + `cmd_run`); a small helper
`_load_goals_file(path) -> list[str]` (in `cli.py`).

**Format + semantics (§2.1a), pin exactly.**
- `--goals PATH`: read `PATH`, **one goal per line**; **skip blank lines and lines
  whose first non-space char is `#`**; strip surrounding whitespace on each kept
  line. Result is a `list[str]`.
- `cmd_run`: if `args.goals` given, `run_config = {"goals": _load_goals_file(path)}`
  else `run_config = {}` (unchanged behavior). Everything downstream is untouched —
  `_create_run` already serializes `run_config` into `runs.config_json`, and
  `queue.load_run` round-trips it back into `run.config`, so `seed` reads it.
- Empty/missing-after-filtering file ⇒ `{"goals": []}` ⇒ zero tickets ⇒ the run
  seeds nothing and terminates immediately (correct degenerate no-op).
- `issue_query` gets **no** CLI flag here (deferred; supplied via the control-plane
  API's arbitrary `config`, §2.1a).

**Tests first (RED)** — `tests/unit/test_cli.py` (extend):
- `_load_goals_file` parses a temp file: keeps 3 goals, drops blank lines, drops
  `#`-comment lines (incl. leading-space `   # x`), strips whitespace, preserves
  order.
- `cmd_run --goals FILE --dry-run` (with a stub playbook) puts the parsed list into
  `runs.config_json` → `run.config["goals"]` (assert via the created run row).
- Missing/empty file ⇒ `run.config["goals"] == []`.
- No `--goals` ⇒ `run.config == {}` (regression: existing runs unaffected).

**DoD.** `hermes run <pb> --site local --goals FILE --dry-run` reports the goals
in `run.config`; existing CLI tests still green; no other engine file touched.

---

## Slice 2 — dexter Playbook: identity, schemas, seed, driver, advancement

**Scope.** The registerable `DexterPlaybook` core: `name`/`phases`, the two
schemas, `seed` (goals→tickets, all three sources), `driver`, `next_phase`,
`is_done`. `verify`/`reduce` are stubbed (raise `NotImplementedError`) and filled
in Slices 3–4. The sink constructor arg is introduced but unused until Slice 4.

**Files.** `playbooks/dexter/playbook.py`, `playbooks/dexter/__init__.py`
(re-export). No engine change.

**Behavior to pin (§2.1–2.4, §2.7).**
- `name = "dexter"`, `phases = ["solve"]`.
- `__init__(self, sink=None)` — stores `self.sink` (default deferred to Slice 4's
  `DexterKbSink`); mirrors `MockAgent(scenarios=…)` injection (§5).
- `seed(run, site)`: build one `Ticket` per goal. Goals from **either**:
  (a) `run.config["goals"]` — accept a `list[str]` (used directly) **or** a `str`
  path (read with the §2.1a filter); (b) if `run.config.get("issue_query")`, call
  `site.issue_source(IssueQuery(**run.config["issue_query"]))` and map each `Issue`
  to a goal (`goal=issue.title`, `issue_ref=issue.ref`,
  `priority=issue.data.get("priority", 0)`). Ticket fields exactly per
  `engine/models.py`: `id=f"{run.id}/solve-{i}"`, `run_id=run.id`, `phase="solve"`,
  `state="queued"`, `resource_req="cpu"`, `priority` (float), `attempts=0`,
  `payload={"goal": <str>, "issue_ref": <str|null>, "context": <object>}` — and
  **only** those payload keys (`additionalProperties:false`, §2.2).
- `payload_schema("solve")` = the §2.2 object (required `["goal"]`,
  `additionalProperties:false`, props `goal`/`issue_ref`/`context`), within the
  `contracts.validate` subset.
- `result_schema("solve")` = the §2.3 object (the dexter finding doc).
- `driver("solve") = Driver(command="/dexter:solve", args={}, loop=None)` —
  `args={}` is deliberate (§2.4: a non-empty `args` renders as literal `k=v` after
  the command; the goal reaches the worker only via `/goal <goal>`).
- `next_phase(run) -> None` always; `is_done(run) -> run.phase == "solve"` (True).

**Tests first (RED)** — `tests/unit/test_dexter_playbook.py`:
- `seed` from a `run.config["goals"]` **list** → N tickets with the exact
  ids/fields/payload keys; goal lands in `payload["goal"]`.
- `seed` from a `run.config["goals"]` **file path** (§2.1a comment/blank filtering).
- `seed` from a **mocked `issue_source`** (a fake site returning `Issue`s) →
  `issue_ref`/`priority` mapped; `IssueQuery(**…)` built from `run.config`.
- `seed` with no goals ⇒ `[]`.
- `payload_schema` **accepts** `{goal, issue_ref, context}` and **rejects** an
  extra key (`additionalProperties:false`) and a missing `goal`, via
  `contracts.validate_envelope`/`validate`.
- `result_schema` accepts a valid §2.3 doc and rejects one missing `root_cause`,
  via `contracts.validate_result`.
- `driver("solve")` == `Driver("/dexter:solve", {}, None)`; and the rendered prompt
  through `ClaudeAgent._build_prompt(goal, driver)` is exactly
  `"/goal <goal> /dexter:solve"` (no `k=v` tail).
- `next_phase` → `None`; `is_done` → `True`.

**DoD.** `playbook.load("dexter")` (after importing the module) returns the
instance; the schema/seed/driver tests are green; `verify`/`reduce` raise
`NotImplementedError` (proven by a test that they are not yet callable).

---

## Slice 3 — dexter Playbook: `verify` (shape gate + D3 duck-type, fail-safe)

**Scope.** Implement `verify(run, ticket, result, site) -> bool` (§2.5) — the point
where the §2.3 contract is actually enforced (the engine never auto-validates a
result payload) and where the **playbook half of D3** lives (duck-typing
`site.recheck_fix`, fail-safe when absent).

**Files.** `playbooks/dexter/playbook.py` (fill `verify`). No engine change.

**Behavior to pin (§2.5).** `verify` runs inside `queue.record_result` on every
`outcome=="ok"` result (True ⇒ `reducing`; False ⇒ `needs_human`). No-trust rule —
do **not** read `result.payload["fix"]["verified"]`.
1. **Shape gate.** Reconstruct the outer result dict from the `Result` dataclass
   (all `RESULT_OUTER` fields: `outcome`, `termination_reason`, `result_ref`,
   `evidence_ref`, `started_at`, `ended_at`, `error_summary`,
   `payload=result.payload`) and call
   `contracts.validate_result(result_dict, self.result_schema("solve"))`. On
   `ContractError` ⇒ return `False`.
2. **Independent fix re-check (D3, duck-typed).**
   `fn = getattr(site, "recheck_fix", None)`; if callable, return
   `bool(fn(result.payload))`. If **absent** ⇒ **fail safe**: return `False`
   (never a false pass) **unless** `run.config.get("verify_recheck_optional")` is
   truthy (test hook that admits on the shape gate alone).
3. Return `True` iff shape gate passes **and** the re-check confirms.

**Tests first (RED)** — `tests/unit/test_dexter_playbook.py`:
- Valid §2.3 payload + a fake site whose `recheck_fix` returns `True` ⇒ `verify`
  True.
- Valid §2.3 payload + `recheck_fix` returns `False` ⇒ `verify` False.
- Malformed payload (missing `root_cause`) + `recheck_fix` True ⇒ `verify` False
  (shape gate wins; no-trust).
- Site **without** `recheck_fix` (e.g. bare `LocalSite`) ⇒ `verify` False
  (fail-safe), and `verify` True when `run.config["verify_recheck_optional"]` set.
- `verify` does **not** read `fix.verified` (payload with `fix.verified=true` but
  `recheck_fix`→False still fails).

**DoD.** All `verify` branches (pass / shape-fail / recheck-false / absent-failsafe
/ optional-admit) covered; `verify` requires no dexter tooling on the master.

---

## Slice 4 — dexter Playbook: `reduce` + LearningSink (cross-host dedup + bank)

**Scope.** Implement `reduce(run, phase, findings, site) -> list[Reduction]`
(§2.6): fold-latest-per-ticket, cluster by root-cause signature, canonical/
duplicate split, one best-effort banked learning per cluster, and the exact
`Reduction.json` shape with `needs_human_ticket_ids`. Add the `LearningSink`
interface + `DexterKbSink` (default) + `FakeSink` (tests).

**Files.** `playbooks/dexter/playbook.py` (fill `reduce`, wire `self.sink`);
`playbooks/dexter/sink.py` (`LearningSink` protocol, `DexterKbSink`, `FakeSink`).
No engine change.

**Behavior to pin (§2.6, §5).**
- **Fold to latest finding per ticket.** `findings` is append-only, ordered by
  `findings.id` asc (`queue.load_findings`); collapse to the **last** finding per
  `ticket_id` before clustering (a ticket with two `ok` findings counts once).
- **Cluster** folded findings by `finding.json["root_cause"]["signature"]`.
- Per cluster: **canonical** `ticket_id` = deterministic **lowest ticket id**;
  duplicates = other members (each with its `fix.diff_ref`).
- **Bank one learning per cluster** via `self.sink.bank(cluster) -> str | None`.
  Best-effort: wrap in try/except — any exception ⇒ `learning_ref=None` +
  `learning_error="<msg>"`; `reduce` must **never raise** (an uncaught exception
  would wedge `dispatch._do_reduce`/`master_loop`).
- Return one **light** `Reduction` per cluster:
  `Reduction(kind="root_cause_cluster", json={signature, cause_category,
  canonical_ticket_id, canonical_diff_ref, duplicate_diffs:[{ticket_id, diff_ref}],
  member_ticket_ids, learning_ref, learning_error, needs_human_ticket_ids:[all
  member ticket ids]})`. `needs_human_ticket_ids` lives **inside** `.json` (that is
  where `queue.record_reduction` reads it), not as a top-level field. The queue
  hydrates `id/run_id/phase/review_state='pending'`.
- `LearningSink.bank(cluster: dict) -> str | None`. `DexterKbSink` shells the
  dexter plugin's `kb.py` (`validate` then `index`) against `INVESTIGATIONS_DIR`
  (the single master-side dexter coupling, §5); `FakeSink` records calls in memory
  and returns a canned ref (or raises when constructed to simulate failure).

**Stale-finding handling (top-risk).** Rely on fold-latest + verify gating (only
verified tickets contribute; verify-failed ones are `needs_human` and block reduce,
§2.6). Add a note + a unit test documenting the residual ok-then-failed edge is
surfaced-and-rejectable (never silently banked); no engine change.

**Tests first (RED)** — `tests/unit/test_dexter_playbook.py` (+ `sink` tests):
- Two findings sharing a `signature` (from two ticket ids) → **one** cluster
  reduction: canonical = lowest id, one `duplicate_diffs` entry, both in
  `member_ticket_ids` and `needs_human_ticket_ids`.
- Distinct signatures → separate clusters.
- **Fold-latest**: a ticket with two `ok` findings (stale then fresh) counts once,
  using the **last** finding's fields.
- `FakeSink` banks **exactly one** learning per cluster; `learning_ref` set in
  `.json`.
- Sink raises ⇒ `learning_ref=None` + `learning_error` present, and `reduce`
  returns normally (no exception).
- `Reduction.json` has all required keys with the exact names; `needs_human_ticket_ids`
  is inside `.json`.

**DoD.** `reduce` clusters/folds/banks correctly, never raises, and emits the
`record_reduction`-compatible shape; sink is injectable and fully faked (no dexter
install needed).

---

## Slice 5 — devserver Site: core `Site` protocol

**Scope.** `DevserverSite` implementing the **exact** `engine/site.py` signatures
over internal devservers with native `buck2`/`sl`/test tooling. A **distinct** site
(not `SSHSite`): real idempotent provisioning + honest guard reporting. May reuse
`transport.build_ssh_opts`/`build_scp_opts` but does not inherit `SSHSite`.
Meta-internal specifics stay deploy-time pluggable (host-list source, install
recipe, dashboard endpoint), not hardcoded.

**Files.** `sites/devserver/site.py`, `sites/devserver/__init__.py` (re-export).
`recheck_fix` deferred to Slice 6. No engine change.

**Behavior to pin (§3).**
- `name = "devserver"`.
- `discover_hosts()` — read an internal host list from config (env/config seam),
  else `[]` (hosts supplied via `--hosts`, which `cmd_run` already splits +
  `crew.add`s).
- `provision(host, base_ref) -> None` — over SSH, **idempotent**: ensure a clean
  checkout at `base_ref` (`sl`/git); ensure `claude` present+authed and the
  `dexter` plugin installed; install the **no-ship guard** PATH shims into a
  per-host guard dir (same `GUARD_SHIMS` set as `sites/local`: block `git push`,
  `sl push|land`, `hg push`, `jf land`, `arc land`, exit `97`); ensure dexter's
  runtime-data dir exists. The install recipe is a pluggable hook.
- `health(host, agent) -> HealthReport` — exact `engine/models.py` fields:
  `reachable` (ssh), `agent_ok`/`auth_ok` (from `agent.health_checks(host, self)`
  via the `_find_ok` helper pattern), `workspace_ready` (checkout at `base_ref`,
  clean), `guard_installed` (shims **actually** present — must not lie, unlike the
  ssh site's hardcoded `True`), `resources={"cpu": <nproc:int>}` (`dict[str,int]`),
  `latency_ms:int`, `checks=[site checks] + agent_checks`.
- `run_worker(host, envelope, agent) -> Result` — SSH transport that (a) scp's the
  envelope up, (b) runs `hermes serve-once --envelope … --result … --timeout …`
  over SSH **with the guard dir prepended to the remote `PATH`** (the ssh command
  exports `PATH=<guarddir>:$PATH` before `serve-once` — the generic
  `ssh_transport` does NOT set PATH, which is why devserver needs its own), (c)
  scp's `result.json` + evidence back and returns `agent.parse_result(raw,
  envelope)`. **Connection-level** failure (ssh exit 255, refused/timeout, failed
  scp) **raises** `transport.TransportError` (→ no-penalty `requeue_transport`); a
  worker that ran and returned a Result passes through (mirror `sites/ssh`).
- `resource_classes() -> ["cpu"]`.
- `guarantees_no_ship() -> True` (installs + verifies the guard).
- `submit_for_review(host, change) -> str` — wraps the box's publish-only
  `jf submit` (never land), returns the review URL.
- `issue_source(query) -> list[Issue]` — optional: query an internal dashboard,
  map rows to `Issue{id, kind, title, ref, data}` (`kind` echoes `query.kind`),
  honor `query.limit`. Endpoint pluggable; default may return `[]`.

**Tests first (RED)** — `tests/unit/test_devserver_site.py` (all `subprocess`
mocked; no real SSH/Meta):
- `run_worker` builds the expected `scp`/`ssh` argv, and the ssh remote command
  **prepends `PATH=<guarddir>:$PATH`** before `hermes serve-once`.
- ssh exit 255 (or a raised `CalledProcessError` on scp) ⇒ `run_worker` raises
  `transport.TransportError`; a worker that ran ⇒ result parsed via
  `agent.parse_result`.
- `health` parses into a `HealthReport` with all fields; `guard_installed` reflects
  the (mocked) shim-presence probe, not a hardcoded `True`;
  `resources == {"cpu": <int>}`; `agent_ok`/`auth_ok` pulled from the agent checks.
- `provision` is idempotent (second call does not re-checkout; always re-verifies/
  re-installs the guard) — assert the mocked command sequence.
- `guarantees_no_ship()` True; `resource_classes()` `["cpu"]`;
  `submit_for_review` returns a URL and never issues a land/push subcommand.

**DoD.** `site.load("devserver")` returns the instance; all core-protocol tests
green with `subprocess` mocked; guard reported honestly.

---

## Slice 6 — devserver Site: `recheck_fix` extension (D3, site half)

**Scope.** Add the **extension** method `recheck_fix(result_payload: dict) -> bool`
(NOT on the core `Site` Protocol) that the dexter `verify` duck-types (Slice 3).
This is the site half of D3.

**Files.** `sites/devserver/site.py` (add `recheck_fix`). No engine change.

**Behavior to pin (§2.5, §3, D3).** Host-agnostic independent re-check: re-query
the published diff's CI signal via the internal tool
(`result_payload["fix"]["diff_ref"]`) and/or spin the recorded minimal repro on a
`discover_hosts()`-chosen box at the run's `base_ref`; return whether the fix
independently holds. The CI-signal lookup / repro command is a deploy-time
pluggable hook. Returns `False` on any inconclusive/failed check (never a false
pass).

**Tests first (RED)** — `tests/unit/test_devserver_site.py`:
- `recheck_fix` with a mocked CI-signal probe returning "green"/"passing" ⇒ `True`.
- Mocked probe returning "failing"/inconclusive/raising ⇒ `False`.
- `recheck_fix` uses `result_payload["fix"]["diff_ref"]` in its query argv.
- End-to-end duck-type check: `getattr(DevserverSite(), "recheck_fix")` is callable
  and the dexter `verify` (Slice 3) invokes it (thin wiring test).

**DoD.** `recheck_fix` present on `DevserverSite`, absent on the core Protocol
(the Protocol is unchanged); both `verify` branches (present-True/False) reachable
against the real site with a mocked probe.

---

## Slice 7 — Delta D2: register the dexter adapters in the CLI loader

**Scope.** Pure wiring: make `hermes run dexter --site devserver --agent claude`
resolvable. `engine/cli.py:_load_playbook_site_agent` currently imports only
`testkit.*` + `sites.local.site` and carries `# TODO: import agents.claude.agent`.
Add imports (for registration side-effects) of `playbooks.dexter`,
`sites.devserver.site`, and `agents.claude`; remove the TODO.

**Why sequenced here (dependency-honest).** D2's imports must **resolve** — they
reference `playbooks.dexter` (Slices 2–4) and `sites.devserver.site` (Slices 5–6).
D1 (Slice 1) is the truly-standalone delta and comes first; D3 is split across the
playbook (Slice 3) and site (Slice 6). D2 lands once the modules it imports exist.

**Files.** `engine/cli.py` (`_load_playbook_site_agent` imports only). No new
modules.

**Tests first (RED)** — `tests/unit/test_cli.py`:
- `_load_playbook_site_agent` with `playbook="dexter", site="devserver",
  agent="claude"` returns the three registered singletons (no `KeyError`).
- Regression: `example`/`local`/`mock` still resolve.
- Import-scan invariant (`tests/unit/test_invariants.py`): importing
  `playbooks.dexter` and `sites.devserver.site` pulls in **no third-party**
  package.

**DoD.** `hermes run dexter --site devserver --agent claude --dry-run --goals FILE`
loads all three adapters and seeds tickets; loader tests green.

---

## Slice 8 — Test doubles: `DexterMockAgent` + `DexterLocalSite`

**Scope.** The two doubles that let the whole flow run without real dexter, SSH, or
Meta (§6). Kept in the dexter sub-project's testkit area, not in production
adapters.

**Files.** `testkit/dexter_doubles.py` (or `testkit/dexter/…`): `DexterMockAgent`,
`DexterLocalSite`. Register `DexterMockAgent` under a name (e.g. `dexter_mock`) via
import side-effect so `HERMES_AGENT` can select it.

**Behavior to pin (§6).**
- `DexterMockAgent(Agent)` — `build_invocation` returns a trivial argv (like
  `MockAgent`: `["true"]`); `parse_result` returns a **§2.3-shaped payload**
  selected per ticket/goal from a scenario map (decoupled from the
  schema-constrained ticket payload — the stock `MockAgent` only echoes the payload
  and cannot emit an arbitrary §2.3 doc). Honors `payload_sha256` integrity like
  the other agents. `health_checks` pass.
- `DexterLocalSite(LocalSite)` — subclass adding `recheck_fix(payload) -> bool`
  returning a per-scenario verdict (so a "fix holds" goal reaches `reducing` and a
  "fix does not hold" goal routes to `needs_human`) — all on localhost, reusing
  LocalSite's real git worktree + guard. Register under `dexter_local`.

**Tests first (RED)** — `tests/unit/test_dexter_doubles.py`:
- `DexterMockAgent.parse_result` yields a **valid §2.3 doc** per scenario (assert
  via `contracts.validate_result` against `result_schema("solve")`), incl. two
  goals sharing a `root_cause.signature` and one "fix-does-not-hold" scenario.
- `DexterLocalSite.recheck_fix` returns the scenario verdict; when composed with
  the dexter `verify`, a "holds" payload ⇒ True, a "does-not-hold" ⇒ False.
- Doubles register and resolve via the agent/site registries.

**DoD.** The doubles emit real §2.3 data and drive both `verify` branches on
localhost; no real `claude`/SSH/Meta.

---

## Slice 9 — Integration: fan-out → cross-host dedup → bank → flag → done

**Scope.** The end-to-end proof on `DexterLocalSite` + `DexterMockAgent` +
`DexterPlaybook(sink=FakeSink())`, driven through the real `dispatch.master_loop`
against a temp `HERMES_HOME`. This is the acceptance slice (spec §8).

**Files.** `tests/integration/test_dexter_run.py`. No production code (all prior
slices supply it); may add a `FakeSink`-injected playbook registration helper in
the test.

**Behavior to pin / assert (§4, §6, §8).**
- **Fan-out.** `seed` one `solve` ticket per goal; each host runs
  `"/goal <goal> /dexter:solve"`; `record_result` writes a finding (`kind="result"`,
  `json`=§2.3 doc) and runs `verify`.
- **Cross-host dedup → one banked learning per cluster.** Two goals sharing a
  `root_cause.signature` → `reduce` yields **one** cluster reduction (canonical +
  **one** duplicate); `FakeSink` banked **exactly one** learning for that cluster;
  a ticket that produced two `ok` findings is counted **once** (fold dedup).
- **Duplicate diff flagged to needs_human.** Both cluster members routed to
  `needs_human` via `needs_human_ticket_ids` inside `reduction.json`
  (`record_reduction` reducing-only routing).
- **Human resolution.** `queue.accept_reduction` (or `hermes reduction accept`) →
  members `done`; a separate reject run → members `failed`.
- **verify-fail blocks + requeue clears (blocked-run top-risk).** A
  "fix-does-not-hold" goal (verify False via `DexterLocalSite.recheck_fix`) lands
  in `needs_human` and **blocks phase reduce** (asserted: `reduce` does not run
  while `nh>0`); `hermes ticket requeue` (`queue.requeue_needs_human`) returns it to
  `queued`; a subsequent re-run that re-verifies lets the phase settle. Also assert
  there is **no** terminal-abandon path (documented accepted limitation).
- **Run reaches done.** After every cluster is accepted, the phase settles
  (done/failed only), `is_done` → True, run `running → done`; learnings already
  banked in `reduce`.
- **No-ship invariant (§7).** A worker `git push`/land attempt is blocked by the
  guard shim (exit `97`); and a site with `guarantees_no_ship()==False` is rejected
  at dispatch (`contract_fail`) — assert both.
- **Event stream.** Assert ordered kinds appear: `ticket_claimed`,
  `result_recorded`, `needs_human`, `reduction_created`,
  `reduction_accepted`/`ticket_failed`, `run_done`.

**Tests first (RED)** — the above as one or a few integration tests via
`master_loop`; all through real engine writers; zero external deps; runs under
`scripts/run_tests.sh`.

**DoD.** Spec §8 acceptance criteria 1–5 pass end-to-end on localhost with no
dexter/devserver/Meta dependency; `run_tests.sh` ALL GREEN.

---

## Dependency graph

```
0 ─▶ 1 (D1) ─────────────────────────────────────┐
     │                                            │
     └▶ 2 (playbook core) ─▶ 3 (verify, D3-pb) ─▶ 4 (reduce+sink) ─┐
                                                                    │
        5 (devserver core) ─▶ 6 (recheck_fix, D3-site) ────────────┤
                                                                    ▼
                                        7 (D2 register) ─▶ 8 (doubles) ─▶ 9 (integration)
```

- **Deltas first where dependency-honest:** D1 (Slice 1) is standalone and leads.
  D3 is split — playbook half in Slice 3, site half in Slice 6. D2 (Slice 7) is
  wiring that requires its imported modules (Slices 2–6) to exist, so it lands
  after them but before the doubles/integration.
- The playbook chain (2→3→4) and the site chain (5→6) are independent and may be
  built in parallel after Slice 1; both converge into Slice 7.
- Slice 9 depends on everything (it drives the full loop through the real engine).

## Test tooling

`pytest` (dev-only), tests under `tests/unit/` and `tests/integration/`, run via
`scripts/run_tests.sh`. No network, no SSH, no real `claude`, no Meta, no dexter
install in any test — `DexterLocalSite` + `DexterMockAgent` + `FakeSink` provide
full coverage. `subprocess` is mocked in all `sites/devserver` unit tests.

## Deferred (not implemented here; recorded, per spec §9)

- A terminal `hermes ticket abandon <id>` engine transition for a never-
  re-verifiable `needs_human` ticket (would be an engine change; out of scope).
- Promoting `recheck_fix` to the core `Site` Protocol (deliberate engine change).
- A `--config JSON` CLI flag for `issue_query`; the internal dashboard
  `issue_source` schema; a shared `_meta_common` module for devserver + a future
  `sites/meta`.
