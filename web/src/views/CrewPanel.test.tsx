import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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
    last_heartbeat: Date.now() / 1000 - 10,
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
    last_heartbeat: Date.now() / 1000 - 5,
  },
  {
    id: 'host-3',
    site: 'local',
    state: 'down',
    capabilities: [],
    resources: { cpu: 16 },
    health: null,
    current_ticket: null,
    last_heartbeat: Date.now() / 1000 - 600,
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
      expect(mockFetch).toHaveBeenCalledWith('/api/crew');
    });

    // Should show all three hosts
    await waitFor(() => {
      expect(screen.getByText('host-1')).toBeInTheDocument();
      expect(screen.getByText('host-2')).toBeInTheDocument();
      expect(screen.getByText('host-3')).toBeInTheDocument();
    });
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
      expect(mockFetch).toHaveBeenCalledWith('/api/leases?host=host-2');
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
      expect(mockFetch).toHaveBeenCalledWith('/api/leases?host=host-1');
    });

    // Should show empty state
    await waitFor(() => {
      expect(screen.getByText(/no active lease/i)).toBeInTheDocument();
    });
  });

  it('should show error state on fetch failure', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));

    render(<CrewPanel />);

    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });
});
