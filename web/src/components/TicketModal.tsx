/**
 * TicketModal - full ticket detail: live context + operator actions.
 *
 * Shows why a ticket is in its current state (derived reason banner), what the
 * agent answered on success, its progress/state history, the flagging reduction
 * when present, and the full payload/result/attempt/evidence detail. Renders an
 * actions menu strictly from the server's available_actions so the UI and API
 * agree on legality: requeue / retry / abandon (confirm) / reprioritize /
 * accept-reject reduction.
 *
 * The header state comes from the freshly fetched detail (the board's prop is a
 * snapshot that goes stale the moment an action lands), and bulky JSON blobs are
 * serialised only while expanded so opening it stays cheap.
 *
 * A centred dialog rather than a side drawer: at 600px the drawer had to wrap
 * every payload, attempt row and trace ref in a column narrower than the content
 * it was showing, while two thirds of the screen sat behind a scrim.
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
import { Dialog, StatusPill, Badge } from '../ds';

import { LoadingOverlay, CARD_SCRIM } from './Spinner';
import { priorityColor } from './HermesTicketCard';
import { normalizeTicketState, normalizeTicketDetail } from '../api/normalize';
import TraceModal from './TraceModal';
import JsonView from './JsonView';
import Markdown from './Markdown';
import { fmtTime, fmtDuration } from '../util/time';

const preStyle: React.CSSProperties = {
  margin: 0,
  background: 'var(--surface-card)',
  border: '1px solid var(--border-hairline)',
  borderRadius: 'var(--radius-sm)',
  padding: 12,
  fontSize: 12,
  fontFamily: 'var(--font-mono)',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
  // No maxHeight/overflow on purpose: these sit inside the dialog's single
  // scroll surface, and a block that scrolls on its own captures the wheel
  // whenever the cursor is over it. Everything here is already behind a toggle.
  color: 'var(--text-secondary)',
};

const sectionTitleStyle: React.CSSProperties = {
  color: 'var(--text-primary)',
  fontSize: 14,
  fontWeight: 600,
};

const captionStyle: React.CSSProperties = {
  color: 'var(--text-muted)',
  fontSize: 12,
};

/** Bytes of captured trace, for the note next to an openable ref. */
function formatTraceBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * A host filesystem path (result_ref / evidence_ref) with no captured trace.
 *
 * These point at files on the worker host, which the browser cannot open. When
 * the engine managed to capture the trace behind a ref, the evidence list makes
 * it a button that opens TraceModal instead; this is the fallback for the rest —
 * older attempts, agents that cannot locate their own transcript, hosts that
 * were already gone. Copy remains the only honest affordance for those.
 */
function HostPathRef({ path }: { path: string }) {
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 1500);
    return () => window.clearTimeout(timer);
  }, [copied]);

  async function copy() {
    setCopyFailed(false);
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(path);
        setCopied(true);
        return;
      }
      throw new Error('clipboard unavailable');
    } catch {
      // Non-secure contexts have no async clipboard; fall back to the legacy
      // command, and if that is missing too, say so rather than lying.
      try {
        const area = document.createElement('textarea');
        area.value = path;
        document.body.appendChild(area);
        area.select();
        const ok = typeof document.execCommand === 'function' && document.execCommand('copy');
        document.body.removeChild(area);
        if (ok) {
          setCopied(true);
          return;
        }
      } catch {
        // fall through to the failure note
      }
      setCopyFailed(true);
    }
  }

  return (
    <span style={{ display: 'inline-flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', minWidth: 0 }}>
      <code
        style={{
          fontSize: 11,
          fontFamily: 'var(--font-mono)',
          color: 'var(--text-secondary)',
          background: 'var(--wash-subtle)',
          border: '1px solid var(--border-hairline)',
          borderRadius: 'var(--radius-sm)',
          padding: '2px 6px',
          wordBreak: 'break-all',
        }}
      >
        {path}
      </code>
      <button
        type="button"
        aria-label="Copy host path"
        title="Copy host path"
        onClick={copy}
        style={{
          padding: '2px 8px',
          fontSize: 11,
          color: 'var(--text-primary)',
          background: 'var(--wash-subtle)',
          border: '1px solid var(--border-hairline)',
          borderRadius: 'var(--radius-md)',
          cursor: 'pointer',
          flex: 'none',
        }}
      >
        {copied ? 'Copied' : 'Copy'}
      </button>
      {copyFailed && (
        <span style={{ color: 'var(--status-attention)', fontSize: 11 }}>
          Copy unavailable — select the path manually.
        </span>
      )}
    </span>
  );
}

