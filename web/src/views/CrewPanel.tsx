/**
 * CrewPanel - crew member list with health badges and host drawer.
 * Phase B4: real crew from GET /api/crew + host drawer with leases.
 */

import { useState, useEffect } from 'react';
import { fetchCrew } from '../api/client';
import type { CrewMember } from '../api/client';
import { HealthBadge, EmptyState } from '../ds';
import CrewDrawer from '../components/CrewDrawer';

export default function CrewPanel() {
  const [crew, setCrew] = useState<CrewMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedHost, setSelectedHost] = useState<CrewMember | null>(null);

  useEffect(() => {
    const loadCrew = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await fetchCrew();
        setCrew(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load crew');
      } finally {
        setLoading(false);
      }
    };

    loadCrew();
  }, []);

  if (loading) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ color: 'var(--text-muted)' }}>Loading crew...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <EmptyState
          title="Error loading crew"
          message={error}
          icon="alert-circle"
        />
      </div>
    );
  }

  if (crew.length === 0) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <EmptyState
          title="No crew members"
          message="No hosts have been registered yet"
          icon="users"
        />
      </div>
    );
  }

  return (
    <>
      <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'auto' }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '20px 20px 12px',
          borderBottom: '1px solid var(--border-hairline)'
        }}>
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 500, color: 'var(--text-primary)' }}>
            Crew
          </h2>
          <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>
            {crew.length} {crew.length === 1 ? 'host' : 'hosts'}
          </span>
        </div>

        <div style={{ borderTop: '1px solid var(--border-hairline)' }}>
          {/* Header row */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: '150px 100px 250px 200px 1fr',
            gap: 'var(--space-4)',
            padding: '10px var(--space-4)',
            borderBottom: '1px solid var(--border-hairline)',
            color: 'var(--text-muted)',
            fontSize: 12,
          }}>
            <span>host</span>
            <span>state</span>
            <span>health</span>
            <span>resources</span>
            <span>current ticket</span>
          </div>

          {/* Crew rows */}
          {crew.map((member) => (
            <div
              key={member.id}
              role="button"
              onClick={() => setSelectedHost(member)}
              style={{
                display: 'grid',
                gridTemplateColumns: '150px 100px 250px 200px 1fr',
                gap: 'var(--space-4)',
                padding: 'var(--space-3) var(--space-4)',
                borderBottom: '1px solid var(--border-hairline)',
                cursor: 'pointer',
                transition: 'background 120ms ease-out',
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLElement).style.background = 'var(--wash-subtle)';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLElement).style.background = 'transparent';
              }}
            >
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-primary)' }}>
                {member.id}
              </span>

              <span style={{ fontSize: 13 }}>
                <StateChip state={member.state} />
              </span>

              <div>
                {member.health ? (
                  <HealthBadge health={member.health} size="sm" />
                ) : (
                  <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>unknown</span>
                )}
              </div>

              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {Object.entries(member.resources).map(([key, value]) => (
                  <span
                    key={key}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 4,
                      padding: '2px 8px',
                      background: 'var(--wash-subtle)',
                      borderRadius: 'var(--radius-md)',
                      fontSize: 12,
                      fontFamily: 'var(--font-mono)',
                      color: 'var(--text-secondary)',
                    }}
                  >
                    <span>{key}</span>
                    <span style={{ color: 'var(--text-primary)' }}>{value}</span>
                  </span>
                ))}
              </div>

              <span style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 12,
                color: member.current_ticket ? 'var(--text-secondary)' : 'var(--text-muted)'
              }}>
                {member.current_ticket || '—'}
              </span>
            </div>
          ))}
        </div>
      </div>

      <CrewDrawer
        isOpen={selectedHost !== null}
        host={selectedHost}
        onClose={() => setSelectedHost(null)}
      />
    </>
  );
}

function StateChip({ state }: { state: string }) {
  const tones: Record<string, string> = {
    idle: 'var(--status-ok)',
    busy: 'var(--status-live)',
    down: 'var(--status-danger)',
    draining: 'var(--status-attention)',
  };

  const tone = tones[state] || 'var(--text-muted)';

  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      padding: '2px 8px',
      background: 'var(--wash-subtle)',
      borderRadius: 'var(--radius-md)',
      fontSize: 12,
      color: tone,
    }}>
      <span style={{
        width: 6,
        height: 6,
        borderRadius: '50%',
        background: tone,
      }} />
      {state}
    </span>
  );
}
