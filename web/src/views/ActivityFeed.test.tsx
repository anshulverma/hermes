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
    // Mock both endpoints: events and event kinds
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/events/kinds' || url.startsWith('/api/events/kinds')) {
        return Promise.resolve({
          ok: true,
          json: async () => ['ticket_claimed', 'result_recorded', 'phase_advanced'],
        });
      }
      // Default: return mockEvents for /api/events
      return Promise.resolve({
        ok: true,
        json: async () => mockEvents,
      });
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
      // First call is /api/events/kinds, second is /api/events
      const calls = (mockFetch as any).mock.calls;
      const eventsCalls = calls.filter((call: any) => call[0] === '/api/events');
      expect(eventsCalls.length).toBeGreaterThan(0);
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
      expect((mockFetch as any).mock.calls[0][0]).toBe('/api/events?kind=ticket_claimed');
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
      expect((mockFetch as any).mock.calls[0][0]).toBe('/api/events?kind=ticket_claimed');
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
      expect((mockFetch as any).mock.calls[0][0]).toBe('/api/events');
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

  it('should populate kind filter options from fetchEventKinds, not hardcoded', async () => {
    // Mock fetchEventKinds to return a custom set of kinds
    const mockKinds = ['kind_a', 'kind_b'];

    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/events/kinds') {
        return Promise.resolve({
          ok: true,
          json: async () => mockKinds,
        });
      }
      if (url === '/api/events') {
        return Promise.resolve({
          ok: true,
          json: async () => [],
        });
      }
      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });

    render(<ActivityFeed />);

    await waitFor(() => {
      const select = screen.getByRole('combobox');
      const options = Array.from(select.querySelectorAll('option')).map(
        (opt) => (opt as HTMLOptionElement).value
      );

      // Should have "all" + the two dynamic kinds
      expect(options).toEqual(['all', 'kind_a', 'kind_b']);

      // Should NOT have hardcoded kinds
      expect(options).not.toContain('ticket_claimed');
      expect(options).not.toContain('result_recorded');
      expect(options).not.toContain('phase_advanced');
      expect(options).not.toContain('needs_human');
      expect(options).not.toContain('crew_health');
      expect(options).not.toContain('lease_acquired');
    });
  });
});
