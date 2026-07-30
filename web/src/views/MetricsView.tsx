/**
 * MetricsView - run metrics, styled after the Claude design prototype.
 *
 * Renders the real time-bucketed series from /api/runs/{id}/metrics as readable
 * charts: a stat-tile summary row, framed line/bar charts with Y-axis scale
 * labels, X-axis time labels, legends, and hover tooltips. Data is real only —
 * the prototype's budget/agent/by-phase cards are intentionally omitted (no real
 * data source yet), matching the prototype's chart design without fabrication.
 */

import { useState, useEffect, useRef } from 'react';
import { fetchRunMetrics } from '../api/client';
import type { RunMetrics, MetricsBucket } from '../api/client';
import { Card, StatTile, EmptyState } from '../ds';
import { LoadingOverlay } from '../components/Spinner';

// --- helpers ---------------------------------------------------------------

/** "now" / "Nm ago" for bucket index i of n, given the bucket width in seconds. */
function minutesAgoLabel(i: number, n: number, bucketS: number): string {
  const mins = Math.round(((n - 1 - i) * bucketS) / 60);
  return mins === 0 ? 'now' : `${mins}m ago`;
}

/** ~5 evenly spaced X-axis time labels across n buckets. */
function xAxisLabels(n: number, bucketS: number): string[] {
  if (n <= 1) return ['now'];
  const count = Math.min(5, n);
  const idxs: number[] = [];
  for (let k = 0; k < count; k++) idxs.push(Math.round((k / (count - 1)) * (n - 1)));
  return Array.from(new Set(idxs)).map((i) => minutesAgoLabel(i, n, bucketS));
}

type Series = { label: string; points: number[]; color: string };
type TipRow = { label: string; color: string; value: string };

/** Cursor-tracking hover state over an n-point chart. */
function useHover(n: number) {
  const [i, setI] = useState<number | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const onMove = (e: React.MouseEvent) => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const t = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    setI(Math.round(t * (n - 1)));
  };
  return { i, ref, onMove, onLeave: () => setI(null) };
}

// --- chart primitives (ported from the prototype) --------------------------

/** Floating value readout pinned to the hovered bucket. */
function TipBox({ leftPct, timeLabel, rows }: { leftPct: number; timeLabel: string; rows: TipRow[] }) {
  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        left: `${leftPct}%`,
        transform: `translateX(${leftPct > 65 ? '-104%' : '4%'})`,
        pointerEvents: 'none',
        zIndex: 5,
        minWidth: 140,
        padding: '8px 10px',
        background: 'var(--surface-overlay)',
        backdropFilter: 'blur(var(--blur-overlay))',
        WebkitBackdropFilter: 'blur(var(--blur-overlay))',
        border: '1px solid var(--border-hairline)',
        borderRadius: 'var(--radius-lg)',
        fontFamily: 'var(--font-mono)',
        fontSize: 12,
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
      }}
    >
      <span style={{ color: 'var(--text-muted)' }}>{timeLabel}</span>
      {rows.map((r) => (
        <span key={r.label} style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-muted)' }}>
            <span aria-hidden="true" style={{ width: 8, height: 2, background: r.color }} />
            {r.label}
          </span>
          <span style={{ color: 'var(--text-primary)' }}>{r.value}</span>
        </span>
      ))}
    </div>
  );
}

function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <>
      {items.map((it) => (
        <span
          key={it.label}
          style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-muted)', fontSize: 12 }}
        >
          <span aria-hidden="true" style={{ width: 8, height: 2, background: it.color }} />
          {it.label}
        </span>
      ))}
    </>
  );
}

