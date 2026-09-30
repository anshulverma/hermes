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

    it('offers ONLY Reopen when run state is "failed" (terminal)', () => {
      render(<RunControl runId="run-001" runState="failed" onSuccess={vi.fn()} />);

      // Lifecycle controls are gone, but a finished run can be put back to work.
      expect(screen.queryByRole('button', { name: /pause/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /resume/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /^stop$/i })).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: /reopen/i })).toBeInTheDocument();
    });

    it('reopens a finished run and reports success', async () => {
      const onSuccess = vi.fn();
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ state: 'running' }),
      }) as any;

      render(<RunControl runId="run-001" runState="done" onSuccess={onSuccess} />);
      screen.getByRole('button', { name: /reopen/i }).click();

      await waitFor(() => {
        expect(fetch).toHaveBeenCalledWith(
          '/api/runs/run-001/reopen',
          expect.objectContaining({ method: 'POST' }),
        );
      });
      await waitFor(() => expect(onSuccess).toHaveBeenCalled());
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

  describe('Focus after a state change', () => {
    const succeed = (state: string) =>
      (globalThis.fetch as any).mockResolvedValue({ ok: true, json: async () => ({ state }) });

    it('moves focus to Resume once the refetched state replaces Pause', async () => {
      succeed('paused');
      const onSuccess = vi.fn();
      const { rerender } = render(<RunControl runId="run-001" runState="running" onSuccess={onSuccess} />);

      fireEvent.click(screen.getByRole('button', { name: 'Pause' }));
      await waitFor(() => expect(onSuccess).toHaveBeenCalled());
      rerender(<RunControl runId="run-001" runState="paused" onSuccess={onSuccess} />);

      const resume = screen.getByRole('button', { name: 'Resume' });
      expect(resume).toHaveFocus();

      // One press moves focus once: the next state change leaves it alone.
      resume.blur();
      rerender(<RunControl runId="run-001" runState="running" onSuccess={onSuccess} />);
      expect(document.body).toHaveFocus();
    });

    it('moves focus to Pause once the refetched state replaces Resume', async () => {
      succeed('running');
      const onSuccess = vi.fn();
      const { rerender } = render(<RunControl runId="run-001" runState="paused" onSuccess={onSuccess} />);

      fireEvent.click(screen.getByRole('button', { name: 'Resume' }));
      await waitFor(() => expect(onSuccess).toHaveBeenCalled());
      // Focus still inside the control (tabbed on to Stop) still follows.
      screen.getByRole('button', { name: 'Stop' }).focus();
      rerender(<RunControl runId="run-001" runState="running" onSuccess={onSuccess} />);

      expect(screen.getByRole('button', { name: 'Pause' })).toHaveFocus();
    });

    it('moves focus to Reopen after a confirmed Stop', async () => {
      succeed('stopped');
      const onSuccess = vi.fn();
      const { rerender } = render(<RunControl runId="run-001" runState="running" onSuccess={onSuccess} />);

      fireEvent.click(screen.getByRole('button', { name: 'Stop' }));
      fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
      await waitFor(() => expect(onSuccess).toHaveBeenCalled());
      rerender(<RunControl runId="run-001" runState="stopped" onSuccess={onSuccess} />);

      expect(screen.getByRole('button', { name: 'Reopen' })).toHaveFocus();
    });

    it('moves focus to Pause after Reopen', async () => {
      succeed('running');
      const onSuccess = vi.fn();
      const { rerender } = render(<RunControl runId="run-001" runState="done" onSuccess={onSuccess} />);

      fireEvent.click(screen.getByRole('button', { name: 'Reopen' }));
      await waitFor(() => expect(onSuccess).toHaveBeenCalled());
      rerender(<RunControl runId="run-001" runState="running" onSuccess={onSuccess} />);

      expect(screen.getByRole('button', { name: 'Pause' })).toHaveFocus();
    });

    it('focuses Cancel when the Stop confirmation opens and returns focus to Stop on Cancel', () => {
      render(<RunControl runId="run-001" runState="running" onSuccess={vi.fn()} />);

      fireEvent.click(screen.getByRole('button', { name: 'Stop' }));
      expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus();

      fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
      expect(screen.getByRole('button', { name: 'Stop' })).toHaveFocus();
    });

    it('leaves focus where you moved it before the refetched state arrived, and stays disarmed', async () => {
      succeed('paused');
      const onSuccess = vi.fn();
      const view = (runState: string) => (
        <>
          <input aria-label="Filter runs" />
          <RunControl runId="run-001" runState={runState} onSuccess={onSuccess} />
        </>
      );
      const { rerender } = render(view('running'));

      fireEvent.click(screen.getByRole('button', { name: 'Pause' }));
      await waitFor(() => expect(onSuccess).toHaveBeenCalled());
      const filter = screen.getByRole('textbox', { name: 'Filter runs' });
      filter.focus();
      rerender(view('paused'));

      expect(filter).toHaveFocus();

      // The press was used up: a later state change with focus lost moves nothing.
      filter.blur();
      rerender(view('running'));
      expect(document.body).toHaveFocus();
    });

    it('leaves focus alone when the state changes without a press here', () => {
      const { rerender } = render(<RunControl runId="run-001" runState="running" onSuccess={vi.fn()} />);

      rerender(<RunControl runId="run-001" runState="paused" onSuccess={vi.fn()} />);

      expect(screen.getByRole('button', { name: 'Resume' })).not.toHaveFocus();
      expect(document.body).toHaveFocus();
    });

    it('does not move focus after a control fails', async () => {
      (globalThis.fetch as any).mockResolvedValue({
        ok: false,
        status: 409,
        json: async () => ({ detail: 'illegal transition' }),
      });
      const presses = [
        { from: 'running', press: ['Pause'], to: 'paused' },
        { from: 'running', press: ['Stop', 'Confirm'], to: 'stopped' },
        { from: 'paused', press: ['Resume'], to: 'running' },
        { from: 'done', press: ['Reopen'], to: 'running' },
      ];
      for (const { from, press, to } of presses) {
        const { rerender, unmount } = render(
          <RunControl runId="run-001" runState={from} onSuccess={vi.fn()} />,
        );

        for (const name of press) fireEvent.click(screen.getByRole('button', { name }));
        await screen.findByText('illegal transition');
        rerender(<RunControl runId="run-001" runState={to} onSuccess={vi.fn()} />);

        expect(document.body, press.join(' then ')).toHaveFocus();
        unmount();
      }
    });
  });
});
