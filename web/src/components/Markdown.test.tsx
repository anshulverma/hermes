import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import Markdown from './Markdown';

describe('Markdown', () => {
  it('renders headings as text, not literal hashes', () => {
    render(<Markdown data-testid="md">{'## Findings\n\nAll clear.'}</Markdown>);

    const md = screen.getByTestId('md');
    expect(md).toHaveTextContent('Findings');
    expect(md.textContent).not.toContain('##');
  });

  it('renders bullets as a list, not literal dashes', () => {
    render(<Markdown data-testid="md">{'- one\n- two\n'}</Markdown>);

    expect(screen.getByTestId('md').querySelectorAll('li')).toHaveLength(2);
    expect(screen.getByTestId('md').textContent).not.toContain('- one');
  });

  it('renders emphasis as elements rather than asterisks', () => {
    render(<Markdown data-testid="md">{'**bold** and *italic*'}</Markdown>);

    const md = screen.getByTestId('md');
    expect(md.querySelector('strong')).toHaveTextContent('bold');
    expect(md.querySelector('em')).toHaveTextContent('italic');
    expect(md.textContent).not.toContain('**');
  });

  it('renders a fenced block as preformatted code, keeping its whitespace', () => {
    render(<Markdown data-testid="md">{'```py\ndef f():\n    return 1\n```'}</Markdown>);

    const pre = screen.getByTestId('md').querySelector('pre');
    expect(pre).not.toBeNull();
    expect(pre?.textContent).toContain('    return 1');
  });

  it('renders GFM tables', () => {
    render(
      <Markdown data-testid="md">{'| a | b |\n| - | - |\n| 1 | 2 |'}</Markdown>,
    );

    const md = screen.getByTestId('md');
    expect(md.querySelector('table')).not.toBeNull();
    expect(md.querySelectorAll('th')).toHaveLength(2);
  });

  it('opens links in a new tab without leaking the referrer', () => {
    render(<Markdown data-testid="md">{'[docs](https://example.com)'}</Markdown>);

    const link = screen.getByText('docs');
    expect(link).toHaveAttribute('href', 'https://example.com');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link.getAttribute('rel')).toContain('noreferrer');
  });

  it('does not render raw HTML, since agent output is untrusted', () => {
    render(<Markdown data-testid="md">{'<img src=x onerror="alert(1)">done'}</Markdown>);

    const md = screen.getByTestId('md');
    expect(md.querySelector('img')).toBeNull();
    expect(md).toHaveTextContent('done');
  });

  it('does not scroll on its own by default', () => {
    render(<Markdown data-testid="md">text</Markdown>);
    const md = screen.getByTestId('md');
    expect(md.style.maxHeight).toBe('');
    expect(md.style.overflowY).toBe('');
  });

  it('bounds its height only when asked', () => {
    render(
      <Markdown data-testid="md" maxHeight={120}>
        text
      </Markdown>,
    );
    const md = screen.getByTestId('md');
    expect(md.style.maxHeight).toBe('120px');
    expect(md.style.overflowY).toBe('auto');
  });
});
