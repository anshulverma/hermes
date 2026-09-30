/**
 * The control plane shell: the top bar's cross-run pages, the runs rail, and
 * beside it the run pane or a cross-run page.
 *
 * App owns the route, the one event stream, the runs list, the selected run's
 * detail, the last run tab used, the rail's view state and the shell's single
 * status region (`announce`). The rail and the pane render what it hands them.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { CSSProperties, MouseEvent as ReactMouseEvent, ReactNode } from 'react';
import TopBar from './components/TopBar';
import RunRail, { defaultRunId, railGroups, useRailState } from './components/RunRail';
import Summary from './views/Summary';
import RunHeader from './components/RunHeader';
import MetricsView from './views/MetricsView';
import TicketBoard from './views/TicketBoard';
import CrewPanel from './views/CrewPanel';
import Outputs from './views/Outputs';
import PlaybookView from './views/PlaybookView';
import NeedsYou from './views/NeedsYou';
import ActivityFeed from './views/ActivityFeed';
import TokenLogin from './components/TokenLogin';
import { useHealth, useRuns } from './hooks/useApi';
import { useEventStream } from './hooks/useEventStream';
import { useLiveTick, TICKET_EVENT_KINDS, CREW_EVENT_KINDS, FINDING_EVENT_KINDS } from './hooks/useLiveTick';
import { useStreamTrigger } from './hooks/useStreamTrigger';
import { useRoute, buildRoute, type Route, type RunTab } from './hooks/useRoute';
import { Button, CrewBackdrop } from './ds';
import { LoadingOverlay } from './components/Spinner';
import { fetchRun } from './api/client';
import type { Event, Run, RunDetail } from './api/client';
import { hasToken, isRemote } from './api/auth';

/** The run tabs, identical for every run of every playbook. */
const RUN_TABS: { tab: RunTab; label: string }[] = [
  { tab: 'summary', label: 'Summary' },
  { tab: 'tickets', label: 'Tickets' },
  { tab: 'outputs', label: 'Outputs' },
  { tab: 'metrics', label: 'Metrics' },
];

/** Input types a shortcut may fire from: none of them take typed text. */
const NON_TEXT_INPUTS = new Set(['checkbox', 'radio', 'button', 'submit', 'reset', 'range', 'color', 'file']);
/** At most one count announcement per window. */
const COUNT_WINDOW_MS = 10_000;
const RAIL = 'nav[aria-label="Runs"]';

/** The rail's live trigger: every event that names a run (crew events name none). */
const touchesARun = (e: Event) => e.run_id != null;

/** Typing here must not fire a shortcut. */
function isTextEntry(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.closest('[contenteditable]:not([contenteditable="false"])')) return true;
  if (target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return true;
  return target instanceof HTMLInputElement && !NON_TEXT_INPUTS.has(target.type);
}

/**
 * The run `[` (dir -1) or `]` (dir 1) selects in the rail's visible order. No
 * wrap-around; when the rail hides the selected run, `]` selects the first
 * visible row and `[` the last.
 */
function stepRun(visible: Run[], runId: string | null, dir: -1 | 1): Run | null {
  const i = visible.findIndex((r) => r.id === runId);
  if (i === -1) return visible.length ? visible[dir === 1 ? 0 : visible.length - 1] : null;
  return visible[i + dir] ?? null;
}

function sameRunRoute(a: Route, b: Route): boolean {
  return a.page === 'run' && b.page === 'run' && a.runId === b.runId && a.tab === b.tab && a.ticket === b.ticket;
}

function tabStyle(current: boolean): CSSProperties {
  return {
    padding: '6px 12px',
    fontSize: 13,
    textDecoration: 'none',
    color: current ? 'var(--text-primary)' : 'var(--text-muted)',
    background: current ? 'var(--wash-subtle)' : 'transparent',
    borderRadius: 'var(--radius-md)',
  };
}

/** The skip link: straight to the page's <h1>, without touching the address. */
function skipToContent(e: ReactMouseEvent<HTMLAnchorElement>) {
  e.preventDefault();
  document.querySelector<HTMLElement>('main h1')?.focus();
}

/** A pane with nothing else to show; its title is the page's <h1>. */
function PaneMessage({ title, description }: { title: string; description?: string }) {
  return (
    <div
      style={{
        padding: 32,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 12,
        textAlign: 'center',
      }}
    >
      <h1
        tabIndex={-1}
        style={{ margin: 0, fontSize: 'var(--text-h3-size)', fontWeight: 500, color: 'var(--text-secondary)' }}
      >
        {title}
      </h1>
      {description && <p style={{ margin: 0, maxWidth: 380, color: 'var(--text-muted)' }}>{description}</p>}
    </div>
  );
}

