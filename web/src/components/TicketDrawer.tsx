/**
 * TicketDrawer - full ticket detail drawer: live context + operator actions.
 *
 * Shows why a ticket is in its current state (derived reason banner), its
 * progress/state history, the flagging reduction when present, and the full
 * payload/result/attempt/evidence detail. Renders an actions menu strictly from
 * the server's available_actions so the UI and API agree on legality:
 * requeue / retry / abandon (confirm) / reprioritize / accept-reject reduction.
 */

import { useEffect, useState } from 'react';
import type { Ticket, TicketDetail } from '../api/client';
import {
  fetchTicketDetail,
  requeueTicket,
  retryTicket,
  abandonTicket,
  setTicketPriority,
  acceptReduction,
  rejectReduction,
  AuthError,
} from '../api/client';
import { Drawer, StatusPill, Badge } from '../ds';
import { normalizeTicketState, normalizeTicketDetail } from '../api/normalize';

type TicketDrawerProps = {
  isOpen: boolean;
  ticket: Ticket | null;
  onClose: () => void;
  // Called after a successful mutation so callers can refresh the board.
  onActionSuccess?: () => void;
};

const ATTENTION_STATES = new Set(['needs-human', 'failed', 'parked']);

const btnStyle = (tone: 'default' | 'danger' | 'primary', disabled: boolean): React.CSSProperties => ({
  padding: '6px 12px',
  fontSize: 13,
  fontWeight: 500,
  color: tone === 'danger' ? 'var(--status-danger)' : 'var(--text-primary)',
  background: tone === 'primary' ? 'var(--status-live)' : 'var(--wash-subtle)',
  border: '1px solid var(--border-hairline)',
  borderRadius: 'var(--radius-md)',
  cursor: disabled ? 'not-allowed' : 'pointer',
  opacity: disabled ? 0.6 : 1,
});

