# Hermes `dexter` playbook + `devserver` site — spec

Status: **draft**. Date: 2026-07-28. Parent: `docs/DESIGN.md`.
Depends on: engine-core (`docs/specs/engine-core.md`).

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
  `reduce` (cluster + bank), independent `verify`, and definition-of-done.
- `sites/devserver/` — a `Site` (§8 of engine-core): SSH reach + idempotent
  provision (checkout, ensure `claude`+`dexter` installed, install no-ship guard),
  structured health, SSH transport, `cpu` resource class, `guarantees_no_ship`,
  optional `issue_source`.
- Tests (unit + integration) that run the whole flow on the **`local` site + a
  `MockAgent`** emitting dexter-shaped results — no real dexter, devservers, SSH,
  or Meta needed.

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

One ticket per **goal** (a thing to investigate). Goals come from **either**
source, per `run.config`:

- **Explicit list** — `run.config.goals` is an inline list or a path to a file
  with one goal per line.
- **issue_source** — if `run.config.issue_query` is set, call
  `site.issue_source(IssueQuery(**issue_query))`; each returned `Issue` becomes a
  goal (`goal = issue.title`, `issue_ref = issue.ref`, priority from `issue.data`).

Each `Ticket`: `phase="solve"`, `resource_req="cpu"`, `goal=<the investigation
goal, restated as a completion condition, §2.4>`, `payload={goal, issue_ref,
context}`, `priority` from the issue (default 0).

### 2.2 payload_schema("solve")

`additionalProperties:false`:
```json
{ "goal": "<string, required>",
  "issue_ref": "<string|null>",
  "context": "<object, optional site/issue extras>" }
```

### 2.3 result_schema("solve")  (what `/dexter:solve` must emit)

The dexter-aware result the worker writes (validated when `outcome=="ok"`):
```json
{ "reproduced": true,
  "root_cause": {
    "signature": "<string, dexter fingerprint — the dedup key>",
    "culprit_symbol": "file:symbol",
    "cause_category": "<one of dexter's fixed cause enum>",
    "mechanism": "<string|null>" },
  "fix": { "verified": true, "diff_url": "<string|null>", "ci_status": "<string|null>" },
  "knowledge_entry": { "ref": "<path/id or paste of the banked kb entry>",
                       "validated": true },
  "evidence_ref": "<durable ref: testrun URL / paste>",
  "notes": "<string|null>" }
```
`root_cause.signature` is the clustering key in `reduce`; it reuses dexter's own
fingerprint so two hosts that reach the same cause collide deterministically.

### 2.4 driver("solve") → Driver

```python
Driver(command="/dexter:solve", args={"goal_from": "ticket"})
```
The engine composes the per-ticket `goal` (from the ticket) with this driver into
the GoalEnvelope; the `claude` agent renders one headless session that (a) sets the
**completion condition** via `/goal`, (b) runs **`/dexter:solve <goal>`**, and
(c) writes the result doc (§2.3) to the result path. The completion condition
mirrors dexter's DoD: *"a root cause is identified, a fix is published as a diff
(not landed), the fix is verified, and a schema-valid knowledge entry is written —
for `<goal>`."* dexter stops at a published diff; the guard blocks landing (§7).

### 2.5 verify(run, ticket, result, site) → bool

Independent master-side re-verify (no-trust rule): do **not** trust
`result.fix.verified`. Confirm at least one of, through the site/box:
- the published diff's CI signal is green (`ci_status`/a signal re-query), **or**
- re-running the minimal repro dexter recorded now passes, **and**
- the knowledge entry passes `kb.py validate`.

Return `True` iff independently confirmed → ticket admitted to `reducing`;
`False` → ticket routed to `needs_human` (integrity signal: dexter claimed success
the master could not confirm).

### 2.6 reduce(run, "solve", findings, site) → list[Reduction]

Cross-host synthesis:
1. **Cluster** findings by `root_cause.signature`.
2. For each cluster, choose a **canonical** ticket (verified fix with the best
   signal; ties → lowest ticket id) and list the **duplicates** (other members
   with their diffs).
3. **Bank one consolidated learning** per cluster into dexter's cross-investigation
   knowledge base via an injectable **learning sink** (default: dexter `kb.py`
   `validate` → `index` against `INVESTIGATIONS_DIR`; tests inject a fake sink).
   Store the returned learning ref.
4. Emit one `Reduction` per cluster:
   ```json
   { "kind": "root_cause_cluster",
     "json": { "signature": "...", "cause_category": "...",
               "canonical_ticket_id": "...", "canonical_diff": "...",
               "duplicate_diffs": [{"ticket_id":"...","diff":"..."}],
               "member_ticket_ids": ["..."], "learning_ref": "..." },
     "review_state": "pending",
     "needs_human_ticket_ids": ["<all member ticket ids>"] }
   ```
   Routing all members to `needs_human` (per engine-core §5/§10) surfaces the
   cluster for human review; **accept** → members `done` (human lands the canonical
   diff out-of-band; nothing auto-lands), **reject** → members `failed`. This is
   the agreed "cluster + flag duplicates for human review" behavior — the engine
   makes no landing choice.

### 2.7 next_phase / is_done

- `next_phase(run)` → `None` (single phase).
- `is_done(run)` → every `solve` ticket is terminal (`done`/`failed`) — which,
  given §2.6 routes members to `needs_human`, means **the human has reviewed every
  cluster** (accepted/rejected). Learnings are already banked in `reduce`.

---

## 3. The `devserver` site

Implements the engine-core `Site` protocol. **This is the only Meta-specific
component** in this sub-project; it shares low-level primitives with `sites/meta`
(a common helper module) but omits buck2/testinfra since dexter uses native
tooling on the box.

