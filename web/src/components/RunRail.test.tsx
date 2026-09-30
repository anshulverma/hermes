/**
 * Tests for the runs rail: railGroups and defaultRunId (pure), useRailState's
 * persistence, and RunRail's rendering, keyboard and accessibility.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { useRef } from 'react';
import { render, renderHook, screen, within, fireEvent, act, waitFor } from '@testing-library/react';
import RunRail, { railGroups, defaultRunId, useRailState, RunStateIcon } from './RunRail';
import type { Run } from '../api/client';
import type { RunTab } from '../hooks/useRoute';
import { fmtTime } from '../util/time';

// One fixed clock, so every age reads the same on every machine.
vi.mock('../hooks/useNow', () => ({ useNow: () => 1_800_000_000 }));
const NOW = 1_800_000_000;
const HIDDEN_KEY = 'hermes.rail.hiddenPlaybooks';
const COLLAPSED_KEY = 'hermes.rail.collapsed';
const NONE: ReadonlySet<string> = new Set();

function run(id: string, over: Partial<Run> = {}): Run {
  return {
    id,
    playbook: 'alpha',
    site: 'local',
    state: 'running',
    phase: 'work',
    base_ref: 'main',
    created_at: NOW - 180,
    updated_at: NOW - 60,
    tickets: {},
    has_view: false,
    awaiting: 0,
    subject: null,
    ...over,
  };
}

/** n done runs, f-01 the most recently ended. */
function finishedRuns(n: number): Run[] {
  return Array.from({ length: n }, (_, i) =>
    run(`f-${String(i + 1).padStart(2, '0')}`, { state: 'done', updated_at: NOW - (i + 1) * 60 }),
  );
}

const ids = (runs: Run[]) => runs.map((r) => r.id);

function setWidth(width: number) {
  Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: width });
}

beforeEach(() => {
  window.localStorage.clear();
  setWidth(1024);
});

afterEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState(null, '', '/');
});

