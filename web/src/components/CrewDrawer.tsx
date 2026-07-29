/**
 * CrewDrawer - host detail drawer showing active leases.
 * Phase B4: read-only drawer showing host's active leases from GET /api/leases?host=<id>.
 */

import { useState, useEffect } from 'react';
import { fetchLeases } from '../api/client';
import type { CrewMember, Lease } from '../api/client';
import { Drawer, EmptyState, HealthBadge, Badge } from '../ds';

type CrewDrawerProps = {
  isOpen: boolean;
  host: CrewMember | null;
  onClose: () => void;
};

export default function CrewDrawer({ isOpen, host, onClose }: CrewDrawerProps) {
  const [leases, setLeases] = useState<Lease[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || !host) {
      setLeases([]);
      setError(null);
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

  if (!host) {
    return null;
  }

  return (
    <Drawer isOpen={isOpen} onClose={onClose} title={`Host: ${host.id}`} width="500px">
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
              message="This host currently holds no active resource leases"
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
