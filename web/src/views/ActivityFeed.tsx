/**
 * ActivityFeed - every event in the home, newest first.
 *
 * The first page is the newest 200 events matching the route's run / kind
 * filters (`#/activity?run=&kind=`). "Load older" pages back from the smallest
 * id shown until a short page puts 'Start of history' in its place (`hermes db
 * prune` deletes old events). Live events come from the app's one event stream,
 * passed in as `streamEvents`, never a second WebSocket: every buffered event
 * newer than this view's cursor is handled once, in id order, and prepended
 * when it matches the filters.
 */

import { useState, useEffect, useLayoutEffect, useRef } from 'react';
import { fetchEvents, fetchEventKinds } from '../api/client';
import type { Event } from '../api/client';
import { buildRoute, useRoute } from '../hooks/useRoute';
import { EmptyState, Button } from '../ds';
import { LoadingOverlay } from '../components/Spinner';

const PAGE = 200;
/** Live prepends never grow the list past this; "Load older" may, the user asked for it. */
const CAP = 1000;
/** The controls focus can be handed to; a number is an event row. */
const FOCUS_TARGET = {
  start: '[data-start-of-history]',
  older: '[data-load-older]',
  retry: '[role="alert"] button',
};

type ActivityFeedProps = {
  runFilter: string | null;
  kindFilter: string | null;
  /** The buffered events of the app's one event stream, oldest first. */
  streamEvents: Event[];
};

/** The rows on screen, newest first, and whether "Load older" is offered. */
type List = { rows: Event[]; more: boolean };

/** Union by id, newest first: a live event that is also in a fetched page shows once. */
function mergeById(a: Event[], b: Event[]): Event[] {
  const byId = new Map<number, Event>();
  for (const e of [...a, ...b]) byId.set(e.id, e);
  return [...byId.values()].sort((x, y) => y.id - x.id);
}

function EventRow({ event }: { event: Event }) {
  const timestamp = new Date(event.ts * 1000).toLocaleTimeString();

  // Determine color/tone by event kind
  const kindColor = event.kind.includes('fail') || event.kind.includes('down')
    ? 'var(--status-danger)'
    : event.kind.includes('done') || event.kind.includes('accept')
    ? 'var(--status-ok)'
    : 'var(--text-secondary)';

  // Focusable (tabIndex -1) so 'Start of history' can hand focus to the first row a page added.
  return (
    <div
      data-event-id={event.id}
      tabIndex={-1}
      style={{
        display: 'grid',
        gridTemplateColumns: 'auto auto 1fr auto auto',
        gap: 12,
        padding: '10px 12px',
        fontSize: 13,
        borderBottom: '1px solid var(--border-hairline)',
        fontFamily: 'var(--font-mono)',
      }}
    >
      <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>{timestamp}</span>
      {/* Crew events carry no run. */}
      <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>
        {event.run_id ? (
          <a href={buildRoute({ page: 'run', runId: event.run_id, tab: 'summary', ticket: null })}>
            {event.run_id}
          </a>
        ) : (
          '—'
        )}
      </span>
      <span style={{ color: 'var(--text-primary)' }}>{event.message || '—'}</span>
      <span style={{ color: kindColor, fontSize: 11 }}>{event.kind}</span>
      <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>
        {event.ticket_id || event.host || '—'}
      </span>
    </div>
  );
}

