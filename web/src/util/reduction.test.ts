import { describe, it, expect } from 'vitest';
import { reductionHeadline, reductionFacts, reductionProse } from './reduction';

// The four reduction shapes actually in the database. None of them has a
// top-level `title`, which is the only thing the findings list used to render —
// so every card read "Untitled reduction" and none showed its content.
const itemAnalyses = {
  item: { id: 'ITEM-101', title: 'Update the module overview', context: 'Phase…' },
  analyses: [{ agent: 'claude', analysis: '## Intent\nThe change does X.\n'.repeat(20) }],
  succeeded_agents: ['claude'],
  failed_agents: [],
  status: 'ok',
};

const diffAnalyses = {
  diff: { number: 'ITEM-102', title: 'demo README: plainer wording', repository: 'main-repo' },
  analyses: [{ agent: 'codex', analysis: 'Long analysis body '.repeat(30) }],
  succeeded_agents: ['codex'],
  failed_agents: ['claude'],
  status: 'ok',
};

const researchReport = {
  report: '# Report: Recent Documentation Work\n\n## Overview\n\nThis covers one landed diff.\n'.repeat(5),
  ticket_id: 'run-9/report-0',
};

const itemSyntheses = {
  syntheses: [{ ticket_id: 'run-9/synthesize-1', item_id: 'ITEM-102', synthesis: 'Merged view '.repeat(40) }],
  item_count: 1,
};

describe('reductionHeadline', () => {
  it('prefers a nested title over nothing', () => {
    expect(reductionHeadline(itemAnalyses, 'item_analyses')).toBe('Update the module overview');
    expect(reductionHeadline(diffAnalyses, 'diff_analyses')).toBe('demo README: plainer wording');
  });

  it('takes a report headline from its first markdown heading', () => {
    expect(reductionHeadline(researchReport, 'research_report')).toBe(
      'Report: Recent Documentation Work',
    );
  });

  it('prefers a top-level title when the document has one', () => {
    expect(reductionHeadline({ title: 'Explicit', item: { title: 'Nested' } }, 'k')).toBe('Explicit');
  });

  it('falls back to the kind rather than inventing a name', () => {
    // A document with no title anywhere still has to be told apart from its
    // neighbours — by its facts and content, not by a fake headline.
    expect(reductionHeadline(itemSyntheses, 'item_syntheses')).toBe('item_syntheses');
  });

  it('never returns a wall of prose as a headline', () => {
    const h = reductionHeadline({ blob: 'x'.repeat(5000) }, 'k');
    expect(h.length).toBeLessThan(200);
  });

  it('survives a document that is not an object', () => {
    expect(reductionHeadline(null as any, 'k')).toBe('k');
    expect(reductionHeadline([1, 2] as any, 'k')).toBe('k');
  });
});

describe('reductionFacts', () => {
  it('surfaces the scalars that say what happened', () => {
    const facts = reductionFacts(itemAnalyses);
    expect(facts).toContainEqual({ key: 'status', value: 'ok' });
    expect(facts).toContainEqual({ key: 'item.id', value: 'ITEM-101' });
  });

  it('reports which agents succeeded and which failed', () => {
    const facts = reductionFacts(diffAnalyses);
    expect(facts).toContainEqual({ key: 'succeeded_agents', value: 'codex' });
    expect(facts).toContainEqual({ key: 'failed_agents', value: 'claude' });
  });

  it('counts a list rather than printing it when it is long', () => {
    const facts = reductionFacts({ items: Array.from({ length: 17 }, (_, i) => `x${i}`) });
    expect(facts).toContainEqual({ key: 'items', value: '17 items' });
  });

  it('counts one thing as one item, not "1 items"', () => {
    const facts = reductionFacts({ analyses: [{ agent: 'claude', analysis: 'x'.repeat(300) }] });
    expect(facts).toContainEqual({ key: 'analyses', value: '1 item' });
  });

  it('leaves prose out of the facts strip', () => {
    const keys = reductionFacts(researchReport).map((f) => f.key);
    expect(keys).not.toContain('report');
  });

  it('survives a document that is not an object', () => {
    expect(reductionFacts(null as any)).toEqual([]);
  });
});

describe('reductionProse', () => {
  it('finds the report body', () => {
    const prose = reductionProse(researchReport);
    expect(prose).toHaveLength(1);
    expect(prose[0].path).toBe('report');
    expect(prose[0].text).toContain('# Report');
  });

  it('finds one entry per agent analysis, labelled by who wrote it', () => {
    const prose = reductionProse(itemAnalyses);
    expect(prose).toHaveLength(1);
    expect(prose[0].path).toBe('analyses[0].analysis');
  });

  it('finds a synthesis nested in a list', () => {
    const prose = reductionProse(itemSyntheses);
    expect(prose[0].path).toBe('syntheses[0].synthesis');
  });

  it('ignores short strings, which are labels not content', () => {
    const prose = reductionProse({ status: 'ok', id: 'D1', note: 'fine' });
    expect(prose).toEqual([]);
  });

  it('survives a document that is not an object', () => {
    expect(reductionProse(null as any)).toEqual([]);
  });

  it('does not recurse forever on a deep document', () => {
    let deep: any = { text: 'y'.repeat(400) };
    for (let i = 0; i < 50; i++) deep = { nested: deep };
    expect(() => reductionProse(deep)).not.toThrow();
  });
});
