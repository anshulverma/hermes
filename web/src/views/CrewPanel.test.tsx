import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen, fireEvent, waitFor } from '@testing-library/react';
import CrewPanel from './CrewPanel';
import type { CrewMember, Lease } from '../api/client';

// Mock fetch
const mockFetch = vi.fn();
(globalThis as any).fetch = mockFetch;

const mockCrew: CrewMember[] = [
  {
    id: 'host-1',
    site: 'local',
    state: 'idle',
    capabilities: ['python', 'gpu'],
    resources: { cpu: 8, gpu: 2 },
    health: {
      reachable: true,
      agent_ok: true,
      auth_ok: true,
      workspace_ready: true,
      guard_installed: true,
      latency_ms: 42,
    },
    current_ticket: null,
    current_run: null,
    current_phase: null,
    current_elapsed_s: null,
    last_heartbeat: Date.now() / 1000 - 10,
    heartbeat_age_s: 10,
  },
  {
    id: 'host-2',
    site: 'local',
    state: 'busy',
    capabilities: ['python'],
    resources: { cpu: 4 },
    health: {
      reachable: true,
      agent_ok: false,
      auth_ok: true,
      workspace_ready: true,
      guard_installed: true,
      latency_ms: 150,
    },
    current_ticket: 'test-run/t-1',
    current_run: 'test-run',
    current_phase: 'solve',
    current_elapsed_s: 240,
    last_heartbeat: Date.now() / 1000 - 5,
    heartbeat_age_s: 5,
  },
  {
    id: 'host-3',
    site: 'local',
    state: 'down',
    capabilities: [],
    resources: { cpu: 16 },
    health: null,
    current_ticket: null,
    current_run: null,
    current_phase: null,
    current_elapsed_s: null,
    last_heartbeat: Date.now() / 1000 - 600,
    heartbeat_age_s: 600,
  },
];

const mockLeases: Lease[] = [
  {
    id: 'lease-1',
    run_id: 'test-run',
    resource_class: 'cpu',
    ticket_id: 'test-run/t-1',
    host: 'host-2',
    acquired_at: Date.now() / 1000 - 600,
    ttl_s: 1800,
    expires_at: Date.now() / 1000 + 1200,
    remaining_s: 1200,
  },
];

