# Runs view redesign

Status: design approved in conversation 2026-09-28/29; this doc is piece 1's spec and the record of
the decisions for pieces 2 and 3. Branch `runs-view`, stacked on `fix-run-kept-across-tabs`
(d978a44), which sits on the committee branches (`committee-one-on-ones` 82983ff and below). None
are merged.

## Problem

The control plane shows one run at a time and hides that fact:

- The only way to change runs is a native `<select>` at the far right of the top bar
  (web/src/components/TopBar.tsx:304-329). It disappears when there is one run.
- No in-app link leads to a run: not Crew's `current_run` (CrewPanel.tsx:204-210), not the crew
  drawer's leases (CrewDrawer.tsx:413-421), not Activity rows (ActivityFeed.tsx:42-47), not the
  ticket window (TicketModal.tsx:326).
- The Run tab (RunOverview) is six tiles and one card; most of the page is empty, and it never
  shows the run id (RunOverview.tsx:161-241).
- Tabs silently differ in scope. Crew and Activity are global; Needs you shows one run's decisions
  (App.tsx:83-101) while three runs are waiting; Activity loads the OLDEST 200 events
  (ActivityFeed.tsx:77-80, engine/events.py:96-104) and never names their runs.
- The Playbook tab appears and disappears as you switch runs (TopBar.tsx:282), which breaks the
  rule that every tab earns its place for every playbook.
- `/api/runs` is fetched once and never refreshed (web/src/hooks/useApi.ts:45-73).
- The run list is noisy: about half the runs are scoring runs (`committee-eval`), untitled.

The user uses the console to: see what needs them across runs, watch a live run, read a finished
run, compare runs, and read high-level numbers about a run.

## Decisions (from the user, binding)

1. Layout: a persistent runs rail on the left plus a run pane on the right (not a home dashboard,
   not top tabs with a switcher).
2. Compare (piece 2) shows key numbers, eval scores and outcomes side by side, and at the bottom a
   judged comparison: which run did better, and lessons so future runs improve.
3. The judged comparison is automatic (piece 3), controlled by a setting on a Settings tab,
   default on.
4. Trigger: when a run delivers its decision (starts waiting on the user's ruling), it is scored
   and compared, so the lessons are ready before the ruling.
5. Baseline: the best-scoring earlier run of the same playbook on the same input.
6. Needs you across runs: preview and rule inline, plus "open in run" for full context.
7. Build order: piece 1 (navigation and rail), then piece 2 (Compare), then piece 3 (automatic
   scoring and comparison). Each gets its own spec, plan and review.

## Constraints

- Every tab earns its place for every playbook; no tab is shown or hidden per playbook.
- The engine stays generic and stdlib-only. The shell names no playbook; a playbook's own content
  appears only through its view bundle (`/api/playbooks/{name}/view.js`, `/api/runs/{id}/view`).
- GET endpoints use `Depends(require_auth_read)` (no token on loopback); every mutation needs the
  token (server/app.py:312-338). Nothing auto-ships; accept/reject keep today's endpoints.
- Append-only tables stay append-only. No schema change.
- Tests never touch `~/.hermes`. The pipeline never restarts the live control plane (44102);
  Playwright runs only in the throwaway container (`make image-fast IMAGE=hermes-control-plane:<tag>
  && make ui-test-committee IMAGE=...`, then `podman rmi`).

## Piece 1: navigation, runs rail, run pane, cross-run pages

### Layout

- Top bar: Hermes; the cross-run pages Needs you (with a count across all runs), Crew, Activity;
  the live indicator. The run `<select>` and the Playbook tab are removed.
- Runs rail, left, about 240px, built on the design kit's sidebar pattern (web/src/ds/_ds_bundle.js
  sidebar component). Collapsible to a narrow strip.
  - A filter box matching run id, playbook, phase or subject.
  - Playbook chips: one per playbook present; clicking toggles showing that playbook's runs. The
    chosen set persists in `localStorage`. (Turning off `committee-eval` hides the scoring runs.)
  - Groups, in order: **Needs you** (at least one decision waiting), **Active** (running or paused),
    **Finished** (done, failed, stopped; the newest 10 shown, the rest behind "show N more").
    Newest first within a group. A run appears in exactly one group (Needs you wins).
  - Row: run id, playbook, a state icon, current phase, age, a thin progress bar (tickets done /
    total), the waiting count when > 0, and a one-line subject when the run's first ticket has one.
  - Row checkboxes and the "Compare N runs" button arrive with piece 2 (no placeholder page in
    piece 1).
