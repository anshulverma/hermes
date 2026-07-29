/**
 * Tests for normalization layer functions.
 * Phase B6: deriveFindingStatus pure function tests.
 */

import { describe, it, expect } from 'vitest';
import { deriveFindingStatus } from './normalize';

describe('deriveFindingStatus', () => {
  it('should return "accepted" for review_state accepted', () => {
    const reduction = {
      id: 1,
      run_id: 'test-run',
      phase: 'work',
      kind: 'test',
      review_state: 'accepted',
      json: {},
      member_ticket_ids: [],
      member_tickets: [],
    };
    expect(deriveFindingStatus(reduction)).toBe('accepted');
  });

  it('should return "rejected" for review_state rejected', () => {
    const reduction = {
      id: 2,
      run_id: 'test-run',
      phase: 'work',
      kind: 'test',
      review_state: 'rejected',
      json: {},
      member_ticket_ids: [],
      member_tickets: [],
    };
    expect(deriveFindingStatus(reduction)).toBe('rejected');
  });

  it('should return "superseded" for review_state superseded', () => {
    const reduction = {
      id: 3,
      run_id: 'test-run',
      phase: 'work',
      kind: 'test',
      review_state: 'superseded',
      json: {},
      member_ticket_ids: [],
      member_tickets: [],
    };
    expect(deriveFindingStatus(reduction)).toBe('superseded');
  });

  it('should return "needs-human" for pending with any needs-human member ticket', () => {
    const reduction = {
      id: 4,
      run_id: 'test-run',
      phase: 'work',
      kind: 'test',
      review_state: 'pending',
      json: {},
      member_ticket_ids: ['t-1', 't-2'],
      member_tickets: [
        { id: 't-1', state: 'done', phase: 'work' },
        { id: 't-2', state: 'needs-human', phase: 'work' },
      ],
    };
    expect(deriveFindingStatus(reduction)).toBe('needs-human');
  });

  it('should return "resolved (pending review)" for pending with all members done', () => {
    const reduction = {
      id: 5,
      run_id: 'test-run',
      phase: 'work',
      kind: 'test',
      review_state: 'pending',
      json: {},
      member_ticket_ids: ['t-1', 't-2'],
      member_tickets: [
        { id: 't-1', state: 'done', phase: 'work' },
        { id: 't-2', state: 'done', phase: 'work' },
      ],
    };
    expect(deriveFindingStatus(reduction)).toBe('resolved (pending review)');
  });

  it('should return "in progress" for pending with active member tickets', () => {
    const reduction = {
      id: 6,
      run_id: 'test-run',
      phase: 'work',
      kind: 'test',
      review_state: 'pending',
      json: {},
      member_ticket_ids: ['t-1', 't-2'],
      member_tickets: [
        { id: 't-1', state: 'running', phase: 'work' },
        { id: 't-2', state: 'queued', phase: 'work' },
      ],
    };
    expect(deriveFindingStatus(reduction)).toBe('in progress');
  });

  it('should return "in progress" for pending with mixed active and done tickets', () => {
    const reduction = {
      id: 7,
      run_id: 'test-run',
      phase: 'work',
      kind: 'test',
      review_state: 'pending',
      json: {},
      member_ticket_ids: ['t-1', 't-2'],
      member_tickets: [
        { id: 't-1', state: 'done', phase: 'work' },
        { id: 't-2', state: 'running', phase: 'work' },
      ],
    };
    expect(deriveFindingStatus(reduction)).toBe('in progress');
  });

  it('should return "pending" for pending with no member tickets', () => {
    const reduction = {
      id: 8,
      run_id: 'test-run',
      phase: 'work',
      kind: 'test',
      review_state: 'pending',
      json: {},
      member_ticket_ids: [],
      member_tickets: [],
    };
    expect(deriveFindingStatus(reduction)).toBe('pending');
  });

  it('should treat parked/failed as active states', () => {
    const reduction = {
      id: 9,
      run_id: 'test-run',
      phase: 'work',
      kind: 'test',
      review_state: 'pending',
      json: {},
      member_ticket_ids: ['t-1'],
      member_tickets: [
        { id: 't-1', state: 'failed', phase: 'work' },
      ],
    };
    expect(deriveFindingStatus(reduction)).toBe('in progress');
  });

  it('should detect needs-human status from normalized state', () => {
    // Phase B6 Finding 2: deriveFindingStatus expects UI-normalized states (needs-human).
    // The normalization happens in fetchReductions pipeline (see client.test.ts).
    // This test verifies the pure function behavior with already-normalized inputs.
    const reduction = {
      id: 10,
      run_id: 'test-run',
      phase: 'work',
      kind: 'test',
      review_state: 'pending',
      json: {},
      member_ticket_ids: ['t-1'],
      member_tickets: [
        { id: 't-1', state: 'needs-human', phase: 'work' },  // UI-normalized state
      ],
    };
    expect(deriveFindingStatus(reduction)).toBe('needs-human');
  });
});
