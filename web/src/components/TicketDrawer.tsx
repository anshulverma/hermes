/**
 * TicketDrawer - minimal drawer showing board-level ticket fields.
 * Phase B2: board-level fields only (id/state/phase/subject/resource/host/attempts/priority).
 * Phase B3: full detail (envelope/result/attempt timeline).
 */

import type { Ticket } from '../api/client';
import { Drawer, StatusPill, Badge } from '../ds';
import { normalizeTicketState } from '../api/normalize';

type TicketDrawerProps = {
  isOpen: boolean;
  ticket: Ticket | null;
  onClose: () => void;
};

export default function TicketDrawer({ isOpen, ticket, onClose }: TicketDrawerProps) {
  if (!ticket) {
    return null;
  }

  const uiState = normalizeTicketState(ticket.state);

  return (
    <Drawer isOpen={isOpen} onClose={onClose} title={ticket.id} width="480px">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20, padding: '20px 24px' }}>
        {/* State and phase */}
        <div style={{ display: 'flex', gap: 10 }}>
          <StatusPill state={uiState} size="md" />
          <Badge variant="outline" tone="ok">
            {ticket.phase}
          </Badge>
        </div>

        {/* Subject */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>Subject</span>
          <span style={{ color: 'var(--text-primary)', fontSize: 14 }}>
            {ticket.subject}
          </span>
        </div>

        {/* Resource */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>Resource</span>
          <Badge
            variant="subtle"
            tone={ticket.resource_req === 'gpu' ? 'attention' : undefined}
          >
            {ticket.resource_req}
          </Badge>
        </div>

        {/* Host */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>Assigned Host</span>
          <span
            style={{
              color: ticket.host ? 'var(--text-secondary)' : 'var(--text-muted)',
              fontSize: 13,
              fontFamily: 'var(--font-mono)',
            }}
          >
            {ticket.host || '—'}
          </span>
        </div>

        {/* Attempts and Priority */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>Attempts</span>
            <span
              style={{
                color: 'var(--text-primary)',
                fontSize: 18,
                fontFamily: 'var(--font-mono)',
              }}
            >
              {ticket.attempts}
            </span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>Priority</span>
            <span
              style={{
                color: 'var(--text-primary)',
                fontSize: 18,
                fontFamily: 'var(--font-mono)',
              }}
            >
              {ticket.priority}
            </span>
          </div>
        </div>

        {/* Elapsed */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>Elapsed</span>
          <span
            style={{
              color: 'var(--text-secondary)',
              fontSize: 13,
              fontFamily: 'var(--font-mono)',
            }}
          >
            {ticket.elapsed_s}s
          </span>
        </div>

        {/* Phase B3 seam: full detail (envelope/result/attempts) goes here */}
      </div>
    </Drawer>
  );
}