- Run pane, right: the selected run (see "Run pane").

### Moving between runs

- Click a row; or `[` / `]` for the previous / next run in the rail's visible order; `/` focuses the
  filter box. Shortcuts do nothing while focus is in a text input, textarea, select or
  contenteditable.
- The selected row is highlighted, marked `aria-current="page"`, and scrolled into view.
- Selecting a run keeps the current run tab (Summary, Tickets, Outputs, Metrics).

### Addresses (hash routes)

The SPA is served only at `/`, so routes stay in the hash.

| Route | Page |
|---|---|
| `#/runs/<id>/<tab>` | run pane, `<tab>` in summary, tickets, outputs, metrics |
| `#/runs/<id>/tickets?ticket=<ticket id>` | ticket window open over Tickets |
| `#/needs-you` (`?run=<id>` optional) | cross-run Needs you |
| `#/activity` (`?run=<id>`, `?kind=<k>` optional) | cross-run Activity |
| `#/crew` | Crew |

- Old hashes convert on load with `history.replaceState` (not a navigation): `#overview?run=X` →
  `#/runs/X/summary`; `#board?run=X&ticket=T` → `#/runs/X/tickets?ticket=T`; `#outputs`/`#findings`
  → outputs; `#metrics` → metrics; `#playbook?run=X` → `#/runs/X/summary`; `#review`/`#needs-you` →
  `#/needs-you` (with `?run=X` when present); `#crew` → `#/crew`; `#activity` → `#/activity`. A
  legacy hash with no `run` uses the default run (below).
- Back/forward move between routes; every route is a link that can be sent.
- A route naming a run not in the list shows a dismissible note "`<id>` isn't in this home" and opens
  the default run.
- Default run (a bare `/` or `#/runs`): the first run in the rail's Needs you group, else the first
  Active run, else the newest run.

### Run pane

**Header** (always visible above the run tabs):
- `<id> · <playbook>`, a state label (running, paused, waiting on you, done, failed, stopped), the
  current phase, the start time and elapsed time.
- A progress bar: tickets done / total, plus working, failed and waiting counts (from the run
  detail's `tickets` map).
- `⚑ N waiting on you` when N > 0, linking to `#/needs-you?run=<id>`.
- Pause / Resume / Stop (today's RunControl, moved from RunOverview.tsx:240), available on every
  run tab. Same endpoints and token rules.
- ‹ › buttons for the previous / next run in the rail's order (the same as `[` / `]`).

**Tabs:** Summary, Tickets, Outputs, Metrics, identical for every run of every playbook.

**Summary** replaces the Run tab:
- Top strip of key numbers: tickets, retries (retry rate), mean time to result, elapsed, and cost
  when `/api/runs/{id}/metrics` reports it. The six tiles of today's RunOverview move here.
- Main area: when the run's playbook ships a view (`has_view`), its default variant renders here
  (committee: transcript, verdict with accept/reject, document stepper, exactly today's Playbook
  tab). Otherwise a phase timeline: each phase with its ticket counts and its latest output's
  headline, linking to Outputs.
- Side column:
  - *Waiting on you here*: this run's pending decisions (same rule as `awaitsDecision`,
    web/src/util/reduction.ts), each with a headline and "preview" / "open" links.
  - (*Score and lessons* is added by piece 3; piece 1 renders no placeholder for it.)
  - *Recent events*: this run's last 10 events, newest first, linking to `#/activity?run=<id>`.

**Tickets, Outputs, Metrics:** today's views, scoped to the header's run. Outputs' "N waiting on
you" link goes to `#/needs-you?run=<id>`. The Metrics tab keeps its playbook metrics column.

### Cross-run pages

**Needs you** (`#/needs-you`):
- Every waiting decision across all runs, from `GET /api/needs-you`, grouped by run. A group header
  shows the run (link), its playbook and how long its oldest item has waited. Items are oldest first.
- Optional `?run=<id>` filter, shown as a removable chip.
- Item row: headline, age, and (piece 3) latest score and top lesson.
- Expand: renders the decision with Outputs' existing reduction card, plus Accept and Reject (the
  existing `POST .../accept|reject` endpoints; Reject asks for a reason as today). On success the
  item leaves the list and every count refreshes. On failure the error shows on the item and it
  stays.
