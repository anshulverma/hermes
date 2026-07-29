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

type TopBarProps = {
  health: HealthResponse | null;
  runs: Run[];
};

export default function TopBar({ health }: TopBarProps) {
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

      {/* View nav tabs will be added incrementally in Phase B as each view lands */}

      <div style={{ flex: 1 }} />

      <LiveDot health={health} />
    </header>
  );
}
