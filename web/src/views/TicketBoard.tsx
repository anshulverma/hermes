/**
 * TicketBoard - kanban view with real tickets from API.
 * Ported from web/prototype/app/TicketBoard.jsx with REAL data.
 *
 * The open ticket lives in the URL hash (`#board?ticket=<id>`), not in local
 * state alone, so a refresh reopens it and the address bar is a link worth
 * sending. The board holds only the id; the ticket object is looked up in the
 * loaded rows, and synthesised from the id when a filter is hiding it -- the
 * modal refetches full detail by id either way.
 */

import { useState, useEffect, useMemo } from 'react';
import { fetchTickets } from '../api/client';
import type { Ticket, TicketFilters } from '../api/client';
import { normalizeTicketState } from '../api/normalize';
import { Button, StatusPill, TICKET_STATES, TONES } from '../ds';
import TicketModal from '../components/TicketModal';
import HermesTicketCard from '../components/HermesTicketCard';
import { LoadingOverlay } from '../components/Spinner';
import { useHashParam } from '../hooks/useHashView';

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

/**
 * One engine state within a lane, as a filter.
 *
 * Rendered only when it has tickets, and never on a lane that holds a single
 * state: a chip reading `done 35` under a lane headed `done 35` is noise, and a
 * row of zeroes reads as a legend rather than the filter it is.
 */
function StateChip({ state, count, active, onClick }: StateChipProps) {
  return (
    <button
      data-testid={`state-chip-${state}`}
      onClick={onClick}
      aria-pressed={active}
      title={active ? `Stop filtering to ${state}` : `Filter this lane to ${state}`}
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

  const countOf = (s: string) =>
    tickets.filter((t) => normalizeTicketState(t.state) === s).length;

  // A chip has to earn its place: it must be able to filter to something, and
  // it must say something the lane header does not. The active one stays even
  // as it narrows its own lane to itself, or there would be no way back.
  const chipStates =
    lane.states.length < 2
      ? []
      : lane.states.filter((s) => countOf(s) > 0 || s === stateFilter);

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
          {chipStates.map((s) => (
            <StateChip
              key={s}
              state={s}
              count={countOf(s)}
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
            <HermesTicketCard
              key={t.id}
              ticket={{
                id: t.id,
                subject: t.subject,
                state: t.state,
                phase: t.phase,
                attempts: t.attempts,
                elapsed_s: t.elapsed_s,
                resource_req: t.resource_req,
                host: t.host || undefined,
                priority: t.priority,
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
  liveTick?: number;
};

export default function TicketBoard({ runId, liveTick }: TicketBoardProps) {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState('');
  const [phase, setPhase] = useState('all phases');
  const [resource, setResource] = useState('all resources');
  const [stateFilter, setStateFilter] = useState<string | undefined>(undefined);

  // The open ticket, addressed by the URL so a refresh reopens it.
  const [openTicketId, setOpenTicketId] = useHashParam('ticket');

  // Bumped after a modal action mutates a ticket, to refetch the board.
  const [refreshTick, setRefreshTick] = useState(0);

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
  }, [runId, stateFilter, phase, resource, search, refreshTick, liveTick]);

  // The row the URL names. A ticket hidden by the current filters (or on a
  // board that has not loaded yet) still opens: the id alone is enough for the
  // modal, which fetches its own detail, so a stub carries it until the row
  // arrives rather than showing nothing on a deep link.
  const openTicket = useMemo<Ticket | null>(() => {
    if (openTicketId === null) return null;
    const found = tickets.find((t) => t.id === openTicketId);
    if (found) return found;
    return {
      id: openTicketId,
      run_id: runId,
      state: 'queued',
      phase: '',
      subject: '',
      resource_req: '',
      host: null,
      attempts: 0,
      elapsed_s: 0,
      priority: 0,
    } as Ticket;
  }, [openTicketId, tickets, runId]);

  const clearFilters = () => {
    setSearch('');
    setPhase('all phases');
    setResource('all resources');
    setStateFilter(undefined);
  };

  const filtering = search !== '' || phase !== 'all phases' || resource !== 'all resources';

  if (loading && tickets.length === 0) {
    return (
      <div style={{ position: 'relative', flex: 1, minHeight: 0 }}>
        <LoadingOverlay label="Loading tickets…" />
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
                onOpen={(t) => setOpenTicketId(t.id)}
                filtering={filtering}
              />
            );
          })}
        </div>
      </div>

      {/* Ticket detail */}
      <TicketModal
        isOpen={openTicketId !== null}
        ticket={openTicket}
        onClose={() => setOpenTicketId(null)}
        onActionSuccess={() => setRefreshTick((n) => n + 1)}
      />
    </div>
  );
}
