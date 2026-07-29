import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import TopBar from './TopBar';

describe('TopBar', () => {
  it('should render Hermes title', () => {
    render(<TopBar health={{ status: 'ok', version: '0.1.0', home: '/tmp' }} runs={[]} />);
    expect(screen.getByText('Hermes')).toBeInTheDocument();
  });

  it('should show live indicator when health is ok', () => {
    render(<TopBar health={{ status: 'ok', version: '0.1.0', home: '/tmp' }} runs={[]} />);
    expect(screen.getByText('live')).toBeInTheDocument();
  });

  it('should show degraded state when health is error', () => {
    render(<TopBar health={null} runs={[]} />);
    expect(screen.getByText('offline')).toBeInTheDocument();
  });

  it('should not render view tabs (no views exist yet)', () => {
    render(<TopBar health={{ status: 'ok', version: '0.1.0', home: '/tmp' }} runs={[]} />);

    // Verify no tabs are present (they will be added in Phase B)
    expect(screen.queryByText('Run')).not.toBeInTheDocument();
    expect(screen.queryByText('Tickets')).not.toBeInTheDocument();
    expect(screen.queryByText('Metrics')).not.toBeInTheDocument();
  });
});
