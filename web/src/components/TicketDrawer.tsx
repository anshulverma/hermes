/**
 * TicketDrawer - full ticket detail drawer.
 * Phase B2: board-level fields only.
 * Phase B3: expanded with payload/result/attempt timeline/evidence (THIS FILE).
 */

import { useEffect, useState } from 'react';
import type { Ticket, TicketDetail } from '../api/client';
import { fetchTicketDetail } from '../api/client';
import { Drawer, StatusPill, Badge } from '../ds';
import { normalizeTicketState, normalizeTicketDetail } from '../api/normalize';

type TicketDrawerProps = {
  isOpen: boolean;
  ticket: Ticket | null;
  onClose: () => void;
};

export default function TicketDrawer({ isOpen, ticket, onClose }: TicketDrawerProps) {
  const [detail, setDetail] = useState<TicketDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || !ticket) {
      setDetail(null);
      setError(null);
      return;
    }

    setLoading(true);
    setError(null);

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
          <div style={{ color: 'var(--error-text)', fontSize: 14 }}>
            Error: {error}
          </div>
        )}

        {/* Detail loaded */}
        {detail && !loading && !error && (
          <>
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
                  background: 'var(--bg-surface)',
                  border: '1px solid var(--border-primary)',
                  borderRadius: 6,
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
                    background: 'var(--bg-surface)',
                    border: '1px solid var(--border-primary)',
                    borderRadius: 6,
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
                        color: detail.result.outcome === 'ok' ? 'var(--ok-text)' : 'var(--error-text)',
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
                          color: 'var(--link-color)',
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
                      <span style={{ fontSize: 12, color: 'var(--error-text)' }}>
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
                        background: 'var(--bg-surface)',
                        border: '1px solid var(--border-primary)',
                        borderRadius: 6,
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
                        <div style={{ color: 'var(--error-text)', fontSize: 11, marginTop: 4 }}>
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
                        background: 'var(--bg-surface)',
                        border: '1px solid var(--border-primary)',
                        borderRadius: 6,
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
                          color: 'var(--link-color)',
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
