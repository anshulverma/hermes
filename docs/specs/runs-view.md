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
  drawer's leases (CrewDrawer.tsx:413-421), not Activity rows (ActivityFeed.tsx:42-47). (The ticket
  window, TicketModal.tsx:326, needs none: TicketBoard.tsx:379 is its only mount, so it only ever
  opens over its own run's Tickets tab.)
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

- Top bar: Hermes (the wordmark links to `#/runs`, i.e. the default run); the cross-run pages Needs
  you (with a count across all runs), Crew, Activity; the live indicator. The run `<select>` and the
  Playbook tab are removed. The Needs you item always shows. Its count badge shows Σ `awaiting` when
  that is above 0, and nothing when it is 0, before the first runs load, or while the runs list has
  never loaded (after a later refetch fails it keeps the last loaded count).
- Runs rail, left, 232px: a local `RunRail` component styled after the kit's console AppShell
  sidebar (web/src/ds/_ds_bundle.js:2147-2270: an `<aside>` with a hairline right border
  `1px solid var(--border-hairline)`, padding `16px 12px`, muted 12px group labels,
  `var(--wash-selected)` for the selected row and `var(--wash-hover)` on hover). Nothing is imported
  from that `Sidebar`: it is a demo inside the kit's console UI-kit bundle (hard-coded 'Northlake'
  and `KIT_DATA`), never put on `window.DSNS` nor exported from web/src/ds/index.ts. RunRail composes
  exported ds parts (Input, Badge, IconButton, Divider). Its rows are links, not the demo's 32px
  `<button>` NavItems (see Accessibility).
  - State icon: RunRail and RunHeader draw the run state from their own five-entry icon map
    (running: pulsing dot, paused: two bars, done: check, failed: cross, stopped: square), each with
    `aria-label` and `title` set to the state word. StatusPill is not used for run state: the kit's
    TICKET_STATES has no paused or stopped (web/src/ds/_ds_bundle.js:1137-1197), so StatusPill would
    draw both with the neutral hollow marker it gives queued (:1293-1297), and it takes no marker prop.
  - A filter box, `<input type="search" aria-label="Filter runs" placeholder="Filter runs (/)"
    aria-keyshortcuts="/">`: a case-insensitive substring match on run id, playbook, phase and
    subject. The text is not persisted. Enter opens the first visible row, as a click would. Escape
    clears the text; on an already empty box it returns focus to the element focused before `/`,
    else the pane's `<h1>`.
  - Playbook chips: one per playbook present, each a `<button aria-pressed>` that shows a check when
    on and a struck-through name when off; clicking toggles showing that playbook's runs.
    `localStorage` key `hermes.rail.hiddenPlaybooks` holds a JSON array of the HIDDEN playbook names
    (default `[]`, and `[]` when it does not parse to an array of strings), so a playbook seen for
    the first time is shown. If `localStorage` throws, the choice is kept in memory. (Turning off
    `committee-eval` hides the scoring runs.)
  - Chips and the filter box apply to all three rail groups and to nothing else: the top-bar count,
    the Needs you page and Activity stay unfiltered. When they hide any run, the rail shows one line,
    "N hidden by filters · Show all" ("N hidden, M waiting on you" when M > 0); Show all clears the
    text and the chips. N = the runs the chips or the filter text hide (rows behind "show N more" are
    not counted); M = Σ `awaiting` over those hidden runs, decisions, the same unit as the top-bar
    count.
  - Groups, in order: **Needs you** (`awaiting > 0`, whatever the run's state), **Active** (running
    or paused), **Finished** (done, failed, stopped). Finished shows its newest 10 and "show N more"
    (N counted after the filters), which reveals every remaining Finished row and is not persisted;
    while the filter box has text, Finished shows every match. A run appears in exactly one group
    (Needs you wins). Needs you and Active sort by `created_at` descending, so their rows don't jump
    when a run changes. Finished sorts by `updated_at` descending (the end time, which a finished run
    never changes, engine/queue.py:103, 612, 992; reopening moves the run out of Finished), so its
    newest 10 are the 10 most recently ended runs and the 'ended' ages read in order. Ties break by
    `id` descending. The selected run is always a visible row when it passes the chips and the filter
    text: if it falls beyond Finished's newest 10, it is shown after them in sort order and the
    "show N more" count leaves it out. A group with no rows after the filters is omitted, heading
    included. The pure `railGroups` and `defaultRunId` (see State ownership) are exported for tests
    and for App.
  - Row: run id, playbook, a state icon, current phase ('starting' when null and the run is running
    or paused; 'not started' when null and the run is done, failed or stopped), age ('started
    <relative created_at>' in Needs you and Active, 'ended <relative updated_at>' in Finished), a
    thin progress bar (tickets done / total) with visible 'D/T' text beside it (the 'progress text'
    the row's `aria-describedby` points at), 'N waiting' when `awaiting` > 0, and a one-line
    `subject` when non-null. With 0 tickets the row renders no `role="progressbar"`: only the empty
    track (`aria-hidden`) and the text 'no tickets yet'.
  - Relative times use `fmtAgo(ts, now)`, added to web/src/util/time.ts (it has only fmtTime,
    fmtDuration and fmtSeconds today): 'just now' under 60 s (a negative difference from clock skew
    is clamped to 0), otherwise `new Intl.RelativeTimeFormat('en', {numeric: 'always'})` on the
    largest whole unit of minutes, hours or days ('3 minutes ago', '2 hours ago', '5 days ago'). Each
    renders as `<time dateTime={ISO}>` with `fmtTime(ts)` as its `title`. Durations (elapsed, Needs you
    group waits) use `fmtSeconds`. One shared 30 s clock, `useNow()` (web/src/hooks/useNow.ts: one
    module-level interval shared by every subscriber through `useSyncExternalStore`, returning epoch
    seconds), redraws the rail, the header's elapsed, the Needs you ages and Summary's side column.
  - Collapse: a button at the top of the rail (`aria-expanded`, `aria-controls` on the rail list,
    labelled 'Hide runs' / 'Show runs') switches between the rail and a 48px strip showing only that
    button and, when above 0, the Needs you group's row count after the filters
    (`groups.needsYou.length`), with the accessible name 'N runs waiting on you'. `localStorage`
    `hermes.rail.collapsed` is '1' (collapsed) or '0' (expanded). Absent or any other value means the
    viewport default: collapsed when `window.innerWidth < 1024` at mount, read once and not re-read on
    resize (jsdom's innerWidth is 1024, so tests render expanded unless they set it). The collapse
    button writes '1' or '0'; `/` expanding the rail writes '0'. If `localStorage` throws, the choice
    is kept in memory. The app has no breakpoint or `matchMedia` today (web/src/App.css is an unused
    Vite template that nothing imports; it stays untouched). The rail, expanded or collapsed, always
    stays in the layout flow and pushes the pane; it never overlays it.
  - Row checkboxes and the "Compare N runs" button arrive with piece 2 (no placeholder page in
    piece 1).
- The rail shows on every route. On a run route the run pane (see "Run pane") fills the right side;
  on a cross-run route (`#/needs-you`, `#/activity`, `#/crew`) that page does, its top-bar item has
  `aria-current="page"`, and no rail row does.

### Moving between runs

- A rail row is a link to `#/runs/<id>/<tab>`: on a run route `<tab>` is the current run tab
  (Summary, Tickets, Outputs, Metrics); on a cross-run route it is the last run tab used this
  session (App state, default summary). Switching runs keeps the tab and drops the tab's other
  parameters (`?ticket=`).
- `[` / `]`: the previous / next row in the rail's visible order, `[...groups.needsYou,
  ...groups.active, ...groups.finished]` (the filtered groups top to bottom, not counting rows behind
  "show N more", but counting a selected run shown beyond the cap), whether or not the rail is
  collapsed. They work only on run routes; on cross-run routes they do nothing. No wrap-around: on
  the first or last visible row the key does nothing and ‹ or › is disabled (`aria-disabled`); `]`
  on the last Finished row shown does not expand "show N more". When the selected run is not among
  the visible rows (the chips or filter text hide it), `]` selects the first visible row and `[` the
  last.
- `/` works on every route: it expands a collapsed rail, focuses the filter box and calls
  `preventDefault()` (so no '/' is typed and Firefox's quick-find does not open). With no runs (no
  filter box) it does nothing and does not call `preventDefault()`.
- Shortcuts use one `keydown` listener on `window` and match `event.key`. They do nothing when
  `metaKey` is held (on macOS Cmd+[ / Cmd+] are browser Back / Forward), or when `ctrlKey` is held
  and `getModifierState('AltGraph')` is false; `altKey` alone does not block `[` or `]` (on many
  non-US layouts they need AltGr, which Windows reports as Ctrl+Alt, or Option on macOS). They also
  do nothing during IME composition (`isComposing`), when the event is already `defaultPrevented`,
  while any `[aria-modal="true"]` element is open (the ticket window's Dialog does not trap focus), or
  when the target is a textarea, a select, contenteditable, or an input whose type is not checkbox,
  radio, button, submit, reset, range, color or file.
- The selected row is highlighted (with a non-colour cue too, see Accessibility), marked
  `aria-current="page"`, and scrolled with `scrollIntoView({block: 'nearest'})` (not smooth; jsdom has
  no `scrollIntoView`, so web/src/test/setup.ts stubs `Element.prototype.scrollIntoView` once) when
  the selection changes (never on a background refetch). A selected run the chips or filter text
  hide stays in the pane, and no row is highlighted.
- Every click or key press changes the selection and the address at once; each is a history entry,
  except that a `[` / `]` keydown with `event.repeat === true` updates the address with
  `history.replaceState`, so holding a key leaves one history entry.

### Addresses (hash routes)

The SPA is served only at `/`, so routes stay in the hash.

| Route | Page |
|---|---|
| `#/runs/<id>/<tab>` | run pane, `<tab>` in summary, tickets, outputs, metrics |
| `#/runs/<id>/tickets?ticket=<ticket id>` | ticket window open over Tickets |
| `#/needs-you` (`?run=<id>` optional) | cross-run Needs you |
| `#/activity` (`?run=<id>`, `?kind=<k>` optional) | cross-run Activity |
| `#/crew` | Crew |

Route grammar (web/src/hooks/useRoute.ts, replacing useHashView.ts):
- `<id>` is written with `encodeURIComponent`, read with `decodeURIComponent` (a malformed `%`
  sequence, which throws `URIError`, makes the whole hash an unrecognised route), and never case-folded
  (today's parser lowercases the slug, useHashView.ts:46; the new one must not). `<tab>` matches
  case-insensitively. Query values go through `URLSearchParams`.
- `type Route = {page:'run', runId:string|null, tab:RunTab, ticket:string|null} | {page:'needs-you',
  run:string|null} | {page:'activity', run:string|null, kind:string|null} | {page:'crew'}`.
- `parseRoute(hash): {route: Route; canonical: string|null}`. `canonical` is the hash to
  `replaceState` to, or null when the hash is already canonical or the route still needs the
  default run. A route that needs the default run has `page:'run', runId:null` and keeps the tab and
  ticket it asked for (`#metrics` → `{runId:null, tab:'metrics', ticket:null}`). `buildRoute(route):
  string` returns `#/runs` for `{page:'run', runId:null, tab:'summary', ticket:null}` and throws for
  any other `runId:null` route. `parseRoute(buildRoute(r))` round-trips for every route with a
  non-null runId, for `#/runs`, and for the three cross-run pages.
- `useRoute(): {route: Route; navigate(r: Route): void; replace(r: Route): void}`. `navigate` sets
  `location.hash = buildRoute(r)` (a history entry); `replace` calls `history.replaceState` and sets
  the hook's state itself, since `replaceState` fires no `hashchange`. `useRoute` is backed by one
  module-level store read through `useSyncExternalStore`: `navigate`, `replace` and `hashchange` all
  update it and notify every subscriber, so App and TicketBoard always see the same route.
  TicketBoard and every other route reader use this API. Once the list has loaded, App resolves a `runId:null` route with
  `replace({...route, runId: defaultRunId(runs, hidden)})`, keeping the pending tab and ticket.
- The page segments `runs`, `needs-you`, `activity` and `crew` match case-insensitively, like
  `<tab>`. An empty query value (`?run=`, `?kind=`, `?ticket=`) reads as null. A `?ticket=` that
  does not start with `<runId>/` is dropped.
- Normalisation always uses `history.replaceState` (never a history entry): a trailing `/` is
  stripped; `#/runs/<id>` or an unknown tab becomes `#/runs/<id>/summary`; params a page doesn't take
  are dropped (`?ticket` on any tab but Tickets); an empty hash, `#/`, `#/runs` or any unrecognised
  route becomes the default run's summary once the list has loaded, so the address always names the
  run on screen. With no runs the hash is left alone until a refetch brings the first run (see
  "States with nothing in them"). If the list failed to load, an empty hash or `#/runs` stays as it
  is and the pane reads 'Couldn't load runs.' beside the rail's error.
- Every user action (a row, a tab, `[` / `]`, ‹ ›, a link, removing a chip, the kind select, opening
  or closing a ticket) pushes a history entry via `navigate` (except a held `[` / `]`, see "Moving
  between runs"). Back/forward move between routes; every route is a link that can be sent.
- Old hashes convert with `history.replaceState` on load and on every `hashchange` (a legacy link
  opened mid-session converts too): `#overview?run=X` → `#/runs/X/summary`; `#board?run=X&ticket=T`
  → `#/runs/X/tickets?ticket=T`; `#outputs`/`#findings` → outputs; `#metrics` → metrics;
  `#playbook?run=X` → `#/runs/X/summary`; `#review`/`#needs-you` → `#/needs-you` (with `?run=X` when
  present); `#crew` → `#/crew`; `#activity` → `#/activity`. A legacy hash with `ticket` but no `run`
  takes its run from the ticket id's prefix before the first `/` (ticket ids are `<run_id>/t-<n>`,
  engine/db/schema.sql:18); any other legacy hash with no `run` uses the default run.
- A route's run is checked against the full `/api/runs` list (not the filtered rail), and only after
  the list has loaded. A run missing from the list first triggers one `/api/runs` refetch (runs are
  never deleted, so "missing" almost always means "created after the list loaded"). Only if it is
  still absent does a dismissible note "`<id>` isn't in this home" show, and the hash is replaced
  with the default run on the same tab. The note is announced through the status region and clears
  on the next route change. If the list failed to load, the pane fetches `/api/runs/<id>` directly;
  a 404 shows the note and leaves the hash alone.
- On Needs you and Activity, a `?run=` naming an unknown run keeps its chip and shows that page's
  empty state.
- Default run, `defaultRunId(runs, hidden): string|null`: the first run in the Needs you group, else
  the first Active run, else the newest run by `created_at` (ties by `id` descending), computed over
  the chip-filtered list (ignoring the filter text), or over the full list when the chips hide every
  run; null only for an empty list.

### Run pane

**Header** (always visible above the run tabs). It renders at once from the selected run's
`/api/runs` row (id, playbook, state, phase, created_at, updated_at, tickets, awaiting: everything
it shows), and falls back to the run detail when there is no row (the list failed). The fallback
has no `awaiting`, so it shows no ⚑ link.
- `<id> · <playbook>` as the pane's `<h1>` (tabindex=-1, the focus target below), the state label
  (with the state icon), the current phase ('starting' when null and the run is running or paused;
  'not started' when null and the run is done, failed or stopped), the start time and the elapsed
  time.
- The state label is `runs.state` verbatim: running, paused, done, failed or stopped. 'Waiting on
  you' is never a state label; it shows only as the ⚑ link, beside whatever the state is.
- Elapsed = now − created_at while running or paused; updated_at − created_at once done, failed or
  stopped (updated_at is written only by reopen, set_run_state and set_run_phase,
  engine/queue.py:103, 612, 992, so for a finished run it is the end time). It uses `fmtSeconds` and
  redraws on the shared 30 s clock.
- A progress bar: done = `tickets.done` of total = the sum over all states, plus working =
  dispatched + running + reducing (claimed work waits in `dispatched`, RunOverview.tsx:24-25) and
  failed = `tickets.failed`. No separate waiting count. Beside it, a text caption 'D of T done · W in
  flight · F failed' (zero W and F terms omitted), also the bar's `aria-valuetext`, so the segments
  are not told apart by colour alone. With 0 tickets there is no `role="progressbar"`: only the empty
  track (`aria-hidden`) and the text 'no tickets yet', never 0%.
- `⚑ N waiting on you` when N = the row's `awaiting` > 0, linking to `#/needs-you?run=<id>`.
- Pause / Resume / Stop / Reopen: today's RunControl (moved from RunOverview.tsx:240), including
  Reopen and its 'Run is <state> — reopen it …' line for a done, failed or stopped run
  (RunControl.tsx:26, 64-126), available on every run tab. Same endpoints and token rules. After a
  control succeeds, `/api/runs` and the detail are refetched. RunControl is rendered with
  `key={run.id}`, so an open Stop confirmation, an error or an in-flight label never carries over to
  another run; the header itself is not keyed, so ‹ › keep focus. RunControl's only change is focus:
  when the refetched state replaces the pressed button, focus moves to the control that replaced it
  (Resume after Pause, Pause after Resume, Reopen after a confirmed Stop, Pause after Reopen);
  opening the Stop confirmation focuses Cancel, and Cancel returns focus to Stop.
- ‹ › controls are links (`<a href={prevHref}>` / `<a href={nextHref}>`, styled as buttons, like the
  run tabs; when the href is null they render with `aria-disabled="true"`, no `href`, `tabIndex=0`)
  (`aria-label="Previous run"` / `aria-label="Next run"`, so they don't clash with the
  committee view's '‹ Prev' step button, Diff.tsx:849-857; `aria-keyshortcuts="["` / `"]"`, tooltips
  'Previous run ([)' / 'Next run (])') do what `[` / `]` do, and are `aria-disabled` (still
  focusable) where those keys do nothing.

**Tabs:** Summary, Tickets, Outputs, Metrics, identical for every run of every playbook. They are
links with `aria-current="page"`, not an ARIA tablist.

**Summary** replaces the Run tab. Summary itself does not scroll: the top strip is fixed, the main
column is PlaybookView's own scroll container (PlaybookView.tsx:176) or the phase timeline's, and
the side column, 320px wide, scrolls on its own (CommitteeView.tsx:1880-1882 avoids a second
scroller inside the first). The two columns use a class whose rule lives in web/src/index.css (the
stylesheet main.tsx imports); `@media (max-width: 1023px)` switches it to `flex-direction: column`,
the side column moves below the main column with full width, `max-height: 40%` and its own scroll,
and the main column takes the rest.
- Top strip, in order: tickets (total), done, in flight (dispatched + running + reducing, the
  header's working; today's tile reads only `running`, RunOverview.tsx:140), parked, failed, queued,
  then retry rate (`metrics.retry_rate` as a %) and mean time to result
  (`metrics.mean_time_to_result_s`) from `/api/runs/{id}/metrics`, each '—' when the value is null
  or `metrics.totals.results === 0` (retry_rate is 0.0, not null, with no results,
  server/app.py:1429). No cost tile: the metrics endpoint reports no cost (server/app.py:1498-1507)
  and nothing else computes one. No elapsed tile: the header shows it.
- Summary does not carry RunOverview's context chips or PlaybookDialog. They switch on playbook
  names (normalize.ts:24-83) and render only for testkit's `example` and three playbooks that no
  longer exist (PlaybookDialog.tsx:19 returns null for dexter, research and committee). Delete
  `deriveContext`, `PLAYBOOK_CONTENT` and PlaybookDialog.tsx with their tests.
- Main area: when the run's playbook ships a view (`has_view`), its default variant renders here
  (committee: transcript, verdict with accept/reject, document stepper, exactly today's Playbook
  tab). Its PlaybookView gets `liveTick = viewTick`, App's tick over FINDING_EVENT_KINDS
  (reduction_created / accepted / rejected) for the selected run, as the Metrics tab's PlaybookView
  and today's Playbook tab get (App.tsx:246, 297), so the transcript and verdict stay live.
  Otherwise a phase timeline: `RunDetail.phases` with their ticket counts; each phase's headline is
  `reductionHeadline` of the newest reduction whose `phase` equals the phase name (from
  `/api/runs/{id}/reductions`, fetched only when there is no view), linking to
  `#/runs/<id>/outputs`. With no phases it reads 'No phases yet.'
- Side column:
  - *Waiting on you here*: this run's items from `/api/needs-you` (the Needs you rule, not a second
    one), each item as plain text (its headline via `reductionHeadline`, and its age), followed by one
    link for the block, 'Rule on these in Needs you', to `#/needs-you?run=<id>`. No per-item link and
    no separate preview. Empty: 'Nothing waiting on you in this run.'
  - (*Score and lessons* is added by piece 3; piece 1 renders no placeholder for it.)
  - *Recent events*: `GET /api/events?run=<id>&order=desc&limit=10` on mount; stream events for
    this run with an id above the newest fetched id are merged in (deduped by id, sorted by id
    descending) and the list keeps 10. It never refetches on a trigger. Newest first, linking to
    `#/activity?run=<id>`. Empty: 'No events.'

**Tickets, Outputs, Metrics:** today's views, scoped to the header's run. Outputs' "N waiting on
you" link goes to `#/needs-you?run=<id>`. The Metrics tab keeps its playbook metrics column.

### Cross-run pages

**Needs you** (`#/needs-you`):
- Every waiting decision across all runs, from `GET /api/needs-you`, grouped by run. Groups are
  ordered by their oldest item, longest-waiting first; items within a group are oldest first. A
  group header shows the run (link to `#/runs/<id>/summary`), its playbook, its state label (from
  its `/api/runs` row; a decision on a stopped or done run is still accepted by the endpoints,
  engine/queue.py:637-687) and how long its oldest item has waited (now − min(created_at),
  `fmtSeconds`).
- Optional `?run=<id>` filter (applied client-side), shown as a removable chip.
- Item row: headline, age (now − created_at, `fmtAgo`), and (piece 3) latest score and top lesson.
  The headline is `reductionHeadline(item.json, item.kind)` (web/src/util/reduction.ts:79), the
  function Outputs uses. It never returns null (it falls back to the kind), so no separate
  empty-headline case exists.
- Expand: items start collapsed, except that with `?run=` and exactly one item, that item starts
  open. Expanding renders the item with Outputs' existing ReductionCard (the item is a full reduction
  row; NeedsYou maps the response through `normalizeReduction` as Outputs.tsx:39 does, so
  ReductionCard's status pill reads 'needs-human' rather than 'in progress',
  ReductionCard.tsx:45, normalize.ts:154), plus Accept and Reject (the existing `POST
  /api/reductions/{id}/accept|reject` endpoints). Reject asks for confirmation with
  `window.confirm`, worded as Review.tsx:49 does today ('Reject this reduction? This will fail the
  tickets it is holding.'). No reason is collected or sent; the endpoint takes no body.
- While a request is in flight both buttons are disabled (one POST per item). On success the item
  leaves the list, the status region announces 'Accepted: <headline>' / 'Rejected: <headline>', and
  `/api/needs-you` and `/api/runs` are refetched, so every count refreshes. A 409 means it was
  decided elsewhere (the CLI, another tab, the committee verdict inside Summary): the status region
  announces '<run id>: decided elsewhere', the item reads 'Already decided elsewhere' with its
  buttons still disabled, and `/api/needs-you` is refetched at once; the refetch removes it, or, if
  it still returns the item, the message stays and the buttons re-enable. Any other failure shows
  the error on the item (`role="alert"`), keeps the item and re-enables the buttons.
- Live refetches (see "Keeping the page current") key items by reduction id and keep which items are
  open and the scroll position. A refetch never removes an item whose accept / reject request is in
  flight; the request's own outcome removes it and makes the announcement (accept_reduction emits
  reduction_accepted in its own commit, engine/queue.py:680-685, so the stream-triggered refetch can
  land before the POST resolves). When a refetch drops an item that is not in flight, the status
  region announces '<run id>: decided elsewhere' only if that item was open. Focus moves (next item's
  toggle, else the previous one, else the page `<h1>`) only if focus was inside the removed item.
