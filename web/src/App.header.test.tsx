/**
 * The run header as App mounts it: drawn from the selected run's /api/runs row
 * above the run tabs, following the run through stream-triggered refetches,
 * with ‹ › and `]` agreeing and RunControl keyed on the run.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within, act } from '@testing-library/react';
import App from './App';
import * as client from './api/client';
import type { Event, Run, RunDetail, RunMetrics } from './api/client';
import * as useEventStreamModule from './hooks/useEventStream';

vi.mock('./api/client');
vi.mock('./hooks/useEventStream');

const row = (id: string, over: Partial<Run> = {}): Run => ({
  id,
  playbook: 'pb',
  site: 'local',
  state: 'running',
  phase: 'work',
  base_ref: 'main',
  created_at: 1_000_000,
  updated_at: 1_000_100,
  tickets: { done: 1, queued: 1 },
  has_view: false,
  awaiting: 0,
  subject: null,
  ...over,
});

const detailOf = (r: Run): RunDetail => ({
  id: r.id,
  playbook: r.playbook,
  site: r.site,
  state: r.state,
  phase: r.phase,
  base_ref: r.base_ref,
  created_at: r.created_at,
  updated_at: r.updated_at,
  tickets: r.tickets,
  has_view: r.has_view,
  config: {},
  phases: [],
});

const zeroMetrics: RunMetrics = {
  run_id: '',
  bucket_s: 60,
  buckets: [],
  totals: { attempts: 0, done: 0, failed: 0, results: 0, tickets: 0 },
  retry_rate: 0,
  mean_time_to_result_s: null,
  by_phase: [],
  by_state: {},
};

// run-a is newer, so the Active group reads run-a, run-b.
let rows: Run[];
let stream: ReturnType<typeof useEventStreamModule.useEventStream>;
let eventId = 0;

/** Deliver one stream event, as the shared buffer would, and re-render App. */
function push(view: ReturnType<typeof render>, kind: string, runId: string) {
  eventId += 1;
  const e: Event = {
    id: eventId,
    ts: 1_000_300,
    kind,
    run_id: runId,
    ticket_id: null,
    host: null,
    message: null,
    data: {},
  };
  stream = { ...stream, events: [...stream.events, e], lastEvent: e };
  view.rerender(<App />);
}

/** Point the address at a route, as a followed link or Back would. */
function go(hash: string) {
  act(() => {
    window.history.replaceState(null, '', hash);
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  });
}

const header = () => screen.getByRole('heading', { level: 1 }).closest('header') as HTMLElement;

async function mount() {
  const view = render(<App />);
  go('#/runs/run-a/summary');
  await waitFor(() =>
    expect(screen.getByRole('heading', { level: 1, name: 'run-a · pb' })).toBeInTheDocument(),
  );
  return view;
}

