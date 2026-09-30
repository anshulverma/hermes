/**
 * The Metrics tab: the host's own metrics, and beside them the section a
 * playbook's view declares for this tab. Both views are stubbed; the loader's
 * own rules (a view that declares no `metrics` section renders nothing) are
 * pinned in PlaybookView.test.tsx.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import App from './App';
import * as client from './api/client';
import type { Run, RunDetail, RunMetrics } from './api/client';
import * as useEventStreamModule from './hooks/useEventStream';

vi.mock('./api/client');
vi.mock('./hooks/useEventStream');
vi.mock('./views/MetricsView', () => ({
  default: ({ runId }: { runId: string }) => <div data-testid="metrics-view">metrics for {runId}</div>,
}));
// Keeps the run it first mounted with, like the real loader, so a body that is
// not keyed on the run shows up as the previous run's id.
vi.mock('./views/PlaybookView', async () => {
  const { useState } = await import('react');
  const PlaybookViewStub = ({
    runId,
    hasView,
    liveTick,
    variant,
  }: {
    runId: string;
    hasView: boolean;
    liveTick?: number;
    variant?: string;
  }) => {
    const [mountedWith] = useState(runId);
    return hasView ? (
      <div data-testid="playbook-view">
        {String(variant)} section for {mountedWith} · tick {String(liveTick)}
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

const run = (id: string, has_view: boolean, created_at: number): RunDetail => ({
  id,
  playbook: 'pb',
  site: 'local',
  state: 'running',
  phase: 'work',
  base_ref: 'main',
  created_at,
  updated_at: created_at + 300,
  config: {},
  has_view,
  tickets: {},
  phases: [],
});

function mockRuns(details: RunDetail[]) {
  vi.mocked(client.fetchHealth).mockResolvedValue({ status: 'ok', version: '0.1.0', home: '/tmp/hermes' });
  vi.mocked(client.fetchRuns).mockImplementation(async () =>
    details.map(
      (d): Run => ({
        id: d.id,
        playbook: d.playbook,
        site: d.site,
        state: d.state,
        phase: d.phase,
        base_ref: d.base_ref,
        created_at: d.created_at,
        updated_at: d.updated_at,
        tickets: d.tickets,
        has_view: d.has_view,
        awaiting: 0,
        subject: null,
      }),
    ),
  );
  vi.mocked(client.fetchRun).mockImplementation(async (id: string) => details.find((d) => d.id === id)!);
}

/** Put a hash in the address as a pasted link would (no history entry). */
function go(hash: string) {
  window.history.replaceState(null, '', hash || window.location.pathname);
  window.dispatchEvent(new HashChangeEvent('hashchange'));
}

describe('the Metrics tab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(client.fetchReductions).mockResolvedValue([]);
    vi.mocked(client.fetchNeedsYou).mockResolvedValue([]);
    vi.mocked(client.fetchEvents).mockResolvedValue([]);
    vi.mocked(client.fetchEventKinds).mockResolvedValue([]);
    vi.mocked(client.fetchCrew).mockResolvedValue([]);
    vi.mocked(client.fetchRunMetrics).mockResolvedValue(ZERO_METRICS);
    vi.mocked(useEventStreamModule.useEventStream).mockReturnValue({
      connected: true,
      events: [],
      lastEvent: null,
      authError: false,
    } as ReturnType<typeof useEventStreamModule.useEventStream>);
  });

  afterEach(() => {
    go('');
  });

  it("shows the view's metrics section beside the host's, per run", async () => {
    mockRuns([run('run-001', true, NOW - 60), run('run-002', true, NOW - 120)]);
    go('#/runs/run-001/metrics');

    render(<App />);

    await waitFor(() => expect(screen.getByTestId('metrics-view')).toHaveTextContent('run-001'));
    expect(screen.getByTestId('playbook-view')).toHaveTextContent(/^metrics section for run-001 · tick \d+$/);

    fireEvent.click(
      await within(screen.getByRole('navigation', { name: 'Runs' })).findByRole('link', { name: /^run-002,/ }),
    );

    await waitFor(() => expect(screen.getByTestId('playbook-view')).toHaveTextContent('run-002'));
    expect(screen.getByTestId('metrics-view')).toHaveTextContent('run-002');
    expect(window.location.hash).toBe('#/runs/run-002/metrics');
  });

  it('shows only the host metrics for a run whose playbook ships no view', async () => {
    mockRuns([run('run-001', false, NOW - 60)]);
    go('#/runs/run-001/metrics');

    render(<App />);

    await waitFor(() => expect(screen.getByTestId('metrics-view')).toHaveTextContent('run-001'));
    expect(screen.queryByTestId('playbook-view')).toBeNull();
  });

  it("lands a legacy #metrics link on the default run's Metrics once the list loads", async () => {
    // Two running runs: the default is the newest Active one, run-001.
    mockRuns([run('run-001', false, NOW - 60), run('run-002', false, NOW - 120)]);
    go('#metrics');

    render(<App />);

    await waitFor(() => expect(window.location.hash).toBe('#/runs/run-001/metrics'));
    expect(await screen.findByTestId('metrics-view')).toHaveTextContent('metrics for run-001');
  });
});
