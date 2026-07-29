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
    last_heartbeat: 1234567890,
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    // Mock fetchLeases to return empty array by default
    vi.spyOn(client, 'fetchLeases').mockResolvedValue([]);
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
});