describe('the run header in App', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.history.replaceState(null, '', '/');
    rows = [row('run-a', { created_at: 1_000_200 }), row('run-b', { created_at: 1_000_100 })];
    vi.mocked(client.fetchHealth).mockResolvedValue({ status: 'ok', version: '0.1.0', home: '/tmp/hermes' });
    vi.mocked(client.fetchRuns).mockImplementation(async () => rows);
    vi.mocked(client.fetchRun).mockImplementation(async (id: string) =>
      detailOf(rows.find((r) => r.id === id)!),
    );
    vi.mocked(client.fetchReductions).mockResolvedValue([]);
    vi.mocked(client.fetchNeedsYou).mockResolvedValue([]);
    vi.mocked(client.fetchEvents).mockResolvedValue([]);
    vi.mocked(client.fetchEventKinds).mockResolvedValue([]);
    vi.mocked(client.fetchCrew).mockResolvedValue([]);
    vi.mocked(client.fetchRunMetrics).mockResolvedValue(zeroMetrics);
    stream = { connected: true, events: [], lastEvent: null, authError: false };
    vi.mocked(useEventStreamModule.useEventStream).mockImplementation(() => stream);
  });

  it("draws the header above the run tabs from the selected run's row, before its detail arrives", async () => {
    vi.mocked(client.fetchRun).mockReturnValue(new Promise<RunDetail>(() => {}));
    await mount();

    const h = header();
    expect(within(h).getByText('running')).toBeInTheDocument();
    expect(within(h).getByText('work')).toBeInTheDocument();
    expect(within(h).getByText('1 of 2 done')).toBeInTheDocument();
    expect(within(h).getByRole('button', { name: 'Pause' })).toBeInTheDocument();
    expect(within(h).getByRole('link', { name: 'Previous run' })).toHaveAttribute('aria-disabled', 'true');
    expect(within(h).getByRole('link', { name: 'Next run' })).toHaveAttribute('href', '#/runs/run-b/summary');

    const summaryTab = screen.getByRole('link', { name: 'Summary' });
    expect(h.contains(summaryTab)).toBe(false);
    expect(h.compareDocumentPosition(summaryTab) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("points ‹ › at the rail's visible neighbours, on the current run tab without ?ticket=", async () => {
    // run-b waits on you, so the rail reads run-b (Needs you) above run-a (Active),
    // the reverse of the list's order.
    rows = [row('run-a', { created_at: 1_000_200 }), row('run-b', { created_at: 1_000_100, awaiting: 1 })];
    vi.mocked(client.fetchRun).mockReturnValue(new Promise<RunDetail>(() => {}));
    render(<App />);
    go('#/runs/run-a/tickets?ticket=run-a/t-1');

    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 1, name: 'run-a · pb' })).toBeInTheDocument(),
    );
    const h = header();
    expect(within(h).getByRole('link', { name: 'Previous run' })).toHaveAttribute('href', '#/runs/run-b/tickets');
    expect(within(h).getByRole('link', { name: 'Next run' })).toHaveAttribute('aria-disabled', 'true');
  });

  it('renders no header, so no ‹ ›, when the home has no runs', async () => {
    rows = [];
    render(<App />);

    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 1, name: /no runs yet/i })).toBeInTheDocument(),
    );
    expect(screen.queryByRole('link', { name: 'Previous run' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Next run' })).not.toBeInTheDocument();
  });

  it('falls back to the run detail, with no ⚑, when the run list fails to load', async () => {
    rows = [row('run-a', { awaiting: 2 })];
    vi.mocked(client.fetchRuns).mockRejectedValue(new Error('boom'));
    render(<App />);
    go('#/runs/run-a/summary');

    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 1, name: 'run-a · pb' })).toBeInTheDocument(),
    );
    const h = header();
    expect(within(h).queryByRole('link', { name: /waiting on you/ })).not.toBeInTheDocument();
    expect(within(h).getByRole('link', { name: 'Previous run' })).toHaveAttribute('aria-disabled', 'true');
    expect(within(h).getByRole('link', { name: 'Next run' })).toHaveAttribute('aria-disabled', 'true');
  });

  it('relabels the header failed on a run_failed event for the selected run, with Reopen and no Pause or Stop', async () => {
    const view = await mount();

    rows = [row('run-a', { created_at: 1_000_200, state: 'failed', updated_at: 1_000_300 }), rows[1]];
    push(view, 'run_failed', 'run-a');

    await waitFor(() => expect(within(header()).getByText('failed')).toBeInTheDocument());
    expect(within(header()).queryByRole('button', { name: 'Pause' })).not.toBeInTheDocument();
    expect(within(header()).queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument();
    expect(within(header()).getByRole('button', { name: 'Reopen' })).toBeInTheDocument();
  });

  it('drops an open Stop confirmation on ], and › pointed where ] went', async () => {
    await mount();
    const nextHref = within(header()).getByRole('link', { name: 'Next run' }).getAttribute('href');
    fireEvent.click(within(header()).getByRole('button', { name: 'Stop' }));
    expect(screen.getByText(/confirm stop/i)).toBeInTheDocument();

    fireEvent.keyDown(document.body, { key: ']' });

    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 1, name: 'run-b · pb' })).toBeInTheDocument(),
    );
    expect(window.location.hash).toBe(nextHref);
    expect(screen.queryByText(/confirm stop/i)).not.toBeInTheDocument();
    expect(within(header()).getByRole('button', { name: 'Stop' })).toBeInTheDocument();
  });

  it('moves focus to Resume after Pause succeeds, refetching the list and the detail', async () => {
    vi.mocked(client.pauseRun).mockImplementation(async () => {
      rows = [row('run-a', { created_at: 1_000_200, state: 'paused' }), rows[1]];
      return { state: 'paused' };
    });
    await mount();
    // Summary, drawn once the detail arrives, adds no second set of controls.
    await screen.findByText('No phases yet.');
    expect(screen.getAllByRole('button', { name: 'Pause' })).toHaveLength(1);
    const runsCalls = vi.mocked(client.fetchRuns).mock.calls.length;
    const detailCalls = vi.mocked(client.fetchRun).mock.calls.length;

    fireEvent.click(within(header()).getByRole('button', { name: 'Pause' }));

    await waitFor(() =>
      expect(within(header()).getByRole('button', { name: 'Resume' })).toHaveFocus(),
    );
    expect(client.pauseRun).toHaveBeenCalledWith('run-a');
    expect(within(header()).getByText('paused')).toBeInTheDocument();
    expect(vi.mocked(client.fetchRuns).mock.calls.length).toBeGreaterThan(runsCalls);
    expect(vi.mocked(client.fetchRun).mock.calls.length).toBeGreaterThan(detailCalls);
  });

  it('clears ⚑ on a reduction_accepted event for the selected run', async () => {
    rows = [row('run-a', { created_at: 1_000_200, awaiting: 1 }), rows[1]];
    const view = await mount();
    expect(within(header()).getByRole('link', { name: '1 waiting on you' })).toHaveAttribute(
      'href',
      '#/needs-you?run=run-a',
    );

    rows = [row('run-a', { created_at: 1_000_200, awaiting: 0 }), rows[1]];
    push(view, 'reduction_accepted', 'run-a');

    await waitFor(() =>
      expect(within(header()).queryByRole('link', { name: /waiting on you/ })).not.toBeInTheDocument(),
    );
  });

  it('keeps focus on › as the selection moves to the run it named', async () => {
    await mount();
    const next = within(header()).getByRole('link', { name: 'Next run' });
    next.focus();

    go('#/runs/run-b/summary');

    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 1, name: 'run-b · pb' })).toBeInTheDocument(),
    );
    expect(next).toHaveFocus();
    expect(next).toHaveAttribute('aria-disabled', 'true');
    expect(within(header()).getByRole('link', { name: 'Previous run' })).toHaveAttribute(
      'href',
      '#/runs/run-a/summary',
    );
  });
});
