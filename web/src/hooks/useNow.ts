/**
 * useNow - one shared 30 s clock, in epoch seconds.
 *
 * Every subscriber reads the same module-level value through
 * useSyncExternalStore, so every relative time on the page redraws together,
 * off one interval that runs only while something is subscribed.
 */

import { useSyncExternalStore } from 'react';

const TICK_MS = 30_000;
const listeners = new Set<() => void>();
let now = Math.floor(Date.now() / 1000);
let timer: ReturnType<typeof setInterval> | undefined;

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  if (timer === undefined) {
    now = Math.floor(Date.now() / 1000);
    timer = setInterval(() => {
      now = Math.floor(Date.now() / 1000);
      listeners.forEach((l) => l());
    }, TICK_MS);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) {
      clearInterval(timer);
      timer = undefined;
    }
  };
}

function getSnapshot(): number {
  return now;
}

export function useNow(): number {
  return useSyncExternalStore(subscribe, getSnapshot);
}
