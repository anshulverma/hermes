# Hermes `dexter` playbook + `devserver` site — spec

Status: **draft (hardened to convergence against the built engine)**. Date: 2026-07-29.
Parent: `docs/DESIGN.md`. Depends on: engine-core (`docs/specs/engine-core.md`).

This specs a **playbook sub-project**: fan the `dexter:solve` forensic-investigation
command across a crew of internal devservers, then **synthesize across hosts**
(dedup investigations by root cause, bank one consolidated learning per cluster,
flag duplicate diffs for human review). It is "Option 2" from the design
discussion — dexter-aware, not a generic runner.

Two adapters are delivered together (both are needed to run this end-to-end):
1. the **`dexter` playbook** (methodology — site- and agent-agnostic), and
2. the thin **`devserver` site** (how to reach/provision/run on internal
   devservers). dexter:solve uses each box's **native** `buck2`/`sl`/test tooling
   directly, so this site is far lighter than the full `meta` site.

The worker runtime is the **`claude` agent adapter** (unchanged); the driver
command is **`/dexter:solve`**.

---

## 1. Scope

**In scope**
- `playbooks/dexter/` — a `Playbook` (§8 of engine-core) implementing seed, the
  solve-phase payload/result schemas, the `/dexter:solve` driver, the cross-host
  `reduce` (cluster + best-effort bank via an injected `LearningSink`, §5),
  independent `verify` (shape gate + duck-typed `recheck_fix`, §2.5), and
  definition-of-done. Uses the existing `claude` agent unchanged.
- `sites/devserver/` — a `Site` (§8 of engine-core) with the exact `engine/site.py`
  signatures: SSH reach + idempotent provision (checkout, ensure `claude`+`dexter`
  installed, install no-ship guard), structured health, SSH transport with the
  guard dir prepended to the remote `PATH`, `cpu` resource class,
  `guarantees_no_ship`, optional `issue_source`, and the `recheck_fix` extension
  (delta D3).
- Three small engine-side deltas (§1a): **D1** `--goals FILE`, **D2** adapter
  registration in the CLI loader, **D3** the `recheck_fix` site extension.
- Tests (unit + integration) that run the whole flow on a **`DexterLocalSite` +
  `DexterMockAgent`** emitting dexter-shaped §2.3 results (§6) — no real dexter,
  devservers, SSH, or Meta needed.

**Out of scope**
- The full `meta` site (buck2/testinfra as site methods) — dexter uses native
  box tooling, so it is unnecessary here.
- Auto-landing (forbidden by construction; §7). Human lands after review.
- The `mechanic`/`rigger` playbooks.

**Runtime prerequisite (master side).** The Hermes master running this playbook
needs the `dexter` plugin present so `reduce` can bank learnings via dexter's
`kb.py`, and an `INVESTIGATIONS_DIR` to write to (§5). This coupling is acceptable
because the playbook is dexter-specific.

---

## 1a. Engine deltas this sub-project requires (new work, labeled)

The current engine (`engine/*.py`, `agents/claude/agent.py`, `sites/*`) does **not**
yet supply everything this playbook needs. The following are the *only* changes
required outside `playbooks/dexter/` and `sites/devserver/`, each specified as an
explicit delta so nothing is assumed:

- **D1 — `hermes run … --goals FILE` (CLI + run.config seam).** `engine/cli.py`
  `cmd_run` hardcodes `run_config = {}`; there is no way to pass goals into a run.
  Add a `--goals PATH` argument to the `run` subparser and populate
  `run_config["goals"]` (§2.1a). Nothing else in the engine changes — `seed`
  reads `run.config`, which the queue already round-trips through `runs.config_json`.
- **D2 — register the dexter adapters in the CLI loader.** `_load_playbook_site_agent`
  imports only `testkit.*` + `sites.local.site` and has a `# TODO: import
  agents.claude.agent`. To resolve `hermes run dexter --site devserver --agent
  claude`, it must also import (for their registration side-effects)
  `playbooks.dexter`, `sites.devserver.site`, and `agents.claude`. Pure wiring.
