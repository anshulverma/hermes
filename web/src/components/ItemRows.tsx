/**
 * ItemRows — a per-item payload as one row each, not one wall each.
 *
 * `syntheses` holds seventeen write-ups; `analyses` holds one per agent.
 * Rendered as prose they are seventeen documents stacked in a card, which is
 * more reading than the run was supposed to save. As rows they are a list you
 * can scan: which item, how much was written, and the write-up's own first
 * heading as its summary. Open the one you care about.
 */

import { useState } from 'react';
import ProseOutline from './ProseOutline';
import { firstLine } from '../util/prose';
import { verdictTone } from '../util/reduction';

export type Item = {
  id: string;
  label: string;
  text: string;
  verdict?: string | null;
  headline?: string | null;
};

const TONE_COLOR: Record<string, string> = {
  danger: 'var(--status-danger, #f85149)',
  attention: 'var(--status-attention, #e3b341)',
  ok: 'var(--status-ok, #7ee787)',
};

/**
 * The verdict the agent stated, or a plain note that it stated none.
 *
 * "unstated" is deliberately visible rather than blank or green: an item nobody
 * judged is a real outcome, and letting it read as clean is the failure this
 * whole contract exists to avoid.
 */
function Verdict({ verdict }: { verdict?: string | null }) {
  const tone = verdictTone(verdict);
  return (
    <span
      data-testid={`verdict-${verdict ?? 'unstated'}`}
      style={{
        flex: 'none',
        minWidth: 96,
        padding: '1px 6px',
        fontSize: 10,
        fontWeight: tone ? 600 : 400,
        textAlign: 'center',
        color: tone ? TONE_COLOR[tone] : 'var(--text-muted)',
        border: `1px solid ${tone ? TONE_COLOR[tone] : 'var(--border-hairline)'}`,
        borderRadius: 'var(--radius-lg)',
      }}
    >
      {verdict ?? 'unstated'}
    </span>
  );
}

export default function ItemRows({ items, testId }: { items: Item[]; testId?: string }) {
  const [open, setOpen] = useState<string | null>(null);

  return (
    <div data-testid={testId}>
      {items.map((item) => {
        const isOpen = open === item.id;
        return (
          <div
            key={item.id}
            style={{ borderTop: '1px solid var(--border-hairline)', padding: '6px 0' }}
          >
            <button
              type="button"
              data-testid={`item-row-${item.id}`}
              aria-expanded={isOpen}
              onClick={() => setOpen(isOpen ? null : item.id)}
              style={{
                display: 'flex',
                gap: 10,
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
                {isOpen ? '▾' : '▸'}
              </span>
              <Verdict verdict={item.verdict} />
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 12,
                  color: 'var(--text-secondary)',
                  flex: 'none',
                }}
              >
                {item.label}
              </span>
              <span
                style={{
                  fontSize: 12,
                  color: 'var(--text-muted)',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {/* The agent's own one-liner when it wrote one; otherwise the
                    write-up's first heading. */}
                {item.headline || firstLine(item.text)}
              </span>
              <span
                style={{
                  marginLeft: 'auto',
                  fontSize: 10,
                  color: 'var(--text-muted)',
                  flex: 'none',
                }}
              >
                {item.text.split('\n').length} lines
              </span>
            </button>
            {isOpen && (
              <div style={{ marginTop: 8, paddingLeft: 18 }}>
                <ProseOutline text={item.text} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
