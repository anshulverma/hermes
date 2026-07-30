import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import HermesTicketCard, { priorityColor } from './HermesTicketCard';

const base = {
  id: 'run-1/t-0',
  subject: 'Fix the thing',
  state: 'queued',
  phase: 'work',
  attempts: 0,
  elapsed_s: 0,
  resource_req: 'cpu',
  priority: 0,
};

describe('HermesTicketCard', () => {
  it('shows a colored priority pill (p0 = highest = danger)', () => {
    render(<HermesTicketCard ticket={{ ...base, priority: 0 }} />);
    const pill = screen.getByText('P0');
    expect(pill).toBeInTheDocument();
    expect(pill.style.color).toContain('--status-danger');
  });

  it('cools the color as the priority number grows', () => {
    expect(priorityColor(0)).toContain('--status-danger');
    expect(priorityColor(1)).toContain('--status-attention');
    expect(priorityColor(2)).toContain('--status-live');
    expect(priorityColor(5)).toContain('--text-muted');
  });

  it('labels metrics clearly (no cryptic "try 0 0s")', () => {
    render(<HermesTicketCard ticket={{ ...base, attempts: 0, elapsed_s: 0 }} />);
    expect(screen.getByText('0 attempts')).toBeInTheDocument();
    expect(screen.getByText('0s elapsed')).toBeInTheDocument();
    expect(screen.queryByText(/try 0/)).not.toBeInTheDocument();
  });

  it('singularizes a single attempt and humanizes elapsed', () => {
    render(<HermesTicketCard ticket={{ ...base, attempts: 1, elapsed_s: 125 }} />);
    expect(screen.getByText('1 attempt')).toBeInTheDocument();
    expect(screen.getByText('2m elapsed')).toBeInTheDocument();
  });

  it('fires onClick when the card is clicked', () => {
    const onClick = vi.fn();
    render(<HermesTicketCard ticket={base} onClick={onClick} />);
    fireEvent.click(screen.getByText('Fix the thing'));
    expect(onClick).toHaveBeenCalledOnce();
  });
});