/**
 * A JSON document behind a toggle.
 *
 * The tree mounts only while expanded, so a multi-kilobyte payload costs
 * nothing until an operator asks for it.
 */
function CollapsibleJson({
  id,
  label,
  caption,
  value,
  defaultOpen = false,
}: {
  id: string;
  label: string;
  caption?: string;
  value: unknown;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <button
        type="button"
        data-testid={`${id}-toggle`}
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
        style={{
          ...sectionTitleStyle,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          alignSelf: 'flex-start',
          padding: 0,
          background: 'none',
          border: 'none',
          cursor: 'pointer',
        }}
      >
        <span aria-hidden="true" style={{ color: 'var(--text-muted)', fontSize: 11 }}>
          {open ? '▾' : '▸'}
        </span>
        {label}
      </button>
      {caption && <span style={captionStyle}>{caption}</span>}
      {/* maxHeight null: the dialog owns the one scroll surface (see the render
          root), so a bounded box here would capture the wheel over it. */}
      {open && <JsonView data-testid={`${id}-json`} value={value} maxHeight={null} />}
    </div>
  );
}

type TicketModalProps = {
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

export default function TicketModal({ isOpen, ticket, onClose, onActionSuccess }: TicketModalProps) {
  const [detail, setDetail] = useState<TicketDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmAbandon, setConfirmAbandon] = useState(false);
  const [priorityInput, setPriorityInput] = useState('');
  // The attempt whose trace is open, or null. Attempt-scoped rather than
  // ticket-scoped: a retried ticket has one trace per try.
  const [traceAttemptId, setTraceAttemptId] = useState<number | null>(null);

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

  // The prop is the board's snapshot and goes stale the moment an action lands;
  // the refetched detail is authoritative once it arrives.
  const uiState = normalizeTicketState(detail?.ticket.state ?? ticket.state);

  const answer = detail?.answer ?? null;
  const finding = detail?.finding ?? null;

  const actions = detail?.available_actions ?? [];
  const reductionId = detail?.reduction?.id ?? detail?.ticket.reduction_id ?? null;

  return (
    <>
    <Dialog open={isOpen} fixed onClose={onClose} title={ticket.id} width="min(1000px, 94vw)">
      {/* The one scrolling surface: nested scroll regions capture the wheel
          wherever the cursor is, so getting down the page means bottoming out
          every box on the way past. */}
      <div
        data-testid="ticket-scroll"
        style={{ position: 'relative', display: 'flex', flexDirection: 'column', gap: 24, padding: '4px 2px', minHeight: 240, maxHeight: '72vh', overflowY: 'auto' }}
      >
        {loading && <LoadingOverlay label="Loading ticket…" scrim={CARD_SCRIM} blur={false} />}

        {/* Board-level header. Phase prefers the fetched detail: on a deep link
            the board's row may not exist yet, so the prop is a stub. */}
        <div style={{ display: 'flex', gap: 10 }}>
          <StatusPill state={uiState} size="md" data-testid="ticket-state-pill" />
          {(detail?.ticket.phase || ticket.phase) && (
            <Badge variant="outline" tone="ok">
              {detail?.ticket.phase || ticket.phase}
            </Badge>
          )}
        </div>

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

            {/* Goal */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>Goal</span>
              <span style={{ color: 'var(--text-primary)', fontSize: 14 }}>{detail.ticket.subject}</span>
            </div>

            {/* Created / updated timestamps */}
            <div style={{ display: 'flex', gap: 24, fontSize: 12 }}>
              <span style={{ color: 'var(--text-muted)' }}>
                Created <span style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>{fmtTime(detail.ticket.created_at)}</span>
              </span>
              <span style={{ color: 'var(--text-muted)' }}>
                Updated <span style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>{fmtTime(detail.ticket.updated_at)}</span>
              </span>
              <span style={{ color: 'var(--text-muted)' }}>
                Priority{' '}
                <span
                  title="p0 = highest priority"
                  style={{ color: priorityColor(detail.ticket.priority ?? 0), fontFamily: 'var(--font-mono)', fontWeight: 600 }}
                >
                  P{detail.ticket.priority}
                </span>
              </span>
            </div>

            {/* Agent answer — what a successful run actually returned. The
                prose form when the playbook produces one; the structured
                finding document otherwise. Both stay reachable either way. */}
            {answer && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <span style={sectionTitleStyle}>Answer</span>
                <span style={captionStyle}>What the agent returned for this ticket.</span>
                <div
                  style={{
                    background: 'var(--surface-card)',
                    border: '1px solid var(--border-hairline)',
                    borderRadius: 'var(--radius-sm)',
                    padding: 12,
                  }}
                >
                  {/* Agents write markdown; rendered flat it arrives as literal
                      `##` and `- ` noise. */}
                  <Markdown data-testid="ticket-answer" maxHeight={null}>
                    {answer}
                  </Markdown>
                </div>
              </div>
            )}

            {finding && (
              <CollapsibleJson
                id="finding"
                label="Finding document"
                caption={
                  answer
                    ? 'The full result document the agent banked, including the answer above.'
                    : 'The result document the agent banked for this ticket.'
                }
                value={finding.json}
                defaultOpen={!answer}
              />
            )}

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
                  {/* plain: this already sits inside a card, and a second
                      bordered box inside it reads as a nesting level. */}
                  <JsonView
                    data-testid="reduction-json"
                    value={detail.reduction.json}
                    maxHeight={null}
                    plain
                  />
                </div>
              </div>
            )}

            {/* Payload section — collapsed by default: it is multi-kilobyte
                prose and serialising it on open is the drawer's biggest cost. */}
            <CollapsibleJson
              id="payload"
              label="Payload"
              caption="The goal envelope this ticket was dispatched with."
              value={detail.payload}
            />

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
                  {detail.result.result_ref && (() => {
                    // The same ref shows here and under Evidence; it must behave
                    // the same in both places rather than being a link in one.
                    const traced = detail.evidence.find(
                      (ev) => ev.ref === detail.result!.result_ref && ev.trace_bytes && ev.attempt_id != null,
                    );
                    return (
                      <div style={{ display: 'grid', gridTemplateColumns: '100px 1fr', gap: 8 }}>
                        <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                          {traced ? 'Trace:' : 'Host path:'}
                        </span>
                        {traced ? (
                          <span>
                            <button
                              type="button"
                              data-testid={`open-trace-result-${traced.attempt_id}`}
                              onClick={() => setTraceAttemptId(traced.attempt_id!)}
                              title="Open the full trace"
                              style={{
                                fontSize: 11,
                                fontFamily: 'var(--font-mono)',
                                color: 'var(--text-link, #6ea8fe)',
                                background: 'var(--wash-subtle)',
                                border: '1px solid var(--border-hairline)',
                                borderRadius: 'var(--radius-sm)',
                                padding: '2px 6px',
                                cursor: 'pointer',
                                wordBreak: 'break-all',
                                textAlign: 'left',
                              }}
                            >
                              {detail.result.result_ref}
                            </button>
                          </span>
                        ) : (
                          <HostPathRef path={detail.result.result_ref} />
                        )}
                      </div>
                    );
                  })()}
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

            {/* Failure output — raw worker output / stderr / stack trace. Tied to
                the latest ATTEMPT result (which persists across a requeue/retry),
                so it shows whenever the last run failed — even if the ticket has
                since moved back to queued. An absent capture reads as a note. */}
            {detail.result && (detail.result.detail || detail.result.outcome !== 'ok') && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <span style={{ color: 'var(--text-primary)', fontSize: 14, fontWeight: 600 }}>Output</span>
                {detail.result?.detail ? (
                  <>
                    <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                      What the worker emitted before failing.
                    </span>
                    <pre style={preStyle}>{detail.result.detail}</pre>
                  </>
                ) : (
                  <span style={{ color: 'var(--text-muted)', fontSize: 12, fontStyle: 'italic' }}>
                    The worker produced no output on stdout or stderr for this attempt.
                  </span>
                )}
              </div>
            )}

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
                        gap: 10,
                        alignItems: 'baseline',
                        fontSize: 12,
                        padding: '4px 0',
                        borderBottom: '1px solid var(--border-hairline)',
                      }}
                    >
                      <span
                        style={{
                          fontFamily: 'var(--font-mono)',
                          color: 'var(--text-muted)',
                          minWidth: 140,
                          flex: 'none',
                        }}
                      >
                        {fmtTime(ev.ts)}
                      </span>
                      <span
                        style={{
                          fontFamily: 'var(--font-mono)',
                          color: 'var(--status-live)',
                          minWidth: 118,
                          flex: 'none',
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
                      <div style={{ display: 'flex', gap: 8, marginBottom: 6, alignItems: 'center' }}>
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
                      <div style={{ color: 'var(--text-muted)', fontSize: 11, fontFamily: 'var(--font-mono)', marginBottom: 4 }}>
                        {fmtTime(att.started_at)} → {fmtTime(att.ended_at)}
                        {fmtDuration(att.started_at, att.ended_at) && ` · ${fmtDuration(att.started_at, att.ended_at)}`}
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
                      {att.detail && (
                        <pre style={{ ...preStyle, marginTop: 6, maxHeight: 200, fontSize: 11 }}>{att.detail}</pre>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Evidence. A ref whose trace was captured opens here; one whose
                trace was not is still only a path on some host, so it stays
                copy-only rather than pretending to be a link. */}
            {detail.evidence.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <span style={sectionTitleStyle}>Evidence</span>
                <span style={captionStyle}>
                  {detail.evidence.some((ev) => ev.trace_bytes)
                    ? "Open a ref to read the worker's whole session. Refs without a captured trace are host paths, not browser URLs — copy those and open them there."
                    : "Each ref is a host path on the worker, not a browser URL — copy it and open it there. Traces are captured from now on; these attempts ran before that."}
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
                        flexWrap: 'wrap',
                      }}
                    >
                      <Badge variant="subtle">#{ev.attempt}</Badge>
                      {ev.trace_bytes && ev.attempt_id != null ? (
                        <button
                          type="button"
                          data-testid={`open-trace-${ev.attempt_id}`}
                          onClick={() => setTraceAttemptId(ev.attempt_id!)}
                          title="Open the full trace"
                          style={{
                            fontSize: 11,
                            fontFamily: 'var(--font-mono)',
                            color: 'var(--text-link, #6ea8fe)',
                            background: 'var(--wash-subtle)',
                            border: '1px solid var(--border-hairline)',
                            borderRadius: 'var(--radius-sm)',
                            padding: '2px 6px',
                            cursor: 'pointer',
                            wordBreak: 'break-all',
                            textAlign: 'left',
                          }}
                        >
                          {ev.ref}
                        </button>
                      ) : (
                        <HostPathRef path={ev.ref} />
                      )}
                      {ev.trace_bytes ? (
                        <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                          {formatTraceBytes(ev.trace_bytes)} trace
                        </span>
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </Dialog>
    {/* Outside the ticket dialog on purpose: nested inside it, the trace dialog inherits the
        drawer's 600px positioned box and opens as a cramped panel over it
        instead of as a full overlay. */}
    <TraceModal
      attemptId={traceAttemptId}
      refLabel={detail?.evidence.find((ev) => ev.attempt_id === traceAttemptId)?.ref ?? null}
      onClose={() => setTraceAttemptId(null)}
    />
    </>
  );
}
