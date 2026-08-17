import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import Clamp from './Clamp';

const long = Array.from({ length: 100 }, (_, i) => `line ${i}`).join('\n');

describe('Clamp', () => {
  it('leaves a short block alone', () => {
    render(<Clamp text={'a\nb'} data-testid="body"><p>short</p></Clamp>);

    expect(screen.getByTestId('body').style.maxHeight).toBe('');
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('clamps a long block and says how much there is', () => {
    render(<Clamp text={long} data-testid="body"><p>long</p></Clamp>);

    expect(screen.getByTestId('body').style.maxHeight).toBe('360px');
    expect(screen.getByRole('button', { name: /show all 100 lines/i })).toBeInTheDocument();
  });

  it('never scrolls on its own — that would steal the wheel from the page', () => {
    render(<Clamp text={long} data-testid="body"><p>long</p></Clamp>);

    const el = screen.getByTestId('body');
    expect(el.style.overflow).toBe('hidden');
    expect(el.style.overflowY).not.toBe('auto');
  });

  it('shows everything when asked, and can go back', () => {
    render(<Clamp text={long} data-testid="body"><p>long</p></Clamp>);

    fireEvent.click(screen.getByRole('button', { name: /show all/i }));
    expect(screen.getByTestId('body').style.maxHeight).toBe('');

    fireEvent.click(screen.getByRole('button', { name: /show less/i }));
    expect(screen.getByTestId('body').style.maxHeight).toBe('360px');
  });

  it('always renders its children, clamped or not', () => {
    render(<Clamp text={long}><p>the content</p></Clamp>);

    expect(screen.getByText('the content')).toBeInTheDocument();
  });

  it('honours a custom threshold', () => {
    render(<Clamp text={'a\nb\nc'} lines={2} height={100} data-testid="body"><p>x</p></Clamp>);

    expect(screen.getByTestId('body').style.maxHeight).toBe('100px');
  });
});
