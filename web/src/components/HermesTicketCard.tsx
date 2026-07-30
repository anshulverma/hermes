/**
 * HermesTicketCard — the kanban ticket card.
 *
 * Mirrors the DS TicketCard's look but adds what the bundled card can't: a
 * color-coded priority pill (p0 = highest → most urgent) and clearly labelled
 * attempt/elapsed metrics (instead of the cryptic "try 0 0s"). Clicking opens
 * the ticket drawer.
 */

import { useState } from 'react';
import { StatusPill } from '../ds';
import { normalizeTicketState } from '../api/normalize';

export type CardTicket = {
  id: string;
  subject: string;
  state: string;
  phase?: string;
  attempts?: number;
  elapsed_s?: number;
  resource_req?: string;
  host?: string;
  priority?: number;
};

/** p0 is highest priority → most urgent color; larger numbers cool to muted. */
export function priorityColor(p: number): string {
  if (p <= 0) return 'var(--status-danger)';
  if (p <= 1) return 'var(--status-attention)';
  if (p <= 2) return 'var(--status-live)';
  return 'var(--text-muted)';
}

function fmtElapsed(s: number | undefined): string {
  const v = s ?? 0;
  if (v <= 0) return '0s';
  if (v < 60) return `${v}s`;
  const m = Math.floor(v / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

type Props = {
  ticket: CardTicket;
  onClick?: () => void;
  style?: React.CSSProperties;
};

export default function HermesTicketCard({ ticket: t, onClick, style }: Props) {
  const [hover, setHover] = useState(false);
  const p = t.priority ?? 0;
  const attempts = t.attempts ?? 0;

  return (
    <article
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      tabIndex={0}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        padding: 'var(--space-3)',
        borderRadius: 'var(--radius-lg)',
        background: hover ? 'var(--wash-hover)' : 'var(--surface-card)',
        border: '1px solid var(--border-hairline)',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'background var(--motion-fast) var(--ease-default)',
        ...style,
      }}
    >
      {/* id + status */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-small-size)', color: 'var(--text-muted)' }}>
          {t.id}
        </span>
        <StatusPill state={normalizeTicketState(t.state)} size="sm" />
      </div>

      {/* goal */}
      <span style={{ color: 'var(--text-primary)', fontSize: 13, lineHeight: '18px', wordBreak: 'break-word' }}>
        {t.subject}
      </span>

      {/* resource / phase / host */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          flexWrap: 'wrap',
          color: 'var(--text-muted)',
          fontSize: 'var(--text-small-size)',
        }}
      >
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 4,
            padding: '0 6px',
            height: 18,
            border: '1px solid var(--border-hairline)',
            borderRadius: 'var(--radius-lg)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          {t.resource_req}
        </span>
        {t.phase && <span>{t.phase}</span>}
        {t.host && <span style={{ fontFamily: 'var(--font-mono)' }}>{t.host}</span>}
      </div>

      {/* footer: colored priority + clearly-labelled metrics */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          color: 'var(--text-muted)',
          fontSize: 'var(--text-small-size)',
          fontFamily: 'var(--font-mono)',
        }}
      >
        <span
          title={`priority ${p} (p0 = highest)`}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            padding: '0 6px',
            height: 18,
            borderRadius: 'var(--radius-lg)',
            color: priorityColor(p),
            border: `1px solid ${priorityColor(p)}`,
            fontWeight: 600,
          }}
        >
          P{p}
        </span>
        <span>{attempts} {attempts === 1 ? 'attempt' : 'attempts'}</span>
        <span>{fmtElapsed(t.elapsed_s)} elapsed</span>
      </div>
    </article>
  );
}
