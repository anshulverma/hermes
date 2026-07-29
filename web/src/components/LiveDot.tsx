/**
 * LiveDot - connection status indicator for WebSocket.
 * Shows live/green when connected, offline/red when not.
 */

type LiveDotProps = {
  connected: boolean;
};

export default function LiveDot({ connected }: LiveDotProps) {
  const label = connected ? 'live' : 'offline';

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
          background: connected ? 'var(--status-live)' : 'var(--status-danger)',
          animation: connected ? 'fm-pulse 1.6s ease-out infinite' : 'none',
        }}
      />
      {label}
    </span>
  );
}