- `name = "devserver"`.
- `discover_hosts()` → optional: read an internal host list from config; else `[]`
  (hosts supplied via `--hosts`).
- `provision(host, base_ref)` — over SSH, idempotent: ensure a clean checkout at
  `base_ref` (`sl`/git); ensure `claude` present + authed and the `dexter` plugin
  installed (internal install/symlink); install the **no-ship guard** PATH shims
  (shadow `sl/jf/arc/hg` land + `git push`, ported `land_guard`); ensure dexter's
  runtime-data dir exists.
- `health(host, agent)` → `HealthReport`: `reachable` (ssh), `workspace_ready`
  (checkout at `base_ref`, clean), `guard_installed`, `resources={"cpu": nproc}`,
  `latency_ms`, merged with `agent.health_checks` (`agent_ok`/`auth_ok`).
- `run_worker(host, envelope, agent)` — `ssh_transport`: ship envelope, run
  `agent.build_invocation(...)` over SSH, pull `result.json` + evidence back.
- `resource_classes()` → `["cpu"]`.
- `guarantees_no_ship()` → `True`.
- `submit_for_review(host, change)` — wraps the box's publish-only `jf submit`
  (never land), returns the review URL. Usually unused (dexter self-publishes);
  provided for completeness.
- `issue_source(query)` — optional: query an internal dashboard for investigation
  targets, mapping rows to `Issue{id,kind,title,ref,data}`.

Meta-isms confined here: SSH to devservers, internal `claude`/`dexter` install,
`sl`/`jf` guards + publish, the dashboard query.

---

## 4. Data flow

```
hermes run dexter --site devserver --agent claude \
  --hosts devvm1,devvm2,devvm3 --goals ./goals.txt
      │
seed ─┤ one ticket/goal ──▶ engine queue
      │
dispatch ─▶ devserver.provision + health-gate each host
         ─▶ claim ticket, lease cpu, ssh run:
              claude -p "/goal <DoD> … /dexter:solve <goal>" --permission-mode bypassPermissions
         ─▶ dexter investigates → publishes diff (no land) → writes result.json
verify ─▶ master independently re-checks the fix (§2.5); fail ⇒ needs_human
reduce ─▶ cluster by root_cause.signature; bank 1 learning/cluster (dexter kb);
          emit cluster reductions (pending) + route members to needs_human
review ─▶ human accepts/rejects each cluster in the control plane (§control-plane)
done  ─▶ every ticket terminal; learnings banked; humans reviewed all clusters
```

---

## 5. Learning-sink coupling (master side)

`reduce` banks via a `LearningSink` interface with one method
`bank(cluster) -> ref`. Default `DexterKbSink` shells to the dexter plugin's
`kb.py` (`validate` then `index`) against `INVESTIGATIONS_DIR`. This is the single
point where the dexter playbook touches dexter tooling on the master; injecting a
`FakeSink` keeps `reduce` fully unit-testable without dexter installed.

---

## 6. Testing (no Meta / no real dexter)

- **Unit** — `seed` from both a goals file and a mocked `issue_source`;
  `payload_schema`/`result_schema` accept/reject; `driver` shape; `reduce`
  clustering by signature (incl. the duplicate/canonical split) with a `FakeSink`;
  `verify` true/false paths; `is_done` gating on `needs_human` resolution;
  `devserver` site command construction + `HealthReport` parsing (subprocess
  mocked).
- **Integration** — full flow on the **`local` site + `MockAgent`** whose scenario
  table emits dexter-shaped results (§2.3), including **two tickets sharing a
  `root_cause.signature`** to exercise clustering → one cluster reduction with a
  canonical + one duplicate, both members routed to `needs_human`; then drive the
  control-plane accept path → members `done`, and a reject path → members `failed`.
  Assert the `FakeSink` banked exactly one learning per cluster, the event stream,
  and that a `verify=False` result routes to `needs_human`.
- Runs via the engine's `scripts/run_tests.sh`; zero external dependencies.

---

## 7. Safety

Inherits the engine invariant transitively: the `devserver` site installs the
no-ship guard and `guarantees_no_ship()=True`; dexter runs under `bypassPermissions`
but cannot land (guard + submit-only). `reduce` **never lands** — it only clusters,
banks learnings, and flags diffs; a human lands the canonical diff after accepting a
cluster. `verify` re-checks every `ok` result independently (§2.5).

---

## 8. Acceptance criteria

1. `hermes run dexter --site devserver --hosts … --goals …` seeds one ticket per
   goal, runs `/dexter:solve` per host, and drives to a terminal run with learnings
   banked.
2. Two hosts with the same `root_cause.signature` collapse into **one** cluster
   reduction (canonical + duplicate), with exactly **one** banked learning.
3. A worker whose fix fails independent `verify` is routed to `needs_human`, not
   silently accepted.
4. No-ship holds: an attempted land on a worker is blocked; `reduce` lands nothing.
5. The entire flow is exercised by `run_tests.sh` on the `local` site + `MockAgent`
   with no dexter/devserver/Meta dependency.

---

## 9. Open items (non-blocking)

- Per-ticket land granularity: accept/reject applies to a whole cluster (engine
  semantics). If humans need "land canonical, discard duplicates" as distinct
  ticket outcomes, that's a control-plane/UI concern, not an engine state — revisit
  if needed.
- `issue_source` schema for the internal dashboard (deferred to the `devserver`
  site build).
- Whether `sites/devserver` and `sites/meta` should share a `_meta_common` module
  now or later (both need SSH + guard + install primitives).
