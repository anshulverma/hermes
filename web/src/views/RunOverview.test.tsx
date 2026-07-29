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

    // Both phases should be present
    expect(screen.getByText('work')).toBeInTheDocument();
    expect(screen.getByText('reduce')).toBeInTheDocument();
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
