# Hermes federation — spec (FUTURE EXTENSION)

Status: **future extension — NOT built now.** Date: 2026-07-28.
Parent: `docs/DESIGN.md`.

Hermes ships **flat**: one root Hermes owns a `queue.db`, musters a `crew` of
hosts, and dispatches `tickets`. This document specs an optional **federation**
layer for later, so today's design can adopt a few cheap seams (see "Federation-ready seams to adopt NOW") that keep the
door open without paying any distributed-systems cost now.

The rule for adopting this: **don't build it until a concrete trigger appears**
(see "When to reach for it"). When one does, this is the design.

---

## 1. What federation is

A **tree of Hermes nodes**. A **deputy** Hermes runs its own tickets against its
own `crew` and streams results/status upward; a **parent** Hermes mirrors those
streams and renders one view across the nodes that report to it. A parent does
**not** assign work — shard routing, the delegation ledger, reclaim and fencing
are cut (see "Work assignment" and "Failure & reassignment"). A deputy is itself
a full Hermes, so the structure could nest, but depth is **capped at 2** (root →
deputy → crew; see "Multi-level specifics & depth cap"). Nothing about a node
changes with depth; only its position does.

```
                 hermes (root)                  ← mirrors each deputy, one view
                /            \
        deputy hermes      deputy hermes        ← each owns its own crew
              |                  |
            crew               crew             ← depth capped at 2
```

A deputy is the recursion of the same engine: **"a lieutenant is just a Hermes"**
— same queue/dispatch/lease/health/reduce machinery, one level up.

## 2. When to reach for it (triggers)

Build federation only when the flat model actually strains. Each trigger below is
an **observation, not a judgment call** by whoever owns this proposal — but they
are observed in two different ways. The scale triggers are **thresholds `hermes
status` reports** (threshold values are defaults to calibrate against a real
run); the reachability trigger is a **predicate discovered at bootstrap**, not
measured, and needs no instrument and no baseline. Each names who observes it and
says the gate is open.

- **Scale beyond one root** — any one of, sustained across a full run:
  - concurrent SSH sessions from the root at the fan-out cap (default 256) for
    >20% of dispatch wall-clock;
  - `queue.db` write-lock wait >10% of dispatch wall-clock (single-writer
    contention);
  - root CPU ≥90% during `reduce`/`verify`, or tickets parked on the concurrency
    cap for >20% of run wall-clock.

  *Declared by*: the on-call for the root deployment.

- **Geography / network / credential domains** — any one of:
  - **Reachability — a predicate, not a threshold**: *there exists a crew the
    root cannot admit because it holds no credentials for that zone* (admission
    fails on credentials, not on host health). This half is a boolean and fires
    the first time it is true: no host count, no counter, no baseline, no
    quarter of data, and no declarer judgment. Reachability is not measured, it
    is **discovered** — by whoever attempts the bootstrap and is refused.
  - median dispatch round-trip from the root to a crew segment >250ms;
  - a cross-zone partition severing the root from a crew segment for >5 minutes,
    more than once a week.

  A deputy local to each zone dispatches with low latency, keeps SSH in-zone,
  holds that zone's credentials, and survives cross-zone partitions.

  *Declared by*: for the two measured conditions, the owner of the
  network/credential zone in question — not the root's operator, who by
  construction cannot see into it. The reachability predicate needs no declarer;
  the refused bootstrap is the observation.

If none of these hold (e.g. a few hundred tickets from one devserver + a handful
of hosts), the flat model is correct and federation is over-engineering.

**Preconditions on building, once a trigger has fired.** A fired trigger opens
the gate; it does not start the build. Both of these are conditions on starting,
not discoveries to be made during:

- **No deputy without an owning rotation.** Under the alerting rule in "Status &
  events roll-up", a node's attention pages its own owner, so every team that
  runs a deputy inherits a permanent on-call obligation. A deputy is not
  provisioned for a team that has not agreed to carry its pager.
- **No build without a named permanent rotation for the federated surface.** Not
  merely two named engineers for the build itself — a rotation that owns this
  surface after it ships. If nobody will sign that line when the trigger fires,
  the right answer at that point is to drop federation, not to build it.

## 3. Terminology

