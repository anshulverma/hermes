/**
 * MetricsView tests - Phase E1: Real run metrics.
 * Vitest + React Testing Library + mocked fetch.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import MetricsView from './MetricsView';

// Mock fetch
const mockFetch = vi.fn();
(globalThis as any).fetch = mockFetch;

describe('MetricsView', () => {
  beforeEach(() => {
    mockFetch.mockClear();
  });

  it('renders metrics charts from API response', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        run_id: 'test-run',
        bucket_s: 300,
        buckets: [
          {
            t_start: 1000,
            throughput: 10,
            done_cumulative: 5,
            failed_cumulative: 2,
            error_rate: 0.2,
            crew_online: 3,
          },
          {
            t_start: 1300,
            throughput: 15,
            done_cumulative: 18,
            failed_cumulative: 4,
            error_rate: 0.15,
            crew_online: 4,
          },
          {
            t_start: 1600,
            throughput: 8,
            done_cumulative: 24,
            failed_cumulative: 6,
            error_rate: 0.25,
            crew_online: 2,
          },
        ],
        totals: { attempts: 4, done: 3, failed: 1, results: 4, tickets: 3 },
        retry_rate: 0.25,
        mean_time_to_result_s: 125,
        by_phase: [{ phase: 'work', tickets: 3, mean_time_s: 12, failure_pct: 10 }],
      }),
    });

    render(<MetricsView runId="test-run" />);

    await waitFor(() => {
      expect(screen.getByText(/run metrics/i)).toBeInTheDocument();
    });

    // Assert API was called correctly
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/runs/test-run/metrics',
      expect.objectContaining({ headers: expect.any(Object) })
    );

    // Chart sections (terms recur as tile labels + chart titles + legends).
    expect(screen.getByText('Progress over time')).toBeInTheDocument();
    expect(screen.getAllByText(/throughput/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/error rate/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/crew online/i).length).toBeGreaterThan(0);

    // Readability affordances: X-axis time labels and final values.
    expect(screen.getAllByText('now').length).toBeGreaterThan(0);
    expect(screen.getByText('done 24')).toBeInTheDocument();
    expect(screen.getByText('failed 6')).toBeInTheDocument();

    // New metrics tiles
    expect(screen.getAllByText('25%').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/retry rate/i).length).toBeGreaterThan(0);
    expect(screen.getByText('2m 5s')).toBeInTheDocument();
    expect(screen.getAllByText(/time to result/i).length).toBeGreaterThan(0);

    // By-phase table
    expect(screen.getByText('work')).toBeInTheDocument();
    expect(screen.getByText('10.0%')).toBeInTheDocument();

    // No GPU/budget/token/spend content
    expect(screen.queryByText(/gpu/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/budget/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/token/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/spend/i)).not.toBeInTheDocument();
  });

  it('shows empty state when buckets are empty', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        run_id: 'empty-run',
        bucket_s: 300,
        buckets: [],
      }),
    });

    render(<MetricsView runId="empty-run" />);

    await waitFor(() => {
      expect(screen.getByText(/no metrics yet/i)).toBeInTheDocument();
    });
  });

  it('does NOT render Resources section (E2 ungated)', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        run_id: 'test-run',
        bucket_s: 300,
        buckets: [],
      }),
    });

    render(<MetricsView runId="test-run" />);

    await waitFor(() => {
      expect(screen.getByText(/no metrics yet/i)).toBeInTheDocument();
    });

    // Should NOT find any resources-related text
    expect(screen.queryByText(/resources/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/gpu-hours/i)).not.toBeInTheDocument();
  });

  it('does NOT render Agent Usage section (E3 ungated)', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        run_id: 'test-run',
        bucket_s: 300,
        buckets: [],
      }),
    });

    render(<MetricsView runId="test-run" />);

    await waitFor(() => {
      expect(screen.getByText(/no metrics yet/i)).toBeInTheDocument();
    });

    // Should NOT find any agent-usage-related text
    expect(screen.queryByText(/agent usage/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/token rate/i)).not.toBeInTheDocument();
  });

  it('renders error state on API failure', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
    });

    render(<MetricsView runId="bad-run" />);

    await waitFor(() => {
      expect(screen.getByText(/error loading metrics/i)).toBeInTheDocument();
    });
  });
});