describe('railGroups', () => {
  it('puts every run in exactly one group, and Needs you wins over the state', () => {
    const g = railGroups(
      [
        run('a', { state: 'running' }),
        run('b', { state: 'paused' }),
        run('c', { state: 'done' }),
        run('d', { state: 'failed', awaiting: 1 }),
        run('e', { state: 'running', awaiting: 2 }),
        run('f', { state: 'stopped' }),
      ],
      NONE,
      '',
      false,
      null,
    );

    expect(ids(g.needsYou).sort()).toEqual(['d', 'e']);
    expect(ids(g.active).sort()).toEqual(['a', 'b']);
    expect(ids(g.finished).sort()).toEqual(['c', 'f']);
  });

  it('sorts Needs you and Active by created_at, newest first, ties by id descending', () => {
    const g = railGroups(
      [
        run('a1', { created_at: 100 }),
        run('a2', { created_at: 300 }),
        run('a3', { created_at: 300 }),
        run('n1', { awaiting: 1, created_at: 100, updated_at: 900 }),
        run('n2', { awaiting: 1, created_at: 200, updated_at: 100 }),
        run('n3', { awaiting: 1, created_at: 200, updated_at: 500 }),
      ],
      NONE,
      '',
      false,
      null,
    );

    expect(ids(g.active)).toEqual(['a3', 'a2', 'a1']);
    expect(ids(g.needsYou)).toEqual(['n3', 'n2', 'n1']);
  });

  it('sorts Finished by updated_at, newest first, ties by id descending', () => {
    const g = railGroups(
      [
        run('x', { state: 'done', created_at: 900, updated_at: 100 }),
        run('y', { state: 'failed', created_at: 100, updated_at: 500 }),
        run('z1', { state: 'stopped', created_at: 50, updated_at: 300 }),
        run('z2', { state: 'done', created_at: 60, updated_at: 300 }),
      ],
      NONE,
      '',
      false,
      null,
    );

    expect(ids(g.finished)).toEqual(['y', 'z2', 'z1', 'x']);
  });

  it('shows the newest 10 finished runs and counts the rest', () => {
    const g = railGroups(finishedRuns(13), NONE, '', false, null);

    expect(ids(g.finished)).toEqual(ids(finishedRuns(10)));
    expect(g.moreFinished).toBe(3);
  });

  it('shows every finished run once "show N more" is chosen', () => {
    const g = railGroups(finishedRuns(13), NONE, '', true, null);

    expect(g.finished).toHaveLength(13);
    expect(g.moreFinished).toBe(0);
  });

  it('lifts the cap while the filter box has text', () => {
    const g = railGroups(finishedRuns(13), NONE, 'F-', false, null);

    expect(g.finished).toHaveLength(13);
    expect(g.moreFinished).toBe(0);
  });

  it('matches the filter text against id, playbook, phase and subject, ignoring case', () => {
    const runs = [
      run('r1', { playbook: 'Alpha' }),
      run('r2', { playbook: 'beta', phase: 'Review' }),
      run('r3', { playbook: 'beta', subject: 'Fix the FLAKY test' }),
      run('r4', { playbook: 'beta', phase: null, subject: null }),
    ];
    const shown = (text: string) => ids(railGroups(runs, NONE, text, false, null).active).sort();

    expect(shown('alp')).toEqual(['r1']);
    expect(shown('review')).toEqual(['r2']);
    expect(shown('flaky')).toEqual(['r3']);
    expect(shown('R4')).toEqual(['r4']);
    expect(shown('BETA')).toEqual(['r2', 'r3', 'r4']);
  });

  it('shows a selected run beyond the cap after the newest 10 and leaves it out of the count', () => {
    const beyond = railGroups(finishedRuns(30), NONE, '', false, 'f-30');
    const within10 = railGroups(finishedRuns(30), NONE, '', false, 'f-05');

    expect(ids(beyond.finished)).toEqual([...ids(finishedRuns(10)), 'f-30']);
    expect(beyond.moreFinished).toBe(19);
    expect(ids(within10.finished)).toEqual(ids(finishedRuns(10)));
    expect(within10.moreFinished).toBe(20);
  });

  it('counts the runs the chips or the filter text hide and their decisions, not the rows behind the cap', () => {
    const runs = [
      ...finishedRuns(12),
      run('b1', { playbook: 'beta', awaiting: 2 }),
      run('b2', { playbook: 'beta', state: 'done' }),
      run('c1', { playbook: 'gamma', awaiting: 1, subject: 'other' }),
    ];

    const byChip = railGroups(runs, new Set(['beta']), '', false, null);
    expect(byChip.hiddenCount).toBe(2);
    expect(byChip.hiddenAwaiting).toBe(2);
    expect(byChip.moreFinished).toBe(2);

    // 'f-0' matches f-01 to f-09; f-10 to f-12 and c1 fall to the text, b1 and b2 to the chip.
    const byText = railGroups(runs, new Set(['beta']), 'f-0', false, null);
    expect(byText.hiddenCount).toBe(6);
    expect(byText.hiddenAwaiting).toBe(3);
  });

  it('leaves every group empty when nothing passes the filters', () => {
    const g = railGroups([run('a'), run('b', { awaiting: 1 }), run('c', { state: 'done' })], NONE, 'zzz', false, null);

    expect(g).toEqual({ needsYou: [], active: [], finished: [], moreFinished: 0, hiddenCount: 3, hiddenAwaiting: 1 });
  });
});

