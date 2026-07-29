/**
 * useEventStream - WebSocket hook for live event updates.
 * Connects to WS /api/ws, receives events, auto-reconnects on close.
 * Phase D1b: Token in query string, 4401 auth error handling.
 */

import { useState, useEffect, useRef } from 'react';
import type { Event } from '../api/client';
import { getToken } from '../api/auth';

const MAX_EVENTS_BUFFER = 500;

type EventStreamState = {
  connected: boolean;
  events: Event[];
  lastEvent: Event | null;
  authError?: boolean;
};

export function useEventStream(since?: number): EventStreamState {
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<Event[]>([]);
  const [lastEvent, setLastEvent] = useState<Event | null>(null);
  const [authError, setAuthError] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

  useEffect(() => {
    function connect() {
      // Derive WebSocket URL from current origin (http:// -> ws://, https:// -> wss://)
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;

      // Build query params (token + since)
      const params = new URLSearchParams();
      const token = getToken();
      if (token) {
        params.append('token', token);
      }
      if (since !== undefined) {
        params.append('since', since.toString());
      }

      const queryString = params.toString();
      const url = `${protocol}//${host}/api/ws${queryString ? '?' + queryString : ''}`;

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
            setEvents((prev) => [...prev, newEvent].slice(-MAX_EVENTS_BUFFER));
            setLastEvent(newEvent);
          }
          // Ignore hello messages (just acknowledges connection)
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err);
        }
      });

      ws.addEventListener('close', (event) => {
        setConnected(false);
        wsRef.current = null;

        // Check for auth failure (code 4401)
        if (event.code === 4401) {
          // Auth error - do NOT reconnect
          setAuthError(true);
          console.error('WebSocket auth error (4401): token invalid or missing');
          return;
        }

        // Transient close - schedule reconnect after a small backoff (3s)
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

  return { connected, events, lastEvent, authError };
}