- "Open in run" goes to `#/runs/<id>/summary`. Piece 1 adds no scroll-to-verdict: a view receives only
  `{runId, data, refetch, variant}` (PlaybookView.tsx:22-28), so there is no focus channel, and
  Summary's side column already lists the decision.
- A help line under the heading: 'A decision settles its tickets now; the run moves on when its
  master is running.' (see "Out of scope / known issues").
- The top-bar count is the number of waiting decisions across all runs (Σ `awaiting`, see "Keeping
  the page current").
- Empty: 'Nothing is waiting on you.', or with `?run=X` 'Nothing from X is waiting on you.' plus a
  'Show all runs' link.

**Activity** (`#/activity`):
- Newest first. The first page is `GET /api/events?order=desc&limit=200` plus `run` / `kind` from
  the route. "Load older" passes `before` = the smallest id shown. A page shorter than 200 hides
  "Load older" and shows 'Start of history' in its place (`hermes db prune` deletes old events).
- Live events: stream events newer than the newest loaded id that match the run / kind filters are
  prepended, deduped by id. The first load merges by id, so live events that arrived during the fetch
  are kept. Changing a filter discards the loaded pages and refetches. Rows are keyed by id and
  prepend without moving what is on screen (the list keeps the browser's default `overflow-anchor`).
  The list keeps at most 1000 rows only against live prepends: a prepend beyond that drops the
  oldest rows and brings back "Load older" (`before` = the smallest id shown). "Load older" is the
  user asking for more, so it always appends its page even past 1000 rows. When "Load older" is replaced by 'Start of
  history', focus moves to the first newly loaded row.
- Each row names its run as a link to `#/runs/<id>/summary`; an event with no run_id (crew events)
  shows '—' there.
- Filters: run (chip, from `?run=`), kind (a select as today, from `?kind=`).
- Uses the app's single event stream (its buffered `events`, passed in) instead of opening a second
  WebSocket (ActivityFeed.tsx:60).
- Empty: 'No events yet.'

**Crew** (`#/crew`): unchanged except for links. Today the drawer never shows a host's current run
(CrewDrawer.tsx:154-168) and lease cards never show their run (:387-430), though the API carries
both (server/app.py:1084-1094, client.ts `Lease.run_id`). The drawer gains a Run row
(`host.current_run` as a link to `#/runs/<run>/summary`) and each lease card a Run line
(`lease.run_id`, same link); `current_ticket` and `lease.ticket_id` become links to
`#/runs/<run>/tickets?ticket=<ticket id>`. CrewPanel loses its `runId` prop (CrewPanel.tsx:21, 208):
in a row the run id always renders, as a link, and the phase text links to the ticket (today the
ticket id is only a `title`, :196-210). CrewPanel rows are clickable `role="button"` divs that open
the drawer (:132-136), so every such link's `onClick` calls `e.stopPropagation()`: it navigates
without opening the drawer. CrewPanel's `<h2>` becomes the page's `<h1 tabIndex={-1}>` 'Crew'.

**Ticket window:** no run link (see Problem: it only opens over its own run's Tickets tab, whose
header names the run).

### Server changes

- `GET /api/runs`: existing fields unchanged; the order becomes `ORDER BY created_at DESC, id DESC`
  (today `created_at DESC` alone, server/app.py:364-365, which leaves ties to SQLite), and each row
  gains
  - `updated_at` (float epoch seconds, runs.updated_at);
  - `has_view` (bool, `view_playbook(name) is not None`, computed once per distinct playbook in the
    response, not per row: view_playbook loads the playbook and stats its asset, server/app.py:185-219);
  - `subject` (`ticket_subject(payload)` of the run's lowest-rowid ticket, from one query `WHERE rowid
    IN (SELECT MIN(rowid) FROM tickets GROUP BY run_id)`; null when the run has no tickets or
    ticket_subject returns '—', server/app.py:227-244);
  - `awaiting` (int ≥ 0: the number of the run's reductions the awaiting rule below accepts).
  The per-run ticket COUNT queries (server/app.py:373-377) become one `GROUP BY run_id, state` query.
- Awaiting rule, one module-level helper. Move the member-ticket union at server/app.py:1193-1218
  (`json.member_ticket_ids` ∪ `json.needs_human_ticket_ids`, each looked up in tickets) into a helper
  that builds one `/api/runs/{id}/reductions` row; `/api/runs/{id}/reductions`, `/api/runs`
  `awaiting` and `/api/needs-you` all use it. A reduction awaits a decision when `awaitsDecision`
  (web/src/util/reduction.ts:191-199) would accept its row: `review_state = 'pending'` and a member
  ticket is in `needs_human`. This deliberately follows Outputs' rule, not `tickets.reduction_id`
  (what accept/reject settle, engine/queue.py:661-665), so no count disagrees with Outputs. Cost
  bound: output reductions stay `pending` forever, so only runs whose grouped ticket counts include
  `needs_human > 0` have their pending reductions read and parsed; every other run gets
  `awaiting = 0` without reading any reduction JSON. `/api/needs-you` uses the same bound.
- `GET /api/needs-you` (new, `require_auth_read`, no query params): 200 with a JSON array, `[]` for an
  empty home, ordered `reductions.created_at, reductions.id` ascending. Each item is exactly a
  `/api/runs/{id}/reductions` row (`id, run_id, phase, kind, json, review_state, member_ticket_ids,
  member_tickets[{id, state, phase}]`) built by the helper above, plus `playbook` (runs.playbook)
  and `created_at` (reductions.created_at, epoch seconds), for every reduction the awaiting rule
  accepts. The server computes no headline; the client uses `reductionHeadline` (see Needs you).
- `engine/events.py`: one generic helper, stdlib only, `latest(conn, *, run_id: str|None = None,
  kind: str|None = None, before: int|None = None, limit: int = 200) -> list[dict]`, returning the
  same dict shape as `since()`, from `SELECT id, ts, kind, run_id, ticket_id, host, message,
  data_json FROM events` plus a WHERE clause built from the filters that are present (`run_id = ?`,
  `kind = ?`, `id < ?`, joined with AND; no WHERE when none) and `ORDER BY id DESC LIMIT ?`. Every
  value is a bound parameter; no value is interpolated into the SQL. (The `(? IS NULL OR id < ?)`
  form stops SQLite from using the rowid range for `before`: EXPLAIN QUERY PLAN gives 'SCAN events'
  instead of 'SEARCH … (id<?)'.) `before` is exclusive; `run_id=X` never matches a null run_id. No other
  engine change, and no index (no schema change): with `run_id` it scans newest-first until `limit`
  rows match, cheap for a live run and a full scan for an old one (only idx_events_stream and
  idx_events_ticket exist, engine/db/schema.sql:96, 121). The code carries a `ponytail:` comment
  naming an additive `idx_events_run(run_id, id)` migration as the upgrade.
- `GET /api/events` gains `order: Literal['asc','desc'] = 'asc'` (any other value is FastAPI's 422),
  `run: str|None` and `before: int|None`. `order=asc` is today's `events.since()` path, unchanged
  (since / kind / limit). An empty `run` counts as absent (`before` is an int, so an empty or
  non-integer `before` is FastAPI's 422 like any bad int). `run` or `before` with
  `order=asc` returns 400 with the detail exactly 'run and before need order=desc'; `since` ≠ 0 with
  `order=desc` returns 400 'since needs order=asc'. `order=desc` calls `latest(run, kind, before,
  limit)`; with it `limit` must be 1..1000, else 400 'limit must be between 1 and 1000' (a negative
  LIMIT is unlimited in SQLite). `limit` keeps today's default of 200.

### Keeping the page current

- Stream consumers read the shared stream event by event: `useEventStream().events`, each consumer
  keeping a last-processed event id and handling every buffered event with id > cursor, in order;
  never `lastEvent` alone. The server sends a poll's events back to back (server/app.py:2072-2079)
  and React 19 batches the updates, so `lastEvent` sees only the last event of a burst (e.g.
  `needs_human` then `attention` from one commit, engine/queue.py:351-355). `useLiveTick` changes
  the same way: `useLiveTick(events, kinds, runId?: string|null)` (today it takes `lastEvent`,
  useLiveTick.ts:39-50); with `runId` it counts only events with that run_id.
- Cursor rule, for every consumer: the cursor starts at the newest buffered event id at mount (the
  consumer's own mount fetch covers older events; starting at 0 would replay the whole 500-event
  buffer, useEventStream.ts:11), and each buffered event with id > cursor is handled once, in id
  order.
- `useStreamTrigger(events: Event[], match: (e: Event) => boolean, onTrigger: () => void, windowMs
  = 2000)` (web/src/hooks/useStreamTrigger.ts) applies the cursor rule and the throttle below, with
  its own window per instance. Instances: App's runs refetch (`e.run_id != null`); App's detail
  refetch (`e.run_id === selectedRunId`); Summary's refetch of metrics, its needs-you items and,
  when there is no view, reductions (same match); NeedsYou's `/api/needs-you` refetch
  (`e.run_id != null`). Recent events and Activity never refetch on a trigger; they merge stream
  events (see each).
- `useEventStream`'s cursor starts at the hello message's `last_id` (server/app.py:2051-2063; the
  hook ignores hello today, useEventStream.ts:64) and advances with each event; every reconnect
  passes `since` = that cursor, so a reconnect replays what it missed, including events committed
  during the 3 s backoff before any event arrived, instead of starting at `MAX(id)` and dropping
  them.
- Rail trigger: any stream event whose `run_id` is non-null. That covers every event kind that
  changes a rail row, the count or the header: the run transitions (run_paused, run_resumed,
  run_stopped, run_done, run_failed, run_reopened, engine/queue.py:26-37, 615); a new run, whose
  first event is `phase_advanced` from null (engine/cli.py:386; `run_started` is declared at
  engine/events.py:13 but never emitted); needs_human; reduction_created / accepted / rejected; an
  operator's ticket_requeued or ticket_abandoned of a needs_human ticket (changes `awaiting`); and
  the ticket events that move the progress bars. Not every change has an event:
  `finish_phase_reductions` moves a phase's reducing tickets to done in its own commit after
  reduction_created, with no event (engine/queue.py:951-972). The trailing refetch below picks it up.
  Crew events carry no run_id and do not trigger.
- Throttle (leading + always trailing): on the first trigger the refetch runs at once and a 2000 ms
  window opens; one trailing refetch always runs at the end of the window, even if no second
  trigger arrived, so a silent commit such as finish_phase_reductions' reducing → done is picked up.
  A trigger after the window has closed starts a new cycle. So N ≥ 1 triggers within one window
  cause exactly one immediate and one trailing refetch. A refetch keeps the previous data (see State
  ownership).
- The top-bar count = Σ `awaiting` over that same unfiltered `/api/runs` response. There is no
  separate count fetch, so the count and the rail never disagree.
- The run pane refetches the selected run's detail, and Summary its metrics, needs-you items and
  (without a view) reductions, on the rail trigger restricted to events whose `run_id` is the
  selected run: two `useStreamTrigger` instances, App's detail refetch and one Summary instance that
  refetches its metrics, needs-you items and (without a view) reductions together. Summary's and the Metrics tab's PlaybookView
  refresh on `viewTick` (see Summary). This replaces today's kind list (App.tsx:108-117), which has
  no run_* kinds and no reduction_accepted / rejected, so the header kept saying 'running' after a
  run ended. The header reads the refetched `/api/runs` row, so its state, phase, progress, ⚑ count
  and controls follow the run.
- The Needs you page refetches `/api/needs-you` on the rail trigger (its own throttle) and right
  after its own accept / reject resolves (refetching `/api/runs` too).
- The run pane's body is keyed on the run id, and every per-run fetch in it (detail, metrics,
  reductions, needs-you items, recent events, view data) drops a response whose run is no longer
  selected (fixes the race in App.tsx:64-70, 119-123).

**State ownership:**
- App owns the route (`useRoute`), the single `useEventStream`, the runs list, the selected run's
  detail, `lastRunTab`, the rail's view state and `announce`. `useRuns()` returns `{data, error,
  loading, refetch}`; `refetch` keeps the previous data and never sets `loading` back to true
  (useApi.ts:45-73 fetches once today). Each runs fetch takes a sequence number, and a response older
  than the newest one already applied is dropped (the throttle, RunControl's success and
  `onDecided` can overlap). The detail fetch is keyed on the resolved selected run id, not on the
  `runs` array (today's effect, App.tsx:75-80, would refetch the detail on every rail refetch).
- The pane body renders only when `detail.id` equals the selected run id. On a selection change App
  clears the detail; until the new one arrives the body shows a LoadingOverlay inside the body (the
  header is already drawn from the row), so it never renders the previous run's tiles, phases, view
  or board. If the detail fetch fails, see Errors.
- The global loading overlay covers health and the first runs load only; the global error covers
  health only. A runs error, first load or later, shows only in the rail (see Errors).
- Rail view state, `useRailState()` (in App) → `{hidden: ReadonlySet<string>, setHidden, filter:
  string, setFilter, showAllFinished: boolean, setShowAllFinished, collapsed: boolean,
  setCollapsed}`. It persists `hidden` and `collapsed` as specified under Layout, each with an
  in-memory fallback when `localStorage` throws; `filter` and `showAllFinished` are not persisted.
- `railGroups(runs: Run[], hidden: ReadonlySet<string>, filter: string, showAllFinished: boolean,
  selectedId: string|null): {needsYou: Run[]; active: Run[]; finished: Run[] /* already capped,
  plus the selected run when it falls beyond the cap */; moreFinished: number; hiddenCount: number;
  hiddenAwaiting: number}`. The visible order is `[...needsYou, ...active, ...finished]`. App
  computes the groups once per render and derives from them `[` / `]`, RunHeader's
  `prevHref` / `nextHref` and (with `defaultRunId`) the default run.
- `RunRail({groups, playbooks: string[], rail: ReturnType<typeof useRailState>, error, onRetry,
  selectedRunId: string|null, tab, filterRef: RefObject<HTMLInputElement>})` is presentational.
  `/` calls `rail.setCollapsed(false)` and focuses `filterRef.current` in an effect after that
  render.
- `RunHeader({run: Run | RunDetail, prevHref: string|null, nextHref: string|null, onRunUpdate})`:
  `run` is the selected run's `/api/runs` row (it carries `awaiting`), or the detail when there is
  no row (no ⚑ then).
- `Summary({run: RunDetail, streamEvents, viewTick})` fetches metrics, this run's needs-you items,
  recent events, and reductions (only when there is no view).
- `announce(message: string): void` sets the text of the shell's single status region.
- `NeedsYou({runFilter: string|null, streamEvents, onDecided, announce})` fetches `/api/needs-you`;
  `onDecided` refetches `/api/runs`.
- `ActivityFeed({runFilter, kindFilter, streamEvents})` does not call `useEventStream`.
- `CrewPanel` loses its `runId` prop.
- Types (web/src/api/client.ts): `Run.phase: string|null`; `Run.created_at` and `updated_at:
  number` (epoch seconds, typed as strings today, client.ts:32); `Run` gains `updated_at`,
  `has_view`, `awaiting` and `subject: string|null`; `RunDetail = Omit<Run, 'awaiting' | 'subject'>
  & {config: Record<string, any>; phases: Phase[]}` (`/api/runs/{id}` returns neither `awaiting`
  nor `subject`).

### Errors

- Run list fails to load (first load or a refetch): the rail shows the error (`role="alert"`) and
  Retry, which calls `refetch`; the top bar and cross-run pages still work, and a run route's pane
  fetches its run directly (see Addresses). A refetch that fails after a success keeps the last rows
  and adds the alert and Retry above them; the next success clears the alert.
- Run detail fails to load: the pane body shows an inline error (`role="alert"`) with Retry; the
  header still renders from the row.
- A Summary sub-fetch (metrics, needs-you items, recent events, reductions) fails: that block shows
  an inline error (`role="alert"`) with Retry, and the rest of Summary renders.
- Unknown run in the address: the note above, then the default run.
- Accept/reject failure: a 409 refetches the list; any other error shows inline on the item, item
  kept (see Needs you).
- Needs you or Activity fetch failure: an inline error (`role="alert"`) with Retry on that page.

### States with nothing in them

- No runs: the rail shows 'No runs yet' in place of the filter, chips and groups; the pane shows
  today's empty state reworded 'No runs yet. Start one with `hermes run <playbook>`.'
  (App.tsx:217-225), with no run header (so no ‹ ›); `#/runs` and every legacy run hash land there.
  `/` does nothing. A hash that names a run shows the "isn't in this home" note above the empty
  state and is left alone. When a refetch turns an empty list into a non-empty one and the hash
  names no run (empty, `#/`, `#/runs`, or a legacy hash with no run), normalisation runs then and
  replaces the hash with the default run's summary.
- A run with no phase (runs are inserted with phase NULL before `set_run_phase`,
  engine/cli.py:316-319, 382-386) shows 'starting' while running or paused. With 0 tickets the
  progress bar shows an empty track and 'no tickets yet'. Dry-run leftovers (stopped, 0 tickets, 0
  events, engine/cli.py:348-357) already have their first phase (set at engine/cli.py:386, before the
  dry-run branch at :407-418), so they show that phase, 'stopped' and 'no tickets yet' with the same
  empty track; 'not started' appears only for a finished run whose phase is still null.
- Summary numbers with no results show '—'. The empty texts of Summary's side column, Needs you and
  Activity are given with each.

### Accessibility

- Landmarks: the rail is a `<nav aria-label="Runs">`; the right side (run pane or cross-run page) is
  `<main>`. The first focusable element in the shell is a 'Skip to content' link, visually hidden
  until focused, that moves focus to the `<h1>` in `<main>`. Every state of `<main>` has one: the run
  header's, each cross-run page's, and the empty states ('No runs yet', 'Couldn't load runs.'), which
  render their title as `<h1 tabIndex={-1}>`.
- The rail has list semantics; groups have headings. Each row is one `<a href="#/runs/<id>/<tab>">`
  in an `<li>`, with the accessible name '<id>, <playbook>, <state>[, N waiting on you]' and
  `aria-describedby` pointing at its phase, age, progress text and subject. The selected row has
  `aria-current="page"` and a non-colour cue (a 2px leading bar and a bold id). Each state icon has
  its own shape per state and a text label (`aria-label` and `title`, see Layout). A progress bar
  with tickets is `role="progressbar"` with `aria-valuenow` / `aria-valuemax` / `aria-valuetext`; with
  0 tickets there is none (see Header).
- Run tabs and top-bar items are links with `aria-current="page"`, not an ARIA tablist.
- Shortcuts follow the guard in "Moving between runs"; every control is reachable by keyboard with a
  visible focus ring.
- Headings: the run pane's `<h1>` is the header's `<id> · <playbook>`; each cross-run page renders
  `<h1 tabIndex={-1}>` reading 'Needs you', 'Activity' or 'Crew' (no page has an `<h1>` today).
- Focus:
  - A rail click leaves focus on the clicked link. `[` / `]`: if focus is on a rail row, it moves to
    the newly selected row; otherwise it stays where it was, or goes to the run header's `<h1>` if
    that element is gone. Either way the status region announces '<id>, <playbook>, <state>'.
  - ‹ › keep focus on the activated link (at an end it is `aria-disabled`, so it stays focusable).
  - A route change that stays on the same page leaves focus where it was: a run-tab link, the kind
    select, opening the ticket window. If the focused control disappears (a removed chip), focus goes
    to the page `<h1>`. Closing the ticket window returns focus to the ticket card that opened it.
  - Only arriving at a different page (top-bar items, cross-run links, "Open in run", Crew links,
    Back / Forward to another page) moves focus to its `<h1>`, without scrolling the rail. The first
    load moves no focus.
  - When a rail refetch removes the focused row from its group (Active → Needs you, Active →
    Finished, or behind the Finished cap), focus moves to the same run's row if it is still visible,
    else to the row now in its old position in that group, else to the filter box. The rail does not
    scroll.
  - After accept / reject removes an item, focus moves to the next item's toggle, else the previous
    one, else the page `<h1>`. After "show N more", focus moves to the first newly shown row.
- Announcements: one visually hidden `role="status"` (polite) region in the app shell, written only
  through `announce`, announces:
  - the top-bar count ('N decisions waiting on you'). The first successful `/api/runs` load sets the
    baseline and announces nothing. A later response whose Σ `awaiting` is higher than the last
    announced value announces it, at most once per 10 s; a rise inside the window is announced once
    at the window's end, with the count at that moment, if it is still higher than the last
    announced value;
  - accept / reject success ('Accepted: <headline>' / 'Rejected: <headline>') and '<run id>: decided
    elsewhere' (see Needs you);
  - the selected run's state ('<id> failed'), only when two consecutive `/api/runs` rows for the
    same run id differ in state; never on a selection change or the first load;
  - the `[` / `]` selection and the "isn't in this home" note.
  Errors use `role="alert"` on their inline element. The rail and the Activity list are not live
  regions (today's only live regions are the Spinner's two `role="status"` elements,
  Spinner.tsx:24, 63-64).

### Tests

- Vitest:
  - route parse/build round-trip, id encoding without case-folding, normalisation by replaceState
    (bare `/`, `#/runs/<id>`, unknown tab, unknown route, trailing `/`, stray params), every legacy
    conversion on load and on hashchange (incl. ticket with no run), unknown-run fallback after one
    refetch, a route naming a run created after the list loaded opens it with no note, default-run
    rule, `buildRoute` throwing for a `runId:null` route other than `#/runs`, a legacy `#metrics`
    landing on the default run's Metrics once the list loads, an empty query value, a foreign
    `?ticket=` dropped, case-insensitive page segments, the list-failed `#/runs` case;
  - `railGroups` (one group per run, Needs you wins, Needs you / Active by `created_at`, Finished by
    `updated_at`, ties by id, the Finished cap and "show N more", filter text lifting the cap, a
    selected run beyond the cap shown after the 10 and left out of the count, empty groups omitted),
    `defaultRunId`, filter box (Enter, Escape), hidden-playbook chips in `localStorage` (a new
    playbook is shown; an unparsable value; `aria-pressed`), the "N hidden" line (N runs, M
    decisions), collapse persistence ('1', '0' and absent, each at a narrow and a wide
    `innerWidth`; `/` writing '0'), the collapsed strip's count, `[` `]` `/` including every guard
    case (AltGr allowed, Meta blocked), the ends and the hidden-selected case, a deep link to the
    30th finished run shows and highlights its row and `]` moves to the next older visible row, a
    held `]` creates one history entry, `aria-current`, `fmtAgo` ('just now', minutes, hours, days,
    a negative difference);
  - run header (verbatim state label, 'starting' / 'not started', elapsed for a finished run,
    progress and caption incl. 0 tickets with no progressbar, ⚑ link, no ⚑ on the detail fallback,
    controls, ‹ › labels and disabled ends); a `run_failed` event for the selected run relabels the
    header 'failed', leaves no Pause / Stop enabled and shows Reopen; an open Stop confirmation does
    not survive `]`; focus moves to Resume after Pause succeeds; a `reduction_accepted` for it
    clears ⚑;
  - Summary for a playbook with a view (renders the view, which refetches on `viewTick`) and without
    (phase timeline with headlines; 'No phases yet.'); the top strip incl. '—' with 0 results; the
    side column's items and recent events (stream merge keeps 10); a failed sub-fetch shows its own
    alert; after a switch the body never renders the previous run's detail; a failed detail fetch
    shows the alert and Retry under the header;
  - Needs you across runs: group and item order, group header state, run filter chip, a single
    `?run=` item starts open, expand into ReductionCard with a 'needs-human' status pill, accept and
    reject success and their announcements, the reject confirm text, the 409 path (announced; the
    item stays until the refetch), another failure, buttons disabled in flight, open items kept
    across a refetch, a refetch arriving before the accept resolves announces Accepted and not
    decided elsewhere, focus kept when another item is removed;
  - Activity newest first, "Load older" and 'Start of history' (focus to the first new row), run and
    kind filters, run links, a null run_id, live prepend drops no event of a burst, the 1000-row cap,
    single stream;
  - live refresh (fake timers): two events delivered in one `act()`, the first run-affecting,
    trigger a refetch; N ≥ 1 triggering events within 2 s cause exactly one immediate and one
    trailing `fetchRuns`; a crew event (null run_id) causes none; a consumer mounted after events
    were buffered replays none of them; the stream's cursor starts at hello's `last_id` and a
    reconnect resumes with `since`; an older `/api/runs` response arriving after a newer one is
    dropped; a first run appearing while the home is empty opens it;
  - focus and announcements: `[` / `]` on a rail row moves focus to the new row and announces it; a
    run-tab click keeps focus; closing the ticket window returns focus to its card; a removed chip
    sends focus to the `<h1>`; the focused row moving from Active to Needs you keeps focus on that
    run's row; the first load announces no count; a rise inside 10 s is announced at the window's
    end; selecting a finished run announces no state; the skip link reaches `<main>`'s `<h1>`;
  - Crew and crew-drawer run and ticket links (drawer Run row, lease Run line), and a link click in
    a CrewPanel row does not open the drawer;
  - stale per-run responses (detail, metrics, needs-you items, events) are discarded after a quick
    switch.
- Pytest: `/api/runs` new fields and types (incl. `awaiting` against a seeded pending reduction
  holding a needs_human ticket, `subject` mapped to null, `has_view` computed once per playbook);
  the SQL statement count of one `GET /api/runs` (`sqlite3.Connection.set_trace_callback` on a
  monkeypatched `server.app.connect`) is the same for 1 and 5 runs with no needs_human tickets;
  `/api/needs-you` (cross-run, oldest first, items carry the full reduction row, an accepted
  reduction and a pending one holding no needs_human ticket are excluded, empty home); `/api/runs`
  order with two runs sharing a `created_at` (id descending); `/api/events` `run` + `kind` +
  `before` combined, each 400 case with its exact detail, `limit` 0 / -1 / 1001 with order=desc, an
  empty `run`, the 422, a short final page, and the unchanged default; `engine.events.latest` (each
  filter, exclusive `before`, null run_id never matching, values bound, never interpolated).
- Playwright (throwaway container): the new scenario goes in web/tests-ui/committee-view.spec.ts,
  the only file `make ui-test-committee` runs (Makefile:103; shell.spec.ts and screenshots.spec.ts
  run only under `make ui-test` against a live server). Its `seed()` (today only runs and
  reductions, :154-182) must stay idempotent: `E2E_HOME` persists between runs (Makefile:95),
  node:sqlite turns foreign keys on, and `tickets.reduction_id` references reductions with no ON
  DELETE (engine/db/schema.sql:30), so deleting the reductions first would fail on the second run.
  `seed()` first runs `DELETE FROM tickets WHERE run_id = ?`, then the existing reductions / runs
  deletes. It inserts the decision reduction with its json extended by `needs_human_ticket_ids:
  [`${RUN}/decision`]` and takes its id from that `insert.run(...).lastInsertRowid`. Then it inserts
  a tickets row: id `${RUN}/decision`, run_id RUN, phase `decision`, state `needs_human`,
  `reduction_id` = that id, `created_at` = `updated_at` = now; the other columns keep their
  defaults. So a decision is waiting. The same seed also writes (deleting it first) a run
  `${RUN}-live` in state `running`, phase `work`, with no tickets. Run A is RUN and run B is
  `${RUN}-live`. Because RUN's decision now holds a needs_human ticket, accepting its verdict in the
  existing committee-view tests also settles that ticket: those tests must still pass (adjust any
  count they pin, and say so in the commit). Steps: select run A, then run B
  in the rail; switch B's tab (still B); Back goes to B's previous tab; Back again goes to run A; open
  Needs you, expand the decision, "Open in run" lands on its Summary; then, through `DatabaseSync`,
  update `${RUN}-live` to state `done` and insert an events row (kind `run_done`, run_id
  `${RUN}-live`, ts now); its rail row moves from Active to Finished within 4 s, with no reload.
- Tests that change:
  - App.test.tsx: :142 ('should show Run tab'); :282-306 ('does not name the run in view on a host
    working on it') and CrewPanel.test.tsx:109 ('naming the run only when it is not the one in view')
    are replaced by 'a host's current run links to `#/runs/<id>/summary` and its ticket to
    `#/runs/<id>/tickets?ticket=<t>`'; :308-321 (expects '#crew'); :324-482, the 'the playbook tab'
    describe (tab-playbook, tab-run, run-picker at :409, :415, :443: absent / present / fallback /
    'keeps the Run tab lit' / remount / finding tick), replaced by Summary cases incl. "Summary shows
    the playbook view for a run that has one"; :542 (run-picker); :92 expects 'No runs yet' and
    :108 expects the header 'run-001 · example' (the spec rewords the empty state and removes the
    'example run' text they expect today).
  - App.test.tsx and App.metrics.test.tsx auto-mock the whole client module (`vi.mock('./api/client')`,
    App.test.tsx:8; App.metrics.test.tsx:15), so every unstubbed client function returns undefined
    and Summary's fetches would throw. Their `beforeEach` also stubs `fetchNeedsYou` → `[]`,
    `fetchEvents` → `[]`, `fetchEventKinds` → `[]`, `fetchCrew` → `[]` and `fetchRunMetrics` → a
    zero RunMetrics.
  - `tsc` includes test files (web/tsconfig.app.json includes `src`), so every Run / RunDetail
    fixture (App.test.tsx :51, 122, 156, 205, 257, 341, 499; App.metrics.test.tsx :46-58, 64-72;
    client.test.ts:61; Summary.test.tsx; TopBar.test.tsx) gains numeric `created_at` / `updated_at`,
    `has_view`, `awaiting` and `subject` (RunDetail fixtures omit the last two).
  - App.metrics.test.tsx:87 ('#metrics') and :102 (run-picker) become the new route and a rail-row
    click.
  - TopBar.test.tsx:36-48, 50-95, 118-144 (the tab list, the run picker and the Playbook tab).
  - useHashView tests become the route tests, keeping d978a44's intent (switching tabs keeps the
    run).
  - useLiveTick.test.ts moves to the `events` + cursor signature; useEventStream.test.ts (:204
    covers `since`) adds hello's `last_id` as the starting cursor and reconnect-resumes-with-since.
  - CrewPanel.test.tsx:110, 128, 277 drop `runId` (an excess prop is a type error);
    CrewDrawer.test.tsx:36 gains the Run row link.
  - RunOverview.test.tsx → Summary.test.tsx; Review.test.tsx → NeedsYou.test.tsx;
    ActivityFeed.test.tsx for paging, filters and the passed-in stream; PlaybookDialog.test.tsx is
    deleted with its component.
  - committee-view.spec.ts :456 and :602 (`tab-playbook`) become checks that the view renders in
    `#/runs/<id>/summary`; the legacy hashes it sets mid-session at :601 and :603 now convert on
    hashchange.

### Acceptance criteria

1. With the filter box empty, every run whose playbook chip is on belongs to exactly one rail group
   (Needs you / Active / Finished), visible without opening a menu except Finished rows beyond its
   newest 10, which sit behind "show N more"; selecting a run keeps the current run tab.
2. The run pane always names the selected run (id, playbook, state) in its header, and the header's
   state follows the run within the bound of AC9.
3. `[` / `]` / `/` work as specified and never fire while typing, with Meta held, with Ctrl held
   but not AltGr, or under an open modal; they do fire when the layout needs AltGr or Option for the
   key.
4. Every route in the table round-trips through refresh and Back/Forward; every legacy hash converts
   on load and on hashchange; an unknown run (still absent after one refetch) shows the note and the
   default run.
5. Summary is present for every run; a playbook's view renders inside it; no tab appears or
   disappears when switching runs.
6. Needs you lists every waiting decision across runs; accept and reject work inline; "Open in run"
   lands on the run's Summary; the top-bar count is cross-run and equals Σ `awaiting`.
7. Activity is newest first, pages older events, names and links each event's run, and filters by
   run and kind; it opens no second WebSocket.
8. Crew and the crew drawer link to runs and tickets.
9. (vitest, fake timers) N ≥ 1 triggering events within 2 s cause exactly one immediate and one
   trailing `fetchRuns`; an event with no run_id causes none; every event of a burst delivered in one
   render is handled. In the running app the rail reflects a run starting, changing phase, waiting on
   the user or ending within 4 s (≤ 1 s WebSocket poll, engine/config.py:114-116, + ≤ 2 s throttle
   window + the fetch), with no reload; the Playwright step that ends `${RUN}-live` checks it.
10. `engine/` gains only `events.latest`. Piece 1's diff adds no playbook name (string literal,
    identifier or comment) to server/ or to non-test files under web/src: the added lines of `git diff
    d978a44 -- server web/src ':!*.test.*' ':!web/src/ds'` contain none of dexter, research,
    committee (which covers committee-eval) or the string literal 'example'. The adapter-registration
    imports at server/app.py:275-280 already exist and are out of scope. After the deletions under
    Summary, no string literal in web/src production code names a playbook. GETs need no token on
    loopback; mutations need it.
11. pytest, vitest, tsc and oxlint pass, and `make ui-test-committee` passes against a throwaway
    image.

### File map (expected)

- web/src/hooks/useHashView.ts → replaced by web/src/hooks/useRoute.ts (parseRoute / buildRoute,
  normalisation, legacy conversion on load and on hashchange).
- web/src/views/TicketBoard.tsx → reads and sets the open ticket through the route API. Today's
  `useHashParam('ticket')` (TicketBoard.tsx:20, 201) rebuilds `#<view>?…` (useHashView.ts:137-151)
  and would rewrite `#/runs/X/tickets?ticket=T` to `#overview?ticket=T`.
- web/src/App.tsx → rail + pane layout, the state ownership above, default-run rule, stale-response
  guard, throttled runs refetch, cross-run count, the status region.
- web/src/hooks/useApi.ts → `useRuns` gains `refetch`.
- web/src/hooks/useEventStream.ts → reconnect resumes with `since`; web/src/hooks/useLiveTick.ts →
  reads `events` with a cursor.
- New: web/src/components/RunRail.tsx (with `railGroups`, `defaultRunId` and `useRailState`),
  RunHeader.tsx; web/src/views/Summary.tsx (from RunOverview.tsx), NeedsYou.tsx (from Review.tsx);
  web/src/hooks/useStreamTrigger.ts, useNow.ts. Summary.tsx rewords RunOverview.tsx:47's
  PhaseTimeline comment ("a sentinel such as research's `complete`") to "a zero-ticket sentinel
  phase"; no added comment or string names a playbook (the ‹ › label comment says "a view's own Prev
  button", not the committee view), so AC10's grep holds.
- web/src/util/time.ts → `fmtAgo`. web/src/index.css → Summary's two-column class and its
  `@media (max-width: 1023px)` rule, and the visually hidden class for the status region and the skip
  link. web/src/components/RunControl.tsx → focus after a state change (nothing else).
- Deleted: web/src/components/PlaybookDialog.tsx and its test; `deriveContext` and
  `PLAYBOOK_CONTENT` in web/src/api/normalize.ts.
- web/src/components/TopBar.tsx → cross-run pages only; the copy-pasted tab buttons become one map.
- web/src/views/ActivityFeed.tsx → paging, filters, passed-in stream, run links;
  web/src/views/CrewPanel.tsx (drops `runId`) and components/CrewDrawer.tsx → run and ticket links.
- web/src/api/client.ts → new endpoint clients (`fetchNeedsYou`, the `fetchEvents` options); the
  `Run` / `RunDetail` types under State ownership (`Run` gains `updated_at`, `has_view`, `awaiting`,
  `subject`; `phase` becomes nullable; `created_at` / `updated_at` become numbers, since they are
  epoch seconds).
- server/app.py → `/api/runs` fields, the awaiting helper, `/api/needs-you`, `/api/events` params.
- engine/events.py → `latest`.
- Tests: web/src/**/*.test.tsx, tests/unit/test_*server*/api tests,
  web/tests-ui/committee-view.spec.ts.

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
- Piece 1 has no master-liveness signal. Accept and reject record the decision whether or not the
  run's master is alive (engine/queue.py:639-687), and the run moves to its next phase or to done
  only when a master drives it (engine/dispatch.py:243-314), so a run whose master exited stays in
  Active with its last state. Needs you's help line says so.

## Clarifications (answered 2026-09-28/29, in conversation; binding)

- The user's jobs: see what needs them across runs, watch a live run, read a finished run, compare runs, read high-level numbers about a run.
- Layout: runs rail + run pane (chosen over a home dashboard and over keeping top tabs).
- Compare shows key numbers, eval scores, outcomes, plus a judged comparison with lessons (piece 2/3).
- Automatic score + compare, a Settings tab switch, default on; trigger when a run delivers its decision; baseline = best-scoring earlier run of the same playbook on the same input; lessons shown only (piece 3).
- Needs you across runs: preview and rule inline AND "open in run".
- Build order: piece 1 -> piece 2 -> piece 3; this pipeline builds PIECE 1 ONLY. Pieces 2 and 3 are recorded decisions, not in scope here.
- No placeholders in piece 1: the Compare checkboxes/button come with piece 2, the Score-and-lessons box with piece 3, the Settings tab with piece 3.
- Branch: `runs-view`, stacked on `fix-run-kept-across-tabs` (d978a44) on top of the committee branches; never merge or push; never restart/deploy 44102.
