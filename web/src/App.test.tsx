import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within, act } from '@testing-library/react';
import App from './App';
import * as client from './api/client';
import type { Event, Run, RunDetail, RunMetrics } from './api/client';
import * as useEventStreamModule from './hooks/useEventStream';

vi.mock('./api/client');
vi.mock('./hooks/useEventStream');
// The host's metrics are not what this file tests; the stub names the run it was given.
vi.mock('./views/MetricsView', () => ({
  default: ({ runId }: { runId: string }) => <div data-testid="metrics-view">metrics for {runId}</div>,
}));
// Renders only for a run whose playbook has a view, with one control inside,
// so a test can hold focus in the pane body and watch where it goes.
// It keeps the run it first mounted with, like the real loader, so a body that is
// not keyed on the run shows up as the previous run's id.
vi.mock('./views/PlaybookView', async () => {
  const { useState } = await import('react');
  const PlaybookViewStub = ({ runId, hasView, liveTick }: { runId: string; hasView: boolean; liveTick?: number }) => {
    const [mountedWith] = useState(runId);
    return hasView ? (
      <div data-testid="playbook-view">
        playbook view for {mountedWith} · tick {String(liveTick)} <button type="button">view action</button>
      </div>
    ) : null;
  };
  return { default: PlaybookViewStub };
});

const NOW = Math.floor(Date.now() / 1000);

const ZERO_METRICS: RunMetrics = {
  run_id: '',
  bucket_s: 60,
  buckets: [],
  totals: { attempts: 0, done: 0, failed: 0, results: 0, tickets: 0 },
  retry_rate: 0,
  mean_time_to_result_s: null,
  by_phase: [],
  by_state: {},
};

function run(id: string, over: Partial<Run> = {}): Run {
  return {
    id,
    playbook: 'pb',
    site: 'local',
    state: 'running',
    phase: 'work',
    base_ref: 'main',
    created_at: NOW - 3600,
    updated_at: NOW - 60,
    tickets: {},
    has_view: false,
    awaiting: 0,
    subject: null,
    ...over,
  };
}

/** The `/api/runs/{id}` shape of a run: no `awaiting`, no `subject`. */
function detailOf(r: Run, over: Partial<RunDetail> = {}): RunDetail {
  return {
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
    ...over,
  };
}

/** Serve these runs. Every `/api/runs` answer is a fresh array, as a real response is. */
function mockHome(runs: Run[], details: RunDetail[] = runs.map((r) => detailOf(r))) {
  vi.mocked(client.fetchRuns).mockImplementation(async () => runs.map((r) => ({ ...r })));
  vi.mocked(client.fetchRun).mockImplementation(async (id: string) => {
    const d = details.find((x) => x.id === id);
    if (!d) throw Object.assign(new Error(`Run '${id}' not found`), { status: 404 });
    return d;
  });
}

let stream: Event[] = [];
let nextEventId = 1000;

function streamState(over: { connected?: boolean; authError?: boolean } = {}) {
  return {
    connected: true,
    events: stream,
    lastEvent: stream.at(-1) ?? null,
    authError: false,
    ...over,
  } as ReturnType<typeof useEventStreamModule.useEventStream>;
}

function ev(kind: string, run_id: string | null): Event {
  return { id: nextEventId++, ts: NOW, kind, run_id, ticket_id: null, host: null, message: null, data: {} };
}

/** Deliver events on the shared stream, all of them in one render. */
async function deliver(rerender: ReturnType<typeof render>['rerender'], ...events: Event[]) {
  stream = [...stream, ...events];
  await act(async () => {
    rerender(<App />);
  });
}

/** Put a hash in the address as a pasted link would (no history entry). */
function go(hash: string) {
  window.history.replaceState(null, '', hash || window.location.pathname);
  window.dispatchEvent(new HashChangeEvent('hashchange'));
}

const rail = () => screen.getByRole('navigation', { name: 'Runs' });
const row = (id: string) => within(rail()).getByRole('link', { name: new RegExp(`^${id},`) });
const findRow = (id: string) => within(rail()).findByRole('link', { name: new RegExp(`^${id},`) });
const heading = (name: string) => screen.findByRole('heading', { level: 1, name });
/** Health and the first runs load are in: the header can be drawn from the detail before the list arrives. */
const settled = () => waitFor(() => expect(screen.queryByText('Loading Hermes…')).toBeNull());
const statusRegion = () => screen.getByTestId('status-region');
/** The pane side; the status region, which repeats the note's text, sits outside it. */
const inMain = () => within(screen.getByRole('main'));

/** Three running runs; the rail's visible order is run-c, run-b, run-a. */
const threeRuns = () => [
  run('run-c', { created_at: NOW - 60 }),
  run('run-b', { created_at: NOW - 120 }),
  run('run-a', { created_at: NOW - 180 }),
];

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  stream = [];
  go('');
  vi.mocked(useEventStreamModule.useEventStream).mockImplementation(() => streamState());
  vi.mocked(client.fetchHealth).mockResolvedValue({ status: 'ok', version: '0.1.0', home: '/tmp/hermes' });
  // Everything a view fetches on mount. Auto-mocked, each returns undefined,
  // which is not a promise.
  vi.mocked(client.fetchReductions).mockResolvedValue([]);
  vi.mocked(client.fetchTickets).mockResolvedValue([]);
  vi.mocked(client.fetchCrew).mockResolvedValue([]);
  vi.mocked(client.fetchEvents).mockResolvedValue([]);
  vi.mocked(client.fetchEventKinds).mockResolvedValue([]);
  vi.mocked(client.fetchNeedsYou).mockResolvedValue([]);
  vi.mocked(client.fetchRunMetrics).mockResolvedValue(ZERO_METRICS);
});

afterEach(() => {
  vi.useRealTimers();
  go('');
});