export default function ActivityFeed({ runFilter, kindFilter, streamEvents }: ActivityFeedProps) {
  const { navigate } = useRoute();
  const [list, setList] = useState<List>({ rows: [], more: false });
  const [loading, setLoading] = useState(true);
  const [loadingOlder, setLoadingOlder] = useState(false);
  // `older` says which request failed, so Retry repeats that one.
  const [error, setError] = useState<{ message: string; older: boolean } | null>(null);
  const [reload, setReload] = useState(0);
  const [availableKinds, setAvailableKinds] = useState<string[]>([]);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  // Cursor over the shared stream. It starts at the newest event buffered at
  // mount, which the first page already covers, so nothing buffered is replayed.
  const cursor = useRef(streamEvents.at(-1)?.id ?? 0);
  // Bumped on every first-page load, so a page answering an older filter is dropped.
  const generation = useRef(0);
  // Where focus goes when the focused control is replaced: the first row a short
  // page added or 'Start of history', the alert's Retry after a failed "Load
  // older", and "Load older" after that Retry. Never <body>.
  const focusNext = useRef<number | keyof typeof FOCUS_TARGET | null>(null);

  useEffect(() => {
    fetchEventKinds()
      .then(setAvailableKinds)
      .catch((err) => {
        console.error('Failed to fetch event kinds:', err);
      });
  }, []);

  // The first page. A filter change discards the loaded pages and starts again.
  useEffect(() => {
    const gen = ++generation.current;
    setList({ rows: [], more: false });
    setLoading(true);
    setLoadingOlder(false);
    setError(null);
    fetchEvents({ order: 'desc', limit: PAGE, run: runFilter ?? undefined, kind: kindFilter ?? undefined })
      .then((page) => {
        if (gen !== generation.current) return;
        // Merge, not replace: live events that arrived during the fetch stay.
        setList((prev) => ({ rows: mergeById(prev.rows, page), more: page.length === PAGE }));
        setLoading(false);
      })
      .catch((err) => {
        if (gen !== generation.current) return;
        setError({ message: err.message, older: false });
        setLoading(false);
      });
  }, [runFilter, kindFilter, reload]);

  // Live events: every buffered event past the cursor, once, in id order, so no
  // event of a burst delivered in one render is lost.
  useEffect(() => {
    const fresh = streamEvents.filter((e) => e.id > cursor.current);
    if (fresh.length === 0) return;
    cursor.current = fresh[fresh.length - 1].id;
    const matched = fresh.filter(
      (e) =>
        (runFilter === null || e.run_id === runFilter) &&
        (kindFilter === null || e.kind === kindFilter),
    );
    if (matched.length === 0) return;
    setList((prev) => {
      const rows = mergeById(matched, prev.rows);
      // Only live prepends are capped, and never below what "Load older" loaded past
      // CAP: the oldest rows go, and "Load older" comes back for them.
      const cap = Math.max(CAP, prev.rows.length);
      return rows.length > cap ? { rows: rows.slice(0, cap), more: true } : { rows, more: prev.more };
    });
  }, [streamEvents, runFilter, kindFilter]);

  // A layout effect: focus moves in the same commit that replaced the focused
  // control, so it is never seen on <body>.
  useLayoutEffect(() => {
    const next = focusNext.current;
    if (next === null) return;
    focusNext.current = null;
    const target = typeof next === 'number' ? `[data-event-id="${next}"]` : FOCUS_TARGET[next];
    listRef.current?.querySelector<HTMLElement>(target)?.focus();
  }, [list, error, loadingOlder]);

  const loadOlder = () => {
    // "Load older" stays focusable while it loads (a disabled button drops focus
    // to <body>), so a second press lands here and asks nothing more.
    if (loadingOlder) return;
    const gen = generation.current;
    // Rows are newest first, so the last one has the smallest id shown.
    const before = list.rows[list.rows.length - 1].id;
    setLoadingOlder(true);
    setError(null);
    fetchEvents({
      order: 'desc',
      limit: PAGE,
      run: runFilter ?? undefined,
      kind: kindFilter ?? undefined,
      before,
    })
      .then((page) => {
        if (gen !== generation.current) return;
        setList((prev) => {
          // Live events trimmed the oldest rows while it loaded: the page no longer
          // joins the list, so it is dropped, and "Load older" (back with the trim)
          // asks again from the new smallest id.
          if (prev.rows.at(-1)?.id !== before) return prev;
          // A short page ends the history: focus its first row, or the marker when it is empty.
          if (page.length < PAGE) focusNext.current = page.length > 0 ? page[0].id : 'start';
          // Always appended, even past CAP.
          return { rows: mergeById(prev.rows, page), more: page.length === PAGE };
        });
        setLoadingOlder(false);
      })
      .catch((err) => {
        if (gen !== generation.current) return;
        focusNext.current = 'retry';
        setError({ message: err.message, older: true });
        setLoadingOlder(false);
      });
  };

  // Retry takes the alert away: focus goes to what replaces it.
  const retry = () => {
    if (error?.older) {
      focusNext.current = 'older';
      loadOlder();
    } else {
      headingRef.current?.focus();
      setReload((n) => n + 1);
    }
  };

  const setFilters = (run: string | null, kind: string | null) =>
    navigate({ page: 'activity', run, kind });
  const { rows, more } = list;

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
        <h1
          ref={headingRef}
          tabIndex={-1}
          style={{ margin: 0, fontSize: 14, fontWeight: 'normal', color: 'var(--text-primary)' }}
        >
          Activity
        </h1>
        {runFilter && (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '2px 4px 2px 10px',
              fontSize: 12,
              fontFamily: 'var(--font-mono)',
              color: 'var(--text-primary)',
              background: 'var(--wash-subtle)',
              border: '1px solid var(--border-hairline)',
              borderRadius: 'var(--radius-md)',
            }}
          >
            <span>run {runFilter}</span>
            <button
              type="button"
              aria-label={`Remove run filter ${runFilter}`}
              onClick={() => {
                setFilters(null, kindFilter);
                // The chip is about to go: focus the page heading, not <body>.
                headingRef.current?.focus();
              }}
              style={{
                border: 'none',
                background: 'none',
                color: 'var(--text-muted)',
                cursor: 'pointer',
                padding: '0 4px',
              }}
            >
              ×
            </button>
          </span>
        )}
        <div style={{ flex: 1 }} />
        <select
          aria-label="Event kind"
          value={kindFilter ?? 'all'}
          onChange={(e) => setFilters(runFilter, e.target.value === 'all' ? null : e.target.value)}
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
          {availableKinds.map((kind) => (
            <option key={kind} value={kind}>
              {kind}
            </option>
          ))}
        </select>
        <span style={{ color: 'var(--text-muted)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>
          {rows.length} shown
        </span>
      </div>

      {/* Events list. Rows are keyed by id and the list keeps the browser's
          default overflow-anchor, so a prepend never moves what is on screen. */}
      <div ref={listRef} style={{ position: 'relative', flex: 1, minHeight: 0, overflow: 'auto' }}>
        {loading ? (
          <LoadingOverlay label="Loading events…" />
        ) : rows.length === 0 && !error ? (
          <div style={{ padding: 32 }}>
            <EmptyState title="No events yet." icon="inbox" />
          </div>
        ) : (
          <>
            {rows.map((event) => (
              <EventRow key={event.id} event={event} />
            ))}
            {error ? (
              <div
                role="alert"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '12px 20px',
                  fontSize: 13,
                  color: 'var(--status-danger)',
                }}
              >
                <span>Could not load events: {error.message}</span>
                <Button size="sm" onClick={retry}>
                  Retry
                </Button>
              </div>
            ) : more ? (
              <div style={{ padding: 12, textAlign: 'center' }}>
                <Button
                  size="sm"
                  data-load-older
                  aria-disabled={loadingOlder}
                  onClick={loadOlder}
                  style={loadingOlder ? { opacity: 0.35, cursor: 'default' } : undefined}
                >
                  Load older
                </Button>
              </div>
            ) : (
              <p
                data-start-of-history
                tabIndex={-1}
                style={{
                  margin: 0,
                  padding: 12,
                  textAlign: 'center',
                  fontSize: 12,
                  color: 'var(--text-muted)',
                }}
              >
                Start of history
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
