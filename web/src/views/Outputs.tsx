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
          {reductions.length} {reductions.length === 1 ? 'reduction' : 'reductions'}
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

      {reductions.map((reduction) => (
        <ReductionCard key={reduction.id} reduction={reduction} />
      ))}
    </div>
  );
}
