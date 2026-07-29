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

export type TicketDetailAttempt = {
  attempt: number;
  host: string;
  outcome: string | null;
  termination_reason: string | null;
  started_at: number | null;
  ended_at: number | null;
  result_ref: string | null;
  error_summary: string | null;
};

export type TicketDetailResult = {
  outcome: string;
  termination_reason: string;
  result_ref: string | null;
  error_summary: string | null;
  started_at: number;
  ended_at: number;
};

export type TicketDetail = {
  ticket: {
    id: string;
    run_id: string;
    phase: string;
    state: string;
    resource_req: string;
    priority: number;
    attempts: number;
    host: string | null;
    subject: string;
    created_at: number;
    updated_at: number;
  };
  payload: Record<string, any>;
  result: TicketDetailResult | null;
  attempt_timeline: TicketDetailAttempt[];
  evidence: Array<{ attempt: number; ref: string }>;
};

export async function fetchTicketDetail(ticketId: string): Promise<TicketDetail> {
  return fetchJSON<TicketDetail>(`/api/tickets/${ticketId}`);
}

export type HealthReport = {
  reachable: boolean;
  agent_ok: boolean;
  auth_ok: boolean;
  workspace_ready: boolean;
  guard_installed: boolean;
  latency_ms: number;
};

export type CrewMember = {
  id: string;
  site: string;
  state: string;
  capabilities: string[];
  resources: Record<string, number>;
  health: HealthReport | null;
  current_ticket: string | null;
  last_heartbeat: number;
};

export type Lease = {
  id: string;
  run_id: string;
  resource_class: string;
  ticket_id: string | null;
  host: string | null;
  acquired_at: number;
  ttl_s: number;
  expires_at: number;
  remaining_s: number;
};

export async function fetchCrew(): Promise<CrewMember[]> {
  return fetchJSON<CrewMember[]>('/api/crew');
}

export async function fetchLeases(host?: string): Promise<Lease[]> {
  const params = new URLSearchParams();
  if (host) params.append('host', host);

  const queryString = params.toString();
  const url = `/api/leases${queryString ? '?' + queryString : ''}`;
  return fetchJSON<Lease[]>(url);
}

export type Event = {
  id: number;
  ts: number;
  kind: string;
  run_id: string | null;
  ticket_id: string | null;
  host: string | null;
  message: string | null;
  data: Record<string, any>;
};

export type EventFilters = {
  since?: number;
  kind?: string;
  limit?: number;
};

export async function fetchEvents(filters?: EventFilters): Promise<Event[]> {
  const params = new URLSearchParams();
  if (filters?.since !== undefined) params.append('since', filters.since.toString());
  if (filters?.kind) params.append('kind', filters.kind);
  if (filters?.limit !== undefined) params.append('limit', filters.limit.toString());

  const queryString = params.toString();
  const url = `/api/events${queryString ? '?' + queryString : ''}`;
  return fetchJSON<Event[]>(url);
}

export async function fetchEventKinds(): Promise<string[]> {
  return fetchJSON<string[]>('/api/events/kinds');
}
