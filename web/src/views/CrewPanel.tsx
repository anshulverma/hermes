/**
 * CrewPanel - crew member list with health badges and host drawer.
 * Phase B4: real crew from GET /api/crew + host drawer with leases.
 * Phase D2b: add-host button + modal.
 */

import { useState, useEffect } from 'react';
import { fetchCrew } from '../api/client';
import type { CrewMember } from '../api/client';
import { HealthBadge, EmptyState, Button } from '../ds';
import { LoadingOverlay } from '../components/Spinner';
import CrewDrawer from '../components/CrewDrawer';
import AddHostModal from '../components/AddHostModal';
import { fmtSeconds } from '../util/time';
import { buildRoute } from '../hooks/useRoute';

const CREW_POLL_MS = 15_000;

type CrewPanelProps = {
  liveTick?: number;
};

const LINK = { color: 'var(--text-link, #6ea8fe)', textDecoration: 'underline' } as const;
const runHref = (runId: string) => buildRoute({ page: 'run', runId, tab: 'summary', ticket: null });
// Ticket ids are `<run_id>/t-<n>` (engine/db/schema.sql:18), so the run is the prefix.
const ticketHref = (ticket: string) =>
  buildRoute({ page: 'run', runId: ticket.slice(0, ticket.indexOf('/')), tab: 'tickets', ticket });
// A row is a button that opens the drawer; a link inside it navigates instead.
const stopRow = (e: React.MouseEvent) => e.stopPropagation();

const PAGE = { flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'auto' } as const;
const HEADER = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  padding: '20px 20px 12px',
  borderBottom: '1px solid var(--border-hairline)',
} as const;
// The page's <h1>, which the skip link and arrival focus target, in every state.
const TITLE = (
  <h1 tabIndex={-1} style={{ margin: 0, fontSize: 16, fontWeight: 500, color: 'var(--text-primary)' }}>
    Crew
  </h1>
);
// Loading, error and empty: the header with only its title, over the state's body. Every
// state puts TITLE first inside the same two <div>s, so React keeps one <h1> node from
// loading to loaded and focus stays on it.
const bare = (body: React.ReactNode) => (
  <div style={PAGE}>
    <div style={HEADER}>{TITLE}</div>
    {body}
  </div>
);

export default function CrewPanel({ liveTick }: CrewPanelProps) {
  const [crew, setCrew] = useState<CrewMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedHost, setSelectedHost] = useState<CrewMember | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);

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

  useEffect(() => {
    loadCrew();
  }, [liveTick]); // eslint-disable-line react-hooks/exhaustive-deps

  // Ages are counted server-side at fetch time, and a long turn emits no
  // events, so without this "0s" would stand for the whole turn.
  useEffect(() => {
    const id = setInterval(loadCrew, CREW_POLL_MS);
    return () => clearInterval(id);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Only show the full-page spinner on the initial load (no data yet).
  // Background live refetches must not blank the already-rendered crew list.
  if (loading && crew.length === 0) {
    return bare(
      <div style={{ position: 'relative', flex: 1, minHeight: 0 }}>
        <LoadingOverlay label="Loading crew…" />
      </div>
    );
  }

  if (error) {
    return bare(
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <EmptyState
          title="Error loading crew"
          description={error}
          icon="alert-circle"
        />
      </div>
    );
  }

  if (crew.length === 0) {
    return bare(
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <EmptyState
          title="No crew members"
          description="No hosts have been registered yet"
          icon="users"
        />
      </div>
    );
  }

  return (
    <>
      <div style={PAGE}>
        <div style={HEADER}>
          {TITLE}
          <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>
            {crew.length} {crew.length === 1 ? 'host' : 'hosts'}
            {` · ${crew.filter((m) => m.current_ticket).length} working`}
          </span>
          <div style={{ marginLeft: 'auto' }}>
            <Button variant="primary" size="sm" onClick={() => setShowAddModal(true)}>
              Add Host
            </Button>
          </div>
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
            <span>working on</span>
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

              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                {member.health ? (
                  <HealthBadge health={member.health} size="sm" />
                ) : (
                  <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>unknown</span>
                )}
                {member.heartbeat_age_s != null && (
                  <span title="last heartbeat" style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    {fmtSeconds(member.heartbeat_age_s)} ago
                  </span>
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

              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 12,
                  color: member.current_ticket ? 'var(--text-secondary)' : 'var(--text-muted)'
                }}
              >
                {member.current_ticket && member.current_run ? (
                  <>
                    <a
                      href={ticketHref(member.current_ticket)}
                      title={member.current_ticket}
                      onClick={stopRow}
                      style={LINK}
                    >
                      {member.current_phase}
                    </a>
                    {` · ${fmtSeconds(member.current_elapsed_s)} · `}
                    <a href={runHref(member.current_run)} onClick={stopRow} style={LINK}>
                      {member.current_run}
                    </a>
                  </>
                ) : '—'}
              </span>
            </div>
          ))}
        </div>
      </div>

      <CrewDrawer
        isOpen={selectedHost !== null}
        host={selectedHost && (crew.find((m) => m.id === selectedHost.id) ?? selectedHost)}
        onClose={() => setSelectedHost(null)}
        onRefresh={loadCrew}
      />

      <AddHostModal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        onAdded={() => {
          setShowAddModal(false);
          loadCrew();
        }}
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
