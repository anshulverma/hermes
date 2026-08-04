/**
 * useHashView — keeps the active tab in the URL hash.
 *
 * The tab lives in `location.hash` (e.g. `#board`) so a refresh, a bookmark, or
 * browser back/forward all land on the same tab. The hash is used rather than a
 * path because the control plane serves the SPA only at `/`, so `/board` would
 * 404 on exactly the refresh this is meant to survive.
 */

import { useCallback, useEffect, useState } from 'react';

export const VIEWS = ['overview', 'metrics', 'board', 'crew', 'findings', 'activity'] as const;

export type View = (typeof VIEWS)[number];

export const DEFAULT_VIEW: View = 'overview';

/** Read a view out of a raw hash, falling back to the default when unrecognised. */
export function parseViewHash(hash: string): View {
  const slug = hash.replace(/^#/, '').replace(/^\/+|\/+$/g, '').toLowerCase();
  return (VIEWS as readonly string[]).includes(slug) ? (slug as View) : DEFAULT_VIEW;
}

/** `[view, setView]`, synced both ways with the URL hash. */
export function useHashView(): [View, (view: View) => void] {
  const [view, setViewState] = useState<View>(() =>
    parseViewHash(typeof window === 'undefined' ? '' : window.location.hash),
  );

  // Browser back/forward (and any external hash edit) drives the view.
  useEffect(() => {
    const onHashChange = () => setViewState(parseViewHash(window.location.hash));
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  // A hash that does not name the tab on screen (stale bookmark, renamed slug,
  // `#/Crew/`) is rewritten once on mount so the URL is always truthful. Replace
  // rather than push: normalising is not a navigation.
  useEffect(() => {
    const raw = window.location.hash;
    if (raw && raw !== `#${view}`) {
      window.history.replaceState(null, '', `#${view}`);
    }
    // Mount only: later changes go through setView / hashchange.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setView = useCallback((next: View) => {
    setViewState(next);
    // Compare the raw hash so a non-canonical one (`#bogus`) is corrected, while
    // re-clicking the current tab stays a no-op (no duplicate history entry).
    if (typeof window !== 'undefined' && window.location.hash !== `#${next}`) {
      window.location.hash = next;
    }
  }, []);

  return [view, setView];
}
