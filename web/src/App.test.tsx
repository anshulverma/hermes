import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import App from './App';
import * as client from './api/client';

vi.mock('./api/client');

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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

  it('should render run summary when runs exist', async () => {
    vi.spyOn(client, 'fetchHealth').mockResolvedValue({
      status: 'ok',
      version: '0.1.0',
      home: '/tmp/hermes',
    });
    vi.spyOn(client, 'fetchRuns').mockResolvedValue([
      {
        id: 'run-001',
        playbook: 'mechanic',
        site: 'local',
        state: 'running',
        phase: 'gather',
        base_ref: 'main',
        created_at: '2026-07-29T10:00:00Z',
        tickets: {
          queued: 5,
          in_flight: 2,
          done: 10,
          failed: 1,
        },
      },
    ]);

    render(<App />);

    // Wait for loading to complete and verify run data is displayed
    await waitFor(() => {
      expect(screen.getByText('run-001')).toBeInTheDocument();
    });

    // Verify ticket counts are displayed
    expect(screen.getByText('10')).toBeInTheDocument(); // done count
    expect(screen.getByText('5')).toBeInTheDocument(); // queued count
  });

  it('should handle API error gracefully', async () => {
    vi.spyOn(client, 'fetchHealth').mockRejectedValue(new Error('Network error'));
    vi.spyOn(client, 'fetchRuns').mockRejectedValue(new Error('Network error'));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });

  it('should show loading state initially', () => {
    vi.spyOn(client, 'fetchHealth').mockImplementation(() => new Promise(() => {}));
    vi.spyOn(client, 'fetchRuns').mockImplementation(() => new Promise(() => {}));

    render(<App />);

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });
});
