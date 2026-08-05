/**
 * CrewDrawer - host detail drawer showing active leases.
 * Phase B4: read-only drawer showing host's active leases from GET /api/leases?host=<id>.
 * Phase D2b: crew control actions (drain/remove/re-probe).
 */

import { useState, useEffect } from 'react';
import { fetchLeases, reprobeCrew, drainCrew, removeCrew, AuthError } from '../api/client';
import type { CrewMember, Lease, HealthChecklist } from '../api/client';
import { Drawer, EmptyState, HealthBadge, Badge, Button } from '../ds';
import { TOPBAR_HEIGHT } from './TopBar';

type CrewDrawerProps = {
  isOpen: boolean;
  host: CrewMember | null;
  onClose: () => void;
  onRefresh?: () => void;
};

export default function CrewDrawer({ isOpen, host, onClose, onRefresh }: CrewDrawerProps) {
  const [leases, setLeases] = useState<Lease[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // D2b: crew control state
  const [checklist, setChecklist] = useState<HealthChecklist | null>(null);
  const [reprobing, setReprobing] = useState(false);
  const [draining, setDraining] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [showRemoveConfirm, setShowRemoveConfirm] = useState(false);
  const [controlError, setControlError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || !host) {
      setLeases([]);
      setError(null);
      setChecklist(null);
      setControlError(null);
      return;
    }

    const loadLeases = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await fetchLeases(host.id);
        setLeases(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load leases');
      } finally {
        setLoading(false);
      }
    };

    loadLeases();
  }, [isOpen, host]);

  const handleReprobe = async () => {
    if (!host) return;

    setReprobing(true);
    setControlError(null);

    try {
      const result = await reprobeCrew(host.id);
      setChecklist(result);
    } catch (err) {
      if (err instanceof AuthError) {
        setControlError('Authentication required. Please log in.');
      } else if (err instanceof Error) {
        setControlError(err.message);
      } else {
        setControlError('Failed to reprobe host');
      }
    } finally {
      setReprobing(false);
    }
  };

  const handleDrain = async () => {
    if (!host) return;

    setDraining(true);
    setControlError(null);

    try {
      await drainCrew(host.id);
      if (onRefresh) onRefresh();
    } catch (err) {
      if (err instanceof AuthError) {
        setControlError('Authentication required. Please log in.');
      } else if (err instanceof Error) {
        setControlError(err.message);
      } else {
        setControlError('Failed to drain host');
      }
    } finally {
      setDraining(false);
    }
  };

  const handleRemoveConfirm = async () => {
    if (!host) return;

    setRemoving(true);
    setControlError(null);

    try {
      await removeCrew(host.id);
      setShowRemoveConfirm(false);
      if (onRefresh) onRefresh();
      onClose();
    } catch (err) {
      if (err instanceof AuthError) {
        setControlError('Authentication required. Please log in.');
      } else if (err instanceof Error) {
        setControlError(err.message);
      } else {
        setControlError('Failed to remove host');
      }
      setShowRemoveConfirm(false);
    } finally {
      setRemoving(false);
    }
  };

  if (!host) {
    return null;
  }

  return (
    <Drawer open={isOpen} fixed onClose={onClose} title={`Host: ${host.id}`} width="500px" style={{ top: TOPBAR_HEIGHT }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
        {/* Host info */}
        <section>
          <h3 style={{ margin: '0 0 12px 0', fontSize: 13, fontWeight: 500, color: 'var(--text-muted)' }}>
            Details
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Site</span>
              <span style={{ fontSize: 13, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
                {host.site}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>State</span>
              <span style={{ fontSize: 13, color: 'var(--text-primary)' }}>
                {host.state}
              </span>
            </div>
            {host.current_ticket && (
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Current ticket</span>
                <span style={{ fontSize: 13, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
                  {host.current_ticket}
                </span>
              </div>
            )}
          </div>
        </section>

        {/* Health */}
        <section>
          <h3 style={{ margin: '0 0 12px 0', fontSize: 13, fontWeight: 500, color: 'var(--text-muted)' }}>
            Health
          </h3>
          {host.health ? (
            <HealthBadge health={host.health} size="md" />
          ) : (
            <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>No health data available</span>
          )}
        </section>

        {/* Resources */}
        <section>
          <h3 style={{ margin: '0 0 12px 0', fontSize: 13, fontWeight: 500, color: 'var(--text-muted)' }}>
            Resources
          </h3>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {Object.entries(host.resources).map(([key, value]) => (
              <span
                key={key}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '4px 12px',
                  background: 'var(--wash-subtle)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: 13,
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--text-secondary)',
                }}
              >
                <span>{key}</span>
                <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{value}</span>
              </span>
            ))}
          </div>
        </section>

        {/* Capabilities */}
        {host.capabilities.length > 0 && (
          <section>
            <h3 style={{ margin: '0 0 12px 0', fontSize: 13, fontWeight: 500, color: 'var(--text-muted)' }}>
              Capabilities
            </h3>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {host.capabilities.map((cap) => (
                <Badge key={cap} variant="outline" size="sm">
                  {cap}
                </Badge>
              ))}
            </div>
          </section>
        )}

        {/* D2b: Crew Control Actions */}
        <section>
          <h3 style={{ margin: '0 0 12px 0', fontSize: 13, fontWeight: 500, color: 'var(--text-muted)' }}>
            Actions
          </h3>

          {/* Control error */}
          {controlError && (
            <div
              style={{
                marginBottom: 12,
                padding: 12,
                background: 'var(--wash-danger)',
                border: '1px solid var(--border-danger)',
                borderRadius: 'var(--radius-md)',
                color: 'var(--status-danger)',
                fontSize: 13,
              }}
            >
              {controlError}
            </div>
          )}

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Button variant="secondary" size="sm" onClick={handleReprobe} disabled={reprobing}>
              {reprobing ? 'Re-probing...' : 'Re-probe'}
            </Button>
            <Button variant="secondary" size="sm" onClick={handleDrain} disabled={draining}>
              {draining ? 'Draining...' : 'Drain'}
            </Button>
            <Button variant="danger" size="sm" onClick={() => setShowRemoveConfirm(true)} disabled={removing}>
              Remove
            </Button>
          </div>

          {/* Remove confirmation */}
          {showRemoveConfirm && (
            <div
              style={{
                marginTop: 12,
                padding: 12,
                background: 'var(--wash-attention)',
                border: '1px solid var(--border-attention)',
                borderRadius: 'var(--radius-md)',
              }}
            >
              <p style={{ margin: '0 0 12px 0', fontSize: 13, color: 'var(--text-primary)' }}>
                Are you sure you want to remove <strong>{host.id}</strong>?
              </p>
              <div style={{ display: 'flex', gap: 8 }}>
                <Button variant="danger" size="sm" onClick={handleRemoveConfirm} disabled={removing}>
                  {removing ? 'Removing...' : 'Confirm Remove'}
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setShowRemoveConfirm(false)} disabled={removing}>
                  Cancel
                </Button>
              </div>
            </div>
          )}

          {/* Re-probe checklist */}
          {checklist && (
            <div
              style={{
                marginTop: 12,
                padding: 12,
                background: 'var(--wash-subtle)',
                border: '1px solid var(--border-hairline)',
                borderRadius: 'var(--radius-md)',
              }}
            >
              <h4 style={{ margin: '0 0 12px 0', fontSize: 12, fontWeight: 500, color: 'var(--text-muted)' }}>
                Latest Health Check
              </h4>

              {/* Overall status */}
              <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Overall:</span>
                <Badge variant="solid" tone={checklist.ok ? 'ok' : 'danger'} size="sm">
                  {checklist.ok ? 'Healthy' : 'Unhealthy'}
                </Badge>
                <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                  {checklist.latency_ms}ms
                </span>
              </div>

              {/* Checks */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {checklist.checks.map((check, idx) => (
                  <div
                    key={idx}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      padding: 6,
                      background: 'var(--surface-bg)',
                      borderRadius: 'var(--radius-sm)',
                    }}
                  >
                    <span
                      style={{
                        width: 6,
                        height: 6,
                        borderRadius: '50%',
                        background: check.ok ? 'var(--status-ok)' : 'var(--status-danger)',
                        flexShrink: 0,
                      }}
                    />
                    <span
                      style={{
                        fontSize: 11,
                        fontFamily: 'var(--font-mono)',
                        color: 'var(--text-secondary)',
                        minWidth: 100,
                      }}
                    >
                      {check.name}
                    </span>
                    <span style={{ fontSize: 11, color: 'var(--text-muted)', flex: 1 }}>
                      {check.detail}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>

        {/* Active leases */}
        <section>
          <h3 style={{ margin: '0 0 12px 0', fontSize: 13, fontWeight: 500, color: 'var(--text-muted)' }}>
            Active Leases
          </h3>

          {loading && (
            <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Loading leases...</span>
          )}

          {error && (
            <span style={{ fontSize: 13, color: 'var(--status-danger)' }}>Error: {error}</span>
          )}

          {!loading && !error && leases.length === 0 && (
            <EmptyState
              title="No active leases"
              description="This host currently holds no active resource leases"
              icon="file-minus"
            />
          )}

          {!loading && !error && leases.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {leases.map((lease) => (
                <div
                  key={lease.id}
                  style={{
                    padding: 12,
                    background: 'var(--wash-subtle)',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--border-hairline)',
                  }}
                >
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{
                        fontSize: 12,
                        fontFamily: 'var(--font-mono)',
                        color: 'var(--text-muted)'
                      }}>
                        {lease.resource_class}
                      </span>
                      <Badge variant="subtle" tone="live" size="sm">
                        active
                      </Badge>
                    </div>

                    {lease.ticket_id && (
                      <div>
                        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Ticket: </span>
                        <span style={{
                          fontSize: 12,
                          fontFamily: 'var(--font-mono)',
                          color: 'var(--text-primary)'
                        }}>
                          {lease.ticket_id}
                        </span>
                      </div>
                    )}

                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                        Remaining TTL
                      </span>
                      <span style={{
                        fontSize: 12,
                        fontFamily: 'var(--font-mono)',
                        color: 'var(--text-secondary)'
                      }}>
                        {formatDuration(lease.remaining_s)}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </Drawer>
  );
}

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);

  if (mins > 60) {
    const hours = Math.floor(mins / 60);
    const remainingMins = mins % 60;
    return `${hours}h ${remainingMins}m`;
  }

  if (mins > 0) {
    return `${mins}m ${secs}s`;
  }

  return `${secs}s`;
}
