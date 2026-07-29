/**
 * Hermes Control Plane App - Phase B4.
 * Shell wired to real /api/health + /api/runs + RunOverview + TicketBoard + CrewPanel views.
 * Phase C1: WebSocket live updates.
 */

import { useEffect, useState, useCallback } from 'react';
import TopBar from './components/TopBar';
import RunOverview from './views/RunOverview';
import TicketBoard from './views/TicketBoard';
import CrewPanel from './views/CrewPanel';
import Findings from './views/Findings';
import ActivityFeed from './views/ActivityFeed';
import TokenLogin from './components/TokenLogin';
import { useHealth, useRuns } from './hooks/useApi';
import { useEventStream } from './hooks/useEventStream';
import { EmptyState, CrewBackdrop } from './ds';
import { fetchRun } from './api/client';
import type { RunDetail } from './api/client';
import { hasToken, isRemote } from './api/auth';

type View = 'overview' | 'metrics' | 'board' | 'crew' | 'findings' | 'activity';

export default function App() {
  const [authenticated, setAuthenticated] = useState(hasToken() || !isRemote());

  const { loading: healthLoading, error: healthError } = useHealth();
  const { data: runs, loading: runsLoading, error: runsError } = useRuns();
  const [view, setView] = useState<View>('overview');
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // WebSocket live event stream
  const { connected, lastEvent, authError } = useEventStream();
  const [authErrorDismissed, setAuthErrorDismissed] = useState(false);

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

  // Fetch run detail when we have a run (initial load)
  useEffect(() => {
    if (runs && runs.length > 0) {
      refreshRunDetail(runs[0].id);
    }
  }, [runs, refreshRunDetail]);

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

  const loading = healthLoading || runsLoading || detailLoading;
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

      <TopBar connected={connected} runs={runs || []} view={view} onViewChange={setView} />

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

        {loading && (
          <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)' }}>
            Loading...
          </div>
        )}

        {error && (
          <div style={{ padding: 32 }}>
            <EmptyState
              title="Error loading data"
              message={error.message}
              icon="alert-circle"
            />
          </div>
        )}

        {!loading && !error && runs && runs.length === 0 && (
          <div style={{ padding: 32 }}>
            <EmptyState
              title="No active run"
              message="No runs are currently active. Start a run with `hermes run <playbook>`."
              icon="inbox"
            />
          </div>
        )}

        {!loading && !error && runDetail && view === 'overview' && (
          <RunOverview run={runDetail} onRunUpdate={() => refreshRunDetail(runDetail.id)} />
        )}

        {!loading && !error && runDetail && view === 'board' && (
          <TicketBoard runId={runDetail.id} />
        )}

        {!loading && !error && view === 'crew' && (
          <CrewPanel />
        )}

        {!loading && !error && runDetail && view === 'findings' && (
          <Findings runId={runDetail.id} />
        )}

        {!loading && !error && view === 'activity' && (
          <ActivityFeed />
        )}
      </div>
    </div>
  );
}
