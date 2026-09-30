import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { buildRoute, parseRoute, useRoute } from './useRoute';
import type { Route } from './useRoute';

function setHash(h: string) {
  window.location.hash = h;
}

function hashChange(h: string) {
  act(() => {
    setHash(h);
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  });
}

const PENDING: Route = { page: 'run', runId: null, tab: 'summary', ticket: null };

// Every pre-route hash, and where it lands. A legacy hash with no run (and no
// ticket to take one from) keeps its tab and waits for the default run.
const LEGACY: [string, Route, string | null][] = [
  ['#overview?run=run-14', { page: 'run', runId: 'run-14', tab: 'summary', ticket: null }, '#/runs/run-14/summary'],
  [
    '#board?run=run-14&ticket=run-14%2Ft-3',
    { page: 'run', runId: 'run-14', tab: 'tickets', ticket: 'run-14/t-3' },
    '#/runs/run-14/tickets?ticket=run-14%2Ft-3',
  ],
  ['#board?run=run-14', { page: 'run', runId: 'run-14', tab: 'tickets', ticket: null }, '#/runs/run-14/tickets'],
  // The old run picker kept a ticket from the previous run: run wins, the ticket goes.
  ['#board?run=run-14&ticket=run-9%2Ft-2', { page: 'run', runId: 'run-14', tab: 'tickets', ticket: null }, '#/runs/run-14/tickets'],
  ['#outputs?run=run-14', { page: 'run', runId: 'run-14', tab: 'outputs', ticket: null }, '#/runs/run-14/outputs'],
  ['#findings?run=run-14', { page: 'run', runId: 'run-14', tab: 'outputs', ticket: null }, '#/runs/run-14/outputs'],
  ['#metrics?run=run-14', { page: 'run', runId: 'run-14', tab: 'metrics', ticket: null }, '#/runs/run-14/metrics'],
  ['#playbook?run=run-14', { page: 'run', runId: 'run-14', tab: 'summary', ticket: null }, '#/runs/run-14/summary'],
  [
    '#overview?run=run-14&ticket=run-14%2Ft-3',
    { page: 'run', runId: 'run-14', tab: 'summary', ticket: null },
    '#/runs/run-14/summary',
  ],
  [
    '#board?ticket=run-9%2Ft-2',
    { page: 'run', runId: 'run-9', tab: 'tickets', ticket: 'run-9/t-2' },
    '#/runs/run-9/tickets?ticket=run-9%2Ft-2',
  ],
  ['#review?run=run-14', { page: 'needs-you', run: 'run-14' }, '#/needs-you?run=run-14'],
  ['#needs-you?run=run-14', { page: 'needs-you', run: 'run-14' }, '#/needs-you?run=run-14'],
  ['#review', { page: 'needs-you', run: null }, '#/needs-you'],
  ['#needs-you', { page: 'needs-you', run: null }, '#/needs-you'],
  ['#crew', { page: 'crew' }, '#/crew'],
  ['#crew?run=run-14', { page: 'crew' }, '#/crew'],
  ['#activity', { page: 'activity', run: null, kind: null }, '#/activity'],
  ['#activity?run=run-14', { page: 'activity', run: null, kind: null }, '#/activity'],
  ['#Board?run=run-14', { page: 'run', runId: 'run-14', tab: 'tickets', ticket: null }, '#/runs/run-14/tickets'],
  ['#overview', PENDING, null],
  ['#playbook', PENDING, null],
  ['#board', { page: 'run', runId: null, tab: 'tickets', ticket: null }, null],
  ['#outputs', { page: 'run', runId: null, tab: 'outputs', ticket: null }, null],
  ['#findings', { page: 'run', runId: null, tab: 'outputs', ticket: null }, null],
  ['#metrics', { page: 'run', runId: null, tab: 'metrics', ticket: null }, null],
];

