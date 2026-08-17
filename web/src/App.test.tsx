import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import App from './App';
import * as client from './api/client';
import type { RunDetail } from './api/client';
import * as useEventStreamModule from './hooks/useEventStream';

vi.mock('./api/client');
vi.mock('./hooks/useEventStream');

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
});
