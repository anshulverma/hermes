/**
 * Normalization layer: engine → UI mappings.
 * Maps engine values (snake_case, engine semantics) to UI values (kebab-case, prototype shapes).
 */

import type { TicketDetail } from './client';

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
