/**
 * TicketDrawer - full ticket detail drawer.
 * Phase B2: board-level fields only.
 * Phase B3: expanded with payload/result/attempt timeline/evidence (THIS FILE).
 */

import { useEffect, useState } from 'react';
import type { Ticket, TicketDetail } from '../api/client';
import { fetchTicketDetail, requeueTicket } from '../api/client';
import { Drawer, StatusPill, Badge } from '../ds';
import { normalizeTicketState, normalizeTicketDetail } from '../api/normalize';
import { AuthError } from '../api/client';

type TicketDrawerProps = {
  isOpen: boolean;
  ticket: Ticket | null;
  onClose: () => void;
};

export default function TicketDrawer({ isOpen, ticket, onClose }: TicketDrawerProps) {
  const [detail, setDetail] = useState<TicketDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [requeueLoading, setRequeueLoading] = useState(false);
  const [requeueError, setRequeueError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || !ticket) {
      setDetail(null);
      setError(null);
      setRequeueError(null);
      return;
    }

    setLoading(true);
    setError(null);
    setRequeueError(null);

    fetchTicketDetail(ticket.id)
      .then((data) => {
        setDetail(normalizeTicketDetail(data));
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message || 'Failed to load ticket detail');
        setLoading(false);
      });
  }, [isOpen, ticket]);

  const handleRequeue = async () => {
    if (!ticket) return;

    setRequeueLoading(true);
    setRequeueError(null);

    try {
      await requeueTicket(ticket.id);
      // Refresh the ticket detail
      const data = await fetchTicketDetail(ticket.id);
      setDetail(normalizeTicketDetail(data));
      setRequeueLoading(false);
    } catch (err) {
      if (err instanceof AuthError) {
        setRequeueError('Authentication required');
      } else if (err instanceof Error) {
        setRequeueError(err.message);
      } else {
        setRequeueError('Failed to requeue ticket');
      }
      setRequeueLoading(false);
    }
  };

  if (!ticket) {
    return null;
  }

  const uiState = normalizeTicketState(ticket.state);

  return (
    <Drawer isOpen={isOpen} onClose={onClose} title={ticket.id} width="600px">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 24, padding: '20px 24px' }}>
        {/* Board-level header (B2) */}
        <div style={{ display: 'flex', gap: 10 }}>
          <StatusPill state={uiState} size="md" />
          <Badge variant="outline" tone="ok">
            {ticket.phase}
          </Badge>
        </div>

        {/* Loading state */}
        {loading && (
          <div style={{ color: 'var(--text-muted)', fontSize: 14 }}>
            Loading ticket detail...
          </div>
        )}

        {/* Error state */}
        {error && (
          <div style={{ color: 'var(--status-danger)', fontSize: 14 }}>
            Error: {error}
          </div>
        )}

        {/* Detail loaded */}
        {detail && !loading && !error && (
          <>
            {/* Requeue control (D3) - only for guard-routed needs_human tickets */}
            {detail.ticket.state === 'needs-human' && !detail.ticket.reduction_id && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <button
                  onClick={handleRequeue}
                  disabled={requeueLoading}
                  style={{
                    padding: '8px 16px',
                    background: 'var(--surface-card)',
                    color: 'var(--text-primary)',
                    border: '1px solid var(--border-hairline)',
                    borderRadius: 'var(--radius-sm)',
                    cursor: requeueLoading ? 'not-allowed' : 'pointer',
                    fontSize: 13,
                    fontWeight: 500,
                  }}
                >
                  {requeueLoading ? 'Requeuing...' : 'Requeue'}
                </button>
                {requeueError && (
                  <div style={{ color: 'var(--status-danger)', fontSize: 12 }}>
                    {requeueError}
                  </div>
                )}
              </div>
            )}

            {/* Subject */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>Subject</span>
              <span style={{ color: 'var(--text-primary)', fontSize: 14 }}>
                {detail.ticket.subject}
              </span>
            </div>

            {/* Payload section */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <span style={{ color: 'var(--text-primary)', fontSize: 14, fontWeight: 600 }}>
                Payload
              </span>
              <pre
                style={{
                  background: 'var(--surface-card)',
                  border: '1px solid var(--border-hairline)',
                  borderRadius: 'var(--radius-sm)',
                  padding: 12,
                  fontSize: 12,
                  fontFamily: 'var(--font-mono)',
                  overflow: 'auto',
                  maxHeight: 200,
                  color: 'var(--text-secondary)',
                }}
              >
                {JSON.stringify(detail.payload, null, 2)}
              </pre>
            </div>

            {/* Result section */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <span style={{ color: 'var(--text-primary)', fontSize: 14, fontWeight: 600 }}>
                Result
              </span>
              {detail.result ? (
                <div
                  style={{
                    background: 'var(--surface-card)',
                    border: '1px solid var(--border-hairline)',
                    borderRadius: 'var(--radius-sm)',
                    padding: 12,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 8,
                  }}
                >
                  <div style={{ display: 'grid', gridTemplateColumns: '100px 1fr', gap: 8 }}>
                    <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>Outcome:</span>
                    <span
                      style={{
                        fontSize: 13,
                        fontFamily: 'var(--font-mono)',
                        color: detail.result.outcome === 'ok' ? 'var(--status-ok)' : 'var(--status-danger)',
                      }}
                    >
                      {detail.result.outcome}
                    </span>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '100px 1fr', gap: 8 }}>
                    <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>Reason:</span>
                    <span style={{ fontSize: 13, fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                      {detail.result.termination_reason}
                    </span>
                  </div>
                  {detail.result.result_ref && (
                    <div style={{ display: 'grid', gridTemplateColumns: '100px 1fr', gap: 8 }}>
                      <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>Ref:</span>
                      <span
                        style={{
                          fontSize: 12,
                          fontFamily: 'var(--font-mono)',
                          color: 'var(--status-live)',
                          wordBreak: 'break-all',
                        }}
                      >
                        {detail.result.result_ref}
                      </span>
                    </div>
                  )}
                  {detail.result.error_summary && (
                    <div style={{ display: 'grid', gridTemplateColumns: '100px 1fr', gap: 8 }}>
                      <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>Error:</span>
                      <span style={{ fontSize: 12, color: 'var(--status-danger)' }}>
                        {detail.result.error_summary}
                      </span>
                    </div>
                  )}
                </div>
              ) : (
                <div
                  style={{
                    color: 'var(--text-muted)',
                    fontSize: 13,
                    fontStyle: 'italic',
                    padding: 12,
                  }}
                >
                  No result yet
                </div>
              )}
            </div>

            {/* Attempt timeline */}
            {detail.attempt_timeline.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <span style={{ color: 'var(--text-primary)', fontSize: 14, fontWeight: 600 }}>
                  Attempt Timeline
                </span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {detail.attempt_timeline.map((att, idx) => (
                    <div
                      key={idx}
                      style={{
                        background: 'var(--surface-card)',
                        border: '1px solid var(--border-hairline)',
                        borderRadius: 'var(--radius-sm)',
                        padding: 10,
                        fontSize: 12,
                      }}
                    >
                      <div style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
                        <Badge variant="subtle">
                          #{att.attempt}
                        </Badge>
                        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                          {att.host}
                        </span>
                        {att.outcome && (
                          <Badge
                            variant="subtle"
                            tone={att.outcome === 'ok' ? 'ok' : 'danger'}
                          >
                            {att.outcome}
                          </Badge>
                        )}
                      </div>
                      {att.termination_reason && (
                        <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                          {att.termination_reason}
                        </div>
                      )}
                      {att.error_summary && (
                        <div style={{ color: 'var(--status-danger)', fontSize: 11, marginTop: 4 }}>
                          {att.error_summary}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Evidence */}
            {detail.evidence.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <span style={{ color: 'var(--text-primary)', fontSize: 14, fontWeight: 600 }}>
                  Evidence
                </span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {detail.evidence.map((ev, idx) => (
                    <div
                      key={idx}
                      style={{
                        background: 'var(--surface-card)',
                        border: '1px solid var(--border-hairline)',
                        borderRadius: 'var(--radius-sm)',
                        padding: 10,
                        fontSize: 12,
                        display: 'flex',
                        gap: 8,
                        alignItems: 'center',
                      }}
                    >
                      <Badge variant="subtle">
                        #{ev.attempt}
                      </Badge>
                      <a
                        href={ev.ref}
                        style={{
                          color: 'var(--status-live)',
                          fontFamily: 'var(--font-mono)',
                          fontSize: 11,
                          wordBreak: 'break-all',
                        }}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {ev.ref}
                      </a>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </Drawer>
  );
}
