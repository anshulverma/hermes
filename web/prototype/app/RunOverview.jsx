function ProgressBar({ done, total }) {
  const pct = Math.round((done / total) * 100);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>
        <span>{done} / {total} tickets</span>
        <span>{pct}%</span>
      </div>
      <div style={{ height: 6, borderRadius: 'var(--radius-full)', background: 'var(--wash-active)', overflow: 'hidden' }}>
        <div style={{ width: pct + '%', height: '100%', background: 'var(--status-ok)', transition: 'width 160ms ease-out' }} />
      </div>
    </div>
  );
}

function PhaseTimeline({ phases }) {
  const { StatusPill } = window.DSNS;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', gap: 4 }}>
        {phases.map((p) => (
          <div key={p.name} style={{ flex: p.share, display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{
              height: 6, borderRadius: 'var(--radius-full)',
              background: p.state === 'running' ? 'var(--status-live)' : 'var(--wash-active)',
              animation: p.state === 'running' ? 'fm-pulse 1.6s ease-out infinite' : 'none',
            }} />
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <StatusPill state={p.state} label={p.name} size="sm" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Sparkline({ points }) {
  const max = Math.max.apply(null, points);
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 24, marginTop: 4 }}>
      {points.map((p, i) => (
        <span key={i} style={{ flex: 1, height: Math.max(2, (p / max) * 24), background: i === points.length - 1 ? 'var(--status-live)' : 'var(--wash-active)', borderRadius: 1 }} />
      ))}
    </div>
  );
}

function RunOverview({ onView }) {
  const { StatTile, AttentionBanner, Card, Button, Divider, EventRow, StatusPill } = window.DSNS;
  const F = window.HERMES;
  const run = F.run;
  const [acked, setAcked] = React.useState(false);

  return (
    <div style={{ flex: 1, overflow: 'auto', padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <AttentionBanner severity="critical" title="Crew member node-b04 is down"
          detail="No heartbeat in 4m 12s. 2 tickets were requeued."
          actionLabel="Open crew" onAction={() => onView('crew')} />
        {!acked && (
          <AttentionBanner title="No progress in 31m on 4 parked tickets"
            detail="All four are waiting on a gpu lease." onAcknowledge={() => setAcked(true)} />
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, minmax(0, 1fr))', gap: 12 }}>
        <StatTile label="tickets" value={run.tickets.total} delta="214 in batch" />
        <StatTile label="done" value={run.tickets.done} delta="+4 in last 5m" tone="ok" />
        <StatTile label="in flight" value={run.tickets.running} tone="live" live emphasis />
        <StatTile label="parked" value={run.tickets.parked} delta="4 on gpu lease" tone="attention" />
        <StatTile label="failed" value={run.tickets.failed} delta="2 need a human" tone="danger" />
        <StatTile label="throughput" value="0.9" delta="tickets / min" sparkline={<Sparkline points={[4, 5, 6, 8, 7, 9, 7, 8, 11, 9]} />} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.5fr) minmax(0, 1fr)', gap: 16, alignItems: 'start' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Card padding="md" style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ color: 'var(--text-primary)', fontSize: 20, lineHeight: '26px' }}>{run.playbook} run</span>
              <StatusPill state={run.state} />
              <div style={{ flex: 1 }} />
              <span style={{ color: 'var(--text-muted)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>started {run.started_at} &middot; {run.eta}</span>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {(run.context || []).map((c) => (
                <span key={c.label} style={{ display: 'flex', gap: 6, padding: '4px 10px', border: '1px solid var(--border-hairline)', borderRadius: 'var(--radius-lg)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                  <span style={{ color: 'var(--text-muted)' }}>{c.label}</span>
                  <span style={{ color: 'var(--text-secondary)' }}>{c.value}</span>
                </span>
              ))}
            </div>
            <ProgressBar done={run.tickets.done} total={run.tickets.total} />
            <Divider />
            <PhaseTimeline phases={F.phases} />
          </Card>

          <Card title="Crew" subtitle="4 of 6 online, 1 draining, 1 down"
            action={<Button size="sm" onClick={() => onView('crew')}>Open crew</Button>} padding="md">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {F.crew.map((m) => (
                <div key={m.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', border: '1px solid var(--border-hairline)', borderRadius: 'var(--radius-lg)' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)' }}>{m.id}</span>
                  <StatusPill state={m.state} size="sm" />
                </div>
              ))}
            </div>
          </Card>
        </div>

        <Card title="Live activity" action={<Button size="sm" onClick={() => onView('activity')}>All events</Button>} padding="md">
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {F.events.slice(0, 6).map((e) => (
              <div key={e.ts} style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '9px 0', borderBottom: '1px solid var(--border-hairline)' }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>{e.ts}</span>
                  <span style={{ color: e.severity === 'critical' ? 'var(--status-danger)' : 'var(--text-secondary)', fontSize: 13 }}>{e.message}</span>
                </div>
                {(e.host || e.ticket_id) && (
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>
                    {[e.host, e.ticket_id].filter(Boolean).join(' · ')}
                  </span>
                )}
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
Object.assign(window, { ProgressBar, PhaseTimeline, Sparkline, RunOverview });
