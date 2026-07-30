import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import TicketDrawer from './TicketDrawer';
import type { Ticket } from '../api/client';

// Mock fetch
const mockFetch = vi.fn();
(globalThis as any).fetch = mockFetch;

const mockTicket: Ticket = {
  id: 'test-run/t-0',
  run_id: 'test-run',
  state: 'needs_human',
  phase: 'work',
  subject: 'Investigate issue #1',
  resource_req: 'cpu',
  host: 'worker-1',
  attempts: 2,
  elapsed_s: 120,
  priority: 1,
};

const mockTicketDetail = {
  ticket: {
    id: 'test-run/t-0',
    run_id: 'test-run',
    phase: 'work',
    state: 'needs_human',
    resource_req: 'cpu',
    priority: 1,
    attempts: 2,
    host: 'worker-1',
    subject: 'Investigate issue #1',
    created_at: 1722211200.0,
    updated_at: 1722211320.0,
  },
  payload: {
    goal: 'Fix bug in authentication flow',
    driver: {
      command: 'claude',
      args: { model: 'sonnet' },
      loop: null,
    },
    done_contract: {
      tests_pass: true,
      no_regressions: true,
    },
    guardrails: {
      max_attempts: 3,
      timeout_s: 1800,
    },
  },
  result: {
    outcome: 'ok',
    termination_reason: 'goal_met',
    result_ref: 's3://results/ticket-1.json',
    error_summary: null,
    started_at: 1722211200.0,
    ended_at: 1722211320.0,
  },
  attempt_timeline: [
    {
      attempt: 1,
      host: 'worker-1',
      outcome: 'driver_failed',
      termination_reason: 'driver_error',
      started_at: 1722211000.0,
      ended_at: 1722211050.0,
      result_ref: null,
      error_summary: 'timeout in phase 1',
    },
    {
      attempt: 2,
      host: 'worker-1',
      outcome: 'ok',
      termination_reason: 'goal_met',
      started_at: 1722211200.0,
      ended_at: 1722211320.0,
      result_ref: 's3://results/ticket-1.json',
      error_summary: null,
    },
  ],
  evidence: [
    {
      attempt: 2,
      ref: 's3://results/ticket-1.json',
    },
  ],
  history: [
    { id: 1, ts: 1722211000.0, kind: 'dispatched', message: null, data: { host: 'worker-1' } },
    { id: 2, ts: 1722211320.0, kind: 'needs_human', message: 're-verify override', data: {} },
  ],
  reason: 'Independent re-verify did not confirm the reported result; routed for human review.',
  reduction: null,
  available_actions: ['requeue', 'reprioritize', 'abandon'],
};

