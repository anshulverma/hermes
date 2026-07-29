import { describe, it, expect, beforeEach, vi } from 'vitest';
import { fetchHealth, fetchRuns, fetchRun, fetchReductions, pauseRun, AuthError, type HealthResponse, type Run, type Reduction } from './client';
import { clearToken, setToken } from './auth';

describe('API client', () => {
  beforeEach(() => {
    // Clear all mocks before each test
    vi.restoreAllMocks();

    // Clear auth state
    clearToken();
    delete (window as any).__HERMES_TOKEN__;
    delete (window as any).__HERMES_BIND__;
  });

  describe('fetchHealth', () => {
    it('should fetch health status successfully', async () => {
      const mockResponse: HealthResponse = {
        status: 'ok',
        version: '0.1.0',
        home: '/tmp/hermes',
      };

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => mockResponse,
      }) as any;

      const result = await fetchHealth();
      expect(result).toEqual(mockResponse);
      expect(fetch).toHaveBeenCalledWith('/api/health', expect.objectContaining({
        headers: expect.any(Object),
      }));
    });

    it('should throw on fetch error', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
      }) as any;

      await expect(fetchHealth()).rejects.toThrow('HTTP error! status: 500');
    });
  });

  describe('fetchRuns', () => {
    it('should return empty array when no runs exist', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [],
      }) as any;

      const result = await fetchRuns();
      expect(result).toEqual([]);
      // Just verify it was called; headers are tested in auth integration tests
      expect(fetch).toHaveBeenCalled();
    });

    it('should fetch runs with ticket counts', async () => {
      const mockRuns: Run[] = [
        {
          id: 'run-001',
          playbook: 'mechanic',
          site: 'local',
          state: 'running',
          phase: 'gather',
          base_ref: 'main',
          created_at: '2026-07-29T10:00:00Z',
          tickets: {
            queued: 5,
            in_flight: 2,
            done: 10,
          },
        },
      ];

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => mockRuns,
      }) as any;

      const result = await fetchRuns();
      expect(result).toEqual(mockRuns);
    });
  });

  describe('fetchRun', () => {
    it('should fetch a single run with detailed info', async () => {
      const mockRun = {
        id: 'run-001',
        playbook: 'mechanic',
        site: 'local',
        state: 'running',
        phase: 'gather',
        base_ref: 'main',
        config: { base: 'fbcode', suite: 'unit' },
        created_at: '2026-07-29T10:00:00Z',
        updated_at: '2026-07-29T10:30:00Z',
        tickets: {
          queued: 5,
          in_flight: 2,
          done: 10,
        },
        phases: {
          gather: { queued: 3, in_flight: 1, done: 5 },
        },
      };

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => mockRun,
      }) as any;

      const result = await fetchRun('run-001');
      expect(result).toEqual(mockRun);
      expect(fetch).toHaveBeenCalled();
    });

    it('should throw on 404', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        statusText: 'Not Found',
      }) as any;

      await expect(fetchRun('no-such-run')).rejects.toThrow('HTTP error! status: 404');
    });
  });

  describe('fetchReductions', () => {
    it('should normalize member ticket states from engine vocab to UI vocab', async () => {
      // Phase B6 Finding 1: server returns needs_human (engine), must normalize to needs-human (UI)
      const mockResponse: Reduction[] = [
        {
          id: 1,
          run_id: 'run-001',
          phase: 'reduce',
          kind: 'test',
          json: { title: 'Test finding' },
          review_state: 'pending',
          member_ticket_ids: ['t-1', 't-2'],
          member_tickets: [
            { id: 't-1', state: 'needs_human', phase: 'reduce' },  // RAW engine state
            { id: 't-2', state: 'done', phase: 'reduce' },
          ],
        },
      ];

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => mockResponse,
      }) as any;

      const result = await fetchReductions('run-001');

      // Assert that member ticket states are normalized
      expect(result[0].member_tickets[0].state).toBe('needs-human');  // underscore → hyphen
      expect(result[0].member_tickets[1].state).toBe('done');  // no change
      expect(fetch).toHaveBeenCalled();
    });

    it('should preserve phase filter in query string', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [],
      }) as any;

      await fetchReductions('run-001', 'reduce');
      // Verify URL construction (first arg of first call)
      expect((fetch as any).mock.calls[0][0]).toBe('/api/runs/run-001/reductions?phase=reduce');
    });
  });

  describe('Auth integration (Phase D1b)', () => {
    it('should include Authorization header on mutations when token is present', async () => {
      setToken('test-bearer-token');

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ state: 'paused' }),
      }) as any;

      await pauseRun('run-001');

      // Assert Authorization header was sent
      expect(fetch).toHaveBeenCalledWith(
        '/api/runs/run-001/pause',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Authorization': 'Bearer test-bearer-token',
          }),
        })
      );
    });

    it('should throw AuthError on 401 response', async () => {
      setToken('invalid-token');

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        statusText: 'Unauthorized',
      }) as any;

      await expect(pauseRun('run-001')).rejects.toThrow(AuthError);
      await expect(pauseRun('run-001')).rejects.toThrow('Unauthorized');
    });

    it('should allow GET requests on loopback without token', async () => {
      // No token set, simulating loopback (default)
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: 'ok', version: '0.1.0', home: '/tmp/hermes' }),
      }) as any;

      const result = await fetchHealth();

      expect(result.status).toBe('ok');
      // Verify no auth header on loopback GET
      const callHeaders = (fetch as any).mock.calls[0][1].headers;
      expect(callHeaders.Authorization).toBeUndefined();
    });

    it('should include Authorization header on GETs when remote and token present', async () => {
      (window as any).__HERMES_BIND__ = 'remote';
      setToken('remote-token');

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [],
      }) as any;

      await fetchRuns();

      // Remote mode should send token on GETs
      expect(fetch).toHaveBeenCalledWith(
        '/api/runs',
        expect.objectContaining({
          headers: expect.objectContaining({
            'Authorization': 'Bearer remote-token',
          }),
        })
      );
    });

    it('should throw generic Error on non-401 failures', async () => {
      setToken('valid-token');

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
      }) as any;

      await expect(pauseRun('run-001')).rejects.toThrow('HTTP error! status: 500');
      // Should NOT be an AuthError instance
      try {
        await pauseRun('run-001');
      } catch (e) {
        expect(e).not.toBeInstanceOf(AuthError);
      }
    });
  });
});
