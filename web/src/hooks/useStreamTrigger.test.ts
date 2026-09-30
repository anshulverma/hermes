/**
 * Tests for useStreamTrigger: the cursor over the shared event buffer and the
 * leading + always-trailing 2 s throttle.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useStreamTrigger } from './useStreamTrigger';
import type { Event } from '../api/client';

function ev(id: number, run_id: string | null = 'r1', kind = 'ticket_claimed'): Event {
  return { id, ts: 1_000_000 + id, kind, run_id, ticket_id: null, host: null, message: null, data: {} };
}

// App's runs refetch match: any event that names a run.
const namesARun = (e: Event) => e.run_id != null;

type Props = { events: Event[] };

/** Mounts the hook over `initial` and returns a way to append to the buffer. */
function setup(initial: Event[] = []) {
  const onTrigger = vi.fn();
  const hook = renderHook(({ events }: Props) => useStreamTrigger(events, namesARun, onTrigger), {
    initialProps: { events: initial },
  });
  let buffer = initial;
  const push = (...more: Event[]) => {
    buffer = [...buffer, ...more];
    act(() => {
      hook.rerender({ events: buffer });
    });
  };
  const advance = (ms: number) => {
    act(() => {
      vi.advanceTimersByTime(ms);
    });
  };
  return { onTrigger, push, advance, hook };
}

describe('useStreamTrigger', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('calls at once on the first matching event and once more when the 2 s window ends', () => {
    const { onTrigger, push, advance } = setup();
    push(ev(1));
    expect(onTrigger).toHaveBeenCalledTimes(1);
    advance(1999);
    expect(onTrigger).toHaveBeenCalledTimes(1);
    advance(1);
    expect(onTrigger).toHaveBeenCalledTimes(2);
    advance(10_000);
    expect(onTrigger).toHaveBeenCalledTimes(2);
  });

  it('N matching events inside one window give exactly one immediate and one trailing call', () => {
    const { onTrigger, push, advance } = setup();
    push(ev(1));
    advance(500);
    push(ev(2));
    advance(1000);
    push(ev(3), ev(4));
    expect(onTrigger).toHaveBeenCalledTimes(1);
    advance(500);
    expect(onTrigger).toHaveBeenCalledTimes(2);
    advance(10_000);
    expect(onTrigger).toHaveBeenCalledTimes(2);
  });

  it('a burst delivered in one render triggers when its first event matches and its last does not', () => {
    const { onTrigger, push } = setup();
    push(ev(1, 'r1', 'needs_human'), ev(2, null, 'crew_health'));
    expect(onTrigger).toHaveBeenCalledTimes(1);
  });

  it('a crew event (null run_id) causes no call', () => {
    const { onTrigger, push, advance } = setup();
    push(ev(1, null, 'crew_health'));
    advance(5000);
    expect(onTrigger).not.toHaveBeenCalled();
  });

  it('a matching event after the window closed starts a new cycle', () => {
    const { onTrigger, push, advance } = setup();
    push(ev(1));
    advance(2000);
    expect(onTrigger).toHaveBeenCalledTimes(2);
    push(ev(2));
    expect(onTrigger).toHaveBeenCalledTimes(3);
    advance(2000);
    expect(onTrigger).toHaveBeenCalledTimes(4);
  });

  it('replays none of the events buffered before it mounted', () => {
    const { onTrigger, push, advance } = setup([ev(1), ev(2), ev(3)]);
    advance(5000);
    expect(onTrigger).not.toHaveBeenCalled();
    push(ev(4));
    expect(onTrigger).toHaveBeenCalledTimes(1);
  });

  it('unmounting inside a window cancels the trailing call', () => {
    const { onTrigger, push, advance, hook } = setup();
    push(ev(1));
    hook.unmount();
    advance(5000);
    expect(onTrigger).toHaveBeenCalledTimes(1);
  });
});
