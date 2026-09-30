/**
 * The run header: which run, its state, phase, times, progress, ⚑, controls and
 * the ‹ › links App hands it.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { ComponentProps } from 'react';
import RunHeader from './RunHeader';
import type { Run, RunDetail } from '../api/client';
import { fmtTime } from '../util/time';

// The shared 30 s clock, frozen: 600 s after the fixtures' created_at.
vi.mock('../hooks/useNow', () => ({ useNow: () => 1_000_600 }));

const row = (over: Partial<Run> = {}): Run => ({
  id: 'run-a',
  playbook: 'pb',
  site: 'local',
  state: 'running',
  phase: 'work',
  base_ref: 'main',
  created_at: 1_000_000,
  updated_at: 1_000_125,
  tickets: { done: 1, queued: 1 },
  has_view: false,
  awaiting: 0,
  subject: null,
  ...over,
});

const detail: RunDetail = {
  id: 'run-a',
  playbook: 'pb',
  site: 'local',
  state: 'running',
  phase: 'work',
  base_ref: 'main',
  created_at: 1_000_000,
  updated_at: 1_000_125,
  tickets: { done: 1, queued: 1 },
  has_view: false,
  config: {},
  phases: [],
};

const header = (props: Partial<ComponentProps<typeof RunHeader>> = {}) => (
  <RunHeader run={row()} prevHref={null} nextHref={null} onRunUpdate={() => {}} {...props} />
);

describe('RunHeader', () => {
  it('names the run as the pane h1, which takes focus but is not in the tab order', () => {
    render(header());

    const h1 = screen.getByRole('heading', { level: 1, name: 'run-a · pb' });
    expect(h1).toHaveAttribute('tabindex', '-1');
  });

  it('shows runs.state verbatim with its icon, and never Waiting on you as the state', () => {
    const { rerender } = render(header({ run: row({ state: 'paused' }) }));
    expect(screen.getByText('paused')).toBeInTheDocument();
    expect(screen.getByTitle('paused')).toBeInTheDocument();

    rerender(header({ run: row({ state: 'running', awaiting: 2 }) }));
    expect(screen.getByText('running')).toBeInTheDocument();
    expect(screen.queryByText(/^waiting on you$/i)).not.toBeInTheDocument();
  });

  it('shows the phase, or starting for a running or paused run with none yet', () => {
    const { rerender } = render(header({ run: row({ phase: 'work' }) }));
    expect(screen.getByText('work')).toBeInTheDocument();

    rerender(header({ run: row({ phase: null, state: 'running' }) }));
    expect(screen.getByText('starting')).toBeInTheDocument();

    rerender(header({ run: row({ phase: null, state: 'paused' }) }));
    expect(screen.getByText('starting')).toBeInTheDocument();
    expect(screen.queryByText('not started')).not.toBeInTheDocument();
  });

  it('shows not started for a done, failed or stopped run whose phase is null', () => {
    for (const state of ['done', 'failed', 'stopped']) {
      const { unmount } = render(header({ run: row({ phase: null, state }) }));
      expect(screen.getByText('not started')).toBeInTheDocument();
      expect(screen.queryByText('starting')).not.toBeInTheDocument();
      unmount();
    }
  });

  it('shows the start time and the elapsed time up to now while the run is live', () => {
    const { rerender } = render(header({ run: row({ state: 'running', created_at: 1_000_000 }) }));

    const started = screen.getByText(fmtTime(1_000_000));
    expect(started.tagName).toBe('TIME');
    expect(started).toHaveAttribute('datetime', new Date(1_000_000_000).toISOString());
    expect(screen.getByText('10m 0s elapsed')).toBeInTheDocument();

    // A start stamped ahead of this browser's clock reads 0s, never negative.
    rerender(header({ run: row({ state: 'running', created_at: 1_000_700 }) }));
    expect(screen.getByText('0s elapsed')).toBeInTheDocument();
  });

  it("measures a finished run's elapsed time to updated_at, not now", () => {
    for (const state of ['done', 'failed', 'stopped']) {
      const { unmount } = render(
        header({ run: row({ state, created_at: 1_000_000, updated_at: 1_000_125 }) }),
      );
      expect(screen.getByText('2m 5s elapsed')).toBeInTheDocument();
      expect(screen.queryByText('10m 0s elapsed')).not.toBeInTheDocument();
      unmount();
    }
  });

  it('draws a progressbar whose valuetext is the done, in flight and failed caption', () => {
    const tickets = { done: 3, dispatched: 1, running: 1, reducing: 1, queued: 2, failed: 1, parked: 1 };
    render(header({ run: row({ tickets }) }));

    const caption = '3 of 10 done · 3 in flight · 1 failed';
    const bar = screen.getByRole('progressbar', { name: 'Tickets' });
    expect(bar).toHaveAttribute('aria-valuemin', '0');
    expect(bar).toHaveAttribute('aria-valuenow', '3');
    expect(bar).toHaveAttribute('aria-valuemax', '10');
    expect(bar).toHaveAttribute('aria-valuetext', caption);
    expect(screen.getByText(caption)).toBeInTheDocument();
    // done, in flight, failed segments, each its share of all 10 tickets.
    expect([...bar.children].map((c) => (c as HTMLElement).style.width)).toEqual(['30%', '30%', '10%']);
  });

  it('drops zero in-flight and failed terms from the caption', () => {
    render(header({ run: row({ tickets: { done: 2, queued: 1 } }) }));

    expect(screen.getByText('2 of 3 done')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuetext', '2 of 3 done');
    expect(screen.queryByText(/in flight|failed/)).not.toBeInTheDocument();
  });

  it('shows the empty track and no tickets yet, with no progressbar, at 0 tickets', () => {
    render(header({ run: row({ tickets: {} }) }));

    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    const empty = screen.getByText('no tickets yet');
    expect(empty.previousElementSibling).toHaveAttribute('aria-hidden', 'true');
    expect(screen.queryByText(/0%/)).not.toBeInTheDocument();
  });

  it('links ⚑ N waiting on you to this run on Needs you', () => {
    render(header({ run: row({ awaiting: 2 }) }));

    const flag = screen.getByRole('link', { name: '2 waiting on you' });
    expect(flag).toHaveAttribute('href', '#/needs-you?run=run-a');
    expect(flag).toHaveTextContent('⚑ 2 waiting on you');
  });

  it("shows no ⚑ when the row's awaiting is 0", () => {
    render(header({ run: row({ awaiting: 0 }) }));

    expect(screen.queryByRole('link', { name: /waiting on you/ })).not.toBeInTheDocument();
  });

  it('shows no ⚑ for the run-detail fallback, which carries no awaiting', () => {
    render(header({ run: detail }));

    expect(screen.getByRole('heading', { level: 1, name: 'run-a · pb' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /waiting on you/ })).not.toBeInTheDocument();
  });

  it('offers Pause and Stop while running, and Reopen with its line once finished', () => {
    const { rerender } = render(header({ run: row({ state: 'running' }) }));
    expect(screen.getByRole('button', { name: 'Pause' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument();

    rerender(header({ run: row({ state: 'done' }) }));
    expect(screen.queryByRole('button', { name: 'Pause' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reopen' })).toBeInTheDocument();
    expect(
      screen.getByText('Run is done — reopen it to dispatch remaining tickets.'),
    ).toBeInTheDocument();
  });

  it('calls onRunUpdate after a control succeeds', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ state: 'paused' }),
    }) as any;
    const onRunUpdate = vi.fn();
    render(header({ onRunUpdate }));

    fireEvent.click(screen.getByRole('button', { name: 'Pause' }));

    await waitFor(() => expect(onRunUpdate).toHaveBeenCalledTimes(1));
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/runs/run-a/pause',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('keys RunControl on the run, so an open Stop confirmation stays with its run', () => {
    const { rerender } = render(header());
    fireEvent.click(screen.getByRole('button', { name: 'Stop' }));
    expect(screen.getByText(/confirm stop/i)).toBeInTheDocument();

    rerender(header({ run: row({ id: 'run-b' }) }));

    expect(screen.queryByText(/confirm stop/i)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument();
  });

  it('renders ‹ › as links to prevHref and nextHref with labels, shortcuts and tooltips', () => {
    render(header({ prevHref: '#/runs/run-0/summary', nextHref: '#/runs/run-b/summary' }));

    const prev = screen.getByRole('link', { name: 'Previous run' });
    expect(prev).toHaveAttribute('href', '#/runs/run-0/summary');
    expect(prev).toHaveAttribute('aria-keyshortcuts', '[');
    expect(prev).toHaveAttribute('title', 'Previous run ([)');
    expect(prev).not.toHaveAttribute('aria-disabled');

    const next = screen.getByRole('link', { name: 'Next run' });
    expect(next).toHaveAttribute('href', '#/runs/run-b/summary');
    expect(next).toHaveAttribute('aria-keyshortcuts', ']');
    expect(next).toHaveAttribute('title', 'Next run (])');
    expect(next).not.toHaveAttribute('aria-disabled');
  });

  it('renders an end with no href as an aria-disabled link that still takes focus', () => {
    render(header({ prevHref: null, nextHref: '#/runs/run-b/summary' }));

    const prev = screen.getByRole('link', { name: 'Previous run' });
    expect(prev).toHaveAttribute('aria-disabled', 'true');
    expect(prev).not.toHaveAttribute('href');
    expect(prev).toHaveAttribute('tabindex', '0');
    prev.focus();
    expect(prev).toHaveFocus();
  });

  it('keeps focus on › while the run and its hrefs change', () => {
    const { rerender } = render(header({ prevHref: null, nextHref: '#/runs/run-b/summary' }));
    const next = screen.getByRole('link', { name: 'Next run' });
    next.focus();

    rerender(
      header({ run: row({ id: 'run-b' }), prevHref: '#/runs/run-a/summary', nextHref: null }),
    );

    expect(screen.getByRole('link', { name: 'Next run' })).toBe(next);
    expect(next).toHaveFocus();
    expect(next).toHaveAttribute('aria-disabled', 'true');
  });
});