describe('App', () => {
  it('should render empty state when no runs exist', async () => {
    mockHome([]);

    render(<App />);

    expect(await heading('No runs yet')).toBeInTheDocument();
    expect(screen.getByText('Start one with `hermes run <playbook>`.')).toBeInTheDocument();
  });

  it('should render the selected run when runs exist', async () => {
    mockHome([run('run-001', { playbook: 'example' })]);

    render(<App />);

    expect(await heading('run-001 · example')).toBeInTheDocument();
    expect(await findRow('run-001')).toHaveAttribute('aria-current', 'page');
  });

  it('shows the run tabs as links, the current one marked', async () => {
    mockHome([run('run-001')]);
    go('#/runs/run-001/outputs');

    render(<App />);

    const tabs = await screen.findByRole('navigation', { name: 'Run tabs' });
    expect(within(tabs).getAllByRole('link').map((a) => [a.textContent, a.getAttribute('href')])).toEqual([
      ['Summary', '#/runs/run-001/summary'],
      ['Tickets', '#/runs/run-001/tickets'],
      ['Outputs', '#/runs/run-001/outputs'],
      ['Metrics', '#/runs/run-001/metrics'],
    ]);
    expect(within(tabs).getByRole('link', { name: 'Outputs' })).toHaveAttribute('aria-current', 'page');
    expect(within(tabs).getByRole('link', { name: 'Summary' })).not.toHaveAttribute('aria-current');
  });

  it('should handle API error gracefully', async () => {
    // The global error covers health only; a runs failure shows in the rail.
    vi.mocked(client.fetchHealth).mockRejectedValue(new Error('Network error'));
    mockHome([]);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('Error loading data')).toBeInTheDocument();
    });
    expect(screen.getByText('Network error')).toBeInTheDocument();
  });

  it('should show loading state initially', async () => {
    let healthy: (h: Awaited<ReturnType<typeof client.fetchHealth>>) => void = () => {};
    vi.mocked(client.fetchHealth).mockImplementation(() => new Promise((resolve) => (healthy = resolve)));
    vi.mocked(client.fetchRuns).mockImplementation(() => new Promise(() => {}));

    render(<App />);

    expect(screen.getByText('Loading Hermes…')).toBeInTheDocument();

    // Health alone does not lift it: it covers the first runs load too.
    await act(async () => {
      healthy({ status: 'ok', version: '0.1.0', home: '/tmp/hermes' });
      await new Promise((r) => setTimeout(r, 30));
    });
    expect(screen.getByText('Loading Hermes…')).toBeInTheDocument();
  });

  it('should show Activity tab in TopBar', async () => {
    mockHome([run('run-001')]);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('Activity')).toBeInTheDocument();
    });
  });

  it('should display auth error banner when WebSocket reports 4401', async () => {
    vi.mocked(useEventStreamModule.useEventStream).mockImplementation(() =>
      streamState({ connected: false, authError: true }),
    );
    mockHome([]);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/live updates unauthorized/i)).toBeInTheDocument();
    });
  });

  describe('tab in the URL', () => {
    function mockLoadedRun() {
      mockHome([run('run-001', { playbook: 'example' })]);
    }

    it('opens the tab named in the URL instead of the default (refresh restores it)', async () => {
      go('#crew');
      mockLoadedRun();

      render(<App />);

      await waitFor(() => {
        expect(screen.getByText(/no crew members/i)).toBeInTheDocument();
      });
      expect(window.location.hash).toBe('#/crew');
      expect(screen.queryByRole('heading', { level: 1, name: 'run-001 · example' })).toBeNull();
    });

    it("a host's current run links to #/runs/<id>/summary and its ticket to #/runs/<id>/tickets?ticket=<t>", async () => {
      go('#/crew');
      mockLoadedRun();
      vi.mocked(client.fetchCrew).mockResolvedValue([
        {
          id: 'host-a',
          site: 'local',
          state: 'busy',
          capabilities: [],
          resources: {},
          health: null,
          current_ticket: 'run-001/t1',
          current_run: 'run-001',
          current_phase: 'work',
          current_elapsed_s: 240,
          last_heartbeat: null,
          heartbeat_age_s: null,
        },
      ]);

      render(<App />);

      // Not `row`: that module-level helper finds rail rows.
      const hostRow = (await screen.findByText('host-a')).closest('div[role="button"]') as HTMLElement;
      // run-001 is the only run, and still it is named: Crew has no run in view.
      expect(hostRow).toHaveTextContent('work · 4m 0s · run-001');
      expect(within(hostRow).getByRole('link', { name: 'run-001' })).toHaveAttribute(
        'href',
        '#/runs/run-001/summary',
      );
      const ticket = within(hostRow).getByRole('link', { name: 'work' });
      expect(ticket).toHaveAttribute('href', '#/runs/run-001/tickets?ticket=run-001%2Ft1');
      expect(ticket).toHaveAttribute('title', 'run-001/t1');
    });

    it('goes to the Crew page when its top-bar link is clicked', async () => {
      mockLoadedRun();

      render(<App />);
      expect(await heading('run-001 · example')).toBeInTheDocument();

      fireEvent.click(screen.getByRole('link', { name: 'Crew' }));

      await waitFor(() => {
        expect(window.location.hash).toBe('#/crew');
      });
    });
  });

  describe('the summary tab', () => {
    // 'work' totals 18 tickets, so its pill reads 'work 18'.
    const phases: RunDetail['phases'] = [
      { name: 'work', counts: { queued: 5, running: 2, done: 10, failed: 1 }, current: true },
      { name: 'reduce', counts: {}, current: false },
    ];
    const withView = (id: string) => run(id, { playbook: 'pb-view', has_view: true });
    const noView = (id: string) => run(id, { playbook: 'pb' });

    /** Serve these rows, each detail carrying the two phases above. */
    function mockRuns(...rows: Run[]) {
      mockHome(rows, rows.map((r) => detailOf(r, { phases })));
    }

    const tabHrefs = () =>
      within(screen.getByRole('navigation', { name: 'Run tabs' }))
        .getAllByRole('link')
        .map((a) => a.getAttribute('href'));

    it('Summary shows the playbook view for a run that has one', async () => {
      mockRuns(withView('run-001'));
      go('#/runs/run-001/summary');

      render(<App />);

      await waitFor(() =>
        expect(screen.getByTestId('playbook-view')).toHaveTextContent('playbook view for run-001'),
      );
      expect(screen.queryByTestId('phase-rail')).toBeNull();
      expect(window.location.hash).toBe('#/runs/run-001/summary');
    });

    it('Summary shows the phase timeline for a run whose playbook ships no view', async () => {
      mockRuns(noView('run-001'));
      go('#/runs/run-001/summary');

      render(<App />);

      await waitFor(() => expect(screen.getByTestId('phase-rail')).toBeInTheDocument());
      expect(screen.getByText('work 18')).toBeInTheDocument();
      expect(screen.queryByTestId('playbook-view')).toBeNull();
    });

    it('hands the view the finding tick for the selected run only', async () => {
      // Drop liveTick={viewTick} and a live run's view stops refreshing on
      // reduction_created, which for turns arriving one at a time is the feature.
      mockRuns(withView('run-001'), noView('run-002'));
      go('#/runs/run-001/summary');
      const { rerender } = render(<App />);
      await waitFor(() => expect(screen.getByTestId('playbook-view')).toHaveTextContent('tick 0'));

      await deliver(rerender, ev('reduction_created', 'run-002'));
      expect(screen.getByTestId('playbook-view')).toHaveTextContent('tick 0');

      await deliver(rerender, ev('reduction_created', 'run-001'));
      await waitFor(() => expect(screen.getByTestId('playbook-view')).toHaveTextContent('tick 1'));
    });

    it('remounts the view when the reader switches to another run with one', async () => {
      // The loader keeps the run it first mounted with (so does the stub at the
      // top of this file): without the body's key the pane shows run-001's view
      // under run-002 for one round trip.
      mockRuns(withView('run-001'), withView('run-002'));
      go('#/runs/run-001/summary');
      render(<App />);
      await waitFor(() => expect(screen.getByTestId('playbook-view')).toHaveTextContent('run-001'));

      act(() => go('#/runs/run-002/summary'));

      await waitFor(() => expect(screen.getByTestId('playbook-view')).toHaveTextContent('run-002'));
    });

    it('shows the same four run tabs, and no Playbook tab, whether or not the run has a view', async () => {
      mockRuns(withView('run-001'), noView('run-002'));
      go('#/runs/run-001/summary');
      render(<App />);
      await waitFor(() => expect(screen.getByTestId('playbook-view')).toBeInTheDocument());
      expect(tabHrefs()).toEqual([
        '#/runs/run-001/summary',
        '#/runs/run-001/tickets',
        '#/runs/run-001/outputs',
        '#/runs/run-001/metrics',
      ]);
      expect(screen.queryByRole('link', { name: 'Playbook' })).toBeNull();
      expect(screen.queryByRole('button', { name: 'Playbook' })).toBeNull();

      act(() => go('#/runs/run-002/summary'));

      await waitFor(() => expect(screen.getByTestId('phase-rail')).toBeInTheDocument());
      expect(tabHrefs()).toEqual([
        '#/runs/run-002/summary',
        '#/runs/run-002/tickets',
        '#/runs/run-002/outputs',
        '#/runs/run-002/metrics',
      ]);
      expect(screen.queryByRole('link', { name: 'Playbook' })).toBeNull();
      expect(screen.queryByRole('button', { name: 'Playbook' })).toBeNull();
    });
  });

  describe('the tickets tab', () => {
    const detail = (id: string, phases: string[]) =>
      detailOf(run(id), { phases: phases.map((name, i) => ({ name, counts: {}, current: i === 0 })) });

    const phaseSelect = () =>
      screen.getByRole('option', { name: 'all phases' }).closest('select') as HTMLElement;
    const phaseOptions = () =>
      Array.from(phaseSelect().querySelectorAll('option')).map((o) => o.textContent);

    it("filters by the viewed run's phases", async () => {
      go('#board');
      mockHome([run('run-001')], [detail('run-001', ['work', 'reduce'])]);

      render(<App />);

      await waitFor(() => expect(phaseOptions()).toEqual(['all phases', 'work', 'reduce']));
    });

    it('drops the phase filter when the reader switches runs', async () => {
      // Another run's phase names filter this run's board to nothing.
      go('#/runs/run-001/tickets');
      mockHome(
        [run('run-001'), run('run-002')],
        [detail('run-001', ['work', 'reduce']), detail('run-002', ['solve'])],
      );

      render(<App />);
      await waitFor(() => expect(phaseOptions()).toContain('work'));
      fireEvent.change(phaseSelect(), { target: { value: 'work' } });
      await waitFor(() =>
        expect(client.fetchTickets).toHaveBeenLastCalledWith('run-001', { phase: 'work' }),
      );

      fireEvent.click(await findRow('run-002'));

      await waitFor(() => expect(client.fetchTickets).toHaveBeenLastCalledWith('run-002', {}));
      expect(phaseOptions()).toEqual(['all phases', 'solve']);
      expect(window.location.hash).toBe('#/runs/run-002/tickets');
    });
  });
});

