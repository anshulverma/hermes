/**
 * Summary — the first tab of every run, whatever its playbook.
 *
 * A fixed strip of key numbers; the playbook's own view when it ships one,
 * else the phase timeline; and a side column with what in this run waits on
 * you and what just happened in it. The run header above owns the name,
 * state, elapsed time, progress and controls, so none of them repeat here.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchEvents, fetchNeedsYou, fetchReductions, fetchRunMetrics } from '../api/client';
import type { Event, Phase, Reduction, RunDetail, RunMetrics } from '../api/client';
import { StatTile, StatusPill } from '../ds';
import PlaybookView from './PlaybookView';
import { buildRoute } from '../hooks/useRoute';
import { useNow } from '../hooks/useNow';
import { useStreamTrigger } from '../hooks/useStreamTrigger';
import { reductionHeadline } from '../util/reduction';
import { fmtAgo, fmtSeconds, fmtTime } from '../util/time';

type SummaryProps = {
  run: RunDetail;
  /** The app's one event stream (`useEventStream().events`), never a second socket. */
  streamEvents: Event[];
  /** App's tick over the finding kinds for this run: keeps the view live. */
  viewTick: number;
};

type Block<T> = { data: T | null; error: Error | null; reload: () => void };

/**
 * One block's fetch. A reload keeps what is on screen until the new response
 * lands, and a response that lands after the block has moved on (another run,
 * an unmount) is dropped instead of drawn under the wrong run.
 *
 * A reload does not cancel the fetch before it: on a busy run the next reload
 * starts before a slow response lands, and cancelling would keep the block
 * empty. Each fetch takes a number instead, and among one run's responses only
 * one newer than the last applied is drawn (the useRuns rule).
 */
function useBlock<T>(load: (() => Promise<T>) | null): Block<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [reloads, setReloads] = useState(0);
  // The load of the run on screen: another run or an unmount replaces it.
  const shown = useRef(load);
  const issued = useRef(0);
  const applied = useRef(0);

  useEffect(() => {
    shown.current = load;
    return () => {
      shown.current = null;
    };
  }, [load]);

  useEffect(() => {
    if (!load) return;
    const seq = ++issued.current;
    const apply = (draw: () => void) => {
      if (shown.current !== load || seq <= applied.current) return;
      applied.current = seq;
      draw();
    };
    load().then(
      (value) =>
        apply(() => {
          setData(value);
          setError(null);
        }),
      (err: Error) => apply(() => setError(err)),
    );
  }, [load, reloads]);

  const reload = useCallback(() => setReloads((n) => n + 1), []);
  return { data, error, reload };
}

/** The fetched page plus this run's stream events newer than it: newest first, ten kept. */
function mergeRecent(fetched: Event[], stream: Event[], runId: string): Event[] {
  const newest = fetched.reduce((max, e) => Math.max(max, e.id), 0);
  const byId = new Map(fetched.map((e) => [e.id, e]));
  for (const e of stream) {
    if (e.run_id === runId && e.id > newest) byId.set(e.id, e);
  }
  return [...byId.values()].sort((a, b) => b.id - a.id).slice(0, 10);
}

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

function PhaseTimeline({ run, reductions }: { run: RunDetail; reductions: Reduction[] }) {
  if (run.phases.length === 0) {
    return <p style={quietStyle}>No phases yet.</p>;
  }
  const ended = ['done', 'stopped', 'failed'].includes(run.state);
  const outputsHref = buildRoute({ page: 'run', runId: run.id, tab: 'outputs', ticket: null });
  // The newest reduction of a phase names what that phase came to.
  const newest = new Map<string, Reduction>();
  for (const r of reductions) {
    const seen = newest.get(r.phase);
    if (!seen || r.id > seen.id) newest.set(r.phase, r);
  }
  // Wraps: a playbook that mints a phase per step has dozens of them.
  return (
    <div data-testid="phase-rail" style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
      {run.phases.map((p: Phase) => {
        const total = Object.values(p.counts).reduce((a, b) => a + b, 0);
        // A phase with no tickets has no counts to read, so a finished run speaks
        // for its last one (a zero-ticket sentinel phase).
        const state = phaseState(p.current && ended && !total ? { [run.state]: 1 } : p.counts);
        const headline = newest.get(p.name);
        return (
          <div key={p.name} style={{ flex: '1 1 120px', display: 'flex', flexDirection: 'column', gap: 6 }}>
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
            {headline && (
              <a href={outputsHref} style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                {reductionHeadline(headline.json, headline.kind)}
              </a>
            )}
          </div>
        );
      })}
    </div>
  );
}

