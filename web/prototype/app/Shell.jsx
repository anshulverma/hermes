function LiveDot({ label }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--text-muted)', fontSize: 12 }}>
      <span aria-hidden="true" style={{ width: 6, height: 6, borderRadius: 'var(--radius-full)', background: 'var(--status-live)', animation: 'fm-pulse 1.6s ease-out infinite' }} />
      {label || 'live'}
    </span>
  );
}

function RunContext({ run, onOpen }) {
  const [hover, setHover] = React.useState(false);
  return (
    <button onClick={onOpen} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      title="Playbook details"
      style={{ display: 'flex', alignItems: 'center', gap: 12, height: 30, padding: '0 10px', fontFamily: 'var(--font-mono)', fontSize: 12,
        background: hover ? 'var(--wash-hover)' : 'transparent', border: '1px solid transparent', borderRadius: 'var(--radius-lg)', cursor: 'pointer' }}>
      <span style={{ color: 'var(--text-secondary)' }}>{run.playbook}</span>
      {(run.context || []).map((c) => (
        <span key={c.label} style={{ display: 'flex', gap: 5 }}>
          <span style={{ color: 'var(--text-muted)' }}>{c.label}</span>
          <span style={{ color: 'var(--text-secondary)' }}>{c.value}</span>
        </span>
      ))}
    </button>
  );
}

function TopBar({ run, view, onView, onStop, onOpenPlaybook }) {
  const { Button, IconButton, Tooltip } = window.DSNS;
  const views = [
    { id: 'overview', label: 'Run' },
    { id: 'metrics', label: 'Metrics' },
    { id: 'board', label: 'Tickets' },
    { id: 'crew', label: 'Crew' },
    { id: 'findings', label: 'Findings' },
    { id: 'activity', label: 'Activity' },
  ];
  return (
    <header style={{
      position: 'sticky', top: 0, zIndex: 40, flex: 'none',
      height: 56, display: 'flex', alignItems: 'center', gap: 24, padding: '0 20px',
      background: 'oklab(0 0 0 / 0.85)', backdropFilter: 'blur(12px)',
      borderBottom: '1px solid var(--border-hairline)',
    }}>
      <span style={{ color: 'var(--text-primary)' }}>Hermes</span>
      <nav style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        {views.map((v) => (
          <button key={v.id} onClick={() => onView(v.id)}
            style={{
              height: 30, padding: '0 10px', background: view === v.id ? 'var(--wash-selected)' : 'transparent',
              border: '1px solid transparent', borderRadius: 'var(--radius-lg)',
              color: view === v.id ? 'var(--text-primary)' : 'var(--text-secondary)',
              font: '400 14px var(--font-sans)', cursor: 'pointer',
            }}>{v.label}</button>
        ))}
      </nav>
      <div style={{ flex: 1 }} />
      <RunContext run={run} onOpen={onOpenPlaybook} />
      <LiveDot />
      <Tooltip label="Re-probe crew" placement="bottom">
        <IconButton label="Re-probe crew"><i data-lucide="activity" style={{ width: 15, height: 15 }} /></IconButton>
      </Tooltip>
      <Button size="sm" onClick={onStop}>Stop run</Button>
    </header>
  );
}

function SectionHead({ title, meta, actions }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12, paddingBottom: 4 }}>
      <h3 style={{ color: 'var(--text-primary)', fontSize: 20, lineHeight: '26px', fontWeight: 400 }}>{title}</h3>
      {meta && <span style={{ color: 'var(--text-muted)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>{meta}</span>}
      <div style={{ flex: 1 }} />
      {actions}
    </div>
  );
}
Object.assign(window, { LiveDot, RunContext, TopBar, SectionHead });
