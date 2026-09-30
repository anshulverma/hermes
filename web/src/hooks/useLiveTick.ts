/**
 * useLiveTick - derive a refetch counter from the shared event stream.
 * Increments only when a not-yet-seen event whose kind is in the provided set arrives.
 * Idempotent: repeated delivery of the same event id never double-increments.
 */

import { useState, useEffect, useRef } from 'react';
import type { Event } from '../api/client';

/** Event kinds that signal a ticket state change. */
export const TICKET_EVENT_KINDS: ReadonlySet<string> = Object.freeze(new Set([
  'ticket_claimed', 'ticket_started', 'result_recorded', 'ticket_requeued',
  'ticket_parked', 'ticket_failed', 'ticket_abandoned', 'ticket_reprioritized',
  'needs_human', 'attention', 'phase_advanced', 'lease_acquired', 'lease_reclaimed',
]));

/**
 * Event kinds that signal a crew state change: a host's own state, or a ticket
 * landing on or leaving a host. The ticket kinds tick the board too, on purpose.
 */
export const CREW_EVENT_KINDS: ReadonlySet<string> = Object.freeze(new Set([
  'crew_added', 'crew_health', 'crew_down', 'crew_drained',
  'ticket_claimed', 'result_recorded', 'ticket_requeued', 'ticket_parked',
  'ticket_failed', 'ticket_abandoned',
]));

/** Event kinds that signal a findings (reduction) state change. */
export const FINDING_EVENT_KINDS: ReadonlySet<string> = Object.freeze(new Set([
  'reduction_created', 'reduction_accepted', 'reduction_rejected',
]));

/**
 * Returns a counter that increments when the stream brings events whose kind
 * is in `kinds` and, when `runId` is given (not null), whose run_id is that
 * run. Reads `events` with a cursor: it starts at the newest event buffered at
 * mount (the caller's own fetch covers older ones) and handles every later
 * event once, in id order, so a burst React batches into one render is never
 * cut to its last event.
 *
 * Pass one of the module-level frozen sets (TICKET_EVENT_KINDS, etc.) so
 * the identity is stable across renders.
 */
export function useLiveTick(
  events: Event[],
  kinds: ReadonlySet<string>,
  runId?: string | null,
): number {
  const [tick, setTick] = useState(0);
  const cursorRef = useRef(events.at(-1)?.id ?? 0);

  useEffect(() => {
    let hit = false;
    for (const e of events) {
      if (e.id <= cursorRef.current) continue;
      cursorRef.current = e.id;
      if (kinds.has(e.kind) && (runId == null || e.run_id === runId)) hit = true;
    }
    if (hit) setTick((n) => n + 1);
  }, [events, kinds, runId]);

  return tick;
}