- "Open in run": `#/runs/<id>/summary`, with the verdict scrolled into view when the playbook view
  exposes one.
- The top-bar count is the number of waiting decisions across all runs.

**Activity** (`#/activity`):
- Newest first. Loads the latest 200 events; "Load older" fetches 200 before the oldest shown; live
  events prepend.
- Each row names its run as a link.
- Filters: run (chip, from `?run=`), kind (as today).
- Uses the app's single event stream instead of opening a second WebSocket (ActivityFeed.tsx:60).

**Crew** (`#/crew`): unchanged, except that a host's current run, its leases' runs and its current
ticket are links (`#/runs/<id>/tickets?ticket=<ticket id>`).

**Ticket window:** shows its run as a link (the ticket id starts with its run id).

### Server changes

- `GET /api/runs`: each row gains `updated_at`, `has_view`, `awaiting` (count of pending reductions
  holding a needs_human ticket, the same rule as the Needs you endpoint) and `subject` (the first
  ticket's subject, or null). Existing fields and order unchanged. The per-run ticket COUNT queries
  (server/app.py:373-377) become one `GROUP BY run_id, state` query.
- `GET /api/needs-you` (new, `require_auth_read`): a list of `{run_id, playbook, reduction_id,
  kind, phase, created_at, headline, member_tickets}` for every pending reduction holding a
  needs_human ticket, across all runs, oldest first. `headline` is the reduction's first non-empty
  summary line, clipped to 200 characters, computed generically from the reduction JSON (the same
  fields Outputs reads); no playbook-specific parsing.
- `GET /api/events`: adds `run=<id>` (filter) and `before=<event id>` with `order=desc`
  (newest-first paging). Default behaviour without these params is unchanged.
- `engine/events.py`: one generic helper, `latest(conn, *, run_id=None, before=None, limit=200)`,
  newest first, stdlib only. No other engine change.

### Keeping the page current

- The rail refetches `/api/runs` when the event stream reports a run-affecting event (run started,
  phase advanced, needs_human, reduction created, reduction accepted or rejected, run state
  changed), at most once per 2 seconds (trailing refetch so the last event is never missed).
- The run pane's detail fetch discards a response for a run that is no longer selected (fixes the
  race in App.tsx:64-70, 119-123).
- The Needs you count refetches on the same events.

### Errors

- Run list fails to load: the rail shows the error and Retry; the top bar and cross-run pages still
  work.
- Unknown run in the address: the note above, then the default run.
- Accept/reject failure: inline error on the item, item kept.
- Needs you or Activity fetch failure: an inline error with Retry on that page.

### Accessibility

- The rail is a `<nav aria-label="Runs">` with list semantics; the selected row has
  `aria-current="page"`; groups have headings.
- Shortcuts are ignored inside text entry; every control is reachable by keyboard with a visible
  focus ring.

### Tests

- Vitest:
  - route parse/build, every legacy conversion, unknown-run fallback, default-run rule;
  - rail grouping (one group per run, Needs you wins), filter box, playbook chips persisted in
    `localStorage`, "show N more", `[` `]` `/` including the text-entry guard, `aria-current`;
  - run header (state label, progress, waiting link, controls, ‹ ›);
  - Summary for a playbook with a view (renders the view) and without (phase timeline);
  - Needs you across runs: grouping, run filter, expand, accept and reject success and failure;
  - Activity newest first, "Load older", run filter, run links, single stream;
  - Crew and ticket-window run links;
  - stale run-detail responses are discarded.
- Pytest: `/api/runs` new fields (incl. `awaiting` against a seeded pending reduction) and the
  single grouped query; `/api/needs-you` (cross-run, oldest first, headline clipping, empty home);
  `/api/events` `run`, `before`, `order=desc` and unchanged default; `engine.events.latest`.
- Playwright (throwaway container): pick a run in the rail, switch tabs (the run is kept), Back
  returns to the previous run, open Needs you, preview a decision, "Open in run" lands on its
  Summary.
