# Hermes control plane (web) — incremental build plan

Status: **draft**. Date: 2026-07-28. Parent: `docs/DESIGN.md` §10.
Depends on: engine-core (`docs/specs/engine-core.md`) + the FastAPI server (DESIGN
sub-project 4). North-star reference: `web/prototype/` (the Claude Design import).

## 1. North star

`web/prototype/Hermes Control Plane.html` is the target. It is a CDN-React +
in-browser-Babel prototype driven by **mock** `window.HERMES` data and the `_ds`
design system (`window.DSNS`). It has six views — **Run overview, Metrics,
Tickets (board), Crew, Findings, Activity** — plus a **Ticket drawer**, **Host
drawer**, a **Playbook dialog**, and a **Stop-run dialog**; a top bar with view
nav, a playbook context chip, a live indicator, a re-probe-crew button, and a stop
button.

We keep `web/prototype/` untouched as the visual reference. The real app is built
fresh under `web/` (Vite + React + TypeScript), consuming the same `_ds` design
system, wired to the live control-plane API — never to mock data.

## 2. The "everything works" contract (non-negotiable)

Every slice obeys all of these, or it does not land:

1. **No mock data in shipped UI.** Every rendered view reads a real endpoint
   backed by real engine state (a real `queue.db` produced by a real run on the
   `local` site + `MockAgent`). Loading / empty / error states are real.
2. **No dead controls.** A button/toggle/filter ships only together with its
   wired, tested action (a real API call with a real effect). If the action can't
   be real yet, the control is not shown.
3. **Full-stack per slice.** A slice = [engine capability if missing] → [API
   endpoint] → [UI component] → [wired interaction], each with tests (§9).
4. **Real fidelity to the design.** Use the `_ds` tokens + components verbatim;
   match the prototype's layout for the view being built.
5. **Data that isn't real yet is not shown.** Metrics/resources/agent-usage
   sections appear only once their underlying telemetry is genuinely computed
   (Phase E). We never ship a chart of invented numbers.

## 3. How we truly incorporate the design

- **App runtime:** replace CDN-React + Babel-in-browser with **Vite + React 18 +
  TypeScript**. `HermesApp`/`Shell`/view components are ported to `.tsx`.
- **Design system:** vendor `_ds/` into `web/src/ds/` as a first-class local
  dependency. Keep the token CSS files (`tokens/*.css`, `styles.css`) imported
  globally (unchanged — they are the source of visual truth). Wrap the component
  bundle behind a **typed module** `web/src/ds/index.ts` exporting `StatTile`,
  `StatusPill`, `TicketCard`, `KanbanColumn`, `CrewRow`, `HealthBadge`, `EventRow`,
  `AttentionBanner`, `Drawer`, `Dialog`, `Card`, `Table`, `Tabs`, `Button`,
  `IconButton`, `Tooltip`, `EmptyState`, `Input`, `Badge`, `CrewBackdrop`, … so the
  app imports typed components instead of reading `window.DSNS`. Icons: bundle
  `lucide-react` instead of the CDN global.
- **The data contract:** `window.HERMES` becomes the API response shapes (§5). A
  thin **normalization layer** (`web/src/api/`) maps engine values to UI values —
  notably ticket state `needs_human` ⇄ the prototype's `needs-human`, and derives
  the playbook-dependent `run.context` (mechanic=base+suite, rigger=model+metric,
  medic=incident+service) from the run's playbook + config.
- **Auth:** the SPA is served by the FastAPI server and uses the bearer-token
  model from DESIGN §10 (loopback bootstrap-injection; token in memory only).

## 4. Architecture

```
web/                      # Vite + React + TS SPA (this plan)
  src/
    ds/                   # vendored _ds design system + typed index
    api/                  # typed client, normalization, react-query hooks, ws
    views/                # RunOverview, Metrics, TicketBoard, Crew, Findings, Activity
    components/           # app-level composites (TopBar, drawers, dialogs)
    App.tsx  main.tsx
  prototype/              # the Claude Design import (reference only, not built)
server/                   # FastAPI JSON API + websocket (DESIGN §10, sub-project 4)
engine/                   # data source (queue.db) — sub-project 1
```

Dev: Vite dev server proxies `/api` → the FastAPI server, which reads the real
`queue.db` under `HERMES_HOME`. A single `hermes serve --api` serves the built SPA
+ API in one process in production.

