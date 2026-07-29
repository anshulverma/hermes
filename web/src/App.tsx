/**
 * Hermes Control Plane App - Phase A1.
 * Shell wired to real /api/health + /api/runs.
 */

import { useEffect } from 'react';
import TopBar from './components/TopBar';
import { useHealth, useRuns } from './hooks/useApi';
import { EmptyState, StatTile, StatusPill, Card, CrewBackdrop } from './ds';

function RunSummary({ run }: { run: any }) {
  const ticketCounts = run.tickets || {};
  const total = Object.values(ticketCounts).reduce((sum: number, count: any) => sum + (count as number), 0);

  return (
    <div style={{ padding: '32px 20px' }}>
      <Card style={{ padding: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
          <h2 style={{ fontSize: 18, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
            {run.id}
          </h2>
          <StatusPill state={run.state} size="sm" />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 16 }}>
          <StatTile label="Total tickets" value={total} />
          <StatTile label="Queued" value={ticketCounts.queued || 0} />
          <StatTile label="In flight" value={ticketCounts.in_flight || 0} />
          <StatTile label="Done" value={ticketCounts.done || 0} />
          {ticketCounts.failed > 0 && <StatTile label="Failed" value={ticketCounts.failed} />}
        </div>

        <div style={{ marginTop: 20, color: 'var(--text-secondary)', fontSize: 14 }}>
          <div style={{ display: 'flex', gap: 24 }}>
            <span>
              <span style={{ color: 'var(--text-muted)' }}>Playbook:</span> {run.playbook}
            </span>
            <span>
              <span style={{ color: 'var(--text-muted)' }}>Phase:</span> {run.phase}
            </span>
            <span>
              <span style={{ color: 'var(--text-muted)' }}>Site:</span> {run.site}
            </span>
          </div>
        </div>
      </Card>
    </div>
  );
}

export default function App() {
  const { data: health, loading: healthLoading, error: healthError } = useHealth();
  const { data: runs, loading: runsLoading, error: runsError } = useRuns();

  // Initialize lucide icons after mount
  useEffect(() => {
    if (typeof window !== 'undefined' && (window as any).lucide) {
      (window as any).lucide.createIcons();
    }
  }, []);

  const loading = healthLoading || runsLoading;
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

      <TopBar health={health} runs={runs || []} />

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

        {!loading && !error && runs && runs.length > 0 && <RunSummary run={runs[0]} />}
      </div>
    </div>
  );
}
