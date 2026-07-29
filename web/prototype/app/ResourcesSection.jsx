function ResourceMeter({ label, used, total, unit, pct, tone }) {
  const p = pct !== undefined ? pct : Math.round((used / total) * 100);
  const hue = tone || (p >= 90 ? 'var(--status-danger)' : p >= 70 ? 'var(--status-attention)' : 'var(--status-ok)');
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
        <span style={{ color: 'var(--text-muted)' }}>{label}</span>
        <span style={{ color: 'var(--text-secondary)' }}>{used} / {total} {unit} <span style={{ color: 'var(--text-muted)' }}>{p}%</span></span>
      </div>
      <div style={{ height: 6, background: 'var(--wash-hover)', borderRadius: 'var(--radius-full)', overflow: 'hidden' }}>
        <div style={{ width: p + '%', height: '100%', background: hue, transition: 'width var(--motion-base) var(--ease-default)' }} />
      </div>
    </div>
  );
}

function ResourceTimeline({ points, total, color, unit, height = 110 }) {
  const n = points.length;
  const h = useHover(n);
  const w = 1000;
  const y = (v) => height - (v / total) * height;
  const line = points.map((v, i) => (i ? 'L' : 'M') + (i / (n - 1)) * w + ' ' + y(v)).join(' ');
  const area = line + ' L' + w + ' ' + height + ' L0 ' + height + ' Z';
  return (
    <div style={{ display: 'flex', gap: 8 }}>
      <YAxis max={total} height={height} />
      <div ref={h.ref} onMouseMove={h.onMove} onMouseLeave={h.onLeave} style={{ position: 'relative', height, flex: 1, minWidth: 0, cursor: 'crosshair' }}>
      <svg viewBox={'0 0 ' + w + ' ' + height} preserveAspectRatio="none" style={{ width: '100%', height, display: 'block', overflow: 'visible' }}>
        <line x1="0" x2={w} y1="0" y2="0" stroke="rgba(255,255,255,0.5)" strokeWidth="1" strokeDasharray="4 3" vectorEffect="non-scaling-stroke" />
        {[0.25, 0.5, 0.75, 1].map((g) => (
          <line key={g} x1="0" x2={w} y1={height * g} y2={height * g} stroke="rgba(255,255,255,0.1)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
        ))}
        <path d={area} fill={color} opacity="0.12" />
        <path d={line} fill="none" stroke={color} strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
        {h.i !== null && <line x1={(h.i / (n - 1)) * w} x2={(h.i / (n - 1)) * w} y1="0" y2={height} stroke="rgba(255,255,255,0.5)" strokeWidth="1" vectorEffect="non-scaling-stroke" />}
      </svg>
      <span aria-hidden="true" style={{ position: 'absolute', top: -8, right: 0, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>capacity</span>
      {h.i !== null && (
        <React.Fragment>
          <span aria-hidden="true" style={{ position: 'absolute', left: (h.i / (n - 1)) * 100 + '%', top: y(points[h.i]), width: 5, height: 5, marginLeft: -2.5, marginTop: -2.5, borderRadius: 'var(--radius-full)', background: color }} />
          <ChartTip index={h.i} n={n} rows={[
            { label: 'used', color: color, value: points[h.i] + ' ' + unit },
            { label: 'free', color: 'rgba(255,255,255,0.5)', value: (total - points[h.i]).toFixed(0) + ' ' + unit },
          ]} />
        </React.Fragment>
      )}
      </div>
    </div>
  );
}

function HostFilter({ crew, selected, onToggle, onAll }) {
  const { TICKET_STATES, TONES } = window.DSNS;
  const dotOf = (st) => {
    const tone = (TICKET_STATES[st] || {}).tone || 'neutral';
    return tone === 'neutral' ? 'rgba(255,255,255,0.4)' : TONES[tone].fg;
  };
  const all = selected.length === 0;
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6 }}>
      <span style={{ color: 'var(--text-muted)', fontSize: 12, marginRight: 2 }}>hosts</span>
      <button onClick={onAll}
        style={{ height: 24, padding: '0 10px', background: all ? 'var(--wash-selected)' : 'transparent', border: '1px solid var(--border-hairline)', borderRadius: 'var(--radius-lg)',
          color: all ? 'var(--text-primary)' : 'var(--text-muted)', font: '400 12px var(--font-mono)', cursor: 'pointer' }}>all</button>
      {crew.map((m) => {
        const on = selected.indexOf(m.id) !== -1;
        return (
          <button key={m.id} onClick={() => onToggle(m.id)}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 24, padding: '0 8px',
              background: on ? 'var(--wash-selected)' : 'transparent',
              border: '1px solid ' + (on ? 'var(--border-control)' : 'var(--border-hairline)'), borderRadius: 'var(--radius-lg)',
              color: on ? 'var(--text-primary)' : 'var(--text-muted)', font: '400 12px var(--font-mono)', cursor: 'pointer',
              transition: 'border-color var(--motion-fast) var(--ease-default), background var(--motion-base) var(--ease-default)' }}>
            <span aria-hidden="true" title={m.state} style={{ width: 6, height: 6, borderRadius: 'var(--radius-full)', background: dotOf(m.state), flex: 'none' }} />
            {m.id}
          </button>
        );
      })}
    </div>
  );
}

