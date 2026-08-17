import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import TopBar from './TopBar';

describe('TopBar', () => {
  it('should render Hermes title', () => {
    render(<TopBar connected={true} />);
    // The wordmark is the favicon mark standing in for the leading "H" plus
    // "ermes", so it is found by its accessible name rather than raw text.
    expect(screen.getByLabelText('Hermes')).toBeInTheDocument();
  });

  it('crops the mark to the artwork so no tile padding shows as a gap', () => {
    const { container } = render(<TopBar connected={true} />);
    const mark = container.querySelector('svg[viewBox]');
    const [minX, , width] = mark!.getAttribute('viewBox')!.split(' ').map(Number);

    // The favicon's own box (0 0 32 32) insets the artwork to leave room for the
    // rounded tile behind it. Reuse it here and that padding renders as dead
    // space between the "H" and the "e". The H stems live at x 8.5-23.5, and the
    // wing ticks reach 5.6 and 26.4, so anything wider is padding.
    expect(minX).toBeGreaterThanOrEqual(5.6);
    expect(minX + width).toBeLessThanOrEqual(26.4);
  });

  it('should show live indicator when connected', () => {
    render(<TopBar connected={true} />);
    expect(screen.getByText('live')).toBeInTheDocument();
  });

  it('should show offline when not connected', () => {
    render(<TopBar connected={false} />);
    expect(screen.getByText('offline')).toBeInTheDocument();
  });

  it('should render Run, Metrics, Tickets, Crew, Outputs, Review and Activity tabs', () => {
    render(<TopBar connected={true} />);

    // All main tabs should be present (Phase E1 adds Metrics)
    expect(screen.getByText('Run')).toBeInTheDocument();
    expect(screen.getByText('Metrics')).toBeInTheDocument();
    expect(screen.getByText('Tickets')).toBeInTheDocument();
    expect(screen.getByText('Crew')).toBeInTheDocument();
    expect(screen.getByText('Outputs')).toBeInTheDocument();
    expect(screen.getByText('Review')).toBeInTheDocument();
    expect(screen.getByText('Activity')).toBeInTheDocument();
  });
});

describe('TopBar — choosing which run to look at', () => {
  const runs = [
    { id: 'run-5', playbook: 'research', site: 'local', state: 'done', phase: 'complete',
      base_ref: 'main', created_at: '3', tickets: {} },
    { id: 'run-4', playbook: 'research', site: 'local', state: 'done', phase: 'complete',
      base_ref: 'main', created_at: '2', tickets: {} },
    { id: 'run-3', playbook: 'research', site: 'local', state: 'stopped', phase: 'research',
      base_ref: 'main', created_at: '1', tickets: {} },
  ];

  it('lists every run, not just the newest', () => {
    // The console used to hardcode runs[0]; every other run was unreachable.
    render(<TopBar connected runs={runs} selectedRunId="run-5" onRunChange={() => {}} />);

    const picker = screen.getByTestId('run-picker') as HTMLSelectElement;
    expect(Array.from(picker.options).map((o) => o.value)).toEqual(['run-5', 'run-4', 'run-3']);
  });

  it('shows which run is being viewed', () => {
    render(<TopBar connected runs={runs} selectedRunId="run-4" onRunChange={() => {}} />);

    expect((screen.getByTestId('run-picker') as HTMLSelectElement).value).toBe('run-4');
  });

  it('reports a change to its caller', () => {
    const onRunChange = vi.fn();
    render(<TopBar connected runs={runs} selectedRunId="run-5" onRunChange={onRunChange} />);

    fireEvent.change(screen.getByTestId('run-picker'), { target: { value: 'run-3' } });

    expect(onRunChange).toHaveBeenCalledWith('run-3');
  });

  it('stays out of the way when there is nothing to choose between', () => {
    render(<TopBar connected runs={[runs[0]]} selectedRunId="run-5" onRunChange={() => {}} />);

    expect(screen.queryByTestId('run-picker')).toBeNull();
  });

  it('renders without run props at all', () => {
    render(<TopBar connected />);

    expect(screen.getByLabelText('Hermes')).toBeInTheDocument();
    expect(screen.queryByTestId('run-picker')).toBeNull();
  });
});

describe('TopBar — the review queue is visible before you go looking', () => {
  it('shows how many decisions are waiting', () => {
    render(<TopBar connected reviewCount={3} />);

    expect(screen.getByTestId('review-count')).toHaveTextContent('3');
  });

  it('shows no badge when nothing is waiting', () => {
    render(<TopBar connected reviewCount={0} />);

    expect(screen.getByTestId('tab-review')).toBeInTheDocument();
    expect(screen.queryByTestId('review-count')).toBeNull();
  });

  it('shows no badge before the count is known', () => {
    render(<TopBar connected reviewCount={null} />);

    expect(screen.queryByTestId('review-count')).toBeNull();
  });
});
