function TicketDrawer({ ticket, onClose }) {
  const { Drawer, Button, Tabs, StatusPill, Badge, Divider } = window.DSNS;
  const F = window.HERMES;
  const [tab, setTab] = React.useState('payload');
  const t = ticket || {};

  const mono = { fontFamily: 'var(--font-mono)', fontSize: 12, lineHeight: '18px' };

  return (
    <Drawer open={!!ticket} title={t.id} subtitle={t.host ? t.host + ' · ' + t.phase : t.phase} onClose={onClose}
      tabs={<Tabs value={tab} onChange={setTab} items={[
        { value: 'payload', label: 'Payload' },
        { value: 'result', label: 'Result' },
        { value: 'history', label: 'History' },
        { value: 'log', label: 'Log' },
      ]} />}
      footer={<>
        <Button variant="ghost" size="sm" onClick={onClose}>Park</Button>
        <Button variant="ghost" size="sm">Reprioritize</Button>
        <Button size="sm">Requeue</Button>
      </>}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <StatusPill state={t.state} />
        <Badge size="sm" variant="outline">{t.resource_req}</Badge>
        <span style={{ ...mono, color: 'var(--text-muted)' }}>try {t.attempts} &middot; {t.elapsed_s}s &middot; p{t.priority}</span>
      </div>
      <span style={{ color: 'var(--text-primary)', fontSize: 13, lineHeight: '18px', wordBreak: 'break-word' }}>{t.subject}</span>
      <Divider />

      {tab === 'payload' && (
        <pre style={{ ...mono, margin: 0, color: 'var(--text-secondary)', whiteSpace: 'pre-wrap' }}>
{JSON.stringify({ ticket_id: t.id, run_id: t.run_id, playbook: 'mechanic', phase: t.phase, target: t.subject, resource_req: t.resource_req, budget_s: 900, base_ref: 'a1b2c3d' }, null, 2)}
        </pre>
      )}

      {tab === 'result' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <pre style={{ ...mono, margin: 0, color: 'var(--text-secondary)', whiteSpace: 'pre-wrap' }}>
{JSON.stringify({ verdict: 'reproduced', confidence: 0.82, finding_id: 'f-31', category: 'test isolation' }, null, 2)}
          </pre>
          <div style={{ display: 'flex', gap: 8 }}>
            <Button variant="ghost" size="sm">Open evidence</Button>
            <Button variant="ghost" size="sm">Open finding f-31</Button>
          </div>
        </div>
      )}

      {tab === 'history' && (
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {[['attempt 1', 'timed out after 900s on node-a11'], ['attempt 2', 'reproduced on gpu-c07'], ['reduction', 'merged into finding f-31']].map((h, i) => (
            <div key={h[0]} style={{ display: 'flex', gap: 12, padding: '10px 0', borderBottom: '1px solid var(--border-hairline)' }}>
              <span style={{ ...mono, color: 'var(--text-muted)', width: 74, flex: 'none' }}>{h[0]}</span>
              <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>{h[1]}</span>
            </div>
          ))}
        </div>
      )}

      {tab === 'log' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <LiveDot label="tailing" />
          </div>
          <pre style={{ ...mono, margin: 0, color: 'var(--text-secondary)', whiteSpace: 'pre-wrap' }}>{F.logTail.join('\n')}</pre>
        </div>
      )}
    </Drawer>
  );
}

function HostDrawer({ member, onClose }) {
  const { Drawer, Button, StatusPill, HealthBadge, Divider } = window.DSNS;
  const m = member || {};
  const res = m.resources || {};
  const mono = { fontFamily: 'var(--font-mono)', fontSize: 12, lineHeight: '18px' };
  return (
    <Drawer open={!!member} title={m.id} subtitle={m.site} onClose={onClose}
      footer={<>
        <Button variant="ghost" size="sm">Remove</Button>
        <Button variant="ghost" size="sm">Re-probe</Button>
        <Button size="sm">Drain</Button>
      </>}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <StatusPill state={m.state} />
        <span style={{ ...mono, color: 'var(--text-muted)' }}>heartbeat {m.last_heartbeat}</span>
      </div>
      <HealthBadge health={m.health} style={{ gap: 12 }} />
      <Divider />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, ...mono, color: 'var(--text-secondary)' }}>
        <span>resources: {Object.keys(res).map((k) => res[k] + '× ' + k).join(' · ') || '—'}</span>
        <span>current ticket: {m.current_ticket || '—'}</span>
        <span>throughput: {m.throughput_per_min}/min</span>
      </div>
    </Drawer>
  );
}
Object.assign(window, { TicketDrawer, HostDrawer });