- **Root Hermes** — the top node; the one a human starts a run on.
- **Deputy Hermes** — a node that runs its own tickets and reports upward to a
  parent; itself a full Hermes. Depth is capped at 2, so a deputy owns crew, not
  deputies.
- **Correlation label** — the operator-supplied string marking the nodes an
  operator intends to read as one logical run. Unauthoritative; see "Status &
  events roll-up".
- **crew**, **ticket**, **playbook**, **reduction** — unchanged from the flat
  design.

## 4. Node link (decided: reuse the control-plane API)

A parent reads a deputy over the **sub-project-3 control-plane HTTP API** — the
same JSON + websocket API the web UI uses. **The parent is an API client of each
deputy.** No separate inter-node protocol is invented.

- **Push — cut.** A parent does not submit work to a deputy. The "submit ticket
  batch into a run" endpoint this required does not exist, is not in the
  sub-project-3 scope, and is no longer specified here; it went with the
  delegation half (see "Work assignment").
- **Pull**: parent consumes the deputy's `events since(cursor)` stream (websocket
  or polling) to mirror status/findings upward; and reads the deputy's
  `HealthReport` for liveness.
- **Auth**: the bearer-token model (loopback-bind default; token at
  `$HERMES_HOME/api_token`) extends to **parent↔deputy**: the deputy is bound to
  its zone-reachable interface (not loopback), and the parent holds the deputy's
  token. Cross-node auth inherits the same rotation semantics (`--rotate-token`
  invalidates in-flight parent sessions, which reconnect). Non-loopback binding
  carries the same trusted-network/proxy caveat already noted in the "Control plane & status" section of DESIGN.
- **Deputies are not provisioned by the root.** The SSH bootstrap this section
  used to specify (install Hermes on the deputy host, start `hermes serve --api`)
  does not survive its own trigger: the reachability trigger is *there exists a
  crew the root cannot SSH to*, and a root that cannot reach the crew cannot
  reach the box the deputy would run on either. A deputy is stood up **out of
  band by the team that owns its hosts** — which is what running Hermes at all
  already means — and is then registered with the parent (endpoint + token) in
  `nodes`. The direction reverses: nodes register, they are not installed.

## 5. Work assignment (sharding & routing) — CUT

Removed with the delegation half; the section number is kept so references into
this document still land. A parent does not route tickets to deputies, deputies
do not advertise capabilities, and there is no delegation ledger. What was here —
capability advertisement (resource classes, zone), `resource_req`/zone-affinity
routing with load balancing, and the ledger recording which tickets went to which
deputy — is not part of this spec. Handing work across an ownership boundary is
its own proposal and needs a named team that wants to be handed work.

## 6. Reduce model (decided: global roll-up + optional pre-reduce)

Each node runs its **own** run; with assignment cut there is no single run
spanning the tree. The root can reduce across nodes only where they share a
playbook and cover disjoint crews — a `reduce` is playbook-defined. Where that
does not hold, what the root produces is one *view* of the nodes that reported,
not one answer (see the completeness bound in "Status & events roll-up").

- **Default — global roll-up**: deputies stream **raw findings** upward; the
  **root runs the single authoritative `reduce`** across all findings. Safe with
  no assumption about the playbook.
- **Opt-in — associative pre-reduce**: a playbook whose `reduce` is
  associative/composable may set `reduce_associative = True`; deputies then
  pre-reduce their own findings locally and stream **reductions** (not raw)
  upward, and the root reduces over those. Cuts upstream data and parallelizes the
  reduce, but is only correct when `reduce` is associative — the engine trusts the
  playbook's flag and documents the contract.
- `verify` (master re-verify) runs at the node that owns the crew member that
  produced the result (the deputy). Whether it is **re-checkable at the root** is
  not something this spec can assert: it depends on an unstated, playbook-
  dependent property of `verify` — see "Safety: no-ship transitivity".

## 7. Lease / resource model (decided: local pools + opt-in global semaphore)

