/**
 * Normalization layer: engine → UI mappings.
 * Maps engine values (snake_case, engine semantics) to UI values (kebab-case, prototype shapes).
 */

import type { RunDetail, TicketDetail } from './client';

export type RunContext = {
  label: string;
  value: string;
}[];

export type PlaybookInfo = {
  name: string;
  summary: string;
  context_note: string;
  stops_at: string;
};

/**
 * Playbook descriptive copy (UI content, not run data).
 * This is the human-readable copy shown in PlaybookDialog.
 */
export const PLAYBOOK_CONTENT: Record<string, PlaybookInfo> = {
  example: {
    name: 'example',
    summary: 'Echo playbook for testing and demos',
    context_note: 'issue_kind determines what issues are fetched',
    stops_at: 'reduce phase completion',
  },
  mechanic: {
    name: 'mechanic',
    summary: 'Automated test suite investigation and triage',
    context_note: 'base is the codebase ref; suite is the test target',
    stops_at: 'diff published or all tests pass',
  },
  rigger: {
    name: 'rigger',
    summary: 'Model/metric performance regression investigation',
    context_note: 'model is the ML model; metric is the performance indicator',
    stops_at: 'root cause identified with mitigation plan',
  },
  medic: {
    name: 'medic',
    summary: 'Production incident investigation and remediation',
    context_note: 'incident is the SEV/alert; service is the affected system',
    stops_at: 'service restored and root cause documented',
  },
};

/**
 * Derive playbook-specific context from run config.
 * mechanic → base + suite
 * rigger → model + metric
 * medic → incident + service
 */
export function deriveContext(run: RunDetail): RunContext {
  const { playbook, config } = run;

  switch (playbook) {
    case 'example':
      return [
        { label: 'issue_kind', value: config.issue_kind || 'bug' },
      ];
    case 'mechanic':
      return [
        { label: 'base', value: config.base || 'unknown' },
        { label: 'suite', value: config.suite || 'unknown' },
      ];
    case 'rigger':
      return [
        { label: 'model', value: config.model || 'unknown' },
        { label: 'metric', value: config.metric || 'unknown' },
      ];
    case 'medic':
      return [
        { label: 'incident', value: config.incident || 'unknown' },
        { label: 'service', value: config.service || 'unknown' },
      ];
    default:
      return [];
  }
}

/**
 * Normalize ticket state: needs_human (engine) ↔ needs-human (UI)
 */
export function normalizeTicketState(engineState: string): string {
  return engineState.replace(/_/g, '-');
}

/**
 * Denormalize ticket state: needs-human (UI) ↔ needs_human (engine)
 */
export function denormalizeTicketState(uiState: string): string {
  return uiState.replace(/-/g, '_');
}

/**
 * Normalize ticket detail: apply state normalization to the detail response.
 */
export function normalizeTicketDetail(detail: TicketDetail): TicketDetail {
  return {
    ...detail,
    ticket: {
      ...detail.ticket,
      state: normalizeTicketState(detail.ticket.state),
    },
  };
}

/**
 * Normalize reduction: apply state normalization to member tickets.
 * Engine vocab (needs_human) → UI vocab (needs-human).
 */
export function normalizeReduction<T extends { member_tickets: Array<{ state: string }> }>(reduction: T): T {
  return {
    ...reduction,
    member_tickets: reduction.member_tickets.map(t => ({
      ...t,
      state: normalizeTicketState(t.state),
    })),
  };
}

/**
 * Derive finding status from REAL fields (no mock fix_state).
 * Maps review_state + member ticket states to a UI status label.
 *
 * Logic:
 * - review_state accepted → "accepted"
 * - review_state rejected → "rejected"
 * - review_state superseded → "superseded"
 * - review_state pending + any member needs-human → "needs-human"
 * - review_state pending + all members done (≥1) → "resolved (pending review)"
 * - review_state pending + members still active → "in progress"
 * - no members → fall back to review_state label
 */
export function deriveFindingStatus(reduction: {
  review_state: string;
  member_tickets: Array<{ state: string }>;
}): string {
  const { review_state, member_tickets } = reduction;

  // Non-pending states: return as-is
  if (review_state === 'accepted') return 'accepted';
  if (review_state === 'rejected') return 'rejected';
  if (review_state === 'superseded') return 'superseded';

  // Pending + no members: fall back to review_state
  if (member_tickets.length === 0) return review_state;

  // Check member states
  const hasNeedsHuman = member_tickets.some(m => m.state === 'needs-human');
  const allDone = member_tickets.every(m => m.state === 'done');

  if (hasNeedsHuman) return 'needs-human';
  if (allDone) return 'resolved (pending review)';

  // Otherwise, active work in progress
  return 'in progress';
}
