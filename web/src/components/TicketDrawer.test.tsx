import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import TicketDrawer from './TicketDrawer';
import { TOPBAR_HEIGHT } from './TopBar';
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

  it('should render payload fields once the payload is expanded', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockTicketDetail,
    });

    render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

    await waitFor(() => {
      expect(screen.getByTestId('payload-toggle')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('payload-toggle'));

    expect(screen.getByText(/Fix bug in authentication flow/i)).toBeInTheDocument();
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

  it('should render evidence refs as copyable host paths, not links', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockTicketDetail,
    });

    const { container } = render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

    await waitFor(() => {
      expect(screen.getByText('Evidence')).toBeInTheDocument();
    });

    // The path is shown as text, never as a dead hyperlink the browser cannot open.
    expect(container.querySelector('a[href="s3://results/ticket-1.json"]')).toBeNull();
    expect(screen.getAllByText('s3://results/ticket-1.json').length).toBeGreaterThan(0);
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

  describe('Detail enrichment', () => {
    it('labels the goal as "Goal" and shows created/priority meta', async () => {
      mockFetch.mockResolvedValue({ ok: true, json: async () => mockTicketDetail });
      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);
      await waitFor(() => expect(screen.getByText('Goal')).toBeInTheDocument());
      expect(screen.getByText('Created')).toBeInTheDocument();
      expect(screen.getByText('Priority')).toBeInTheDocument();
      // The old "Subject" label is gone.
      expect(screen.queryByText('Subject')).not.toBeInTheDocument();
    });

    it('shows the failure Output block with the raw detail when present', async () => {
      const failed = {
        ...mockTicketDetail,
        ticket: { ...mockTicketDetail.ticket, state: 'failed' },
        result: {
          ...mockTicketDetail.result,
          outcome: 'driver_failed',
          detail: 'Traceback (most recent call last): ValueError: boom',
        },
        available_actions: ['retry'],
      };
      mockFetch.mockResolvedValue({ ok: true, json: async () => failed });
      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);
      await waitFor(() => expect(screen.getByText('Output')).toBeInTheDocument());
      expect(screen.getByText(/ValueError: boom/)).toBeInTheDocument();
    });

    it('shows an explicit no-output note for a failure without captured detail', async () => {
      const failed = {
        ...mockTicketDetail,
        ticket: { ...mockTicketDetail.ticket, state: 'failed' },
        result: { ...mockTicketDetail.result, outcome: 'driver_failed', detail: null },
        available_actions: ['retry'],
      };
      mockFetch.mockResolvedValue({ ok: true, json: async () => failed });
      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);
      await waitFor(() => expect(screen.getByText('Output')).toBeInTheDocument());
      expect(screen.getByText(/no output/i)).toBeInTheDocument();
    });

    it('does not show an Output block for a done ticket', async () => {
      const done = {
        ...mockTicketDetail,
        ticket: { ...mockTicketDetail.ticket, state: 'done' },
        result: { ...mockTicketDetail.result, outcome: 'ok', detail: null },
        available_actions: [],
      };
      mockFetch.mockResolvedValue({ ok: true, json: async () => done });
      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);
      await waitFor(() => expect(screen.getByText('Goal')).toBeInTheDocument());
      expect(screen.queryByText('Output')).not.toBeInTheDocument();
    });
  });

  describe('Agent answer (successful tickets)', () => {
    const LONG_ANSWER =
      'The dequeue rate collapsed because the consumer pool was pinned to a single region. ' +
      'Rebalancing across regions restored throughput to 4200 msg/s.';

    const doneWithAnswer = {
      ...mockTicketDetail,
      ticket: { ...mockTicketDetail.ticket, state: 'done' },
      result: { ...mockTicketDetail.result, outcome: 'ok', detail: null },
      available_actions: [],
      answer: LONG_ANSWER,
      finding: {
        id: 7,
        kind: 'result',
        created_at: 1722211320.0,
        json: { answer: LONG_ANSWER },
      },
    };

    it('shows the agent answer for a done ticket', async () => {
      mockFetch.mockResolvedValue({ ok: true, json: async () => doneWithAnswer });
      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

      await waitFor(() => expect(screen.getByText('Answer')).toBeInTheDocument());
      expect(screen.getByTestId('ticket-answer')).toHaveTextContent(
        /Rebalancing across regions restored throughput to 4200 msg\/s\./,
      );
    });

    it('renders a long answer as wrapped, scrollable text rather than a JSON blob', async () => {
      mockFetch.mockResolvedValue({ ok: true, json: async () => doneWithAnswer });
      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

      await waitFor(() => expect(screen.getByTestId('ticket-answer')).toBeInTheDocument());
      const answer = screen.getByTestId('ticket-answer');
      expect(answer.style.whiteSpace).toBe('pre-wrap');
      expect(answer.style.overflowY).toBe('auto');
      expect(answer.style.maxHeight).not.toBe('');
      // Prose, not a serialised object.
      expect(answer.textContent).not.toContain('{');
    });

    it('keeps the full finding document reachable behind a toggle when an answer exists', async () => {
      mockFetch.mockResolvedValue({ ok: true, json: async () => doneWithAnswer });
      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

      await waitFor(() => expect(screen.getByTestId('finding-toggle')).toBeInTheDocument());
      expect(screen.queryByTestId('finding-json')).not.toBeInTheDocument();

      fireEvent.click(screen.getByTestId('finding-toggle'));
      expect(screen.getByTestId('finding-json')).toBeInTheDocument();
    });

    it('renders a structured finding that carries no answer prose', async () => {
      const structured = {
        ...mockTicketDetail,
        ticket: { ...mockTicketDetail.ticket, state: 'done' },
        result: { ...mockTicketDetail.result, outcome: 'ok', detail: null },
        available_actions: [],
        answer: null,
        finding: {
          id: 9,
          kind: 'result',
          created_at: 1722211320.0,
          json: { reproduced: true, root_cause: { signature: 'off-by-one in cursor' } },
        },
      };
      mockFetch.mockResolvedValue({ ok: true, json: async () => structured });
      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

      await waitFor(() => expect(screen.getByTestId('finding-json')).toBeInTheDocument());
      expect(screen.getByTestId('finding-json')).toHaveTextContent(/off-by-one in cursor/);
      expect(screen.queryByTestId('ticket-answer')).not.toBeInTheDocument();
    });

    it('shows no answer section when the ticket has no finding', async () => {
      mockFetch.mockResolvedValue({ ok: true, json: async () => mockTicketDetail });
      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

      await waitFor(() => expect(screen.getByText('Goal')).toBeInTheDocument());
      expect(screen.queryByTestId('ticket-answer')).not.toBeInTheDocument();
      expect(screen.queryByTestId('finding-json')).not.toBeInTheDocument();
    });

    it('still shows failure diagnostics for a failed ticket that also has a finding', async () => {
      const failed = {
        ...mockTicketDetail,
        ticket: { ...mockTicketDetail.ticket, state: 'failed' },
        result: {
          ...mockTicketDetail.result,
          outcome: 'driver_failed',
          detail: 'Traceback (most recent call last): ValueError: boom',
        },
        available_actions: ['retry'],
        answer: 'stale answer from an earlier attempt',
        finding: { id: 3, kind: 'result', created_at: 1.0, json: { answer: 'stale answer from an earlier attempt' } },
      };
      mockFetch.mockResolvedValue({ ok: true, json: async () => failed });
      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

      await waitFor(() => expect(screen.getByText('Output')).toBeInTheDocument());
      expect(screen.getByText(/ValueError: boom/)).toBeInTheDocument();
    });
  });

  describe('Header state freshness', () => {
    it('renders the freshly fetched detail state, not the stale board prop', async () => {
      const staleProp: Ticket = { ...mockTicket, state: 'failed' };
      const fresh = {
        ...mockTicketDetail,
        ticket: { ...mockTicketDetail.ticket, state: 'queued' },
        available_actions: ['reprioritize', 'abandon'],
      };
      mockFetch.mockResolvedValue({ ok: true, json: async () => fresh });

      render(<TicketDrawer isOpen={true} ticket={staleProp} onClose={() => {}} />);

      await waitFor(() =>
        expect(screen.getByTestId('ticket-state-pill')).toHaveTextContent('queued'),
      );
      expect(screen.getByTestId('ticket-state-pill')).not.toHaveTextContent('failed');
    });

    it('falls back to the prop state before the detail arrives', () => {
      mockFetch.mockImplementation(() => new Promise(() => {}));
      const staleProp: Ticket = { ...mockTicket, state: 'failed' };

      render(<TicketDrawer isOpen={true} ticket={staleProp} onClose={() => {}} />);

      expect(screen.getByTestId('ticket-state-pill')).toHaveTextContent('failed');
    });

    it('shows the queued state after a successful Retry without a manual refresh', async () => {
      const failed = {
        ...mockTicketDetail,
        ticket: { ...mockTicketDetail.ticket, state: 'failed', reduction_id: null },
        available_actions: ['retry'],
      };
      const requeued = {
        ...failed,
        ticket: { ...failed.ticket, state: 'queued' },
        available_actions: ['reprioritize', 'abandon'],
      };
      mockFetch
        .mockResolvedValueOnce({ ok: true, json: async () => failed })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ state: 'queued' }) })
        .mockResolvedValueOnce({ ok: true, json: async () => requeued });

      render(<TicketDrawer isOpen={true} ticket={{ ...mockTicket, state: 'failed' }} onClose={() => {}} />);
      await waitFor(() => expect(screen.getByText('Retry')).toBeInTheDocument());
      expect(screen.getByTestId('ticket-state-pill')).toHaveTextContent('failed');

      fireEvent.click(screen.getByText('Retry'));

      await waitFor(() =>
        expect(screen.getByTestId('ticket-state-pill')).toHaveTextContent('queued'),
      );
    });
  });

  describe('Host path references', () => {
    it('copies an evidence ref to the clipboard on click', async () => {
      const writeText = vi.fn().mockResolvedValue(undefined);
      Object.defineProperty(globalThis.navigator, 'clipboard', {
        value: { writeText },
        configurable: true,
      });

      mockFetch.mockResolvedValue({ ok: true, json: async () => mockTicketDetail });
      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

      await waitFor(() => expect(screen.getByText('Evidence')).toBeInTheDocument());
      const copyButtons = screen.getAllByRole('button', { name: /copy host path/i });
      expect(copyButtons.length).toBeGreaterThan(0);

      fireEvent.click(copyButtons[copyButtons.length - 1]);
      await waitFor(() => expect(writeText).toHaveBeenCalledWith('s3://results/ticket-1.json'));
    });

    it('labels the result ref as a host path and renders no hyperlink for it', async () => {
      mockFetch.mockResolvedValue({ ok: true, json: async () => mockTicketDetail });
      const { container } = render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

      await waitFor(() => expect(screen.getByText('Result')).toBeInTheDocument());
      expect(screen.getAllByText(/host path/i).length).toBeGreaterThan(0);
      expect(container.querySelector('a')).toBeNull();
    });
  });

  describe('Raw payload collapsing', () => {
    it('does not render the raw payload until it is expanded', async () => {
      mockFetch.mockResolvedValue({ ok: true, json: async () => mockTicketDetail });
      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

      await waitFor(() => expect(screen.getByTestId('payload-toggle')).toBeInTheDocument());
      expect(screen.queryByTestId('payload-json')).not.toBeInTheDocument();
      expect(screen.queryByText(/done_contract/)).not.toBeInTheDocument();

      fireEvent.click(screen.getByTestId('payload-toggle'));

      expect(screen.getByTestId('payload-json')).toBeInTheDocument();
      expect(screen.getByTestId('payload-json')).toHaveTextContent(/done_contract/);
    });

    it('collapses the raw payload again on a second click', async () => {
      mockFetch.mockResolvedValue({ ok: true, json: async () => mockTicketDetail });
      render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

      await waitFor(() => expect(screen.getByTestId('payload-toggle')).toBeInTheDocument());
      fireEvent.click(screen.getByTestId('payload-toggle'));
      expect(screen.getByTestId('payload-json')).toBeInTheDocument();

      fireEvent.click(screen.getByTestId('payload-toggle'));
      expect(screen.queryByTestId('payload-json')).not.toBeInTheDocument();
    });
  });
});