export default function TicketDrawer({ isOpen, ticket, onClose, onActionSuccess }: TicketDrawerProps) {
  const [detail, setDetail] = useState<TicketDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmAbandon, setConfirmAbandon] = useState(false);
  const [priorityInput, setPriorityInput] = useState('');

  useEffect(() => {
    if (!isOpen || !ticket) {
      setDetail(null);
      setError(null);
      setActionError(null);
      setConfirmAbandon(false);
      return;
    }

    setLoading(true);
    setError(null);
    setActionError(null);
    setConfirmAbandon(false);

    fetchTicketDetail(ticket.id)
      .then((data) => {
        const norm = normalizeTicketDetail(data);
        setDetail(norm);
        setPriorityInput(String(norm.ticket.priority ?? ''));
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message || 'Failed to load ticket detail');
        setLoading(false);
      });
  }, [isOpen, ticket]);

  async function refresh() {
    if (!ticket) return;
    const data = await fetchTicketDetail(ticket.id);
    setDetail(normalizeTicketDetail(data));
  }

  async function runAction(fn: () => Promise<unknown>) {
    setActionLoading(true);
    setActionError(null);
    try {
      await fn();
      await refresh();
      onActionSuccess?.();
    } catch (err) {
      if (err instanceof AuthError) {
        setActionError('Authentication required');
      } else if (err instanceof Error) {
        setActionError(err.message);
      } else {
        setActionError('Action failed');
      }
    } finally {
      setActionLoading(false);
      setConfirmAbandon(false);
    }
  }

  if (!ticket) {
    return null;
  }

  const uiState = normalizeTicketState(ticket.state);

  const actions = detail?.available_actions ?? [];
  const reductionId = detail?.reduction?.id ?? detail?.ticket.reduction_id ?? null;

  return (
    <Drawer open={isOpen} fixed onClose={onClose} title={ticket.id} width="600px">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 24, padding: '20px 24px' }}>
        {/* Board-level header */}
        <div style={{ display: 'flex', gap: 10 }}>
          <StatusPill state={uiState} size="md" />
          <Badge variant="outline" tone="ok">
            {ticket.phase}
          </Badge>
        </div>

        {loading && (
          <div style={{ color: 'var(--text-muted)', fontSize: 14 }}>Loading ticket detail...</div>
        )}

        {error && (
          <div style={{ color: 'var(--status-danger)', fontSize: 14 }}>Error: {error}</div>
        )}

        {detail && !loading && !error && (
          <>
            {/* Reason banner — why the ticket is in its current state */}
            {detail.reason && (
              <div
                data-testid="ticket-reason"
                role="note"
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 4,
                  padding: '10px 12px',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border-hairline)',
                  background: 'var(--wash-subtle)',
                  borderLeft: `3px solid ${
                    ATTENTION_STATES.has(detail.ticket.state)
                      ? 'var(--status-attention)'
                      : 'var(--status-live)'
                  }`,
                }}
              >
                <span style={{ color: 'var(--text-muted)', fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.4 }}>
                  Why this state
                </span>
                <span style={{ color: 'var(--text-primary)', fontSize: 13 }}>{detail.reason}</span>
              </div>
            )}

            {/* Actions menu — rendered strictly from available_actions */}
            {actions.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <span style={{ color: 'var(--text-primary)', fontSize: 14, fontWeight: 600 }}>
                  Actions
                </span>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
                  {actions.includes('requeue') && (
                    <button
                      style={btnStyle('default', actionLoading)}
                      disabled={actionLoading}
                      onClick={() => runAction(() => requeueTicket(ticket.id))}
                    >
                      Requeue
                    </button>
                  )}

                  {actions.includes('retry') && (
                    <button
                      style={btnStyle('default', actionLoading)}
                      disabled={actionLoading}
                      onClick={() => runAction(() => retryTicket(ticket.id))}
                    >
                      Retry
                    </button>
                  )}

                  {actions.includes('accept_reduction') && (
                    <button
                      style={btnStyle('primary', actionLoading)}
                      disabled={actionLoading || reductionId == null}
                      onClick={() => reductionId != null && runAction(() => acceptReduction(reductionId))}
                    >
                      Accept
                    </button>
                  )}

                  {actions.includes('reject_reduction') && (
                    <button
                      style={btnStyle('default', actionLoading)}
                      disabled={actionLoading || reductionId == null}
                      onClick={() => reductionId != null && runAction(() => rejectReduction(reductionId))}
                    >
                      Reject
                    </button>
                  )}

                  {actions.includes('reprioritize') && (
                    <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
                      <input
                        aria-label="priority"
                        type="number"
                        value={priorityInput}
                        onChange={(e) => setPriorityInput(e.target.value)}
                        style={{
                          width: 72,
                          padding: '6px 8px',
                          fontSize: 13,
                          color: 'var(--text-primary)',
                          background: 'var(--surface-card)',
                          border: '1px solid var(--border-hairline)',
                          borderRadius: 'var(--radius-md)',
                        }}
                      />
                      <button
                        style={btnStyle('default', actionLoading || priorityInput.trim() === '')}
                        disabled={actionLoading || priorityInput.trim() === ''}
                        onClick={() => runAction(() => setTicketPriority(ticket.id, Number(priorityInput)))}
                      >
                        Set priority
                      </button>
                    </span>
                  )}

                  {actions.includes('abandon') && !confirmAbandon && (
                    <button
                      style={btnStyle('danger', actionLoading)}
                      disabled={actionLoading}
                      onClick={() => setConfirmAbandon(true)}
                    >
                      Abandon
                    </button>
                  )}
                </div>

                {confirmAbandon && (
                  <div
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 8,
                      padding: 12,
                      background: 'var(--wash-subtle)',
                      border: '1px solid var(--border-hairline)',
                      borderRadius: 'var(--radius-md)',
                    }}
                  >
                    <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                      Abandon this ticket? It will be marked failed and its lease released.
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button
                        style={btnStyle('danger', actionLoading)}
                        disabled={actionLoading}
                        onClick={() => runAction(() => abandonTicket(ticket.id))}
                      >
                        {actionLoading ? 'Abandoning...' : 'Confirm abandon'}
                      </button>
                      <button
                        style={btnStyle('default', actionLoading)}
                        disabled={actionLoading}
                        onClick={() => setConfirmAbandon(false)}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}

                {actionError && (
                  <div style={{ color: 'var(--status-danger)', fontSize: 12 }}>{actionError}</div>
                )}
              </div>
            )}

            {/* Subject */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>Subject</span>
              <span style={{ color: 'var(--text-primary)', fontSize: 14 }}>{detail.ticket.subject}</span>
            </div>

            {/* Reduction summary (when flagged) */}
            {detail.reduction && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <span style={{ color: 'var(--text-primary)', fontSize: 14, fontWeight: 600 }}>
                  Reduction #{detail.reduction.id}
                </span>
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
                  <div style={{ display: 'flex', gap: 8 }}>
                    <Badge variant="subtle">{detail.reduction.kind}</Badge>
                    <Badge variant="subtle" tone="attention">
                      {detail.reduction.review_state}
                    </Badge>
                  </div>
                  <pre
                    style={{
                      margin: 0,
                      fontSize: 12,
                      fontFamily: 'var(--font-mono)',
                      color: 'var(--text-secondary)',
                      overflow: 'auto',
                      maxHeight: 160,
                    }}
                  >
                    {JSON.stringify(detail.reduction.json, null, 2)}
                  </pre>
                </div>
              </div>
            )}

            {/* Payload section */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <span style={{ color: 'var(--text-primary)', fontSize: 14, fontWeight: 600 }}>Payload</span>
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
              <span style={{ color: 'var(--text-primary)', fontSize: 14, fontWeight: 600 }}>Result</span>
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
                <div style={{ color: 'var(--text-muted)', fontSize: 13, fontStyle: 'italic', padding: 12 }}>
                  No result yet
                </div>
              )}
            </div>

            {/* Progress / state history */}
            {detail.history.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <span style={{ color: 'var(--text-primary)', fontSize: 14, fontWeight: 600 }}>History</span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {detail.history.map((ev) => (
                    <div
                      key={ev.id}
                      style={{
                        display: 'flex',
                        gap: 8,
                        alignItems: 'baseline',
                        fontSize: 12,
                        padding: '4px 0',
                        borderBottom: '1px solid var(--border-hairline)',
                      }}
                    >
                      <span
                        style={{
                          fontFamily: 'var(--font-mono)',
                          color: 'var(--status-live)',
                          minWidth: 140,
                        }}
                      >
                        {ev.kind}
                      </span>
                      <span style={{ color: 'var(--text-secondary)' }}>{ev.message || '—'}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

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
                        <Badge variant="subtle">#{att.attempt}</Badge>
                        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                          {att.host}
                        </span>
                        {att.outcome && (
                          <Badge variant="subtle" tone={att.outcome === 'ok' ? 'ok' : 'danger'}>
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
                <span style={{ color: 'var(--text-primary)', fontSize: 14, fontWeight: 600 }}>Evidence</span>
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
                      <Badge variant="subtle">#{ev.attempt}</Badge>
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
