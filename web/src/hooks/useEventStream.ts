/**
 * useEventStream - WebSocket hook for live event updates.
 * Connects to WS /api/ws, receives events, auto-reconnects on close.
 */

import { useState, useEffect, useRef } from 'react';
import type { Event } from '../api/client';

type EventStreamState = {
  connected: boolean;
  events: Event[];
  lastEvent: Event | null;
};

export function useEventStream(since?: number): EventStreamState {
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<Event[]>([]);
  const [lastEvent, setLastEvent] = useState<Event | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

  useEffect(() => {
    function connect() {
      // Derive WebSocket URL from current origin (http:// -> ws://, https:// -> wss://)
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      const sinceParam = since !== undefined ? `?since=${since}` : '';
      const url = `${protocol}//${host}/api/ws${sinceParam}`;

      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.addEventListener('open', () => {
        setConnected(true);
      });

      ws.addEventListener('message', (event) => {
        try {
          const msg = JSON.parse(event.data);

          if (msg.type === 'event' && msg.event) {
            const newEvent = msg.event as Event;
            setEvents((prev) => [...prev, newEvent]);
            setLastEvent(newEvent);
          }
          // Ignore hello messages (just acknowledges connection)
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err);
        }
      });

      ws.addEventListener('close', () => {
        setConnected(false);
        wsRef.current = null;

        // Schedule reconnect after a small backoff (3s)
        reconnectTimeoutRef.current = window.setTimeout(() => {
          connect();
        }, 3000);
      });

      ws.addEventListener('error', (err) => {
        console.error('WebSocket error:', err);
      });
    }

    connect();

    // Cleanup on unmount
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [since]);

  return { connected, events, lastEvent };
}