describe('addresses and the rail', () => {
  it("resolves an empty address to the default run's summary without a history entry", async () => {
    // Default run: the first run in the Needs you group, whatever its state.
    mockHome([
      run('run-a', { created_at: NOW - 60 }),
      run('run-b', { state: 'done', awaiting: 2, created_at: NOW - 7200 }),
    ]);
    const before = window.history.length;

    render(<App />);

    await waitFor(() => expect(window.location.hash).toBe('#/runs/run-b/summary'));
    expect(window.history.length).toBe(before);
    expect(await heading('run-b · pb')).toBeInTheDocument();
  });

  it('opens a run created after the list loaded, after one refetch, with no note', async () => {
    const a = run('run-a');
    const b = run('run-b', { created_at: NOW - 60 });
    vi.mocked(client.fetchRuns).mockResolvedValueOnce([a]).mockResolvedValue([a, b]);
    vi.mocked(client.fetchRun).mockImplementation(async (id: string) => detailOf(id === 'run-b' ? b : a));
    go('#/runs/run-b/metrics');

    render(<App />);

    await waitFor(() => expect(client.fetchRuns).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(row('run-b')).toHaveAttribute('aria-current', 'page'));
    expect(await heading('run-b · pb')).toBeInTheDocument();
    expect(window.location.hash).toBe('#/runs/run-b/metrics');
    expect(inMain().queryByText(/isn't in this home/)).toBeNull();
    expect(client.fetchRuns).toHaveBeenCalledTimes(2);
  });

  it('shows the note and the default run on the same tab when the run is still absent after one refetch', async () => {
    mockHome([run('run-a')]);
    go('#/runs/ghost/metrics');
    const before = window.history.length;

    render(<App />);

    await waitFor(() => expect(window.location.hash).toBe('#/runs/run-a/metrics'));
    expect(client.fetchRuns).toHaveBeenCalledTimes(2);
    expect(window.history.length).toBe(before);
    expect(await inMain().findByText("ghost isn't in this home")).toBeInTheDocument();
    expect(statusRegion()).toHaveTextContent("ghost isn't in this home");
    expect(await screen.findByTestId('metrics-view')).toHaveTextContent('metrics for run-a');

    // Dismissible, and gone on the next route change either way.
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(inMain().queryByText("ghost isn't in this home")).toBeNull();

    act(() => go('#/runs/ghost/metrics'));
    expect(await inMain().findByText("ghost isn't in this home")).toBeInTheDocument();
    fireEvent.click(within(screen.getByRole('navigation', { name: 'Run tabs' })).getByRole('link', { name: 'Tickets' }));
    await waitFor(() => expect(window.location.hash).toBe('#/runs/run-a/tickets'));
    expect(inMain().queryByText("ghost isn't in this home")).toBeNull();
  });

  it('shows the note and the default run when the one refetch fails', async () => {
    const a = run('run-a');
    vi.mocked(client.fetchRuns).mockResolvedValueOnce([a]).mockRejectedValue(new Error('runs down'));
    vi.mocked(client.fetchRun).mockImplementation(async (id: string) => {
      if (id === 'run-a') return detailOf(a);
      throw Object.assign(new Error(`Run '${id}' not found`), { status: 404 });
    });
    go('#/runs/ghost/metrics');

    render(<App />);

    // A failed refetch is an answer too: the old rows stand, and ghost is not among them.
    await waitFor(() => expect(window.location.hash).toBe('#/runs/run-a/metrics'));
    expect(client.fetchRuns).toHaveBeenCalledTimes(2);
    expect(await inMain().findByText("ghost isn't in this home")).toBeInTheDocument();
  });

  it("leaves #/runs alone and says Couldn't load runs. when the list fails", async () => {
    vi.mocked(client.fetchRuns).mockRejectedValue(new Error('runs down'));
    go('#/runs');

    render(<App />);

    expect(await heading("Couldn't load runs.")).toBeInTheDocument();
    expect(window.location.hash).toBe('#/runs');
  });

  it('fetches the named run directly when the list fails', async () => {
    vi.mocked(client.fetchRuns).mockRejectedValue(new Error('runs down'));
    vi.mocked(client.fetchRun).mockResolvedValue(detailOf(run('run-a')));
    go('#/runs/run-a/metrics');

    render(<App />);

    expect(await heading('run-a · pb')).toBeInTheDocument();
    expect(await screen.findByTestId('metrics-view')).toHaveTextContent('metrics for run-a');
    expect(within(rail()).getByRole('alert')).toBeInTheDocument();
  });

  it('shows the note and leaves the address alone when the list failed and the run is a 404', async () => {
    vi.mocked(client.fetchRuns).mockRejectedValue(new Error('runs down'));
    vi.mocked(client.fetchRun).mockImplementation((id: string) =>
      id === 'ghost'
        ? Promise.reject(Object.assign(new Error("Run 'ghost' not found"), { status: 404 }))
        : new Promise<RunDetail>(() => {}),
    );
    go('#/runs/ghost/summary');

    render(<App />);

    expect(await inMain().findByText("ghost isn't in this home")).toBeInTheDocument();
    expect(statusRegion()).toHaveTextContent("ghost isn't in this home");
    expect(window.location.hash).toBe('#/runs/ghost/summary');
    expect(await heading("Couldn't load runs.")).toBeInTheDocument();

    // The note names the run in the address, not the last one that was a 404.
    act(() => go('#/runs/run-a/summary'));
    await waitFor(() => expect(window.location.hash).toBe('#/runs/run-a/summary'));
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30));
    });
    expect(inMain().queryByText("ghost isn't in this home")).toBeNull();
  });

  it('shows no note when the list failed and the run fetch failed any other way', async () => {
    vi.mocked(client.fetchRuns).mockRejectedValue(new Error('runs down'));
    vi.mocked(client.fetchRun).mockRejectedValue(Object.assign(new Error('boom'), { status: 500 }));
    go('#/runs/run-a/summary');

    render(<App />);

    expect(await heading("Couldn't load runs.")).toBeInTheDocument();
    expect(inMain().queryByText(/isn't in this home/)).toBeNull();
    expect(statusRegion().textContent).toBe('');
  });

  it('shows a runs failure only in the rail, with Retry, while the top bar still works', async () => {
    vi.mocked(client.fetchRuns).mockRejectedValue(new Error('runs down'));
    go('#/crew');

    render(<App />);

    expect(await within(rail()).findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByText('Error loading data')).toBeNull();
    expect(await screen.findByText(/no crew members/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Crew' })).toHaveAttribute('aria-current', 'page');
    // The count shows nothing while the list has never loaded.
    expect(screen.queryByTestId('needs-you-count')).toBeNull();

    fireEvent.click(within(rail()).getByRole('button', { name: /retry/i }));

    await waitFor(() => expect(client.fetchRuns).toHaveBeenCalledTimes(2));
  });

  it('shows the rail on a cross-run page, with its top-bar item current and no rail row current', async () => {
    mockHome([run('run-a'), run('run-b', { created_at: NOW - 7200 })]);
    go('#/activity');

    render(<App />);

    await waitFor(() => expect(row('run-a')).toBeInTheDocument());
    expect(screen.getByRole('link', { name: 'Activity' })).toHaveAttribute('aria-current', 'page');
    expect(
      within(rail()).getAllByRole('link').filter((a) => a.getAttribute('aria-current') === 'page'),
    ).toEqual([]);
    expect(window.location.hash).toBe('#/activity');
  });

  it('opens a rail row on the last run tab used when on a cross-run page', async () => {
    mockHome([run('run-a'), run('run-b', { created_at: NOW - 7200 })]);
    go('#/runs/run-a/tickets');

    render(<App />);
    expect(await heading('run-a · pb')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('link', { name: 'Crew' }));

    await waitFor(() => expect(screen.getByRole('link', { name: 'Crew' })).toHaveAttribute('aria-current', 'page'));
    expect(await findRow('run-b')).toHaveAttribute('href', '#/runs/run-b/tickets');
  });

  it('counts waiting decisions across every run in the top bar, whatever the chips hide', async () => {
    localStorage.setItem('hermes.rail.hiddenPlaybooks', JSON.stringify(['pb-hidden']));
    mockHome([run('run-a', { awaiting: 2 }), run('run-b', { playbook: 'pb-hidden', awaiting: 1 })]);

    render(<App />);

    expect(await screen.findByTestId('needs-you-count')).toHaveTextContent('3');
  });

  it("never renders the previous run's body while the next run's detail loads", async () => {
    const a = run('run-a');
    const b = run('run-b', { created_at: NOW - 7200 });
    vi.mocked(client.fetchRuns).mockResolvedValue([a, b]);
    vi.mocked(client.fetchRun).mockImplementation((id: string) =>
      id === 'run-a' ? Promise.resolve(detailOf(a)) : new Promise<RunDetail>(() => {}),
    );
    go('#/runs/run-a/metrics');

    render(<App />);
    expect(await screen.findByTestId('metrics-view')).toHaveTextContent('metrics for run-a');

    fireEvent.click(await findRow('run-b'));

    // The header is drawn from the row at once; the body waits for run-b's detail.
    expect(await heading('run-b · pb')).toBeInTheDocument();
    expect(screen.queryByTestId('metrics-view')).toBeNull();
    expect(within(screen.getByRole('main')).getAllByRole('status').length).toBeGreaterThan(0);
  });

  it('drops a detail response for a run that is no longer selected', async () => {
    const a = run('run-a');
    const b = run('run-b', { created_at: NOW - 7200 });
    let resolveA: (d: RunDetail) => void = () => {};
    vi.mocked(client.fetchRuns).mockResolvedValue([a, b]);
    vi.mocked(client.fetchRun).mockImplementation((id: string) =>
      id === 'run-a'
        ? new Promise<RunDetail>((resolve) => {
            resolveA = resolve;
          })
        : Promise.resolve(detailOf(b)),
    );
    go('#/runs/run-a/metrics');

    render(<App />);
    expect(await heading('run-a · pb')).toBeInTheDocument();
    fireEvent.click(await findRow('run-b'));
    expect(await screen.findByTestId('metrics-view')).toHaveTextContent('metrics for run-b');

    await act(async () => resolveA(detailOf(a)));

    expect(screen.getByTestId('metrics-view')).toHaveTextContent('metrics for run-b');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('run-b · pb');
  });

  it('shows an alert with Retry under the header when the detail fails', async () => {
    const a = run('run-a');
    const b = run('run-b', { created_at: NOW - 7200 });
    vi.mocked(client.fetchRuns).mockResolvedValue([a, b]);
    // run-a: fails, then answers, then never answers again.
    let aCalls = 0;
    vi.mocked(client.fetchRun).mockImplementation((id: string) => {
      if (id === 'run-b') return Promise.resolve(detailOf(b));
      aCalls++;
      if (aCalls === 1) return Promise.reject(new Error('detail down'));
      if (aCalls === 2) return Promise.resolve(detailOf(a));
      return new Promise<RunDetail>(() => {});
    });
    go('#/runs/run-a/metrics');

    render(<App />);

    const main = screen.getByRole('main');
    expect(await within(main).findByRole('alert')).toHaveTextContent('detail down');
    expect(within(main).getByRole('heading', { level: 1, name: 'run-a · pb' })).toBeInTheDocument();

    fireEvent.click(within(main).getByRole('button', { name: 'Retry' }));

    expect(await screen.findByTestId('metrics-view')).toHaveTextContent('metrics for run-a');
    expect(within(main).queryByRole('alert')).toBeNull();

    // The success cleared the error: back on run-a while it loads, it does not return.
    fireEvent.click(await findRow('run-b'));
    await waitFor(() => expect(screen.getByTestId('metrics-view')).toHaveTextContent('metrics for run-b'));
    fireEvent.click(await findRow('run-a'));
    expect(await heading('run-a · pb')).toBeInTheDocument();
    expect(within(main).queryByRole('alert')).toBeNull();
  });

  it("keeps one run's detail failure off the next run", async () => {
    const a = run('run-a');
    const b = run('run-b', { created_at: NOW - 7200 });
    vi.mocked(client.fetchRuns).mockResolvedValue([a, b]);
    vi.mocked(client.fetchRun).mockImplementation((id: string) =>
      id === 'run-a' ? Promise.reject(new Error('detail down')) : new Promise<RunDetail>(() => {}),
    );
    go('#/runs/run-a/metrics');

    render(<App />);

    const main = screen.getByRole('main');
    expect(await within(main).findByRole('alert')).toHaveTextContent('detail down');

    fireEvent.click(await findRow('run-b'));

    expect(await heading('run-b · pb')).toBeInTheDocument();
    expect(within(main).queryByRole('alert')).toBeNull();
  });

  it('shows the note above the empty state when the address names a run in an empty home', async () => {
    mockHome([]);
    go('#/runs/ghost/summary');

    render(<App />);

    expect(await inMain().findByText("ghost isn't in this home")).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'No runs yet' })).toBeInTheDocument();
    expect(window.location.hash).toBe('#/runs/ghost/summary');
  });
});