- **D3 — a devserver-site fix-recheck extension method (NOT core `Site`).** The
  core `Site` protocol has no primitive to re-run a repro or query a diff's CI
  signal, so `verify` cannot re-check a fix through the *generic* protocol. The
  `devserver` site adds one **site-specific** method (`recheck_fix`, §2.5) that the
  dexter `verify` calls by duck-typing; when absent the playbook fails safe
  (returns `False` → `needs_human`). This keeps the core protocol untouched
  (DESIGN goal #6: Meta-internal specifics are deploy-time pluggable) and is the
  only capability the engine "lacks."

No other engine method, signature, table, or state is added or changed; everything
below maps onto the engine exactly as built.

---

## 2. The `dexter` playbook

Implements the engine-core `Playbook` protocol.

```
name    = "dexter"
phases  = ["solve"]          # one worker phase; reduce runs after it
```

Single worker phase: `/dexter:solve` already performs the full
investigate → fix → verify → learn loop autonomously (its own definition-of-done),
so Hermes fans it out once per goal and then reduces. `next_phase(run)` returns
`None` after `solve`.

### 2.1 seed(run, site) → list[Ticket]

`seed(run, site)` is called once (phase 0 = `solve`; there is no later phase, so
the `run.reductions`-driven branch other playbooks use does not apply). It yields
one ticket per **goal** (a thing to investigate). Goals come from **either**
source, read from `run.config` (the queue round-trips `run.config` through
`runs.config_json`, so whatever created the run — the `--goals` CLI delta D1, the
control-plane API, or a test — is the source of truth):

- **Explicit list** — `run.config["goals"]`. Accept both shapes: a `list[str]`
  (inline, e.g. from the API) used directly, or a `str` path to a file read with
  the §2.1a format. The CLI delta D1 writes a `list[str]`.
- **issue_source** — if `run.config.get("issue_query")` is set, call
  `site.issue_source(IssueQuery(**run.config["issue_query"]))`; each returned
  `Issue` becomes a goal (`goal = issue.title`, `issue_ref = issue.ref`, priority
  from `issue.data.get("priority", 0)`). `IssueQuery` fields are exactly
  `kind: str, filters: dict={}, limit: int=100` (`engine/models.py`).

Each `Ticket` is constructed with the exact `engine/models.py` fields:
`id=f"{run.id}/solve-{i}"`, `run_id=run.id`, `phase="solve"`, `state="queued"`,
`resource_req="cpu"`, `priority` (float, from the issue else `0.0`), `attempts=0`,
`payload={"goal": <the investigation goal restated as a completion condition,
§2.4>, "issue_ref": <str|null>, "context": <object>}`. There is **no** `goal`
field on `Ticket`; the goal lives in `payload["goal"]`, which
`transport._build_envelope` lifts to `goal_envelope.goal` (it reads
`payload.get("goal")`).

### 2.1a `--goals FILE` format + semantics (delta D1)

`--goals PATH` (new arg on the `run` subparser): read `PATH`, one goal per line;
**skip blank lines and lines whose first non-space char is `#`** (comments);
strip surrounding whitespace. Store the resulting `list[str]` as
`run_config["goals"]`. `cmd_run` builds `run_config` from this (replacing the
hardcoded `{}`) before `_create_run`. Empty/missing file after filtering ⇒ zero
tickets ⇒ the run seeds nothing and terminates `done` immediately (a no-op run),
which is the correct degenerate behavior. `issue_query` has no dedicated CLI flag;
supply it via the control-plane API run-create (which already accepts arbitrary
`config`) or a future optional `--config JSON` flag — not required for D1.

### 2.2 payload_schema("solve")

Validated by `contracts.validate_envelope(envelope, payload_schema)` against
`envelope["payload"]` (= `ticket.payload`) at dispatch time
(`transport.serve_once_for_host`). The contracts validator supports exactly
`type` (incl. union lists like `["string","null"]`), `required`, `properties`,
`additionalProperties:false`, `enum`, `items` — so the schema must stay within
that subset. With `additionalProperties:false`, `seed` must emit **only** these
keys:
```json
{ "type": "object",
  "required": ["goal"],
  "additionalProperties": false,
  "properties": {
    "goal":      {"type": "string"},
    "issue_ref": {"type": ["string", "null"]},
    "context":   {"type": "object"} } }
```

### 2.3 result_schema("solve")  (what `/dexter:solve` must emit)

`result_schema("solve")` is carried into the envelope as
`goal_envelope.done_contract` (`transport._build_envelope`), i.e. it is the
contract handed to the worker. **Important engine reality:** the master does
**not** auto-validate the returned result payload against this schema.
`contracts.validate_result` exists but is called **only in tests** — no dispatch,
queue, or agent code invokes it. `ClaudeAgent.parse_result` maps the worker's
emitted JSON doc to a `Result`, taking `payload = doc["payload"]` on `outcome=="ok"`
with **no** schema check. Therefore the §2.3 shape is enforced by the dexter
`verify` (§2.5), which calls `contracts.validate_result(result_dict,
result_schema("solve"))` and fails a malformed payload to `needs_human`.

The dexter-aware result payload (`Result.payload`, which becomes the `Finding.json`
— see §2.6) that `/dexter:solve` must emit:
```json
{ "type": "object",
  "required": ["reproduced", "root_cause", "fix", "knowledge_entry", "evidence_ref"],
  "additionalProperties": false,
  "properties": {
    "reproduced": {"type": "boolean"},
    "root_cause": {
      "type": "object",
      "required": ["signature", "cause_category"],
      "properties": {
        "signature":      {"type": "string"},
        "culprit_symbol": {"type": ["string", "null"]},
        "cause_category": {"type": "string"},
        "mechanism":      {"type": ["string", "null"]} } },
    "fix": {
      "type": "object",
      "required": ["verified"],
      "properties": {
        "verified":  {"type": "boolean"},
        "diff_ref":  {"type": ["string", "null"]},
        "ci_status": {"type": ["string", "null"]} } },
    "knowledge_entry": {
      "type": "object",
      "properties": {
        "ref":       {"type": ["string", "null"]},
        "validated": {"type": "boolean"} } },
    "evidence_ref": {"type": ["string", "null"]},
    "notes":        {"type": ["string", "null"]} } }
```
`root_cause.signature` is the clustering key in `reduce`; it reuses dexter's own
fingerprint so two hosts that reach the same cause collide deterministically.
(`fix.diff_ref` replaces the earlier `diff_url` name for consistency with the
site's `submit_for_review` return and the cluster schema in §2.6.)

### 2.4 driver("solve") → Driver

```python
Driver(command="/dexter:solve", args={}, loop=None)
```
`args={}` is deliberate. `ClaudeAgent._build_prompt` renders the prompt as
`"/goal <goal>"` + the driver command + any `driver.args` rendered as literal
`k=v` text (sorted). So a non-empty `args` (e.g. `{"goal_from":"ticket"}`) would
inject the meaningless string `goal_from=ticket` after the command
(`/dexter:solve goal_from=ticket`) — **not** the goal. The engine does **not**
substitute the goal into the driver command; the goal reaches the worker only via
the `/goal <goal>` prefix. The rendered prompt is therefore:

```
/goal <goal> /dexter:solve
```

`<goal>` = `goal_envelope.goal`, which `transport._build_envelope` lifts from
`ticket.payload["goal"]` (§2.1). `/dexter:solve` runs and picks up the
investigation goal from the `/goal` context set in the same session.

**Caveat (what actually reaches the worker):** only `payload["goal"]` is rendered
into the prompt. `issue_ref` and `context` ride along in `envelope["payload"]`
(for provenance and the finding) but are **not** shown to `/dexter:solve`. If
issue/site context must steer the investigation, `seed` must fold it into the
`goal` string itself.

The `goal` string doubles as the **completion condition**, mirroring dexter's DoD:
*"a root cause is identified, a fix is published as a diff (not landed), the fix is
verified, and a schema-valid knowledge entry (§2.3) is written."* dexter stops at a
published diff; the guard blocks landing (§7). The invocation runs under
`--permission-mode bypassPermissions` with no `--max-turns`; the wall-clock budget
is `envelope["timeout_s"]` (from `run.config.get("timeout_s", 3600)`) enforced by
the transport's `timeout` wrapper. The worker writes its result doc as JSON to
stdout (which `serve-once` captures to `result.json`); `parse_result` reads the
outer `Result` fields and takes the §2.3 doc as `payload`.

### 2.5 verify(run, ticket, result, site) → bool

**When it runs.** `verify` is called by `queue.record_result` at result-record
time (not during `reduce`), on every `outcome=="ok"` result: `True` →
`ok`-ticket transitions `running → reducing`; `False` → `running → needs_human`
("re-verify override", the only path by which an `ok` result does not reach
`reducing`). The finding row is written by `record_result` **regardless** of the
verify verdict (see §2.6 dedup consequence).

**What it does** (no-trust rule — do not trust `result.payload["fix"]["verified"]`):

1. **Shape gate.** Reconstruct the outer result dict and call
   `contracts.validate_result(result_dict, self.result_schema("solve"))`. A payload
   that violates §2.3 ⇒ return `False` (malformed success claim → `needs_human`).
   This is where the §2.3 contract is actually enforced (§2.3).
2. **Independent fix re-check via the devserver-site extension (delta D3).** The
   core `Site` protocol (`engine/site.py`) exposes no primitive to re-run a repro
   or read a diff's CI signal, so `verify` cannot re-check through the *generic*
   protocol. It instead **duck-types** a devserver-site method
   `recheck_fix(result_payload: dict) -> bool` (§3, D3): host-agnostic — it
   re-queries the published diff's CI signal (`result_payload["fix"]["diff_ref"]`)
   and/or spins the recorded minimal repro on a `discover_hosts()`-chosen box at
   `run.base_ref`, returning whether the fix independently holds. If the site does
   **not** provide `recheck_fix` (e.g. the `local` test site, or a mock), `verify`
   **fails safe**: it returns `False` (never a false pass) unless
   `run.config["verify_recheck_optional"]` is set for tests that want the shape
   gate alone to admit.

Return `True` iff the shape gate passes **and** the fix re-check confirms →
`reducing`; else `False` → `needs_human` (integrity signal: dexter claimed a
success the master could not confirm). Knowledge-entry validity is **not**
re-checked here — the learning is validated only when banked in `reduce` (§2.6, via
the injectable sink), so `verify` needs no dexter tooling on the master and the
master's sole dexter coupling stays the single point in §5.

### 2.6 reduce(run, "solve", findings, site) → list[Reduction]

**When it runs (engine gating).** `dispatch._reduce_and_advance` reduces the
`solve` phase **only** once it is fully settled: zero tickets in
`queued|dispatched|running|parked` **and** zero in `needs_human`. So any
verify-failed `needs_human` ticket (§2.5) blocks the whole phase from reducing
until an operator clears it (§2.7). `reduce` runs exactly once per phase (guarded
by `_phase_reduced`); it is not re-run after human accept/reject.

**Finding shape (engine reality).** `record_result` inserts each `ok` result as a
finding with **`kind="result"`** (hardcoded) and **`json` = the `Result.payload`**
— i.e. `finding.json` *is* the §2.3 dexter doc. `queue.load_findings(run_id,
"solve")` returns them as `Finding(run_id, ticket_id, kind, json)`, ordered by
`findings.id` ascending. The cluster key is `finding.json["root_cause"]["signature"]`.

**Fold to the latest finding per ticket first.** `findings` is append-only and
scoped by phase, so a ticket that returned `ok` twice (e.g. verify-failed →
operator-requeued → re-succeeded) yields **two** findings. Before clustering,
collapse to the **last** finding per `ticket_id` (ascending `id` order means the
last wins). Known edge the protocol cannot fully close: `reduce` receives only
`Finding`s + `run` + `site` (no ticket-state access), so a ticket that returned
`ok` once (finding written) then later went terminal-`failed` still contributes a
stale finding; since every cluster is routed to a human anyway (below), such a
cluster is surfaced for review and can be rejected — it is never silently banked-and-done.

Cross-host synthesis:
1. **Cluster** the folded findings by `root_cause.signature`.
2. For each cluster, pick a **canonical** `ticket_id` (deterministic: lowest
   ticket id — every clustered finding comes from a verified ticket, since
   verify-failed ones are `needs_human` and block reduce, so there is no "best
   signal" to rank on) and list the **duplicates** (the other members with their
   `fix.diff_ref`).
3. **Bank one consolidated learning** per cluster via the injectable **learning
   sink** held on the playbook instance (`self.sink`, §5; default `DexterKbSink`
   → dexter `kb.py` `validate` then `index` against `INVESTIGATIONS_DIR`; tests
   construct the playbook with a `FakeSink`). The sink is **best-effort**: any
   exception is caught and recorded as `learning_ref=null` +
   `learning_error="<msg>"` in the reduction json — `reduce` must **never raise**
   (an uncaught exception in `reduce` would propagate through
   `dispatch._do_reduce` and wedge the master loop). A banking failure still
   surfaces the cluster for human review.
4. Return one **light** `Reduction` per cluster (the queue hydrates `id/run_id/
   phase/review_state`; `record_reduction` INSERTs `review_state='pending'`).
   Note `needs_human_ticket_ids` lives **inside** `reduction.json` —
   `queue.record_reduction` reads `reduction.json.get("needs_human_ticket_ids")`;
   it is **not** a top-level `Reduction` field:
   ```python
   Reduction(
     kind="root_cause_cluster",
     json={
       "signature": "...",
       "cause_category": "...",
       "canonical_ticket_id": "...",
       "canonical_diff_ref": "<str|null>",
       "duplicate_diffs": [{"ticket_id": "...", "diff_ref": "<str|null>"}],
       "member_ticket_ids": ["..."],
       "learning_ref": "<str|null>",
       "learning_error": "<str|null>",
       "needs_human_ticket_ids": ["<all member ticket ids>"] })
   ```
   `record_reduction` routes each id in `needs_human_ticket_ids` that is **still
   `reducing`** to `needs_human` and stamps `tickets.reduction_id` (ids not in
   `reducing` are skipped, so listing all members is safe);
   `finish_phase_reductions` then settles any unflagged `reducing` ticket to
   `done` (dexter flags all members, so none remain). This surfaces the cluster for
   human review; **accept** (`hermes reduction accept <id>`) → the reduction's
   `needs_human` tickets → `done` (human lands the canonical diff out-of-band;
   nothing auto-lands), **reject** → those tickets → `failed`. The engine makes no
   landing choice.

### 2.7 next_phase / is_done

- `next_phase(run)` → `None` always (single phase). The engine treats a `None`
  next phase, on a settled phase, as "either done or stuck."
- `is_done(run)` → `return run.phase == "solve"` (i.e. `True`). Like
  `EchoPlaybook.is_done`, it does **not** itself inspect ticket states: the engine
  only consults `is_done` from `_reduce_and_advance` **after** the phase has fully
  settled to `done`/`failed` (no active, no `needs_human`, no `reducing`). Because
  §2.6 routes members to `needs_human`, this settlement is reached only **after the
  human has accepted/rejected every cluster**; then `is_done` returns `True` and
  the queue transitions the run `running → done`. Learnings are already banked in
  `reduce`. (If `is_done` returned `False` here the engine would mark the run
  `failed` as "stuck", so it must return `True`.)

**Blocking / operator caveat (engine reality).** A verify-failed ticket (§2.5)
enters `needs_human` with **no** `reduction_id` link. The only operator command
that touches such a ticket is `hermes ticket requeue <id>`
(`queue.requeue_needs_human` → back to `queued` for a fresh attempt);
`reduction accept/reject` only settle reduction-linked `needs_human` tickets. There
is **no** engine command to terminally abandon a re-verify `needs_human` ticket, so
the phase stays blocked until that ticket is requeued and eventually reaches
`reducing` or terminal-`failed`. This is an accepted limitation (see §9).

---

## 3. The `devserver` site

Implements the engine-core `Site` protocol with the **exact** `engine/site.py`
signatures. **This is the only Meta-specific component** in this sub-project. It is
a **distinct site**, not `sites/ssh.SSHSite`: `SSHSite.provision` assumes a *baked*
image (it only verifies `hermes` is on PATH) and reports `guard_installed=True`
unconditionally, whereas `devserver` does **real** idempotent provisioning
(checkout + install + guard) and reports the guard honestly. It may reuse
`transport.build_ssh_opts` / `build_scp_opts` for connection options, but does not
inherit `SSHSite`. It keeps to native box tooling (no buck2/testinfra as site
methods).

- `name = "devserver"`.
- `discover_hosts() -> list[str]` — read an internal host list from config; else
  `[]` (hosts supplied via `--hosts`, which `cmd_run` splits and `crew.add`s).
- `provision(host, base_ref) -> None` — over SSH, idempotent: ensure a clean
  checkout at `base_ref` (`sl`/git); ensure `claude` present + authed and the
  `dexter` plugin installed (internal install/symlink); install the **no-ship
  guard** PATH shims into a per-host guard dir on the box — the same shim set as
  `sites/local` (`GUARD_SHIMS`: block `git push`, `sl push|land`, `hg push`,
  `jf land`, `arc land`, exit `97`); ensure dexter's runtime-data dir exists.
  Returns `None`.
- `health(host, agent) -> HealthReport` — construct with the exact
  `engine/models.py` fields: `reachable` (ssh), `agent_ok`/`auth_ok` (pulled from
  `agent.health_checks(host, self)` via the `_find_ok` helper pattern),
  `workspace_ready` (checkout at `base_ref`, clean), `guard_installed` (shims
  actually present — must not lie), `resources={"cpu": <nproc:int>}` (`dict[str,
  int]`), `latency_ms` (`int`), `checks=[site checks] + agent_checks`.
- `run_worker(host, envelope, agent) -> Result` — SSH transport that (a) scp's the
  envelope up, (b) runs `hermes serve-once --envelope … --result … --timeout …`
  over SSH **with the guard dir prepended to the remote `PATH`** (e.g. the ssh
  command exports `PATH=<guarddir>:$PATH` before `serve-once`), so any
  `git push`/land the worker attempts is blocked by construction (mirrors
  `LocalSite.run_worker`'s PATH-prepend; the generic `ssh_transport` does **not**
  set PATH, which is why devserver needs its own). It (c) scp's `result.json` +
  evidence back and returns `agent.parse_result(raw, envelope)`. Connection-level
  failure (ssh exit 255, refused/timeout, failed scp) raises
  `transport.TransportError` → the serve loop does a no-penalty
  `requeue_transport`; a worker that ran and returned a Result passes through.
- `resource_classes() -> list[str]` → `["cpu"]`.
- `guarantees_no_ship() -> bool` → `True` (it installs + verifies the guard).
- `submit_for_review(host, change: dict) -> str` — wraps the box's publish-only
  `jf submit` (never land), returns the review URL. Usually unused (dexter
  self-publishes); provided for completeness.
- `issue_source(query: IssueQuery) -> list[Issue]` — optional: query an internal
  dashboard for investigation targets, mapping rows to `Issue{id, kind, title,
  ref, data}` (`kind` echoes `query.kind`). Honors `query.limit`.

**Extension method beyond the core protocol (delta D3):**
- `recheck_fix(result_payload: dict) -> bool` — the independent fix re-check
  `verify` duck-types (§2.5). Host-agnostic: re-queries the published diff's CI
  signal via the internal tool (`result_payload["fix"]["diff_ref"]`) and/or spins
  the recorded minimal repro on a `discover_hosts()`-chosen box at the run's
  `base_ref`; returns whether the fix independently holds. This is **not** part of
  the core `Site` protocol — it is a devserver-specific capability the playbook
  calls only when present (deploy-time pluggable, DESIGN goal #6).

Meta-isms confined here: SSH to devservers, internal `claude`/`dexter` install,
`sl`/`jf` guards + publish, the dashboard query, the CI/repro re-check. Anything
Meta-internal (host-list source, install recipe, dashboard endpoint, CI-signal
lookup) is a deploy-time-pluggable detail, not hardcoded into the playbook.

---

## 4. Data flow

```
hermes run dexter --site devserver --agent claude \
  --hosts devvm1,devvm2,devvm3 --goals ./goals.txt      (--goals = delta D1)
      │
cmd_run ─▶ run_config["goals"] = parsed goals.txt (D1); crew.add health-gates each host
      │
seed ─┤ one ticket/goal (payload={goal,issue_ref,context}) ──▶ engine queue
      │
serve ─▶ claim ticket, acquire cpu lease, devserver.run_worker over ssh:
           PATH=<guarddir>:$PATH claude -p "/goal <goal> /dexter:solve" \
             --permission-mode bypassPermissions
         ─▶ dexter investigates → publishes diff (no land) → writes result.json (§2.3)
record_result ─▶ writes finding(kind="result", json=payload); calls verify (§2.5):
                   pass ⇒ reducing;  fail ⇒ needs_human (blocks phase reduce)
reduce (phase settled, nh==0) ─▶ fold latest finding/ticket; cluster by
          root_cause.signature; best-effort bank 1 learning/cluster (dexter kb);
          record_reduction ⇒ cluster reductions (pending) + route members to needs_human
review ─▶ human accept/reject each cluster (hermes reduction accept|reject / control plane)
done  ─▶ phase settled (done/failed only); is_done ⇒ run done; learnings banked
```

---

## 5. Learning-sink coupling (master side)

`reduce` banks via a `LearningSink` interface with one method
`bank(cluster: dict) -> str | None` (returns the learning ref, or `None` on a
handled failure). Default `DexterKbSink` shells to the dexter plugin's `kb.py`
(`validate` then `index`) against `INVESTIGATIONS_DIR`.

**Injection (engine reality).** `reduce(run, phase, findings, site)` has no sink
parameter and no db handle, so the sink is a **constructor arg on the playbook
instance**, exactly like `MockAgent(scenarios=…)`: `DexterPlaybook(sink=None)`
defaults to `DexterKbSink()`. The module registers the default singleton
(`playbook.register("dexter", DexterPlaybook())`, resolved by
`_load_playbook_site_agent` via the D2 import); tests construct
`DexterPlaybook(sink=FakeSink())` and either register that instance or call
`reduce` on it directly. This is the single point where the dexter playbook touches
dexter tooling on the master; the `FakeSink` keeps `reduce` fully unit-testable
without dexter installed. Banking is best-effort (§2.6): the sink never raises out
of `reduce`.

---

## 6. Testing (no Meta / no real dexter)

Two test-double realities constrain how the flow is exercised without Meta/dexter,
and the spec must build to them:

- The stock testkit `MockAgent` **echoes `envelope["payload"]`** as the `ok`
  result payload and its scenario table maps only to `(outcome,
  termination_reason)` — it cannot emit an arbitrary §2.3 doc, and the ticket
  payload is `payload_schema`-constrained to `{goal, issue_ref, context}` (§2.2).
  So the integration test supplies a thin **`DexterMockAgent`** (in the dexter
  sub-project's tests; still no real `claude`, SSH, or Meta) whose `parse_result`
  returns a **§2.3-shaped payload** selected per ticket/goal from a scenario map,
  decoupled from the schema-constrained ticket payload.
- The `local` site has **no** `recheck_fix` (delta D3), so `verify`'s fix re-check
  fails safe (§2.5). To drive both branches, the test uses a `local`-site subclass
  (`DexterLocalSite`) that adds `recheck_fix(payload) -> bool` returning the
  per-scenario verdict — so a "fix holds" goal reaches `reducing` and a "fix does
  not hold" goal routes to `needs_human` — all on localhost.

- **Unit** — `seed` from both a `run.config["goals"]` list, a goals-file path
  (§2.1a: comment/blank filtering), and a mocked `issue_source`; `payload_schema`
  accept/reject (extra key rejected by `additionalProperties:false`);
  `result_schema` accept/reject via `contracts.validate_result`; `driver` shape
  (`command="/dexter:solve"`, `args={}`) and the rendered prompt
  `"/goal <goal> /dexter:solve"`; `reduce` clustering by `root_cause.signature`
  incl. the **fold-latest-per-ticket** dedup (a ticket with two `ok` findings
  counted once) and the canonical/duplicate split, with a `FakeSink`; the
  best-effort sink path (sink raises → `learning_ref=null` + `learning_error`, no
  exception out of `reduce`); `verify` shape-gate + `recheck_fix` true/false/absent
  (fail-safe) paths; `is_done` → `True`; `devserver` command construction +
  `HealthReport` field parsing + the guard-on-PATH prepend (subprocess mocked).
- **Integration** — full flow on **`DexterLocalSite` + `DexterMockAgent`** via
  `master_loop`, including **two goals sharing a `root_cause.signature`** →
  clustering yields **one** cluster reduction (canonical + one duplicate), both
  members routed to `needs_human`; then `hermes reduction accept` → members `done`
  (and a separate reject run → members `failed`). Assert: `FakeSink` banked exactly
  **one** learning per cluster; a "fix-does-not-hold" goal (verify-fail) lands in
  `needs_human` and **blocks reduce** until `hermes ticket requeue` clears it; the
  event stream (`ticket_claimed`, `result_recorded`, `needs_human`,
  `reduction_created`, `reduction_accepted`/`ticket_failed`, `run_done`); and that
  no-ship holds (a worker `git push`/land attempt is blocked by the guard shim).
- Runs via the engine's `scripts/run_tests.sh`; zero external dependencies.

---

## 7. Safety

Inherits the engine invariant transitively along two enforcement layers:

1. **Dispatch-time gate.** `transport._build_envelope` always sets
   `guardrails.no_ship=true` and raises if `site.guarantees_no_ship()` is `False`;
   `serve_once_for_host` maps that to `queue.fail_contract_violation` (terminal
   `failed`, `contract_fail`, no retry). `devserver.guarantees_no_ship()` returns
   `True` only because it installs + verifies the guard, so dispatch proceeds.
2. **Runtime guard.** The worker runs with the guard dir prepended to `PATH`
   (§3), so the shims shadow `git push` / `sl push|land` / `hg push` / `jf land` /
   `arc land` and refuse with exit `97`; dexter runs under `bypassPermissions` with
   no `--max-turns` but **cannot land** (guard + submit-only). `LocalSite.run_worker`
   even self-defends (re-installs or refuses to run unguarded); `devserver`
   mirrors this posture.

`reduce` **never lands** — it only clusters, banks learnings, and flags diffs; a
human lands the canonical diff out-of-band after accepting a cluster. `verify`
re-checks every `ok` result independently (§2.5), failing safe to `needs_human`
when it cannot confirm — so an unverifiable success is never silently admitted.

---

## 8. Acceptance criteria

1. `hermes run dexter --site devserver --hosts … --goals FILE` (deltas D1+D2)
   parses `FILE` into `run.config["goals"]`, seeds one `solve` ticket per goal,
   renders `"/goal <goal> /dexter:solve"` per host, and drives to a terminal run
   with learnings banked.
2. Two hosts with the same `root_cause.signature` collapse into **one** cluster
   reduction (canonical + duplicate), with exactly **one** banked learning; a
   ticket that produced two `ok` findings is counted **once** (fold dedup, §2.6).
3. A worker whose fix fails independent `verify` (shape gate or `recheck_fix`, or
   `recheck_fix` absent → fail-safe) is routed to `needs_human`, blocks the phase
   reduce, and is cleared only by `hermes ticket requeue` — never silently accepted.
4. No-ship holds on both layers (§7): a site that cannot guarantee no-ship is
   rejected at dispatch (`contract_fail`); an attempted land on a guarded worker is
   blocked (exit `97`); `reduce` lands nothing.
5. The entire flow is exercised by `run_tests.sh` on `DexterLocalSite` +
   `DexterMockAgent` (§6) with no dexter/devserver/Meta dependency.

---

## 9. Open items (non-blocking)

- **No terminal-abandon for a re-verify `needs_human` ticket (engine gap).** A
  verify-failed ticket can only be `hermes ticket requeue`d (→ `queued`); there is
  no command to give up on it and let the phase settle. A goal whose fix never
  re-verifies keeps the run blocked. If this bites, the engine (not this playbook)
  would need a `ticket abandon <id>` → terminal `failed` transition. Out of scope
  here; noted so the operator understands the block (§2.7).
- **Stale finding on ok-then-failed tickets (protocol limit).** `reduce` gets no
  ticket-state access, so a ticket that returned `ok` once (finding written) then
  went terminal-`failed` still contributes a folded finding to a cluster (§2.6).
  Mitigated by the mandatory human review of every cluster (reject drops it); a
  clean fix would need the engine to pass ticket state (or filter stale findings)
  into `reduce`.
- **Promoting `recheck_fix` to the core `Site` protocol.** D3 is currently a
  devserver-only duck-typed method. If more playbooks need independent re-verify,
  a generic `Site.recheck`/`run_check` primitive could be added to
  `engine/site.py` — a deliberate engine change, deferred.
- Per-ticket land granularity: accept/reject applies to a whole cluster (engine
  semantics). If humans need "land canonical, discard duplicates" as distinct
  ticket outcomes, that's a control-plane/UI concern, not an engine state — revisit
  if needed.
- `issue_source` schema for the internal dashboard; a `--config JSON` CLI flag for
  `issue_query` (deferred; §2.1a) — both deferred to the `devserver` site build.
- Whether `sites/devserver` and a future `sites/meta` should share a `_meta_common`
  module now or later (both need SSH + guard + install primitives).
