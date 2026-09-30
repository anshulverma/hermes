/**
 * Hermes Control Plane App - Phase B4.
 * Shell wired to real /api/health + /api/runs + RunOverview + TicketBoard + CrewPanel views.
 * Phase C1: WebSocket live updates.
 */

import { useEffect, useState, useCallback } from 'react';
import TopBar from './components/TopBar';
import type { View } from './components/TopBar';
import RunOverview from './views/RunOverview';
import MetricsView from './views/MetricsView';
import TicketBoard from './views/TicketBoard';
import CrewPanel from './views/CrewPanel';
import Outputs from './views/Outputs';
import PlaybookView from './views/PlaybookView';
import { fetchReductions } from './api/client';
import { normalizeReduction } from './api/normalize';
import { awaitsDecision } from './util/reduction';
import Review from './views/Review';
import ActivityFeed from './views/ActivityFeed';
import TokenLogin from './components/TokenLogin';
import { useHealth, useRuns } from './hooks/useApi';
import { useEventStream } from './hooks/useEventStream';
import { useLiveTick, TICKET_EVENT_KINDS, CREW_EVENT_KINDS, FINDING_EVENT_KINDS } from './hooks/useLiveTick';
import { EmptyState, CrewBackdrop } from './ds';
import { LoadingOverlay } from './components/Spinner';
import { fetchRun } from './api/client';
import type { RunDetail } from './api/client';
import { hasToken, isRemote } from './api/auth';
import { useRoute } from './hooks/useRoute';
import type { Route, RunTab } from './hooks/useRoute';

// Today's top tabs, read off the route until the runs rail replaces them.
const TAB_VIEW: Record<RunTab, View> = {
  summary: 'overview',
  tickets: 'board',
  outputs: 'outputs',
  metrics: 'metrics',
};
const VIEW_TAB: Record<'overview' | 'playbook' | 'board' | 'outputs' | 'metrics', RunTab> = {
  overview: 'summary',
  playbook: 'summary',
  board: 'tickets',
  outputs: 'outputs',
  metrics: 'metrics',
};

function routeView(route: Route): View {
  if (route.page === 'run') return TAB_VIEW[route.tab];
  return route.page === 'needs-you' ? 'review' : route.page;
}