describe('keyboard', () => {
  async function onRunC() {
    mockHome(threeRuns());
    go('#/runs/run-c/metrics');
    render(<App />);
    expect(await heading('run-c · pb')).toBeInTheDocument();
    await settled();
  }

  it('] and [ select the next and previous visible run, each a history entry', async () => {
    await onRunC();
    const start = window.history.length;

    fireEvent.keyDown(document.body, { key: ']' });
    expect(await heading('run-b · pb')).toBeInTheDocument();
    expect(window.location.hash).toBe('#/runs/run-b/metrics');

    fireEvent.keyDown(document.body, { key: '[' });
    expect(await heading('run-c · pb')).toBeInTheDocument();
    expect(window.location.hash).toBe('#/runs/run-c/metrics');
    expect(window.history.length).toBe(start + 2);
  });

  it('does nothing past either end: no wrap-around', async () => {
    await onRunC();

    fireEvent.keyDown(document.body, { key: '[' });
    expect(window.location.hash).toBe('#/runs/run-c/metrics');

    act(() => go('#/runs/run-a/metrics'));
    expect(await heading('run-a · pb')).toBeInTheDocument();
    fireEvent.keyDown(document.body, { key: ']' });
    expect(window.location.hash).toBe('#/runs/run-a/metrics');
  });

  it('a held ] leaves one history entry', async () => {
    await onRunC();
    const start = window.history.length;

    fireEvent.keyDown(document.body, { key: ']' });
    expect(await heading('run-b · pb')).toBeInTheDocument();
    fireEvent.keyDown(document.body, { key: ']', repeat: true });
    expect(await heading('run-a · pb')).toBeInTheDocument();

    expect(window.location.hash).toBe('#/runs/run-a/metrics');
    expect(window.history.length).toBe(start + 1);
  });

  it('ignores [ and ] on a cross-run page', async () => {
    mockHome(threeRuns());
    go('#/crew');
    render(<App />);
    await waitFor(() => expect(row('run-c')).toBeInTheDocument());

    fireEvent.keyDown(document.body, { key: ']' });
    fireEvent.keyDown(document.body, { key: '[' });

    expect(window.location.hash).toBe('#/crew');
  });

  it('ignores shortcuts with Meta, or with Ctrl but not AltGr', async () => {
    await onRunC();

    // Cmd+] is the browser's Forward; Ctrl+] is a browser or OS chord.
    fireEvent.keyDown(document.body, { key: ']', metaKey: true });
    fireEvent.keyDown(document.body, { key: ']', ctrlKey: true });
    // Ctrl+Alt without AltGraph is still a Ctrl chord: the check is AltGraph, not altKey.
    fireEvent.keyDown(document.body, { key: ']', ctrlKey: true, altKey: true });
    fireEvent.keyDown(document.body, { key: '/', metaKey: true });

    expect(window.location.hash).toBe('#/runs/run-c/metrics');
    expect(document.activeElement).toBe(document.body);
  });

  it('accepts AltGr (Ctrl+Alt) and Alt alone', async () => {
    await onRunC();

    // Many non-US layouts type [ and ] with AltGr, which Windows reports as Ctrl+Alt.
    fireEvent.keyDown(document.body, { key: ']', ctrlKey: true, altKey: true, modifierAltGraph: true });
    expect(await heading('run-b · pb')).toBeInTheDocument();

    // Option on macOS.
    fireEvent.keyDown(document.body, { key: ']', altKey: true });
    expect(await heading('run-a · pb')).toBeInTheDocument();
  });

  it('ignores shortcuts while composing, already handled, or under an open modal', async () => {
    await onRunC();

    fireEvent.keyDown(document.body, { key: ']', isComposing: true });

    const handled = (e: KeyboardEvent) => e.preventDefault();
    document.addEventListener('keydown', handled);
    fireEvent.keyDown(document.body, { key: ']' });
    document.removeEventListener('keydown', handled);

    const modal = document.createElement('div');
    modal.setAttribute('aria-modal', 'true');
    document.body.appendChild(modal);
    fireEvent.keyDown(document.body, { key: ']' });
    fireEvent.keyDown(document.body, { key: '/' });
    modal.remove();

    expect(window.location.hash).toBe('#/runs/run-c/metrics');
    expect(document.activeElement).toBe(document.body);
  });

  it('ignores shortcuts typed into text entry, but not from a checkbox', async () => {
    await onRunC();
    const editable = document.createElement('div');
    editable.setAttribute('contenteditable', 'true');
    const textEntry = [
      document.createElement('textarea'),
      document.createElement('select'),
      Object.assign(document.createElement('input'), { type: 'text' }),
      Object.assign(document.createElement('input'), { type: 'search' }),
      editable,
    ];

    // Every contenteditable value but "false" takes text.
    for (const value of ['', 'plaintext-only']) {
      const el = document.createElement('div');
      el.setAttribute('contenteditable', value);
      textEntry.push(el);
    }

    for (const el of textEntry) {
      document.body.appendChild(el);
      fireEvent.keyDown(el, { key: ']' });
      el.remove();
    }
    expect(window.location.hash).toBe('#/runs/run-c/metrics');

    // Every input type that takes no text fires: ] and [ in turn, run-c ↔ run-b.
    let at = 'run-c';
    for (const type of ['checkbox', 'radio', 'button', 'submit', 'reset', 'range', 'color', 'file']) {
      const box = Object.assign(document.createElement('input'), { type });
      document.body.appendChild(box);
      fireEvent.keyDown(box, { key: at === 'run-c' ? ']' : '[' });
      box.remove();
      at = at === 'run-c' ? 'run-b' : 'run-c';
      await waitFor(() => expect(window.location.hash).toBe(`#/runs/${at}/metrics`));
    }
    expect(await heading('run-c · pb')).toBeInTheDocument();
  });

  it('steps in from the ends when the chips hide the selected run', async () => {
    localStorage.setItem('hermes.rail.hiddenPlaybooks', JSON.stringify(['pb-x']));
    mockHome([...threeRuns(), run('run-x', { playbook: 'pb-x', created_at: NOW - 90 })]);
    go('#/runs/run-x/metrics');
    render(<App />);
    // A hidden selected run stays in the pane, and no row is highlighted.
    expect(await heading('run-x · pb-x')).toBeInTheDocument();
    await settled();

    fireEvent.keyDown(document.body, { key: ']' });
    expect(await heading('run-c · pb')).toBeInTheDocument();

    act(() => go('#/runs/run-x/metrics'));
    expect(await heading('run-x · pb-x')).toBeInTheDocument();
    fireEvent.keyDown(document.body, { key: '[' });
    expect(await heading('run-a · pb')).toBeInTheDocument();
  });

  it('a deep link to the 30th finished run shows and highlights its row; [ and ] move within the visible rows', async () => {
    // f-01 ended most recently; Finished shows f-01..f-10, then the selected f-30.
    const finished = Array.from({ length: 32 }, (_, i) =>
      run(`f-${String(i + 1).padStart(2, '0')}`, {
        state: 'done',
        created_at: NOW - 100_000 + i,
        updated_at: NOW - (i + 1) * 60,
      }),
    );
    mockHome(finished);
    go('#/runs/f-30/metrics');
    render(<App />);
    expect(await heading('f-30 · pb')).toBeInTheDocument();
    await waitFor(() => expect(row('f-30')).toHaveAttribute('aria-current', 'page'));
    expect(within(rail()).queryByRole('link', { name: /^f-11,/ })).toBeNull();

    // f-30 is the last visible row: ] neither wraps nor opens "show N more".
    fireEvent.keyDown(document.body, { key: ']' });
    expect(window.location.hash).toBe('#/runs/f-30/metrics');

    fireEvent.keyDown(document.body, { key: '[' });
    expect(await heading('f-10 · pb')).toBeInTheDocument();
  });

  it('/ focuses the filter box and prevents the typed slash, on any route', async () => {
    mockHome(threeRuns());
    go('#/crew');
    render(<App />);
    await waitFor(() => expect(row('run-c')).toBeInTheDocument());

    // fireEvent returns false when the listener called preventDefault(). The rows can be
    // drawn a moment before the listener that knows about them is registered.
    await waitFor(() => expect(fireEvent.keyDown(document.body, { key: '/' })).toBe(false));

    const filter = screen.getByRole('searchbox', { name: 'Filter runs' });
    await waitFor(() => expect(filter).toHaveFocus());
    // A slash typed inside the box is text, not a shortcut.
    expect(fireEvent.keyDown(filter, { key: '/' })).toBe(true);

    // And every later press goes there again.
    filter.blur();
    fireEvent.keyDown(document.body, { key: '/' });
    await waitFor(() => expect(filter).toHaveFocus());
  });

  it("/ expands a collapsed rail and writes '0'", async () => {
    localStorage.setItem('hermes.rail.collapsed', '1');
    await onRunC();
    expect(screen.queryByRole('searchbox', { name: 'Filter runs' })).toBeNull();

    fireEvent.keyDown(document.body, { key: '/' });

    const filter = await screen.findByRole('searchbox', { name: 'Filter runs' });
    await waitFor(() => expect(filter).toHaveFocus());
    expect(localStorage.getItem('hermes.rail.collapsed')).toBe('0');
  });

  it('/ does nothing with no runs', async () => {
    mockHome([]);
    render(<App />);
    expect(await heading('No runs yet')).toBeInTheDocument();

    expect(fireEvent.keyDown(document.body, { key: '/' })).toBe(true);
    expect(document.activeElement).toBe(document.body);
  });
});

