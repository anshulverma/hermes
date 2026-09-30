/**
 * useRoute — the page on screen, held in the URL hash.
 *
 * The control plane serves the SPA only at `/`, so the route lives in the hash
 * (`#/runs/<id>/<tab>`, `#/needs-you`, `#/activity`, `#/crew`): a refresh, a
 * bookmark, Back and Forward all land on the same page, and every page is a link
 * worth sending.
 *
 * One module-level store backs every `useRoute()`: `navigate`, `replace` and
 * `hashchange` all notify every subscriber, so App and TicketBoard never
 * disagree about the route. The store derives the route from
 * `location.hash` itself, so it cannot drift from the address bar.
 */

import { useSyncExternalStore } from 'react';

export const RUN_TABS = ['summary', 'tickets', 'outputs', 'metrics'] as const;

export type RunTab = (typeof RUN_TABS)[number];

export type Route =
  | { page: 'run'; runId: string | null; tab: RunTab; ticket: string | null }
  | { page: 'needs-you'; run: string | null }
  | { page: 'activity'; run: string | null; kind: string | null }
  | { page: 'crew' };

/** The route of an empty or unrecognised hash: the default run's summary, once it is known. */
const PENDING: Route = { page: 'run', runId: null, tab: 'summary', ticket: null };

/**
 * Pre-route hashes (`#board?run=X&ticket=T`) and the page each became. Links
 * people already have must keep working.
 */
const LEGACY_RUN_TABS: Record<string, RunTab> = {
  overview: 'summary',
  playbook: 'summary',
  board: 'tickets',
  outputs: 'outputs',
  findings: 'outputs',
  metrics: 'metrics',
};

function query(params: Record<string, string | null>): string {
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) search.set(k, v);
  const s = search.toString();
  return s ? `?${s}` : '';
}

/** The hash for a route. Only `#/runs` may leave the run to the default. */
export function buildRoute(route: Route): string {
  switch (route.page) {
    case 'run':
      if (route.runId === null) {
        if (route.tab === 'summary' && route.ticket === null) return '#/runs';
        throw new Error(`buildRoute: a ${route.tab} route needs a run id`);
      }
      return (
        `#/runs/${encodeURIComponent(route.runId)}/${route.tab}` +
        query({ ticket: route.tab === 'tickets' ? route.ticket : null })
      );
    case 'needs-you':
      return `#/needs-you${query({ run: route.run })}`;
    case 'activity':
      return `#/activity${query({ run: route.run, kind: route.kind })}`;
    case 'crew':
      return '#/crew';
  }
}

/** A run page, with the ticket kept only on Tickets and only when it is this run's. */
function runRoute(runId: string | null, tab: RunTab, ticket: string | null): Route {
  const own = runId !== null && tab === 'tickets' && ticket?.startsWith(`${runId}/`);
  return { page: 'run', runId, tab, ticket: own ? ticket : null };
}

function readRoute(path: string, params: URLSearchParams): Route | null {
  const param = (k: string) => params.get(k) || null;
  if (!path.startsWith('/')) {
    // A legacy hash: `#<view>?run=X&ticket=T`.
    const slug = path.toLowerCase();
    const tab = LEGACY_RUN_TABS[slug];
    if (tab) {
      // Ticket ids are `<run_id>/t-<n>`, so a ticket names its run.
      const ticket = param('ticket');
      const ticketRun = /^([^/]+)\//.exec(ticket ?? '')?.[1] ?? null;
      return runRoute(param('run') ?? ticketRun, tab, ticket);
    }
    if (slug === 'review' || slug === 'needs-you') return { page: 'needs-you', run: param('run') };
    if (slug === 'crew') return { page: 'crew' };
    if (slug === 'activity') return { page: 'activity', run: null, kind: null };
    return null;
  }
  const [page, id, ...rest] = path.slice(1).split('/');
  switch (page.toLowerCase()) {
    case 'runs': {
      if (id === undefined) return PENDING;
      if (id === '') return null;
      const tab = rest.join('/').toLowerCase();
      return runRoute(
        decodeURIComponent(id),
        (RUN_TABS as readonly string[]).includes(tab) ? (tab as RunTab) : 'summary',
        param('ticket'),
      );
    }
    case 'needs-you':
      return id === undefined ? { page: 'needs-you', run: param('run') } : null;
    case 'activity':
      return id === undefined ? { page: 'activity', run: param('run'), kind: param('kind') } : null;
    case 'crew':
      return id === undefined ? { page: 'crew' } : null;
    default:
      return null;
  }
}

/**
 * Read a hash. `canonical` is the hash to `replaceState` to, or null when the
 * hash is already canonical or the route still needs the default run
 * (`runId: null`, keeping the tab it asked for).
 */
export function parseRoute(hash: string): { route: Route; canonical: string | null } {
  const bare = hash.replace(/^#/, '');
  const at = bare.indexOf('?');
  const path = (at === -1 ? bare : bare.slice(0, at)).replace(/\/+$/, '');
  let route: Route | null;
  try {
    route = readRoute(path, new URLSearchParams(at === -1 ? '' : bare.slice(at + 1)));
  } catch (e) {
    // decodeURIComponent on a malformed `%` sequence: the hash names nothing.
    if (!(e instanceof URIError)) throw e;
    route = null;
  }
  if (route === null || (route.page === 'run' && route.runId === null)) {
    return { route: route ?? PENDING, canonical: null };
  }
  const canonical = buildRoute(route);
  return { route, canonical: canonical === `#${bare}` ? null : canonical };
}

const listeners = new Set<() => void>();
let snapshotHash: string | null = null;
let snapshot: Route = PENDING;

function getSnapshot(): Route {
  const hash = window.location.hash;
  if (hash !== snapshotHash) {
    snapshotHash = hash;
    snapshot = parseRoute(hash).route;
  }
  return snapshot;
}

function notify() {
  for (const listener of listeners) listener();
}

/** Legacy conversion and normalisation: never a history entry. */
function normalise() {
  const { canonical } = parseRoute(window.location.hash);
  if (canonical !== null) window.history.replaceState(null, '', canonical);
}

function onHashChange() {
  normalise();
  notify();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  if (listeners.size === 1) {
    window.addEventListener('hashchange', onHashChange);
    normalise();
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) window.removeEventListener('hashchange', onHashChange);
  };
}

/** Go to a route: a history entry, so Back returns here. */
function navigate(route: Route) {
  const hash = buildRoute(route);
  if (window.location.hash !== hash) window.location.hash = hash;
  notify();
}

/** Show a route without a history entry. `replaceState` fires no hashchange, so notify here. */
function replace(route: Route) {
  window.history.replaceState(null, '', buildRoute(route));
  notify();
}

export function useRoute(): {
  route: Route;
  navigate: (r: Route) => void;
  replace: (r: Route) => void;
} {
  return { route: useSyncExternalStore(subscribe, getSnapshot), navigate, replace };
}
