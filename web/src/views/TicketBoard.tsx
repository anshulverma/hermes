/**
 * TicketBoard - kanban view with real tickets from API.
 * Phase B2: kanban columns, filters, search, drawer.
 * Ported from web/prototype/app/TicketBoard.jsx with REAL data.
 */

import { useState, useEffect } from 'react';
import { fetchTickets } from '../api/client';
import type { Ticket, TicketFilters } from '../api/client';
import { normalizeTicketState } from '../api/normalize';
import { Button, StatusPill, TicketCard, TICKET_STATES, TONES } from '../ds';
import TicketDrawer from '../components/TicketDrawer';

// Lane definitions matching prototype
const TICKET_LANES = [
  { id: 'waiting', label: 'waiting', states: ['queued', 'dispatched'] },
  { id: 'working', label: 'working', states: ['running', 'reducing'] },
  { id: 'attention', label: 'needs attention', states: ['parked', 'failed', 'needs-human'] },
  { id: 'done', label: 'done', states: ['done'] },
];

type StateChipProps = {
  state: string;
  count: number;
  active: boolean;
  onClick: () => void;
};

function StateChip({ state, count, active, onClick }: StateChipProps) {
  return (
    <button
      onClick={onClick}
      title={`Filter to ${state}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '2px 6px 2px 2px',
        background: active ? 'var(--wash-selected)' : 'transparent',
        border: `1px solid ${active ? 'var(--border-hairline)' : 'transparent'}`,
        borderRadius: 'var(--radius-lg)',
        cursor: 'pointer',
      }}
    >
      <StatusPill state={state} size="sm" />
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 12,
          color: 'var(--text-secondary)',
        }}
      >
        {count}
      </span>
    </button>
  );
}

type TicketLaneProps = {
  lane: { id: string; label: string; states: string[] };
  tickets: Ticket[];
  stateFilter: string | undefined;
  onStateFilter: (state: string | undefined) => void;
  onOpen: (ticket: Ticket) => void;
  filtering: boolean;
};

function TicketLane({ lane, tickets, stateFilter, onStateFilter, onOpen, filtering }: TicketLaneProps) {
  const states = lane.states.filter((s) => !stateFilter || s === stateFilter);
  const rows = tickets.filter((t) => states.includes(normalizeTicketState(t.state)));

  const hueOf = (st: string) => {
    const tone = (TICKET_STATES as any)?.[st]?.tone || 'neutral';
    return tone === 'neutral' ? 'rgba(255,255,255,0.28)' : (TONES as any)?.[tone]?.fg || 'rgba(255,255,255,0.28)';
  };

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 12, minHeight: 0, minWidth: 0 }}>
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          paddingBottom: 8,
          borderBottom: '1px solid var(--border-hairline)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <span style={{ color: 'var(--text-primary)', fontSize: 14 }}>{lane.label}</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>
            {rows.length}
          </span>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {lane.states.map((s) => (
            <StateChip
              key={s}
              state={s}
              count={tickets.filter((t) => normalizeTicketState(t.state) === s).length}
              active={stateFilter === s}
              onClick={() => onStateFilter(stateFilter === s ? undefined : s)}
            />
          ))}
        </div>
      </div>
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          overflow: 'auto',
          minHeight: 0,
          paddingBottom: 16,
        }}
      >
        {rows.length ? (
          rows.map((t) => (
            <TicketCard
              key={t.id}
              ticket={{
                id: t.id,
                subject: t.subject,
                phase: t.phase,
                attempts: t.attempts,
                elapsed_s: t.elapsed_s,
                resource_req: t.resource_req,
                host: t.host || undefined,
              }}
              onClick={() => onOpen(t)}
              style={{ borderLeft: `2px solid ${hueOf(normalizeTicketState(t.state))}` }}
            />
          ))
        ) : (
          <div
            style={{
              padding: '24px 12px',
              textAlign: 'center',
              color: 'var(--text-muted)',
              fontSize: 12,
              border: '1px dashed var(--border-hairline)',
              borderRadius: 'var(--radius-lg)',
            }}
          >
            {filtering ? 'Nothing matches here' : 'No tickets'}
          </div>
        )}
      </div>
    </section>
  );
}

type TicketBoardProps = {
  runId: string;
};

export default function TicketBoard({ runId }: TicketBoardProps) {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState('');
  const [phase, setPhase] = useState('all phases');
  const [resource, setResource] = useState('all resources');
  const [stateFilter, setStateFilter] = useState<string | undefined>(undefined);

  // Drawer
  const [selectedTicket, setSelectedTicket] = useState<Ticket | null>(null);

  // Fetch tickets
  useEffect(() => {
    const filters: TicketFilters = {};
    if (stateFilter) filters.state = stateFilter;
    if (phase !== 'all phases') filters.phase = phase;
    if (resource !== 'all resources') filters.resource = resource;
    if (search) filters.search = search;

    setLoading(true);
    setError(null);
    fetchTickets(runId, filters)
      .then((data) => {
        setTickets(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [runId, stateFilter, phase, resource, search]);

  const clearFilters = () => {
    setSearch('');
    setPhase('all phases');
    setResource('all resources');
    setStateFilter(undefined);
  };

  const filtering = search !== '' || phase !== 'all phases' || resource !== 'all resources';

  if (loading && tickets.length === 0) {
    return (
      <div
        style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--text-muted)',
        }}
      >
        Loading tickets...
      </div>
    );
  }

  if (error) {
    return (
      <div
        style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--status-danger)',
        }}
      >
        Error: {error}
      </div>
    );
  }

  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      {/* Filter bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '16px 20px',
          borderBottom: '1px solid var(--border-hairline)',
        }}
      >
        <input
          type="text"
          placeholder="Search tickets, hosts"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            width: 260,
            padding: '6px 10px',
            fontSize: 13,
            color: 'var(--text-primary)',
            background: 'var(--wash-subtle)',
            border: '1px solid var(--border-hairline)',
            borderRadius: 'var(--radius-md)',
          }}
        />
        <select
          value={phase}
          onChange={(e) => setPhase(e.target.value)}
          style={{
            padding: '6px 10px',
            fontSize: 13,
            color: 'var(--text-primary)',
            background: 'var(--wash-subtle)',
            border: '1px solid var(--border-hairline)',
            borderRadius: 'var(--radius-md)',
          }}
        >
          <option>all phases</option>
          <option>diagnose</option>
          <option>work</option>
          <option>reduce</option>
          <option>fix</option>
        </select>
        <select
          value={resource}
          onChange={(e) => setResource(e.target.value)}
          style={{
            padding: '6px 10px',
            fontSize: 13,
            color: 'var(--text-primary)',
            background: 'var(--wash-subtle)',
            border: '1px solid var(--border-hairline)',
            borderRadius: 'var(--radius-md)',
          }}
        >
          <option>all resources</option>
          <option>cpu</option>
          <option>gpu</option>
        </select>
        <span style={{ color: 'var(--text-muted)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>
          {tickets.length} shown
        </span>
        <div style={{ flex: 1 }} />
        <Button variant="ghost" size="sm" onClick={clearFilters}>
          Clear
        </Button>
      </div>

      {/* Kanban lanes */}
      <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', padding: '16px 20px 0' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 16, height: '100%' }}>
          {TICKET_LANES.map((lane) => {
            const activeFilter = lane.states.includes(stateFilter || '') ? stateFilter : undefined;
            return (
              <TicketLane
                key={lane.id}
                lane={lane}
                tickets={tickets}
                stateFilter={activeFilter}
                onStateFilter={setStateFilter}
                onOpen={setSelectedTicket}
                filtering={filtering}
              />
            );
          })}
        </div>
      </div>

      {/* Ticket drawer */}
      <TicketDrawer
        isOpen={selectedTicket !== null}
        ticket={selectedTicket}
        onClose={() => setSelectedTicket(null)}
      />
    </div>
  );
}