describe('defaultRunId', () => {
  it('picks the first run in the Needs you group', () => {
    const runs = [
      run('a', { created_at: 900 }),
      run('n1', { awaiting: 1, created_at: 100 }),
      run('n2', { awaiting: 1, created_at: 200 }),
    ];

    expect(defaultRunId(runs, NONE)).toBe('n2');
  });

  it('else the first Active run', () => {
    const runs = [run('d', { state: 'done', created_at: 900 }), run('a1', { created_at: 100 }), run('a2', { created_at: 200 })];

    expect(defaultRunId(runs, NONE)).toBe('a2');
  });

  it('else the newest run by created_at, ties by id descending', () => {
    const runs = [
      run('d1', { state: 'done', created_at: 300, updated_at: 1 }),
      run('d2', { state: 'failed', created_at: 300, updated_at: 1 }),
      run('d3', { state: 'stopped', created_at: 100, updated_at: 900 }),
    ];

    expect(defaultRunId(runs, NONE)).toBe('d2');
  });

  it('skips runs whose chip is off, uses every run when the chips hide them all, and is null for none', () => {
    const runs = [run('a', { playbook: 'alpha', awaiting: 1 }), run('b', { playbook: 'beta' })];

    expect(defaultRunId(runs, new Set(['alpha']))).toBe('b');
    expect(defaultRunId(runs, new Set(['alpha', 'beta']))).toBe('a');
    expect(defaultRunId([], NONE)).toBeNull();
  });
});

describe('useRailState', () => {
  it('reads the hidden playbooks from a JSON array, nothing hidden by default', () => {
    expect([...renderHook(() => useRailState()).result.current.hidden]).toEqual([]);

    window.localStorage.setItem(HIDDEN_KEY, '["beta"]');
    expect([...renderHook(() => useRailState()).result.current.hidden]).toEqual(['beta']);
  });

  it('hides nothing when the stored value is not a JSON array of strings', () => {
    for (const stored of ['nope', '{"beta":true}', '[1,"beta"]', 'null']) {
      window.localStorage.setItem(HIDDEN_KEY, stored);
      expect([...renderHook(() => useRailState()).result.current.hidden]).toEqual([]);
    }
  });

  it('stores the hidden playbooks as a JSON array', () => {
    const { result } = renderHook(() => useRailState());

    act(() => result.current.setHidden(new Set(['beta', 'gamma'])));

    expect([...result.current.hidden]).toEqual(['beta', 'gamma']);
    expect(window.localStorage.getItem(HIDDEN_KEY)).toBe('["beta","gamma"]');
  });

  it("stays collapsed on '1' at a narrow and a wide window", () => {
    window.localStorage.setItem(COLLAPSED_KEY, '1');
    setWidth(800);
    expect(renderHook(() => useRailState()).result.current.collapsed).toBe(true);
    setWidth(1440);
    expect(renderHook(() => useRailState()).result.current.collapsed).toBe(true);
  });

  it("stays expanded on '0' at a narrow and a wide window", () => {
    window.localStorage.setItem(COLLAPSED_KEY, '0');
    setWidth(800);
    expect(renderHook(() => useRailState()).result.current.collapsed).toBe(false);
    setWidth(1440);
    expect(renderHook(() => useRailState()).result.current.collapsed).toBe(false);
  });

  it('follows the window when the value is absent or anything else: collapsed below 1024px', () => {
    for (const stored of [null, 'yes']) {
      if (stored == null) window.localStorage.removeItem(COLLAPSED_KEY);
      else window.localStorage.setItem(COLLAPSED_KEY, stored);
      setWidth(1023);
      expect(renderHook(() => useRailState()).result.current.collapsed).toBe(true);
      setWidth(1024);
      expect(renderHook(() => useRailState()).result.current.collapsed).toBe(false);
    }
  });

  it('reads the window width once, at mount', () => {
    const { result, rerender } = renderHook(() => useRailState());

    setWidth(600);
    rerender();

    expect(result.current.collapsed).toBe(false);
  });

  it("writes '1' on collapse and '0' on expand", () => {
    const { result } = renderHook(() => useRailState());

    act(() => result.current.setCollapsed(true));
    expect(result.current.collapsed).toBe(true);
    expect(window.localStorage.getItem(COLLAPSED_KEY)).toBe('1');

    act(() => result.current.setCollapsed(false));
    expect(result.current.collapsed).toBe(false);
    expect(window.localStorage.getItem(COLLAPSED_KEY)).toBe('0');
  });

  it('keeps both choices in memory when localStorage throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('denied');
    });
    const { result } = renderHook(() => useRailState());
    expect(result.current.collapsed).toBe(false);
    expect([...result.current.hidden]).toEqual([]);

    act(() => {
      result.current.setHidden(new Set(['beta']));
      result.current.setCollapsed(true);
    });

    expect([...result.current.hidden]).toEqual(['beta']);
    expect(result.current.collapsed).toBe(true);
  });

  it('does not store the filter text or the show-more choice', () => {
    const { result } = renderHook(() => useRailState());

    act(() => {
      result.current.setFilter('abc');
      result.current.setShowAllFinished(true);
    });

    expect(result.current.filter).toBe('abc');
    expect(result.current.showAllFinished).toBe(true);
    expect(window.localStorage.length).toBe(0);
  });
});