## 5. API surface (derived from the data contract)

Read (Phase B): `GET /api/health`; `GET /api/runs`; `GET /api/runs/{id}` (run +
phases + ticket-state counts + context); `GET /api/runs/{id}/tickets`
(filter: state/phase/resource/host/search); `GET /api/tickets/{id}` (envelope,
result, attempts, evidence); `GET /api/crew` (members + `HealthReport`);
`GET /api/runs/{id}/reductions` (findings); `GET /api/events?since=` (feed);
`GET /api/leases`.
Live (Phase C): `WS /api/ws` — event stream + counter deltas.
Mutate (Phase D, token-gated): `POST /api/runs/{id}/{pause|resume|stop}`;
`POST /api/crew` (add), `POST /api/crew/{host}/{drain|reprobe}`,
`DELETE /api/crew/{host}`; `POST /api/tickets/{id}/{requeue|park}`;
`POST /api/reductions/{id}/{accept|reject}`.
Metrics (Phase E, gated): `GET /api/runs/{id}/metrics` (+ `resources`, `agent`
sub-objects only when instrumented).

Each endpoint maps to engine callables already specified in engine-core (queue,
crew, leases, events, reductions) — the server is a thin read/adapt + auth layer.

## 6. Prerequisite: engine-core milestone

The web app needs a **real run to look at**. Engine-core Slices 0–9
(`engine-core-plan.md`) — through the end-to-end local run producing tickets /
events / crew / reductions in `queue.db` — are the prerequisite for Phase B onward.
Phase A (app + DS scaffold) has **no** backend dependency and can proceed in
parallel with engine-core. Each slice below names its engine-core dependency.

## 7. Slices (each obeys §2 and the §9 DoD)

**Phase A — real app skeleton (no features, but real).**
- **A0. Vite+TS app + vendored `_ds`.** Scaffold `web/`; vendor `_ds` + typed
  `ds/index.ts`; global token CSS; `lucide-react`. Deliver a DS **component gallery**
  route rendering each DS primitive (the library itself is real + tested). Dep:
  none. DoD: `vite build` clean; vitest renders every DS export; gallery matches
  prototype styling.
- **A1. Shell + real health.** `GET /api/health` + `GET /api/runs` (thin FastAPI
  over `queue.db`); `TopBar` + view nav + real **empty states** ("no active run").
  Nav items whose views don't exist yet are absent, not stubbed. Dep: engine-core
  Slice 1 (schema). DoD: with an empty DB the shell shows the real empty state;
  with a seeded run it lists it.

**Phase B — read-only views over a real run (one per slice).**
- **B1. Run overview.** `GET /api/runs/{id}`; `StatTile` counts + phase timeline +
  playbook context chip + `PlaybookDialog` — all from real counts. Dep: engine-core
  Slice 9. DoD: numbers equal a `sqlite` query on the real run.
- **B2. Ticket board.** `GET /api/runs/{id}/tickets`; `KanbanColumn`/`TicketCard`;
  search + state/resource/host filters wired to real query params; row → drawer.
  Dep: engine-core Slice 9.
- **B3. Ticket drawer.** `GET /api/tickets/{id}`; payload, strict result, attempt
  timeline, evidence links (read-only). Dep: engine-core Slice 9.
- **B4. Crew panel.** `GET /api/crew` + `GET /api/leases`; `CrewRow` +
  `HealthBadge` from real `HealthReport`; host drawer (read-only) also renders the
  host's active lease (ticket id + remaining lease TTL) from `GET /api/leases`, or a
  truthful empty state when the host holds none. This is the sole consumer of
  `GET /api/leases` and the view backing §10's fleet-wide-leases e2e assertion. Dep:
  engine-core Slice 8 (crew + health) — implies Slice 6 (leases).
- **B5. Activity feed.** `GET /api/events?since=`; `EventRow` list + kind filter. Dep: engine-core Slice 9.
- **B6. Findings.** `GET /api/runs/{id}/reductions`; finding cards with member
  tickets + the reduction's real `review_state` (pending/accepted/rejected/
  superseded). Any playbook-specific fix status (e.g. mechanic's diff-published/
  proposed) is derived from the reduction `json` + member-ticket states via the
  normalization layer — never the prototype's mock `fix_state` field (read-only).
  Dep: engine-core Slice 9.

