/**
 * JsonView - a collapsible tree for JSON documents.
 *
 * Replaces `JSON.stringify(value, null, 2)` in a <pre>: an operator scanning a
 * payload for one field had to read the whole blob, and a multi-kilobyte answer
 * nested three levels down pushed everything else off screen. Here containers
 * fold, so the shape is readable first and the contents on demand.
 *
 * Depth is the only thing that auto-collapses: the top two levels open so the
 * document's shape is visible immediately, and anything deeper starts folded.
 * Long strings clamp to a few lines with an inline expander rather than being
 * truncated, because a truncated stack trace is worse than a folded one.
 *
 * Hand-rolled rather than pulled from a library so it themes off the same CSS
 * variables as the rest of the dashboard and inherits its density.
 */

import { useState } from 'react';

/** Levels open on first render; deeper containers start folded. */
const AUTO_OPEN_DEPTH = 2;
/** A string longer than this gets an expander instead of filling the panel. */
const LONG_STRING_CHARS = 220;

const MONO: React.CSSProperties = {
  fontFamily: 'var(--font-mono)',
  fontSize: 12,
  lineHeight: 1.6,
};

const COLORS = {
  key: 'var(--text-primary)',
  string: 'var(--status-ok)',
  number: 'var(--status-info, #6ea8fe)',
  boolean: 'var(--status-attention)',
  null: 'var(--text-muted)',
  punctuation: 'var(--text-muted)',
} as const;

type Json = unknown;

function isContainer(v: Json): v is Record<string, Json> | Json[] {
  return v !== null && typeof v === 'object';
}

/** "3 keys" / "12 items" — shown on a folded container so it stays scannable. */
function summarize(v: Record<string, Json> | Json[]): string {
  if (Array.isArray(v)) {
    return v.length === 1 ? '1 item' : `${v.length} items`;
  }
  const n = Object.keys(v).length;
  return n === 1 ? '1 key' : `${n} keys`;
}

/**
 * A string leaf. Multi-line and very long values are the common case here
 * (prompts, diffs, stack traces), so they clamp rather than flood the panel.
 */
function StringValue({ value }: { value: string }) {
  const [expanded, setExpanded] = useState(false);
  const isLong = value.length > LONG_STRING_CHARS || value.includes('\n');

  if (!isLong) {
    return <span style={{ color: COLORS.string, wordBreak: 'break-word' }}>"{value}"</span>;
  }

  return (
    <span style={{ display: 'inline-flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
      <span
        style={{
          color: COLORS.string,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          ...(expanded ? {} : { maxHeight: 60, overflow: 'hidden' }),
        }}
      >
        "{value}"
      </span>
      <button
        type="button"
        onClick={() => setExpanded((p) => !p)}
        style={{
          alignSelf: 'flex-start',
          padding: 0,
          border: 'none',
          background: 'none',
          color: 'var(--text-link, #6ea8fe)',
          fontSize: 11,
          fontFamily: 'var(--font-mono)',
          cursor: 'pointer',
        }}
      >
        {expanded ? 'show less' : `show all ${value.length} chars`}
      </button>
    </span>
  );
}

function Leaf({ value }: { value: Json }) {
  if (value === null) return <span style={{ color: COLORS.null }}>null</span>;
  if (value === undefined) return <span style={{ color: COLORS.null }}>undefined</span>;
  if (typeof value === 'string') return <StringValue value={value} />;
  if (typeof value === 'number') return <span style={{ color: COLORS.number }}>{String(value)}</span>;
  if (typeof value === 'boolean') return <span style={{ color: COLORS.boolean }}>{String(value)}</span>;
  return <span style={{ color: COLORS.null }}>{String(value)}</span>;
}

function Node({
  name,
  value,
  depth,
  isLast,
}: {
  name?: string;
  value: Json;
  depth: number;
  isLast: boolean;
}) {
  const [open, setOpen] = useState(depth < AUTO_OPEN_DEPTH);

  const label = name !== undefined && (
    <>
      <span style={{ color: COLORS.key }}>"{name}"</span>
      <span style={{ color: COLORS.punctuation }}>: </span>
    </>
  );

  if (!isContainer(value)) {
    return (
      <div style={{ ...MONO, paddingLeft: depth === 0 ? 0 : 14, display: 'flex', minWidth: 0 }}>
        <span style={{ minWidth: 0 }}>
          {label}
          <Leaf value={value} />
          {!isLast && <span style={{ color: COLORS.punctuation }}>,</span>}
        </span>
      </div>
    );
  }

  const arr = Array.isArray(value);
  const openBrace = arr ? '[' : '{';
  const closeBrace = arr ? ']' : '}';
  const entries: [string | undefined, Json][] = arr
    ? (value as Json[]).map((v) => [undefined, v])
    : Object.entries(value as Record<string, Json>);

  if (entries.length === 0) {
    return (
      <div style={{ ...MONO, paddingLeft: depth === 0 ? 0 : 14 }}>
        {label}
        <span style={{ color: COLORS.punctuation }}>
          {openBrace}
          {closeBrace}
          {!isLast && ','}
        </span>
      </div>
    );
  }

  return (
    <div style={{ ...MONO, paddingLeft: depth === 0 ? 0 : 14 }}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((p) => !p)}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 4,
          padding: 0,
          border: 'none',
          background: 'none',
          cursor: 'pointer',
          font: 'inherit',
          textAlign: 'left',
        }}
      >
        <span aria-hidden="true" style={{ color: 'var(--text-muted)', fontSize: 10, width: 8 }}>
          {open ? '▾' : '▸'}
        </span>
        {label}
        <span style={{ color: COLORS.punctuation }}>{openBrace}</span>
        {!open && (
          <>
            <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>{summarize(value)}</span>
            <span style={{ color: COLORS.punctuation }}>
              {closeBrace}
              {!isLast && ','}
            </span>
          </>
        )}
      </button>
      {open && (
        <>
          <div
            style={{
              marginLeft: 4,
              paddingLeft: 8,
              borderLeft: '1px solid var(--border-hairline)',
            }}
          >
            {entries.map(([k, v], i) => (
              <Node
                key={k ?? i}
                name={k}
                value={v}
                depth={depth + 1}
                isLast={i === entries.length - 1}
              />
            ))}
          </div>
          <div style={{ color: COLORS.punctuation, paddingLeft: depth === 0 ? 0 : 0 }}>
            {closeBrace}
            {!isLast && ','}
          </div>
        </>
      )}
    </div>
  );
}

/**
 * Renders any JSON-serialisable value as a foldable tree.
 *
 * `maxHeight` bounds the scroll area; pass null for callers that own their own
 * scrolling (the trace modal scrolls one surface for the whole conversation, so
 * a nested scroller there would trap the wheel). `plain` drops the card chrome
 * for callers that already draw a box around the body.
 */
export default function JsonView({
  value,
  maxHeight = 280,
  plain = false,
  'data-testid': testId,
}: {
  value: Json;
  maxHeight?: number | null;
  plain?: boolean;
  'data-testid'?: string;
}) {
  return (
    <div
      data-testid={testId}
      style={{
        ...(plain
          ? {}
          : {
              background: 'var(--surface-card)',
              border: '1px solid var(--border-hairline)',
              borderRadius: 'var(--radius-sm)',
              padding: 12,
            }),
        ...(maxHeight == null ? {} : { maxHeight, overflow: 'auto' }),
      }}
    >
      <Node value={value} depth={0} isLast />
    </div>
  );
}
