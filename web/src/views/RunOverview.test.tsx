import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import RunOverview from './RunOverview';
import type { RunDetail } from '../api/client';

const mockRun: RunDetail = {
  id: 'test-run-123',
  playbook: 'example',
  site: 'local',
  state: 'running',
  phase: 'work',
  base_ref: 'main',
  created_at: '2026-07-29T10:00:00Z',
  updated_at: '2026-07-29T10:05:00Z',
  config: { issue_kind: 'bug' },
  has_view: false,
  tickets: {
    queued: 15,
    running: 8,
    done: 42,
    parked: 3,
    failed: 2,
  },
  phases: [
    {
      name: 'work',
      counts: { queued: 15, running: 8, done: 30, parked: 3, failed: 2 },
      current: true,
    },
    {
      name: 'reduce',
      counts: { done: 12 },
      current: false,
    },
  ],
};

describe('RunOverview', () => {
  it('should render stat tiles with correct counts', () => {
    render(<RunOverview run={mockRun} />);

    // Total tickets (15 + 8 + 42 + 3 + 2 = 70)
    expect(screen.getByText('70')).toBeInTheDocument();
    // Done
    expect(screen.getByText('42')).toBeInTheDocument();
    // Running
    expect(screen.getByText('8')).toBeInTheDocument();
    // Parked
    expect(screen.getByText('3')).toBeInTheDocument();
    // Failed
    expect(screen.getByText('2')).toBeInTheDocument();
    // Queued
    expect(screen.getByText('15')).toBeInTheDocument();
  });

  it('should render phase timeline with current phase highlighted', () => {
    render(<RunOverview run={mockRun} />);

    // Both phases should be present, each carrying its ticket total
    expect(screen.getByText('work 58')).toBeInTheDocument();
    expect(screen.getByText('reduce 12')).toBeInTheDocument();
  });

  it('colours each phase pill by what its tickets came to, not by whether it is current', () => {
    const run: RunDetail = {
      ...mockRun,
      phase: 't04-ops',
      phases: [
        { name: 't01-pm', counts: { done: 1 }, current: false },
        { name: 't02-eng', counts: { failed: 1 }, current: false },
        { name: 't03-qa', counts: { needs_human: 1 }, current: false },
        // work waiting in Needs you outranks a failure beside it
        { name: 'solve', counts: { failed: 1, needs_human: 1 }, current: false },
        // `running` is a state the engine barely writes: claimed work sits in
        // `dispatched` until its result lands, then in `reducing`.
        { name: 't04-ops', counts: { dispatched: 1 }, current: true },
        { name: 't05-sre', counts: { reducing: 1 }, current: false },
        { name: 't06-sec', counts: { parked: 1 }, current: false },
        { name: 'fan', counts: { done: 3, queued: 2 }, current: false },
        { name: 'report', counts: {}, current: false },
      ],
    };
    render(<RunOverview run={run} />);

    const stateOf = (label: string) => screen.getByText(label).getAttribute('data-state');
    expect(stateOf('t01-pm')).toBe('done');
    expect(stateOf('t02-eng')).toBe('failed');
    expect(stateOf('t03-qa')).toBe('needs-human');
    expect(stateOf('solve 2')).toBe('needs-human');
    expect(stateOf('t04-ops')).toBe('running');
    expect(stateOf('t05-sre')).toBe('running');
    expect(stateOf('t06-sec')).toBe('parked');
    expect(stateOf('fan 5')).toBe('queued');
    expect(stateOf('report')).toBe('queued');
  });

  it('keeps a finished run\'s last phase from reading as running', () => {
    // A run that is over still names its last phase as current.
    const run: RunDetail = {
      ...mockRun,
      state: 'done',
      phases: [{ name: 'solve', counts: { done: 11, failed: 1 }, current: true }],
    };
    render(<RunOverview run={run} />);

    expect(screen.getByText('solve 12').getAttribute('data-state')).toBe('failed');
  });

  it.each(['done', 'failed'])(
    'ends a %s run\'s zero-ticket last phase as the run did, without a live pulse',
    (state) => {
      // committee's `ruling` and research's `complete` mint no tickets.
      const run: RunDetail = {
        ...mockRun,
        state,
        phases: [
          { name: 'decision', counts: { [state]: 1 }, current: false },
          { name: 'ruling', counts: {}, current: true },
        ],
      };
      render(<RunOverview run={run} />);

      const pill = screen.getByText('ruling');
      expect(pill.getAttribute('data-state')).toBe(state);
      const bar = pill.parentElement!.parentElement!.firstChild as HTMLElement;
      expect(bar.style.animation).toBe('none');
    },
  );

  it('pulses the current phase of a live run', () => {
    render(<RunOverview run={mockRun} />);

    const bar = screen.getByText('work 58').parentElement!.parentElement!.firstChild as HTMLElement;
    expect(bar.style.animation).toContain('fm-pulse');
  });

  it('lets the phase rail wrap rather than squeeze many phases into one row', () => {
    const run: RunDetail = {
      ...mockRun,
      phases: Array.from({ length: 17 }, (_, i) => ({
        name: `t${i + 1}`,
        counts: { done: 1 },
        current: false,
      })),
    };
    render(<RunOverview run={run} />);

    const rail = screen.getByText('t1').closest('[data-testid="phase-rail"]') as HTMLElement;
    expect(rail.style.flexWrap).toBe('wrap');
    expect(rail.children).toHaveLength(17);
  });

  it('should render playbook name and allow opening playbook dialog', () => {
    render(<RunOverview run={mockRun} />);

    const playbookTitle = screen.getByText(/example run/i);
    expect(playbookTitle).toBeInTheDocument();

    // Click to open dialog
    fireEvent.click(playbookTitle);

    // Dialog should now be visible
    expect(screen.getByText(/example playbook/i)).toBeInTheDocument();
  });

  it('should render context chips', () => {
    render(<RunOverview run={mockRun} />);

    expect(screen.getByText('issue_kind')).toBeInTheDocument();
    expect(screen.getByText('bug')).toBeInTheDocument();
  });

  it('should render progress bar with correct percentage', () => {
    render(<RunOverview run={mockRun} />);

    // 42 done / 70 total = 60%
    expect(screen.getByText('42 / 70 tickets')).toBeInTheDocument();
    expect(screen.getByText('60%')).toBeInTheDocument();
  });

  it('should handle zero total tickets gracefully', () => {
    const emptyRun: RunDetail = {
      ...mockRun,
      tickets: {},
      phases: [
        { name: 'work', counts: {}, current: true },
        { name: 'reduce', counts: {}, current: false },
      ],
    };

    render(<RunOverview run={emptyRun} />);

    // Should show 0 / 0 tickets and 0%
    expect(screen.getByText('0 / 0 tickets')).toBeInTheDocument();
    expect(screen.getByText('0%')).toBeInTheDocument();
  });
});