- Tests that change: App.test.tsx's "Playbook tab appears and disappears as the reader switches
  runs" (replaced by "Summary shows the playbook view for a run that has one"); the TopBar run
  picker tests (the picker is removed); useHashView tests (replaced by the route tests, keeping
  d978a44's intent).

### Acceptance criteria

1. Every run in the home is visible in the rail without opening a menu, grouped Needs you / Active
   / Finished, and selecting one keeps the current run tab.
2. The run pane always names the selected run (id, playbook, state) in its header.
3. `[` / `]` / `/` work as specified and never fire while typing.
4. Every route in the table round-trips through refresh and Back/Forward; every legacy hash
   converts; an unknown run shows the note and the default run.
5. Summary is present for every run; a playbook's view renders inside it; no tab appears or
   disappears when switching runs.
6. Needs you lists every waiting decision across runs; accept and reject work inline; "Open in run"
   lands on the run's Summary; the top-bar count is cross-run.
7. Activity is newest first, pages older events, names and links each event's run, and filters by
   run; it opens no second WebSocket.
8. Crew, crew drawer and ticket window link to runs.
9. The rail updates within ~2 s of a run starting, changing phase, waiting on the user or ending,
   with no reload.
10. `engine/` gains only `events.latest`; no playbook name appears in `web/src` production code or
    `server/`; GETs need no token on loopback, mutations need it.
11. Python, web (vitest, tsc, oxlint) and Playwright suites pass.

### File map (expected)

- web/src/hooks/useHashView.ts → route parser/builder with legacy conversion (or a new
  `useRoute.ts` replacing it).
- web/src/App.tsx → rail + pane layout, default-run rule, stale-response guard, runs refetch,
  cross-run count.
- New: web/src/components/RunRail.tsx, RunHeader.tsx; web/src/views/Summary.tsx (from
  RunOverview.tsx), NeedsYou page (from Review.tsx).
- web/src/components/TopBar.tsx → cross-run pages only; the copy-pasted tab buttons become one map.
- web/src/views/ActivityFeed.tsx, CrewPanel.tsx, components/CrewDrawer.tsx, TicketModal.tsx → run
  links; Activity paging/filter/shared stream.
- web/src/api/client.ts → new endpoint clients; fix `created_at`/`updated_at` typed as string
  (they are epoch seconds).
- server/app.py → `/api/runs` fields, `/api/needs-you`, `/api/events` params.
- engine/events.py → `latest`.
- Tests: web/src/**/*.test.tsx, tests/unit/test_*server*/api tests, web/tests-ui/.

## Piece 2: Compare (decisions only; own spec later)

- Each rail row gains a checkbox (accessible label "Compare run-20"); ticking two or more shows a
  "Compare N runs" button → `#/compare?runs=a,b[,c]`.
- Side by side: key numbers (generic: state, elapsed, cost, tickets done/failed/retried; plus the
  playbook's own numbers through its view bundle), eval scores per dimension with the weakest
  highlighted (when a run has been scored), outcomes (decision text and status: pending, accepted,
  rejected).
- At the bottom, the judged comparison for the pair when one exists (piece 3 produces it); a
  "judge this comparison" action for an arbitrary selection is optional in piece 2's spec.
- Generic: the shell reads scores and comparisons through a playbook-neutral shape; committee is the
  first provider (its eval.json and evals.jsonl).

## Piece 3: automatic scoring and comparison (decisions only; own spec later)

- A Settings tab (cross-run, top bar) with "Score and compare runs automatically", default on,
  persisted in `HERMES_HOME` (not the browser).
- When a run delivers its decision and the setting is on: score it (the playbook's eval), then run a
  judge comparing it with the best-scoring earlier run of the same playbook on the same input; record
  which did better and 3-5 lessons, each citing where in the runs it comes from.
- While the judge runs, pause every other running run whose master is alive and the run itself
  (the engine's cross-run claim bug), then resume them all, unconditionally.
- Lessons show in Needs you (on the item), the run's Summary (Score and lessons) and Compare. They
  are shown only; nothing feeds them into future runs automatically.

## Out of scope / known issues

- The engine's `claim_ticket` (engine/queue.py:146) hands any queued ticket to any running run's
  master. Not fixed here; it is an engine change to propose separately. Piece 3 works around it by
  pausing.
- Titling runs (no title column exists); the rail uses the first ticket's subject when present.