describe('parseRoute', () => {
  it('converts every legacy hash', () => {
    for (const [hash, route, canonical] of LEGACY) {
      expect(parseRoute(hash), hash).toEqual({ route, canonical });
    }
  });

  it('reads every canonical hash as canonical and builds it back unchanged', () => {
    for (const hash of [
      '#/runs/run-1/summary',
      '#/runs/run-1/tickets',
      '#/runs/run-1/tickets?ticket=run-1%2Ft-3',
      '#/runs/run-1/outputs',
      '#/runs/run-1/metrics',
      '#/runs/Run%20A%2FB/summary',
      '#/runs',
      '#/needs-you',
      '#/needs-you?run=run-1',
      '#/activity',
      '#/activity?run=run-1',
      '#/activity?kind=needs_human',
      '#/activity?run=run-1&kind=needs_human',
      '#/crew',
    ]) {
      const { route, canonical } = parseRoute(hash);
      expect(canonical, hash).toBeNull();
      expect(buildRoute(route), hash).toBe(hash);
    }
  });

  it('round-trips every route with a run, #/runs and the three cross-run pages', () => {
    const routes: Route[] = [
      { page: 'run', runId: 'run-1', tab: 'summary', ticket: null },
      { page: 'run', runId: 'Run A/B?#%', tab: 'metrics', ticket: null },
      { page: 'run', runId: 'run-1', tab: 'outputs', ticket: null },
      { page: 'run', runId: 'run-1', tab: 'tickets', ticket: null },
      { page: 'run', runId: 'run-1', tab: 'tickets', ticket: 'run-1/t-12' },
      PENDING,
      { page: 'needs-you', run: null },
      { page: 'needs-you', run: 'run 1' },
      { page: 'activity', run: 'run-1', kind: 'run_done' },
      { page: 'activity', run: null, kind: null },
      { page: 'crew' },
    ];
    for (const route of routes) {
      expect(parseRoute(buildRoute(route)).route).toEqual(route);
    }
  });

  it('encodes the run id and never case-folds it, while the tab matches in any case', () => {
    expect(buildRoute({ page: 'run', runId: 'a b/c', tab: 'summary', ticket: null })).toBe(
      '#/runs/a%20b%2Fc/summary',
    );
    expect(parseRoute('#/runs/Run-ABC/Metrics')).toEqual({
      route: { page: 'run', runId: 'Run-ABC', tab: 'metrics', ticket: null },
      canonical: '#/runs/Run-ABC/metrics',
    });
  });

  it('matches the page segments in any case', () => {
    expect(parseRoute('#/RUNS/run-1/Tickets').canonical).toBe('#/runs/run-1/tickets');
    expect(parseRoute('#/Needs-You?run=run-1').canonical).toBe('#/needs-you?run=run-1');
    expect(parseRoute('#/ACTIVITY').canonical).toBe('#/activity');
    expect(parseRoute('#/Crew').canonical).toBe('#/crew');
  });

  it('normalises a trailing slash, a bare run, an unknown tab and stray params', () => {
    expect(parseRoute('#/runs/run-1/summary/').canonical).toBe('#/runs/run-1/summary');
    expect(parseRoute('#/crew/').canonical).toBe('#/crew');
    expect(parseRoute('#/runs/run-1').canonical).toBe('#/runs/run-1/summary');
    expect(parseRoute('#/runs/run-1/bogus').canonical).toBe('#/runs/run-1/summary');
    expect(parseRoute('#/runs/run-1/summary?ticket=run-1%2Ft-3').canonical).toBe('#/runs/run-1/summary');
    expect(parseRoute('#/crew?run=run-1').canonical).toBe('#/crew');
    expect(parseRoute('#/needs-you?kind=run_done').canonical).toBe('#/needs-you');
  });

  it('leaves an empty, bare or unrecognised hash to the default run', () => {
    for (const hash of ['', '#', '#/', '#/runs', '#/runs/', '#bogus', '#/bogus', '#/crew/extra', '#/needs-you/extra', '#/activity/extra', '#/runs//summary']) {
      expect(parseRoute(hash), hash).toEqual({ route: PENDING, canonical: null });
    }
  });

  it('treats a malformed % sequence in the run id as an unrecognised route', () => {
    expect(parseRoute('#/runs/run-%E0%A4%A/summary')).toEqual({ route: PENDING, canonical: null });
    expect(parseRoute('#/runs/%/tickets?ticket=x%2Ft-1')).toEqual({ route: PENDING, canonical: null });
  });

  it('reads an empty query value as null', () => {
    expect(parseRoute('#/needs-you?run=')).toEqual({
      route: { page: 'needs-you', run: null },
      canonical: '#/needs-you',
    });
    expect(parseRoute('#/activity?run=&kind=')).toEqual({
      route: { page: 'activity', run: null, kind: null },
      canonical: '#/activity',
    });
    expect(parseRoute('#/runs/run-1/tickets?ticket=')).toEqual({
      route: { page: 'run', runId: 'run-1', tab: 'tickets', ticket: null },
      canonical: '#/runs/run-1/tickets',
    });
  });

  it("drops a ticket that is not the run's own", () => {
    expect(parseRoute('#/runs/run-1/tickets?ticket=run-2%2Ft-3')).toEqual({
      route: { page: 'run', runId: 'run-1', tab: 'tickets', ticket: null },
      canonical: '#/runs/run-1/tickets',
    });
    // A prefix of the id is not the id.
    expect(parseRoute('#/runs/run-1/tickets?ticket=run-10%2Ft-3').route).toEqual({
      page: 'run',
      runId: 'run-1',
      tab: 'tickets',
      ticket: null,
    });
  });
});

