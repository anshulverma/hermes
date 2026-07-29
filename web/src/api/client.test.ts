import { describe, it, expect, beforeEach, vi } from 'vitest';
import { fetchHealth, fetchRuns, fetchRun, type HealthResponse, type Run } from './client';

describe('API client', () => {
  beforeEach(() => {
    // Clear all mocks before each test
    vi.restoreAllMocks();
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
      expect(fetch).toHaveBeenCalledWith('/api/health');
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
      expect(fetch).toHaveBeenCalledWith('/api/runs');
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
      expect(fetch).toHaveBeenCalledWith('/api/runs/run-001');
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
});
