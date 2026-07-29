function PlaybookDialog({ open, run, playbook, onClose }) {
  const { Dialog, Button, Divider, StatusPill } = window.DSNS;
  if (!open || !playbook) return null;
  const row = (label, value) => (
    <div style={{ display: 'grid', gridTemplateColumns: '96px minmax(0, 1fr)', gap: 12, padding: '8px 0' }}>
      <span style={{ color: 'var(--text-muted)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>{label}</span>
      <span style={{ color: 'var(--text-secondary)', fontSize: 14 }}>{value}</span>
    </div>
  );
  return (
    <Dialog open title={playbook.name + ' playbook'} description={playbook.summary} width={560} onClose={onClose}
      footer={<Button size="sm" onClick={onClose}>Close</Button>}>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <Divider />
        {row('run', <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontFamily: 'var(--font-mono)', fontSize: 12 }}>{run.id}<StatusPill state={run.state} size="sm" /></span>)}
        <Divider />
        {row('site', <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{run.site}<span style={{ color: 'var(--text-muted)' }}> · environment and tools the crew runs in</span></span>)}
        <Divider />
        {row('context', (
          <span style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {(run.context || []).map((c) => (
              <span key={c.label} style={{ display: 'flex', gap: 6, padding: '4px 10px', border: '1px solid var(--border-hairline)', borderRadius: 'var(--radius-lg)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                <span style={{ color: 'var(--text-muted)' }}>{c.label}</span>
                <span style={{ color: 'var(--text-secondary)' }}>{c.value}</span>
              </span>
            ))}
          </span>
        ))}
        {row('', <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>{playbook.context_note}</span>)}
        <Divider />
        {row('phases', (
          <span style={{ display: 'flex', flexWrap: 'wrap', gap: 8, fontFamily: 'var(--font-mono)', fontSize: 12 }}>
            {playbook.phases.map((p) => (
              <span key={p} style={{ color: p === run.phase ? 'var(--status-live)' : 'var(--text-secondary)' }}>{p}</span>
            ))}
          </span>
        ))}
        <Divider />
        {row('stops at', playbook.stops_at)}
      </div>
    </Dialog>
  );
}

function HermesApp() {
  const F = window.HERMES;
  const [view, setView] = React.useState('overview');
  const [ticket, setTicket] = React.useState(null);
  const [host, setHost] = React.useState(null);
  const [stopping, setStopping] = React.useState(false);
  const [playbookOpen, setPlaybookOpen] = React.useState(false);
  const { Dialog, Button, CrewBackdrop } = window.DSNS;

  React.useEffect(() => { if (window.lucide) lucide.createIcons(); });

  return (
    <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      <CrewBackdrop theme="graph" fixed={false} basePath="_ds/mono-dark-dash-design-system-66fdfec6-1d48-4dc6-9bbe-67df91704189/assets/backdrops/" />
      <TopBar run={F.run} view={view} onView={setView} onStop={() => setStopping(true)} onOpenPlaybook={() => setPlaybookOpen(true)} />
      <div style={{ position: 'relative', zIndex: 1, flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        {view === 'overview' && <RunOverview onView={setView} />}
        {view === 'metrics' && <MetricsView />}
        {view === 'board' && <TicketBoard onOpen={setTicket} />}
        {view === 'crew' && <CrewPanel onOpenHost={setHost} />}
        {view === 'findings' && <Findings />}
        {view === 'activity' && <ActivityFeed />}
      </div>

      <TicketDrawer ticket={ticket} onClose={() => setTicket(null)} />
      <HostDrawer member={host} onClose={() => setHost(null)} />

      <PlaybookDialog open={playbookOpen} run={F.run} playbook={F.playbooks[F.run.playbook]} onClose={() => setPlaybookOpen(false)} />

      <Dialog open={stopping} title="Stop this run?" description="In-flight tickets finish; nothing new is dispatched."
        onClose={() => setStopping(false)}
        footer={<><Button variant="ghost" size="sm" onClick={() => setStopping(false)}>Keep running</Button>
                 <Button size="sm" onClick={() => setStopping(false)}>Stop run</Button></>} />
    </div>
  );
}
Object.assign(window, { PlaybookDialog, HermesApp });
