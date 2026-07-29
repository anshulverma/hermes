function bucketLabel(i, n) {
  const mins = (n - 1 - i) * 5;
  return mins === 0 ? 'now' : mins + 'm ago';
}

function useHover(n) {
  const [i, setI] = React.useState(null);
  const ref = React.useRef(null);
  const onMove = (e) => {
    const r = ref.current.getBoundingClientRect();
    const t = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    setI(Math.round(t * (n - 1)));
  };
  return { i, ref, onMove, onLeave: () => setI(null) };
}

function ChartTip({ index, n, rows }) {
  const left = (index / (n - 1)) * 100;
  return (
    <div style={{
      position: 'absolute', top: 0, left: left + '%', transform: 'translateX(' + (left > 65 ? '-104%' : '4%') + ')',
      pointerEvents: 'none', zIndex: 5, minWidth: 132, padding: '8px 10px',
      background: 'var(--surface-overlay)', backdropFilter: 'blur(var(--blur-overlay))', WebkitBackdropFilter: 'blur(var(--blur-overlay))',
      border: '1px solid var(--border-hairline)', borderRadius: 'var(--radius-lg)',
      fontFamily: 'var(--font-mono)', fontSize: 12, display: 'flex', flexDirection: 'column', gap: 4,
    }}>
      <span style={{ color: 'var(--text-muted)' }}>{bucketLabel(index, n)}</span>
      {rows.map((r) => (
        <span key={r.label} style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-muted)' }}>
            <span aria-hidden="true" style={{ width: 8, height: 2, background: r.color }} />{r.label}
          </span>
          <span style={{ color: 'var(--text-primary)' }}>{r.value}</span>
        </span>
      ))}
    </div>
  );
}

function ChartFrame({ title, meta, legend, height = 160, children }) {
  const { Card } = window.DSNS;
  return (
    <Card padding="md" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <span style={{ color: 'var(--text-primary)', fontSize: 14 }}>{title}</span>
        {meta && <span style={{ color: 'var(--text-muted)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>{meta}</span>}
        <div style={{ flex: 1 }} />
        {legend && <div style={{ display: 'flex', gap: 12 }}>{legend}</div>}
      </div>
      <div style={{ height }}>{children}</div>
    </Card>
  );
}

function Legend({ items }) {
  return (
    <React.Fragment>
      {items.map((i) => (
        <span key={i.label} style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-muted)', fontSize: 12 }}>
          <span aria-hidden="true" style={{ width: 8, height: 2, background: i.color }} />{i.label}
        </span>
      ))}
    </React.Fragment>
  );
}

function YAxis({ max, height, format, ticks = 4 }) {
  const fmt = format || ((v) => (max >= 1000 ? Math.round(v) : Math.round(v * 10) / 10));
  const rows = [];
  for (let i = ticks; i >= 0; i--) rows.push(i / ticks);
  return (
    <div style={{ position: 'relative', width: 44, height, flex: 'none' }}>
      {rows.map((f) => (
        <span key={f} style={{ position: 'absolute', right: 0, top: (1 - f) * height - 8, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 11, lineHeight: '16px' }}>
          {fmt(max * f)}
        </span>
      ))}
    </div>
  );
}

function AxisLabels({ labels, inset = 52 }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6, marginLeft: inset, color: 'var(--text-muted)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>
      {labels.map((l) => <span key={l}>{l}</span>)}
    </div>
  );
}

function LineChart({ series, max, height = 130, labels, format, yFormat, extraRows }) {
  const n = series[0].points.length;
  const h = useHover(n);
  const w = 1000;
  const fmt = format || ((v) => v);
  const path = (pts) => pts.map((v, i) => (i ? 'L' : 'M') + (i / (pts.length - 1)) * w + ' ' + (height - (v / max) * height)).join(' ');
  return (
    <div>
      <div style={{ display: 'flex', gap: 8 }}>
        <YAxis max={max} height={height} format={yFormat} />
        <div ref={h.ref} onMouseMove={h.onMove} onMouseLeave={h.onLeave} style={{ position: 'relative', height, flex: 1, minWidth: 0, cursor: 'crosshair' }}>
        <svg viewBox={'0 0 ' + w + ' ' + height} preserveAspectRatio="none" style={{ width: '100%', height, display: 'block', overflow: 'visible' }}>
          {[0, 0.25, 0.5, 0.75, 1].map((g) => (
            <line key={g} x1="0" x2={w} y1={height * g} y2={height * g} stroke="rgba(255,255,255,0.1)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
          ))}
          {h.i !== null && (
            <line x1={(h.i / (n - 1)) * w} x2={(h.i / (n - 1)) * w} y1="0" y2={height} stroke="rgba(255,255,255,0.5)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
          )}
          {series.map((s) => (
            <path key={s.label} d={path(s.points)} fill="none" stroke={s.color} strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
          ))}
        </svg>
        {h.i !== null && series.map((s) => (
          <span key={s.label} aria-hidden="true" style={{
            position: 'absolute', left: (h.i / (n - 1)) * 100 + '%', top: height - (s.points[h.i] / max) * height,
            width: 5, height: 5, marginLeft: -2.5, marginTop: -2.5, borderRadius: 'var(--radius-full)', background: s.color,
          }} />
        ))}
        {h.i !== null && <ChartTip index={h.i} n={n} rows={series.map((s) => ({ label: s.label, color: s.color, value: fmt(s.points[h.i]) })).concat(extraRows ? extraRows(h.i) : [])} />}
        </div>
      </div>
      {labels && <AxisLabels labels={labels} />}
    </div>
  );
}

function BarChart({ points, max, color, height = 130, labels, overlay, format, yFormat }) {
  const n = points.length;
  const h = useHover(n);
  const fmt = format || ((v) => v);
  return (
    <div>
      <div style={{ display: 'flex', gap: 8 }}>
        <YAxis max={max} height={height} format={yFormat} />
        <div ref={h.ref} onMouseMove={h.onMove} onMouseLeave={h.onLeave} style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height, position: 'relative', flex: 1, minWidth: 0, cursor: 'crosshair' }}>
        {points.map((v, i) => (
          <div key={i} style={{
            flex: 1, height: Math.max(2, (v / max) * height), background: color,
            opacity: h.i === null ? (i === n - 1 ? 1 : 0.55) : (h.i === i ? 1 : 0.3),
            transition: 'opacity var(--motion-fast) var(--ease-default)',
          }} />
        ))}
        {overlay && (
          <svg viewBox="0 0 1000 100" preserveAspectRatio="none" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}>
            <path d={overlay.points.map((v, i) => (i ? 'L' : 'M') + (i / (overlay.points.length - 1)) * 1000 + ' ' + (100 - (v / overlay.max) * 100)).join(' ')}
              fill="none" stroke={overlay.color} strokeWidth="1" strokeDasharray="4 3" vectorEffect="non-scaling-stroke" />
          </svg>
        )}
        {h.i !== null && (
          <ChartTip index={h.i} n={n} rows={[{ label: 'throughput', color: color, value: fmt(points[h.i]) }].concat(
            overlay ? [{ label: 'crew online', color: overlay.color, value: overlay.points[h.i] + ' hosts' }] : []
          )} />
        )}
        </div>
      </div>
      {labels && <AxisLabels labels={labels} />}
    </div>
  );
}