describe('buildRoute', () => {
  it('builds #/runs for the default-run summary and throws for any other route with no run', () => {
    expect(buildRoute(PENDING)).toBe('#/runs');
    expect(() => buildRoute({ page: 'run', runId: null, tab: 'metrics', ticket: null })).toThrow();
    expect(() => buildRoute({ page: 'run', runId: null, tab: 'summary', ticket: 'run-1/t-1' })).toThrow();
  });
});

describe('useRoute', () => {
  beforeEach(() => setHash(''));
  afterEach(() => setHash(''));

  it('converts every legacy hash on load, with replaceState', () => {
    for (const [hash, route, canonical] of LEGACY) {
      setHash(hash);
      const entries = window.history.length;
      const { result, unmount } = renderHook(() => useRoute());
      expect(result.current.route, hash).toEqual(route);
      expect(window.location.hash, hash).toBe(canonical ?? hash);
      expect(window.history.length, hash).toBe(entries);
      unmount();
    }
  });

  it('converts every legacy hash opened mid-session, on hashchange', () => {
    const { result } = renderHook(() => useRoute());
    for (const [hash, route, canonical] of LEGACY) {
      const entries = window.history.length;
      hashChange(hash);
      expect(result.current.route, hash).toEqual(route);
      expect(window.location.hash, hash).toBe(canonical ?? hash);
      // One entry for the hash the reader set; the conversion replaces it.
      expect(window.history.length, hash).toBe(entries + 1);
    }
  });

  it('normalises an untidy hash on load and leaves a clean one alone', () => {
    setHash('#/Runs/run-1/Metrics/');
    const { result, unmount } = renderHook(() => useRoute());
    expect(result.current.route).toEqual({ page: 'run', runId: 'run-1', tab: 'metrics', ticket: null });
    expect(window.location.hash).toBe('#/runs/run-1/metrics');
    unmount();

    setHash('');
    renderHook(() => useRoute());
    expect(window.location.hash).toBe('');
  });

  it('navigate pushes one history entry; a second navigate to the same route pushes none', () => {
    const { result } = renderHook(() => useRoute());
    const entries = window.history.length;
    act(() => result.current.navigate({ page: 'run', runId: 'run-1', tab: 'outputs', ticket: null }));
    expect(window.location.hash).toBe('#/runs/run-1/outputs');
    expect(result.current.route).toEqual({ page: 'run', runId: 'run-1', tab: 'outputs', ticket: null });
    expect(window.history.length).toBe(entries + 1);
    act(() => result.current.navigate({ page: 'run', runId: 'run-1', tab: 'outputs', ticket: null }));
    expect(window.history.length).toBe(entries + 1);
  });

  it('replace updates the route without a history entry', () => {
    setHash('#metrics');
    const { result } = renderHook(() => useRoute());
    const entries = window.history.length;
    act(() => result.current.replace({ page: 'run', runId: 'run-1', tab: 'metrics', ticket: null }));
    expect(window.location.hash).toBe('#/runs/run-1/metrics');
    expect(result.current.route).toEqual({ page: 'run', runId: 'run-1', tab: 'metrics', ticket: null });
    expect(window.history.length).toBe(entries);
  });

  it('switching tabs keeps the run and drops the ticket', () => {
    // d978a44: dropping the run sent the console to the newest run on every tab click.
    setHash('#/runs/run-14/tickets?ticket=run-14%2F3-report');
    const { result } = renderHook(() => useRoute());
    const { route } = result.current;
    if (route.page !== 'run') throw new Error('expected a run route');
    act(() => result.current.navigate({ ...route, tab: 'outputs', ticket: null }));
    expect(window.location.hash).toBe('#/runs/run-14/outputs');
  });

  it('shows every hook instance the same route after navigate, replace and hashchange', () => {
    const a = renderHook(() => useRoute());
    const b = renderHook(() => useRoute());

    act(() => a.result.current.navigate({ page: 'crew' }));
    expect(b.result.current.route).toEqual({ page: 'crew' });

    act(() => b.result.current.replace({ page: 'needs-you', run: 'run-2' }));
    expect(a.result.current.route).toEqual({ page: 'needs-you', run: 'run-2' });

    hashChange('#/activity?kind=run_done');
    expect(a.result.current.route).toEqual({ page: 'activity', run: null, kind: 'run_done' });
    expect(b.result.current.route).toEqual({ page: 'activity', run: null, kind: 'run_done' });
  });
});
