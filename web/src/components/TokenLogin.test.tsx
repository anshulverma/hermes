/**
 * Tests for TokenLogin component (Phase D1b).
 * Shows only when remote + no token, setToken proceeds.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import TokenLogin from './TokenLogin';
import { clearToken, setToken, getToken } from '../api/auth';

describe('TokenLogin', () => {
  beforeEach(() => {
    vi.restoreAllMocks();

    // Reset auth state
    clearToken();
    delete (window as any).__HERMES_TOKEN__;
    delete (window as any).__HERMES_BIND__;
  });

  describe('Visibility conditions', () => {
    it('shows login form when remote and no token', () => {
      (window as any).__HERMES_BIND__ = 'remote';

      render(<TokenLogin onAuthenticated={vi.fn()} />);

      expect(screen.getByLabelText(/token/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /login/i })).toBeInTheDocument();
    });

    it('does NOT show when loopback (token bootstrapped)', () => {
      (window as any).__HERMES_BIND__ = 'loopback';
      (window as any).__HERMES_TOKEN__ = 'bootstrap-token';

      const { container } = render(<TokenLogin onAuthenticated={vi.fn()} />);

      expect(container.firstChild).toBeNull(); // Component renders nothing
    });

    it('does NOT show when remote but token already set', () => {
      (window as any).__HERMES_BIND__ = 'remote';
      setToken('already-have-token');

      const { container } = render(<TokenLogin onAuthenticated={vi.fn()} />);

      expect(container.firstChild).toBeNull();
    });

    it('does NOT show when loopback and no token (token will be bootstrapped)', () => {
      (window as any).__HERMES_BIND__ = 'loopback';
      // No token set - this is OK on loopback, token comes from window.__HERMES_TOKEN__

      const { container } = render(<TokenLogin onAuthenticated={vi.fn()} />);

      expect(container.firstChild).toBeNull();
    });
  });

  describe('Login flow', () => {
    it('calls setToken and onAuthenticated when user submits valid token', async () => {
      (window as any).__HERMES_BIND__ = 'remote';

            const onAuthenticated = vi.fn();

      render(<TokenLogin onAuthenticated={onAuthenticated} />);

      const input = screen.getByLabelText(/token/i);
      const submitButton = screen.getByRole('button', { name: /login/i });

      fireEvent.change(input, { target: { value: 'my-secret-token-123' } });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(getToken()).toBe('my-secret-token-123');
        expect(onAuthenticated).toHaveBeenCalled();
      });
    });

    it('does not submit when input is empty', async () => {
      (window as any).__HERMES_BIND__ = 'remote';

            const onAuthenticated = vi.fn();

      render(<TokenLogin onAuthenticated={onAuthenticated} />);

      const submitButton = screen.getByRole('button', { name: /login/i });

      fireEvent.click(submitButton);

      // Should not proceed (input validation)
      expect(onAuthenticated).not.toHaveBeenCalled();
    });

    it('trims whitespace from token input', async () => {
      (window as any).__HERMES_BIND__ = 'remote';

            const onAuthenticated = vi.fn();

      render(<TokenLogin onAuthenticated={onAuthenticated} />);

      const input = screen.getByLabelText(/token/i);
      const submitButton = screen.getByRole('button', { name: /login/i });

      fireEvent.change(input, { target: { value: '  token-with-spaces  ' } });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(getToken()).toBe('token-with-spaces'); // trimmed
        expect(onAuthenticated).toHaveBeenCalled();
      });
    });
  });
});
