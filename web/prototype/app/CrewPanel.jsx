function AddHostModal({ open, onClose }) {
  const { Dialog, Input, Button, HealthBadge } = window.DSNS;
  const [step, setStep] = React.useState(0);
  const probes = ['reachable', 'agent_ok', 'auth_ok', 'workspace_ready', 'guard_installed'];

  React.useEffect(() => {
    if (!open) { setStep(0); return; }
    const id = setInterval(() => setStep((s) => (s >= probes.length ? s : s + 1)), 700);
    return () => clearInterval(id);
  }, [open]);

  const health = {};
  probes.forEach((p, i) => { health[p] = i < step ? true : null; });

  return (
    <Dialog open={open} title="Add crew member" description="Hermes probes the host before it joins the pool."
      onClose={onClose}
      footer={<><Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
               <Button size="sm" disabled={step < probes.length} onClick={onClose}>Add host</Button></>}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <Input label="Hostname" defaultValue="node-e02" />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>health check</span>
          <HealthBadge health={health} showLatency={false} style={{ gap: 12 }} />
          <span style={{ color: 'var(--text-muted)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>
            {step < probes.length ? step + ' of ' + probes.length + ' probes complete' : 'all probes passed'}
          </span>
        </div>
      </div>
    </Dialog>
  );
}

function CrewPanel({ onOpenHost }) {
  const { CrewRow, CREW_GRID, Button, IconButton, Tooltip, StatTile } = window.DSNS;
  const GRID = CREW_GRID.replace(/150px$/, '250px');
  const errTone = (r) => (r >= 8 ? 'var(--status-danger)' : r >= 3 ? 'var(--status-attention)' : 'var(--text-muted)');
  const F = window.HERMES;
  const [adding, setAdding] = React.useState(false);
  const online = F.crew.filter((m) => m.state !== 'down').length;

  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'auto' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 12, padding: 20 }}>
        <StatTile label="crew online" value={online + ' / ' + F.crew.length} delta="1 draining, 1 down" tone="attention" />
        <StatTile label="gpu leases" value={F.leases.length + ' / 2'} delta="both held over 40m" />
        <StatTile label="cpu capacity" value="400" delta="cores across 6 hosts" />
        <StatTile label="mean latency" value="35ms" tone="live" live />
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '0 20px 12px' }}>
        <SectionHead title="Crew" meta={F.crew.length + ' hosts'} />
        <div style={{ flex: 1 }} />
        <Tooltip label="Re-probe all" placement="left">
          <IconButton label="Re-probe all"><i data-lucide="refresh-cw" style={{ width: 15, height: 15 }} /></IconButton>
        </Tooltip>
        <Button size="sm" iconLeft={<i data-lucide="plus" style={{ width: 14, height: 14 }} />} onClick={() => setAdding(true)}>Add host</Button>
      </div>

      <div style={{ borderTop: '1px solid var(--border-hairline)' }}>
        <div style={{
          display: 'grid',
          gridTemplateColumns: GRID,
          gap: 'var(--space-4)', padding: '10px var(--space-4)',
          borderBottom: '1px solid var(--border-hairline)',
          color: 'var(--text-muted)', fontSize: 12,
        }}>
          <span>host</span><span>state</span><span>health</span><span>resources</span><span>current ticket</span><span>throughput</span><span style={{ textAlign: 'right' }}>heartbeat &middot; errors</span>
        </div>
        {F.crew.map((m) => (
          <CrewRow key={m.id} member={m} onClick={() => onOpenHost(m)} style={{ gridTemplateColumns: GRID }}
            actions={
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <Tooltip label={m.errors + (m.errors === 1 ? ' failed result · ' : ' failed results · ') + m.error_rate + '% of its results'} placement="left">
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontFamily: 'var(--font-mono)', fontSize: 12, color: errTone(m.error_rate), marginRight: 4 }}>
                    <span>{m.errors}</span>
                    <span style={{ opacity: 0.75 }}>{m.error_rate}%</span>
                  </span>
                </Tooltip>
                <Tooltip label="Drain" placement="left"><IconButton label="Drain"><i data-lucide="arrow-down-to-line" style={{ width: 14, height: 14 }} /></IconButton></Tooltip>
                <Tooltip label="Remove" placement="left"><IconButton label="Remove"><i data-lucide="minus" style={{ width: 14, height: 14 }} /></IconButton></Tooltip>
              </div>
            } />
        ))}
      </div>

      <AddHostModal open={adding} onClose={() => setAdding(false)} />
    </div>
  );
}
Object.assign(window, { AddHostModal, CrewPanel });