describe('live refresh', () => {
  async function onRunA() {
    mockHome([run('run-a'), run('run-b', { created_at: NOW - 7200 })]);
    go('#/runs/run-a/metrics');
    const view = render(<App />);
    expect(await screen.findByTestId('metrics-view')).toHaveTextContent('metrics for run-a');
    return view;
  }

  it('N events naming runs within 2 s cause one immediate and one trailing runs fetch', async () => {
    const { rerender } = await onRunA();
    expect(client.fetchRuns).toHaveBeenCalledTimes(1);
    vi.useFakeTimers();

    await deliver(rerender, ev('ticket_claimed', 'run-a'));
    expect(client.fetchRuns).toHaveBeenCalledTimes(2);

    await deliver(rerender, ev('result_recorded', 'run-b'), ev('phase_advanced', 'run-a'));
    expect(client.fetchRuns).toHaveBeenCalledTimes(2);

    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    expect(client.fetchRuns).toHaveBeenCalledTimes(3);

    await act(async () => {
      vi.advanceTimersByTime(4000);
    });
    expect(client.fetchRuns).toHaveBeenCalledTimes(3);
  });

  it('a crew event with no run_id causes no runs fetch', async () => {
    const { rerender } = await onRunA();
    vi.useFakeTimers();

    await deliver(rerender, ev('crew_down', null));
    await act(async () => {
      vi.advanceTimersByTime(4000);
    });

    expect(client.fetchRuns).toHaveBeenCalledTimes(1);
  });

  it('handles every event of a burst delivered in one render', async () => {
    const { rerender } = await onRunA();

    // The run event comes first; the last event of the burst names no run.
    await deliver(rerender, ev('needs_human', 'run-b'), ev('crew_health', null));

    expect(client.fetchRuns).toHaveBeenCalledTimes(2);
  });

  it('a first run appearing while the home is empty opens it', async () => {
    const a = run('run-a');
    vi.mocked(client.fetchRuns).mockResolvedValueOnce([]).mockResolvedValue([a]);
    vi.mocked(client.fetchRun).mockResolvedValue(detailOf(a));
    const { rerender } = render(<App />);
    expect(await heading('No runs yet')).toBeInTheDocument();

    await deliver(rerender, ev('phase_advanced', 'run-a'));

    await waitFor(() => expect(window.location.hash).toBe('#/runs/run-a/summary'));
    expect(await heading('run-a · pb')).toBeInTheDocument();
  });

  it("refetches the selected run's detail on its own events only", async () => {
    const { rerender } = await onRunA();
    expect(client.fetchRun).toHaveBeenCalledTimes(1);

    // Another run's event refreshes the list, not this run's detail; nor does
    // the list refetch it (the detail is keyed on the run id, not the list).
    await deliver(rerender, ev('ticket_claimed', 'run-b'));
    await waitFor(() => expect(client.fetchRuns).toHaveBeenCalledTimes(2));
    expect(client.fetchRun).toHaveBeenCalledTimes(1);

    await deliver(rerender, ev('run_failed', 'run-a'));
    expect(client.fetchRun).toHaveBeenCalledTimes(2);
    expect(client.fetchRun).toHaveBeenLastCalledWith('run-a');
  });
});

