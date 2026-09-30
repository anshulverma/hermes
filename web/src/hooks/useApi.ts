/**
 * Data hooks for API client.
 * Simple fetch + React state pattern (no heavy deps).
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { fetchHealth, fetchRuns, type HealthResponse, type Run } from '../api/client';

type ApiState<T> = {
  data: T | null;
  loading: boolean;
  error: Error | null;
};

export function useHealth() {
  const [state, setState] = useState<ApiState<HealthResponse>>({
    data: null,
    loading: true,
    error: null,
  });

  useEffect(() => {
    let mounted = true;

    fetchHealth()
      .then((data) => {
        if (mounted) {
          setState({ data, loading: false, error: null });
        }
      })
      .catch((error) => {
        if (mounted) {
          setState({ data: null, loading: false, error });
        }
      });

    return () => {
      mounted = false;
    };
  }, []);

  return state;
}

export function useRuns() {
  const [state, setState] = useState<ApiState<Run[]>>({
    data: null,
    loading: true,
    error: null,
  });
  // Every fetch takes a number, and a response older than the newest one
  // already applied is dropped: the stream throttle, RunControl's success and
  // a decision's refetch can overlap.
  const issued = useRef(0);
  const applied = useRef(0);

  const refetch = useCallback(() => {
    const seq = ++issued.current;
    const apply = (next: (prev: ApiState<Run[]>) => ApiState<Run[]>) => {
      if (seq < applied.current) return;
      applied.current = seq;
      setState(next);
    };
    fetchRuns().then(
      (data) => apply(() => ({ data, loading: false, error: null })),
      // A failed refetch keeps the last rows; `loading` never goes back to true.
      (error) => apply((prev) => ({ data: prev.data, loading: false, error })),
    );
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { ...state, refetch };
}