type HarnessProps = {
  runs: Run[];
  selectedRunId?: string | null;
  tab?: RunTab;
  error?: Error | null;
  onRetry?: () => void;
};

/** RunRail as App will mount it: the rail state, groups and playbooks computed here. */
function Harness({ runs, selectedRunId = null, tab = 'summary', error = null, onRetry = () => {} }: HarnessProps) {
  const rail = useRailState();
  const filterRef = useRef<HTMLInputElement>(null);
  const groups = railGroups(runs, rail.hidden, rail.filter, rail.showAllFinished, selectedRunId);
  const playbooks = [...new Set(runs.map((r) => r.playbook))].sort();
  return (
    <>
      <RunRail
        groups={groups}
        playbooks={playbooks}
        rail={rail}
        error={error}
        onRetry={onRetry}
        selectedRunId={selectedRunId}
        tab={tab}
        filterRef={filterRef}
      />
      <main>
        <h1 tabIndex={-1}>pane title</h1>
      </main>
    </>
  );
}

const row = (id: string) => screen.getByRole('link', { name: new RegExp(`^${id},`) });
const filterBox = () => screen.getByRole('searchbox', { name: 'Filter runs' });

describe('RunRail rows', () => {
  it('is a nav named Runs with a heading and a list per group, each row a link in a list item', () => {
    render(<Harness runs={[run('n', { awaiting: 1 }), run('a'), run('d', { state: 'done' })]} />);
    const nav = screen.getByRole('navigation', { name: 'Runs' });

    expect(within(nav).getAllByRole('heading').map((h) => h.textContent)).toEqual(['Needs you', 'Active', 'Finished']);
    expect(within(nav).getAllByRole('list')).toHaveLength(3);
    const links = within(nav).getAllByRole('link');
    expect(links.map((l) => l.getAttribute('href'))).toEqual(['#/runs/n/summary', '#/runs/a/summary', '#/runs/d/summary']);
    for (const link of links) expect(link.parentElement?.tagName).toBe('LI');
  });

  it('links each row to the run tab in use, with the id encoded', () => {
    render(<Harness runs={[run('run 1')]} tab="metrics" />);

    expect(row('run 1')).toHaveAttribute('href', '#/runs/run%201/metrics');
  });

  it('omits a group with no rows, heading included', () => {
    render(<Harness runs={[run('d', { state: 'done' })]} />);

    expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual(['Finished']);
  });

  it('names each row by id, playbook and state, plus the decisions waiting', () => {
    render(
      <Harness
        runs={[run('r1', { state: 'paused' }), run('r2', { playbook: 'beta', state: 'failed', awaiting: 2 })]}
      />,
    );

    expect(screen.getByRole('link', { name: 'r1, alpha, paused' })).toBeInTheDocument();
    const waiting = screen.getByRole('link', { name: 'r2, beta, failed, 2 waiting on you' });
    expect(within(waiting).getByText('2 waiting')).toBeInTheDocument();
  });

  it('describes each row by its phase, age, progress text and subject', () => {
    render(
      <Harness
        runs={[
          run('r1', { tickets: { done: 2, queued: 3 }, subject: 'Fix the flaky test' }),
          run('r2', { state: 'done', phase: null, updated_at: NOW - 7200 }),
          run('r3', { state: 'paused', phase: null, created_at: NOW - 5 * 86400 }),
        ]}
      />,
    );

    expect(row('r1')).toHaveAccessibleDescription('work started 3 minutes ago 2/5 Fix the flaky test');
    expect(row('r2')).toHaveAccessibleDescription('not started ended 2 hours ago no tickets yet');
    expect(row('r3')).toHaveAccessibleDescription('starting started 5 days ago no tickets yet');
  });

  it('renders each age as a <time> with the ISO instant and the full time as its title', () => {
    render(<Harness runs={[run('r1'), run('d1', { state: 'done', updated_at: NOW - 7200 })]} />);

    const started = within(row('r1')).getByText('3 minutes ago');
    expect(started.tagName).toBe('TIME');
    expect(started).toHaveAttribute('datetime', new Date((NOW - 180) * 1000).toISOString());
    expect(started).toHaveAttribute('title', fmtTime(NOW - 180));
    const ended = within(row('d1')).getByText('2 hours ago');
    expect(ended).toHaveAttribute('datetime', new Date((NOW - 7200) * 1000).toISOString());
  });

  it('draws a progressbar for a run with tickets, and only an empty track without', () => {
    render(<Harness runs={[run('r1', { tickets: { done: 2, running: 1, queued: 2 } }), run('r2')]} />);

    const bar = within(row('r1')).getByRole('progressbar');
    expect(bar).toHaveAttribute('aria-valuenow', '2');
    expect(bar).toHaveAttribute('aria-valuemax', '5');
    expect(bar).toHaveAttribute('aria-valuetext', '2 of 5 done');
    expect(within(row('r1')).getByText('2/5')).toBeInTheDocument();
    expect(within(row('r2')).queryByRole('progressbar')).toBeNull();
    expect(within(row('r2')).getByTestId('rail-empty-track')).toHaveAttribute('aria-hidden', 'true');
    expect(within(row('r2')).getByText('no tickets yet')).toBeInTheDocument();
  });

  it('marks the selected row with aria-current, a leading bar and a bold id', () => {
    render(<Harness runs={[run('r1'), run('r2')]} selectedRunId="r2" />);

    expect(row('r2')).toHaveAttribute('aria-current', 'page');
    expect(row('r1')).not.toHaveAttribute('aria-current');
    expect(within(row('r2')).getByTestId('rail-selected-bar')).toBeInTheDocument();
    expect(within(row('r1')).queryByTestId('rail-selected-bar')).toBeNull();
    expect(within(row('r2')).getByText('r2')).toHaveStyle({ fontWeight: '600' });
    expect(within(row('r1')).getByText('r1')).toHaveStyle({ fontWeight: '400' });
  });

  it('highlights no row when the chips hide the selected run', () => {
    render(<Harness runs={[run('r1'), run('r2', { playbook: 'beta' })]} selectedRunId="r2" />);

    fireEvent.click(screen.getByRole('button', { name: 'beta' }));

    expect(screen.queryByRole('link', { name: /^r2,/ })).toBeNull();
    expect(document.querySelector('[aria-current]')).toBeNull();
  });

  it('shows a deep-linked 30th finished run after the newest 10, highlighted', () => {
    render(<Harness runs={finishedRuns(30)} selectedRunId="f-30" />);

    const shown = screen.getAllByRole('link').map((l) => l.getAttribute('aria-label')!.split(',')[0]);
    expect(shown).toEqual([...ids(finishedRuns(10)), 'f-30']);
    expect(row('f-30')).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('button', { name: 'show 19 more' })).toBeInTheDocument();
  });

  it('gives each state its own icon shape, named by the state word', () => {
    const states = ['running', 'paused', 'done', 'failed', 'stopped'];
    render(
      <>
        {states.map((s) => (
          <RunStateIcon key={s} state={s} />
        ))}
      </>,
    );

    const icons = screen.getAllByRole('img');
    expect(icons.map((i) => i.getAttribute('aria-label'))).toEqual(states);
    expect(icons.map((i) => i.getAttribute('title'))).toEqual(states);
    expect(new Set(icons.map((i) => i.querySelector('svg')!.innerHTML)).size).toBe(5);
  });
});

