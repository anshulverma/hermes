/**
 * API client for Hermes control plane.
 * Typed fetch wrappers for /api endpoints.
 * Phase D1b: Auth integration (Authorization header, AuthError).
 */

import { getToken, isRemote } from './auth';

/**
 * AuthError - thrown on 401 responses.
 */
export class AuthError extends Error {
  constructor(message: string = 'Unauthorized') {
    super(message);
    this.name = 'AuthError';
  }
}

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

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  // Build headers with auth if token is available
  const headers: Record<string, string> = {
    ...(options?.headers as Record<string, string> || {}),
  };

  const token = getToken();

  // Add Authorization header if:
  // - Token is present AND
  // - (Request is a mutation OR we're in remote mode)
  const isMutation = options?.method && options.method !== 'GET';
  if (token && (isMutation || isRemote())) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // If we're sending JSON, add Content-Type
  if (options?.body && typeof options.body === 'string') {
    headers['Content-Type'] = 'application/json';
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    // Throw AuthError on 401
    if (response.status === 401) {
      throw new AuthError(response.statusText || 'Unauthorized');
    }

    // For other errors, try to extract server detail from JSON body
    let errorMessage = `HTTP error! status: ${response.status}`;
    try {
      const errorBody = await response.json();
      if (errorBody.detail) {
        errorMessage = errorBody.detail;
      }
    } catch (parseError) {
      // Body is not JSON or doesn't have detail field - use default message
    }

    throw new Error(errorMessage);
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
    reduction_id?: number | null;
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

export type MemberTicket = {
  id: string;
  state: string;
  phase: string;
};

export type Reduction = {
  id: number;
  run_id: string;
  phase: string;
  kind: string;
  json: Record<string, any>;
  review_state: string;
  member_ticket_ids: string[];
  member_tickets: MemberTicket[];
};

export async function fetchReductions(runId: string, phase?: string): Promise<Reduction[]> {
  const params = new URLSearchParams();
  if (phase) params.append('phase', phase);

  const queryString = params.toString();
  const url = `/api/runs/${runId}/reductions${queryString ? '?' + queryString : ''}`;
  const reductions = await fetchJSON<Reduction[]>(url);

  // Normalize member ticket states: engine vocab (needs_human) → UI vocab (needs-human)
  // so deriveFindingStatus sees consistent values (Phase B6 fix)
  return reductions.map(r => ({
    ...r,
    member_tickets: r.member_tickets.map(t => ({
      ...t,
      state: t.state.replace(/_/g, '-'),
    })),
  }));
}

/**
 * Run control endpoints (Phase D1b).
 * POST /api/runs/{id}/pause|resume|stop
 */

export type RunControlResponse = {
  state: string;
};

export async function pauseRun(runId: string): Promise<RunControlResponse> {
  return fetchJSON<RunControlResponse>(`/api/runs/${runId}/pause`, {
    method: 'POST',
  });
}

export async function resumeRun(runId: string): Promise<RunControlResponse> {
  return fetchJSON<RunControlResponse>(`/api/runs/${runId}/resume`, {
    method: 'POST',
  });
}

export async function stopRun(runId: string): Promise<RunControlResponse> {
  return fetchJSON<RunControlResponse>(`/api/runs/${runId}/stop`, {
    method: 'POST',
  });
}

/**
 * Crew control endpoints (Phase D2b).
 */

export type HealthCheck = {
  name: string;
  ok: boolean;
  detail: string;
};

export type HealthChecklist = {
  host: string;
  ok: boolean;
  reachable: boolean;
  agent_ok: boolean;
  auth_ok: boolean;
  workspace_ready: boolean;
  guard_installed: boolean;
  resources: Record<string, number>;
  latency_ms: number;
  checks: HealthCheck[];
};

export async function probeCrew(params: {
  host: string;
  site: string;
  agent?: string;
}): Promise<HealthChecklist> {
  return fetchJSON<HealthChecklist>('/api/crew/probe', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export async function addCrew(params: {
  host: string;
  site: string;
  agent?: string;
  base_ref?: string;
}): Promise<CrewMember> {
  return fetchJSON<CrewMember>('/api/crew', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export async function reprobeCrew(host: string, agent?: string): Promise<HealthChecklist> {
  return fetchJSON<HealthChecklist>(`/api/crew/${host}/reprobe`, {
    method: 'POST',
    body: JSON.stringify(agent ? { agent } : {}),
  });
}

export async function drainCrew(host: string): Promise<{ state: string }> {
  return fetchJSON<{ state: string }>(`/api/crew/${host}/drain`, {
    method: 'POST',
  });
}

export async function removeCrew(host: string): Promise<{ status: string }> {
  return fetchJSON<{ status: string }>(`/api/crew/${host}`, {
    method: 'DELETE',
  });
}

/**
 * Ticket control endpoints (Phase D3).
 * POST /api/tickets/{id}/requeue
 */

export type TicketControlResponse = {
  state: string;
};

export async function requeueTicket(ticketId: string): Promise<TicketControlResponse> {
  return fetchJSON<TicketControlResponse>(`/api/tickets/${ticketId}/requeue`, {
    method: 'POST',
  });
}

/**
 * Reduction control endpoints (Phase D4).
 * POST /api/reductions/{id}/accept|reject
 */

export type ReductionControlResponse = {
  review_state: string;
};

export async function acceptReduction(reductionId: number): Promise<ReductionControlResponse> {
  return fetchJSON<ReductionControlResponse>(`/api/reductions/${reductionId}/accept`, {
    method: 'POST',
  });
}

export async function rejectReduction(reductionId: number): Promise<ReductionControlResponse> {
  return fetchJSON<ReductionControlResponse>(`/api/reductions/${reductionId}/reject`, {
    method: 'POST',
  });
}

/**
 * Metrics endpoints (Phase E1).
 */

export type MetricsBucket = {
  t_start: number;
  throughput: number;
  done_cumulative: number;
  failed_cumulative: number;
  error_rate: number;
  crew_online: number;
};

export type RunMetrics = {
  run_id: string;
  bucket_s: number;
  buckets: MetricsBucket[];
};

export async function fetchRunMetrics(runId: string, bucketS?: number): Promise<RunMetrics> {
  const params = new URLSearchParams();
  if (bucketS !== undefined) params.append('bucket_s', bucketS.toString());

  const queryString = params.toString();
  const url = `/api/runs/${runId}/metrics${queryString ? '?' + queryString : ''}`;
  return fetchJSON<RunMetrics>(url);
}
