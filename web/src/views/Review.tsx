/**
 * Review — the reductions actually waiting on a person.
 *
 * This is the human end of the no-trust invariant. Nothing auto-ships: when a
 * playbook's `reduce` or the master's independent re-verify routes a ticket to
 * `needs_human`, the reduction that did it lands here, and the decision resolves
 * the ticket — accept settles it to `done`, reject to `failed`.
 *
 * So the queue holds only reductions that are holding a ticket. A run whose
 * reductions are pure output (analyses, syntheses, a report) shows an empty
 * queue, which is the truth: there is nothing to decide. Read those in Outputs.
 */

import { useState, useEffect } from 'react';
import { fetchReductions, acceptReduction, rejectReduction } from '../api/client';
import type { Reduction } from '../api/client';
import { normalizeReduction } from '../api/normalize';
import { EmptyState, Button } from '../ds';
import { LoadingOverlay } from '../components/Spinner';
import ReductionCard from '../components/ReductionCard';
import { awaitsDecision } from '../util/reduction';

type ReviewProps = {
  runId: string;
  liveTick?: number;
  /** Send the reader to the outputs list, which is where the rest of the run is. */
  onGoToOutputs?: () => void;
};

export default function Review({ runId, liveTick, onGoToOutputs }: ReviewProps) {
  const [reductions, setReductions] = useState<Reduction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    fetchReductions(runId)
      .then((data) => setReductions(data.map(normalizeReduction)))
      .catch((err) => setError(err))
      .finally(() => setLoading(false));
  };

  useEffect(load, [runId, liveTick]); // eslint-disable-line react-hooks/exhaustive-deps

  const decide = async (id: number, accept: boolean) => {
    if (!accept && !confirm('Reject this reduction? This will fail the tickets it is holding.')) {
      return;
    }
    setActionError(null);
    setBusyId(id);
    try {
      await (accept ? acceptReduction(id) : rejectReduction(id));
      load();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to record the decision');
    } finally {
      setBusyId(null);
    }
  };

  const queue = reductions.filter(awaitsDecision);

  if (loading && reductions.length === 0) {
    return (
      <div style={{ position: 'relative', flex: 1, minHeight: 0 }}>
        <LoadingOverlay label="Loading review queue…" />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: 32 }}>
        <EmptyState title="Error loading review queue" description={error.message} icon="alert-circle" />
      </div>
    );
  }

  if (queue.length === 0) {
    return (
      <div style={{ padding: 32 }}>
        <EmptyState
          title="Nothing waiting on you"
          description={
            reductions.length > 0
              ? `This run produced ${reductions.length} ${
                  reductions.length === 1 ? 'reduction' : 'reductions'
                }, none of which is holding a ticket for a human. Read them in Outputs.`
              : 'A reduction appears here when it routes a ticket to needs_human — accepting it settles that ticket to done, rejecting it to failed.'
          }
          icon="check-circle"
          action={
            reductions.length > 0 && onGoToOutputs ? (
              <Button data-testid="go-to-outputs" onClick={onGoToOutputs}>
                Go to Outputs
              </Button>
            ) : undefined
          }
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
        <h2 style={{ margin: 0, fontSize: 20, color: 'var(--text-primary)' }}>Review</h2>
        <span style={{ color: 'var(--text-muted)', fontSize: 14 }}>
          {queue.length} waiting on a decision
        </span>
      </div>

      <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
        Accepting settles the tickets this reduction is holding to <code>done</code>; rejecting
        settles them to <code>failed</code>. Follow-on work is seeded as new tickets either way.
      </span>

      {actionError && (
        <div
          data-testid="review-error"
          style={{
            padding: '12px 16px',
            background: 'var(--status-danger-tint)',
            border: '1px solid var(--status-danger-edge)',
            borderRadius: 'var(--radius-md)',
            color: 'var(--status-danger)',
            fontSize: 13,
          }}
        >
          {actionError}
        </div>
      )}

      {queue.map((reduction) => (
        <ReductionCard
          key={reduction.id}
          reduction={reduction}
          actions={
            <>
              <Button
                variant="primary"
                size="sm"
                disabled={busyId === reduction.id}
                onClick={() => decide(reduction.id, true)}
              >
                Accept
              </Button>
              <Button
                variant="danger"
                size="sm"
                disabled={busyId === reduction.id}
                onClick={() => decide(reduction.id, false)}
              >
                Reject
              </Button>
            </>
          }
        />
      ))}
    </div>
  );
}