function MetricRow({ children, style }) {
  const [hover, setHover] = React.useState(false);
  return (
    <div onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{ background: hover ? 'var(--wash-hover)' : 'transparent', borderRadius: 'var(--radius-lg)', margin: '0 -8px', padding: '6px 8px', transition: 'background var(--motion-fast) var(--ease-default)', ...style }}>
      {children}
    </div>
  );
}

function MetricsView() {
  const { StatTile, Card, Divider, Tooltip } = window.DSNS;
  const F = window.HERMES;
  const m = F.metrics;
  const L = m.bucket_labels;
  const budgetPct = Math.round((m.gpu_hours_used / m.gpu_hours_budget) * 100);
  const cpuBudgetPct = Math.round((m.cpu_hours_used / m.cpu_hours_budget) * 100);
  const tiles = [
    { label: 'throughput', value: '0.9', delta: 'tickets / min', tone: 'live', live: true, hint: 'Results per minute, last 5m' },
    { label: 'gpu burn', value: m.burn_rate_gpu_h, delta: 'gpu-hours / hour', tone: 'attention', hint: 'Current draw: 14 of 16 gpus held' },
    { label: 'cpu burn', value: m.burn_rate_cpu_h, delta: 'core-hours / hour', hint: 'Current draw: 212 of 400 cores busy' },
    { label: 'error rate', value: '3.0%', delta: m.failed + ' failed of ' + m.results, tone: 'danger', hint: 'Failed over all results' },
    { label: 'retry rate', value: m.retry_rate + '%', delta: 'tickets retried once+', hint: 'Needed a second attempt' },
    { label: 'time to result', value: m.mean_time_to_result, delta: 'median · drain ' + m.drain_eta, hint: 'Median claim to result' },
    { label: 'agent spend', value: '$' + Math.round(m.agent.spend_usd), delta: '$' + m.agent.cost_per_ticket_usd + ' per ticket', tone: 'attention', hint: 'Token spend this run' },
    { label: 'token rate', value: '690k', delta: 'tokens / min', hint: 'Tokens per minute across the crew' },
  ];

  return (
    <div style={{ flex: 1, overflow: 'auto', padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <SectionHead title="Playbook metrics" meta={'run ' + F.run.id + ' · last 2h'} />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 12 }}>
        {tiles.map((t) => (
          <Tooltip key={t.label} label={t.hint} placement="bottom" style={{ minWidth: 0, alignItems: 'stretch' }}>
            <StatTile label={t.label} value={t.value} delta={t.delta} tone={t.tone} live={t.live} style={{ flex: '1 1 auto', minWidth: 0 }} />
          </Tooltip>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.5fr) minmax(0, 1fr)', gap: 16, alignItems: 'start' }}>
        <ChartFrame title="Progress over time" meta="cumulative tickets" height={160}
          legend={<Legend items={[{ label: 'done', color: 'var(--status-ok)' }, { label: 'failed', color: 'var(--status-danger)' }]} />}>
          <LineChart height={130} max={214} labels={L} yFormat={(v) => Math.round(v)}
            series={[{ label: 'done', points: m.done_cum, color: 'var(--status-ok)' }, { label: 'failed', points: m.failed_cum, color: 'var(--status-danger)' }]} />
        </ChartFrame>

        <ChartFrame title="Error rate" meta="% of results failing" height={160}
          legend={<Legend items={[{ label: 'error rate', color: 'var(--status-danger)' }]} />}>
          <LineChart height={130} max={8} labels={L} format={(v) => v + '%'} yFormat={(v) => v + '%'}
            series={[{ label: 'error rate', points: m.error_rate, color: 'var(--status-danger)' }]} />
        </ChartFrame>

        <ChartFrame title="Throughput" meta="tickets / min per 5m bucket" height={160}
          legend={<Legend items={[{ label: 'throughput', color: 'var(--status-live)' }, { label: 'crew online', color: 'var(--text-muted)' }]} />}>
          <BarChart points={m.throughput} max={1.5} color="var(--status-live)" height={130} labels={L} format={(v) => v + ' / min'} yFormat={(v) => Math.round(v * 10) / 10}
            overlay={{ points: m.crew_online, max: 8, color: 'rgba(255,255,255,0.5)' }} />
        </ChartFrame>

        <Card padding="md" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <span style={{ color: 'var(--text-primary)', fontSize: 14 }}>Budget</span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <Tooltip label={budgetPct + '% spent · ' + (m.gpu_hours_budget - m.gpu_hours_used).toFixed(1) + ' gpu-h left'} placement="bottom" style={{ display: 'block' }}>
              <div style={{ width: '100%' }}>
                <ResourceMeter label="gpu-hours" used={m.gpu_hours_used} total={m.gpu_hours_budget} unit="gpu-h" tone="var(--status-attention)" />
              </div>
            </Tooltip>
            <Tooltip label={cpuBudgetPct + '% spent · ' + (m.cpu_hours_budget - m.cpu_hours_used) + ' core-h left'} placement="bottom" style={{ display: 'block' }}>
              <div style={{ width: '100%' }}>
                <ResourceMeter label="cpu core-hours" used={m.cpu_hours_used} total={m.cpu_hours_budget} unit="core-h" tone="var(--status-live)" />
              </div>
            </Tooltip>
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>At {m.burn_rate_gpu_h} gpu-h and {m.burn_rate_cpu_h} core-h per hour, gpu runs out first {'—'} about {Math.round((m.gpu_hours_budget - m.gpu_hours_used) / m.burn_rate_gpu_h)}h.</span>
          </div>
          <Divider />
          <MetricRow>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
              <span style={{ color: 'var(--text-muted)' }}>cost per resolved ticket</span>
              <span style={{ color: 'var(--text-secondary)' }}>{m.cost_per_ticket}</span>
            </div>
          </MetricRow>
        </Card>
      </div>

      <ResourcesSection />

      <AgentUsageSection />

      <Card padding="md" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <span style={{ color: 'var(--text-primary)', fontSize: 14 }}>By phase</span>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr 1fr', gap: 12, color: 'var(--text-muted)', fontSize: 12, fontFamily: 'var(--font-mono)', paddingBottom: 8, borderBottom: '1px solid var(--border-hairline)' }}>
          <span>phase</span><span>tickets</span><span>mean_time</span><span>failure_pct</span><span>gpu_hours</span>
        </div>
        {m.phases.map((p) => (
          <MetricRow key={p.name}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr 1fr', gap: 12, fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
              <span style={{ color: p.name === F.run.phase ? 'var(--status-live)' : 'var(--text-secondary)' }}>{p.name}</span>
              <span>{p.tickets}</span>
              <span>{p.mean}</span>
              <span style={{ color: p.failure_pct > 5 ? 'var(--status-danger)' : 'var(--text-secondary)' }}>{p.failure_pct}%</span>
              <span>{p.gpu_h}</span>
            </div>
          </MetricRow>
        ))}
      </Card>
    </div>
  );
}
Object.assign(window, { bucketLabel, useHover, ChartTip, ChartFrame, Legend, YAxis, AxisLabels, LineChart, BarChart, MetricRow, MetricsView });
