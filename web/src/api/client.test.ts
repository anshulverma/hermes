import { describe, it, expect, beforeEach, vi } from 'vitest';
import { fetchHealth, fetchRuns, fetchRun, fetchReductions, pauseRun, AuthError, probeCrew, addCrew, reprobeCrew, drainCrew, removeCrew, requeueTicket, abandonTicket, retryTicket, setTicketPriority, acceptReduction, rejectReduction, type HealthResponse, type Run, type Reduction, type HealthChecklist } from './client';
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
        config: { base: 'src', suite: 'unit' },
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
    it('should return raw data without normalization', async () => {
      // fetchReductions now returns raw engine data; normalization happens in view layer
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

      // Assert that raw states are preserved (normalization moved to view layer)
      expect(result[0].member_tickets[0].state).toBe('needs_human');  // unchanged
      expect(result[0].member_tickets[1].state).toBe('done');
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

    it('should surface server detail message on 409 conflict', async () => {
      setToken('valid-token');

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        json: async () => ({ detail: 'illegal transition running->running' }),
      }) as any;

      await expect(pauseRun('run-001')).rejects.toThrow('illegal transition running->running');
    });

    it('should fall back to generic message if response body is not JSON', async () => {
      setToken('valid-token');

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        json: async () => { throw new Error('not json'); },
      }) as any;

      await expect(pauseRun('run-001')).rejects.toThrow('HTTP error! status: 409');
    });
  });

  describe('Crew control endpoints (Phase D2b)', () => {
    beforeEach(() => {
      setToken('test-token');
    });

    describe('probeCrew', () => {
      it('should POST to /api/crew/probe with body and auth header', async () => {
        const mockChecklist: HealthChecklist = {
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
          ],
        };

        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          json: async () => mockChecklist,
        }) as any;

        const result = await probeCrew({ host: 'worker-1', site: 'local', agent: 'claude' });

        expect(result).toEqual(mockChecklist);
        expect(fetch).toHaveBeenCalledWith(
          '/api/crew/probe',
          expect.objectContaining({
            method: 'POST',
            headers: expect.objectContaining({
              'Authorization': 'Bearer test-token',
              'Content-Type': 'application/json',
            }),
            body: JSON.stringify({ host: 'worker-1', site: 'local', agent: 'claude' }),
          })
        );
      });

      it('should handle probe failure with error detail', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: false,
          status: 400,
          json: async () => ({ detail: 'Missing required fields: host, site' }),
        }) as any;

        await expect(probeCrew({ host: '', site: 'local' })).rejects.toThrow('Missing required fields: host, site');
      });
    });

    describe('addCrew', () => {
      it('should POST to /api/crew with body and auth header', async () => {
        const mockMember = {
          id: 'worker-1',
          site: 'local',
          state: 'idle',
          capabilities: [],
          resources: { cpu: 8 },
          health: { reachable: true, agent_ok: true, auth_ok: true, workspace_ready: true, guard_installed: true, latency_ms: 42 },
          current_ticket: null,
          last_heartbeat: 1234567890,
        };

        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          json: async () => mockMember,
        }) as any;

        const result = await addCrew({ host: 'worker-1', site: 'local', agent: 'claude', base_ref: 'main' });

        expect(result).toEqual(mockMember);
        expect(fetch).toHaveBeenCalledWith(
          '/api/crew',
          expect.objectContaining({
            method: 'POST',
            headers: expect.objectContaining({
              'Authorization': 'Bearer test-token',
              'Content-Type': 'application/json',
            }),
            body: JSON.stringify({ host: 'worker-1', site: 'local', agent: 'claude', base_ref: 'main' }),
          })
        );
      });

      it('should surface 422 failing-checks detail', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: false,
          status: 422,
          json: async () => ({ detail: 'Health check failed: auth_ok=false, workspace_ready=false' }),
        }) as any;

        await expect(addCrew({ host: 'unhealthy', site: 'local' })).rejects.toThrow('Health check failed: auth_ok=false, workspace_ready=false');
      });
    });

    describe('reprobeCrew', () => {
      it('should POST to /api/crew/{host}/reprobe with optional agent', async () => {
        const mockChecklist: HealthChecklist = {
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

        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          json: async () => mockChecklist,
        }) as any;

        const result = await reprobeCrew('worker-1', 'claude');

        expect(result).toEqual(mockChecklist);
        expect(fetch).toHaveBeenCalledWith(
          '/api/crew/worker-1/reprobe',
          expect.objectContaining({
            method: 'POST',
            headers: expect.objectContaining({
              'Authorization': 'Bearer test-token',
              'Content-Type': 'application/json',
            }),
            body: JSON.stringify({ agent: 'claude' }),
          })
        );
      });

      it('should handle reprobe without agent', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          json: async () => ({
            host: 'worker-1',
            ok: true,
            reachable: true,
            agent_ok: true,
            auth_ok: true,
            workspace_ready: true,
            guard_installed: true,
            resources: {},
            latency_ms: 40,
            checks: [],
          }),
        }) as any;

        await reprobeCrew('worker-1');

        expect(fetch).toHaveBeenCalledWith(
          '/api/crew/worker-1/reprobe',
          expect.objectContaining({
            method: 'POST',
            body: JSON.stringify({}),
          })
        );
      });

      it('should throw 404 if host not found', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: false,
          status: 404,
          json: async () => ({ detail: "Crew member 'unknown-host' not found" }),
        }) as any;

        await expect(reprobeCrew('unknown-host')).rejects.toThrow("Crew member 'unknown-host' not found");
      });
    });

    describe('drainCrew', () => {
      it('should POST to /api/crew/{host}/drain and return new state', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          json: async () => ({ state: 'draining' }),
        }) as any;

        const result = await drainCrew('worker-1');

        expect(result).toEqual({ state: 'draining' });
        expect(fetch).toHaveBeenCalledWith(
          '/api/crew/worker-1/drain',
          expect.objectContaining({
            method: 'POST',
            headers: expect.objectContaining({
              'Authorization': 'Bearer test-token',
            }),
          })
        );
      });
    });

    describe('removeCrew', () => {
      it('should DELETE /api/crew/{host} with auth header', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          json: async () => ({ status: 'removed' }),
        }) as any;

        const result = await removeCrew('worker-1');

        expect(result).toEqual({ status: 'removed' });
        expect(fetch).toHaveBeenCalledWith(
          '/api/crew/worker-1',
          expect.objectContaining({
            method: 'DELETE',
            headers: expect.objectContaining({
              'Authorization': 'Bearer test-token',
            }),
          })
        );
      });

      it('should throw 404 if host not found', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: false,
          status: 404,
          json: async () => ({ detail: "Crew member 'unknown' not found" }),
        }) as any;

        await expect(removeCrew('unknown')).rejects.toThrow("Crew member 'unknown' not found");
      });
    });
  });

  describe('Ticket control endpoints (Phase D3)', () => {
    beforeEach(() => {
      setToken('test-token');
    });

    describe('requeueTicket', () => {
      it('should POST to /api/tickets/{id}/requeue with auth header', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          json: async () => ({ state: 'queued' }),
        }) as any;

        const result = await requeueTicket('ticket-123');

        expect(result).toEqual({ state: 'queued' });
        expect(fetch).toHaveBeenCalledWith(
          '/api/tickets/ticket-123/requeue',
          expect.objectContaining({
            method: 'POST',
            headers: expect.objectContaining({
              'Authorization': 'Bearer test-token',
            }),
          })
        );
      });

      it('should throw 404 if ticket not found', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: false,
          status: 404,
          json: async () => ({ detail: "Ticket 'unknown' not found" }),
        }) as any;

        await expect(requeueTicket('unknown')).rejects.toThrow("Ticket 'unknown' not found");
      });

      it('should throw 409 with server detail if ticket not needs_human', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: false,
          status: 409,
          json: async () => ({ detail: "ticket 'ticket-123' is 'queued', not 'needs_human'; cannot operator-requeue" }),
        }) as any;

        await expect(requeueTicket('ticket-123')).rejects.toThrow("ticket 'ticket-123' is 'queued', not 'needs_human'; cannot operator-requeue");
      });

      it('should throw AuthError on 401', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: false,
          status: 401,
          statusText: 'Unauthorized',
        }) as any;

        await expect(requeueTicket('ticket-123')).rejects.toThrow(AuthError);
      });
    });

    describe('abandonTicket', () => {
      it('should POST to /api/tickets/{id}/abandon with auth header', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          json: async () => ({ state: 'failed' }),
        }) as any;

        const result = await abandonTicket('ticket-123');

        expect(result).toEqual({ state: 'failed' });
        expect(fetch).toHaveBeenCalledWith(
          '/api/tickets/ticket-123/abandon',
          expect.objectContaining({
            method: 'POST',
            headers: expect.objectContaining({ 'Authorization': 'Bearer test-token' }),
          })
        );
      });

      it('should throw 409 with server detail if ticket terminal', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: false,
          status: 409,
          json: async () => ({ detail: "ticket 'ticket-123' is terminal ('done'); cannot abandon" }),
        }) as any;

        await expect(abandonTicket('ticket-123')).rejects.toThrow("ticket 'ticket-123' is terminal ('done'); cannot abandon");
      });

      it('should throw AuthError on 401', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: false,
          status: 401,
          statusText: 'Unauthorized',
        }) as any;

        await expect(abandonTicket('ticket-123')).rejects.toThrow(AuthError);
      });
    });

    describe('retryTicket', () => {
      it('should POST to /api/tickets/{id}/retry with auth header', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          json: async () => ({ state: 'queued' }),
        }) as any;

        const result = await retryTicket('ticket-123');

        expect(result).toEqual({ state: 'queued' });
        expect(fetch).toHaveBeenCalledWith(
          '/api/tickets/ticket-123/retry',
          expect.objectContaining({
            method: 'POST',
            headers: expect.objectContaining({ 'Authorization': 'Bearer test-token' }),
          })
        );
      });

      it('should throw 409 with server detail if ticket not failed', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: false,
          status: 409,
          json: async () => ({ detail: "ticket 'ticket-123' is 'running', not 'failed'; cannot retry" }),
        }) as any;

        await expect(retryTicket('ticket-123')).rejects.toThrow("ticket 'ticket-123' is 'running', not 'failed'; cannot retry");
      });
    });

    describe('setTicketPriority', () => {
      it('should POST to /api/tickets/{id}/priority with priority body and auth header', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          json: async () => ({ state: 'queued' }),
        }) as any;

        const result = await setTicketPriority('ticket-123', 5);

        expect(result).toEqual({ state: 'queued' });
        expect(fetch).toHaveBeenCalledWith(
          '/api/tickets/ticket-123/priority',
          expect.objectContaining({
            method: 'POST',
            body: JSON.stringify({ priority: 5 }),
            headers: expect.objectContaining({ 'Authorization': 'Bearer test-token' }),
          })
        );
      });

      it('should throw 409 with server detail if ticket terminal', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: false,
          status: 409,
          json: async () => ({ detail: "ticket 'ticket-123' is terminal ('done'); cannot reprioritize" }),
        }) as any;

        await expect(setTicketPriority('ticket-123', 2)).rejects.toThrow("cannot reprioritize");
      });
    });
  });

  describe('Reduction control endpoints (Phase D4)', () => {
    beforeEach(() => {
      setToken('test-token');
    });

    describe('acceptReduction', () => {
      it('should POST to /api/reductions/{id}/accept with auth header', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          json: async () => ({ review_state: 'accepted' }),
        }) as any;

        const result = await acceptReduction(1);

        expect(result).toEqual({ review_state: 'accepted' });
        expect(fetch).toHaveBeenCalledWith(
          '/api/reductions/1/accept',
          expect.objectContaining({
            method: 'POST',
            headers: expect.objectContaining({
              'Authorization': 'Bearer test-token',
            }),
          })
        );
      });

      it('should throw 404 if reduction not found', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: false,
          status: 404,
          json: async () => ({ detail: "Reduction 999 not found" }),
        }) as any;

        await expect(acceptReduction(999)).rejects.toThrow("Reduction 999 not found");
      });

      it('should throw 409 with server detail if reduction already resolved', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: false,
          status: 409,
          json: async () => ({ detail: "reduction 1 is 'accepted', not 'pending'; already resolved" }),
        }) as any;

        await expect(acceptReduction(1)).rejects.toThrow("reduction 1 is 'accepted', not 'pending'; already resolved");
      });

      it('should throw AuthError on 401', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: false,
          status: 401,
          statusText: 'Unauthorized',
        }) as any;

        await expect(acceptReduction(1)).rejects.toThrow(AuthError);
      });
    });

    describe('rejectReduction', () => {
      it('should POST to /api/reductions/{id}/reject with auth header', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          json: async () => ({ review_state: 'rejected' }),
        }) as any;

        const result = await rejectReduction(2);

        expect(result).toEqual({ review_state: 'rejected' });
        expect(fetch).toHaveBeenCalledWith(
          '/api/reductions/2/reject',
          expect.objectContaining({
            method: 'POST',
            headers: expect.objectContaining({
              'Authorization': 'Bearer test-token',
            }),
          })
        );
      });

      it('should throw 404 if reduction not found', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: false,
          status: 404,
          json: async () => ({ detail: "Reduction 999 not found" }),
        }) as any;

        await expect(rejectReduction(999)).rejects.toThrow("Reduction 999 not found");
      });

      it('should throw 409 with server detail if reduction already resolved', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: false,
          status: 409,
          json: async () => ({ detail: "reduction 2 is 'rejected', not 'pending'; already resolved" }),
        }) as any;

        await expect(rejectReduction(2)).rejects.toThrow("reduction 2 is 'rejected', not 'pending'; already resolved");
      });

      it('should throw AuthError on 401', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: false,
          status: 401,
          statusText: 'Unauthorized',
        }) as any;

        await expect(rejectReduction(2)).rejects.toThrow(AuthError);
      });
    });
  });
});
