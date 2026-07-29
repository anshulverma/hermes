function Findings() {
  const { Card, Badge, Button, Divider, StatusPill } = window.DSNS;
  const F = window.HERMES;
  const FIX_LABEL = { diff_published: 'diff published', proposed: 'change proposed', needs_human: 'needs human' };

  return (
    <div style={{ flex: 1, overflow: 'auto', padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <SectionHead title="Findings" meta={F.findings.length + ' unique root causes from 96 results'} />
      {F.findings.map((fd) => (
        <Card key={fd.id} padding="md">
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
            <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>{fd.id}</span>
                <Badge size="sm" variant="outline">{fd.category}</Badge>
                {fd.fix_state === 'needs_human'
                  ? <StatusPill state="needs-human" size="sm" label={FIX_LABEL[fd.fix_state]} />
                  : <Badge size="sm" tone={fd.fix_state === 'diff_published' ? 'ok' : 'attention'} variant={fd.fix_state === 'diff_published' ? 'solid' : 'subtle'}>{FIX_LABEL[fd.fix_state]}</Badge>}
              </div>
              <span style={{ color: 'var(--text-primary)', fontSize: 20, lineHeight: '26px' }}>{fd.title}</span>
            </div>
            <div style={{ display: 'flex', gap: 8, flex: 'none' }}>
              <Button variant="ghost" size="sm">Open diff</Button>
              <Button size="sm">Review</Button>
            </div>
          </div>
          <Divider style={{ margin: '16px 0 12px' }} />
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>{fd.member_ticket_ids.length} member tickets</span>
            {fd.member_ticket_ids.map((id) => (
              <span key={id} style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', padding: '2px 6px', border: '1px solid var(--border-hairline)', borderRadius: 'var(--radius-lg)' }}>{id}</span>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}
Object.assign(window, { Findings });