function ChartFrame({
  title,
  meta,
  legend,
  height = 160,
  children,
}: {
  title: string;
  meta?: string;
  legend?: React.ReactNode;
  height?: number;
  children: React.ReactNode;
}) {
  return (
    <Card padding="md" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <span style={{ color: 'var(--text-primary)', fontSize: 14 }}>{title}</span>
        {meta && (
          <span style={{ color: 'var(--text-muted)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>{meta}</span>
        )}
        <div style={{ flex: 1 }} />
        {legend && <div style={{ display: 'flex', gap: 12 }}>{legend}</div>}
      </div>
      <div style={{ height }}>{children}</div>
    </Card>
  );
}

function YAxis({
  max,
  height,
  format,
  ticks = 4,
}: {
  max: number;
  height: number;
  format?: (v: number) => string | number;
  ticks?: number;
}) {
  const fmt = format || ((v: number) => (max >= 1000 ? Math.round(v) : Math.round(v * 10) / 10));
  const rows: number[] = [];
  for (let i = ticks; i >= 0; i--) rows.push(i / ticks);
  return (
    <div style={{ position: 'relative', width: 44, height, flex: 'none' }}>
      {rows.map((f) => (
        <span
          key={f}
          style={{
            position: 'absolute',
            right: 0,
            top: (1 - f) * height - 8,
            color: 'var(--text-muted)',
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            lineHeight: '16px',
          }}
        >
          {fmt(max * f)}
        </span>
      ))}
    </div>
  );
}

function AxisLabels({ labels, inset = 52 }: { labels: string[]; inset?: number }) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        marginTop: 6,
        marginLeft: inset,
        color: 'var(--text-muted)',
        fontSize: 12,
        fontFamily: 'var(--font-mono)',
      }}
    >
      {labels.map((l, idx) => (
        <span key={`${l}-${idx}`}>{l}</span>
      ))}
    </div>
  );
}

function LineChart({
  series,
  max,
  height = 130,
  labels,
  bucketS,
  format,
  yFormat,
}: {
  series: Series[];
  max: number;
  height?: number;
  labels: string[];
  bucketS: number;
  format?: (v: number) => string;
  yFormat?: (v: number) => string | number;
}) {
  const n = series[0].points.length;
  const h = useHover(n);
  const w = 1000;
  const fmt = format || ((v: number) => String(v));
  const denom = Math.max(1, max);
  const path = (pts: number[]) =>
    pts
      .map((v, i) => `${i ? 'L' : 'M'}${(i / Math.max(1, pts.length - 1)) * w} ${height - (v / denom) * height}`)
      .join(' ');
  const cursorPct = h.i !== null ? (h.i / Math.max(1, n - 1)) * 100 : 0;

  return (
    <div>
      <div style={{ display: 'flex', gap: 8 }}>
        <YAxis max={max} height={height} format={yFormat} />
        <div
          ref={h.ref}
          onMouseMove={h.onMove}
          onMouseLeave={h.onLeave}
          style={{ position: 'relative', height, flex: 1, minWidth: 0, cursor: 'crosshair' }}
        >
          <svg
            viewBox={`0 0 ${w} ${height}`}
            preserveAspectRatio="none"
            style={{ width: '100%', height, display: 'block', overflow: 'visible' }}
          >
            {[0, 0.25, 0.5, 0.75, 1].map((g) => (
              <line
                key={g}
                x1="0"
                x2={w}
                y1={height * g}
                y2={height * g}
                stroke="rgba(255,255,255,0.1)"
                strokeWidth="1"
                vectorEffect="non-scaling-stroke"
              />
            ))}
            {h.i !== null && (
              <line
                x1={(h.i / Math.max(1, n - 1)) * w}
                x2={(h.i / Math.max(1, n - 1)) * w}
                y1="0"
                y2={height}
                stroke="rgba(255,255,255,0.5)"
                strokeWidth="1"
                vectorEffect="non-scaling-stroke"
              />
            )}
            {series.map((s) => (
              <path
                key={s.label}
                d={path(s.points)}
                fill="none"
                stroke={s.color}
                strokeWidth="1.5"
                vectorEffect="non-scaling-stroke"
              />
            ))}
          </svg>
          {h.i !== null &&
            series.map((s) => (
              <span
                key={s.label}
                aria-hidden="true"
                style={{
                  position: 'absolute',
                  left: `${(h.i! / Math.max(1, n - 1)) * 100}%`,
                  top: height - (s.points[h.i!] / denom) * height,
                  width: 5,
                  height: 5,
                  marginLeft: -2.5,
                  marginTop: -2.5,
                  borderRadius: 'var(--radius-full)',
                  background: s.color,
                }}
              />
            ))}
          {h.i !== null && (
            <TipBox
              leftPct={cursorPct}
              timeLabel={minutesAgoLabel(h.i, n, bucketS)}
              rows={series.map((s) => ({ label: s.label, color: s.color, value: fmt(s.points[h.i!]) }))}
            />
          )}
        </div>
      </div>
      <AxisLabels labels={labels} />
    </div>
  );
}

