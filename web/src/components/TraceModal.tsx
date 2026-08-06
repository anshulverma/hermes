/**
 * TraceModal — the worker's whole session, opened from its evidence ref.
 *
 * A ref like `claude:session:9b0e67d3-…` used to be a string you copied and
 * then went hunting for on some host. The engine now captures the transcript
 * behind it when the result is recorded, so it can simply be read here.
 *
 * A real trace is ~150 records of which only ~50 are the session: the rest are
 * hook attachments and bookkeeping. So the conversation is what you land on,
 * with the noise present but collapsed, and a raw toggle for the bytes exactly
 * as captured. Nothing is hidden — it is ordered by how likely you are to want
 * it.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Dialog, Button, Badge } from '../ds';
import {
  fetchAttemptTrace,
  fetchAttemptTraceRaw,
  AuthError,
  type AttemptTrace,
  type TraceRecord,
} from '../api/client';

type TraceModalProps = {
  attemptId: number | null;
  refLabel?: string | null;
  onClose: () => void;
};

/** Kinds that are the conversation, in the order a reader meets them. */
const CONVERSATION = new Set(['prompt', 'answer', 'thinking', 'tool_call', 'tool_result']);

/** Which kinds start collapsed: everything that is volume rather than signal. */
const COLLAPSED_BY_DEFAULT = new Set(['thinking', 'tool_call', 'tool_result', 'attachment', 'meta']);

const KIND_LABEL: Record<string, string> = {
  prompt: 'Prompt',
  answer: 'Answer',
  thinking: 'Thinking',
  tool_call: 'Tool',
  tool_result: 'Result',
  attachment: 'Attachment',
  meta: 'Meta',
  unparsed: 'Unreadable',
};

