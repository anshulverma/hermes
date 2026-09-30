/**
 * RunHeader - the run pane's header, above the run tabs on every tab: which run
 * (the pane's <h1>, the skip link's target), its state, phase, start and elapsed
 * time, ticket progress, the decisions waiting on you, its controls, and ‹ › to
 * the neighbouring rail rows.
 *
 * Drawn from the run's /api/runs row, which carries `awaiting`; from the run
 * detail only when the list has no row for it (then no ⚑). App does not key it,
 * so a focused ‹ or › keeps focus as the selection moves; RunControl is keyed on
 * the run, so a Stop confirmation, an error or an in-flight label stays behind.
 */

import type { CSSProperties } from 'react';
import type { Run, RunDetail } from '../api/client';
import { buildRoute } from '../hooks/useRoute';
import { useNow } from '../hooks/useNow';
import { fmtSeconds, fmtTime } from '../util/time';
import RunControl from './RunControl';
import { RunStateIcon, phaseLabel } from './RunRail';

type RunHeaderProps = {
  run: Run | RunDetail;
  prevHref: string | null;
  nextHref: string | null;
  onRunUpdate: () => void;
};

const ENDED = ['done', 'failed', 'stopped'];

const muted: CSSProperties = {
  color: 'var(--text-muted)',
  fontSize: 12,
  fontFamily: 'var(--font-mono)',
};

const stepStyle: CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: 28,
  height: 28,
  fontSize: 16,
  color: 'var(--text-primary)',
  textDecoration: 'none',
  background: 'var(--wash-subtle)',
  border: '1px solid var(--border-hairline)',
  borderRadius: 'var(--radius-md)',
};

/**
 * ‹ or ›: a link styled as a button, like the run tabs, labelled 'Previous run'
 * / 'Next run' so it does not clash with a view's own Prev button. At an end it
 * stays the same element with no href, aria-disabled and still focusable, so
 * focus stays on it as the selection moves.
 */
function StepLink({
  href,
  label,
  shortcut,
  glyph,
}: {
  href: string | null;
  label: string;
  shortcut: string;
  glyph: string;
}) {
  return (
    <a
      href={href ?? undefined}
      role={href ? undefined : 'link'}
      aria-disabled={href ? undefined : 'true'}
      tabIndex={href ? undefined : 0}
      aria-label={label}
      aria-keyshortcuts={shortcut}
      title={`${label} (${shortcut})`}
      style={{ ...stepStyle, opacity: href ? 1 : 0.4, cursor: href ? 'pointer' : 'default' }}
    >
      {glyph}
    </a>
  );
}

/**
 * Done of total, plus in flight (dispatched + running + reducing: claimed work
 * waits in `dispatched`) and failed. The caption is also the bar's valuetext, so
 * the segments are not told apart by colour alone.
 */
function Progress({ tickets }: { tickets: Record<string, number> }) {
  const n = (state: string) => tickets[state] || 0;
  const total = Object.values(tickets).reduce((a, b) => a + b, 0);
  const row: CSSProperties = { display: 'flex', alignItems: 'center', gap: 10 };
  const track: CSSProperties = {
    flex: '0 0 200px',
    display: 'flex',
    height: 6,
    borderRadius: 'var(--radius-full)',
    background: 'var(--wash-active)',
    overflow: 'hidden',
  };
  if (total === 0) {
    return (
      <div style={row}>
        <div aria-hidden="true" style={track} />
        <span style={muted}>no tickets yet</span>
      </div>
    );
  }
  const done = n('done');
  const working = n('dispatched') + n('running') + n('reducing');
  const failed = n('failed');
  const caption = [
    `${done} of ${total} done`,
    working ? `${working} in flight` : '',
    failed ? `${failed} failed` : '',
  ]
    .filter(Boolean)
    .join(' · ');
  const segment = (count: number, color: string) => (
    <div style={{ width: `${(count / total) * 100}%`, background: color }} />
  );
  return (
    <div style={row}>
      <div
        role="progressbar"
        aria-label="Tickets"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={done}
        aria-valuetext={caption}
        style={track}
      >
        {segment(done, 'var(--status-ok)')}
        {segment(working, 'var(--status-live)')}
        {segment(failed, 'var(--status-danger)')}
      </div>
      <span style={muted}>{caption}</span>
    </div>
  );
}

export default function RunHeader({ run, prevHref, nextHref, onRunUpdate }: RunHeaderProps) {
  const now = useNow();
  const ended = ENDED.includes(run.state);
  // A finished run's updated_at is its end time: only reopen and the state and
  // phase writers touch it.
  const elapsed = Math.max(0, (ended ? run.updated_at : now) - run.created_at);
  const awaiting = 'awaiting' in run ? run.awaiting : 0;

  return (
    <header
      style={{
        padding: '14px 20px 12px',
        borderBottom: '1px solid var(--border-hairline)',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <StepLink href={prevHref} label="Previous run" shortcut="[" glyph="‹" />
        <StepLink href={nextHref} label="Next run" shortcut="]" glyph="›" />
        <h1
          tabIndex={-1}
          style={{
            margin: 0,
            fontSize: 20,
            lineHeight: '26px',
            fontWeight: 500,
            color: 'var(--text-primary)',
          }}
        >
          {`${run.id} · ${run.playbook}`}
        </h1>
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            fontSize: 13,
            color: 'var(--text-secondary)',
          }}
        >
          <RunStateIcon state={run.state} />
          <span>{run.state}</span>
        </span>
        <span style={muted}>{phaseLabel(run)}</span>
        <span style={muted}>
          started{' '}
          <time dateTime={new Date(run.created_at * 1000).toISOString()}>
            {fmtTime(run.created_at)}
          </time>
        </span>
        <span style={muted}>{fmtSeconds(elapsed)} elapsed</span>
        {awaiting > 0 && (
          <a
            href={buildRoute({ page: 'needs-you', run: run.id })}
            style={{ fontSize: 13, color: 'var(--status-attention)' }}
          >
            <span aria-hidden="true">⚑ </span>
            {awaiting} waiting on you
          </a>
        )}
      </div>
      <Progress tickets={run.tickets} />
      <RunControl key={run.id} runId={run.id} runState={run.state} onSuccess={onRunUpdate} />
    </header>
  );
}
