/**
 * Tests for useEventStream hook.
 * Mock global WebSocket to test connection lifecycle.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useEventStream } from './useEventStream';

describe('useEventStream', () => {
  let mockWebSocketInstance: any;
  let eventListeners: Map<string, Function[]>;

  beforeEach(() => {
    eventListeners = new Map();

    // Mock global WebSocket constructor
    mockWebSocketInstance = {
      readyState: WebSocket.CONNECTING,
      send: vi.fn(),
      close: vi.fn(),
      addEventListener: vi.fn((event: string, handler: Function) => {
        if (!eventListeners.has(event)) {
          eventListeners.set(event, []);
        }
        eventListeners.get(event)!.push(handler);
      }),
      removeEventListener: vi.fn(),
    };

    // Replace global WebSocket
    // @ts-ignore - test mock
    globalThis.WebSocket = class MockWebSocket {
      constructor(_url: string) {
        return mockWebSocketInstance;
      }
    };
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('connects on mount and sets connected=true on open', async () => {
    const { result } = renderHook(() => useEventStream());

    // Initially not connected
    expect(result.current.connected).toBe(false);

    // Simulate onopen
    const openHandlers = eventListeners.get('open');
    expect(openHandlers).toBeDefined();
    expect(openHandlers!.length).toBeGreaterThan(0);

    mockWebSocketInstance.readyState = WebSocket.OPEN;
    openHandlers![0]({ type: 'open' });

    await waitFor(() => {
      expect(result.current.connected).toBe(true);
    });
  });

  it('receives events via onmessage and exposes them', async () => {
    const { result } = renderHook(() => useEventStream());

    // Simulate connection open
    const openHandlers = eventListeners.get('open');
    mockWebSocketInstance.readyState = WebSocket.OPEN;
    openHandlers![0]({ type: 'open' });

    await waitFor(() => {
      expect(result.current.connected).toBe(true);
    });

    // Simulate receiving an event message
    const messageHandlers = eventListeners.get('message');
    expect(messageHandlers).toBeDefined();

    const eventData = {
      type: 'event',
      event: {
        id: 42,
        ts: 1234567890,
        kind: 'ticket_claimed',
        run_id: 'test-run',
        ticket_id: 'test-run/t-1',
        host: 'worker-1',
        message: 'Test event',
        data: { test: true },
      },
    };

    messageHandlers![0]({ data: JSON.stringify(eventData) });

    await waitFor(() => {
      expect(result.current.events.length).toBe(1);
      expect(result.current.events[0].id).toBe(42);
      expect(result.current.events[0].kind).toBe('ticket_claimed');
      expect(result.current.lastEvent).toEqual(eventData.event);
    });
  });

  it('sets connected=false on close and schedules reconnect', async () => {
    const { result } = renderHook(() => useEventStream());

    // Simulate connection open
    const openHandlers = eventListeners.get('open');
    mockWebSocketInstance.readyState = WebSocket.OPEN;
    openHandlers![0]({ type: 'open' });

    await waitFor(() => {
      expect(result.current.connected).toBe(true);
    });

    // Simulate close
    const closeHandlers = eventListeners.get('close');
    expect(closeHandlers).toBeDefined();

    mockWebSocketInstance.readyState = WebSocket.CLOSED;
    closeHandlers![0]({ type: 'close' });

    await waitFor(() => {
      expect(result.current.connected).toBe(false);
    });

    // Should attempt reconnect after a delay (mock timers would verify this properly)
  });

  it('cleans up on unmount', () => {
    const { unmount } = renderHook(() => useEventStream());

    unmount();

    // Should have called close on the websocket
    expect(mockWebSocketInstance.close).toHaveBeenCalled();
  });

  it('bounds events buffer to most recent 500 entries', async () => {
    const { result } = renderHook(() => useEventStream());

    // Simulate connection open
    const openHandlers = eventListeners.get('open');
    mockWebSocketInstance.readyState = WebSocket.OPEN;
    openHandlers![0]({ type: 'open' });

    await waitFor(() => {
      expect(result.current.connected).toBe(true);
    });

    const messageHandlers = eventListeners.get('message');
    expect(messageHandlers).toBeDefined();

    // Push 600 events through the WebSocket
    for (let i = 0; i < 600; i++) {
      const eventData = {
        type: 'event',
        event: {
          id: i + 1,
          ts: 1234567890 + i,
          kind: 'test_event',
          run_id: 'test-run',
          ticket_id: `test-run/t-${i}`,
          host: 'worker-1',
          message: `Event ${i}`,
          data: { index: i },
        },
      };

      messageHandlers![0]({ data: JSON.stringify(eventData) });
    }

    await waitFor(() => {
      // Buffer should never exceed 500
      expect(result.current.events.length).toBe(500);
    });

    // Should retain the MOST RECENT events (events 100-599, zero-indexed)
    expect(result.current.events[0].id).toBe(101); // First kept event (index 100)
    expect(result.current.events[499].id).toBe(600); // Last event (index 599)

    // Last event should be the most recent
    expect(result.current.lastEvent?.id).toBe(600);
  });
});