export default function App() {
  const [authenticated, setAuthenticated] = useState(hasToken() || !isRemote());

  const { loading: healthLoading, error: healthError } = useHealth();
  const { data: runs, loading: runsLoading, error: runsError, refetch: refetchRuns } = useRuns();
  const { route, navigate, replace } = useRoute();
  const rail = useRailState();
  const filterRef = useRef<HTMLInputElement>(null);

  // The one WebSocket: every live consumer reads its buffered events.
  const { connected, events, authError } = useEventStream();
  const [authErrorDismissed, setAuthErrorDismissed] = useState(false);

  // The shell's single status region, written only through announce. Each call
  // gets a new key, so the region's text is replaced and read out even when it
  // repeats the last announcement.
  const [status, setStatus] = useState({ text: '', n: 0 });
  const announce = useCallback((message: string) => setStatus((s) => ({ text: message, n: s.n + 1 })), []);

  const selectedId = route.page === 'run' ? route.runId : null;

  // A rail row on a cross-run page opens the last run tab used this session.
  const [lastRunTab, setLastRunTab] = useState<RunTab>('summary');
  if (route.page === 'run' && route.tab !== lastRunTab) setLastRunTab(route.tab);

  const ticketLiveTick = useLiveTick(events, TICKET_EVENT_KINDS);
  const crewLiveTick = useLiveTick(events, CREW_EVENT_KINDS);
  // The selected run's own reductions, so its view's transcript and verdict stay live.
  const viewTick = useLiveTick(events, FINDING_EVENT_KINDS, selectedId);

  // Initialize lucide icons after mount
  useEffect(() => {
    if (typeof window !== 'undefined' && (window as any).lucide) {
      (window as any).lucide.createIcons();
    }
  }, []);

  // The selected run's detail, fetched per selected id, never per list refetch.
  // A response for a run no longer selected is dropped, and the body renders
  // only a detail whose id is the selected one, so it never shows the last run.
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [detailError, setDetailError] = useState<{ id: string; error: Error } | null>(null);
  const [detailNonce, setDetailNonce] = useState(0);
  const refetchDetail = useCallback(() => setDetailNonce((n) => n + 1), []);

  useEffect(() => {
    if (!selectedId) return;
    let live = true;
    fetchRun(selectedId)
      .then((d) => {
        if (!live) return;
        setDetail(d);
        setDetailError(null);
      })
      .catch((error: Error) => {
        if (live) setDetailError({ id: selectedId, error });
      });
    return () => {
      live = false;
    };
  }, [selectedId, detailNonce]);

  const onRunUpdate = useCallback(() => {
    refetchRuns();
    refetchDetail();
  }, [refetchRuns, refetchDetail]);

  // Live: any event naming a run refetches the list (rail, count, header); the
  // selected run's own events refetch its detail. Each has its own throttle.
  useStreamTrigger(events, touchesARun, refetchRuns);
  const touchesSelected = useCallback(
    (e: Event) => selectedId !== null && e.run_id === selectedId,
    [selectedId],
  );
  useStreamTrigger(events, touchesSelected, refetchDetail);

  const groups = useMemo(
    () => railGroups(runs ?? [], rail.hidden, rail.filter, rail.showAllFinished, selectedId),
    [runs, rail.hidden, rail.filter, rail.showAllFinished, selectedId],
  );
  const visible = useMemo(() => [...groups.needsYou, ...groups.active, ...groups.finished], [groups]);
  const playbooks = useMemo(() => [...new Set((runs ?? []).map((r) => r.playbook))].sort(), [runs]);
  // Unfiltered, and from the same response as the rail, so the two never disagree.
  const needsYouCount = runs ? runs.reduce((sum, r) => sum + r.awaiting, 0) : null;

  const row = runs?.find((r) => r.id === selectedId) ?? null;
  const paneDetail = detail && detail.id === selectedId ? detail : null;
  const paneError = detailError && detailError.id === selectedId ? detailError.error : null;
  // Drawn from the list row at once; from the detail when the list failed.
  const headerRun: Run | RunDetail | null = row ?? paneDetail;
  // ‹ › go where `[` / `]` go (stepRun), on the same run tab, dropping `?ticket=`.
  const stepHref = (dir: -1 | 1) => {
    const to = stepRun(visible, selectedId, dir);
    return to && route.page === 'run' ? buildRoute({ ...route, runId: to.id, ticket: null }) : null;
  };

  // "<id> isn't in this home", shown until the next route change.
  const [note, setNote] = useState<{ id: string; route: Route } | null>(null);
  const unknownCheck = useRef<{ id: string; runs: Run[]; error: Error | null } | null>(null);

  // The default run for an address that names none, and a named run the list
  // does not have. Checked against the full list, only once it has loaded.
  useEffect(() => {
    if (route.page !== 'run' || !runs) return;
    const fallback = defaultRunId(runs, rail.hidden);
    if (route.runId === null) {
      if (fallback) replace({ ...route, runId: fallback });
      return;
    }
    if (runs.some((r) => r.id === route.runId)) {
      unknownCheck.current = null;
      return;
    }
    // Runs are never deleted, so a missing one was almost always created after
    // the list loaded: refetch once before calling it unknown.
    const check = unknownCheck.current;
    if (!check || check.id !== route.runId) {
      unknownCheck.current = { id: route.runId, runs, error: runsError };
      refetchRuns();
      return;
    }
    // A refetch that answers sets a new `data` array; one that fails keeps the
    // old array and sets a new error. Either means the one refetch is done.
    if (check.runs === runs && check.error === runsError) return; // not answered yet
    unknownCheck.current = null;
    const next: Route = fallback ? { ...route, runId: fallback, ticket: null } : route;
    setNote({ id: route.runId, route: next });
    announce(`${route.runId} isn't in this home`);
    if (fallback) replace(next);
  }, [route, runs, runsError, rail.hidden, refetchRuns, replace, announce]);

  // The list failed, so the pane asked for its run directly: a 404 means this
  // home has no such run. The address is left alone.
  useEffect(() => {
    if (runs || !runsError || !detailError || route.page !== 'run' || detailError.id !== route.runId) return;
    if ((detailError.error as Error & { status?: number }).status !== 404) return;
    setNote({ id: detailError.id, route });
    announce(`${detailError.id} isn't in this home`);
  }, [detailError, runs, runsError, route, announce]);

  // The note goes on the next route change; the replace that showed it is not
  // one (the note names that route). Setting the note is not a route change.
  const [routeSeen, setRouteSeen] = useState(route);
  if (route !== routeSeen) {
    setRouteSeen(route);
    if (note && !sameRunRoute(note.route, route)) setNote(null);
  }

  // Shortcuts: `[` / `]` step through the rail's visible rows on run routes;
  // `/` goes to the filter box on every route.
  const [focusFilter, setFocusFilter] = useState(0);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== '[' && e.key !== ']' && e.key !== '/') return;
      // Cmd+[ / Cmd+] are Back / Forward, and Ctrl without AltGr is a browser or
      // OS chord. Alt alone is how many layouts type [ and ], so it is allowed.
      if (e.metaKey || (e.ctrlKey && !e.getModifierState('AltGraph'))) return;
      if (e.isComposing || e.defaultPrevented) return;
      if (document.querySelector('[aria-modal="true"]') || isTextEntry(e.target)) return;

      if (e.key === '/') {
        if (!runs || runs.length === 0) return; // no filter box to go to
        e.preventDefault();
        if (rail.collapsed) rail.setCollapsed(false);
        setFocusFilter((n) => n + 1);
        return;
      }
      if (route.page !== 'run' || route.runId === null) return;
      const target = stepRun(visible, route.runId, e.key === ']' ? 1 : -1);
      if (!target) return;
      // Focus on a rail row follows the selection: RunRail's own effect does it.
      const next: Route = { page: 'run', runId: target.id, tab: route.tab, ticket: null };
      // Holding the key moves through runs but leaves one history entry.
      if (e.repeat) replace(next);
      else navigate(next);
      announce(`${target.id}, ${target.playbook}, ${target.state}`);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [runs, rail, route, visible, navigate, replace, announce]);

  // After the render that expanded the rail, so the box exists.
  useEffect(() => {
    if (focusFilter) filterRef.current?.focus();
  }, [focusFilter]);

  // Focus. Arriving at another page goes to its <h1> (a rail click stays on its
  // row); a route change that removes the focused control goes there too. `[` /
  // `]` from a rail row: RunRail's child effect has already moved focus to the
  // new row, which is connected, so nothing here fires. Closing the ticket
  // window: TicketBoard's child effect has already focused the card. The first
  // load moves nothing.
  const lastFocused = useRef<Element | null>(null);
  const prevPage = useRef<Route['page'] | null>(null);
  const focusH1 = useRef(false);
  // The href of the rail row last clicked (the filter box's Enter clicks one
  // too): a rail navigation is the route change that lands on it. Focus sitting
  // on a row says nothing, since Back / Forward leave it there.
  const railClick = useRef<string | null>(null);

  useEffect(() => {
    const onFocusIn = (e: FocusEvent) => {
      lastFocused.current = e.target as Element;
    };
    const onClick = (e: MouseEvent) => {
      const link = e.target instanceof Element ? e.target.closest(`${RAIL} a[href]`) : null;
      railClick.current = link?.getAttribute('href') ?? null;
    };
    document.addEventListener('focusin', onFocusIn);
    document.addEventListener('click', onClick, true);
    return () => {
      document.removeEventListener('focusin', onFocusIn);
      document.removeEventListener('click', onClick, true);
    };
  }, []);

  useEffect(() => {
    const was = prevPage.current;
    prevPage.current = route.page;
    const fromRail = railClick.current === window.location.hash;
    railClick.current = null;
    if (was !== null && was !== route.page) {
      focusH1.current = !fromRail;
      return;
    }
    const active = document.activeElement;
    if ((!active || active === document.body) && lastFocused.current && !lastFocused.current.isConnected) {
      focusH1.current = true;
    }
  }, [route]);

  // Every render: the <h1> can arrive a render after the route (the run header
  // waits for the default run to be resolved).
  useEffect(() => {
    if (!focusH1.current) return;
    const h1 = document.querySelector<HTMLElement>('main h1');
    if (!h1) return;
    focusH1.current = false;
    h1.focus();
  });

  // 'N decisions waiting on you' when the count rises. The first load is the
  // baseline; at most one announcement per window, and a rise inside the window
  // is announced at its end if the count is still above the last one announced.
  const countSaid = useRef<{ last: number | null; latest: number; timer: number }>({
    last: null,
    latest: 0,
    timer: 0,
  });
  useEffect(() => {
    if (needsYouCount === null) return;
    const s = countSaid.current;
    s.latest = needsYouCount;
    if (s.last === null) {
      s.last = needsYouCount;
      return;
    }
    if (s.timer || needsYouCount <= s.last) return;
    const say = () => {
      s.last = s.latest;
      announce(`${s.latest} ${s.latest === 1 ? 'decision' : 'decisions'} waiting on you`);
      s.timer = window.setTimeout(() => {
        s.timer = 0;
        if (s.last !== null && s.latest > s.last) say();
      }, COUNT_WINDOW_MS);
    };
    say();
  }, [needsYouCount, announce]);
  useEffect(() => {
    const s = countSaid.current;
    return () => window.clearTimeout(s.timer);
  }, []);

  // '<id> failed': the selected run's state differing between two consecutive
  // lists. A selection change compares a list with itself, so it says nothing.
  const prevRuns = useRef<Run[] | null>(null);
  useEffect(() => {
    const before = prevRuns.current;
    prevRuns.current = runs;
    if (!before || !runs || !selectedId) return;
    const was = before.find((r) => r.id === selectedId);
    const now = runs.find((r) => r.id === selectedId);
    if (was && now && was.state !== now.state) announce(`${now.id} ${now.state}`);
  }, [runs, selectedId, announce]);

  // The global overlay covers health and the first runs load only.
  const loading = healthLoading || runsLoading;

  // Show token login if remote and not authenticated
  if (!authenticated) {
    return <TokenLogin onAuthenticated={() => setAuthenticated(true)} />;
  }

  let pane: ReactNode = null;
  if (healthError) {
    pane = <PaneMessage title="Error loading data" description={healthError.message} />;
  } else if (route.page === 'crew') {
    pane = <CrewPanel liveTick={crewLiveTick} />;
  } else if (route.page === 'activity') {
    pane = <ActivityFeed runFilter={route.run} kindFilter={route.kind} streamEvents={events} />;
  } else if (route.page === 'needs-you') {
    // Cross-run: no selected run, and no run list needed (the state labels drop out without it).
    pane = (
      <NeedsYou
        runFilter={route.run}
        runs={runs}
        streamEvents={events}
        onDecided={refetchRuns}
        announce={announce}
      />
    );
  } else if (runs && runs.length === 0) {
    pane = <PaneMessage title="No runs yet" description="Start one with `hermes run <playbook>`." />;
  } else if (!headerRun) {
    if (!runs && runsError && (route.runId === null || paneError)) {
      pane = <PaneMessage title="Couldn't load runs." />;
    } else if (route.runId !== null) {
      pane = <LoadingOverlay label="Loading run…" />;
    }
  } else {
    const id = headerRun.id;
    const tab = route.tab;
    pane = (
      <>
        <RunHeader run={headerRun} prevHref={stepHref(-1)} nextHref={stepHref(1)} onRunUpdate={onRunUpdate} />
        <nav
          aria-label="Run tabs"
          style={{ display: 'flex', gap: 4, padding: '8px 16px', borderBottom: '1px solid var(--border-hairline)' }}
        >
          {RUN_TABS.map((t) => (
            <a
              key={t.tab}
              href={buildRoute({ page: 'run', runId: id, tab: t.tab, ticket: null })}
              aria-current={t.tab === tab ? 'page' : undefined}
              style={tabStyle(t.tab === tab)}
            >
              {t.label}
            </a>
          ))}
        </nav>
        {/* Keyed on the run: nothing in one run's body survives into the next. */}
        <div key={id} style={{ position: 'relative', flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
          {paneDetail ? (
            <>
              {tab === 'summary' && <Summary run={paneDetail} streamEvents={events} viewTick={viewTick} />}
              {tab === 'tickets' && (
                <TicketBoard runId={id} phases={paneDetail.phases.map((p) => p.name)} liveTick={ticketLiveTick} />
              )}
              {tab === 'outputs' && (
                <Outputs
                  runId={id}
                  liveTick={viewTick}
                />
              )}
              {tab === 'metrics' && (
                <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
                  <MetricsView runId={id} />
                  {/* Renders only a section the view declares for this tab. */}
                  <PlaybookView
                    runId={id}
                    playbook={paneDetail.playbook}
                    hasView={paneDetail.has_view}
                    liveTick={viewTick}
                    variant="metrics"
                  />
                </div>
              )}
            </>
          ) : paneError ? (
            <div style={{ padding: 20, display: 'flex', alignItems: 'center', gap: 12 }}>
              <span role="alert" style={{ fontSize: 13, color: 'var(--status-danger)' }}>
                {`Couldn't load ${id}: ${paneError.message}`}
              </span>
              <Button variant="secondary" size="sm" onClick={refetchDetail}>
                Retry
              </Button>
            </div>
          ) : (
            <LoadingOverlay label="Loading run…" />
          )}
        </div>
      </>
    );
  }

  return (
    <div
      style={{
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        overflow: 'hidden',
      }}
    >
      {/* The first focusable element in the shell. */}
      <a href="#" className="skip-link" onClick={skipToContent}>
        Skip to content
      </a>

      <CrewBackdrop theme="graph" />

      <TopBar connected={connected} page={route.page} needsYouCount={needsYouCount} />

      <div
        style={{
          position: 'relative',
          zIndex: 1,
          flex: 1,
          minHeight: 0,
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {authError && !connected && !authErrorDismissed && (
          <div
            style={{
              margin: '12px 12px 0 12px',
              padding: 12,
              background: 'var(--wash-subtle)',
              border: '1px solid var(--status-warning)',
              borderRadius: 'var(--radius-md)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              fontSize: 13,
              color: 'var(--text-secondary)',
            }}
          >
            <span>
              Live updates unauthorized — the API token may have rotated; reload to refresh.
            </span>
            <button
              onClick={() => setAuthErrorDismissed(true)}
              style={{
                padding: '4px 8px',
                fontSize: 12,
                color: 'var(--text-secondary)',
                background: 'transparent',
                border: '1px solid var(--border-hairline)',
                borderRadius: 'var(--radius-sm)',
                cursor: 'pointer',
              }}
            >
              Dismiss
            </button>
          </div>
        )}

        {/* The rail stays in the layout flow, expanded or collapsed, and pushes the pane. */}
        <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
          <RunRail
            groups={groups}
            playbooks={playbooks}
            rail={rail}
            error={runsError}
            onRetry={refetchRuns}
            selectedRunId={selectedId}
            tab={route.page === 'run' ? route.tab : lastRunTab}
            filterRef={filterRef}
          />
          <main
            style={{
              position: 'relative',
              flex: 1,
              minWidth: 0,
              minHeight: 0,
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            {note && (
              <div
                style={{
                  margin: '12px 20px 0',
                  padding: '8px 12px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 12,
                  fontSize: 13,
                  color: 'var(--text-secondary)',
                  background: 'var(--wash-subtle)',
                  border: '1px solid var(--border-hairline)',
                  borderRadius: 'var(--radius-md)',
                }}
              >
                <span>{`${note.id} isn't in this home`}</span>
                <Button variant="ghost" size="sm" onClick={() => setNote(null)}>
                  Dismiss
                </Button>
              </div>
            )}
            {pane}
          </main>
        </div>

        {loading && <LoadingOverlay label="Loading Hermes…" />}
      </div>

      <div role="status" aria-live="polite" className="visually-hidden" data-testid="status-region">
        <span key={status.n}>{status.text}</span>
      </div>
    </div>
  );
}
