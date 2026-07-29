import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import TopBar from './TopBar';

describe('TopBar', () => {
  it('should render Hermes title', () => {
    render(<TopBar connected={true} runs={[]} />);
    expect(screen.getByText('Hermes')).toBeInTheDocument();
  });

  it('should show live indicator when connected', () => {
    render(<TopBar connected={true} runs={[]} />);
    expect(screen.getByText('live')).toBeInTheDocument();
  });

  it('should show offline when not connected', () => {
    render(<TopBar connected={false} runs={[]} />);
    expect(screen.getByText('offline')).toBeInTheDocument();
  });

  it('should render Run, Metrics, Tickets, Crew, Findings, and Activity tabs (Phase E1)', () => {
    render(<TopBar connected={true} runs={[]} />);

    // All main tabs should be present (Phase E1 adds Metrics)
    expect(screen.getByText('Run')).toBeInTheDocument();
    expect(screen.getByText('Metrics')).toBeInTheDocument();
    expect(screen.getByText('Tickets')).toBeInTheDocument();
    expect(screen.getByText('Crew')).toBeInTheDocument();
    expect(screen.getByText('Findings')).toBeInTheDocument();
    expect(screen.getByText('Activity')).toBeInTheDocument();
  });
});
