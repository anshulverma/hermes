/**
 * Outputs — what a run produced, read-only.
 *
 * Every reduction the run's `reduce` emitted: the per-item analyses, the
 * syntheses, the final report. This is where you come to *read* a run.
 *
 * Deliberately without accept/reject. Those settle a `needs_human` ticket, and
 * a reduction holding no such ticket has no decision in it — offering the
 * buttons anyway implies an authority they do not have, since they would flip a
 * flag and move nothing. The ones that really are waiting on a person live in
 * Review, which this links to when it has any.
 */

import { useState, useEffect } from 'react';
import { fetchReductions } from '../api/client';
import type { Reduction } from '../api/client';
import { normalizeReduction } from '../api/normalize';
import { EmptyState } from '../ds';
import { LoadingOverlay } from '../components/Spinner';
import ReductionCard from '../components/ReductionCard';
import { awaitsDecision } from '../util/reduction';

type OutputsProps = {
  runId: string;
  liveTick?: number;
  /** Send the reader to the review queue when something is waiting there. */
  onGoToReview?: () => void;
};

export default function Outputs({ runId, liveTick, onGoToReview }: OutputsProps) {
  const [reductions, setReductions] = useState<Reduction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchReductions(runId)
      .then((data) => setReductions(data.map(normalizeReduction)))
      .catch((err) => setError(err))
      .finally(() => setLoading(false));
  }, [runId, liveTick]);

  const waiting = reductions.filter(awaitsDecision).length;

  // Most synthesised first. A pipeline banks its reductions in phase order, so
  // the newest is the most aggregated: the report before the syntheses before
  // the seventeen per-item analyses. Reading a run top-down should start with
  // the thing that read the rest of it.
  const ordered = [...reductions].sort((a, b) => b.id - a.id);

  // What this run produced, by kind — so the shape of it is legible before
  // scrolling through nineteen cards.
  const byKind = ordered.reduce<Record<string, number>>((acc, r) => {
    acc[r.kind] = (acc[r.kind] ?? 0) + 1;
    return acc;
  }, {});

  // Only blank the page on the first load; a live refetch must not wipe what is
  // already on screen.
  if (loading && reductions.length === 0) {
    return (
      <div style={{ position: 'relative', flex: 1, minHeight: 0 }}>
        <LoadingOverlay label="Loading outputs…" />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: 32 }}>
        <EmptyState title="Error loading outputs" description={error.message} icon="alert-circle" />
      </div>
    );
  }

  if (reductions.length === 0) {
    return (
      <div style={{ padding: 32 }}>
        <EmptyState
          title="No outputs yet"
          description="Outputs appear as the reduce phase turns finished tickets into analyses, syntheses and reports."
          icon="inbox"
        />
      </div>
    );
  }

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
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <h2 style={{ margin: 0, fontSize: 20, color: 'var(--text-primary)' }}>Outputs</h2>
        <span style={{ color: 'var(--text-muted)', fontSize: 14 }}>
          {Object.entries(byKind)
            .map(([kind, n]) => `${n} ${kind}`)
            .join(' · ')}
        </span>
        {waiting > 0 && onGoToReview && (
          <button
            type="button"
            data-testid="go-to-review"
            onClick={onGoToReview}
            style={{
              marginLeft: 'auto',
              padding: '4px 10px',
              fontSize: 12,
              color: 'var(--status-attention, #e3b341)',
              background: 'var(--wash-subtle)',
              border: '1px solid var(--border-hairline)',
              borderRadius: 'var(--radius-md)',
              cursor: 'pointer',
            }}
          >
            {waiting} waiting on you
          </button>
        )}
      </div>

      {ordered.map((reduction) => (
        <ReductionCard key={reduction.id} reduction={reduction} />
      ))}
    </div>
  );
}
