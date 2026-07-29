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

export type Phase = {
  name: string;
  counts: Record<string, number>;
  current: boolean;
};

export type RunDetail = Run & {
  config: Record<string, any>;
  updated_at: string;
  phases: Phase[];
};

export type Ticket = {
  id: string;
  run_id: string;
  state: string;
  phase: string;
  subject: string;
  resource_req: string;
  host: string | null;
  attempts: number;
  elapsed_s: number;
  priority: number;
};

export type TicketFilters = {
  state?: string;
  phase?: string;
  resource?: string;
  host?: string;
  search?: string;
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

export async function fetchTickets(runId: string, filters?: TicketFilters): Promise<Ticket[]> {
  const params = new URLSearchParams();
  if (filters?.state) params.append('state', filters.state);
  if (filters?.phase) params.append('phase', filters.phase);
  if (filters?.resource) params.append('resource', filters.resource);
  if (filters?.host) params.append('host', filters.host);
  if (filters?.search) params.append('search', filters.search);

  const queryString = params.toString();
  const url = `/api/runs/${runId}/tickets${queryString ? '?' + queryString : ''}`;
  return fetchJSON<Ticket[]>(url);
}