function KeyNumbers({ run, metrics }: { run: RunDetail; metrics: Block<RunMetrics> }) {
  const n = (s: string) => run.tickets[s] || 0;
  const total = Object.values(run.tickets).reduce((a, b) => a + b, 0);
  // The header's "in flight": claimed work waits in dispatched, then reducing.
  const inFlight = n('dispatched') + n('running') + n('reducing');
  // With no results retry_rate is 0.0, not null; it must not read as a real 0%.
  const m = metrics.data && metrics.data.totals.results > 0 ? metrics.data : null;
  return (
    <div
      style={{
        flex: 'none',
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(96px, 1fr))',
        gap: 12,
      }}
    >
      <StatTile label="tickets" value={total} />
      <StatTile label="done" value={n('done')} tone="ok" />
      <StatTile label="in flight" value={inFlight} tone="live" live={inFlight > 0} emphasis />
      <StatTile label="parked" value={n('parked')} tone={n('parked') > 0 ? 'attention' : undefined} />
      <StatTile label="failed" value={n('failed')} tone={n('failed') > 0 ? 'danger' : undefined} />
      <StatTile label="queued" value={n('queued')} />
      {metrics.error ? (
        <div style={{ gridColumn: 'span 2', alignSelf: 'center' }}>
          <BlockError what="metrics" onRetry={metrics.reload} />
        </div>
      ) : (
        <>
          <StatTile label="retry rate" value={m ? `${Math.round(m.retry_rate * 100)}%` : '—'} />
          <StatTile label="mean time to result" value={m ? fmtSeconds(m.mean_time_to_result_s) : '—'} />
        </>
      )}
    </div>
  );
}

function Ago({ ts, now }: { ts: number; now: number }) {
  return (
    <time dateTime={new Date(ts * 1000).toISOString()} title={fmtTime(ts)} style={{ color: 'var(--text-muted)', fontSize: 12 }}>
      {fmtAgo(ts, now)}
    </time>
  );
}

function BlockError({ what, onRetry }: { what: string; onRetry: () => void }) {
  return (
    <div role="alert" style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--status-danger)' }}>
      {`Couldn't load ${what}.`}
      <button
        type="button"
        onClick={onRetry}
        style={{
          padding: '2px 8px',
          fontSize: 12,
          color: 'var(--text-secondary)',
          background: 'transparent',
          border: '1px solid var(--border-hairline)',
          borderRadius: 'var(--radius-sm)',
          cursor: 'pointer',
        }}
      >
        Retry
      </button>
    </div>
  );
}

const headingStyle = { margin: 0, fontSize: 13, fontWeight: 500, color: 'var(--text-muted)' } as const;
const listStyle = { margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8 } as const;
const itemStyle = { display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 13, color: 'var(--text-secondary)' } as const;
const quietStyle = { margin: 0, fontSize: 13, color: 'var(--text-muted)' } as const;
const sectionStyle = { display: 'flex', flexDirection: 'column', gap: 8 } as const;

