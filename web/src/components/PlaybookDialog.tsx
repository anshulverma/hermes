/**
 * PlaybookDialog - displays playbook info and run context.
 * Ported from web/prototype/app/HermesApp.jsx PlaybookDialog.
 */

import type { RunDetail } from '../api/client';
import { deriveContext, PLAYBOOK_CONTENT } from '../api/normalize';
import { Dialog, Button, StatusPill } from '../ds';

type PlaybookDialogProps = {
  open: boolean;
  run: RunDetail | null;
  onClose: () => void;
};

export default function PlaybookDialog({ open, run, onClose }: PlaybookDialogProps) {
  if (!open || !run) return null;

  const playbookInfo = PLAYBOOK_CONTENT[run.playbook];
  if (!playbookInfo) return null;

  const context = deriveContext(run);

  const row = (label: string, value: React.ReactNode) => (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '96px minmax(0, 1fr)',
        gap: 12,
        padding: '8px 0',
      }}
    >
      <span
        style={{
          color: 'var(--text-muted)',
          fontSize: 12,
          fontFamily: 'var(--font-mono)',
        }}
      >
        {label}
      </span>
      <span style={{ color: 'var(--text-secondary)', fontSize: 14 }}>{value}</span>
    </div>
  );

  const Divider = () => (
    <div style={{ borderBottom: '1px solid var(--border-hairline)' }} />
  );

  return (
    <Dialog
      isOpen={open}
      title={playbookInfo.name + ' playbook'}
      description={playbookInfo.summary}
      width={560}
      onClose={onClose}
      footer={
        <Button size="sm" onClick={onClose}>
          Close
        </Button>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <Divider />
        {row(
          'run',
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
            }}
          >
            {run.id}
            <StatusPill state={run.state} size="sm" />
          </span>
        )}
        <Divider />
        {row(
          'site',
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>
            {run.site}
            <span style={{ color: 'var(--text-muted)' }}>
              {' '}
              · environment and tools the crew runs in
            </span>
          </span>
        )}
        <Divider />
        {row(
          'context',
          <span style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {context.map((c) => (
              <span
                key={c.label}
                style={{
                  display: 'flex',
                  gap: 6,
                  padding: '4px 10px',
                  border: '1px solid var(--border-hairline)',
                  borderRadius: 'var(--radius-lg)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 12,
                }}
              >
                <span style={{ color: 'var(--text-muted)' }}>{c.label}</span>
                <span style={{ color: 'var(--text-secondary)' }}>{c.value}</span>
              </span>
            ))}
          </span>
        )}
        {row(
          '',
          <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
            {playbookInfo.context_note}
          </span>
        )}
        <Divider />
        {row(
          'phases',
          <span
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: 8,
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
            }}
          >
            {run.phases.map((p) => (
              <span
                key={p.name}
                style={{
                  color: p.current ? 'var(--status-live)' : 'var(--text-secondary)',
                }}
              >
                {p.name}
              </span>
            ))}
          </span>
        )}
        <Divider />
        {row('stops at', playbookInfo.stops_at)}
      </div>
    </Dialog>
  );
}
