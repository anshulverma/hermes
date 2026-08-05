import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
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

  it('should render Run, Metrics, Tickets, Crew, Findings, and Activity tabs (Phase E1)', () => {
    render(<TopBar connected={true} />);

    // All main tabs should be present (Phase E1 adds Metrics)
    expect(screen.getByText('Run')).toBeInTheDocument();
    expect(screen.getByText('Metrics')).toBeInTheDocument();
    expect(screen.getByText('Tickets')).toBeInTheDocument();
    expect(screen.getByText('Crew')).toBeInTheDocument();
    expect(screen.getByText('Findings')).toBeInTheDocument();
    expect(screen.getByText('Activity')).toBeInTheDocument();
  });
});
