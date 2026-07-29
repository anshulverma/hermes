# Hermes fleet integration harness (Docker) — spec

Status: **draft**. Date: 2026-07-28. Parent: `docs/DESIGN.md` §12.
Depends on: engine-core (`ssh_transport`, crew, leases, dispatch, events).

A development + CI integration harness that stands up **several worker nodes as
Docker containers** and drives them, over real SSH, through **one shared run** — a
deterministic **fake scenario** — until the fleet converges. It is the realistic
multi-node tier of the test pyramid, above the single-box `local` + `MockAgent`
tier.

## 1. Why (what the single-box tier can't test)

`local` site + `MockAgent` runs everything in one process on localhost, so it never
exercises the distributed machinery. The Docker fleet does, with **zero Meta / no
real agent / no cloud**:

- the **real `ssh_transport`** (ship envelope, run worker over SSH, pull result),
- **multi-host claim atomicity** (N nodes claiming from one `queue.db` yield
  disjoint tickets),
- **crew provisioning, health probes, and the heartbeat sweep** across real hosts,
- **leases across hosts** (a scarce class's semaphore is honored fleet-wide),
- **host-down requeue** (kill a container mid-run → its in-flight tickets requeue
  to survivors with no attempt penalty),
- **cross-host reduce** (findings from many nodes cluster + bank on the master).

## 2. Topology

One Docker Compose network, all hermetic:

```
docker-compose.fleet.yml
  master           # runs the master loop + queue.db + the ssh site + scenario
  worker-cpu-1..3  # cpu-class crew nodes (resources: {cpu: N})
  worker-gpu-1..2  # gpu-class crew nodes (resources: {cpu: N, gpu: M} — M is a
                   #   FAKE count via env/label; no real GPU in CI)
```

- **Auth is hermetic:** a throwaway SSH keypair is generated at harness build; the
  private key lives on `master`, the public key is baked into each worker's
  `authorized_keys`. No external credentials, no `/design-login`, no proxy.
- **Master** holds `HERMES_HOME` (the real `queue.db`), the `ssh` site config
  listing the worker containers as hosts (with their resource labels), and the
  fake scenario. It runs `hermes run <scenario> --site ssh --agent mock`.
- **Workers** run only `sshd` + the hermes worker runner + the `MockAgent` + the
  no-ship guard shims (all baked into the image). They are stateless, reached only
  via master-initiated SSH — exactly the production model.

## 3. Images

- `Dockerfile.worker` — small base (python3 + openssh-server), a non-root user, the
  hermes engine's worker runner + `agents/` (so `MockAgent` is available), the
  no-ship guard shims installed early on `PATH`, and `authorized_keys`. Resource
  class + counts come from env (`HERMES_NODE_RESOURCES='{"cpu":4}'` /
  `'{"cpu":8,"gpu":2}'`).
- `master` reuses the same image plus the CLI + scenario; it is the only node with
  the private key and the `queue.db`.

## 4. The `ssh` site adapter (`sites/ssh/`)

A generic SSH `Site` (agent-agnostic; the containers are just SSH hosts) — also the
foundation the future `meta`/`devserver` sites extend:

- `discover_hosts()` — from the site config (the compose worker list) or `--hosts`.
- `provision(host, base_ref)` — idempotent verify against the baked image (checkout
  present, guard installed, agent runner present); no install needed since the image
  bakes it.
- `health(host, agent)` — `ssh true` reachability + latency, guard-installed check,
  `resources` from the node's label, merged with `agent.health_checks`.
- `run_worker(host, envelope, agent)` — the real `ssh_transport`: scp envelope, ssh
  the worker runner (which invokes the configured `agent`, here `MockAgent`), scp
  the result/evidence back.
- `resource_classes()` — the union of classes the crew advertises (`cpu`, `gpu`).
- `guarantees_no_ship()` — `True` (guard baked in).
- `submit_for_review` / `issue_source` — no-ops/file-based for the harness.

## 5. The fake scenario (`testkit/scenarios/`)

A deterministic generator producing one run's worth of work **plus** the `MockAgent`
result table keyed by ticket, engineered to exercise every path so the fleet has a
real "shared goal" with a rich, checkable outcome:

- **Volume + spread:** ~40 tickets across `cpu` and `gpu` resource reqs so work
  spreads over both node classes and the gpu semaphore actually binds.
- **Clustering:** several tickets share a `root_cause.signature` → `reduce`
  produces a known number of clusters (canonical + duplicates) — verifies
  cross-host dedup.
- **Failures:** a few `driver_failed` (terminal) and a few `infra_failed`
  (retry-then-succeed) → verifies the retry cap + backoff.
- **needs_human:** a couple with `verify=False` → routed to `needs_human` →
  verifies the re-verify override and reduction review path.
- **Contention:** more gpu tickets than gpu slots → some `parked` then un-parked as
  leases free → verifies the parked lifecycle + semaphore.
- The scenario is a single seedable fixture reused by BOTH the single-box tier and
  the fleet tier, so the two tiers assert the same expected outcome.

## 6. The shared goal & convergence assertions

The master runs one run; all worker containers pull from its queue and drive it to
terminal. The integration test asserts the fleet **converged correctly**:

1. **Run → `done`**; every ticket terminal (`done`/`failed`/`needs_human` resolved).
2. **Distribution:** the `attempts` audit shows work ran on **multiple distinct
   hosts**, and no ticket was double-claimed.
3. **Reduce:** exactly the scenario's expected clusters/reductions were produced and
   banked (via the injectable sink).
4. **Leases:** the gpu semaphore was never over-issued (max concurrent gpu leases ≤
   fleet gpu capacity); parked tickets un-parked and completed.
5. **Failure handling:** infra-failed tickets retried and finished; driver-failed
   went terminal with no retry.
6. **Events:** the ordered `events` stream reflects claims/results/lease/host events
   across hosts (the same stream the web control plane renders).

## 7. Failure injection

The harness can perturb the fleet mid-run and assert recovery:

- **Down node:** `docker stop worker-cpu-2` mid-run → the heartbeat sweep marks it
  `down`, its in-flight ticket requeues (no penalty), a survivor finishes it, the
  run still converges.
- **Slow node (optional):** add latency (`tc`/sleep in the runner) → verifies
  timeout handling maps to a terminal `driver_failed` (no infra retry).

## 8. Where it fits

- **Test tiers:** (1) unit (`pytest`/`vitest`); (2) single-box integration (`local`
  + `MockAgent`, always-on, fast, no Docker); (3) **fleet integration (this
  harness)** — realistic multi-node, gated behind a `@pytest.mark.docker` marker so
  suites without Docker skip it cleanly; (4) web e2e (Playwright) may point at the
  fleet for a realistic multi-host run to render.
- **engine-core:** delivered as a new plan slice (see `engine-core-plan.md` — Slice
  12, "Fleet integration harness"), after dispatch/crew/leases/ssh_transport exist.
- **web control plane:** `web-control-plane-plan.md` §10 e2e can run against the
  fleet so the SPA is proven against real multi-host data, not just single-box.

## 9. Definition of done

- `make fleet-test` (or `pytest -m docker`) brings the fleet up, runs the scenario
  to convergence, asserts §6 + the §7 down-node recovery, and tears down — green,
  hermetic, no Meta/cloud/real-agent.
- The `ssh` site has unit tests (command construction, health parsing; subprocess
  mocked) independent of Docker.
- CI runs it where Docker is available; local runs skip gracefully without Docker.

## 10. Non-goals

- Not a performance/load benchmark (it's correctness-of-distribution).
- Not a real-agent test by default — workers run `MockAgent` for determinism. An
  opt-in variant can run a real `claude` agent in the containers for manual demos,
  but that needs agent auth and is out of scope for automated CI.
- Not the `meta`/`devserver` site — but the generic `ssh` site here is the base
  those extend.
