/**
 * API client for Hermes control plane.
 * Typed fetch wrappers for /api endpoints.
 */

export type HealthResponse = {
  status: string;
  version: string;
  home: string;
};

export type Run = {
  id: string;
  playbook: string;
  site: string;
  state: string;
  phase: string;
  base_ref: string;
  created_at: string;
  tickets: Record<string, number>;
};

export type RunDetail = Run & {
  config: Record<string, any>;
  updated_at: string;
  phases: Record<string, Record<string, number>>;
};

async function fetchJSON<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  return response.json();
}

export async function fetchHealth(): Promise<HealthResponse> {
  return fetchJSON<HealthResponse>('/api/health');
}

export async function fetchRuns(): Promise<Run[]> {
  return fetchJSON<Run[]>('/api/runs');
}

export async function fetchRun(id: string): Promise<RunDetail> {
  return fetchJSON<RunDetail>(`/api/runs/${id}`);
}
