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

/** Event kinds that signal a crew state change. */
export const CREW_EVENT_KINDS: ReadonlySet<string> = Object.freeze(new Set([
  'crew_added', 'crew_health', 'crew_down', 'crew_drained',
]));

/** Event kinds that signal a findings (reduction) state change. */
export const FINDING_EVENT_KINDS: ReadonlySet<string> = Object.freeze(new Set([
  'reduction_created', 'reduction_accepted', 'reduction_rejected',
]));

/**
 * Returns a counter that increments only when a new (not-yet-seen) event
 * whose kind is in `kinds` arrives via `lastEvent`.
 *
 * Pass one of the module-level frozen sets (TICKET_EVENT_KINDS, etc.) so
 * the identity is stable across renders and the effect does not loop.
 */
export function useLiveTick(lastEvent: Event | null, kinds: ReadonlySet<string>): number {
  const [tick, setTick] = useState(0);
  const lastSeenIdRef = useRef<number | null>(null);

  useEffect(() => {
    if (!lastEvent) return;
    if (lastEvent.id === lastSeenIdRef.current) return;
    lastSeenIdRef.current = lastEvent.id;
    if (kinds.has(lastEvent.kind)) {
      setTick((n) => n + 1);
    }
  }, [lastEvent, kinds]);

  return tick;
}
