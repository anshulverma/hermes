import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ActivityFeed from './ActivityFeed';

// Mock fetch
const mockFetch = vi.fn();
(globalThis as any).fetch = mockFetch;

const mockEvents = [
  {
    id: 1,
    ts: 1627849200.5,
    kind: 'ticket_claimed',
    run_id: 'test-run',
    ticket_id: 'test-run/t-0',
    host: 'worker-1',
    message: 'Claimed ticket',
    data: { priority: 10 },
  },
  {
    id: 2,
    ts: 1627849210.3,
    kind: 'result_recorded',
    run_id: 'test-run',
    ticket_id: 'test-run/t-0',
    host: 'worker-1',
    message: 'Recorded result',
    data: { outcome: 'done' },
  },
  {
    id: 3,
    ts: 1627849220.1,
    kind: 'phase_advanced',
    run_id: 'test-run',
    ticket_id: null,
    host: null,
    message: 'Advanced to reduce',
    data: { from: 'work', to: 'reduce' },
  },
];

describe('ActivityFeed', () => {
  beforeEach(() => {
    mockFetch.mockClear();
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockEvents,
    });
  });

  it('should render a row per event', async () => {
    render(<ActivityFeed />);

    await waitFor(() => {
      // Should show event messages
      expect(screen.getByText('Claimed ticket')).toBeInTheDocument();
      expect(screen.getByText('Recorded result')).toBeInTheDocument();
      expect(screen.getByText('Advanced to reduce')).toBeInTheDocument();
    });
  });

  it('should fetch events on mount', async () => {
    render(<ActivityFeed />);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith('/api/events');
    });
  });

  it('should refetch with kind param when filter changes', async () => {
    render(<ActivityFeed />);

    await waitFor(() => {
      expect(screen.getByText('Claimed ticket')).toBeInTheDocument();
    });

    // Clear and setup for next fetch
    mockFetch.mockClear();
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => [mockEvents[0]], // Only ticket_claimed
    });

    // Find the kind filter (could be a select or segmented control)
    // Assuming it's a select with options
    const select = screen.getByRole('combobox');
    fireEvent.change(select, { target: { value: 'ticket_claimed' } });

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith('/api/events?kind=ticket_claimed');
    });
  });

  it('should clear kind filter when "all" is selected', async () => {
    render(<ActivityFeed />);

    await waitFor(() => {
      expect(screen.getByText('Claimed ticket')).toBeInTheDocument();
    });

    // First set a filter
    mockFetch.mockClear();
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => [mockEvents[0]],
    });

    const select = screen.getByRole('combobox');
    fireEvent.change(select, { target: { value: 'ticket_claimed' } });

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith('/api/events?kind=ticket_claimed');
    });

    // Now clear back to "all"
    mockFetch.mockClear();
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockEvents,
    });

    fireEvent.change(select, { target: { value: 'all' } });

    await waitFor(() => {
      // Should fetch without kind param
      expect(mockFetch).toHaveBeenCalledWith('/api/events');
    });
  });

  it('should render empty state when no events', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => [],
    });

    render(<ActivityFeed />);

    await waitFor(() => {
      // Should show an empty state message
      expect(screen.getByText(/no events/i)).toBeInTheDocument();
    });
  });

  it('should handle loading state', () => {
    mockFetch.mockImplementation(
      () => new Promise(() => {}), // Never resolves
    );

    render(<ActivityFeed />);

    // Should show loading indicator
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });
});
