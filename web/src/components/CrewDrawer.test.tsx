import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import CrewDrawer from './CrewDrawer';
import * as client from '../api/client';
import { AuthError } from '../api/client';

describe('CrewDrawer', () => {
  const mockHost: client.CrewMember = {
    id: 'worker-1',
    site: 'local',
    state: 'idle',
    capabilities: ['gpu'],
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
    last_heartbeat: 1234567890,
    heartbeat_age_s: 8,
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    // Mock fetchLeases to return empty array by default
    vi.spyOn(client, 'fetchLeases').mockResolvedValue([]);
  });

  it('says what the host is working on and how old its health is', async () => {
    const busy: client.CrewMember = {
      ...mockHost,
      state: 'busy',
      current_ticket: 'run-a/t-7',
      current_run: 'run-a',
      current_phase: 'review',
      current_elapsed_s: 125,
    };
    render(<CrewDrawer isOpen={true} host={busy} onClose={vi.fn()} onRefresh={vi.fn()} />);

    expect(await screen.findByRole('link', { name: 'run-a/t-7' })).toHaveAttribute(
      'href',
      '#/runs/run-a/tickets?ticket=run-a%2Ft-7',
    );
    // The Run row names the host's run as a link to its Summary.
    expect(screen.getByText('Run')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'run-a' })).toHaveAttribute('href', '#/runs/run-a/summary');
    expect(screen.getByText('review · 2m 5s')).toBeInTheDocument();
    expect(screen.getByText('8s ago')).toBeInTheDocument();
  });

  it('should render drain button', async () => {
    const onClose = vi.fn();
    const onRefresh = vi.fn();

    render(<CrewDrawer isOpen={true} host={mockHost} onClose={onClose} onRefresh={onRefresh} />);

    await waitFor(() => {
      expect(screen.getByText('Drain')).toBeInTheDocument();
    });
  });

  it('should render remove button', async () => {
    const onClose = vi.fn();
    const onRefresh = vi.fn();

    render(<CrewDrawer isOpen={true} host={mockHost} onClose={onClose} onRefresh={onRefresh} />);

    await waitFor(() => {
      expect(screen.getByText('Remove')).toBeInTheDocument();
    });
  });

  it('should render reprobe button', async () => {
    const onClose = vi.fn();
    const onRefresh = vi.fn();

    render(<CrewDrawer isOpen={true} host={mockHost} onClose={onClose} onRefresh={onRefresh} />);

    await waitFor(() => {
      expect(screen.getByText('Re-probe')).toBeInTheDocument();
    });
  });

  it('should call drainCrew when Drain button is clicked', async () => {
    const drainCrewSpy = vi.spyOn(client, 'drainCrew').mockResolvedValue({ state: 'draining' });
    const onClose = vi.fn();
    const onRefresh = vi.fn();

    render(<CrewDrawer isOpen={true} host={mockHost} onClose={onClose} onRefresh={onRefresh} />);

    const drainButton = await screen.findByText('Drain');
    fireEvent.click(drainButton);

    await waitFor(() => {
      expect(drainCrewSpy).toHaveBeenCalledWith('worker-1');
      expect(onRefresh).toHaveBeenCalled();
    });
  });

  it('should call reprobeCrew when Re-probe button is clicked', async () => {
    const mockChecklist: client.HealthChecklist = {
      host: 'worker-1',
      ok: true,
      reachable: true,
      agent_ok: true,
      auth_ok: true,
      workspace_ready: true,
      guard_installed: true,
      resources: { cpu: 8 },
      latency_ms: 38,
      checks: [
        { name: 'reachable', ok: true, detail: 'ssh ok' },
      ],
    };

    const reprobeCrewSpy = vi.spyOn(client, 'reprobeCrew').mockResolvedValue(mockChecklist);
    const onClose = vi.fn();
    const onRefresh = vi.fn();

    render(<CrewDrawer isOpen={true} host={mockHost} onClose={onClose} onRefresh={onRefresh} />);

    const reprobeButton = await screen.findByText('Re-probe');
    fireEvent.click(reprobeButton);

    await waitFor(() => {
      expect(reprobeCrewSpy).toHaveBeenCalledWith('worker-1');
    });

    // Should render the checklist
    await waitFor(() => {
      expect(screen.getByText('Latest Health Check')).toBeInTheDocument();
      expect(screen.getByText('ssh ok')).toBeInTheDocument();
    });
  });

  it('should show confirmation dialog when Remove button is clicked', async () => {
    const onClose = vi.fn();
    const onRefresh = vi.fn();

    render(<CrewDrawer isOpen={true} host={mockHost} onClose={onClose} onRefresh={onRefresh} />);

    const removeButton = await screen.findByText('Remove');
    fireEvent.click(removeButton);

    await waitFor(() => {
      expect(screen.getByText(/are you sure/i)).toBeInTheDocument();
    });
  });

  it('should call removeCrew when confirmed', async () => {
    const removeCrewSpy = vi.spyOn(client, 'removeCrew').mockResolvedValue({ status: 'removed' });
    const onClose = vi.fn();
    const onRefresh = vi.fn();

    render(<CrewDrawer isOpen={true} host={mockHost} onClose={onClose} onRefresh={onRefresh} />);

    const removeButton = await screen.findByText('Remove');
    fireEvent.click(removeButton);

    // Find and click confirm button
    const confirmButton = await screen.findByText('Confirm Remove');
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(removeCrewSpy).toHaveBeenCalledWith('worker-1');
      expect(onRefresh).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('should show AuthError message when auth fails', async () => {
    vi.spyOn(client, 'drainCrew').mockRejectedValue(new AuthError('Unauthorized'));
    const onClose = vi.fn();
    const onRefresh = vi.fn();

    render(<CrewDrawer isOpen={true} host={mockHost} onClose={onClose} onRefresh={onRefresh} />);

    const drainButton = await screen.findByText('Drain');
    fireEvent.click(drainButton);

    await waitFor(() => {
      expect(screen.getByText(/authentication required/i)).toBeInTheDocument();
    });
  });

  it('links each lease card to its run and its ticket', async () => {
    const lease = (id: string, run_id: string, ticket_id: string | null): client.Lease => ({
      id,
      run_id,
      resource_class: 'cpu',
      ticket_id,
      host: 'worker-1',
      acquired_at: 1000,
      ttl_s: 1800,
      expires_at: 2800,
      remaining_s: 1200,
    });
    vi.spyOn(client, 'fetchLeases').mockResolvedValue([
      lease('lease-1', 'run-b', 'run-b/t-3'),
      lease('lease-2', 'run-c', null),
    ]);

    render(<CrewDrawer isOpen={true} host={mockHost} onClose={vi.fn()} onRefresh={vi.fn()} />);

    expect(await screen.findByRole('link', { name: 'run-b' })).toHaveAttribute('href', '#/runs/run-b/summary');
    expect(screen.getByRole('link', { name: 'run-b/t-3' })).toHaveAttribute(
      'href',
      '#/runs/run-b/tickets?ticket=run-b%2Ft-3',
    );
    // A lease holding no ticket still names its run, and shows no Ticket line.
    expect(screen.getByRole('link', { name: 'run-c' })).toHaveAttribute('href', '#/runs/run-c/summary');
    expect(screen.getAllByText('Run:')).toHaveLength(2);
    expect(screen.getAllByText('Ticket:')).toHaveLength(1);
  });
});
