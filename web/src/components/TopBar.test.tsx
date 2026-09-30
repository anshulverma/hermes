import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
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

  it('links the wordmark to the default run', () => {
    render(<TopBar connected />);
    expect(screen.getByRole('link', { name: 'Hermes' })).toHaveAttribute('href', '#/runs');
  });

  it('lists the cross-run pages Needs you, Crew and Activity as links, and nothing about one run', () => {
    render(<TopBar connected />);
    const pages = within(screen.getByRole('navigation', { name: 'Pages' })).getAllByRole('link');
    expect(pages.map((a) => [a.textContent, a.getAttribute('href')])).toEqual([
      ['Needs you', '#/needs-you'],
      ['Crew', '#/crew'],
      ['Activity', '#/activity'],
    ]);
    // No run picker and no per-run tabs: the rail picks the run, the pane has its tabs.
    expect(screen.queryByRole('combobox')).toBeNull();
    expect(screen.queryByText('Playbook')).toBeNull();
    expect(screen.queryByText('Metrics')).toBeNull();
  });

  it('marks the cross-run page on screen, and only it, with aria-current', () => {
    render(<TopBar connected page="crew" />);
    expect(screen.getByRole('link', { name: 'Crew' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Activity' })).not.toHaveAttribute('aria-current');
    expect(screen.getByRole('link', { name: 'Needs you' })).not.toHaveAttribute('aria-current');
  });

  it('marks no item on a run route', () => {
    render(<TopBar connected page="run" />);
    const pages = within(screen.getByRole('navigation', { name: 'Pages' })).getAllByRole('link');
    expect(pages.filter((a) => a.hasAttribute('aria-current'))).toEqual([]);
  });
});

describe('TopBar — the Needs you count', () => {
  it('shows how many decisions are waiting across every run', () => {
    render(<TopBar connected needsYouCount={3} />);
    expect(screen.getByTestId('needs-you-count')).toHaveTextContent('3');
  });

  it('shows no badge when nothing is waiting, but keeps the item', () => {
    render(<TopBar connected needsYouCount={0} />);
    expect(screen.getByRole('link', { name: 'Needs you' })).toBeInTheDocument();
    expect(screen.queryByTestId('needs-you-count')).toBeNull();
  });

  it('shows no badge before the count is known', () => {
    render(<TopBar connected needsYouCount={null} />);
    expect(screen.queryByTestId('needs-you-count')).toBeNull();
  });
});
