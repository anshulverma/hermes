/**
 * MetricsView - Phase E1: Run metrics (core charts only).
 * REAL time-bucketed metrics from /api/runs/{id}/metrics.
 * NO Resources (E2) or Agent Usage (E3) sections (ungated).
 */

import { useState, useEffect } from 'react';
import { fetchRunMetrics } from '../api/client';
import type { RunMetrics } from '../api/client';
import { Card, EmptyState } from '../ds';

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
      <div
        style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--text-muted)',
        }}
      >
        Loading metrics...
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ flex: 1, overflow: 'auto', padding: 32 }}>
        <EmptyState
          title="Error loading metrics"
          message={error}
          icon="alert-circle"
        />
      </div>
    );
  }

  if (!metrics || metrics.buckets.length === 0) {
    return (
      <div style={{ flex: 1, overflow: 'auto', padding: 32 }}>
        <EmptyState
          title="No metrics yet"
          message="This run has no recorded metrics. Metrics will appear as tickets are processed."
          icon="bar-chart"
        />
      </div>
    );
  }

  const buckets = metrics.buckets;
  const maxThroughput = Math.max(...buckets.map((b) => b.throughput), 1);
  const maxDone = Math.max(...buckets.map((b) => b.done_cumulative), 1);
  const maxCrew = Math.max(...buckets.map((b) => b.crew_online), 1);

  return (
    <div style={{ flex: 1, overflow: 'auto', padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <h2 style={{ margin: 0, color: 'var(--text-primary)', fontSize: 18 }}>Run Metrics</h2>
        <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>
          {buckets.length} buckets · {metrics.bucket_s}s each
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 16 }}>
        {/* Throughput chart */}
        <Card padding style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <span style={{ color: 'var(--text-primary)', fontSize: 14 }}>Throughput</span>
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>attempts/bucket</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 120 }}>
            {buckets.map((b, i) => (
              <div
                key={i}
                style={{
                  flex: 1,
                  height: Math.max(2, (b.throughput / maxThroughput) * 120),
                  background: 'var(--status-live)',
                  opacity: i === buckets.length - 1 ? 1 : 0.6,
                }}
                title={`${b.throughput} attempts`}
              />
            ))}
          </div>
        </Card>

        {/* Progress (done/failed cumulative) */}
        <Card padding style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <span style={{ color: 'var(--text-primary)', fontSize: 14 }}>Progress</span>
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>cumulative</span>
          </div>
          <div style={{ position: 'relative', height: 120 }}>
            <svg
              viewBox={`0 0 ${buckets.length * 10} 120`}
              preserveAspectRatio="none"
              style={{ width: '100%', height: '100%' }}
            >
              {/* Done line */}
              <polyline
                points={buckets
                  .map((b, i) => `${i * 10},${120 - (b.done_cumulative / maxDone) * 120}`)
                  .join(' ')}
                fill="none"
                stroke="var(--status-ok)"
                strokeWidth="1.5"
                vectorEffect="non-scaling-stroke"
              />
              {/* Failed line */}
              <polyline
                points={buckets
                  .map((b, i) => `${i * 10},${120 - (b.failed_cumulative / maxDone) * 120}`)
                  .join(' ')}
                fill="none"
                stroke="var(--status-danger)"
                strokeWidth="1.5"
                vectorEffect="non-scaling-stroke"
              />
            </svg>
            <div style={{ display: 'flex', gap: 12, marginTop: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
                <div style={{ width: 12, height: 2, background: 'var(--status-ok)' }} />
                <span style={{ color: 'var(--text-muted)' }}>
                  done: {buckets[buckets.length - 1].done_cumulative}
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
                <div style={{ width: 12, height: 2, background: 'var(--status-danger)' }} />
                <span style={{ color: 'var(--text-muted)' }}>
                  failed: {buckets[buckets.length - 1].failed_cumulative}
                </span>
              </div>
            </div>
          </div>
        </Card>

        {/* Error rate */}
        <Card padding style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <span style={{ color: 'var(--text-primary)', fontSize: 14 }}>Error Rate</span>
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>per bucket</span>
          </div>
          <div style={{ position: 'relative', height: 120 }}>
            <svg
              viewBox={`0 0 ${buckets.length * 10} 120`}
              preserveAspectRatio="none"
              style={{ width: '100%', height: '100%' }}
            >
              <polyline
                points={buckets
                  .map((b, i) => `${i * 10},${120 - b.error_rate * 120}`)
                  .join(' ')}
                fill="none"
                stroke="var(--status-danger)"
                strokeWidth="1.5"
                vectorEffect="non-scaling-stroke"
              />
            </svg>
            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-muted)' }}>
              Current: {(buckets[buckets.length - 1].error_rate * 100).toFixed(1)}%
            </div>
          </div>
        </Card>

        {/* Crew online */}
        <Card padding style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <span style={{ color: 'var(--text-primary)', fontSize: 14 }}>Crew Online</span>
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>hosts</span>
          </div>
          <div style={{ position: 'relative', height: 120 }}>
            <svg
              viewBox={`0 0 ${buckets.length * 10} 120`}
              preserveAspectRatio="none"
              style={{ width: '100%', height: '100%' }}
            >
              <polyline
                points={buckets
                  .map((b, i) => `${i * 10},${120 - (b.crew_online / maxCrew) * 120}`)
                  .join(' ')}
                fill="none"
                stroke="var(--text-secondary)"
                strokeWidth="1.5"
                vectorEffect="non-scaling-stroke"
              />
            </svg>
            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-muted)' }}>
              Current: {buckets[buckets.length - 1].crew_online} hosts
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