describe('TicketDrawer', () => {
  beforeEach(() => {
    mockFetch.mockClear();
  });

  it('should fetch ticket detail when opened', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockTicketDetail,
    });

    render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

    await waitFor(() => {
      expect((mockFetch as any).mock.calls[0][0]).toBe('/api/tickets/test-run/t-0');
    });
  });

  it('should render payload fields', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockTicketDetail,
    });

    render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

    await waitFor(() => {
      expect(screen.getByText(/Fix bug in authentication flow/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/payload/i)).toBeInTheDocument();
  });

  it('should render latest result', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockTicketDetail,
    });

    render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

    await waitFor(() => {
      const goals = screen.getAllByText('goal_met');
      expect(goals.length).toBeGreaterThan(0);
    });

    expect(screen.getByText('Result')).toBeInTheDocument();
  });

  it('should render attempt timeline', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockTicketDetail,
    });

    render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

    await waitFor(() => {
      expect(screen.getByText('driver_failed')).toBeInTheDocument();
      expect(screen.getByText('driver_error')).toBeInTheDocument();
    });

    expect(screen.getByText('Attempt Timeline')).toBeInTheDocument();
  });

  it('should render evidence links', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockTicketDetail,
    });

    const { container } = render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

    await waitFor(() => {
      const link = container.querySelector('a[href="s3://results/ticket-1.json"]');
      expect(link).toBeInTheDocument();
    });

    expect(screen.getByText('Evidence')).toBeInTheDocument();
  });

  it('should show empty state when result is null', async () => {
    const detailNoResult = {
      ...mockTicketDetail,
      result: null,
      attempt_timeline: [],
      evidence: [],
    };

    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => detailNoResult,
    });

    render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

    await waitFor(() => {
      expect(screen.getByText(/no result yet/i)).toBeInTheDocument();
    });
  });

  it('should show error state when fetch fails', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));

    render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });

  it('should show loading state while fetching', () => {
    mockFetch.mockImplementation(
      () => new Promise(() => {}),
    );

    render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('should not fetch when drawer is closed', () => {
    render(<TicketDrawer isOpen={false} ticket={mockTicket} onClose={() => {}} />);

    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('should not fetch when ticket is null', () => {
    render(<TicketDrawer isOpen={true} ticket={null} onClose={() => {}} />);

    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('actually opens the DS drawer when isOpen (dialog is exposed, not hidden)', async () => {
    // The DS Drawer sets aria-hidden from its `open` prop; a mis-wired prop name
    // leaves the panel permanently hidden. getByRole excludes aria-hidden nodes,
    // so this fails if `open` is not wired through.
    mockFetch.mockResolvedValue({ ok: true, json: async () => mockTicketDetail });
    render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('keeps the DS drawer closed (dialog hidden) when isOpen is false', () => {
    render(<TicketDrawer isOpen={false} ticket={mockTicket} onClose={() => {}} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  describe('Reason banner', () => {
    it('shows the derived reason when present', async () => {
      mockFetch.mockResolvedValue({ ok: true, json: async () => mockTicketDetail });

      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

      await waitFor(() => {
        expect(screen.getByText(/independent re-verify did not confirm/i)).toBeInTheDocument();
      });
    });

    it('does not render a banner when reason is null', async () => {
      const noReason = { ...mockTicketDetail, reason: null };
      mockFetch.mockResolvedValue({ ok: true, json: async () => noReason });

      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

      await waitFor(() => {
        expect(screen.getByText(/investigate issue/i)).toBeInTheDocument();
      });
      expect(screen.queryByTestId('ticket-reason')).not.toBeInTheDocument();
    });
  });

  describe('History timeline', () => {
    it('renders each history event kind', async () => {
      mockFetch.mockResolvedValue({ ok: true, json: async () => mockTicketDetail });

      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

      await waitFor(() => {
        expect(screen.getByText('History')).toBeInTheDocument();
      });
      expect(screen.getByText('dispatched')).toBeInTheDocument();
      // needs_human appears both as an event kind and the state pill; at least one.
      expect(screen.getAllByText('needs_human').length).toBeGreaterThan(0);
    });
  });

  describe('Actions menu (available_actions)', () => {
    it('renders Requeue for a guard-routed needs_human ticket', async () => {
      mockFetch.mockResolvedValue({ ok: true, json: async () => mockTicketDetail });
      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);
      await waitFor(() => expect(screen.getByText('Requeue')).toBeInTheDocument());
    });

    it('does NOT render Requeue for a reduction-flagged ticket (offers Accept/Reject)', async () => {
      const flagged = {
        ...mockTicketDetail,
        ticket: { ...mockTicketDetail.ticket, state: 'needs_human', reduction_id: 42 },
        reduction: { id: 42, kind: 'cluster', review_state: 'pending', json: { cause_category: 'parser' } },
        available_actions: ['accept_reduction', 'reject_reduction', 'abandon'],
      };
      mockFetch.mockResolvedValue({ ok: true, json: async () => flagged });
      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

      await waitFor(() => expect(screen.getByText('Accept')).toBeInTheDocument());
      expect(screen.getByText('Reject')).toBeInTheDocument();
      expect(screen.queryByText('Requeue')).not.toBeInTheDocument();
    });

    it('renders only Retry for a failed ticket', async () => {
      const failed = {
        ...mockTicketDetail,
        ticket: { ...mockTicketDetail.ticket, state: 'failed', reduction_id: null },
        reason: 'driver_error: empty output',
        available_actions: ['retry'],
      };
      mockFetch.mockResolvedValue({ ok: true, json: async () => failed });
      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

      await waitFor(() => expect(screen.getByText('Retry')).toBeInTheDocument());
      expect(screen.queryByText('Requeue')).not.toBeInTheDocument();
      expect(screen.queryByText('Abandon')).not.toBeInTheDocument();
    });

    it('calls requeueTicket and refreshes when Requeue clicked', async () => {
      const requeued = {
        ...mockTicketDetail,
        ticket: { ...mockTicketDetail.ticket, state: 'queued' },
        available_actions: ['reprioritize', 'abandon'],
      };
      mockFetch
        .mockResolvedValueOnce({ ok: true, json: async () => mockTicketDetail })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ state: 'queued' }) })
        .mockResolvedValueOnce({ ok: true, json: async () => requeued });

      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);
      await waitFor(() => expect(screen.getByText('Requeue')).toBeInTheDocument());
      screen.getByText('Requeue').click();

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith(
          '/api/tickets/test-run/t-0/requeue',
          expect.objectContaining({ method: 'POST' }),
        );
      });
      await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(3));
    });

    it('calls retryTicket when Retry clicked', async () => {
      const failed = {
        ...mockTicketDetail,
        ticket: { ...mockTicketDetail.ticket, state: 'failed', reduction_id: null },
        available_actions: ['retry'],
      };
      mockFetch
        .mockResolvedValueOnce({ ok: true, json: async () => failed })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ state: 'queued' }) })
        .mockResolvedValueOnce({ ok: true, json: async () => failed });

      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);
      await waitFor(() => expect(screen.getByText('Retry')).toBeInTheDocument());
      screen.getByText('Retry').click();

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith(
          '/api/tickets/test-run/t-0/retry',
          expect.objectContaining({ method: 'POST' }),
        );
      });
    });

    it('confirms before abandoning, then calls abandonTicket', async () => {
      mockFetch
        .mockResolvedValueOnce({ ok: true, json: async () => mockTicketDetail })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ state: 'failed' }) })
        .mockResolvedValueOnce({ ok: true, json: async () => mockTicketDetail });

      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);
      await waitFor(() => expect(screen.getByText('Abandon')).toBeInTheDocument());

      // First click reveals a confirm; no POST yet.
      screen.getByText('Abandon').click();
      expect(mockFetch).toHaveBeenCalledTimes(1);

      await waitFor(() => expect(screen.getByText('Confirm abandon')).toBeInTheDocument());
      screen.getByText('Confirm abandon').click();

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith(
          '/api/tickets/test-run/t-0/abandon',
          expect.objectContaining({ method: 'POST' }),
        );
      });
    });

    it('reprioritizes with the entered value', async () => {
      const queued = {
        ...mockTicketDetail,
        ticket: { ...mockTicketDetail.ticket, state: 'queued', reduction_id: null },
        available_actions: ['reprioritize', 'abandon'],
      };
      mockFetch
        .mockResolvedValueOnce({ ok: true, json: async () => queued })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ state: 'queued' }) })
        .mockResolvedValueOnce({ ok: true, json: async () => queued });

      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);
      await waitFor(() => expect(screen.getByText('Set priority')).toBeInTheDocument());

      const input = screen.getByLabelText('priority') as HTMLInputElement;
      fireEvent.change(input, { target: { value: '7' } });
      screen.getByText('Set priority').click();

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith(
          '/api/tickets/test-run/t-0/priority',
          expect.objectContaining({ method: 'POST', body: JSON.stringify({ priority: 7 }) }),
        );
      });
    });

    it('accepts a flagged reduction', async () => {
      const flagged = {
        ...mockTicketDetail,
        ticket: { ...mockTicketDetail.ticket, state: 'needs_human', reduction_id: 42 },
        reduction: { id: 42, kind: 'cluster', review_state: 'pending', json: {} },
        available_actions: ['accept_reduction', 'reject_reduction', 'abandon'],
      };
      mockFetch
        .mockResolvedValueOnce({ ok: true, json: async () => flagged })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ review_state: 'accepted' }) })
        .mockResolvedValueOnce({ ok: true, json: async () => flagged });

      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);
      await waitFor(() => expect(screen.getByText('Accept')).toBeInTheDocument());
      screen.getByText('Accept').click();

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith(
          '/api/reductions/42/accept',
          expect.objectContaining({ method: 'POST' }),
        );
      });
    });

    it('shows an error when an action returns 409', async () => {
      mockFetch
        .mockResolvedValueOnce({ ok: true, json: async () => mockTicketDetail })
        .mockResolvedValueOnce({
          ok: false,
          status: 409,
          json: async () => ({ detail: "action 'requeue' is not available for ticket in state 'queued'" }),
        });

      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);
      await waitFor(() => expect(screen.getByText('Requeue')).toBeInTheDocument());
      screen.getByText('Requeue').click();

      await waitFor(() => {
        expect(screen.getByText(/not available/i)).toBeInTheDocument();
      });
    });
  });
});