function BarChart({
  points,
  max,
  color,
  height = 130,
  labels,
  bucketS,
  overlay,
  format,
  yFormat,
}: {
  points: number[];
  max: number;
  color: string;
  height?: number;
  labels: string[];
  bucketS: number;
  overlay?: { points: number[]; max: number; color: string; label: string };
  format?: (v: number) => string;
  yFormat?: (v: number) => string | number;
}) {
  const n = points.length;
  const h = useHover(n);
  const fmt = format || ((v: number) => String(v));
  const denom = Math.max(1, max);
  const cursorPct = h.i !== null ? (h.i / Math.max(1, n - 1)) * 100 : 0;

  return (
    <div>
      <div style={{ display: 'flex', gap: 8 }}>
        <YAxis max={max} height={height} format={yFormat} />
        <div
          ref={h.ref}
          onMouseMove={h.onMove}
          onMouseLeave={h.onLeave}
          style={{
            display: 'flex',
            alignItems: 'flex-end',
            gap: 3,
            height,
            position: 'relative',
            flex: 1,
            minWidth: 0,
            cursor: 'crosshair',
          }}
        >
          {points.map((v, i) => (
            <div
              key={i}
              style={{
                flex: 1,
                height: Math.max(2, (v / denom) * height),
                background: color,
                opacity: h.i === null ? (i === n - 1 ? 1 : 0.55) : h.i === i ? 1 : 0.3,
                transition: 'opacity var(--motion-fast) var(--ease-default)',
              }}
            />
          ))}
          {overlay && (
            <svg
              viewBox="0 0 1000 100"
              preserveAspectRatio="none"
              style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
            >
              <path
                d={overlay.points
                  .map(
                    (v, i) =>
                      `${i ? 'L' : 'M'}${(i / Math.max(1, overlay.points.length - 1)) * 1000} ${
                        100 - (v / Math.max(1, overlay.max)) * 100
                      }`,
                  )
                  .join(' ')}
                fill="none"
                stroke={overlay.color}
                strokeWidth="1"
                strokeDasharray="4 3"
                vectorEffect="non-scaling-stroke"
              />
            </svg>
          )}
          {h.i !== null && (
            <TipBox
              leftPct={cursorPct}
              timeLabel={minutesAgoLabel(h.i, n, bucketS)}
              rows={[{ label: 'throughput', color, value: fmt(points[h.i]) }].concat(
                overlay
                  ? [{ label: overlay.label, color: overlay.color, value: `${overlay.points[h.i]} hosts` }]
                  : [],
              )}
            />
          )}
        </div>
      </div>
      <AxisLabels labels={labels} />
    </div>
  );
}

// --- view ------------------------------------------------------------------

type MetricsViewProps = {
  runId: string;
};

