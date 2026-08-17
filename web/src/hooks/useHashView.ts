/**
 * useHashView — keeps the active tab, and what is open on it, in the URL hash.
 *
 * The tab lives in `location.hash` (e.g. `#board`) so a refresh, a bookmark, or
 * browser back/forward all land on the same tab. The hash is used rather than a
 * path because the control plane serves the SPA only at `/`, so `/board` would
 * 404 on exactly the refresh this is meant to survive.
 *
 * A tab may carry parameters after a `?` (`#board?ticket=run-5%2F35-report`) for
 * the thing open on it. Same reasoning: a ticket you are reading should survive
 * a refresh, and be a link you can send someone. Parameters belong to the tab,
 * so switching tabs drops them.
 */

import { useCallback, useEffect, useState } from 'react';

export const VIEWS = ['overview', 'metrics', 'board', 'crew', 'outputs', 'review', 'activity'] as const;

/**
 * Slugs that used to name a view, mapped to what replaced them.
 *
 * `findings` was one page doing two jobs — reading a run's output and deciding
 * the reductions holding a ticket. Splitting it must not break a link someone
 * already has.
 */
const VIEW_ALIASES: Record<string, View> = { findings: 'outputs' };

export type View = (typeof VIEWS)[number];

export const DEFAULT_VIEW: View = 'overview';

/** Split a raw hash into its view slug and its query string. */
function splitHash(hash: string): { slug: string; query: string } {
  const bare = hash.replace(/^#/, '');
  const at = bare.indexOf('?');
  const slug = (at === -1 ? bare : bare.slice(0, at)).replace(/^\/+|\/+$/g, '').toLowerCase();
  return { slug, query: at === -1 ? '' : bare.slice(at + 1) };
}

/** Read a view out of a raw hash, falling back to the default when unrecognised. */
export function parseViewHash(hash: string): View {
  const { slug } = splitHash(hash);
  if ((VIEWS as readonly string[]).includes(slug)) return slug as View;
  return VIEW_ALIASES[slug] ?? DEFAULT_VIEW;
}

/** Read one parameter out of a raw hash, or null when it is not there. */
export function parseHashParam(hash: string, key: string): string | null {
  const { query } = splitHash(hash);
  if (!query) return null;
  const value = new URLSearchParams(query).get(key);
  return value === null || value === '' ? null : value;
}

/** Build a hash for a view plus its parameters, omitting the `?` when empty. */
export function buildHash(view: string, params: Record<string, string | null>): string {
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== '') search.set(k, v);
  }
  const query = search.toString();
  return query ? `#${view}?${query}` : `#${view}`;
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
  // rather than push: normalising is not a navigation. The query is preserved --
  // it addresses what is open on the tab, which is exactly what a stale-looking
  // hash like `#board?ticket=…` is carrying.
  useEffect(() => {
    const raw = window.location.hash;
    if (!raw) return;
    const { query } = splitHash(raw);
    const canonical = query ? `#${view}?${query}` : `#${view}`;
    if (raw !== canonical) {
      window.history.replaceState(null, '', canonical);
    }
    // Mount only: later changes go through setView / hashchange.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setView = useCallback((next: View) => {
    setViewState(next);
    // Switching tabs drops the previous tab's parameters: a ticket id means
    // nothing on the crew tab. Compare the raw hash so a non-canonical one
    // (`#bogus`) is corrected, while re-clicking the current tab stays a no-op.
    if (typeof window !== 'undefined' && window.location.hash !== `#${next}`) {
      window.location.hash = next;
    }
  }, []);

  return [view, setView];
}

/**
 * `[value, setValue]` for one hash parameter on the current tab.
 *
 * Writing goes through `location.hash`, so it lands in history: Back closes what
 * was opened, which is what a browser user expects from something that changed
 * the URL.
 */
export function useHashParam(key: string): [string | null, (value: string | null) => void] {
  const [value, setValueState] = useState<string | null>(() =>
    parseHashParam(typeof window === 'undefined' ? '' : window.location.hash, key),
  );

  useEffect(() => {
    const onHashChange = () => setValueState(parseHashParam(window.location.hash, key));
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, [key]);

  const setValue = useCallback(
    (next: string | null) => {
      setValueState(next);
      if (typeof window === 'undefined') return;
      const raw = window.location.hash;
      const { slug, query } = splitHash(raw);
      const params = new URLSearchParams(query);
      if (next === null || next === '') params.delete(key);
      else params.set(key, next);
      const view = (VIEWS as readonly string[]).includes(slug)
        ? slug
        : (VIEW_ALIASES[slug] ?? DEFAULT_VIEW);
      const target = buildHash(view, Object.fromEntries(params));
      if (raw !== target) window.location.hash = target.slice(1);
    },
    [key],
  );

  return [value, setValue];
}