const KIND_TONE: Record<string, string> = {
  prompt: 'var(--status-info, #6ea8fe)',
  answer: 'var(--status-ok, #7ee787)',
  thinking: 'var(--text-muted)',
  tool_call: 'var(--status-attention, #e3b341)',
  tool_result: 'var(--text-secondary)',
  attachment: 'var(--text-muted)',
  meta: 'var(--text-muted)',
  unparsed: 'var(--status-error, #f85149)',
};

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function TraceRow({ record, defaultOpen }: { record: TraceRecord; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const label = KIND_LABEL[record.kind] ?? record.kind;
  const tone = KIND_TONE[record.kind] ?? 'var(--text-muted)';
  const lines = record.text ? record.text.split('\n').length : 0;
  const preview = (record.text || '').slice(0, 120).replace(/\s+/g, ' ').trim();

  return (
    <div
      data-testid={`trace-record-${record.line}-${record.kind}`}
      style={{
        borderTop: '1px solid var(--border-hairline)',
        padding: '8px 0',
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        style={{
          display: 'flex',
          gap: 8,
          alignItems: 'baseline',
          width: '100%',
          textAlign: 'left',
          background: 'none',
          border: 'none',
          padding: 0,
          cursor: 'pointer',
          color: 'var(--text-primary)',
          minWidth: 0,
        }}
      >
        <span aria-hidden style={{ color: 'var(--text-muted)', fontSize: 10, width: 10 }}>
          {open ? '▾' : '▸'}
        </span>
        <span style={{ color: tone, fontSize: 11, fontWeight: 600, flex: 'none' }}>{label}</span>
        {record.title && (
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              color: 'var(--text-secondary)',
              flex: 'none',
            }}
          >
            {record.title}
          </span>
        )}
        {!open && preview && (
          <span
            style={{
              fontSize: 11,
              color: 'var(--text-muted)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {preview}
          </span>
        )}
        <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-muted)', flex: 'none' }}>
          {lines > 1 ? `${lines} lines` : ''}
        </span>
      </button>
      {open && record.text && (
        <pre
          style={{
            margin: '6px 0 0 18px',
            padding: 8,
            background: 'var(--wash-subtle)',
            border: '1px solid var(--border-hairline)',
            borderRadius: 'var(--radius-sm)',
            fontSize: 11,
            fontFamily: 'var(--font-mono)',
            color: 'var(--text-secondary)',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            maxHeight: 360,
            overflow: 'auto',
          }}
        >
          {record.text}
        </pre>
      )}
    </div>
  );
}

export default function TraceModal({ attemptId, refLabel, onClose }: TraceModalProps) {
  const [trace, setTrace] = useState<AttemptTrace | null>(null);
  const [raw, setRaw] = useState<string | null>(null);
  const [showRaw, setShowRaw] = useState(false);
  const [showNoise, setShowNoise] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const open = attemptId !== null;

  useEffect(() => {
    if (attemptId === null) {
      setTrace(null);
      setRaw(null);
      setShowRaw(false);
      setShowNoise(false);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchAttemptTrace(attemptId)
      .then((t) => {
        if (!cancelled) setTrace(t);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof AuthError) setError('Authentication required. Please log in.');
        else setError(err instanceof Error ? err.message : 'Could not load the trace');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [attemptId]);

  const loadRaw = useCallback(async () => {
    if (attemptId === null || raw !== null) {
      setShowRaw((v) => !v);
      return;
    }
    setLoading(true);
    try {
      const r = await fetchAttemptTraceRaw(attemptId);
      setRaw(r.raw);
      setShowRaw(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load the raw trace');
    } finally {
      setLoading(false);
    }
  }, [attemptId, raw]);

  const { conversation, noise } = useMemo(() => {
    const records = trace?.records ?? [];
    return {
      conversation: records.filter((r) => CONVERSATION.has(r.kind)),
      noise: records.filter((r) => !CONVERSATION.has(r.kind)),
    };
  }, [trace]);

  const title = refLabel ? `Trace — ${refLabel}` : 'Trace';

  return (
    <Dialog open={open} fixed onClose={onClose} title={title} width="min(1100px, 92vw)">
      {loading && !trace && <div style={{ padding: 16, color: 'var(--text-muted)' }}>Loading trace…</div>}

      {error && (
        <div
          data-testid="trace-error"
          style={{ padding: 12, color: 'var(--status-attention, #e3b341)', fontSize: 13 }}
        >
          {error}
        </div>
      )}

      {trace && (
        <>
          <div
            style={{
              display: 'flex',
              gap: 8,
              alignItems: 'center',
              flexWrap: 'wrap',
              paddingBottom: 8,
            }}
          >
            <Badge>{`attempt ${trace.attempt}`}</Badge>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
              {trace.lines} records · {formatBytes(trace.bytes)}
            </span>
            {trace.unparsed > 0 && (
              <span style={{ fontSize: 11, color: 'var(--status-attention, #e3b341)' }}>
                {trace.unparsed} unreadable
              </span>
            )}
            <span style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
              {noise.length > 0 && (
                <Button onClick={() => setShowNoise((v) => !v)}>
                  {showNoise ? 'Hide' : 'Show'} {noise.length} non-conversation
                </Button>
              )}
              <Button onClick={loadRaw}>{showRaw ? 'Readable' : 'Raw'}</Button>
            </span>
          </div>

          {showRaw ? (
            <pre
              data-testid="trace-raw"
              style={{
                margin: 0,
                padding: 8,
                background: 'var(--wash-subtle)',
                border: '1px solid var(--border-hairline)',
                borderRadius: 'var(--radius-sm)',
                fontSize: 11,
                fontFamily: 'var(--font-mono)',
                color: 'var(--text-secondary)',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all',
                maxHeight: '65vh',
                overflow: 'auto',
              }}
            >
              {raw}
            </pre>
          ) : (
            <div data-testid="trace-records" style={{ maxHeight: '65vh', overflow: 'auto' }}>
              {conversation.length === 0 && (
                <div style={{ padding: 12, color: 'var(--text-muted)', fontSize: 13 }}>
                  This trace has no conversation records — only bookkeeping. Use Raw to read it
                  as captured.
                </div>
              )}
              {conversation.map((r, i) => (
                <TraceRow
                  key={`c-${r.line}-${i}`}
                  record={r}
                  defaultOpen={!COLLAPSED_BY_DEFAULT.has(r.kind)}
                />
              ))}
              {showNoise &&
                noise.map((r, i) => (
                  <TraceRow key={`n-${r.line}-${i}`} record={r} defaultOpen={false} />
                ))}
            </div>
          )}
        </>
      )}
    </Dialog>
  );
}
