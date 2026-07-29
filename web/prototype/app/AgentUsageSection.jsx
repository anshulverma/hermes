function AgentUsageSection() {
  const { Card, Divider, Tooltip } = window.DSNS;
  const F = window.HERMES;
  const a = F.metrics.agent;
  const L = F.metrics.bucket_labels;
  const [split, setSplit] = React.useState('models');
  const spendPct = Math.round((a.spend_usd / a.budget_usd) * 100);
  const money = (v) => '$' + v.toFixed(2);
  const rows = split === 'models' ? a.models : a.by_phase;
  // Cumulative tokens per bucket, so spend and tokens read off the same line.
  const tokensCum = a.tokens.reduce((acc, v) => acc.concat([(acc.length ? acc[acc.length - 1] : 0) + v]), []);

  const tab = (id, label) => (
    <button onClick={() => setSplit(id)}
      style={{ height: 26, padding: '0 10px', background: split === id ? 'var(--wash-selected)' : 'transparent', border: 'none', borderRadius: 'var(--radius-lg)',
        color: split === id ? 'var(--text-primary)' : 'var(--text-muted)', font: '400 12px var(--font-sans)', cursor: 'pointer' }}>{label}</button>
  );

  const figure = (label, value, sub, hint) => (
    <Tooltip label={hint} placement="bottom" style={{ display: 'block', minWidth: 0 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0, width: '100%' }}>
        <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>{label}</span>
        <span style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: 20, lineHeight: '26px' }}>{value}</span>
        <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>{sub}</span>
      </div>
    </Tooltip>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <SectionHead title="Agent usage" meta="tokens and spend" />

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.5fr) minmax(0, 1fr)', gap: 16, alignItems: 'start' }}>
        <ChartFrame title="Token throughput" meta="millions of tokens per 5m bucket" height={160}
          legend={<Legend items={[{ label: 'tokens', color: 'var(--status-live)' }]} />}>
          <BarChart points={a.tokens} max={4} color="var(--status-live)" height={130} labels={L} format={(v) => v + 'M tokens'} yFormat={(v) => (Math.round(v * 10) / 10) + 'M'} />
        </ChartFrame>

        <ChartFrame title="Spend" meta={'cumulative · $' + Math.round(a.spend_cum[a.spend_cum.length - 1]) + ' · ' + (Math.round(tokensCum[tokensCum.length - 1] * 10) / 10) + 'M tokens'} height={160}
          legend={<Legend items={[{ label: 'spend', color: 'var(--status-attention)' }]} />}>
          <LineChart height={130} max={450} labels={L} format={(v) => '$' + v} yFormat={(v) => '$' + Math.round(v)}
            extraRows={(i) => [{ label: 'tokens', color: 'rgba(255,255,255,0.5)', value: (Math.round(tokensCum[i] * 10) / 10) + 'M' }]}
            series={[{ label: 'spend', points: a.spend_cum, color: 'var(--status-attention)' }]} />
        </ChartFrame>
      </div>

      <Card padding="md" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 16 }}>
          {figure('tokens in', '61.4M', 'prompt tokens', 'Prompt tokens sent to agents this run')}
          {figure('tokens out', '8.9M', 'completion tokens', 'Completion tokens returned by agents')}
          {figure('cache reads', '214.3M', '3.5x reuse of context', 'Cached prompt tokens read back, billed at the cache rate')}
          {figure('rate', '690k', 'tokens / min', 'Tokens per minute across the crew')}
        </div>
        <Divider />
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: 24, alignItems: 'center' }}>
          <ResourceMeter label="spend" used={a.spend_usd} total={a.budget_usd} unit="usd" tone="var(--status-attention)" />
          <div style={{ display: 'flex', gap: 24 }}>
            {figure('per resolved ticket', money(a.cost_per_ticket_usd), F.metrics.results + ' results', 'Run spend divided by results recorded')}
            {figure('per finding', money(a.cost_per_finding_usd), '3 unique findings', 'Run spend divided by deduped findings')}
          </div>
        </div>
        <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>{spendPct}% of the run budget spent. At the current rate the run finishes near {money(a.spend_usd * 1.6)}.</span>
      </Card>

      <Card padding="md" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ color: 'var(--text-primary)', fontSize: 14 }}>Spend split</span>
          <div style={{ flex: 1 }} />
          <div style={{ display: 'flex', gap: 2, padding: 2, border: '1px solid var(--border-hairline)', borderRadius: 'var(--radius-lg)' }}>{tab('models', 'By model')}{tab('phases', 'By phase')}</div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr 1fr 1.4fr', gap: 12, color: 'var(--text-muted)', fontSize: 12, fontFamily: 'var(--font-mono)', paddingBottom: 8, borderBottom: '1px solid var(--border-hairline)' }}>
          <span>{split === 'models' ? 'model' : 'phase'}</span><span>tokens</span><span>spend_usd</span><span>{split === 'models' ? 'role' : 'usd_per_ticket'}</span>
        </div>
        {rows.map((r) => (
          <MetricRow key={r.name}>
            <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr 1fr 1.4fr', gap: 12, alignItems: 'center', fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
              <span style={{ color: 'var(--text-primary)' }}>{r.name}</span>
              <span>{r.tokens}</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                {money(r.spend)}
                <span style={{ flex: 1, maxWidth: 70, height: 4, background: 'var(--wash-hover)', borderRadius: 'var(--radius-full)', overflow: 'hidden' }}>
                  <span style={{ display: 'block', width: Math.round((r.spend / a.spend_usd) * 100) + '%', height: '100%', background: 'var(--status-attention)' }} />
                </span>
              </span>
              <span style={{ color: 'var(--text-muted)' }}>{split === 'models' ? r.role : money(r.per_ticket)}</span>
            </div>
          </MetricRow>
        ))}
      </Card>
    </div>
  );
}
Object.assign(window, { AgentUsageSection });