function ResourcesSection() {
  const F = window.HERMES;
  const r = F.metrics.resources;
  const [mode, setMode] = React.useState('timeline');
  const [selected, setSelected] = React.useState([]);
  const L = F.metrics.bucket_labels;
  const capOf = (m, key) => (key === 'mem' ? m.mem_gb : (m.resources[key] || 0));
  const shownCrew = selected.length ? F.crew.filter((m) => selected.indexOf(m.id) !== -1) : F.crew;

  // Per-host series are the fleet series split by each host's share of live load
  // (capacity x utilization), so selecting every host reproduces the fleet line.
  const sliceFor = (key) => {
    const weight = (m) => capOf(m, key) * (m.util[key] / 100);
    const totalW = F.crew.reduce((s, m) => s + weight(m), 0) || 1;
    const share = shownCrew.reduce((s, m) => s + weight(m), 0) / totalW;
    return {
      points: r.series[key].map((v) => Math.round(v * share * 10) / 10),
      total: shownCrew.reduce((s, m) => s + capOf(m, key), 0),
    };
  };

  const specs = [
    { key: 'cpu', label: 'cpu', color: 'var(--status-live)', d: r.cpu },
    { key: 'gpu', label: 'gpu', color: 'var(--status-attention)', d: r.gpu },
    { key: 'mem', label: 'memory', color: 'var(--status-ok)', d: r.mem },
  ].map((s) => {
    const sl = sliceFor(s.key);
    return Object.assign({}, s, { points: sl.points, total: sl.total, used: sl.points[sl.points.length - 1] });
  });
  const tab = (id, label) => (
    <button onClick={() => setMode(id)}
      style={{ height: 26, padding: '0 10px', background: mode === id ? 'var(--wash-selected)' : 'transparent', border: 'none', borderRadius: 'var(--radius-lg)',
        color: mode === id ? 'var(--text-primary)' : 'var(--text-muted)', font: '400 12px var(--font-sans)', cursor: 'pointer' }}>{label}</button>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <SectionHead title="System resources" meta={selected.length ? selected.length + ' of ' + F.crew.length + ' hosts' : 'fleet-wide'}
        actions={<div style={{ display: 'flex', gap: 2, padding: 2, border: '1px solid var(--border-hairline)', borderRadius: 'var(--radius-lg)' }}>{tab('timeline', 'Timeline')}{tab('hosts', 'By host')}</div>} />

      <HostFilter crew={F.crew} selected={selected}
        onToggle={(id) => setSelected((s) => (s.indexOf(id) !== -1 ? s.filter((x) => x !== id) : s.concat([id])))}
        onAll={() => setSelected([])} />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 16 }}>
        {specs.map((s) => (
          <ChartFrame key={s.key} title={s.label} meta={s.used + ' of ' + s.total + ' ' + s.d.unit + ' used'} height={150}
            legend={<Legend items={[{ label: 'used', color: s.color }, { label: 'capacity', color: 'rgba(255,255,255,0.5)' }]} />}>
            {mode === 'timeline' ? (
              s.total ? (
                <div>
                  <ResourceTimeline points={s.points} total={s.total} color={s.color} unit={s.d.unit} height={110} />
                  <AxisLabels labels={L} />
                </div>
              ) : (
                <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 12, border: '1px dashed var(--border-hairline)', borderRadius: 'var(--radius-lg)' }}>
                  No {s.label} on the selected hosts
                </div>
              )
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, overflow: 'auto', height: '100%' }}>
                {shownCrew.map((m) => (
                  <ResourceMeter key={m.id} label={m.id} pct={m.util[s.key]} tone={s.color}
                    used={Math.round((m.util[s.key] / 100) * capOf(m, s.key))}
                    total={capOf(m, s.key)} unit={s.d.unit} />
                ))}
              </div>
            )}
          </ChartFrame>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 16 }}>
        {specs.map((s) => (
          <ResourceMeter key={s.key} label={s.label + ' now'} used={s.used} total={s.total} unit={s.d.unit} />
        ))}
      </div>
    </div>
  );
}
Object.assign(window, { ResourceMeter, ResourceTimeline, HostFilter, ResourcesSection });