**Phase C — live.**
- **C1. Websocket.** `WS /api/ws` backed by the `events` table; `LiveDot` + feed +
  overview counters update in real time (replaces polling). Dep: engine-core Slice
  3 (events). DoD: an event emitted engine-side appears in the UI without reload.

**Phase D — control actions (each a real, token-gated mutation).**
- **D1. Run control.** Stop/pause/resume dialog → `POST /api/runs/{id}/…`
  (`queue.set_run_state`). Dep: engine-core Slice 5.
- **D2. Crew control.** Add-host modal with a **live health-check checklist** →
  `crew.add`; drain/remove/re-probe. Dep: engine-core Slice 8.
- **D3. Ticket control.** requeue / park from the drawer (requeue →
  `queue.requeue_needs_human`, park → `queue.park_ticket`). Dep: engine-core
  Slice 5.
- **D4. Findings review.** accept/reject a reduction → `POST /api/reductions/{id}/…`
  (members settle per engine semantics). Dep: engine-core Slice 5.
- Auth is added with the first mutation (D1): loopback bind + bearer token, 401/4401
  (DESIGN §10).

**Phase E — metrics & cost (gated on real instrumentation; ship a section only when
its data is real).**
- **E1. Run metrics.** Server aggregates time-buckets from `events`/`attempts`
  (throughput, done/failed cumulative, error rate, crew online) →
  `GET /api/runs/{id}/metrics`; `MetricsView` core. Dep: engine-core Slice 9
  (events/attempts populated by a real run).
- **E2. Resources.** Requires periodic host-resource sampling
  (`HealthReport.resources` over time); `ResourcesSection` (CPU/GPU/mem series).
  Not shipped until sampling exists.
- **E3. Agent usage.** Requires the **agent adapter to capture per-run token/cost
  telemetry** (from `claude -p` usage output) and the engine to record it;
  `AgentUsageSection` (tokens in/out, cache, spend, per-model, per-phase). This is
  the most instrumentation-heavy and ships last; until then the section is absent.

## 8. What we deliberately defer / never fake

- The prototype's rich metrics (GPU burn, $ spend, per-model token share, cost per
  finding) are **not shipped** until Phase E instrumentation makes them real. A
  view with no real data shows a truthful "not yet instrumented" empty state, not
  invented numbers.
- Multi-run history, federation (tree) views — out of scope here (federation is a
  future extension).

## 9. Definition-of-done per slice

1. **Backend:** endpoint implemented over real engine callables; `pytest` covers
   it (happy + empty + error + auth where applicable).
2. **Frontend:** component in `web/src/`, typed against the API shape; `vitest` +
   React Testing Library cover render + interaction; loading/empty/error states.
3. **Wired:** the interaction performs the real API call and reflects the real
   result (optimistic UI + revalidate).
4. **E2E:** one Playwright test drives the **real local stack** (`hermes serve
   --api` over a real local run seeded with `MockAgent`) and asserts the real
   behavior end-to-end (no network mocks).
5. **Fidelity:** the view visually matches `web/prototype/` for that screen.
6. No mock data, no dead controls (§2).

## 10. Testing strategy

- **Backend:** `pytest` against a temp `HERMES_HOME` with a seeded local run.
- **Frontend unit:** `vitest` + RTL; the typed API client mocked at the fetch
  boundary for unit tests only (never in shipped code).
- **E2E:** `Playwright` against the real `hermes serve --api` + a real run. Two
  backends: (a) a single-box local run (`local` site + `MockAgent`) for fast
  per-slice checks, and (b) the **Docker fleet** (`fleet-integration-harness.md`)
  for a realistic multi-host run — proving the SPA renders real distributed data
  (multiple crew nodes, host-down, fleet-wide leases), not just single-box.
- All runnable with no Meta dependency.

## 11. Open items

- Exact `_ds` vendoring: consume `_ds_bundle.js` behind a typed shim vs. extract
  components to TSX. Lean: typed shim first (preserves visuals), extract later if
  needed.
- Token/cost telemetry shape from the `claude` agent adapter (drives E3) — define
  when Phase E starts.
- Whether the server (sub-project 4) gets its own spec doc or is specified inline
  here; lean: fold the server's read/mutate/ws contract into this plan and keep
  DESIGN §10 as the authority for auth/binding.
