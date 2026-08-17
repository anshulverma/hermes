/**
 * TopBar component - app header with live indicator.
 * Phase A1: minimal shell (no view nav tabs yet - those are added incrementally in Phase B).
 * Phase C1: LiveDot now reflects WebSocket connection state.
 */

import LiveDot from './LiveDot';

import type { View } from '../hooks/useHashView';
import type { Run } from '../api/client';

/**
 * Height of the app chrome, in px.
 *
 * Overlays anchor below this. The content wrapper sets a z-index, which creates
 * a stacking context the drawer's own z-index cannot escape, so a drawer pinned
 * to top:0 renders UNDER this bar however high its z-index is. Offsetting by the
 * bar's height avoids the overlap entirely (and keeps the nav usable).
 */
export const TOPBAR_HEIGHT = 56;

/**
 * The Hermes mark: the favicon artwork, standing in for the leading "H".
 *
 * Inlined rather than an <img src="/favicon.svg"> so it scales with the text and
 * costs no extra request.
 *
 * The paths are the favicon's, but NOT its viewBox. The favicon is a rounded
 * tile, so its 0 0 32 32 box insets the artwork by ~8.5 units a side to leave
 * room for the background — padding that, in a wordmark, renders as a visible
 * gap between the "H" and the "e". This box is cropped to the artwork's real
 * bounds: the H stems span x 8.5-23.5 (3-wide strokes, round caps) and y 7-25,
 * and the wing ticks reach x 5.6 and 26.4, y 6.9. What is left either side of
 * the stems is the wings' own 2.9 units, which reads as a normal letter gap.
 *
 * Sized in em off the cap height (Inter's is 0.727em) so the mark tracks the
 * font rather than a hardcoded pixel size, and baseline-aligned rather than
 * centred: the H's feet are flush with the bottom of the cropped box, so they
 * land on the text baseline the way a real glyph would.
 */
const CAP_EM = 0.727; // Inter cap height, in em
const MARK_UNITS_W = 20.8;
const MARK_UNITS_H = 18.1;
const MARK_CAP_UNITS = 18; // the H stems, y 7 -> 25

function HermesMark() {
  return (
    <svg
      viewBox="5.6 6.9 20.8 18.1"
      width={`${((MARK_UNITS_W / MARK_CAP_UNITS) * CAP_EM).toFixed(3)}em`}
      height={`${((MARK_UNITS_H / MARK_CAP_UNITS) * CAP_EM).toFixed(3)}em`}
      aria-hidden="true"
      focusable="false"
      style={{ verticalAlign: 'baseline' }}
    >
      <path
        d="M6.5 10 l3.2 -2.2 M25.5 10 l-3.2 -2.2"
        stroke="#863bff"
        strokeWidth="1.8"
        strokeLinecap="round"
        fill="none"
      />
      <path
        d="M10 8.5 V23.5 M22 8.5 V23.5"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        fill="none"
      />
      <path d="M10 16 H22" stroke="#863bff" strokeWidth="3" strokeLinecap="round" fill="none" />
    </svg>
  );
}

type TopBarProps = {
  connected: boolean;
  view?: View;
  onViewChange?: (view: View) => void;
  // Every run, newest first, and which one the console is showing. Optional so
  // the bar still renders before the run list has loaded.
  runs?: Run[];
  selectedRunId?: string | null;
  onRunChange?: (runId: string) => void;
};

