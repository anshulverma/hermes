/**
 * The Metrics tab: the host's own metrics, and beside them the section a
 * playbook's view declares for this tab. Both views are stubbed; the loader's
 * own rules (a view that declares no `metrics` section renders nothing) are
 * pinned in PlaybookView.test.tsx.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import App from './App';
import * as client from './api/client';
import type { RunDetail } from './api/client';
import * as useEventStreamModule from './hooks/useEventStream';

vi.mock('./api/client');
vi.mock('./hooks/useEventStream');
vi.mock('./views/MetricsView', () => ({
  default: ({ runId }: { runId: string }) => <div data-testid="metrics-view">metrics for {runId}</div>,
}));
// Keeps the run it first mounted with, like the real loader, so a missing
// `key` shows up as the previous run's id.
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

const run = (id: string, has_view: boolean): RunDetail => ({
  id,
  playbook: 'pb',
  site: 'local',
  state: 'running',
  phase: 'work',
  base_ref: 'main',
  created_at: '2026-07-29T10:00:00Z',
  updated_at: '2026-07-29T10:05:00Z',
  config: {},
  has_view,
  tickets: {},
  phases: [],
});

function mockRuns(details: RunDetail[]) {
  vi.spyOn(client, 'fetchHealth').mockResolvedValue({ status: 'ok', version: '0.1.0', home: '/tmp/hermes' });
  vi.spyOn(client, 'fetchRuns').mockResolvedValue(
    details.map((d) => ({
      id: d.id,
      playbook: d.playbook,
      site: 'local',
      state: 'running',
      phase: 'work',
      base_ref: 'main',
      created_at: d.created_at,
      tickets: {},
    })),
  );
  vi.spyOn(client, 'fetchRun').mockImplementation(async (id: string) => details.find((d) => d.id === id)!);
}

describe('the Metrics tab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(client.fetchReductions).mockResolvedValue([]);
    vi.spyOn(useEventStreamModule, 'useEventStream').mockReturnValue({
      connected: true,
      events: [],
      lastEvent: null,
      authError: false,
    });
    window.location.hash = '#metrics';
  });

  afterEach(() => {
    window.location.hash = '';
  });

  it("shows the view's metrics section beside the host's, per run", async () => {
    mockRuns([run('run-001', true), run('run-002', true)]);

    render(<App />);

    await waitFor(() => expect(screen.getByTestId('metrics-view')).toHaveTextContent('run-001'));
    expect(screen.getByTestId('playbook-view')).toHaveTextContent(/^metrics section for run-001 · tick \d+$/);

    fireEvent.change(screen.getByTestId('run-picker'), { target: { value: 'run-002' } });

    await waitFor(() => expect(screen.getByTestId('playbook-view')).toHaveTextContent('run-002'));
    expect(screen.getByTestId('metrics-view')).toHaveTextContent('run-002');
  });

  it('shows only the host metrics for a run whose playbook ships no view', async () => {
    mockRuns([run('run-001', false)]);

    render(<App />);

    await waitFor(() => expect(screen.getByTestId('metrics-view')).toHaveTextContent('run-001'));
    expect(screen.queryByTestId('playbook-view')).toBeNull();
  });
});
