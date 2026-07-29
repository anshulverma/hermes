/**
 * Tests for Findings view.
 * Phase B6: rendering reductions with real review_state + member tickets.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import Findings from './Findings';

// Mock fetch
const mockFetch = vi.fn();
(globalThis as any).fetch = mockFetch;

const mockReductions = [
  {
    id: 1,
    run_id: 'test-run',
    phase: 'work',
    kind: 'duplicate_root_cause',
    review_state: 'pending',
    json: {
      title: 'Null pointer in module X',
    },
    member_ticket_ids: ['test-run/t-100', 'test-run/t-101'],
    member_tickets: [
      { id: 'test-run/t-100', state: 'done', phase: 'work' },
      { id: 'test-run/t-101', state: 'needs-human', phase: 'work' },
    ],
  },
  {
    id: 2,
    run_id: 'test-run',
    phase: 'reduce',
    kind: 'test_flake',
    review_state: 'accepted',
    json: {
      title: 'Timeout in CI',
    },
    member_ticket_ids: ['test-run/t-102'],
    member_tickets: [
      { id: 'test-run/t-102', state: 'done', phase: 'reduce' },
    ],
  },
  {
    id: 3,
    run_id: 'test-run',
    phase: 'work',
    kind: 'config_error',
    review_state: 'rejected',
    json: {
      title: 'Missing env var',
    },
    member_ticket_ids: [],
    member_tickets: [],
  },
];

describe('Findings', () => {
  beforeEach(() => {
    mockFetch.mockClear();
  });

  it('should render a card per reduction with real review_state', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockReductions,
    });

    render(<Findings runId="test-run" />);

    await waitFor(() => {
      // Should render reduction titles
      expect(screen.getByText('Null pointer in module X')).toBeInTheDocument();
      expect(screen.getByText('Timeout in CI')).toBeInTheDocument();
      expect(screen.getByText('Missing env var')).toBeInTheDocument();
    });
  });

  it('should display kind as category badge', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockReductions,
    });

    render(<Findings runId="test-run" />);

    await waitFor(() => {
      expect(screen.getByText('duplicate_root_cause')).toBeInTheDocument();
      expect(screen.getByText('test_flake')).toBeInTheDocument();
      expect(screen.getByText('config_error')).toBeInTheDocument();
    });
  });

  it('should display real review_state for each reduction', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockReductions,
    });

    render(<Findings runId="test-run" />);

    await waitFor(() => {
      // Check for review state labels (pending/accepted/rejected)
      // The exact rendering depends on StatusPill/Badge component
      // We verify the states are present in the DOM
      expect(screen.getByText('pending')).toBeInTheDocument();
      expect(screen.getByText('accepted')).toBeInTheDocument();
      expect(screen.getByText('rejected')).toBeInTheDocument();
    });
  });

  it('should display member tickets with real states', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockReductions,
    });

    render(<Findings runId="test-run" />);

    await waitFor(() => {
      // Should show member ticket IDs
      expect(screen.getByText('test-run/t-100')).toBeInTheDocument();
      expect(screen.getByText('test-run/t-101')).toBeInTheDocument();
      expect(screen.getByText('test-run/t-102')).toBeInTheDocument();

      // Should show member ticket states
      // done appears multiple times, needs human appears (StatusPill normalizes with space)
      const needsHumanElements = screen.getAllByText('needs human');
      expect(needsHumanElements.length).toBeGreaterThan(0);
    });
  });

  it('should display derived status based on real fields (no fix_state)', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockReductions,
    });

    render(<Findings runId="test-run" />);

    await waitFor(() => {
      // First reduction: pending + needs-human member -> "needs human" status (StatusPill uses space)
      const needsHumanElements = screen.getAllByText('needs human');
      expect(needsHumanElements.length).toBeGreaterThan(0);

      // Second reduction: accepted -> "accepted" status
      expect(screen.getByText('accepted')).toBeInTheDocument();

      // Third reduction: rejected -> "rejected" status
      expect(screen.getByText('rejected')).toBeInTheDocument();
    });

    // Verify no fix_state is present anywhere in the rendered output
    // (This is a negative assertion - fix_state should not exist)
    const domText = document.body.textContent || '';
    expect(domText).not.toContain('fix_state');
  });

  it('should render empty state when no reductions exist', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => [],
    });

    render(<Findings runId="test-run" />);

    await waitFor(() => {
      // Should show empty state
      expect(screen.getByText(/no findings/i)).toBeInTheDocument();
    });
  });

  it('should display member ticket count', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockReductions,
    });

    render(<Findings runId="test-run" />);

    await waitFor(() => {
      // First reduction has 2 member tickets
      expect(screen.getByText('2 member tickets')).toBeInTheDocument();
      // Second has 1
      expect(screen.getByText('1 member ticket')).toBeInTheDocument();
      // Third has 0 (may not show or show "0 member tickets")
    });
  });

  it('should fetch reductions from the correct endpoint', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockReductions,
    });

    render(<Findings runId="test-run-123" />);

    await waitFor(() => {
      expect((mockFetch as any).mock.calls[0][0]).toBe('/api/runs/test-run-123/reductions');
    });
  });

  // --- Phase D4: Accept/Reject actions ---

  it('should show Accept and Reject buttons only for pending reductions', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockReductions,
    });

    render(<Findings runId="test-run" />);

    await waitFor(() => {
      // Should show Accept/Reject buttons (only pending reductions have them)
      const acceptButtons = screen.queryAllByText('Accept');
      const rejectButtons = screen.queryAllByText('Reject');

      // Only reduction 1 is pending, so should have 1 Accept and 1 Reject button
      expect(acceptButtons.length).toBe(1);
      expect(rejectButtons.length).toBe(1);
    });
  });

  it('should NOT show Accept/Reject buttons for accepted reductions', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => [mockReductions[1]], // accepted reduction
    });

    render(<Findings runId="test-run" />);

    await waitFor(() => {
      // Verify reduction is shown
      expect(screen.getByText('Timeout in CI')).toBeInTheDocument();
      // But no action buttons
      expect(screen.queryByText('Accept')).not.toBeInTheDocument();
      expect(screen.queryByText('Reject')).not.toBeInTheDocument();
    });
  });

  it('should NOT show Accept/Reject buttons for rejected reductions', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => [mockReductions[2]], // rejected reduction
    });

    render(<Findings runId="test-run" />);

    await waitFor(() => {
      // Verify reduction is shown
      expect(screen.getByText('Missing env var')).toBeInTheDocument();
      // But no action buttons
      expect(screen.queryByText('Accept')).not.toBeInTheDocument();
      expect(screen.queryByText('Reject')).not.toBeInTheDocument();
    });
  });
});
