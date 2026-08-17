/**
 * Findings - reductions view with real review_state + member tickets.
 * Phase B6: full-stack real data (no mock fix_state).
 */

import { useState, useEffect } from 'react';
import { fetchReductions, acceptReduction, rejectReduction } from '../api/client';
import type { Reduction } from '../api/client';
import { deriveFindingStatus, normalizeReduction } from '../api/normalize';
import { Card, Badge, StatusPill, Divider, EmptyState, Button } from '../ds';
import { LoadingOverlay } from '../components/Spinner';
import JsonView from '../components/JsonView';
import Clamp from '../components/Clamp';
import Markdown from '../components/Markdown';
import { reductionHeadline, reductionFacts, reductionProse } from '../util/reduction';

type FindingsProps = {
  runId: string;
  liveTick?: number;
};

export default function Findings({ runId, liveTick }: FindingsProps) {
  const [reductions, setReductions] = useState<Reduction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const loadReductions = () => {
    setLoading(true);
    setError(null);
    fetchReductions(runId)
      .then((data) => setReductions(data.map(normalizeReduction)))
      .catch((err) => setError(err))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadReductions();
  }, [runId, liveTick]); // eslint-disable-line react-hooks/exhaustive-deps

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

  // Only show the full-page spinner on the initial load (no data yet).
  // Background live refetches must not blank the already-rendered findings list.
  if (loading && reductions.length === 0) {
    return (
      <div style={{ position: 'relative', flex: 1, minHeight: 0 }}>
        <LoadingOverlay label="Loading findings…" />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: 32 }}>
        <EmptyState
          title="Error loading findings"
          description={error.message}
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
          description="This run has no reductions yet. Findings appear as the reduce phase processes tickets."
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
        const facts = reductionFacts(reduction.json);
        const prose = reductionProse(reduction.json);

        return (
          <Card key={reduction.id} padding="md">
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

                {/* A name derived from the document. Reductions carry no
                    `title`, so rendering that key alone gave every card the
                    same "Untitled reduction" and showed none of its content. */}
                <span
                  style={{
                    color: 'var(--text-primary)',
                    fontSize: 16,
                    lineHeight: '22px',
                  }}
                >
                  {reductionHeadline(reduction.json, reduction.kind)}
                </span>

                {/* What happened, from the document's own scalars. */}
                {facts.length > 0 && (
                  <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                    {facts.map((f) => (
                      <span key={f.key} style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                        <span style={{ fontFamily: 'var(--font-mono)' }}>{f.key}</span>{' '}
                        <span style={{ color: 'var(--text-secondary)' }}>{f.value}</span>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* The content itself: the long string leaves, which is where an
                agent's actual analysis, synthesis or report lives. */}
            {prose.map((p) => (
              <div key={p.path} style={{ marginTop: 12 }}>
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                    color: 'var(--text-muted)',
                  }}
                >
                  {p.path}
                </span>
                <div
                  style={{
                    marginTop: 4,
                    padding: 10,
                    background: 'var(--wash-subtle)',
                    border: '1px solid var(--border-hairline)',
                    borderRadius: 'var(--radius-sm)',
                  }}
                >
                  {/* Clamped, not scrolled: an 800-line input context must not
                      bury the analysis under it, and a scroll box here would
                      take the wheel from the page. */}
                  <Clamp text={p.text} data-testid={`finding-prose-${reduction.id}`}>
                    <Markdown maxHeight={null} fontSize={12}>
                      {p.text}
                    </Markdown>
                  </Clamp>
                </div>
              </div>
            ))}

            {/* The whole document, for anything the reading above did not
                surface. Mounts only when opened. */}
            <details style={{ marginTop: 12 }}>
              <summary
                style={{
                  cursor: 'pointer',
                  fontSize: 12,
                  color: 'var(--text-muted)',
                }}
              >
                Full document
              </summary>
              <div style={{ marginTop: 8 }}>
                <JsonView value={reduction.json} maxHeight={null} />
              </div>
            </details>

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
