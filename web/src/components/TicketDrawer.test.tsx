import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
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

  describe('Requeue control (Phase D3)', () => {
    it('should show Requeue button for guard-routed needs_human ticket', async () => {
      const guardRoutedDetail = {
        ...mockTicketDetail,
        ticket: {
          ...mockTicketDetail.ticket,
          state: 'needs_human',  // Raw engine state (will be normalized by fetchTicketDetail)
          reduction_id: null,  // Guard-routed
        },
      };

      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => guardRoutedDetail,
      });

      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

      await waitFor(() => {
        expect(screen.getByText('Requeue')).toBeInTheDocument();
      });
    });

    it('should NOT show Requeue button for reduction-flagged needs_human ticket', async () => {
      const reductionFlaggedDetail = {
        ...mockTicketDetail,
        ticket: {
          ...mockTicketDetail.ticket,
          state: 'needs_human',  // Raw engine state (will be normalized by fetchTicketDetail)
          reduction_id: 42,  // Reduction-flagged
        },
      };

      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => reductionFlaggedDetail,
      });

      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

      await waitFor(() => {
        expect(screen.getByText(/investigate issue/i)).toBeInTheDocument();
      });

      expect(screen.queryByText('Requeue')).not.toBeInTheDocument();
    });

    it('should NOT show Requeue button for non-needs_human ticket', async () => {
      const queuedDetail = {
        ...mockTicketDetail,
        ticket: {
          ...mockTicketDetail.ticket,
          state: 'queued',
          reduction_id: null,
        },
      };

      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => queuedDetail,
      });

      const queuedTicket = { ...mockTicket, state: 'queued' };

      render(<TicketDrawer isOpen={true} ticket={queuedTicket} onClose={() => {}} />);

      await waitFor(() => {
        expect(screen.getByText(/investigate issue/i)).toBeInTheDocument();
      });

      expect(screen.queryByText('Requeue')).not.toBeInTheDocument();
    });

    it('should call requeueTicket and refresh detail when Requeue clicked', async () => {
      const guardRoutedDetail = {
        ...mockTicketDetail,
        ticket: {
          ...mockTicketDetail.ticket,
          state: 'needs_human',  // Raw engine state (will be normalized by fetchTicketDetail)
          reduction_id: null,
        },
      };

      const requeuedDetail = {
        ...guardRoutedDetail,
        ticket: {
          ...guardRoutedDetail.ticket,
          state: 'queued',  // After requeue
        },
      };

      // First call: initial detail fetch
      // Second call: requeue POST
      // Third call: refresh detail fetch
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: async () => guardRoutedDetail,
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ state: 'queued' }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => requeuedDetail,
        });

      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

      // Wait for initial load
      await waitFor(() => {
        expect(screen.getByText('Requeue')).toBeInTheDocument();
      });

      // Click requeue
      const requeueButton = screen.getByText('Requeue');
      requeueButton.click();

      // Wait for requeue to complete and detail to refresh
      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith(
          '/api/tickets/test-run/t-0/requeue',
          expect.objectContaining({
            method: 'POST',
          })
        );
      });

      // Verify detail was refreshed (third call to fetch detail)
      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledTimes(3);
      });
    });

    it('should show error when requeue returns 409', async () => {
      const guardRoutedDetail = {
        ...mockTicketDetail,
        ticket: {
          ...mockTicketDetail.ticket,
          state: 'needs_human',  // Raw engine state (will be normalized by fetchTicketDetail)
          reduction_id: null,
        },
      };

      // First call: initial detail fetch
      // Second call: requeue POST (409 error)
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: async () => guardRoutedDetail,
        })
        .mockResolvedValueOnce({
          ok: false,
          status: 409,
          json: async () => ({ detail: "ticket 'test-run/t-0' is 'queued', not 'needs_human'; cannot operator-requeue" }),
        });

      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

      // Wait for initial load
      await waitFor(() => {
        expect(screen.getByText('Requeue')).toBeInTheDocument();
      });

      // Click requeue
      const requeueButton = screen.getByText('Requeue');
      requeueButton.click();

      // Wait for error to show
      await waitFor(() => {
        expect(screen.getByText(/not 'needs_human'/)).toBeInTheDocument();
      });
    });
  });
});
