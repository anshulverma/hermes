/**
 * TopBar component - app header with live indicator.
 * Phase A1: minimal shell (no view nav tabs yet - those are added incrementally in Phase B).
 * Phase C1: LiveDot now reflects WebSocket connection state.
 */

import LiveDot from './LiveDot';

type View = 'overview' | 'metrics' | 'board' | 'crew' | 'findings' | 'activity';

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
        position: 'sticky',
        top: 0,
        zIndex: 40,
        flex: 'none',
        height: 56,
        display: 'flex',
        alignItems: 'center',
        gap: 24,
        padding: '0 20px',
        background: 'oklab(0 0 0 / 0.85)',
        backdropFilter: 'blur(12px)',
        borderBottom: '1px solid var(--border-hairline)',
      }}
    >
      <span style={{ color: 'var(--text-primary)' }}>Hermes</span>

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