- **Default — local disjoint pools**: each deputy owns its own resource pool
  (capacity = Σ its crew's `resources_json[class]`, exactly as flat). Correct when
  resources are physically partitioned per deputy/zone. No cross-node lease
  coordination — no round-trips, no shared state.
- **Opt-in — parent-held global semaphore**: a genuinely shared scarce pool (e.g.
  one global RE/GPU quota) is modeled as a **parent-held semaphore** that deputies
  request grants from over the API before dispatching against that class. Only the
  classes declared "global" pay the round-trip; everything else stays local. A
  grant is a lease (TTL 1800s, renewed on the parent heartbeat, reclaimed on
  deputy loss) — the flat lease mechanics, delegated.

## 8. Failure & reassignment — CUT

Removed with the delegation half; the section number is kept so references into
this document still land. A parent that assigns nothing has nothing to reclaim:
no grace window (`HERMES_DEPUTY_GRACE_S` is gone), no reassignment of a shard's
non-terminal tickets, no fencing epoch, no revive-and-drop dance.

What survives is liveness only: the parent probes each deputy's health on its
heartbeat sweep (over the API) and marks an unreachable deputy `down` in `nodes`.
That is a fact rendered in the view, not a recovery action. A deputy's own crew
failures are handled by the deputy, exactly as in the flat engine, because the
deputy owns its own `queue.db`.

## 9. Status & events roll-up

The parent mirrors each deputy's `events since(cursor)` into its own `events`
table, tagged with the deputy's node id (and a node path for depth). `hermes
status` and the SPA render a **tree**: per-node crew/ticket/lease rollups with
drill-down into any subtree.

**What correlates the tree, and the bound on it.** Nodes are grouped by an
**operator-supplied correlation label**: whoever runs the nodes marks the ones
they intend to read as one logical run. Nothing mints that label
authoritatively — it can collide or be mistyped — and there is deliberately **no
manifest of expected nodes**: a manifest is a membership record the parent would
have to write into and reconcile, which is the delegation half returning through
a side door. So the bound is stated in the product rather than hidden in it:
**the view shows the nodes that reported, and claims nothing about the ones that
did not.** A node that was never started, or never labelled, is absent — not
green. Completeness is not offered here; anything that needs it is a separate
proposal.

Attention conditions (parked ratio, all-crew-down, no-progress) are **displayed**
up the tree but do **not** page up it. The rule is: **a node's attention pages its
own owner, and the root pages only on root-actionable conditions** — a deputy
unreachable past its heartbeat timeout, and global no-progress. (The third
condition here, "a shard with no capable deputy to reassign it to", went with
the delegation half: the root reassigns nothing.) Descendant attention is
visible on drill-down and is never a page at the root.

The transitive rule this replaces — "a node is in attention if it or any
descendant is" — is the noise generator: one parked ticket at depth 2 lights the
root, and it wakes the root's rotation for failures only the deputy's team can
clear.

## 10. Safety: no-ship transitivity

The no-ship invariant is **per-Hermes**, so it holds at **every level
automatically**: every leaf worker runs under its owning node's site guard
(`guarantees_no_ship` + `guard_installed` health gate), regardless of how deep the
tree is. A deputy enforces no-ship on its crew exactly as the root does.

**The parent's re-verify claim is unsupported, and the `verify` contract is
unstated.** This section used to say a parent never needs to trust a deputy's
guard because it re-verifies (`verify`) the results it rolls up. That holds only
if `verify` is **payload-checkable** — the finding carries enough for the root to
re-derive the verdict. If `verify` is **host-checkable** — it goes back and looks
at the machine — then a root that cannot reach the deputy's crew cannot
re-verify anything, and the claim degrades into trusting the deputy's guard,
which is exactly what it promises we never do. Which of the two it is, is
**playbook-dependent, and nothing in the flat design states it**: today one node
owns the hosts, re-verification is always available, and the distinction has
never had to exist. Two consequences:

- It is a property of `verify` that belongs in `DESIGN.md`, not only here — it
  bites any time results cross an ownership boundary, including a human merging
  two runs by hand.
- It is a **precondition**: nothing reduces across an ownership boundary until
  the contract is written down. For host-checkable playbooks the root gets one
  view, not one answer.

## 11. Multi-level specifics & depth cap

Depth is unbounded by construction (recursion of one protocol), but **capped at 2
(root → deputy → crew)**, validated at node registration. The cap is a **fixed
ceiling in this spec, not a configurable default**: there is no
`HERMES_MAX_DEPTH` knob. Debugging a depth-3 tree means three `queue.db`s, three
zones, three credential sets and three logins before anyone sees the ticket that
failed — and the first person to hit a real problem should not also be the first
person to exercise a depth nobody tested. Federation is primarily about
**breadth** (many deputies); depth past 2, for genuine hierarchy of zones
(region → zone → rack), is out of scope here and needs its own justification.

## 12. Data-model additions (deferred — added only when federation is built)

Additive, per-node (no shared DB; the flat invariant is preserved):

- `nodes` — registered deputies: id, parent-relative endpoint URL, token ref,
  zone, state (idle/busy/down/draining), health_json, last_heartbeat,
  event_cursor, and the operator-supplied correlation label (see "Status &
  events roll-up").

That is the whole data-model cost: **one table**. `capabilities` is gone with
capability advertisement; the `delegations` ledger and the `tickets.origin`
marker are gone with the delegation half — nothing is handed out, so nothing
records what was handed out, and no ticket is parent-delegated.

The root and every deputy keep their **own** `queue.db` under their own
`HERMES_HOME` — federation never introduces a shared database or peer-to-peer
state, so the flat design's core invariant survives.

## 13. Interaction with the recursion (driver-as-Hermes) note

Distinct from cross-node federation, a *single ticket* can also become a
sub-run when its `driver` runs `hermes run` locally (a worker that decomposes its
task into its own run). That "recursion" flavor and this "federation" flavor
compose but are separate: federation aggregates independent runs on separate
nodes into one view; recursion turns one ticket into a nested run. Both rely on the same
seam (see "Federation-ready seams to adopt NOW"): a Hermes node is reachable/usable exactly like the engine itself.

## 14. Federation-ready seams to adopt NOW (cheap; keep the door open)

These cost a note today and avoid a rewrite later. Adopt them in the flat build:

1. **Keep the control-plane API's event stream usable as the north-bound
   roll-up feed.** `events since(cursor)` is already sub-project-3 read
   surface with a named UI consumer, so the seam is an *invariant* on it, not
   work: **the cursor is monotonic, and events are not pruned within a run.** A
   UI can survive a gap in a scrollback feed; a parent mirroring a deputy's state
   upward cannot. Write it down and a future parent can be a plain API client.

   *Batch-submit of externally-created tickets was listed here and is not a
   seam.* It is not in the sub-project-3 scope — the SPA never creates tickets,
   the playbook seeds them — so "already needed by the UI" was false for it. And
   it prevents no rewrite: `POST /api/runs/{id}/tickets` is a thin endpoint over
   the ticket-creation callable the engine already has for seeding. It has now
   gone entirely, along with the delegation half it existed to serve (see "Work
   assignment"). **Correction to DESIGN, recorded here:** the federation-seam
   bullet in DESIGN's "Control plane & status" section drops "submit a batch of
   externally-created tickets into a run" and the "both already needed by the
   UI" claim attached to it. Sub-project 3 has no ticket-creation endpoint, so
   the claim was false there as it was here. What the seam records is `events
   since(cursor)` alone, on the invariant above.
2. **Keep `driver.command` opaque enough that `hermes run` can be a driver.**
   Already true in the flat `Driver`/`/goal` model; just reserve that a ticket's
   result may summarize a nested run.
3. **Per-node `HERMES_HOME` / own `queue.db`, no shared state.** Already the flat
   invariant — do not add any cross-process shared DB, so federation stays additive.
4. **Make `verify` and the no-ship guard strictly per-node** (already the case) so
   transitivity is automatic.

Nothing else in the flat engine changes for federation.

## 15. Explicitly NOT built now / open questions

- **Not built now** (deferred until a trigger appears; see "When to reach for
  it"): the `nodes` table, the parent-as-API-client read loop,
  global-semaphore grants, tree status roll-up.
- **Cut, not deferred**: capability advertisement and shard routing, the
  `delegations` ledger, grace-window reassignment and the fencing epoch, the
  shard-submit endpoint, and SSH provisioning of deputies (see "Work
  assignment", "Failure & reassignment", "Node link").
- Open when built: cross-node clock skew handling for heartbeats/leases;
  whether the SPA renders one federated tree or per-node views with a switcher.
