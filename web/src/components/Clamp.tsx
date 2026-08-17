/**
 * Clamp — a long block cut to a readable height, with a way to see the rest.
 *
 * Not a scroll box. A block that scrolls on its own captures the wheel whenever
 * the cursor is over it, so getting down a page means bottoming out every block
 * on the way past; the page should own the one scrolling surface. Clamping
 * keeps a long block from burying what follows it without taking the wheel.
 *
 * The estimate is by line count rather than measured height, so it is decided
 * before layout and does not need a ref or a resize observer. It only has to be
 * roughly right: the consequence of being wrong is a block clamped slightly too
 * early or too late, and the control says how much is hidden either way.
 */

import { useState, type ReactNode } from 'react';

type ClampProps = {
  /** Source text, used only to decide whether clamping is warranted. */
  text: string;
  children: ReactNode;
  /** Clamp beyond this many lines. */
  lines?: number;
  /** Height to clamp to, in px. */
  height?: number;
  'data-testid'?: string;
};

export default function Clamp({
  text,
  children,
  lines = 24,
  height = 360,
  'data-testid': testId,
}: ClampProps) {
  const [showAll, setShowAll] = useState(false);
  const lineCount = text ? text.split('\n').length : 0;
  const clamped = lineCount > lines && !showAll;

  return (
    <div style={{ position: 'relative' }}>
      <div
        data-testid={testId}
        style={clamped ? { maxHeight: height, overflow: 'hidden' } : undefined}
      >
        {children}
      </div>
      {clamped && (
        <div
          aria-hidden
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            bottom: 0,
            height: 48,
            background: 'linear-gradient(to bottom, transparent, var(--surface-card))',
            pointerEvents: 'none',
          }}
        />
      )}
      {lineCount > lines && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          style={{
            marginTop: 4,
            padding: '2px 8px',
            fontSize: 11,
            color: 'var(--text-primary)',
            background: 'var(--wash-subtle)',
            border: '1px solid var(--border-hairline)',
            borderRadius: 'var(--radius-md)',
            cursor: 'pointer',
          }}
        >
          {showAll ? 'Show less' : `Show all ${lineCount} lines`}
        </button>
      )}
    </div>
  );
}
