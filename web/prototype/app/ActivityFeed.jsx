function ActivityFeed() {
  const { EventRow, Select, Button, Card } = window.DSNS;
  const F = window.HERMES;
  const [kind, setKind] = React.useState('all events');
  const kinds = ['all events', 'ticket_claimed', 'result_recorded', 'phase_advanced', 'host_down', 'lease_acquired'];
  const rows = F.events.filter((e) => kind === 'all events' || e.kind === kind);

  return (
    <div style={{ flex: 1, overflow: 'auto', padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <SectionHead title="Activity" />
        <LiveDot label="streaming" />
        <div style={{ flex: 1 }} />
        <Select options={kinds} value={kind} onChange={(e) => setKind(e.target.value)} />
        <Button variant="ghost" size="sm">Pause</Button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 1fr)', gap: 16, alignItems: 'start' }}>
        <div>
          {rows.map((e) => <EventRow key={e.ts} event={e} />)}
        </div>
        <Card title="Leases" subtitle="Scarce-resource claims" padding="md">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {F.leases.map((l) => (
              <div key={l.id} style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                <span style={{ color: 'var(--text-secondary)' }}>{l.resource_class} &middot; {l.host}</span>
                <span style={{ color: 'var(--text-muted)' }}>{l.holder_ticket} &middot; {Math.round(l.ttl_s / 60)}m ttl</span>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
Object.assign(window, { ActivityFeed });