export default function Summary({ run, streamEvents, viewTick }: SummaryProps) {
  const id = run.id;
  const now = useNow();

  const metrics = useBlock(useCallback(() => fetchRunMetrics(id), [id]));
  const waiting = useBlock(
    useCallback(() => fetchNeedsYou().then((items) => items.filter((item) => item.run_id === id)), [id]),
  );
  const events = useBlock(useCallback(() => fetchEvents({ run: id, order: 'desc', limit: 10 }), [id]));
  const loadReductions = useCallback(() => fetchReductions(id), [id]);
  const reductions = useBlock(run.has_view ? null : loadReductions);

  // One trigger for the blocks a run event can change. Recent events never
  // refetch: the stream itself carries them (merged below).
  const { reload: reloadMetrics } = metrics;
  const { reload: reloadWaiting } = waiting;
  const { reload: reloadReductions } = reductions;
  const refetch = useCallback(() => {
    reloadMetrics();
    reloadWaiting();
    reloadReductions();
  }, [reloadMetrics, reloadWaiting, reloadReductions]);
  const forThisRun = useCallback((e: Event) => e.run_id === id, [id]);
  useStreamTrigger(streamEvents, forThisRun, refetch);

  const recent = events.data && mergeRecent(events.data, streamEvents, id);

  return (
    <div
      style={{
        flex: 1,
        minHeight: 0,
        overflow: 'hidden',
        padding: 20,
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
      }}
    >
      <KeyNumbers run={run} metrics={metrics} />

      <div className="summary-columns">
        <div className="summary-main">
          {run.has_view ? (
            // Keyed on playbook and run: the loader blanks its pane only on the
            // first load, so a reused element would show the previous run's
            // view data under this run's id for one round trip.
            <PlaybookView
              key={`${run.playbook}:${id}`}
              runId={id}
              playbook={run.playbook}
              hasView={run.has_view}
              liveTick={viewTick}
            />
          ) : (
            <div style={{ flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 12 }}>
              {reductions.error && <BlockError what="phase headlines" onRetry={reductions.reload} />}
              <PhaseTimeline run={run} reductions={reductions.data ?? []} />
            </div>
          )}
        </div>

        <aside className="summary-side">
          <section aria-labelledby="summary-waiting" style={sectionStyle}>
            <h2 id="summary-waiting" style={headingStyle}>
              Waiting on you here
            </h2>
            {waiting.error ? (
              <BlockError what="waiting items" onRetry={waiting.reload} />
            ) : waiting.data && waiting.data.length === 0 ? (
              <p style={quietStyle}>Nothing waiting on you in this run.</p>
            ) : (
              waiting.data && (
                <>
                  <ul style={listStyle}>
                    {waiting.data.map((item) => (
                      <li key={item.id} style={itemStyle}>
                        <span>{reductionHeadline(item.json, item.kind)}</span>
                        <Ago ts={item.created_at} now={now} />
                      </li>
                    ))}
                  </ul>
                  <a href={buildRoute({ page: 'needs-you', run: id })} style={{ fontSize: 13 }}>
                    Rule on these in Needs you
                  </a>
                </>
              )
            )}
          </section>

          <section aria-labelledby="summary-events" style={sectionStyle}>
            <h2 id="summary-events" style={headingStyle}>
              Recent events
            </h2>
            {events.error ? (
              <BlockError what="recent events" onRetry={events.reload} />
            ) : recent && recent.length === 0 ? (
              <p style={quietStyle}>No events.</p>
            ) : (
              recent && (
                <ul style={listStyle}>
                  {recent.map((e) => (
                    <li key={e.id} style={itemStyle}>
                      <span>{e.message ? `${e.kind} · ${e.message}` : e.kind}</span>
                      <Ago ts={e.ts} now={now} />
                    </li>
                  ))}
                </ul>
              )
            )}
            <a href={buildRoute({ page: 'activity', run: id, kind: null })} style={{ fontSize: 13 }}>
              All events in Activity
            </a>
          </section>
        </aside>
      </div>
    </div>
  );
}