export default function App() {
  const [authenticated, setAuthenticated] = useState(hasToken() || !isRemote());

  const { loading: healthLoading, error: healthError } = useHealth();
  const { data: runs, loading: runsLoading, error: runsError } = useRuns();
  // The page and the run being viewed live in the route, so a refresh reopens
  // both: without the run the console could only ever show runs[0], and every
  // other run in the database was unreachable.
  const { route, navigate, replace } = useRoute();
  const view = routeView(route);
  const pendingDefault = route.page === 'run' && route.runId === null;
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  // The run being viewed: the one the route names, else (on a page that names
  // none: Crew, Activity, a bare Needs you) the one already on screen, so a
  // trip through those pages comes back to the same run (d978a44).
  const selectedRunId =
    (route.page === 'run' ? route.runId : route.page === 'crew' ? null : route.run) ??
    runDetail?.id ??
    null;
  // How many reductions are holding a ticket for a human. Lives here, not in
  // the Review view, because the nav has to show it before you go looking.
  const [reviewCount, setReviewCount] = useState<number | null>(null);

  // WebSocket live event stream
  const { connected, events, lastEvent, authError } = useEventStream();
  const [authErrorDismissed, setAuthErrorDismissed] = useState(false);

  // Per-domain live ticks derived from the shared event stream
  const ticketLiveTick = useLiveTick(events, TICKET_EVENT_KINDS);
  const crewLiveTick = useLiveTick(events, CREW_EVENT_KINDS);
  const findingLiveTick = useLiveTick(events, FINDING_EVENT_KINDS);

  // Initialize lucide icons after mount
  useEffect(() => {
    if (typeof window !== 'undefined' && (window as any).lucide) {
      (window as any).lucide.createIcons();
    }
  }, []);

  // Fetch run detail function (used both in initial load and live refresh)
  const refreshRunDetail = useCallback((runId: string) => {
    setDetailLoading(true);
    fetchRun(runId)
      .then((detail) => setRunDetail(detail))
      .catch((err) => console.error('Failed to fetch run detail:', err))
      .finally(() => setDetailLoading(false));
  }, []);

  // A route that leaves the run to the default (an empty hash, `#/runs`, a
  // legacy `#metrics`) names it once the list has loaded, keeping its tab, so
  // the address always names the run on screen. Not a history entry.
  // ponytail: runs[0] (the newest) stands in for defaultRunId until the rail lands.
  useEffect(() => {
    if (runs && runs.length > 0 && route.page === 'run' && route.runId === null) {
      replace({ ...route, runId: runs[0].id });
    }
  }, [runs, route, replace]);

  // Fetch the run being viewed: the one named in the URL when it exists, else
  // the newest. A URL naming a run that is gone falls back to the newest rather
  // than leaving the console empty.
  useEffect(() => {
    if (!runs || runs.length === 0 || pendingDefault) return;
    const named =
      selectedRunId && runs.some((r) => r.id === selectedRunId) ? selectedRunId : runs[0].id;
    refreshRunDetail(named);
  }, [runs, selectedRunId, pendingDefault, refreshRunDetail]);

  // A tab click: a run tab keeps the run on screen and drops what was open on
  // the old tab (the ticket); Needs you shows that run's reductions.
  const setView = (next: View) => {
    const runId = runDetail?.id ?? null;
    if (next === 'crew') navigate({ page: 'crew' });
    else if (next === 'activity') navigate({ page: 'activity', run: null, kind: null });
    else if (next === 'review') navigate({ page: 'needs-you', run: runId });
    else if (runId !== null) navigate({ page: 'run', runId, tab: VIEW_TAB[next], ticket: null });
  };

  // Picking a run keeps the run tab and drops the ticket; from a page that
  // names no run it opens the run's summary.
  const setSelectedRunId = (runId: string) =>
    navigate({ page: 'run', runId, tab: route.page === 'run' ? route.tab : 'summary', ticket: null });

  // The review queue's size, refreshed with the run and on finding events.
  useEffect(() => {
    const runId = runDetail?.id;
    if (!runId) {
      setReviewCount(null);
      return;
    }
    let cancelled = false;
    fetchReductions(runId)
      .then((rs) => {
        if (!cancelled) setReviewCount(rs.map(normalizeReduction).filter(awaitsDecision).length);
      })
      .catch(() => {
        // A count is an affordance, not information the console depends on.
        if (!cancelled) setReviewCount(null);
      });
    return () => {
      cancelled = true;
    };
  }, [runDetail?.id, findingLiveTick]);

  // Live refresh: when state-changing events arrive, re-fetch run detail
  useEffect(() => {
    if (!lastEvent || !runDetail) return;

    // State-changing event kinds that should trigger a run detail refresh
    const stateChangingKinds = new Set([
      'ticket_claimed',
      'result_recorded',
      'phase_advanced',
      'needs_human',
      'reduction_created',
      'ticket_requeued',
      'ticket_parked',
      'ticket_failed',
    ]);

    if (stateChangingKinds.has(lastEvent.kind)) {
      // Only refresh if the event is for the current run
      if (lastEvent.run_id === runDetail.id) {
        refreshRunDetail(runDetail.id);
      }
    }
  }, [lastEvent, runDetail, refreshRunDetail]);

  // Only the INITIAL load blanks the app. A background run-detail refresh (fired
  // on every live event) must NOT unmount the views/drawer — it updates in place.
  const loading = healthLoading || runsLoading || (detailLoading && !runDetail);
  const error = healthError || runsError;

  // Show token login if remote and not authenticated
  if (!authenticated) {
    return <TokenLogin onAuthenticated={() => setAuthenticated(true)} />;
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
      <CrewBackdrop theme="graph" />

      <TopBar
        connected={connected}
        view={view}
        onViewChange={setView}
        runs={runs ?? undefined}
        selectedRunId={runDetail?.id ?? selectedRunId}
        onRunChange={setSelectedRunId}
        reviewCount={reviewCount}
      />

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

        {loading && <LoadingOverlay label="Loading Hermes…" />}

        {error && (
          <div style={{ padding: 32 }}>
            <EmptyState
              title="Error loading data"
              description={error.message}
              icon="alert-circle"
            />
          </div>
        )}

        {!loading && !error && runs && runs.length === 0 && (
          <div style={{ padding: 32 }}>
            <EmptyState
              title="No active run"
              description="No runs are currently active. Start a run with `hermes run <playbook>`."
              icon="inbox"
            />
          </div>
        )}

        {/* The Run tab: the run's own view when its playbook ships one (a
            legacy `#playbook` link lands here too), else the overview. */}
        {!loading && !error && runDetail && view === 'overview' && !runDetail.has_view && (
          <RunOverview run={runDetail} onRunUpdate={() => refreshRunDetail(runDetail.id)} />
        )}

        {!loading && !error && runDetail && view === 'metrics' && (
          <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
            <MetricsView runId={runDetail.id} />
            {/* Renders only a section the view declares for this tab. */}
            <PlaybookView
              key={`${runDetail.playbook}:${runDetail.id}`}
              runId={runDetail.id}
              playbook={runDetail.playbook}
              hasView={runDetail.has_view}
              liveTick={findingLiveTick}
              variant="metrics"
            />
          </div>
        )}

        {/* Keyed on the run: a phase or resource picked on one run names
            nothing on the next, and would filter its board to empty. */}
        {!loading && !error && runDetail && view === 'board' && (
          <TicketBoard
            key={runDetail.id}
            runId={runDetail.id}
            phases={runDetail.phases.map((p) => p.name)}
            liveTick={ticketLiveTick}
          />
        )}

        {!loading && !error && view === 'crew' && (
          <CrewPanel liveTick={crewLiveTick} runId={runDetail?.id} />
        )}

        {!loading && !error && runDetail && view === 'outputs' && (
          <Outputs
            runId={runDetail.id}
            liveTick={findingLiveTick}
            onGoToReview={() => setView('review')}
          />
        )}

        {!loading && !error && runDetail && view === 'review' && (
          <Review
            runId={runDetail.id}
            liveTick={findingLiveTick}
            onGoToOutputs={() => setView('outputs')}
          />
        )}

        {!loading && !error && view === 'activity' && (
          <ActivityFeed />
        )}

        {/* Keyed on the run so switching runs remounts rather than reusing the
            loaded component and the previous run's data: the loader only blanks
            its pane on the FIRST load, so without this the pane would show run
            B's id over run A's view_data for one round trip. */}
        {!loading && !error && runDetail && view === 'overview' && runDetail.has_view && (
          <PlaybookView
            key={`${runDetail.playbook}:${runDetail.id}`}
            runId={runDetail.id}
            playbook={runDetail.playbook}
            hasView={runDetail.has_view}
            liveTick={findingLiveTick}
          />
        )}
      </div>
    </div>
  );
}
