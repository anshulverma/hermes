/**
 * ProseOutline — a long agent write-up as its own table of contents.
 *
 * The alternative is what this replaces: a hundred lines of markdown dumped
 * into a card, which is text you scroll past rather than read. The agent
 * already wrote the structure as headings; this shows the outline and lets a
 * reader open the one section they came for.
 *
 * The opening paragraph stays visible, because it is usually the summary.
 */

import { useState } from 'react';
import Markdown from './Markdown';
import Clamp from './Clamp';
import { markdownSections } from '../util/prose';

export default function ProseOutline({ text, testId }: { text: string; testId?: string }) {
  const { intro, sections } = markdownSections(text);
  const [open, setOpen] = useState<Set<number>>(new Set());

  const toggle = (i: number) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });

  return (
    <div data-testid={testId}>
      {intro && (
        <Clamp text={intro} lines={8} height={160}>
          <Markdown maxHeight={null} fontSize={12}>
            {intro}
          </Markdown>
        </Clamp>
      )}

      {sections.map((s, i) => (
        <div
          key={`${s.title}-${i}`}
          style={{ borderTop: '1px solid var(--border-hairline)', padding: '6px 0' }}
        >
          <button
            type="button"
            data-testid={`section-${i}`}
            aria-expanded={open.has(i)}
            onClick={() => toggle(i)}
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
              fontSize: 13,
            }}
          >
            <span aria-hidden style={{ color: 'var(--text-muted)', fontSize: 10, width: 10 }}>
              {open.has(i) ? '▾' : '▸'}
            </span>
            <span style={{ paddingLeft: (s.level - 1) * 10 }}>{s.title}</span>
            <span
              style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-muted)', flex: 'none' }}
            >
              {s.body ? `${s.body.split('\n').length} lines` : ''}
            </span>
          </button>
          {open.has(i) && s.body && (
            <div style={{ marginTop: 6, paddingLeft: 18 }}>
              <Markdown maxHeight={null} fontSize={12}>
                {s.body}
              </Markdown>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
