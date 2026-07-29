/**
 * Findings - reductions view with real review_state + member tickets.
 * Phase B6: full-stack real data (no mock fix_state).
 */

import { useState, useEffect } from 'react';
import { fetchReductions } from '../api/client';
import type { Reduction } from '../api/client';
import { deriveFindingStatus, normalizeTicketState } from '../api/normalize';
import { Card, Badge, StatusPill, Divider, EmptyState } from '../ds';

type FindingsProps = {
  runId: string;
};

export default function Findings({ runId }: FindingsProps) {
  const [reductions, setReductions] = useState<Reduction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchReductions(runId)
      .then((data) => setReductions(data))
      .catch((err) => setError(err))
      .finally(() => setLoading(false));
  }, [runId]);

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
                      <StatusPill state={normalizeTicketState(ticket.state)} size="sm" />
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
          </Card>
        );
      })}
    </div>
  );
}
