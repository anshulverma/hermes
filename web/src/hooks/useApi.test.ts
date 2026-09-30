/**
 * Tests for useRuns: a refetch keeps the rows it has, and an older /api/runs
 * response never overwrites a newer one.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useRuns } from './useApi';
import type { Run } from '../api/client';

function run(id: string): Run {
  return {
    id,
    playbook: 'pb',
    site: 'local',
    state: 'running',
    phase: 'work',
    base_ref: 'main',
    created_at: 1785319200,
    updated_at: 1785319200,
    tickets: {},
    has_view: false,
    awaiting: 0,
    subject: null,
  };
}

// A fake fetch: every call stays pending until the test settles it, in any order.
function fakeFetch() {
  const pending: Array<{ resolve: (rows: Run[]) => void; fail: (status: number) => void }> = [];
  const fetchMock = vi.fn(
    (_url: string) =>
      new Promise<unknown>((resolve) => {
        pending.push({
          resolve: (rows) => resolve({ ok: true, status: 200, json: async () => rows }),
          fail: (status) =>
            resolve({ ok: false, status, statusText: 'Error', json: async () => ({ detail: `boom ${status}` }) }),
        });
      }),
  );
  vi.stubGlobal('fetch', fetchMock);
  return { fetchMock, pending };
}

// Settle one response, then let every promise hop behind it run.
async function settle(fn: () => void) {
  await act(async () => {
    fn();
    await new Promise((r) => setTimeout(r, 0));
  });
}

const ids = (runs: Run[] | null) => runs?.map((r) => r.id);

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useRuns', () => {
  it('refetch keeps the previous rows and never sets loading back to true', async () => {
    const { fetchMock, pending } = fakeFetch();
    const { result } = renderHook(() => useRuns());
    expect(result.current.loading).toBe(true);
    expect(fetchMock.mock.calls[0][0]).toBe('/api/runs');
    await settle(() => pending[0].resolve([run('run-1')]));

    act(() => result.current.refetch());

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(ids(result.current.data)).toEqual(['run-1']);
    expect(result.current.loading).toBe(false);

    await settle(() => pending[1].resolve([run('run-2'), run('run-1')]));

    expect(ids(result.current.data)).toEqual(['run-2', 'run-1']);
    expect(result.current.loading).toBe(false);
  });

  it('drops a response older than the newest one applied', async () => {
    const { pending } = fakeFetch();
    const { result } = renderHook(() => useRuns());
    act(() => result.current.refetch());
    act(() => result.current.refetch());

    await settle(() => pending[2].resolve([run('newest')]));
    await settle(() => pending[0].resolve([run('oldest')]));
    await settle(() => pending[1].fail(500));

    expect(ids(result.current.data)).toEqual(['newest']);
    expect(result.current.error).toBeNull();
  });

  it('a failed refetch keeps the last rows; the next success clears the error', async () => {
    const { pending } = fakeFetch();
    const { result } = renderHook(() => useRuns());
    await settle(() => pending[0].resolve([run('run-1')]));

    act(() => result.current.refetch());
    await settle(() => pending[1].fail(500));

    expect(ids(result.current.data)).toEqual(['run-1']);
    expect(result.current.error?.message).toBe('boom 500');
    expect(result.current.loading).toBe(false);

    act(() => result.current.refetch());
    await settle(() => pending[2].resolve([run('run-1')]));

    expect(result.current.error).toBeNull();
  });
});
