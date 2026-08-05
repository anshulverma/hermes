/**
 * TopBar component - app header with live indicator.
 * Phase A1: minimal shell (no view nav tabs yet - those are added incrementally in Phase B).
 * Phase C1: LiveDot now reflects WebSocket connection state.
 */

import LiveDot from './LiveDot';

import type { View } from '../hooks/useHashView';

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
 * costs no extra request. Kept visually identical to public/favicon.svg.
 */
function HermesMark() {
  return (
    <svg
      viewBox="0 0 32 32"
      width="18"
      height="18"
      aria-hidden="true"
      focusable="false"
      style={{ display: 'block', marginRight: 1 }}
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
};

export default function TopBar({ connected, view = 'overview', onViewChange }: TopBarProps) {
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
      <span
        aria-label="Hermes"
        style={{ display: 'inline-flex', alignItems: 'center', color: 'var(--text-primary)' }}
      >
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

      <LiveDot connected={connected} />
    </header>
  );
}
