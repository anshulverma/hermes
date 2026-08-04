/**
 * Tests for useLiveTick hook.
 */

import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useLiveTick, TICKET_EVENT_KINDS, CREW_EVENT_KINDS, FINDING_EVENT_KINDS } from './useLiveTick';
import type { Event } from '../api/client';

function makeEvent(id: number, kind: string): Event {
  return {
    id,
    ts: 1000000 + id,
    kind,
    run_id: 'test-run',
    ticket_id: null,
    host: null,
    message: null,
    data: {},
  };
}

type HookProps = { evt: Event | null };

describe('useLiveTick', () => {
  it('starts at 0 with no event', () => {
    const { result } = renderHook(() => useLiveTick(null, TICKET_EVENT_KINDS));
    expect(result.current).toBe(0);
  });

  it('increments when a matching event kind arrives', () => {
    const { result, rerender } = renderHook(
      ({ evt }: HookProps) => useLiveTick(evt, TICKET_EVENT_KINDS),
      { initialProps: { evt: null } as HookProps },
    );
    expect(result.current).toBe(0);

    act(() => {
      rerender({ evt: makeEvent(1, 'ticket_claimed') });
    });
    expect(result.current).toBe(1);
  });

  it('does NOT increment for a non-matching kind', () => {
    const { result, rerender } = renderHook(
      ({ evt }: HookProps) => useLiveTick(evt, TICKET_EVENT_KINDS),
      { initialProps: { evt: null } as HookProps },
    );

    act(() => {
      rerender({ evt: makeEvent(2, 'crew_added') }); // crew event, not ticket
    });
    expect(result.current).toBe(0);
  });

  it('does NOT increment when the same event id is delivered again', () => {
    const event = makeEvent(10, 'ticket_started');
    const { result, rerender } = renderHook(
      ({ evt }: HookProps) => useLiveTick(evt, TICKET_EVENT_KINDS),
      { initialProps: { evt: null } as HookProps },
    );

    act(() => {
      rerender({ evt: event });
    });
    expect(result.current).toBe(1);

    // Same object reference — must not re-increment
    act(() => {
      rerender({ evt: event });
    });
    expect(result.current).toBe(1);

    // Different object, same id — must not re-increment
    act(() => {
      rerender({ evt: { ...event } });
    });
    expect(result.current).toBe(1);
  });

  it('increments once per distinct new matching event', () => {
    const { result, rerender } = renderHook(
      ({ evt }: HookProps) => useLiveTick(evt, TICKET_EVENT_KINDS),
      { initialProps: { evt: null } as HookProps },
    );

    act(() => { rerender({ evt: makeEvent(1, 'ticket_claimed') }); });
    expect(result.current).toBe(1);

    act(() => { rerender({ evt: makeEvent(2, 'result_recorded') }); });
    expect(result.current).toBe(2);

    act(() => { rerender({ evt: makeEvent(3, 'phase_advanced') }); });
    expect(result.current).toBe(3);
  });

  it('CREW_EVENT_KINDS: increments on crew_added, ignores ticket kinds', () => {
    const { result, rerender } = renderHook(
      ({ evt }: HookProps) => useLiveTick(evt, CREW_EVENT_KINDS),
      { initialProps: { evt: null } as HookProps },
    );

    act(() => { rerender({ evt: makeEvent(1, 'ticket_claimed') }); });
    expect(result.current).toBe(0); // ticket kind, not crew

    act(() => { rerender({ evt: makeEvent(2, 'crew_added') }); });
    expect(result.current).toBe(1);
  });

  it('FINDING_EVENT_KINDS: increments on reduction_created, ignores others', () => {
    const { result, rerender } = renderHook(
      ({ evt }: HookProps) => useLiveTick(evt, FINDING_EVENT_KINDS),
      { initialProps: { evt: null } as HookProps },
    );

    act(() => { rerender({ evt: makeEvent(1, 'ticket_claimed') }); });
    expect(result.current).toBe(0);

    act(() => { rerender({ evt: makeEvent(2, 'reduction_created') }); });
    expect(result.current).toBe(1);

    act(() => { rerender({ evt: makeEvent(3, 'reduction_accepted') }); });
    expect(result.current).toBe(2);
  });
});
