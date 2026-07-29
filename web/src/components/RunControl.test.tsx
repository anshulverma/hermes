/**
 * Tests for RunControl component (Phase D1b).
 * Legal-transitions-only, auth headers, 409 handling, Stop confirmation.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import RunControl from './RunControl';
import { clearToken, setToken } from '../api/auth';

describe('RunControl', () => {
  beforeEach(() => {
    vi.restoreAllMocks();

    // Setup auth
    clearToken();
    setToken('test-control-token');

    // Mock fetch
    globalThis.fetch = vi.fn();
  });

  describe('Legal transitions only', () => {
    it('shows only Pause and Stop when run state is "running"', () => {
      render(<RunControl runId="run-001" runState="running" onSuccess={vi.fn()} />);

      expect(screen.getByRole('button', { name: /pause/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /stop/i })).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /resume/i })).not.toBeInTheDocument();
    });

    it('shows only Resume and Stop when run state is "paused"', () => {
      render(<RunControl runId="run-001" runState="paused" onSuccess={vi.fn()} />);

      expect(screen.getByRole('button', { name: /resume/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /stop/i })).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /pause/i })).not.toBeInTheDocument();
    });

    it('shows NO controls when run state is "done" (terminal)', () => {
      render(<RunControl runId="run-001" runState="done" onSuccess={vi.fn()} />);

      expect(screen.queryByRole('button', { name: /pause/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /resume/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /stop/i })).not.toBeInTheDocument();
    });

    it('shows NO controls when run state is "stopped" (terminal)', () => {
      render(<RunControl runId="run-001" runState="stopped" onSuccess={vi.fn()} />);

      expect(screen.queryByRole('button', { name: /pause/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /resume/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /stop/i })).not.toBeInTheDocument();
    });

    it('shows NO controls when run state is "failed" (terminal)', () => {
      render(<RunControl runId="run-001" runState="failed" onSuccess={vi.fn()} />);

      expect(screen.queryByRole('button')).not.toBeInTheDocument();
    });
  });

  describe('Pause action', () => {
    it('sends POST to /api/runs/{id}/pause with Authorization header', async () => {
            const onSuccess = vi.fn();

      (globalThis.fetch as any).mockResolvedValue({
        ok: true,
        json: async () => ({ state: 'paused' }),
      });

      render(<RunControl runId="run-001" runState="running" onSuccess={onSuccess} />);

      fireEvent.click(screen.getByRole('button', { name: /pause/i }));

      await waitFor(() => {
        expect(fetch).toHaveBeenCalledWith(
          '/api/runs/run-001/pause',
          expect.objectContaining({
            method: 'POST',
            headers: expect.objectContaining({
              'Authorization': 'Bearer test-control-token',
            }),
          })
        );
      });

      expect(onSuccess).toHaveBeenCalled();
    });

    it('shows error on 409 (illegal transition)', async () => {

      (globalThis.fetch as any).mockResolvedValue({
        ok: false,
        status: 409,
        statusText: 'Conflict',
        json: async () => ({ detail: 'Cannot pause: run is not running' }),
      });

      render(<RunControl runId="run-001" runState="running" onSuccess={vi.fn()} />);

      fireEvent.click(screen.getByRole('button', { name: /pause/i }));

      await waitFor(() => {
        expect(screen.getByText(/cannot pause/i)).toBeInTheDocument();
      });
    });

    it('displays actual server detail message on 409', async () => {
      (globalThis.fetch as any).mockResolvedValue({
        ok: false,
        status: 409,
        json: async () => ({ detail: 'illegal transition running->running' }),
      });

      render(<RunControl runId="run-001" runState="running" onSuccess={vi.fn()} />);

      fireEvent.click(screen.getByRole('button', { name: /pause/i }));

      await waitFor(() => {
        expect(screen.getByText('illegal transition running->running')).toBeInTheDocument();
      });
    });

    it('shows error on 401 (auth failure)', async () => {
      
      (globalThis.fetch as any).mockResolvedValue({
        ok: false,
        status: 401,
        statusText: 'Unauthorized',
      });

      render(<RunControl runId="run-001" runState="running" onSuccess={vi.fn()} />);

      fireEvent.click(screen.getByRole('button', { name: /pause/i }));

      await waitFor(() => {
        expect(screen.getByText(/unauthorized/i)).toBeInTheDocument();
      });
    });
  });

  describe('Resume action', () => {
    it('sends POST to /api/runs/{id}/resume with Authorization header', async () => {
            const onSuccess = vi.fn();

      (globalThis.fetch as any).mockResolvedValue({
        ok: true,
        json: async () => ({ state: 'running' }),
      });

      render(<RunControl runId="run-001" runState="paused" onSuccess={onSuccess} />);

      fireEvent.click(screen.getByRole('button', { name: /resume/i }));

      await waitFor(() => {
        expect(fetch).toHaveBeenCalledWith(
          '/api/runs/run-001/resume',
          expect.objectContaining({
            method: 'POST',
            headers: expect.objectContaining({
              'Authorization': 'Bearer test-control-token',
            }),
          })
        );
      });

      expect(onSuccess).toHaveBeenCalled();
    });
  });

  describe('Stop action', () => {
    it('requires confirmation before sending request', async () => {
      
      (globalThis.fetch as any).mockResolvedValue({
        ok: true,
        json: async () => ({ state: 'stopped' }),
      });

      render(<RunControl runId="run-001" runState="running" onSuccess={vi.fn()} />);

      fireEvent.click(screen.getByRole('button', { name: /stop/i }));

      // Confirmation dialog should appear
      expect(screen.getByText(/confirm stop/i)).toBeInTheDocument();

      // Fetch should NOT have been called yet
      expect(fetch).not.toHaveBeenCalled();
    });

    it('sends POST to /api/runs/{id}/stop after confirmation', async () => {
            const onSuccess = vi.fn();

      (globalThis.fetch as any).mockResolvedValue({
        ok: true,
        json: async () => ({ state: 'stopped' }),
      });

      render(<RunControl runId="run-001" runState="running" onSuccess={onSuccess} />);

      fireEvent.click(screen.getByRole('button', { name: /stop/i }));

      // Confirm the action
      fireEvent.click(screen.getByRole('button', { name: /confirm/i }));

      await waitFor(() => {
        expect(fetch).toHaveBeenCalledWith(
          '/api/runs/run-001/stop',
          expect.objectContaining({
            method: 'POST',
            headers: expect.objectContaining({
              'Authorization': 'Bearer test-control-token',
            }),
          })
        );
      });

      expect(onSuccess).toHaveBeenCalled();
    });

    it('does NOT send request if user cancels confirmation', async () => {
      
      render(<RunControl runId="run-001" runState="running" onSuccess={vi.fn()} />);

      fireEvent.click(screen.getByRole('button', { name: /stop/i }));

      // Cancel the action
      fireEvent.click(screen.getByRole('button', { name: /cancel/i }));

      // Fetch should NOT have been called
      expect(fetch).not.toHaveBeenCalled();
    });
  });
});
