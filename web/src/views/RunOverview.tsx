/**
 * RunOverview - main dashboard view showing run status and progress.
 * Ported from web/prototype/app/RunOverview.jsx.
 */

import { useState } from 'react';
import type { RunDetail, Phase } from '../api/client';
import { deriveContext } from '../api/normalize';
import { StatTile, Card, StatusPill } from '../ds';
import PlaybookDialog from '../components/PlaybookDialog';
import { fmtTime } from '../util/time';

type PhaseTimelineProps = {
  phases: Phase[];
  runState: string;
};

/**
 * What a phase's tickets have come to, worst first.
 *
 * Read from the counts, not from `current`: a finished run still names its last
 * phase as current, and a phase that fans out stays current while its tickets
 * fail. Claimed work waits in `dispatched` until its result lands, so that is
 * active too; `running` alone is almost never written.
 */
function phaseState(counts: Record<string, number>): string {
  const n = (s: string) => counts[s] || 0;
  if (n('needs_human')) return 'needs-human';
  if (n('failed')) return 'failed';
  if (n('dispatched') || n('running') || n('reducing')) return 'running';
  if (n('parked')) return 'parked';
  if (n('queued')) return 'queued';
  if (n('done')) return 'done';
  return 'queued';
}

function PhaseTimeline({ phases, runState }: PhaseTimelineProps) {
  const ended = ['done', 'stopped', 'failed'].includes(runState);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {/* Wraps: a playbook that mints a phase per step has dozens of them. */}
      <div data-testid="phase-rail" style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
        {phases.map((p) => {
          const total = Object.values(p.counts).reduce((a, b) => a + b, 0);
          // A zero-ticket phase has no counts to read, so a finished run speaks
          // for its last one (a sentinel such as research's `complete`).
          const state = phaseState(p.current && ended && !total ? { [runState]: 1 } : p.counts);
          return (
            <div
              key={p.name}
              style={{
                flex: '1 1 120px',
                display: 'flex',
                flexDirection: 'column',
                gap: 6,
              }}
            >
              <div
                style={{
                  height: 6,
                  borderRadius: 'var(--radius-full)',
                  background: p.current ? 'var(--status-live)' : 'var(--wash-active)',
                  animation: p.current && !ended ? 'fm-pulse 1.6s ease-out infinite' : 'none',
                }}
              />
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <StatusPill
                  state={state}
                  data-state={state}
                  label={total > 1 ? `${p.name} ${total}` : p.name}
                  size="sm"
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

type ProgressBarProps = {
  done: number;
  total: number;
};

function ProgressBar({ done, total }: ProgressBarProps) {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          color: 'var(--text-muted)',
          fontSize: 12,
          fontFamily: 'var(--font-mono)',
        }}
      >
        <span>
          {done} / {total} tickets
        </span>
        <span>{pct}%</span>
      </div>
      <div
        style={{
          height: 6,
          borderRadius: 'var(--radius-full)',
          background: 'var(--wash-active)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: pct + '%',
            height: '100%',
            background: 'var(--status-ok)',
            transition: 'width 160ms ease-out',
          }}
        />
      </div>
    </div>
  );
}

type RunOverviewProps = {
  run: RunDetail;
};

export default function RunOverview({ run }: RunOverviewProps) {
  const [playbookOpen, setPlaybookOpen] = useState(false);

  const context = deriveContext(run);
  const tickets = run.tickets || {};
  const total = Object.values(tickets).reduce((sum, count) => sum + count, 0);
  const done = tickets.done || 0;
  const running = tickets.running || 0;
  const queued = tickets.queued || 0;
  const parked = tickets.parked || 0;
  const failed = tickets.failed || 0;

  const Divider = () => (
    <div style={{ borderBottom: '1px solid var(--border-hairline)' }} />
  );

  return (
    <div
      style={{
        flex: 1,
        overflow: 'auto',
        padding: 20,
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
      }}
    >
      {/* KPI stat tiles */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(6, minmax(0, 1fr))',
          gap: 12,
        }}
      >
        <StatTile label="tickets" value={total} />
        <StatTile label="done" value={done} tone="ok" />
        <StatTile label="in flight" value={running} tone="live" live={running > 0} emphasis />
        <StatTile label="parked" value={parked} tone={parked > 0 ? 'attention' : undefined} />
        <StatTile label="failed" value={failed} tone={failed > 0 ? 'danger' : undefined} />
        <StatTile label="queued" value={queued} />
      </div>

      {/* Main content */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <Card style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 18 }}>
          {/* Run header */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span
              style={{
                color: 'var(--text-primary)',
                fontSize: 20,
                lineHeight: '26px',
                cursor: 'pointer',
              }}
              onClick={() => setPlaybookOpen(true)}
              title="Click to view playbook details"
            >
              {run.playbook} run
            </span>
            <StatusPill state={run.state} />
            <div style={{ flex: 1 }} />
            <span
              style={{
                color: 'var(--text-muted)',
                fontSize: 12,
                fontFamily: 'var(--font-mono)',
              }}
            >
              started {fmtTime(run.created_at)}
            </span>
          </div>

          {/* Context chips */}
          {context.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {context.map((c) => (
                <span
                  key={c.label}
                  style={{
                    display: 'flex',
                    gap: 6,
                    padding: '4px 10px',
                    border: '1px solid var(--border-hairline)',
                    borderRadius: 'var(--radius-lg)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 12,
                  }}
                >
                  <span style={{ color: 'var(--text-muted)' }}>{c.label}</span>
                  <span style={{ color: 'var(--text-secondary)' }}>{c.value}</span>
                </span>
              ))}
            </div>
          )}

          {/* Progress bar */}
          <ProgressBar done={done} total={total} />

          <Divider />

          {/* Phase timeline */}
          <PhaseTimeline phases={run.phases} runState={run.state} />
        </Card>
      </div>

      {/* Playbook dialog */}
      <PlaybookDialog open={playbookOpen} run={run} onClose={() => setPlaybookOpen(false)} />
    </div>
  );
}
