import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import AddHostModal from './AddHostModal';
import * as client from '../api/client';
import { AuthError } from '../api/client';

describe('AddHostModal', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('should render the modal when open', () => {
    const onClose = vi.fn();
    const onAdded = vi.fn();

    render(<AddHostModal isOpen={true} onClose={onClose} onAdded={onAdded} />);

    expect(screen.getAllByText('Add Host').length).toBeGreaterThan(0);
    expect(screen.getByPlaceholderText(/host/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/site/i)).toBeInTheDocument();
  });

  it('should not render when closed', () => {
    const onClose = vi.fn();
    const onAdded = vi.fn();

    render(<AddHostModal isOpen={false} onClose={onClose} onAdded={onAdded} />);

    expect(screen.queryByText('Add Host')).not.toBeInTheDocument();
  });

  it('should call probeCrew when Probe button is clicked', async () => {
    const mockChecklist: client.HealthChecklist = {
      host: 'worker-1',
      ok: true,
      reachable: true,
      agent_ok: true,
      auth_ok: true,
      workspace_ready: true,
      guard_installed: true,
      resources: { cpu: 8, gpu: 2 },
      latency_ms: 42,
      checks: [
        { name: 'reachable', ok: true, detail: 'ssh ok' },
        { name: 'agent', ok: true, detail: 'claude v1.2' },
        { name: 'auth', ok: true, detail: 'token valid' },
      ],
    };

    const probeCrewSpy = vi.spyOn(client, 'probeCrew').mockResolvedValue(mockChecklist);

    const onClose = vi.fn();
    const onAdded = vi.fn();

    render(<AddHostModal isOpen={true} onClose={onClose} onAdded={onAdded} />);

    // Fill in the form
    const hostInput = screen.getByPlaceholderText(/host/i);
    const siteInput = screen.getByPlaceholderText(/site/i);

    fireEvent.change(hostInput, { target: { value: 'worker-1' } });
    fireEvent.change(siteInput, { target: { value: 'local' } });

    // Click Probe
    const probeButton = screen.getByRole('button', { name: /probe|run health check/i });
    fireEvent.click(probeButton);

    await waitFor(() => {
      expect(probeCrewSpy).toHaveBeenCalled();
      const call = probeCrewSpy.mock.calls[0][0];
      expect(call.host).toBe('worker-1');
      expect(call.site).toBe('local');
    });

    // Should render the checklist
    await waitFor(() => {
      expect(screen.getByText('reachable')).toBeInTheDocument();
      expect(screen.getByText('ssh ok')).toBeInTheDocument();
      expect(screen.getByText('agent')).toBeInTheDocument();
      expect(screen.getByText('claude v1.2')).toBeInTheDocument();
      expect(screen.getByText('auth')).toBeInTheDocument();
      expect(screen.getByText('token valid')).toBeInTheDocument();
    });
  });

  it('should show error message on failed probe', async () => {
    vi.spyOn(client, 'probeCrew').mockRejectedValue(new Error('Host unreachable'));

    const onClose = vi.fn();
    const onAdded = vi.fn();

    render(<AddHostModal isOpen={true} onClose={onClose} onAdded={onAdded} />);

    const hostInput = screen.getByPlaceholderText(/host/i);
    const siteInput = screen.getByPlaceholderText(/site/i);

    fireEvent.change(hostInput, { target: { value: 'worker-1' } });
    fireEvent.change(siteInput, { target: { value: 'local' } });

    const probeButton = screen.getByRole('button', { name: /probe|run health check/i });
    fireEvent.click(probeButton);

    await waitFor(() => {
      expect(screen.getByText(/Host unreachable/i)).toBeInTheDocument();
    });
  });

  it('should call addCrew when Add button is clicked after successful probe', async () => {
    const mockChecklist: client.HealthChecklist = {
      host: 'worker-1',
      ok: true,
      reachable: true,
      agent_ok: true,
      auth_ok: true,
      workspace_ready: true,
      guard_installed: true,
      resources: { cpu: 8 },
      latency_ms: 40,
      checks: [
        { name: 'reachable', ok: true, detail: 'ok' },
      ],
    };

    const mockMember: client.CrewMember = {
      id: 'worker-1',
      site: 'local',
      state: 'idle',
      capabilities: [],
      resources: { cpu: 8 },
      health: {
        reachable: true,
        agent_ok: true,
        auth_ok: true,
        workspace_ready: true,
        guard_installed: true,
        latency_ms: 40,
      },
      current_ticket: null,
      last_heartbeat: 1234567890,
    };

    vi.spyOn(client, 'probeCrew').mockResolvedValue(mockChecklist);
    const addCrewSpy = vi.spyOn(client, 'addCrew').mockResolvedValue(mockMember);

    const onClose = vi.fn();
    const onAdded = vi.fn();

    render(<AddHostModal isOpen={true} onClose={onClose} onAdded={onAdded} />);

    const hostInput = screen.getByPlaceholderText(/host/i);
    const siteInput = screen.getByPlaceholderText(/site/i);

    fireEvent.change(hostInput, { target: { value: 'worker-1' } });
    fireEvent.change(siteInput, { target: { value: 'local' } });

    const probeButton = screen.getByRole('button', { name: /probe|run health check/i });
    fireEvent.click(probeButton);

    await waitFor(() => {
      expect(screen.getByText('reachable')).toBeInTheDocument();
    });

    // Now click Add
    const addButton = screen.getByRole('button', { name: /add host/i });
    fireEvent.click(addButton);

    await waitFor(() => {
      expect(addCrewSpy).toHaveBeenCalled();
      const call = addCrewSpy.mock.calls[0][0];
      expect(call.host).toBe('worker-1');
      expect(call.site).toBe('local');
      expect(onAdded).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('should render failing checks on 422 response from addCrew', async () => {
    const mockChecklist: client.HealthChecklist = {
      host: 'worker-1',
      ok: true,
      reachable: true,
      agent_ok: true,
      auth_ok: true,
      workspace_ready: true,
      guard_installed: true,
      resources: { cpu: 8 },
      latency_ms: 40,
      checks: [
        { name: 'reachable', ok: true, detail: 'ok' },
      ],
    };

    const failedChecklist = 'Health check failed: auth_ok=false';

    vi.spyOn(client, 'probeCrew').mockResolvedValue(mockChecklist);
    vi.spyOn(client, 'addCrew').mockRejectedValue(new Error(failedChecklist));

    const onClose = vi.fn();
    const onAdded = vi.fn();

    render(<AddHostModal isOpen={true} onClose={onClose} onAdded={onAdded} />);

    const hostInput = screen.getByPlaceholderText(/host/i);
    const siteInput = screen.getByPlaceholderText(/site/i);

    fireEvent.change(hostInput, { target: { value: 'worker-1' } });
    fireEvent.change(siteInput, { target: { value: 'local' } });

    const probeButton = screen.getByRole('button', { name: /probe|run health check/i });
    fireEvent.click(probeButton);

    await waitFor(() => {
      expect(screen.getByText('reachable')).toBeInTheDocument();
    });

    const addButton = screen.getByRole('button', { name: /add host/i });
    fireEvent.click(addButton);

    await waitFor(() => {
      expect(screen.getByText(failedChecklist)).toBeInTheDocument();
    });
  });

  it('should show auth error message when AuthError is thrown', async () => {
    vi.spyOn(client, 'probeCrew').mockRejectedValue(new AuthError('Unauthorized'));

    const onClose = vi.fn();
    const onAdded = vi.fn();

    render(<AddHostModal isOpen={true} onClose={onClose} onAdded={onAdded} />);

    const hostInput = screen.getByPlaceholderText(/host/i);
    const siteInput = screen.getByPlaceholderText(/site/i);

    fireEvent.change(hostInput, { target: { value: 'worker-1' } });
    fireEvent.change(siteInput, { target: { value: 'local' } });

    const probeButton = screen.getByRole('button', { name: /probe|run health check/i });
    fireEvent.click(probeButton);

    await waitFor(() => {
      expect(screen.getByText(/authentication required/i)).toBeInTheDocument();
    });
  });
});
