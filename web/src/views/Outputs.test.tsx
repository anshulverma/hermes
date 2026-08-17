/**
 * Tests for Outputs view.
 * Phase B6: rendering reductions with real review_state + member tickets.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import Outputs from './Outputs';

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

describe('Outputs', () => {
  beforeEach(() => {
    mockFetch.mockClear();
  });

  it('should render a card per reduction with real review_state', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockReductions,
    });

    render(<Outputs runId="test-run" />);

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

    render(<Outputs runId="test-run" />);

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

    render(<Outputs runId="test-run" />);

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

    render(<Outputs runId="test-run" />);

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

    render(<Outputs runId="test-run" />);

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

    render(<Outputs runId="test-run" />);

    await waitFor(() => {
      // Should show empty state
      expect(screen.getByText(/no outputs yet/i)).toBeInTheDocument();
    });
  });

  it('should display member ticket count', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockReductions,
    });

    render(<Outputs runId="test-run" />);

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

    render(<Outputs runId="test-run-123" />);

    await waitFor(() => {
      expect((mockFetch as any).mock.calls[0][0]).toBe('/api/runs/test-run-123/reductions');
    });
  });

  // --- Phase D4: Accept/Reject actions ---

  it('offers no accept/reject: this page decides nothing', async () => {
    // Those buttons settle a needs_human ticket. A reduction holding no such
    // ticket has no decision in it, so offering them here implies an authority
    // they do not have — they would flip a flag and move nothing.
    mockFetch.mockResolvedValue({ ok: true, json: async () => mockReductions });
    render(<Outputs runId="test-run" />);

    await waitFor(() => expect(screen.getByText('Outputs')).toBeInTheDocument());

    expect(screen.queryByRole('button', { name: /accept/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /reject/i })).toBeNull();
  });

  it('should refetch when liveTick changes', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockReductions,
    });

    const { rerender } = render(<Outputs runId="test-run" liveTick={0} />);

    await waitFor(() => {
      expect(screen.getByText('Null pointer in module X')).toBeInTheDocument();
    });

    const callsBefore = (mockFetch as any).mock.calls.length;

    rerender(<Outputs runId="test-run" liveTick={1} />);

    await waitFor(() => {
      expect((mockFetch as any).mock.calls.length).toBeGreaterThan(callsBefore);
    });
  });

  it('should keep previously rendered findings visible during a live refetch', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockReductions,
    });

    const { rerender } = render(<Outputs runId="test-run" liveTick={0} />);

    await waitFor(() => {
      expect(screen.getByText('Null pointer in module X')).toBeInTheDocument();
    });

    // Start a slow refetch
    mockFetch.mockImplementation(() => new Promise(() => {}));
    rerender(<Outputs runId="test-run" liveTick={1} />);

    // Outputs should still be on screen (no blanking spinner)
    expect(screen.getByText('Null pointer in module X')).toBeInTheDocument();
  });
});
