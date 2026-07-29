/**
 * Hermes Control Plane App - Phase B4.
 * Shell wired to real /api/health + /api/runs + RunOverview + TicketBoard + CrewPanel views.
 */

import { useEffect, useState } from 'react';
import TopBar from './components/TopBar';
import RunOverview from './views/RunOverview';
import TicketBoard from './views/TicketBoard';
import CrewPanel from './views/CrewPanel';
import Findings from './views/Findings';
import ActivityFeed from './views/ActivityFeed';
import { useHealth, useRuns } from './hooks/useApi';
import { EmptyState, CrewBackdrop } from './ds';
import { fetchRun } from './api/client';
import type { RunDetail } from './api/client';

type View = 'overview' | 'metrics' | 'board' | 'crew' | 'findings' | 'activity';

export default function App() {
  const { data: health, loading: healthLoading, error: healthError } = useHealth();
  const { data: runs, loading: runsLoading, error: runsError } = useRuns();
  const [view, setView] = useState<View>('overview');
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Initialize lucide icons after mount
  useEffect(() => {
    if (typeof window !== 'undefined' && (window as any).lucide) {
      (window as any).lucide.createIcons();
    }
  }, []);

  // Fetch run detail when we have a run
  useEffect(() => {
    if (runs && runs.length > 0) {
      setDetailLoading(true);
      fetchRun(runs[0].id)
        .then((detail) => setRunDetail(detail))
        .catch((err) => console.error('Failed to fetch run detail:', err))
        .finally(() => setDetailLoading(false));
    }
  }, [runs]);

  const loading = healthLoading || runsLoading || detailLoading;
  const error = healthError || runsError;

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

      <TopBar health={health} runs={runs || []} view={view} onViewChange={setView} />

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
          <RunOverview run={runDetail} />
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
