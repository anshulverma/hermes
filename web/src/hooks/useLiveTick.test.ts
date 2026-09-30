/**
 * Tests for useLiveTick hook.
 */

import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useLiveTick, TICKET_EVENT_KINDS, CREW_EVENT_KINDS, FINDING_EVENT_KINDS } from './useLiveTick';
import type { Event } from '../api/client';

function makeEvent(id: number, kind: string, run_id: string | null = 'test-run'): Event {
  return {
    id,
    ts: 1000000 + id,
    kind,
    run_id,
    ticket_id: null,
    host: null,
    message: null,
    data: {},
  };
}

type HookProps = { events: Event[] };

/** Mounts useLiveTick over a buffer that starts empty; `push` appends to it. */
function setup(kinds: ReadonlySet<string>, runId?: string | null, initial: Event[] = []) {
  const hook = renderHook(({ events }: HookProps) => useLiveTick(events, kinds, runId), {
    initialProps: { events: initial },
  });
  let buffer = initial;
  const push = (...more: Event[]) => {
    buffer = [...buffer, ...more];
    act(() => {
      hook.rerender({ events: buffer });
    });
  };
  const redeliver = (events: Event[]) => {
    act(() => {
      hook.rerender({ events });
    });
  };
  return { result: hook.result, push, redeliver, buffer: () => buffer };
}

describe('useLiveTick', () => {
  it('starts at 0 with no events', () => {
    const { result } = renderHook(() => useLiveTick([], TICKET_EVENT_KINDS));
    expect(result.current).toBe(0);
  });

  it('increments when a matching event kind arrives', () => {
    const { result, push } = setup(TICKET_EVENT_KINDS);
    expect(result.current).toBe(0);

    push(makeEvent(1, 'ticket_claimed'));
    expect(result.current).toBe(1);
  });

  it('does NOT increment for a non-matching kind', () => {
    const { result, push } = setup(TICKET_EVENT_KINDS);

    push(makeEvent(2, 'crew_added')); // crew event, not ticket
    expect(result.current).toBe(0);
  });

  it('does NOT increment when the same event id is delivered again', () => {
    const event = makeEvent(10, 'ticket_started');
    const { result, push, redeliver, buffer } = setup(TICKET_EVENT_KINDS);

    push(event);
    expect(result.current).toBe(1);

    // Same array, new reference: must not re-increment
    redeliver([...buffer()]);
    expect(result.current).toBe(1);

    // Different object, same id: must not re-increment
    redeliver([{ ...event }]);
    expect(result.current).toBe(1);
  });

  it('increments once per distinct new matching event', () => {
    const { result, push } = setup(TICKET_EVENT_KINDS);

    push(makeEvent(1, 'ticket_claimed'));
    expect(result.current).toBe(1);

    push(makeEvent(2, 'result_recorded'));
    expect(result.current).toBe(2);

    push(makeEvent(3, 'phase_advanced'));
    expect(result.current).toBe(3);
  });

  it('counts a matching event that is not the last of a burst delivered in one render', () => {
    const { result, push } = setup(TICKET_EVENT_KINDS);

    // needs_human then a crew heartbeat, batched by React into one render
    push(makeEvent(1, 'needs_human'), makeEvent(2, 'crew_health', null));
    expect(result.current).toBe(1);
  });

  it('replays none of the events buffered before it mounted', () => {
    const { result, push } = setup(TICKET_EVENT_KINDS, undefined, [
      makeEvent(1, 'ticket_claimed'),
      makeEvent(2, 'result_recorded'),
    ]);
    expect(result.current).toBe(0);

    push(makeEvent(3, 'ticket_parked'));
    expect(result.current).toBe(1);
  });

  it("with runId counts only that run's events", () => {
    const { result, push } = setup(TICKET_EVENT_KINDS, 'run-a');

    push(makeEvent(1, 'ticket_claimed', 'run-b'));
    expect(result.current).toBe(0);

    push(makeEvent(2, 'ticket_claimed', 'run-a'));
    expect(result.current).toBe(1);
  });

  it('CREW_EVENT_KINDS: increments on crew_added and on work changing hands', () => {
    const { result, push } = setup(CREW_EVENT_KINDS);

    push(makeEvent(1, 'ticket_claimed'));
    expect(result.current).toBe(1); // a host took work: the crew view is stale

    push(makeEvent(2, 'crew_added', null));
    expect(result.current).toBe(2);

    push(makeEvent(3, 'reduction_created'));
    expect(result.current).toBe(2); // no host gained or lost work
  });

  it('CREW_EVENT_KINDS: every engine kind that gives a host work or takes it away', () => {
    // claim, result, requeue (penalty, host lost, lease expired), park, and the
    // two failures that end in-flight work with no result: a contract violation
    // and an operator abandon.
    for (const kind of [
      'ticket_claimed', 'result_recorded', 'ticket_requeued', 'ticket_parked',
      'ticket_failed', 'ticket_abandoned',
    ]) {
      expect(CREW_EVENT_KINDS.has(kind), kind).toBe(true);
    }
  });

  it('FINDING_EVENT_KINDS: increments on reduction_created, ignores others', () => {
    const { result, push } = setup(FINDING_EVENT_KINDS);

    push(makeEvent(1, 'ticket_claimed'));
    expect(result.current).toBe(0);

    push(makeEvent(2, 'reduction_created'));
    expect(result.current).toBe(1);

    push(makeEvent(3, 'reduction_accepted'));
    expect(result.current).toBe(2);
  });
});
