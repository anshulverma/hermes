import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ItemRows from './ItemRows';

const items = [
  { id: '1', label: 'ITEM-1', text: '# One\n\nbody', verdict: 'blocking', headline: 'Tier leaks' },
  { id: '2', label: 'ITEM-2', text: '# Two\n\nbody', verdict: 'clean', headline: null },
  { id: '3', label: 'ITEM-3', text: '# Three\n\nbody', verdict: null, headline: null },
];

describe('ItemRows', () => {
  it('shows one row per item rather than one document per item', () => {
    render(<ItemRows items={items} />);

    expect(screen.getByTestId('item-row-1')).toBeInTheDocument();
    expect(screen.getByTestId('item-row-3')).toBeInTheDocument();
    // Bodies stay shut until asked for.
    expect(screen.queryByText('body')).toBeNull();
  });

  it('shows a stated verdict', () => {
    render(<ItemRows items={items} />);

    expect(screen.getByTestId('verdict-blocking')).toHaveTextContent('blocking');
    expect(screen.getByTestId('verdict-clean')).toHaveTextContent('clean');
  });

  it('says "unstated" rather than leaving a gap that reads as clean', () => {
    render(<ItemRows items={items} />);

    expect(screen.getByTestId('verdict-unstated')).toHaveTextContent('unstated');
  });

  it("prefers the agent's own headline over the write-up's first heading", () => {
    render(<ItemRows items={items} />);

    expect(screen.getByText('Tier leaks')).toBeInTheDocument();
    expect(screen.getByText('Two')).toBeInTheDocument(); // fell back to the heading
  });

  it('opens one item at a time', () => {
    render(<ItemRows items={items} />);

    fireEvent.click(screen.getByTestId('item-row-1'));
    expect(screen.getByTestId('item-row-1').getAttribute('aria-expanded')).toBe('true');

    fireEvent.click(screen.getByTestId('item-row-2'));
    expect(screen.getByTestId('item-row-1').getAttribute('aria-expanded')).toBe('false');
    expect(screen.getByTestId('item-row-2').getAttribute('aria-expanded')).toBe('true');
  });
});

describe('ReductionCard verdict summary', () => {
  it('states the shape of a batch before its rows', async () => {
    const { default: ReductionCard } = await import('./ReductionCard');
    const reduction = {
      id: 7, run_id: 'r', phase: 'synthesize', kind: 'item_syntheses',
      review_state: 'pending', member_ticket_ids: [], member_tickets: [],
      json: {
        syntheses: [{ item_id: 'A', synthesis: 'body', verdict: 'blocking' }],
        verdict_counts: { blocking: 2, 'needs-discussion': 1, clean: 0, unstated: 1 },
      },
    };

    render(<ReductionCard reduction={reduction as any} />);

    const summary = screen.getByTestId('verdict-summary-7');
    expect(summary).toHaveTextContent('2 blocking');
    expect(summary).toHaveTextContent('1 unstated');
    // A band with nothing in it is not worth a slot.
    expect(summary).not.toHaveTextContent('0 clean');
  });
});
