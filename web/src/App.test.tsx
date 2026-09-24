import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import App from './App';
import * as client from './api/client';
import type { RunDetail } from './api/client';
import * as useEventStreamModule from './hooks/useEventStream';

vi.mock('./api/client');
vi.mock('./hooks/useEventStream');

// The real loader injects a <script> tag and reads a window global; neither is
// what this file is testing. The stub keeps the two rules App depends on:
//
//  1. it renders nothing unless the run has a view;
//  2. it KEEPS THE RUN IT FIRST MOUNTED WITH.
//
// (2) is stateful on purpose. It is the real loader's behaviour -- it only
// blanks its pane on the first load, so a runId change renders the previous
// run's view_data for one round trip -- and it is the entire reason App keys
// the element on the run. Without it modelled here the `key` can be deleted
// for free: a stateless stub re-renders with the new runId either way, and a
// test in PlaybookView.test.tsx would only be testing React's reconciler.
vi.mock('./views/PlaybookView', async () => {
  const { useState } = await import('react');
  const PlaybookViewStub = ({
    runId,
    hasView,
    liveTick,
  }: {
    runId: string;
    hasView: boolean;
    liveTick?: number;
  }) => {
    const [mountedWith] = useState(runId);
    return hasView ? (
      <div data-testid="playbook-view">
        playbook view for {mountedWith} · tick {String(liveTick)}
      </div>
    ) : null;
  };
  return { default: PlaybookViewStub };
});