export default function MetricsView({ runId }: MetricsViewProps) {
  const [metrics, setMetrics] = useState<RunMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchRunMetrics(runId)
      .then((data) => {
        setMetrics(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [runId]);

  if (loading) {
    return (
      <div style={{ position: 'relative', flex: 1, minHeight: 0 }}>
        <LoadingOverlay label="Loading metrics…" />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ flex: 1, overflow: 'auto', padding: 32 }}>
        <EmptyState title="Error loading metrics" description={error} icon="alert-circle" />
      </div>
    );
  }

  if (!metrics || metrics.buckets.length === 0) {
    return (
      <div style={{ flex: 1, overflow: 'auto', padding: 32 }}>
        <EmptyState
          title="No metrics yet"
          description="This run has no recorded metrics. Metrics will appear as tickets are processed."
          icon="bar-chart"
        />
      </div>
    );
  }

  const buckets: MetricsBucket[] = metrics.buckets;
  const bucketS = metrics.bucket_s;
  const n = buckets.length;
  const last = buckets[n - 1];
  const labels = xAxisLabels(n, bucketS);

  const donePts = buckets.map((b) => b.done_cumulative);
  const failedPts = buckets.map((b) => b.failed_cumulative);
  const throughputPts = buckets.map((b) => b.throughput);
  const errorPts = buckets.map((b) => b.error_rate * 100);
  const crewPts = buckets.map((b) => b.crew_online);

  const maxProgress = Math.max(...donePts, ...failedPts, 1);
  const maxThroughput = Math.max(...throughputPts, 1);
  const maxError = Math.max(...errorPts, 1);
  const maxCrew = Math.max(...crewPts, 1);

  // Stat tiles — all backed by real bucket data (latest bucket / cumulative).
  const tiles = [
    { label: 'throughput', value: String(last.throughput), delta: 'attempts / bucket', tone: 'live', live: true },
    { label: 'done', value: String(last.done_cumulative), delta: 'completed', tone: undefined },
    { label: 'failed', value: String(last.failed_cumulative), delta: 'failed', tone: last.failed_cumulative > 0 ? 'danger' : undefined },
    { label: 'error rate', value: `${(last.error_rate * 100).toFixed(1)}%`, delta: 'of results', tone: last.error_rate > 0 ? 'danger' : undefined },
  ];

  const spanMin = Math.round((n * bucketS) / 60);

  return (
    <div style={{ flex: 1, overflow: 'auto', padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <h2 style={{ margin: 0, color: 'var(--text-primary)', fontSize: 18 }}>Run Metrics</h2>
        <span style={{ color: 'var(--text-muted)', fontSize: 13, fontFamily: 'var(--font-mono)' }}>
          run {metrics.run_id} · last {spanMin}m · {n} buckets
        </span>
      </div>

      {/* Summary tiles */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 12 }}>
        {tiles.map((t) => (
          <StatTile
            key={t.label}
            label={t.label}
            value={t.value}
            delta={t.delta}
            tone={t.tone}
            live={(t as any).live}
            style={{ minWidth: 0 }}
          />
        ))}
      </div>

      {/* Charts */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.5fr) minmax(0, 1fr)', gap: 16, alignItems: 'start' }}>
        <ChartFrame
          title="Progress over time"
          meta="cumulative tickets"
          height={170}
          legend={
            <Legend
              items={[
                { label: `done ${last.done_cumulative}`, color: 'var(--status-ok)' },
                { label: `failed ${last.failed_cumulative}`, color: 'var(--status-danger)' },
              ]}
            />
          }
        >
          <LineChart
            height={130}
            max={maxProgress}
            labels={labels}
            bucketS={bucketS}
            yFormat={(v) => Math.round(v)}
            series={[
              { label: 'done', points: donePts, color: 'var(--status-ok)' },
              { label: 'failed', points: failedPts, color: 'var(--status-danger)' },
            ]}
          />
        </ChartFrame>

        <ChartFrame
          title="Error rate"
          meta="% of results failing"
          height={170}
          legend={<Legend items={[{ label: 'error rate', color: 'var(--status-danger)' }]} />}
        >
          <LineChart
            height={130}
            max={maxError}
            labels={labels}
            bucketS={bucketS}
            format={(v) => `${Math.round(v * 10) / 10}%`}
            yFormat={(v) => `${Math.round(v)}%`}
            series={[{ label: 'error rate', points: errorPts, color: 'var(--status-danger)' }]}
          />
        </ChartFrame>

        <ChartFrame
          title="Throughput"
          meta="attempts per bucket"
          height={170}
          legend={
            <Legend
              items={[
                { label: 'throughput', color: 'var(--status-live)' },
                { label: 'crew online', color: 'rgba(255,255,255,0.5)' },
              ]}
            />
          }
        >
          <BarChart
            points={throughputPts}
            max={maxThroughput}
            color="var(--status-live)"
            height={130}
            labels={labels}
            bucketS={bucketS}
            format={(v) => String(v)}
            yFormat={(v) => Math.round(v * 10) / 10}
            overlay={{ points: crewPts, max: maxCrew, color: 'rgba(255,255,255,0.5)', label: 'crew online' }}
          />
        </ChartFrame>

        <ChartFrame
          title="Crew online"
          meta="hosts over time"
          height={170}
          legend={<Legend items={[{ label: 'crew online', color: 'var(--text-secondary)' }]} />}
        >
          <LineChart
            height={130}
            max={maxCrew}
            labels={labels}
            bucketS={bucketS}
            format={(v) => `${v} hosts`}
            yFormat={(v) => Math.round(v)}
            series={[{ label: 'crew online', points: crewPts, color: 'var(--text-secondary)' }]}
          />
        </ChartFrame>
      </div>
    </div>
  );
}