describe('RunRail chips and filter box', () => {
  it('shows one pressed chip per playbook; a click hides its runs, strikes its name and stores it', () => {
    render(<Harness runs={[run('r1'), run('r2', { playbook: 'beta' })]} />);
    const chip = screen.getByRole('button', { name: 'beta' });
    expect(screen.getByRole('button', { name: 'alpha' })).toHaveAttribute('aria-pressed', 'true');
    expect(chip).toHaveAttribute('aria-pressed', 'true');
    expect(within(chip).getByText('✓')).toBeInTheDocument();

    fireEvent.click(chip);
    expect(chip).toHaveAttribute('aria-pressed', 'false');
    expect(within(chip).queryByText('✓')).toBeNull();
    expect(within(chip).getByText('beta')).toHaveStyle({ textDecoration: 'line-through' });
    expect(screen.queryByRole('link', { name: /^r2,/ })).toBeNull();
    expect(window.localStorage.getItem(HIDDEN_KEY)).toBe('["beta"]');

    fireEvent.click(chip);
    expect(chip).toHaveAttribute('aria-pressed', 'true');
    expect(row('r2')).toBeInTheDocument();
    expect(window.localStorage.getItem(HIDDEN_KEY)).toBe('[]');
  });

  it('shows a playbook first seen after the choice was stored', () => {
    window.localStorage.setItem(HIDDEN_KEY, '["beta"]');
    render(<Harness runs={[run('r1'), run('r2', { playbook: 'beta' }), run('r3', { playbook: 'gamma' })]} />);

    expect(screen.getByRole('button', { name: 'beta' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: 'gamma' })).toHaveAttribute('aria-pressed', 'true');
    expect(row('r3')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /^r2,/ })).toBeNull();
  });

  it('turns every chip on when the stored value does not parse', () => {
    window.localStorage.setItem(HIDDEN_KEY, '{oops');
    render(<Harness runs={[run('r1'), run('r2', { playbook: 'beta' })]} />);

    expect(screen.getByRole('button', { name: 'alpha' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'beta' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('says how many runs the filters hide, and Show all clears the text and the chips', () => {
    render(<Harness runs={[run('r1'), run('r2', { playbook: 'beta' }), run('r3', { playbook: 'beta' })]} />);
    expect(screen.queryByText(/hidden/)).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'beta' }));
    expect(screen.getByText(/^2 hidden by filters/)).toBeInTheDocument();
    fireEvent.change(filterBox(), { target: { value: 'nomatch' } });
    expect(screen.getByText(/^3 hidden by filters/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Show all' }));
    expect(filterBox()).toHaveValue('');
    expect(screen.getByRole('button', { name: 'beta' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getAllByRole('link')).toHaveLength(3);
    expect(screen.queryByText(/hidden/)).toBeNull();
  });

  it('counts the decisions waiting in the runs it hides', () => {
    render(
      <Harness
        runs={[run('r1'), run('r2', { playbook: 'beta', awaiting: 2 }), run('r3', { playbook: 'beta', awaiting: 1 })]}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'beta' }));

    expect(screen.getByText(/^2 hidden, 3 waiting on you/)).toBeInTheDocument();
  });

  it('labels the filter box, and filters the rows as you type', () => {
    render(<Harness runs={[run('r1', { subject: 'Fix the flaky test' }), run('r2')]} />);
    const box = filterBox();
    expect(box).toHaveAttribute('placeholder', 'Filter runs (/)');
    expect(box).toHaveAttribute('aria-keyshortcuts', '/');

    fireEvent.change(box, { target: { value: 'FLAKY' } });

    expect(screen.getAllByRole('link').map((l) => l.getAttribute('aria-label'))).toEqual(['r1, alpha, running']);
  });

  it('opens the first visible row on Enter, as a click would', async () => {
    render(<Harness runs={[run('r1', { created_at: 100 }), run('r2', { created_at: 200 })]} tab="tickets" />);

    fireEvent.change(filterBox(), { target: { value: 'r1' } });
    fireEvent.keyDown(filterBox(), { key: 'Enter' });

    await waitFor(() => expect(window.location.hash).toBe('#/runs/r1/tickets'));
  });

  it('clears the text on Escape, then returns focus to where it was before', () => {
    render(
      <>
        <button type="button">elsewhere</button>
        <Harness runs={[run('r1')]} />
      </>,
    );
    act(() => screen.getByRole('button', { name: 'elsewhere' }).focus());
    act(() => filterBox().focus());
    fireEvent.change(filterBox(), { target: { value: 'r' } });

    fireEvent.keyDown(filterBox(), { key: 'Escape' });
    expect(filterBox()).toHaveValue('');
    expect(filterBox()).toHaveFocus();

    fireEvent.keyDown(filterBox(), { key: 'Escape' });
    expect(screen.getByRole('button', { name: 'elsewhere' })).toHaveFocus();
  });

  it("sends focus to the pane's heading on Escape when nothing had it before", () => {
    render(<Harness runs={[run('r1')]} />);
    act(() => filterBox().focus());

    fireEvent.keyDown(filterBox(), { key: 'Escape' });

    expect(screen.getByRole('heading', { level: 1, name: 'pane title' })).toHaveFocus();
  });

  it('reveals every Finished row on "show N more" and focuses the first one it revealed', () => {
    render(<Harness runs={finishedRuns(13)} />);

    fireEvent.click(screen.getByRole('button', { name: 'show 3 more' }));

    expect(screen.getAllByRole('link')).toHaveLength(13);
    expect(row('f-11')).toHaveFocus();
    expect(screen.queryByRole('button', { name: /more$/ })).toBeNull();
  });
});

describe('RunRail collapse, empty and error states', () => {
  it('collapses to a strip with the button and the Needs you count, and stores the choice', () => {
    render(<Harness runs={[run('n1', { awaiting: 1 }), run('n2', { awaiting: 3 }), run('a')]} />);
    const nav = screen.getByRole('navigation', { name: 'Runs' });
    const toggle = screen.getByRole('button', { name: 'Hide runs' });
    const listId = toggle.getAttribute('aria-controls')!;
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(document.getElementById(listId)).toContainElement(filterBox());
    expect(nav).toHaveStyle({ width: '232px' });

    fireEvent.click(toggle);
    expect(screen.getByRole('button', { name: 'Show runs' })).toHaveAttribute('aria-expanded', 'false');
    expect(document.getElementById(listId)).toBeNull();
    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByRole('img', { name: '2 runs waiting on you' })).toHaveTextContent('2');
    expect(nav).toHaveStyle({ width: '48px' });
    expect(window.localStorage.getItem(COLLAPSED_KEY)).toBe('1');

    fireEvent.click(screen.getByRole('button', { name: 'Show runs' }));
    expect(screen.getAllByRole('link')).toHaveLength(3);
    expect(window.localStorage.getItem(COLLAPSED_KEY)).toBe('0');
  });

  it("counts the strip's Needs you rows after the chips, and shows no count at 0", () => {
    window.localStorage.setItem(COLLAPSED_KEY, '1');
    window.localStorage.setItem(HIDDEN_KEY, '["beta"]');
    const { rerender } = render(
      <Harness runs={[run('n1', { awaiting: 1 }), run('n2', { playbook: 'beta', awaiting: 1 })]} />,
    );
    expect(screen.getByRole('img', { name: '1 runs waiting on you' })).toBeInTheDocument();

    rerender(<Harness runs={[run('a1'), run('n2', { playbook: 'beta', awaiting: 1 })]} />);
    expect(screen.queryByRole('img', { name: /waiting on you/ })).toBeNull();
  });

  it('shows No runs yet in place of the filter box, chips and groups', () => {
    render(<Harness runs={[]} />);

    expect(screen.getByText('No runs yet')).toBeInTheDocument();
    expect(screen.queryByRole('searchbox')).toBeNull();
    expect(screen.queryByRole('group', { name: 'Playbooks' })).toBeNull();
    expect(screen.queryAllByRole('heading', { level: 2 })).toHaveLength(0);
    expect(screen.getByRole('button', { name: 'Hide runs' })).toBeInTheDocument();
  });

  it('shows a load error with Retry above the rows it still has, and no empty text', () => {
    const onRetry = vi.fn();
    const { rerender } = render(<Harness runs={[run('r1')]} error={new Error('HTTP 500')} onRetry={onRetry} />);
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent("Couldn't load runs: HTTP 500");
    expect(alert.compareDocumentPosition(filterBox()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(row('r1')).toBeInTheDocument();

    fireEvent.click(within(alert).getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledTimes(1);

    rerender(<Harness runs={[]} error={new Error('HTTP 500')} onRetry={onRetry} />);
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.queryByText('No runs yet')).toBeNull();
  });
});

describe('RunRail selection and focus', () => {
  it('scrolls a new selection into view, and not on a background refetch', () => {
    const scrolled = vi.spyOn(Element.prototype, 'scrollIntoView');
    const runs = [run('r1'), run('r2')];
    const { rerender } = render(<Harness runs={runs} selectedRunId="r1" />);
    expect(scrolled).toHaveBeenCalledTimes(1);
    expect(scrolled.mock.contexts[0]).toBe(row('r1'));
    expect(scrolled).toHaveBeenLastCalledWith({ block: 'nearest' });

    rerender(<Harness runs={[...runs, run('r3')]} selectedRunId="r1" />);
    expect(scrolled).toHaveBeenCalledTimes(1);

    rerender(<Harness runs={[...runs, run('r3')]} selectedRunId="r2" />);
    expect(scrolled).toHaveBeenCalledTimes(2);
    expect(scrolled.mock.contexts[1]).toBe(row('r2'));
  });

  it('moves focus to the newly selected row when a row had it, and leaves it elsewhere', () => {
    const runs = [run('r1'), run('r2')];
    const { rerender } = render(<Harness runs={runs} selectedRunId="r1" />);
    act(() => row('r1').focus());

    rerender(<Harness runs={runs} selectedRunId="r2" />);
    expect(row('r2')).toHaveFocus();

    act(() => filterBox().focus());
    rerender(<Harness runs={runs} selectedRunId="r1" />);
    expect(filterBox()).toHaveFocus();
  });

  it('keeps focus on a row a refetch moves from Active to Needs you', () => {
    const { rerender } = render(<Harness runs={[run('a1', { created_at: 200 }), run('a2', { created_at: 100 })]} />);
    act(() => row('a2').focus());

    rerender(<Harness runs={[run('a1', { created_at: 200 }), run('a2', { created_at: 100, awaiting: 1 })]} />);

    expect(row('a2')).toHaveFocus();
    expect(row('a2').closest('ul')).not.toBe(row('a1').closest('ul'));
  });

  it('gives focus to the row now in its place when a refetch pushes the focused row behind the cap', () => {
    const { rerender } = render(<Harness runs={finishedRuns(12)} />);
    act(() => row('f-10').focus());

    rerender(<Harness runs={[...finishedRuns(12), run('f-00', { state: 'done', updated_at: NOW })]} />);

    expect(screen.queryByRole('link', { name: /^f-10,/ })).toBeNull();
    expect(row('f-09')).toHaveFocus();
  });

  it('gives focus to the filter box when the focused row and its group are gone', () => {
    const { rerender } = render(<Harness runs={[run('n1', { awaiting: 1 }), run('a1')]} />);
    act(() => row('n1').focus());

    rerender(<Harness runs={[run('a1')]} />);

    expect(filterBox()).toHaveFocus();
  });
});
