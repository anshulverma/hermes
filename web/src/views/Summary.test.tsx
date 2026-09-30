/**
 * Summary: the key numbers, the playbook's view or the phase timeline, and the
 * side column (what waits on you in this run, its recent events). The view
 * loader is stubbed; its own rules are pinned in PlaybookView.test.tsx.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import Summary from './Summary';
import * as client from '../api/client';
import type { Event, Reduction, RunDetail, RunMetrics } from '../api/client';

vi.mock('../api/client');
vi.mock('./PlaybookView', () => ({
  default: ({ runId, liveTick, variant }: { runId: string; liveTick?: number; variant?: string }) => (
    <div data-testid="playbook-view">{`view for ${runId} · tick ${liveTick} · variant ${variant}`}</div>
  ),
}));

type Waiting = Awaited<ReturnType<typeof client.fetchNeedsYou>>;

const nowS = () => Date.now() / 1000;

const run: RunDetail = {
  id: 'run-001',
  playbook: 'pb',
  site: 'local',
  state: 'running',
  phase: 'work',
  base_ref: 'main',
  created_at: 1_790_000_000,
  updated_at: 1_790_000_300,
  config: {},
  has_view: false,
  tickets: { queued: 15, dispatched: 3, running: 5, reducing: 1, done: 42, parked: 4, failed: 2 },
  phases: [
    {
      name: 'work',
      counts: { queued: 15, dispatched: 3, running: 5, done: 30, parked: 4, failed: 2 },
      current: true,
    },
    { name: 'reduce', counts: { reducing: 1, done: 12 }, current: false },
  ],
};

function metricsFor(results: number, retry_rate: number, mean: number | null): RunMetrics {
  return {
    run_id: 'run-001',
    bucket_s: 60,
    buckets: [],
    totals: { attempts: results, done: results, failed: 0, results, tickets: results },
    retry_rate,
    mean_time_to_result_s: mean,
    by_phase: [],
    by_state: {},
  };
}

function reduction(id: number, phase: string, kind: string, json: Record<string, unknown>): Reduction {
  return { id, run_id: 'run-001', phase, kind, json, review_state: 'pending', member_ticket_ids: [], member_tickets: [] };
}

function waitingItem(id: number, run_id: string, title: string, created_at: number): Waiting[number] {
  return {
    id,
    run_id,
    phase: 'decision',
    kind: 'verdict',
    json: { title },
    review_state: 'pending',
    member_ticket_ids: [`${run_id}/t-${id}`],
    member_tickets: [{ id: `${run_id}/t-${id}`, state: 'needs_human', phase: 'decision' }],
    playbook: 'pb',
    created_at,
  };
}

function event(id: number, run_id: string | null, kind: string): Event {
  return { id, ts: nowS() - 5, kind, run_id, ticket_id: null, host: null, message: null, data: {} };
}

/** A promise the test settles itself. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

describe('Summary', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(client.fetchRunMetrics).mockResolvedValue(metricsFor(8, 0.25, 90));
    vi.mocked(client.fetchNeedsYou).mockResolvedValue([]);
    vi.mocked(client.fetchEvents).mockResolvedValue([]);
    vi.mocked(client.fetchReductions).mockResolvedValue([]);
  });

  it('shows the key numbers: tickets, done, in flight, parked, failed, queued, retry rate and mean time to result', async () => {
    render(<Summary run={run} streamEvents={[]} viewTick={0} />);

    expect(screen.getByText('72')).toBeInTheDocument(); // every state
    expect(screen.getByText('42')).toBeInTheDocument(); // done
    // Claimed work waits in dispatched, then reducing: 3 + 5 + 1, not running alone.
    expect(screen.getByText('in flight')).toBeInTheDocument();
    expect(screen.getByText('9')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument(); // parked
    expect(screen.getByText('2')).toBeInTheDocument(); // failed
    expect(screen.getByText('15')).toBeInTheDocument(); // queued
    expect(await screen.findByText('25%')).toBeInTheDocument();
    expect(screen.getByText('retry rate')).toBeInTheDocument();
    expect(screen.getByText('mean time to result')).toBeInTheDocument();
    expect(screen.getByText('1m 30s')).toBeInTheDocument();
    expect(client.fetchRunMetrics).toHaveBeenCalledWith('run-001');
    // The metrics endpoint reports no cost, and the header owns elapsed.
    expect(screen.queryByText(/cost/i)).toBeNull();
    expect(screen.queryByText(/elapsed/i)).toBeNull();
  });

  it("shows '—' for retry rate and mean time to result while the run has no results", async () => {
    // retry_rate is 0.0, not null, with no results: it must not read as a real 0%.
    vi.mocked(client.fetchRunMetrics).mockResolvedValue(metricsFor(0, 0, null));
    render(<Summary run={run} streamEvents={[]} viewTick={0} />);

    await waitFor(() => expect(client.fetchRunMetrics).toHaveBeenCalled());
    await act(async () => {});
    expect(screen.getAllByText('—')).toHaveLength(2);
    expect(screen.queryByText('0%')).toBeNull();
  });

  it('shows the playbook view for a run that has one, fed the view tick, and no phase timeline', () => {
    const withView: RunDetail = { ...run, has_view: true };
    const { rerender } = render(<Summary run={withView} streamEvents={[]} viewTick={3} />);

    // The default variant: the view's own section, exactly today's Playbook tab.
    expect(screen.getByTestId('playbook-view')).toHaveTextContent('view for run-001 · tick 3 · variant undefined');
    rerender(<Summary run={withView} streamEvents={[]} viewTick={4} />);
    expect(screen.getByTestId('playbook-view')).toHaveTextContent('tick 4');
    expect(screen.queryByTestId('phase-rail')).toBeNull();
    expect(screen.queryByText('No phases yet.')).toBeNull();
    expect(client.fetchReductions).not.toHaveBeenCalled();
  });

  it("shows the phase timeline for a run with no view, each phase's newest headline linking to Outputs", async () => {
    vi.mocked(client.fetchReductions).mockResolvedValue([
      reduction(1, 'work', 'item_analysis', { title: 'First pass' }),
      reduction(5, 'work', 'item_analysis', { title: 'Second pass' }),
      reduction(3, 'reduce', 'final_report', {}),
    ]);
    render(<Summary run={run} streamEvents={[]} viewTick={0} />);

    expect(screen.getByText('work 59')).toBeInTheDocument();
    expect(screen.getByText('reduce 13')).toBeInTheDocument();
    const newest = await screen.findByRole('link', { name: 'Second pass' });
    expect(newest).toHaveAttribute('href', '#/runs/run-001/outputs');
    // A reduction with no title falls back to its kind.
    expect(screen.getByRole('link', { name: 'final_report' })).toHaveAttribute('href', '#/runs/run-001/outputs');
    expect(screen.queryByText('First pass')).toBeNull();
    expect(client.fetchReductions).toHaveBeenCalledWith('run-001');
    expect(screen.queryByTestId('playbook-view')).toBeNull();
  });

  it("reads 'No phases yet.' for a run with no phases", () => {
    render(<Summary run={{ ...run, phase: null, phases: [] }} streamEvents={[]} viewTick={0} />);

    expect(screen.getByText('No phases yet.')).toBeInTheDocument();
    expect(screen.queryByTestId('phase-rail')).toBeNull();
  });

  it('colours each phase pill by what its tickets came to, not by whether it is current', () => {
    const r: RunDetail = {
      ...run,
      phase: 't04-ops',
      phases: [
        { name: 't01-pm', counts: { done: 1 }, current: false },
        { name: 't02-eng', counts: { failed: 1 }, current: false },
        { name: 't03-qa', counts: { needs_human: 1 }, current: false },
        // work waiting in Needs you outranks a failure beside it
        { name: 'solve', counts: { failed: 1, needs_human: 1 }, current: false },
        // `running` is a state the engine barely writes: claimed work sits in
        // `dispatched` until its result lands, then in `reducing`.
        { name: 't04-ops', counts: { dispatched: 1 }, current: true },
        { name: 't05-sre', counts: { reducing: 1 }, current: false },
        { name: 't06-sec', counts: { parked: 1 }, current: false },
        { name: 'fan', counts: { done: 3, queued: 2 }, current: false },
        { name: 'report', counts: {}, current: false },
      ],
    };
    render(<Summary run={r} streamEvents={[]} viewTick={0} />);

    const stateOf = (label: string) => screen.getByText(label).getAttribute('data-state');
    expect(stateOf('t01-pm')).toBe('done');
    expect(stateOf('t02-eng')).toBe('failed');
    expect(stateOf('t03-qa')).toBe('needs-human');
    expect(stateOf('solve 2')).toBe('needs-human');
    expect(stateOf('t04-ops')).toBe('running');
    expect(stateOf('t05-sre')).toBe('running');
    expect(stateOf('t06-sec')).toBe('parked');
    expect(stateOf('fan 5')).toBe('queued');
    expect(stateOf('report')).toBe('queued');
  });

  it("keeps a finished run's last phase from reading as running", () => {
    // A run that is over still names its last phase as current.
    const r: RunDetail = {
      ...run,
      state: 'done',
      phases: [{ name: 'solve', counts: { done: 11, failed: 1 }, current: true }],
    };
    render(<Summary run={r} streamEvents={[]} viewTick={0} />);

    expect(screen.getByText('solve 12').getAttribute('data-state')).toBe('failed');
  });

  it.each(['done', 'failed'])(
    "ends a %s run's zero-ticket last phase as the run did, without a live pulse",
    (state) => {
      // A closing phase that mints no tickets has no counts to read.
      const r: RunDetail = {
        ...run,
        state,
        phases: [
          { name: 'decision', counts: { [state]: 1 }, current: false },
          { name: 'ruling', counts: {}, current: true },
        ],
      };
      render(<Summary run={r} streamEvents={[]} viewTick={0} />);

      const pill = screen.getByText('ruling');
      expect(pill.getAttribute('data-state')).toBe(state);
      const bar = pill.parentElement!.parentElement!.firstChild as HTMLElement;
      expect(bar.style.animation).toBe('none');
    },
  );

  it('pulses the current phase of a live run', () => {
    render(<Summary run={run} streamEvents={[]} viewTick={0} />);

    const bar = screen.getByText('work 59').parentElement!.parentElement!.firstChild as HTMLElement;
    expect(bar.style.animation).toContain('fm-pulse');
  });

  it('lets the phase rail wrap rather than squeeze many phases into one row', () => {
    const r: RunDetail = {
      ...run,
      phases: Array.from({ length: 17 }, (_, i) => ({
        name: `t${i + 1}`,
        counts: { done: 1 },
        current: false,
      })),
    };
    render(<Summary run={r} streamEvents={[]} viewTick={0} />);

    const rail = screen.getByText('t1').closest('[data-testid="phase-rail"]') as HTMLElement;
    expect(rail.style.flexWrap).toBe('wrap');
    expect(rail.children).toHaveLength(17);
  });

  it("lists this run's waiting items as plain text with their age, and one link to rule on them in Needs you", async () => {
    // The Needs you rule, not a second one: the cross-run list, kept to this run.
    vi.mocked(client.fetchNeedsYou).mockResolvedValue([
      waitingItem(1, 'run-001', 'Pick the rollout plan', nowS() - 150),
      waitingItem(2, 'run-002', 'Another run entirely', nowS() - 60),
      waitingItem(3, 'run-001', 'Approve the verdict', nowS() - 3 * 3600 - 600),
    ]);
    render(<Summary run={run} streamEvents={[]} viewTick={0} />);

    const waiting = screen.getByRole('region', { name: 'Waiting on you here' });
    expect(await within(waiting).findByText('Pick the rollout plan')).toBeInTheDocument();
    expect(within(waiting).getByText('Approve the verdict')).toBeInTheDocument();
    expect(within(waiting).queryByText('Another run entirely')).toBeNull();
    expect(within(waiting).getByText('2 minutes ago')).toBeInTheDocument();
    expect(within(waiting).getByText('3 hours ago')).toBeInTheDocument();
    // No per-item link and no preview: one link for the block.
    const links = within(waiting).getAllByRole('link');
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveTextContent('Rule on these in Needs you');
    expect(links[0]).toHaveAttribute('href', '#/needs-you?run=run-001');
  });

  it("reads 'Nothing waiting on you in this run.' when nothing in it waits", async () => {
    vi.mocked(client.fetchNeedsYou).mockResolvedValue([
      waitingItem(2, 'run-002', 'Another run entirely', nowS() - 60),
    ]);
    render(<Summary run={run} streamEvents={[]} viewTick={0} />);

    const waiting = screen.getByRole('region', { name: 'Waiting on you here' });
    expect(await within(waiting).findByText('Nothing waiting on you in this run.')).toBeInTheDocument();
    expect(within(waiting).queryByRole('link')).toBeNull();
  });

  it('lists the ten newest events, merging stream events for this run newer than the fetch', async () => {
    vi.mocked(client.fetchEvents).mockResolvedValue(
      Array.from({ length: 10 }, (_, i) => event(10 - i, 'run-001', `kind-${10 - i}`)),
    );
    const { rerender } = render(<Summary run={run} streamEvents={[]} viewTick={0} />);
    const recent = screen.getByRole('region', { name: 'Recent events' });
    await waitFor(() => expect(within(recent).getAllByRole('listitem')).toHaveLength(10));

    rerender(
      <Summary
        run={run}
        streamEvents={[event(5, 'run-001', 'kind-5'), event(11, 'run-001', 'kind-11'), event(12, 'run-002', 'kind-12')]}
        viewTick={0}
      />,
    );

    const rows = within(recent).getAllByRole('listitem');
    expect(rows).toHaveLength(10);
    expect(rows[0]).toHaveTextContent(/^kind-11/);
    expect(rows[9]).toHaveTextContent(/^kind-2/);
    expect(within(recent).queryByText('kind-12')).toBeNull();
    expect(within(recent).queryByText('kind-1')).toBeNull();
    expect(within(recent).getByRole('link', { name: 'All events in Activity' })).toHaveAttribute(
      'href',
      '#/activity?run=run-001',
    );
    // The merge is the only update: a trigger never refetches recent events.
    expect(client.fetchEvents).toHaveBeenCalledTimes(1);
    expect(client.fetchEvents).toHaveBeenCalledWith({ run: 'run-001', order: 'desc', limit: 10 });
  });

  it("reads 'No events.' when the run has none", async () => {
    render(<Summary run={run} streamEvents={[]} viewTick={0} />);

    const recent = screen.getByRole('region', { name: 'Recent events' });
    expect(await within(recent).findByText('No events.')).toBeInTheDocument();
  });

  it("refetches metrics, waiting items and phase headlines on an event for this run, never on another run's", async () => {
    const { rerender } = render(<Summary run={run} streamEvents={[]} viewTick={0} />);
    await waitFor(() => expect(client.fetchRunMetrics).toHaveBeenCalledTimes(1));
    expect(client.fetchNeedsYou).toHaveBeenCalledTimes(1);
    expect(client.fetchReductions).toHaveBeenCalledTimes(1);

    const other = [event(1, 'run-002', 'result_recorded')];
    rerender(<Summary run={run} streamEvents={other} viewTick={0} />);
    expect(client.fetchRunMetrics).toHaveBeenCalledTimes(1);

    rerender(<Summary run={run} streamEvents={[...other, event(2, 'run-001', 'result_recorded')]} viewTick={0} />);

    // The throttle's leading edge: at once, all three together.
    await waitFor(() => expect(client.fetchRunMetrics).toHaveBeenCalledTimes(2));
    expect(client.fetchNeedsYou).toHaveBeenCalledTimes(2);
    expect(client.fetchReductions).toHaveBeenCalledTimes(2);
    expect(client.fetchEvents).toHaveBeenCalledTimes(1);
  });

  it('shows its own alert and Retry when a block fails, and renders the rest', async () => {
    vi.mocked(client.fetchRunMetrics).mockRejectedValueOnce(new Error('boom'));
    vi.mocked(client.fetchEvents).mockRejectedValueOnce(new Error('boom'));
    render(<Summary run={run} streamEvents={[]} viewTick={0} />);

    await waitFor(() => expect(screen.getAllByRole('alert')).toHaveLength(2));
    expect(screen.getByText("Couldn't load metrics.")).toBeInTheDocument();
    expect(screen.getByText("Couldn't load recent events.")).toBeInTheDocument();
    expect(screen.getByText('72')).toBeInTheDocument();
    expect(screen.getByText('Nothing waiting on you in this run.')).toBeInTheDocument();
    expect(screen.getByTestId('phase-rail')).toBeInTheDocument();

    const metricsAlert = screen.getByText("Couldn't load metrics.").closest('[role="alert"]') as HTMLElement;
    fireEvent.click(within(metricsAlert).getByRole('button', { name: 'Retry' }));

    expect(await screen.findByText('25%')).toBeInTheDocument();
    expect(screen.getAllByRole('alert')).toHaveLength(1);
    expect(client.fetchRunMetrics).toHaveBeenCalledTimes(2);
    expect(client.fetchEvents).toHaveBeenCalledTimes(1);
  });

  it('drops metrics, waiting items and events that land after a switch to another run', async () => {
    const metricsA = deferred<RunMetrics>();
    const waitingA = deferred<Waiting>();
    const eventsA = deferred<Event[]>();
    vi.mocked(client.fetchRunMetrics).mockImplementation((id: string) =>
      id === 'run-001' ? metricsA.promise : Promise.resolve(metricsFor(4, 0.5, 30)),
    );
    vi.mocked(client.fetchNeedsYou)
      .mockReturnValueOnce(waitingA.promise)
      .mockResolvedValueOnce([waitingItem(2, 'run-002', 'Fresh B item', nowS() - 60)]);
    vi.mocked(client.fetchEvents).mockImplementation((filters) =>
      filters?.run === 'run-001' ? eventsA.promise : Promise.resolve([event(20, 'run-002', 'kind-b')]),
    );

    const { rerender } = render(<Summary run={run} streamEvents={[]} viewTick={0} />);
    rerender(<Summary run={{ ...run, id: 'run-002' }} streamEvents={[]} viewTick={0} />);
    expect(await screen.findByText('50%')).toBeInTheDocument();
    expect(await screen.findByText('Fresh B item')).toBeInTheDocument();
    expect(await screen.findByText('kind-b')).toBeInTheDocument();

    // run-001's answers arrive late, after the switch.
    await act(async () => {
      metricsA.resolve(metricsFor(4, 0.25, 90));
      waitingA.resolve([waitingItem(1, 'run-002', 'Stale B item', nowS() - 60)]);
      eventsA.resolve([event(10, 'run-001', 'kind-a')]);
    });

    expect(screen.getByText('50%')).toBeInTheDocument();
    expect(screen.queryByText('25%')).toBeNull();
    expect(screen.getByText('Fresh B item')).toBeInTheDocument();
    expect(screen.queryByText('Stale B item')).toBeNull();
    expect(screen.getByText('kind-b')).toBeInTheDocument();
    expect(screen.queryByText('kind-a')).toBeNull();
  });
});
