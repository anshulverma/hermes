/**
 * Data hooks for API client.
 * Simple fetch + React state pattern (no heavy deps).
 */

import { useState, useEffect } from 'react';
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

  useEffect(() => {
    let mounted = true;

    fetchRuns()
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
