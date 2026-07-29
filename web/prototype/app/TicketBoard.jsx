const TICKET_LANES = [
  { id: 'waiting', label: 'waiting', states: ['queued', 'dispatched'] },
  { id: 'working', label: 'working', states: ['running', 'reducing'] },
  { id: 'attention', label: 'needs attention', states: ['parked', 'failed', 'needs-human'] },
  { id: 'done', label: 'done', states: ['done'] },
];

function StateChip({ state, count, active, onClick }) {
  const { StatusPill } = window.DSNS;
  return (
    <button onClick={onClick} title={'Filter to ' + state}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '2px 6px 2px 2px', background: active ? 'var(--wash-selected)' : 'transparent',
        border: '1px solid ' + (active ? 'var(--border-hairline)' : 'transparent'), borderRadius: 'var(--radius-lg)', cursor: 'pointer' }}>
      <StatusPill state={state} size="sm" />
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)' }}>{count}</span>
    </button>
  );
}

function TicketLane({ lane, tickets, hueOf, stateFilter, onStateFilter, onOpen, emptyText }) {
  const { TicketCard } = window.DSNS;
  const states = lane.states.filter((s) => !stateFilter || s === stateFilter);
  const rows = tickets.filter((t) => states.indexOf(t.state) !== -1);
  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 12, minHeight: 0, minWidth: 0 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingBottom: 8, borderBottom: '1px solid var(--border-hairline)' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <span style={{ color: 'var(--text-primary)', fontSize: 14 }}>{lane.label}</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>{rows.length}</span>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {lane.states.map((s) => (
            <StateChip key={s} state={s} count={tickets.filter((t) => t.state === s).length}
              active={stateFilter === s} onClick={() => onStateFilter(stateFilter === s ? null : s)} />
          ))}
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, overflow: 'auto', minHeight: 0, paddingBottom: 16 }}>
        {rows.length ? rows.map((t) => (
          <TicketCard key={t.id} ticket={t} onClick={() => onOpen(t)}
            style={{ borderLeft: '2px solid ' + hueOf(t.state) }} />
        )) : (
          <div style={{ padding: '24px 12px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 12, border: '1px dashed var(--border-hairline)', borderRadius: 'var(--radius-lg)' }}>{emptyText}</div>
        )}
      </div>
    </section>
  );
}

function TicketList({ tickets, hueOf, onOpen }) {
  const { Table, StatusPill } = window.DSNS;
  return (
    <div style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: '0 20px 20px' }}>
      <Table dense onRowClick={(r) => onOpen(r)}
        columns={[
          { key: 'id', label: 'id', mono: true, render: (r) => (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              <span aria-hidden="true" style={{ width: 2, height: 14, background: hueOf(r.state) }} />{r.id}
            </span>
          ) },
          { key: 'state', label: 'state', render: (r) => <StatusPill state={r.state} size="sm" /> },
          { key: 'subject', label: 'subject' },
          { key: 'phase', label: 'phase', muted: true },
          { key: 'resource_req', label: 'resource', mono: true, muted: true },
          { key: 'host', label: 'host', mono: true, muted: true, render: (r) => r.host || '—' },
          { key: 'attempts', label: 'attempts', mono: true, muted: true, align: 'right' },
          { key: 'elapsed_s', label: 'elapsed_s', mono: true, muted: true, align: 'right' },
          { key: 'priority', label: 'priority', mono: true, muted: true, align: 'right' },
        ]}
        rows={tickets} />
    </div>
  );
}

function TicketBoard({ onOpen }) {
  const { TICKET_STATES, TONES, Input, Select, Button, IconButton, Tooltip } = window.DSNS;
  const F = window.HERMES;
  const [q, setQ] = React.useState('');
  const [phase, setPhase] = React.useState('all phases');
  const [resource, setResource] = React.useState('all resources');
  const [stateFilter, setStateFilter] = React.useState(null);
  const [mode, setMode] = React.useState('lanes');

  const hueOf = (st) => {
    const tone = (TICKET_STATES[st] || {}).tone || 'neutral';
    return tone === 'neutral' ? 'rgba(255,255,255,0.28)' : TONES[tone].fg;
  };

  const match = (t) =>
    (!q || (t.subject + ' ' + t.id + ' ' + (t.host || '')).toLowerCase().includes(q.toLowerCase())) &&
    (phase === 'all phases' || t.phase === phase) &&
    (resource === 'all resources' || t.resource_req === resource);

  const visible = F.tickets.filter(match);
  const listRows = stateFilter ? visible.filter((t) => t.state === stateFilter) : visible;
  const filtering = q || phase !== 'all phases' || resource !== 'all resources';

  const modeBtn = (id, label, icon) => (
    <button onClick={() => setMode(id)}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 26, padding: '0 10px',
        background: mode === id ? 'var(--wash-selected)' : 'transparent', border: 'none', borderRadius: 'var(--radius-lg)',
        color: mode === id ? 'var(--text-primary)' : 'var(--text-muted)', font: '400 12px var(--font-sans)', cursor: 'pointer' }}>
      <i data-lucide={icon} style={{ width: 14, height: 14 }} />{label}
    </button>
  );

  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '16px 20px', borderBottom: '1px solid var(--border-hairline)' }}>
        <Input placeholder="Search tickets, hosts" value={q} onChange={(e) => setQ(e.target.value)}
          prefix={<i data-lucide="search" style={{ width: 14, height: 14 }} />} style={{ width: 260 }} />
        <Select options={['all phases', 'diagnose', 'reduce', 'fix']} value={phase} onChange={(e) => setPhase(e.target.value)} />
        <Select options={['all resources', 'cpu', 'gpu']} value={resource} onChange={(e) => setResource(e.target.value)} />
        <span style={{ color: 'var(--text-muted)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>{listRows.length} of {F.tickets.length} shown</span>
        <div style={{ flex: 1 }} />
        <div style={{ display: 'flex', gap: 2, padding: 2, border: '1px solid var(--border-hairline)', borderRadius: 'var(--radius-lg)' }}>
          {modeBtn('lanes', 'Lanes', 'columns-3')}
          {modeBtn('list', 'List', 'table-2')}
        </div>
        <Button variant="ghost" size="sm" onClick={() => { setQ(''); setPhase('all phases'); setResource('all resources'); setStateFilter(null); }}>Clear</Button>
      </div>

      {mode === 'lanes' ? (
        <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', padding: '16px 20px 0' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 16, height: '100%' }}>
            {TICKET_LANES.map((lane) => (
              <TicketLane key={lane.id} lane={lane} tickets={visible} hueOf={hueOf} onOpen={onOpen}
                stateFilter={lane.states.indexOf(stateFilter) !== -1 ? stateFilter : null}
                onStateFilter={setStateFilter}
                emptyText={filtering ? 'Nothing matches here' : 'No tickets'} />
            ))}
          </div>
        </div>
      ) : (
        <TicketList tickets={listRows} hueOf={hueOf} onOpen={onOpen} />
      )}
    </div>
  );
}
Object.assign(window, { TICKET_LANES, StateChip, TicketLane, TicketList, TicketBoard });
