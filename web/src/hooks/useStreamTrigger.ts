/**
 * useStreamTrigger - call `onTrigger` when the shared event stream brings an
 * event that `match` accepts, throttled leading + always trailing.
 *
 * Cursor: starts at the newest event buffered at mount (the caller's own mount
 * fetch covers older ones) and handles each later event once, in id order, so
 * a burst React batches into one render still triggers when any of it matches.
 *
 * Throttle: the first trigger calls `onTrigger` at once and opens a `windowMs`
 * window; one trailing call always runs when the window ends, even with no
 * second trigger, so a change committed with no event of its own is still
 * picked up. A trigger after the window has closed starts a new cycle, so
 * N >= 1 triggers in one window give exactly two calls. Each instance has its
 * own window.
 */

import { useEffect, useRef } from 'react';
import type { Event } from '../api/client';

export function useStreamTrigger(
  events: Event[],
  match: (e: Event) => boolean,
  onTrigger: () => void,
  windowMs = 2000,
): void {
  const cursorRef = useRef(events.at(-1)?.id ?? 0);
  const timerRef = useRef<number | null>(null);
  // The latest callbacks, so the trailing call made after a re-render uses them.
  const matchRef = useRef(match);
  const onTriggerRef = useRef(onTrigger);
  useEffect(() => {
    matchRef.current = match;
    onTriggerRef.current = onTrigger;
  });

  useEffect(() => {
    let hit = false;
    for (const e of events) {
      if (e.id <= cursorRef.current) continue;
      cursorRef.current = e.id;
      if (matchRef.current(e)) hit = true;
    }
    if (!hit || timerRef.current !== null) return;
    onTriggerRef.current();
    timerRef.current = window.setTimeout(() => {
      timerRef.current = null;
      onTriggerRef.current();
    }, windowMs);
  }, [events, windowMs]);

  useEffect(
    () => () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
      timerRef.current = null;
    },
    [],
  );
}
