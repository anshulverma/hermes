/**
 * Tests for useNow: one shared 30 s clock in epoch seconds.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useNow } from './useNow';

const T0 = 1_750_000_000; // epoch seconds

describe('useNow', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(T0 * 1000);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('returns epoch seconds and moves every 30 s', () => {
    const { result } = renderHook(() => useNow());
    expect(result.current).toBe(T0);

    act(() => {
      vi.advanceTimersByTime(29_999);
    });
    expect(result.current).toBe(T0);

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current).toBe(T0 + 30);
  });

  it('every subscriber shares one interval, cleared when the last one unmounts', () => {
    const setSpy = vi.spyOn(globalThis, 'setInterval');
    const clearSpy = vi.spyOn(globalThis, 'clearInterval');
    const a = renderHook(() => useNow());
    const b = renderHook(() => useNow());
    expect(setSpy).toHaveBeenCalledTimes(1);

    act(() => {
      vi.advanceTimersByTime(30_000);
    });
    expect(a.result.current).toBe(T0 + 30);
    expect(b.result.current).toBe(T0 + 30);

    a.unmount();
    expect(clearSpy).not.toHaveBeenCalled();
    b.unmount();
    expect(clearSpy).toHaveBeenCalledTimes(1);
  });
});