describe('Layout: clear of the app chrome', () => {
  it('anchors the drawer below the top bar so its title is not hidden behind it', async () => {
    // The content wrapper sets a z-index, creating a stacking context the
    // drawer's own z-index cannot escape — so a drawer pinned to top:0 renders
    // UNDER the (z-index 40) top bar. Offsetting by the bar height is what
    // keeps the title visible.
    mockFetch.mockResolvedValue({ ok: true, json: async () => mockTicketDetail });
    render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

    const panel = screen.getByRole('dialog');
    expect(panel).toBeInTheDocument();
    expect(panel.style.top).toBe(`${TOPBAR_HEIGHT}px`);
    expect(TOPBAR_HEIGHT).toBeGreaterThan(0);
  });
});

describe('TicketDrawer — opening a captured trace', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  const withTrace = {
    ...mockTicketDetail,
    evidence: [
      {
        attempt: 2,
        attempt_id: 12,
        ref: 'claude:session:9b0e67d3-772f-45cf-85b3-e95832ad150d',
        trace_bytes: 741553,
      },
    ],
  };

  it('makes a ref with a captured trace clickable, and says how big it is', async () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => withTrace });

    render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

    await waitFor(() => expect(screen.getByText('Evidence')).toBeInTheDocument());
    expect(screen.getByTestId('open-trace-12')).toBeInTheDocument();
    expect(screen.getByText(/724\.2 KB trace/)).toBeInTheDocument();
  });

  it('opens the trace modal on the ref, fetching that attempt', async () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => withTrace });

    render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);
    await waitFor(() => expect(screen.getByTestId('open-trace-12')).toBeInTheDocument());

    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        attempt_id: 12, attempt: 2, ticket_id: 'test-run/t-0', run_id: 'test-run',
        ref: 'claude:session:9b0e67d3', lines: 1, bytes: 10, unparsed: 0, counts: {},
        records: [{ line: 0, kind: 'prompt', role: 'user', ts: null, title: '', text: 'the goal' }],
      }),
    });

    fireEvent.click(screen.getByTestId('open-trace-12'));

    await waitFor(() =>
      expect(
        mockFetch.mock.calls.some((c: any[]) => String(c[0]).includes('/api/attempts/12/trace')),
      ).toBe(true),
    );
    expect(await screen.findByText('the goal')).toBeInTheDocument();
  });

  it('leaves a ref without a captured trace copy-only', async () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => mockTicketDetail });

    render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

    await waitFor(() => expect(screen.getByText('Evidence')).toBeInTheDocument());
    expect(screen.queryByTestId(/^open-trace-/)).toBeNull();
    expect(screen.getAllByText('s3://results/ticket-1.json').length).toBeGreaterThan(0);
  });

  it('explains why older attempts are not openable', async () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => mockTicketDetail });

    render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

    await waitFor(() => expect(screen.getByText('Evidence')).toBeInTheDocument());
    expect(screen.getByText(/ran before that/)).toBeInTheDocument();
  });
});

describe('TicketDrawer — the result ref matches the evidence ref', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it('makes the Result host path openable too when its trace was captured', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        ...mockTicketDetail,
        result: { ...mockTicketDetail.result, result_ref: 'claude:session:abc' },
        evidence: [
          { attempt: 2, attempt_id: 12, ref: 'claude:session:abc', trace_bytes: 4096 },
        ],
      }),
    });

    render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

    await waitFor(() => expect(screen.getByTestId('open-trace-result-12')).toBeInTheDocument());
    expect(screen.getByText('Trace:')).toBeInTheDocument();
  });

  it('leaves the Result host path copy-only when no trace was captured', async () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => mockTicketDetail });

    render(<TicketDrawer isOpen={true} ticket={mockTicket} onClose={() => {}} />);

    await waitFor(() => expect(screen.getByText('Host path:')).toBeInTheDocument());
    expect(screen.queryByTestId(/^open-trace-result-/)).toBeNull();
  });
});