export default function TopBar({
  connected,
  view = 'overview',
  onViewChange,
  runs,
  selectedRunId,
  onRunChange,
}: TopBarProps) {
  const handleTabClick = (newView: View) => {
    if (onViewChange) {
      onViewChange(newView);
    }
  };

  return (
    <header
      style={{
        // Deliberately NOT sticky: the shell is a fixed-height flex column whose
        // content pane does the scrolling, so this bar is already pinned. Sticky
        // only let it drift when the page was overscrolled past its end.
        position: 'relative',
        zIndex: 40,
        flex: 'none',
        height: TOPBAR_HEIGHT,
        display: 'flex',
        alignItems: 'center',
        gap: 24,
        padding: '0 20px',
        background: 'oklab(0 0 0 / 0.85)',
        backdropFilter: 'blur(12px)',
        borderBottom: '1px solid var(--border-hairline)',
      }}
    >
      {/* Plain inline layout, not flex: the mark is a stand-in glyph, so it has to
          sit on the text baseline, and a flex container would strip that away. */}
      <span aria-label="Hermes" style={{ color: 'var(--text-primary)', whiteSpace: 'nowrap' }}>
        <HermesMark />
        <span aria-hidden="true">ermes</span>
      </span>

      {/* View nav tabs - Phase E1 adds "Metrics" */}
      <nav style={{ display: 'flex', gap: 4 }}>
        <button
          onClick={() => handleTabClick('overview')}
          style={{
            padding: '6px 12px',
            fontSize: 13,
            color: view === 'overview' ? 'var(--text-primary)' : 'var(--text-muted)',
            background: view === 'overview' ? 'var(--wash-subtle)' : 'transparent',
            border: 'none',
            borderRadius: 'var(--radius-md)',
            cursor: 'pointer',
            transition: 'all 120ms ease-out',
          }}
        >
          Run
        </button>
        <button
          onClick={() => handleTabClick('metrics')}
          style={{
            padding: '6px 12px',
            fontSize: 13,
            color: view === 'metrics' ? 'var(--text-primary)' : 'var(--text-muted)',
            background: view === 'metrics' ? 'var(--wash-subtle)' : 'transparent',
            border: 'none',
            borderRadius: 'var(--radius-md)',
            cursor: 'pointer',
            transition: 'all 120ms ease-out',
          }}
        >
          Metrics
        </button>
        <button
          onClick={() => handleTabClick('board')}
          style={{
            padding: '6px 12px',
            fontSize: 13,
            color: view === 'board' ? 'var(--text-primary)' : 'var(--text-muted)',
            background: view === 'board' ? 'var(--wash-subtle)' : 'transparent',
            border: 'none',
            borderRadius: 'var(--radius-md)',
            cursor: 'pointer',
            transition: 'all 120ms ease-out',
          }}
        >
          Tickets
        </button>
        <button
          onClick={() => handleTabClick('crew')}
          style={{
            padding: '6px 12px',
            fontSize: 13,
            color: view === 'crew' ? 'var(--text-primary)' : 'var(--text-muted)',
            background: view === 'crew' ? 'var(--wash-subtle)' : 'transparent',
            border: 'none',
            borderRadius: 'var(--radius-md)',
            cursor: 'pointer',
            transition: 'all 120ms ease-out',
          }}
        >
          Crew
        </button>
        <button
          onClick={() => handleTabClick('findings')}
          style={{
            padding: '6px 12px',
            fontSize: 13,
            color: view === 'findings' ? 'var(--text-primary)' : 'var(--text-muted)',
            background: view === 'findings' ? 'var(--wash-subtle)' : 'transparent',
            border: 'none',
            borderRadius: 'var(--radius-md)',
            cursor: 'pointer',
            transition: 'all 120ms ease-out',
          }}
        >
          Findings
        </button>
        <button
          onClick={() => handleTabClick('activity')}
          style={{
            padding: '6px 12px',
            fontSize: 13,
            color: view === 'activity' ? 'var(--text-primary)' : 'var(--text-muted)',
            background: view === 'activity' ? 'var(--wash-subtle)' : 'transparent',
            border: 'none',
            borderRadius: 'var(--radius-md)',
            cursor: 'pointer',
            transition: 'all 120ms ease-out',
          }}
        >
          Activity
        </button>
      </nav>

      <div style={{ flex: 1 }} />

      {/* Which run every view below is about. Hidden when there is only one:
          a picker with a single option is furniture, not a control. */}
      {runs && runs.length > 1 && (
        <select
          data-testid="run-picker"
          aria-label="Run"
          value={selectedRunId ?? runs[0].id}
          onChange={(e) => onRunChange?.(e.target.value)}
          style={{
            padding: '4px 8px',
            fontSize: 12,
            fontFamily: 'var(--font-mono)',
            color: 'var(--text-secondary)',
            background: 'var(--wash-subtle)',
            border: '1px solid var(--border-hairline)',
            borderRadius: 'var(--radius-md)',
            maxWidth: 260,
          }}
        >
          {runs.map((r) => (
            <option key={r.id} value={r.id}>
              {r.id} · {r.state}
            </option>
          ))}
        </select>
      )}

      <LiveDot connected={connected} />
    </header>
  );
}
