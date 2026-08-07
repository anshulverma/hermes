import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import JsonView from './JsonView';
import { tryParseJson } from '../util/json';

describe('JsonView', () => {
  it('renders keys and scalar values instead of a serialised blob', () => {
    render(<JsonView data-testid="v" value={{ name: 'gemma', size: 27, ok: true, ref: null }} />);

    const view = screen.getByTestId('v');
    expect(view).toHaveTextContent('"name"');
    expect(view).toHaveTextContent('"gemma"');
    expect(view).toHaveTextContent('27');
    expect(view).toHaveTextContent('true');
    expect(view).toHaveTextContent('null');
  });

  it('folds containers past the auto-open depth and summarises what is hidden', () => {
    render(
      <JsonView
        data-testid="v"
        value={{ outer: { middle: { deep: { a: 1, b: 2 } } } }}
      />,
    );

    // Depth 0/1 are open, so "middle" is visible; the container below it is not.
    expect(screen.getByTestId('v')).toHaveTextContent('"middle"');
    expect(screen.getByTestId('v')).not.toHaveTextContent('"a"');
    // A folded container still says how much it is hiding.
    expect(screen.getByTestId('v')).toHaveTextContent('1 key');
  });

  it('expands a folded container when clicked', () => {
    // "middle" is the first folded level, so its contents appear on one click.
    render(<JsonView data-testid="v" value={{ outer: { middle: { a: 1 } } }} />);

    const view = screen.getByTestId('v');
    expect(view).not.toHaveTextContent('"a"');

    fireEvent.click(within(view).getByText('"middle"'));

    expect(view).toHaveTextContent('"a"');
  });

  it('counts array items and object keys separately, and singularises', () => {
    render(<JsonView data-testid="v" value={{ a: { b: { list: [1, 2, 3] } } }} />);
    expect(screen.getByTestId('v')).toHaveTextContent('1 key');

    render(<JsonView data-testid="w" value={{ a: { b: [1, 2, 3] } }} />);
    expect(screen.getByTestId('w')).toHaveTextContent('3 items');
  });

  it('renders empty containers inline rather than as a toggle', () => {
    render(<JsonView data-testid="v" value={{ empty: {}, none: [] }} />);
    const view = screen.getByTestId('v');
    expect(view).toHaveTextContent('{}');
    expect(view).toHaveTextContent('[]');
  });

  it('clamps a long string behind an expander instead of truncating it', () => {
    const long = 'x'.repeat(400);
    render(<JsonView data-testid="v" value={{ detail: long }} />);

    const toggle = screen.getByText(/show all 400 chars/);
    expect(toggle).toBeInTheDocument();
    // The whole value is present, just visually clamped — nothing is lost.
    expect(screen.getByTestId('v')).toHaveTextContent(long);

    fireEvent.click(toggle);
    expect(screen.getByText('show less')).toBeInTheDocument();
  });

  it('drops its card chrome when plain, for callers that already draw a box', () => {
    const { rerender } = render(<JsonView data-testid="v" value={{ a: 1 }} />);
    expect(screen.getByTestId('v').style.border).not.toBe('');

    rerender(<JsonView data-testid="v" value={{ a: 1 }} plain />);
    expect(screen.getByTestId('v').style.border).toBe('');
  });

  it('does not scroll on its own when maxHeight is null', () => {
    render(<JsonView data-testid="v" value={{ a: 1 }} maxHeight={null} />);
    const view = screen.getByTestId('v');
    expect(view.style.overflow).toBe('');
    expect(view.style.maxHeight).toBe('');
  });
});

describe('tryParseJson', () => {
  it('parses objects and arrays', () => {
    expect(tryParseJson('{"a":1}')).toEqual({ value: { a: 1 } });
    expect(tryParseJson('  [1,2] ')).toEqual({ value: [1, 2] });
  });

  it('declines bare scalars, which a tree would only add chrome to', () => {
    expect(tryParseJson('42')).toBeUndefined();
    expect(tryParseJson('"ok"')).toBeUndefined();
    expect(tryParseJson('true')).toBeUndefined();
  });

  it('declines anything that is not JSON', () => {
    expect(tryParseJson('')).toBeUndefined();
    expect(tryParseJson('Rebalanced the shards.')).toBeUndefined();
    // Looks like an object but is not parseable — must not throw.
    expect(tryParseJson('{ not json')).toBeUndefined();
  });
});
