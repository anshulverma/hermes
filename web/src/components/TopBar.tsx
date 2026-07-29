/**
 * TopBar component - app header with live indicator.
 * Phase A1: minimal shell (no view nav tabs yet - those are added incrementally in Phase B).
 */

import type { HealthResponse, Run } from '../api/client';

type LiveDotProps = {
  health: HealthResponse | null;
};

function LiveDot({ health }: LiveDotProps) {
  const isLive = health?.status === 'ok';
  const label = isLive ? 'live' : 'offline';

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        color: 'var(--text-muted)',
        fontSize: 12,
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: 6,
          height: 6,
          borderRadius: 'var(--radius-full)',
          background: isLive ? 'var(--status-live)' : 'var(--status-danger)',
          animation: isLive ? 'fm-pulse 1.6s ease-out infinite' : 'none',
        }}
      />
      {label}
    </span>
  );
}

type View = 'overview' | 'metrics' | 'board' | 'crew' | 'findings' | 'activity';

type TopBarProps = {
  health: HealthResponse | null;
  runs: Run[];
  view?: View;
  onViewChange?: (view: View) => void;
};

export default function TopBar({ health, view = 'overview', onViewChange }: TopBarProps) {
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

      {/* View nav tabs - only show "Run" for now (Phase B1) */}
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
      </nav>

      <div style={{ flex: 1 }} />

      <LiveDot health={health} />
    </header>
  );
}
