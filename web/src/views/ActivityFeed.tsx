/**
 * ActivityFeed - event stream view with real events from API.
 * Phase B5: event rows, kind filter.
 * Ported from web/prototype/app/ActivityFeed.jsx with REAL data.
 */

import { useState, useEffect } from 'react';
import { fetchEvents } from '../api/client';
import type { Event } from '../api/client';
import { EmptyState } from '../ds';

type EventRowProps = {
  event: Event;
};

function EventRow({ event }: EventRowProps) {
  // Format timestamp (simple for now)
  const timestamp = new Date(event.ts * 1000).toLocaleTimeString();

  // Determine color/tone by event kind
  const kindColor = event.kind.includes('fail') || event.kind.includes('down')
    ? 'var(--status-danger)'
    : event.kind.includes('done') || event.kind.includes('accept')
    ? 'var(--status-success)'
    : 'var(--text-secondary)';

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'auto 1fr auto auto',
        gap: 12,
        padding: '10px 12px',
        fontSize: 13,
        borderBottom: '1px solid var(--border-hairline)',
        fontFamily: 'var(--font-mono)',
      }}
    >
      <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>{timestamp}</span>
      <span style={{ color: 'var(--text-primary)' }}>{event.message || '—'}</span>
      <span style={{ color: kindColor, fontSize: 11 }}>{event.kind}</span>
      <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>
        {event.ticket_id || event.host || '—'}
      </span>
    </div>
  );
}

export default function ActivityFeed() {
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [kindFilter, setKindFilter] = useState<string>('all');

  // Fetch events
  useEffect(() => {
    setLoading(true);
    setError(null);

    const filters = kindFilter !== 'all' ? { kind: kindFilter } : {};

    fetchEvents(filters)
      .then((data) => {
        setEvents(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [kindFilter]);

  if (loading && events.length === 0) {
    return (
      <div
        style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--text-muted)',
        }}
      >
        Loading events...
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: 32 }}>
        <EmptyState
          title="Error loading events"
          message={error}
          icon="alert-circle"
        />
      </div>
    );
  }

  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      {/* Filter bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '16px 20px',
          borderBottom: '1px solid var(--border-hairline)',
        }}
      >
        <span style={{ color: 'var(--text-primary)', fontSize: 14 }}>Activity Feed</span>
        <div style={{ flex: 1 }} />
        <select
          value={kindFilter}
          onChange={(e) => setKindFilter(e.target.value)}
          style={{
            padding: '6px 10px',
            fontSize: 13,
            color: 'var(--text-primary)',
            background: 'var(--wash-subtle)',
            border: '1px solid var(--border-hairline)',
            borderRadius: 'var(--radius-md)',
          }}
        >
          <option value="all">all events</option>
          <option value="ticket_claimed">ticket_claimed</option>
          <option value="result_recorded">result_recorded</option>
          <option value="phase_advanced">phase_advanced</option>
          <option value="needs_human">needs_human</option>
          <option value="crew_health">crew_health</option>
          <option value="lease_acquired">lease_acquired</option>
        </select>
        <span style={{ color: 'var(--text-muted)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>
          {events.length} shown
        </span>
      </div>

      {/* Events list */}
      <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
        {events.length === 0 ? (
          <div style={{ padding: 32 }}>
            <EmptyState
              title="No events yet"
              message="Events will appear here as the run progresses."
              icon="inbox"
            />
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {events.map((event) => (
              <EventRow key={event.id} event={event} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
