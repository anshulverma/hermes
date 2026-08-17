import { describe, it, expect } from 'vitest';
import { markdownSections, firstLine } from './prose';

const report = `All 17 ledgers recovered and read. Every line below traces to those.

---

# Review batch: 17 diffs

**Corpus.** 17 diffs, all reviewed.

## Theme A — the launcher stack

Body of theme A.

## Theme B — the warmup stack

Body of theme B.

## Loose ends

Two things unresolved.
`;

describe('markdownSections', () => {
  it('keeps the opening prose as the intro', () => {
    const { intro } = markdownSections(report);
    expect(intro).toContain('All 17 ledgers recovered');
    expect(intro).not.toContain('Theme A');
  });

  it('splits the body into its headed sections', () => {
    const { sections } = markdownSections(report);
    expect(sections.map((s) => s.title)).toEqual([
      'Review batch: 17 diffs',
      'Theme A — the launcher stack',
      'Theme B — the warmup stack',
      'Loose ends',
    ]);
  });

  it('carries each section its own body', () => {
    const { sections } = markdownSections(report);
    const themeA = sections.find((s) => s.title.startsWith('Theme A'))!;
    expect(themeA.body).toContain('Body of theme A');
    expect(themeA.body).not.toContain('Body of theme B');
  });

  it('reports a document with no headings as all intro', () => {
    const { intro, sections } = markdownSections('just a paragraph.\n\nand another.');
    expect(sections).toEqual([]);
    expect(intro).toContain('just a paragraph');
  });

  it('ignores a # inside a fenced code block', () => {
    // Otherwise a shell comment becomes a section and the outline is nonsense.
    const text = 'intro\n\n```bash\n# not a heading\necho hi\n```\n\n## Real heading\n\nbody';
    const { sections } = markdownSections(text);
    expect(sections.map((s) => s.title)).toEqual(['Real heading']);
  });

  it('survives empty input', () => {
    expect(markdownSections('')).toEqual({ intro: '', sections: [] });
  });
});

describe('firstLine', () => {
  it('takes the first heading when there is one', () => {
    expect(firstLine('# D1 — merged account\n\nbody')).toBe('D1 — merged account');
  });

  it('falls back to the first non-empty line', () => {
    expect(firstLine('Merging the single analysis.\n\nmore')).toBe('Merging the single analysis.');
  });

  it('skips a horizontal rule', () => {
    expect(firstLine('---\n\n# Real title')).toBe('Real title');
  });

  it('is empty for empty input', () => {
    expect(firstLine('')).toBe('');
  });
});
