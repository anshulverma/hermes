/**
 * Findings - reductions view with real review_state + member tickets.
 * Phase B6: full-stack real data (no mock fix_state).
 */

import { useState, useEffect } from 'react';
import { fetchReductions, acceptReduction, rejectReduction } from '../api/client';
import type { Reduction } from '../api/client';
import { deriveFindingStatus } from '../api/normalize';
import { Card, Badge, StatusPill, Divider, EmptyState, Button } from '../ds';

type FindingsProps = {
  runId: string;
};

export default function Findings({ runId }: FindingsProps) {
  const [reductions, setReductions] = useState<Reduction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const loadReductions = () => {
    setLoading(true);
    setError(null);
    fetchReductions(runId)
      .then((data) => setReductions(data))
      .catch((err) => setError(err))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadReductions();
  }, [runId]);

  const handleAccept = async (reductionId: number) => {
    setActionError(null);
    try {
      await acceptReduction(reductionId);
      // Refresh the list
      loadReductions();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to accept reduction');
    }
  };

  const handleReject = async (reductionId: number) => {
    if (!confirm('Reject this reduction? This will fail the linked member tickets.')) {
      return;
    }

    setActionError(null);
    try {
      await rejectReduction(reductionId);
      // Refresh the list
      loadReductions();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to reject reduction');
    }
  };

  if (loading) {
    return (
      <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)' }}>
        Loading findings...
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: 32 }}>
        <EmptyState
          title="Error loading findings"
          message={error.message}
          icon="alert-circle"
        />
      </div>
    );
  }

  if (reductions.length === 0) {
    return (
      <div style={{ padding: 32 }}>
        <EmptyState
          title="No findings"
          message="This run has no reductions yet. Findings appear as the reduce phase processes tickets."
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
        <h2 style={{ margin: 0, fontSize: 20, color: 'var(--text-primary)' }}>
          Findings
        </h2>
        <span style={{ color: 'var(--text-muted)', fontSize: 14 }}>
          {reductions.length} {reductions.length === 1 ? 'reduction' : 'reductions'}
        </span>
      </div>

      {actionError && (
        <div
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

      {reductions.map((reduction) => {
        const status = deriveFindingStatus(reduction);

        return (
          <Card key={reduction.id} padding={true}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
              <div
                style={{
                  flex: 1,
                  minWidth: 0,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 6,
                }}
              >
                {/* ID, kind badge, review_state pill, derived status */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 12,
                      color: 'var(--text-muted)',
                    }}
                  >
                    {reduction.id}
                  </span>
                  <Badge size="sm" variant="outline">
                    {reduction.kind}
                  </Badge>
                  <Badge size="sm" variant="outline">
                    {reduction.phase}
                  </Badge>
                  <StatusPill state={reduction.review_state} size="sm" />
                  {status !== reduction.review_state && (
                    <StatusPill state={status} size="sm" />
                  )}
                </div>

                {/* Title from json */}
                <span
                  style={{
                    color: 'var(--text-primary)',
                    fontSize: 16,
                    lineHeight: '22px',
                  }}
                >
                  {reduction.json.title || 'Untitled reduction'}
                </span>
              </div>
            </div>

            {/* Member tickets */}
            {reduction.member_tickets.length > 0 && (
              <>
                <Divider style={{ margin: '16px 0 12px' }} />
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    flexWrap: 'wrap',
                  }}
                >
                  <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                    {reduction.member_tickets.length}{' '}
                    {reduction.member_tickets.length === 1
                      ? 'member ticket'
                      : 'member tickets'}
                  </span>
                  {reduction.member_tickets.map((ticket) => (
                    <div
                      key={ticket.id}
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 6,
                        padding: '2px 6px 2px 2px',
                        border: '1px solid var(--border-hairline)',
                        borderRadius: 'var(--radius-lg)',
                      }}
                    >
                      <StatusPill state={ticket.state} size="sm" />
                      <span
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: 11,
                          color: 'var(--text-secondary)',
                        }}
                      >
                        {ticket.id}
                      </span>
                    </div>
                  ))}
                </div>
              </>
            )}

            {/* Accept/Reject actions (Phase D4) - only for pending reductions */}
            {reduction.review_state === 'pending' && (
              <>
                <Divider style={{ margin: '16px 0 12px' }} />
                <div style={{ display: 'flex', gap: 8 }}>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => handleAccept(reduction.id)}
                  >
                    Accept
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => handleReject(reduction.id)}
                  >
                    Reject
                  </Button>
                </div>
              </>
            )}
          </Card>
        );
      })}
    </div>
  );
}