const mockRunDetail: RunDetail = {
  id: 'run-001',
  playbook: 'example',
  site: 'local',
  state: 'running',
  phase: 'work',
  base_ref: 'main',
  created_at: '2026-07-29T10:00:00Z',
  updated_at: '2026-07-29T10:05:00Z',
  config: { issue_kind: 'bug' },
  has_view: false,
  tickets: {
    queued: 5,
    running: 2,
    done: 10,
    failed: 1,
  },
  phases: [
    {
      name: 'work',
      counts: { queued: 5, running: 2, done: 10, failed: 1 },
      current: true,
    },
    {
      name: 'reduce',
      counts: {},
      current: false,
    },
  ],
};

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    // App reads the review queue's size for the nav badge. Auto-mocked to
    // undefined otherwise, which is not a promise.
    vi.mocked(client.fetchReductions).mockResolvedValue([]);

    // Default mock for useEventStream (no authError)
    vi.spyOn(useEventStreamModule, 'useEventStream').mockReturnValue({
      connected: true,
      events: [],
      lastEvent: null,
      authError: false,
    });
  });

  it('should render empty state when no runs exist', async () => {
    vi.spyOn(client, 'fetchHealth').mockResolvedValue({
      status: 'ok',
      version: '0.1.0',
      home: '/tmp/hermes',
    });
    vi.spyOn(client, 'fetchRuns').mockResolvedValue([]);

    render(<App />);

    // Wait for loading to complete
    await waitFor(() => {
      expect(screen.getByText(/no active run/i)).toBeInTheDocument();
    });
  });

  it('should render RunOverview when runs exist', async () => {
    vi.spyOn(client, 'fetchHealth').mockResolvedValue({
      status: 'ok',
      version: '0.1.0',
      home: '/tmp/hermes',
    });
    vi.spyOn(client, 'fetchRuns').mockResolvedValue([
      {
        id: 'run-001',
        playbook: 'example',
        site: 'local',
        state: 'running',
        phase: 'work',
        base_ref: 'main',
        created_at: '2026-07-29T10:00:00Z',
        tickets: { queued: 5, running: 2, done: 10, failed: 1 },
      },
    ]);
    vi.spyOn(client, 'fetchRun').mockResolvedValue(mockRunDetail);

    render(<App />);

    // Wait for loading to complete and verify run data is displayed
    await waitFor(() => {
      expect(screen.getByText(/example run/i)).toBeInTheDocument();
    });

    // Verify stat tiles show correct counts
    expect(screen.getByText('18')).toBeInTheDocument(); // total tickets
    expect(screen.getByText('10')).toBeInTheDocument(); // done count
    expect(screen.getByText('2')).toBeInTheDocument(); // running count
    expect(screen.getByText('5')).toBeInTheDocument(); // queued count
  });

  it('should show Run tab in TopBar', async () => {
    vi.spyOn(client, 'fetchHealth').mockResolvedValue({
      status: 'ok',
      version: '0.1.0',
      home: '/tmp/hermes',
    });
    vi.spyOn(client, 'fetchRuns').mockResolvedValue([
      {
        id: 'run-001',
        playbook: 'example',
        site: 'local',
        state: 'running',
        phase: 'work',
        base_ref: 'main',
        created_at: '2026-07-29T10:00:00Z',
        tickets: { queued: 5 },
      },
    ]);
    vi.spyOn(client, 'fetchRun').mockResolvedValue(mockRunDetail);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('Run')).toBeInTheDocument();
    });
  });

  it('should handle API error gracefully', async () => {
    vi.spyOn(client, 'fetchHealth').mockRejectedValue(new Error('Network error'));
    vi.spyOn(client, 'fetchRuns').mockRejectedValue(new Error('Network error'));

    render(<App />);

    // Title AND the now-rendered description both surface the failure.
    await waitFor(() => {
      expect(screen.getByText('Error loading data')).toBeInTheDocument();
    });
    expect(screen.getByText('Network error')).toBeInTheDocument();
  });

  it('should show loading state initially', () => {
    vi.spyOn(client, 'fetchHealth').mockImplementation(() => new Promise(() => {}));
    vi.spyOn(client, 'fetchRuns').mockImplementation(() => new Promise(() => {}));

    render(<App />);

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('should show Activity tab in TopBar', async () => {
    vi.spyOn(client, 'fetchHealth').mockResolvedValue({
      status: 'ok',
      version: '0.1.0',
      home: '/tmp/hermes',
    });
    vi.spyOn(client, 'fetchRuns').mockResolvedValue([
      {
        id: 'run-001',
        playbook: 'example',
        site: 'local',
        state: 'running',
        phase: 'work',
        base_ref: 'main',
        created_at: '2026-07-29T10:00:00Z',
        tickets: { queued: 5 },
      },
    ]);
    vi.spyOn(client, 'fetchRun').mockResolvedValue(mockRunDetail);

    render(<App />);

    await waitFor(() => {
      // Activity tab should be present
      expect(screen.getByText('Activity')).toBeInTheDocument();
    });
  });

  it('should display auth error banner when WebSocket reports 4401', async () => {
    // Mock useEventStream to report authError=true and not connected
    vi.spyOn(useEventStreamModule, 'useEventStream').mockReturnValue({
      connected: false,
      events: [],
      lastEvent: null,
      authError: true,
    });

    vi.spyOn(client, 'fetchHealth').mockResolvedValue({
      status: 'ok',
      version: '0.1.0',
      home: '/tmp/hermes',
    });
    vi.spyOn(client, 'fetchRuns').mockResolvedValue([]);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/live updates unauthorized/i)).toBeInTheDocument();
    });
  });

  describe('tab in the URL', () => {
    function mockLoadedRun() {
      vi.spyOn(client, 'fetchHealth').mockResolvedValue({
        status: 'ok',
        version: '0.1.0',
        home: '/tmp/hermes',
      });
      vi.spyOn(client, 'fetchRuns').mockResolvedValue([
        {
          id: 'run-001',
          playbook: 'example',
          site: 'local',
          state: 'running',
          phase: 'work',
          base_ref: 'main',
          created_at: '2026-07-29T10:00:00Z',
          tickets: { queued: 5, running: 2, done: 10, failed: 1 },
        },
      ]);
      vi.spyOn(client, 'fetchRun').mockResolvedValue(mockRunDetail);
      vi.spyOn(client, 'fetchCrew').mockResolvedValue([]);
    }

    afterEach(() => {
      window.location.hash = '';
    });

    it('opens the tab named in the URL instead of the default (refresh restores it)', async () => {
      window.location.hash = '#crew';
      mockLoadedRun();

      render(<App />);

      // The Crew view renders; the default Run overview does not.
      await waitFor(() => {
        expect(screen.getByText(/no crew members/i)).toBeInTheDocument();
      });
      expect(screen.queryByText(/example run/i)).not.toBeInTheDocument();
    });

    it('does not name the run in view on a host working on it', async () => {
      window.location.hash = '#crew';
      mockLoadedRun();
      vi.spyOn(client, 'fetchCrew').mockResolvedValue([
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

      await waitFor(() => expect(screen.getByTitle('run-001/t1')).toHaveTextContent('work'));
      expect(screen.getByTitle('run-001/t1')).not.toHaveTextContent('run-001');
    });

    it('writes the tab into the URL when a tab is clicked', async () => {
      mockLoadedRun();

      render(<App />);
      await waitFor(() => {
        expect(screen.getByText(/example run/i)).toBeInTheDocument();
      });

      screen.getByRole('button', { name: /^crew$/i }).click();

      await waitFor(() => {
        expect(window.location.hash).toBe('#crew');
      });
    });
  });

  describe('the playbook tab', () => {
    const withView: RunDetail = { ...mockRunDetail, playbook: 'committee', has_view: true };

    function mockRuns(...ids: string[]) {
      vi.spyOn(client, 'fetchHealth').mockResolvedValue({
        status: 'ok',
        version: '0.1.0',
        home: '/tmp/hermes',
      });
      vi.spyOn(client, 'fetchRuns').mockResolvedValue(
        ids.map((id) => ({
          id,
          playbook: 'committee',
          site: 'local',
          state: 'running',
          phase: 'work',
          base_ref: 'main',
          created_at: '2026-07-29T10:00:00Z',
          tickets: { queued: 5 },
        })),
      );
    }

    afterEach(() => {
      window.location.hash = '';
    });

    it('is absent for a run whose playbook ships no view', async () => {
      mockRuns('run-001');
      vi.spyOn(client, 'fetchRun').mockResolvedValue(mockRunDetail);

      render(<App />);

      await waitFor(() => {
        expect(screen.getByText(/example run/i)).toBeInTheDocument();
      });
      expect(screen.queryByTestId('tab-playbook')).toBeNull();
    });

    it('is present, and opens the view, for a run whose playbook has one', async () => {
      mockRuns('run-001');
      vi.spyOn(client, 'fetchRun').mockResolvedValue(withView);

      render(<App />);

      await waitFor(() => {
        expect(screen.getByTestId('tab-playbook')).toBeInTheDocument();
      });

      screen.getByTestId('tab-playbook').click();

      await waitFor(() => {
        expect(screen.getByTestId('playbook-view')).toHaveTextContent('run-001');
      });
      expect(window.location.hash).toBe('#playbook');
    });

    it('falls back to the run overview when #playbook names a run with no view', async () => {
      // A bookmarked hash outlives the run it was taken on. Blank pane, no tab
      // to click your way out of: the one outcome the fallback exists to avoid.
      window.location.hash = '#playbook';
      mockRuns('run-001');
      vi.spyOn(client, 'fetchRun').mockResolvedValue(mockRunDetail);

      render(<App />);

      await waitFor(() => {
        expect(screen.getByText(/example run/i)).toBeInTheDocument();
      });
      expect(screen.queryByTestId('playbook-view')).toBeNull();
      expect(screen.queryByTestId('tab-playbook')).toBeNull();
    });

    it('appears and disappears as the reader switches runs', async () => {
      mockRuns('run-001', 'run-002');
      vi.spyOn(client, 'fetchRun').mockImplementation(async (id: string) =>
        id === 'run-001' ? withView : { ...mockRunDetail, id: 'run-002' },
      );

      render(<App />);

      await waitFor(() => {
        expect(screen.getByTestId('tab-playbook')).toBeInTheDocument();
      });

      fireEvent.change(screen.getByTestId('run-picker'), { target: { value: 'run-002' } });

      await waitFor(() => {
        expect(screen.queryByTestId('tab-playbook')).toBeNull();
      });

      fireEvent.change(screen.getByTestId('run-picker'), { target: { value: 'run-001' } });

      await waitFor(() => {
        expect(screen.getByTestId('tab-playbook')).toBeInTheDocument();
      });
    });

    it('remounts the view when the reader switches to another run with one', async () => {
      // Finding 10.1. The loader keeps the run it first mounted with, so
      // without `key` on the element the pane shows run-001's view_data under
      // run-002's id for one round trip. One round trip, easy to miss in
      // review, invisible in CI.
      mockRuns('run-001', 'run-002');
      vi.spyOn(client, 'fetchRun').mockImplementation(async (id: string) => ({
        ...withView,
        id,
      }));

      render(<App />);

      await waitFor(() => {
        expect(screen.getByTestId('tab-playbook')).toBeInTheDocument();
      });
      screen.getByTestId('tab-playbook').click();
      await waitFor(() => {
        expect(screen.getByTestId('playbook-view')).toHaveTextContent('run-001');
      });

      fireEvent.change(screen.getByTestId('run-picker'), { target: { value: 'run-002' } });

      await waitFor(() => {
        expect(screen.getByTestId('playbook-view')).toHaveTextContent('run-002');
      });
    });

    it('hands the view the finding tick, so a new reduction refreshes it', async () => {
      // Finding 10.2. Drop `liveTick={findingLiveTick}` and a live committee
      // run silently stops refreshing on reduction_created -- which, for turns
      // arriving one at a time, is the feature.
      mockRuns('run-001');
      vi.spyOn(client, 'fetchRun').mockResolvedValue(withView);

      render(<App />);

      await waitFor(() => {
        expect(screen.getByTestId('tab-playbook')).toBeInTheDocument();
      });
      screen.getByTestId('tab-playbook').click();

      await waitFor(() => {
        expect(screen.getByTestId('playbook-view')).toHaveTextContent(/tick \d+/);
      });
    });

    it('keeps the Run tab lit when #playbook falls back to the overview', async () => {
      // Finding 10.4: RunOverview is on screen, so some tab has to claim it.
      window.location.hash = '#playbook';
      mockRuns('run-001');
      vi.spyOn(client, 'fetchRun').mockResolvedValue(mockRunDetail);

      render(<App />);

      await waitFor(() => {
        expect(screen.getByText(/example run/i)).toBeInTheDocument();
      });
      expect(screen.getByTestId('tab-run')).toHaveStyle({ color: 'var(--text-primary)' });
    });
  });

  describe('the tickets tab', () => {
    function mockRuns(...ids: string[]) {
      vi.spyOn(client, 'fetchHealth').mockResolvedValue({
        status: 'ok',
        version: '0.1.0',
        home: '/tmp/hermes',
      });
      vi.spyOn(client, 'fetchRuns').mockResolvedValue(
        ids.map((id) => ({
          id,
          playbook: 'example',
          site: 'local',
          state: 'running',
          phase: 'work',
          base_ref: 'main',
          created_at: '2026-07-29T10:00:00Z',
          tickets: {},
        })),
      );
      vi.mocked(client.fetchTickets).mockResolvedValue([]);
    }

    const phaseSelect = () =>
      screen.getByRole('option', { name: 'all phases' }).closest('select') as HTMLElement;
    const phaseOptions = () =>
      Array.from(phaseSelect().querySelectorAll('option')).map((o) => o.textContent);

    afterEach(() => {
      window.location.hash = '';
    });

    it("filters by the viewed run's phases", async () => {
      window.location.hash = '#board';
      mockRuns('run-001');
      vi.spyOn(client, 'fetchRun').mockResolvedValue(mockRunDetail);

      render(<App />);

      await waitFor(() => expect(phaseOptions()).toEqual(['all phases', 'work', 'reduce']));
    });

    it('drops the phase filter when the reader switches runs', async () => {
      // Another run's phase names filter this run's board to nothing.
      window.location.hash = '#board';
      mockRuns('run-001', 'run-002');
      vi.spyOn(client, 'fetchRun').mockImplementation(async (id: string) =>
        id === 'run-001'
          ? mockRunDetail
          : { ...mockRunDetail, id, phases: [{ name: 'solve', counts: {}, current: true }] },
      );

      render(<App />);
      await waitFor(() => expect(phaseOptions()).toContain('work'));
      fireEvent.change(phaseSelect(), { target: { value: 'work' } });
      await waitFor(() =>
        expect(client.fetchTickets).toHaveBeenLastCalledWith('run-001', { phase: 'work' }),
      );

      fireEvent.change(screen.getByTestId('run-picker'), { target: { value: 'run-002' } });

      await waitFor(() => expect(client.fetchTickets).toHaveBeenLastCalledWith('run-002', {}));
      expect(phaseOptions()).toEqual(['all phases', 'solve']);
    });
  });
});
