import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import Review from './Review';

const mockFetch = vi.fn();
(globalThis as any).fetch = mockFetch;

/** A reduction that is holding a ticket for a human — the only kind that queues. */
const holding = {
  id: 1, run_id: 'r', phase: 'work', kind: 'root_causes', review_state: 'pending',
  json: { title: 'Null pointer in module X' },
  member_ticket_ids: ['r/t-1'],
  member_tickets: [{ id: 'r/t-1', state: 'needs_human', phase: 'work' }],
};

/** A reduction that is pure output — pending forever, deciding nothing. */
const output = {
  id: 2, run_id: 'r', phase: 'report', kind: 'research_report', review_state: 'pending',
  json: { report: '# Report\n\nbody'.repeat(30) },
  member_ticket_ids: [], member_tickets: [],
};

function respond(body: any) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

describe('Review', () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockFetch.mockImplementation(() => respond([holding, output]));
  });

  it('queues only what is actually holding a ticket', async () => {
    render(<Review runId="r" />);

    expect(await screen.findByText('Null pointer in module X')).toBeInTheDocument();
    expect(screen.queryByText(/research_report/)).toBeNull();
    expect(screen.getByText(/1 waiting on a decision/)).toBeInTheDocument();
  });

  it('offers the decision on a queued reduction', async () => {
    render(<Review runId="r" />);
    await screen.findByText('Null pointer in module X');

    expect(screen.getByRole('button', { name: /accept/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /reject/i })).toBeInTheDocument();
  });

  it('says plainly what the decision does to the ticket', async () => {
    render(<Review runId="r" />);
    await screen.findByText('Null pointer in module X');

    expect(screen.getByText(/settles the tickets this reduction is holding/i)).toBeInTheDocument();
  });

  it('accepts through the API and refreshes', async () => {
    render(<Review runId="r" />);
    await screen.findByText('Null pointer in module X');
    mockFetch.mockClear();
    mockFetch.mockImplementation(() => respond([]));

    fireEvent.click(screen.getByRole('button', { name: /accept/i }));

    await waitFor(() =>
      expect(
        mockFetch.mock.calls.some(
          (c: any[]) => String(c[0]).includes('/api/reductions/1/accept'),
        ),
      ).toBe(true),
    );
  });

  it('asks before rejecting, because rejecting fails the ticket', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<Review runId="r" />);
    await screen.findByText('Null pointer in module X');
    mockFetch.mockClear();

    fireEvent.click(screen.getByRole('button', { name: /reject/i }));

    expect(confirmSpy).toHaveBeenCalled();
    expect(mockFetch).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('surfaces a refused decision rather than looking like it worked', async () => {
    render(<Review runId="r" />);
    await screen.findByText('Null pointer in module X');
    mockFetch.mockImplementation(() =>
      Promise.resolve({
        ok: false, status: 409, statusText: 'Conflict',
        json: () => Promise.resolve({ detail: 'reduction 1 is accepted, not pending' }),
      }),
    );

    fireEvent.click(screen.getByRole('button', { name: /accept/i }));

    expect(await screen.findByTestId('review-error')).toHaveTextContent('not pending');
  });

  it('is empty, and says why, when a run produced only output', async () => {
    // The honest state for a research run: plenty banked, nothing to decide.
    mockFetch.mockImplementation(() => respond([output]));
    render(<Review runId="r" />);

    expect(await screen.findByText(/nothing waiting on you/i)).toBeInTheDocument();
    expect(screen.getByText(/none of which is holding a ticket/i)).toBeInTheDocument();
  });

  it('points at Outputs when that is where the content is', async () => {
    const onGoToOutputs = vi.fn();
    mockFetch.mockImplementation(() => respond([output]));
    render(<Review runId="r" onGoToOutputs={onGoToOutputs} />);

    fireEvent.click(await screen.findByTestId('go-to-outputs'));

    expect(onGoToOutputs).toHaveBeenCalled();
  });

  it('explains itself when the run has no reductions at all', async () => {
    mockFetch.mockImplementation(() => respond([]));
    render(<Review runId="r" />);

    expect(await screen.findByText(/routes a ticket to needs_human/i)).toBeInTheDocument();
  });
});