describe('focus and announcements', () => {
  it('the skip link moves focus to the <h1> in <main>; the first load moves none', async () => {
    mockHome([run('run-a')]);
    go('#/runs/run-a/metrics');
    render(<App />);
    const h1 = await heading('run-a · pb');
    expect(document.activeElement).toBe(document.body);

    const skip = screen.getByRole('link', { name: 'Skip to content' });
    // The first focusable element in the shell.
    expect(document.querySelector('a[href], button, input, select, textarea')).toBe(skip);
    // fireEvent returns false when the listener called preventDefault(): the link's own navigation is cancelled.
    expect(fireEvent.click(skip)).toBe(false);

    expect(h1).toHaveFocus();
    expect(screen.getByRole('main')).toContainElement(h1);
    expect(window.location.hash).toBe('#/runs/run-a/metrics');
    // One status region in the shell.
    expect(statusRegion()).toHaveAttribute('role', 'status');
    expect(screen.getAllByTestId('status-region')).toHaveLength(1);
  });

  it('[ / ] on a rail row moves focus to the new row and announces it', async () => {
    mockHome(threeRuns());
    go('#/runs/run-c/metrics');
    render(<App />);
    expect(await heading('run-c · pb')).toBeInTheDocument();
    await waitFor(() => expect(row('run-c')).toBeInTheDocument());

    row('run-c').focus();
    fireEvent.keyDown(row('run-c'), { key: ']' });

    await waitFor(() => expect(row('run-b')).toHaveFocus());
    expect(statusRegion()).toHaveTextContent('run-b, pb, running');

    // The same words again are read out again: the region's DOM changes on every announce.
    fireEvent.click(row('run-c'));
    expect(await heading('run-c · pb')).toBeInTheDocument();
    const changes: MutationRecord[] = [];
    const observer = new MutationObserver((records) => changes.push(...records));
    observer.observe(statusRegion(), { childList: true, subtree: true, characterData: true });
    fireEvent.keyDown(row('run-c'), { key: ']' });
    await waitFor(() => expect(row('run-b')).toHaveFocus());
    await waitFor(() => expect(changes.length).toBeGreaterThan(0));
    observer.disconnect();
    expect(statusRegion()).toHaveTextContent('run-b, pb, running');
  });

  it('] from a control the pane drops sends focus to the header <h1>', async () => {
    mockHome([
      run('run-c', { has_view: true, created_at: NOW - 60 }),
      run('run-b', { has_view: true, created_at: NOW - 120 }),
    ]);
    go('#/runs/run-c/metrics');
    render(<App />);
    const action = await screen.findByRole('button', { name: 'view action' });
    await settled();

    action.focus();
    fireEvent.keyDown(action, { key: ']' });

    await waitFor(() => expect(screen.getByRole('heading', { level: 1 })).toHaveFocus());
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('run-b · pb');

    // Nothing focused, and the control last focused is still on screen: focus stays put.
    const tab = within(screen.getByRole('navigation', { name: 'Run tabs' })).getByRole('link', { name: 'Tickets' });
    tab.focus();
    tab.blur();
    fireEvent.keyDown(document.body, { key: '[' });
    expect(await heading('run-c · pb')).toBeInTheDocument();
    expect(tab).toBeInTheDocument();
    expect(document.activeElement).toBe(document.body);
  });

  it('a run-tab click keeps focus on the tab', async () => {
    mockHome([run('run-a')]);
    go('#/runs/run-a/metrics');
    render(<App />);
    expect(await heading('run-a · pb')).toBeInTheDocument();
    const tickets = within(screen.getByRole('navigation', { name: 'Run tabs' })).getByRole('link', {
      name: 'Tickets',
    });

    tickets.focus();
    fireEvent.click(tickets);

    await waitFor(() => expect(window.location.hash).toBe('#/runs/run-a/tickets'));
    await waitFor(() => expect(tickets).toHaveAttribute('aria-current', 'page'));
    expect(tickets).toHaveFocus();
  });

  it('arriving at another page moves focus to its <h1>', async () => {
    mockHome([run('run-a')]);
    go('#/crew');
    render(<App />);
    await waitFor(() => expect(row('run-a')).toBeInTheDocument());
    const home = screen.getByRole('link', { name: 'Hermes' });

    home.focus();
    fireEvent.click(home);

    const h1 = await heading('run-a · pb');
    await waitFor(() => expect(h1).toHaveFocus());
    expect(window.location.hash).toBe('#/runs/run-a/summary');
  });

  it('a rail click from a cross-run page leaves focus on the row', async () => {
    mockHome([run('run-a')]);
    go('#/crew');
    render(<App />);
    await waitFor(() => expect(row('run-a')).toBeInTheDocument());
    const link = row('run-a');

    link.focus();
    fireEvent.click(link);

    expect(await heading('run-a · pb')).toBeInTheDocument();
    expect(link).toHaveFocus();
  });

  it('Back and Forward to another page move focus to its <h1>, even from a rail row', async () => {
    mockHome([run('run-a'), run('run-b', { created_at: NOW - 7200 })]);
    go('#/crew');
    render(<App />);
    await waitFor(() => expect(row('run-b')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('link', { name: 'Activity' }));
    await waitFor(() => expect(screen.getByRole('heading', { level: 1, name: 'Activity' })).toHaveFocus());
    const link = row('run-b');
    link.focus();
    fireEvent.click(link);
    expect(await heading('run-b · pb')).toBeInTheDocument();
    expect(link).toHaveFocus();
    // A click on the row already selected goes nowhere, so it is no rail navigation either.
    fireEvent.click(link);

    // The row is still on screen, and focused, but it is not how the reader got here.
    const traverse = (delta: -1 | 1) =>
      act(
        () =>
          new Promise<void>((resolve) => {
            window.addEventListener('hashchange', () => resolve(), { once: true });
            window.history.go(delta);
          }),
      );
    await traverse(-1);
    await waitFor(() => expect(screen.getByRole('heading', { level: 1, name: 'Activity' })).toHaveFocus());
    await traverse(1);
    await waitFor(() => expect(screen.getByRole('heading', { level: 1, name: 'run-b · pb' })).toHaveFocus());
  });

  it('the first load announces no count; a later rise is announced', async () => {
    const a = run('run-a', { awaiting: 1 });
    vi.mocked(client.fetchRuns).mockResolvedValueOnce([a]).mockResolvedValue([{ ...a, awaiting: 3 }]);
    vi.mocked(client.fetchRun).mockResolvedValue(detailOf(a));
    go('#/runs/run-a/metrics');
    const { rerender } = render(<App />);
    expect(await screen.findByTestId('needs-you-count')).toHaveTextContent('1');
    expect(statusRegion().textContent).toBe('');

    await deliver(rerender, ev('needs_human', 'run-a'));

    await waitFor(() => expect(screen.getByTestId('needs-you-count')).toHaveTextContent('3'));
    expect(statusRegion().textContent).toBe('3 decisions waiting on you');
  });

  it("a rise inside the 10 s window is announced at the window's end", async () => {
    const a = run('run-a', { awaiting: 1 });
    vi.mocked(client.fetchRuns)
      .mockResolvedValueOnce([a])
      .mockResolvedValueOnce([{ ...a, awaiting: 2 }])
      .mockResolvedValue([{ ...a, awaiting: 4 }]);
    vi.mocked(client.fetchRun).mockResolvedValue(detailOf(a));
    go('#/runs/run-a/metrics');
    const { rerender } = render(<App />);
    expect(await screen.findByTestId('needs-you-count')).toHaveTextContent('1');
    vi.useFakeTimers();

    await deliver(rerender, ev('needs_human', 'run-a')); // immediate refetch: 2, announced
    expect(statusRegion().textContent).toBe('2 decisions waiting on you');

    await act(async () => {
      vi.advanceTimersByTime(2000); // trailing refetch: 4, inside the window
    });
    expect(screen.getByTestId('needs-you-count')).toHaveTextContent('4');
    expect(statusRegion().textContent).toBe('2 decisions waiting on you');

    await act(async () => {
      vi.advanceTimersByTime(7999); // 1 ms before the window ends
    });
    expect(statusRegion().textContent).toBe('2 decisions waiting on you');
    await act(async () => {
      vi.advanceTimersByTime(1); // the window ends
    });
    expect(statusRegion().textContent).toBe('4 decisions waiting on you');
  });

  it('says nothing when the count holds at, or comes back to, the last one announced', async () => {
    const a = run('run-a', { awaiting: 1 });
    vi.mocked(client.fetchRuns)
      .mockResolvedValueOnce([a])
      .mockResolvedValueOnce([{ ...a, awaiting: 2 }])
      .mockResolvedValueOnce([{ ...a, awaiting: 2, state: 'failed' }])
      .mockResolvedValueOnce([{ ...a, awaiting: 1, state: 'failed' }])
      .mockResolvedValue([{ ...a, awaiting: 2, state: 'failed' }]);
    vi.mocked(client.fetchRun).mockResolvedValue(detailOf(a));
    go('#/runs/run-a/metrics');
    const { rerender } = render(<App />);
    expect(await screen.findByTestId('needs-you-count')).toHaveTextContent('1');
    vi.useFakeTimers();

    await deliver(rerender, ev('needs_human', 'run-a')); // immediate refetch: 2, announced
    expect(statusRegion().textContent).toBe('2 decisions waiting on you');
    await act(async () => {
      vi.advanceTimersByTime(2000); // trailing refetch: still 2, and the run failed
    });
    expect(statusRegion().textContent).toBe('run-a failed');
    await act(async () => {
      vi.advanceTimersByTime(10_000); // the window ends at the count last announced
    });
    expect(statusRegion().textContent).toBe('run-a failed');

    await deliver(rerender, ev('ticket_claimed', 'run-a')); // immediate refetch: down to 1
    expect(screen.getByTestId('needs-you-count')).toHaveTextContent('1');
    await act(async () => {
      vi.advanceTimersByTime(2000); // trailing refetch: back up to 2, no higher than announced
    });
    expect(screen.getByTestId('needs-you-count')).toHaveTextContent('2');
    expect(statusRegion().textContent).toBe('run-a failed');
  });

  it("announces the selected run's state change, but not a selection", async () => {
    const a = run('run-a', { created_at: NOW - 60 });
    const b = run('run-b', { state: 'done', created_at: NOW - 120 });
    vi.mocked(client.fetchRuns).mockResolvedValueOnce([a, b]).mockResolvedValue([{ ...a, state: 'failed' }, b]);
    vi.mocked(client.fetchRun).mockImplementation(async (id: string) => detailOf(id === 'run-b' ? b : a));
    go('#/runs/run-a/metrics');
    const { rerender } = render(<App />);
    expect(await heading('run-a · pb')).toBeInTheDocument();

    fireEvent.click(await findRow('run-b'));
    expect(await heading('run-b · pb')).toBeInTheDocument();
    expect(statusRegion().textContent).toBe('');

    act(() => go('#/runs/run-a/metrics'));
    expect(await heading('run-a · pb')).toBeInTheDocument();
    await deliver(rerender, ev('run_failed', 'run-a'));

    await waitFor(() => expect(statusRegion()).toHaveTextContent('run-a failed'));
  });
});

describe('the Needs you page', () => {
  /** One decision waiting in run-001, as /api/needs-you returns it. */
  function mockWaiting() {
    vi.mocked(client.fetchNeedsYou).mockResolvedValue([
      {
        id: 7,
        run_id: 'run-001',
        phase: 'decide',
        kind: 'verdict',
        json: { title: 'Pick the schema' },
        review_state: 'pending',
        member_ticket_ids: ['run-001/t-1'],
        member_tickets: [{ id: 'run-001/t-1', state: 'needs_human', phase: 'decide' }],
        playbook: 'pb',
        created_at: NOW - 50,
      },
    ]);
  }

  it('renders the cross-run page at #/needs-you, filtered by ?run', async () => {
    mockHome([run('run-001', { tickets: { needs_human: 1 }, awaiting: 1 })]);
    mockWaiting();
    go('#/needs-you?run=run-001');

    render(<App />);

    expect(await heading('Needs you')).toBeInTheDocument();
    const toggle = await screen.findByRole('button', { name: 'Pick the schema' });
    // ?run= with exactly one item: it starts open, with its ruling buttons.
    await waitFor(() => expect(toggle).toHaveAttribute('aria-expanded', 'true'));
    expect(screen.getByRole('button', { name: 'Accept' })).toBeEnabled();
    expect(screen.getByTestId('needs-you-run-chip')).toHaveTextContent('run run-001');
    // The group's state label comes from App's own run list, handed down as `runs`.
    const group = screen.getByRole('region', { name: 'run-001' });
    expect(await within(group).findByText('running')).toBeInTheDocument();
  });

  it('still lists what needs you when the run list fails', async () => {
    vi.mocked(client.fetchRuns).mockRejectedValue(new Error('database is locked'));
    mockWaiting();
    go('#/needs-you');

    render(<App />);

    // Cross-run pages keep working without the list (spec, Errors): no run
    // needs to be selected, and the group header just drops its state label.
    expect(await heading('Needs you')).toBeInTheDocument();
    expect(await inMain().findByRole('button', { name: 'Pick the schema' })).toBeInTheDocument();
    expect(within(inMain().getByRole('region', { name: 'run-001' })).queryByText('running')).toBeNull();
  });

  it("announces a decision in the shell, refreshes the run list, and refetches on the app's stream", async () => {
    mockHome([run('run-001', { tickets: { needs_human: 1 }, awaiting: 1 })]);
    mockWaiting();
    vi.mocked(client.acceptReduction).mockResolvedValue({ review_state: 'accepted' });
    go('#/needs-you?run=run-001');
    const { rerender } = render(<App />);
    await settled();
    const toggle = await screen.findByRole('button', { name: 'Pick the schema' });
    await waitFor(() => expect(toggle).toHaveAttribute('aria-expanded', 'true'));
    const runFetches = vi.mocked(client.fetchRuns).mock.calls.length;

    fireEvent.click(screen.getByRole('button', { name: 'Accept' }));

    await waitFor(() => expect(statusRegion()).toHaveTextContent('Accepted: Pick the schema'));
    expect(vi.mocked(client.fetchRuns).mock.calls.length).toBeGreaterThan(runFetches);
    // The decision's own refetch; then an event on the app's one stream refetches again.
    await waitFor(() => expect(client.fetchNeedsYou).toHaveBeenCalledTimes(2));

    await deliver(rerender, ev('reduction_accepted', 'run-001'));

    await waitFor(() => expect(client.fetchNeedsYou).toHaveBeenCalledTimes(3));
  });
});