describe('CrewPanel', () => {
  beforeEach(() => {
    mockFetch.mockClear();
    // Default: return crew members
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockCrew,
    });
  });

  it('should fetch and render all crew members', async () => {
    render(<CrewPanel />);

    // Wait for the fetch to complete
    await waitFor(() => {
      expect((mockFetch as any).mock.calls[0][0]).toBe('/api/crew');
    });

    // Should show all three hosts
    await waitFor(() => {
      expect(screen.getByText('host-1')).toBeInTheDocument();
      expect(screen.getByText('host-2')).toBeInTheDocument();
      expect(screen.getByText('host-3')).toBeInTheDocument();
    });
  });

  it('says what each host is working on, naming the run only when it is not the one in view', async () => {
    const { rerender } = render(<CrewPanel runId="test-run" />);

    await waitFor(() => {
      expect(screen.getByText('host-2')).toBeInTheDocument();
    });
    const row = (id: string) => screen.getByText(id).closest('div[role="button"]')!;

    expect(screen.getByText('3 hosts · 1 working')).toBeInTheDocument();
    expect(screen.getByText('working on')).toBeInTheDocument();
    expect(row('host-2')).toHaveTextContent('solve · 4m 0s');
    expect(row('host-2')).not.toHaveTextContent('test-run');
    expect(row('host-1')).toHaveTextContent('—');

    // The health badge says how old it is.
    expect(row('host-1')).toHaveTextContent('10s ago');
    expect(row('host-3')).toHaveTextContent('10m 0s ago');

    // Looking at another run: the host is carrying someone else's work.
    rerender(<CrewPanel runId="other-run" />);
    expect(row('host-2')).toHaveTextContent('solve · 4m 0s · test-run');
  });

  it('should render health badges from real health data', async () => {
    render(<CrewPanel />);

    await waitFor(() => {
      // host-1 has all checks ok (green)
      // host-2 has agent_ok = false (degraded/red)
      // host-3 has null health (unknown)
      // The actual rendering depends on HealthBadge component
      expect(screen.getByText('host-1')).toBeInTheDocument();
      expect(screen.getByText('host-2')).toBeInTheDocument();
      expect(screen.getByText('host-3')).toBeInTheDocument();
    });
  });

  it('should open host drawer on row click and fetch host leases', async () => {
    // Set up fetch to return crew first, then leases
    let callCount = 0;
    mockFetch.mockImplementation((url) => {
      callCount++;
      if (url === '/api/crew') {
        return Promise.resolve({
          ok: true,
          json: async () => mockCrew,
        });
      }
      if (url === '/api/leases?host=host-2') {
        return Promise.resolve({
          ok: true,
          json: async () => mockLeases,
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => [],
      });
    });

    render(<CrewPanel />);

    // Wait for crew to load
    await waitFor(() => {
      expect(screen.getByText('host-2')).toBeInTheDocument();
    });

    // Click on host-2
    const host2Row = screen.getByText('host-2').closest('div[role="button"]');
    if (host2Row) {
      fireEvent.click(host2Row);
    }

    // Should fetch leases for host-2
    await waitFor(() => {
      const calls = (mockFetch as any).mock.calls;
      const leasesCalls = calls.filter((call: any) => call[0].startsWith('/api/leases'));
      expect(leasesCalls.length).toBeGreaterThan(0);
      expect(leasesCalls[0][0]).toBe('/api/leases?host=host-2');
    });

    // Drawer should show the lease info (multiple matches, just verify one exists)
    await waitFor(() => {
      const matches = screen.getAllByText(/test-run\/t-1/);
      expect(matches.length).toBeGreaterThan(0);
    });
  });

  it('should show empty state when host has no active leases', async () => {
    // Set up fetch to return empty leases
    mockFetch.mockImplementation((url) => {
      if (url === '/api/crew') {
        return Promise.resolve({
          ok: true,
          json: async () => mockCrew,
        });
      }
      if (url.startsWith('/api/leases?host=')) {
        return Promise.resolve({
          ok: true,
          json: async () => [],
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => [],
      });
    });

    render(<CrewPanel />);

    // Wait for crew to load
    await waitFor(() => {
      expect(screen.getByText('host-1')).toBeInTheDocument();
    });

    // Click on host-1 (idle, no leases)
    const host1Row = screen.getByText('host-1').closest('div[role="button"]');
    if (host1Row) {
      fireEvent.click(host1Row);
    }

    // Should fetch leases for host-1
    await waitFor(() => {
      const calls = (mockFetch as any).mock.calls;
      const leasesCalls = calls.filter((call: any) => call[0].startsWith('/api/leases'));
      expect(leasesCalls.length).toBeGreaterThan(0);
      expect(leasesCalls[0][0]).toBe('/api/leases?host=host-1');
    });

    // Should show empty state
    await waitFor(() => {
      expect(screen.getByText(/no active lease/i)).toBeInTheDocument();
    });
  });

  it('should show error state on fetch failure', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));

    render(<CrewPanel />);

    // Title AND the now-rendered description both surface the failure.
    await waitFor(() => {
      expect(screen.getByText('Error loading crew')).toBeInTheDocument();
    });
    expect(screen.getByText('Network error')).toBeInTheDocument();
  });

  it('should refetch when liveTick changes', async () => {
    const { rerender } = render(<CrewPanel liveTick={0} />);

    await waitFor(() => {
      expect(screen.getByText('host-1')).toBeInTheDocument();
    });

    const callsBefore = (mockFetch as any).mock.calls.length;

    rerender(<CrewPanel liveTick={1} />);

    await waitFor(() => {
      expect((mockFetch as any).mock.calls.length).toBeGreaterThan(callsBefore);
    });
  });

  it('refetches on a clock, so the ages keep counting through a long turn with no events', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const mid = { ...mockCrew[1], current_elapsed_s: 2400, heartbeat_age_s: 2400 };
      render(<CrewPanel runId="test-run" />);
      await waitFor(() => {
        expect(screen.getByText('host-2')).toBeInTheDocument();
      });
      const row = () => screen.getByText('host-2').closest('div[role="button"]')!;
      expect(row()).toHaveTextContent('solve · 4m 0s');
      fireEvent.click(row()); // the open drawer counts too

      mockFetch.mockImplementation(async (url: string) => ({
        ok: true,
        json: async () => (url === '/api/crew' ? [mockCrew[0], mid, mockCrew[2]] : []),
      }));
      await act(async () => {
        vi.advanceTimersByTime(15_000);
      });
      await waitFor(() => {
        expect(row()).toHaveTextContent('solve · 40m 0s');
      });
      expect(row()).toHaveTextContent('40m 0s ago');
      expect(screen.getAllByText('solve · 40m 0s')).toHaveLength(2);
      // Without the lease list reloading (and flashing) on every tick.
      const leaseCalls = mockFetch.mock.calls.filter((c: any) => c[0].startsWith('/api/leases'));
      expect(leaseCalls).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('should keep previously rendered crew visible during a live refetch', async () => {
    const { rerender } = render(<CrewPanel liveTick={0} />);

    await waitFor(() => {
      expect(screen.getByText('host-1')).toBeInTheDocument();
    });

    // Start a slow refetch
    mockFetch.mockImplementation(() => new Promise(() => {}));
    rerender(<CrewPanel liveTick={1} />);

    // Crew list should still be visible (no blanking spinner)
    expect(screen.getByText('host-1')).toBeInTheDocument();
    expect(screen.getByText('host-2')).toBeInTheDocument();
  });
});
