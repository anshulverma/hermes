import { describe, it, expect } from 'vitest';
import {
  reductionHeadline,
  reductionFacts,
  reductionProse,
  awaitsDecision,
  primaryPath,
  splitProse,
  primaryItems,
  factTone,
  verdictTone,
} from './reduction';

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

describe('awaitsDecision', () => {
  const base = {
    id: 1, run_id: 'r', phase: 'work', kind: 'k', review_state: 'pending',
    json: {}, member_ticket_ids: [], member_tickets: [],
  };

  it('is true only when a pending reduction is holding a ticket for a human', () => {
    expect(
      awaitsDecision({
        ...base,
        member_tickets: [{ id: 't1', state: 'needs-human', phase: 'work' }],
      }),
    ).toBe(true);
  });

  it('is false when the reduction gates nothing', () => {
    // Every reduction a research run emits is an output, not a decision: it
    // routes no ticket to a human, so accepting it would settle nothing.
    expect(awaitsDecision(base)).toBe(false);
    expect(
      awaitsDecision({ ...base, member_tickets: [{ id: 't1', state: 'done', phase: 'work' }] }),
    ).toBe(false);
  });

  it('is false once the decision has been made', () => {
    const held = [{ id: 't1', state: 'needs-human', phase: 'work' }];
    expect(awaitsDecision({ ...base, review_state: 'accepted', member_tickets: held })).toBe(false);
    expect(awaitsDecision({ ...base, review_state: 'rejected', member_tickets: held })).toBe(false);
    expect(awaitsDecision({ ...base, review_state: 'superseded', member_tickets: held })).toBe(false);
  });

  it('accepts either spelling of the state', () => {
    // The engine says needs_human; the UI normalises to needs-human. A queue
    // that silently empties because of an underscore is the worst failure here.
    expect(
      awaitsDecision({ ...base, member_tickets: [{ id: 't', state: 'needs_human', phase: 'w' }] }),
    ).toBe(true);
  });
});

describe('primaryPath — telling what the run produced from what it was given', () => {
  it('takes the payload key from the kind', () => {
    // A card that leads with `item.context` leads with the material hermes fed
    // the agent, not with anything the agent concluded.
    expect(primaryPath(itemAnalyses, 'item_analyses')).toBe('analyses');
    expect(primaryPath(diffAnalyses, 'diff_analyses')).toBe('analyses');
    expect(primaryPath(itemSyntheses, 'item_syntheses')).toBe('syntheses');
    expect(primaryPath(researchReport, 'research_report')).toBe('report');
  });

  it('matches the whole kind when the document uses it verbatim', () => {
    expect(primaryPath({ root_causes: ['x'] }, 'root_causes')).toBe('root_causes');
  });

  it('is null when the kind names nothing in the document', () => {
    expect(primaryPath({ a: 1 }, 'something_else')).toBeNull();
  });

  it('survives a document that is not an object', () => {
    expect(primaryPath(null as any, 'k')).toBeNull();
  });
});

describe('splitProse — the conclusion first, the rest out of the way', () => {
  it('separates what the agent produced from what it was given', () => {
    const doc = {
      item: { id: 'ITEM-1', title: 't', context: 'INPUT '.repeat(80) },
      analyses: [{ agent: 'claude', analysis: 'CONCLUSION '.repeat(80) }],
    };

    const { primary, secondary } = splitProse(doc, 'item_analyses');

    expect(primary.map((p) => p.path)).toEqual(['analyses[0].analysis']);
    expect(secondary.map((p) => p.path)).toEqual(['item.context']);
  });

  it('keeps every agent analysis in the primary group', () => {
    const doc = {
      analyses: [
        { agent: 'claude', analysis: 'a'.repeat(300) },
        { agent: 'codex', analysis: 'b'.repeat(300) },
      ],
    };

    expect(splitProse(doc, 'item_analyses').primary).toHaveLength(2);
  });

  it('puts everything in primary when the kind names nothing', () => {
    const doc = { blob: 'x'.repeat(300) };

    const { primary, secondary } = splitProse(doc, 'unknown_kind');

    expect(primary).toHaveLength(1);
    expect(secondary).toHaveLength(0);
  });

  it('loses nothing: every prose leaf lands in one group or the other', () => {
    const doc = {
      item: { context: 'i'.repeat(300) },
      analyses: [{ analysis: 'a'.repeat(300) }],
      notes: 'n'.repeat(300),
    };

    const { primary, secondary } = splitProse(doc, 'item_analyses');

    expect(primary.length + secondary.length).toBe(reductionProse(doc).length);
  });
});

describe('reductionHeadline — finding a name in prose', () => {
  it('finds a heading that is not on the first line', () => {
    // A real report opens with a sentence of preamble and only then a heading;
    // looking at line 1 alone fell back to the bare kind, so the card that
    // mattered most was the one that said least.
    const doc = {
      report: 'All 17 ledgers recovered and read.\n\n# Review batch: 17 diffs\n\nbody'.padEnd(300, '.'),
    };

    expect(reductionHeadline(doc, 'research_report')).toBe('Review batch: 17 diffs');
  });

  it('falls back to the opening sentence when there is no heading at all', () => {
    const doc = { synthesis: `Merging the single analysis into one account. ${'x'.repeat(300)}` };

    expect(reductionHeadline(doc, 'item_syntheses')).toBe(
      'Merging the single analysis into one account.',
    );
  });

  it('does not go hunting past the top of a long document', () => {
    const body = `${'filler line\n'.repeat(200)}# Buried heading\n`;

    expect(reductionHeadline({ report: body }, 'research_report')).not.toBe('Buried heading');
  });

  it('still falls back to the kind when prose yields nothing usable', () => {
    expect(reductionHeadline({ blob: '#'.repeat(400) }, 'k')).toBe('k');
  });
});

describe('primaryItems — a per-item payload as rows', () => {
  it('turns a list payload into one labelled entry per element', () => {
    const doc = {
      syntheses: [
        { item_id: 'ITEM-1', ticket_id: 'r/t-1', synthesis: 'a'.repeat(300) },
        { item_id: 'ITEM-2', ticket_id: 'r/t-2', synthesis: 'b'.repeat(300) },
      ],
    };

    const items = primaryItems(doc, 'item_syntheses');

    expect(items).toHaveLength(2);
    expect(items[0].label).toBe('ITEM-1');
    expect(items[0].text).toContain('a');
  });

  it('labels by agent when that is what distinguishes the entries', () => {
    const doc = {
      analyses: [
        { agent: 'claude', analysis: 'a'.repeat(300) },
        { agent: 'codex', analysis: 'b'.repeat(300) },
      ],
    };

    expect(primaryItems(doc, 'item_analyses').map((i) => i.label)).toEqual(['claude', 'codex']);
  });

  it('is empty when the payload is a single body rather than a list', () => {
    expect(primaryItems({ report: 'x'.repeat(300) }, 'research_report')).toEqual([]);
  });

  it('is empty when the kind names nothing', () => {
    expect(primaryItems({ a: 1 }, 'unknown')).toEqual([]);
  });

  it('skips entries that carry no prose', () => {
    const doc = { syntheses: [{ item_id: 'ITEM-1', synthesis: '' }, { item_id: 'ITEM-2' }] };
    expect(primaryItems(doc, 'item_syntheses')).toEqual([]);
  });
});

describe('factTone — colour only where the data actually says something', () => {
  it('flags a failure as a failure', () => {
    expect(factTone('failed_agents', 'claude')).toBe('danger');
    expect(factTone('status', 'error')).toBe('danger');
  });

  it('marks a clean status as clean', () => {
    expect(factTone('status', 'ok')).toBe('ok');
    expect(factTone('succeeded_agents', 'claude')).toBe('ok');
  });

  it('says nothing about a fact that carries no judgement', () => {
    // Inventing a colour for `item_count` or a ticket id would be decoration
    // pretending to be information.
    expect(factTone('item_count', '17')).toBeNull();
    expect(factTone('ticket_id', 'run-5/35-report')).toBeNull();
    expect(factTone('item.id', 'ITEM-1')).toBeNull();
  });

  it('does not call an empty failure list a failure', () => {
    expect(factTone('failed_agents', '')).toBeNull();
    expect(factTone('failed_agents', '0 items')).toBeNull();
  });
});

describe('primaryItems — carrying a stated verdict to the row', () => {
  it('carries the verdict and headline a synthesis stated', () => {
    const doc = {
      syntheses: [
        { item_id: 'ITEM-1', synthesis: 'a'.repeat(300), verdict: 'blocking', headline: 'Tier leaks' },
      ],
    };

    const [row] = primaryItems(doc, 'item_syntheses');

    expect(row.verdict).toBe('blocking');
    expect(row.headline).toBe('Tier leaks');
  });

  it('reports an unstated verdict as unstated, not as clean', () => {
    const doc = { syntheses: [{ item_id: 'ITEM-1', synthesis: 'a'.repeat(300), verdict: null }] };

    expect(primaryItems(doc, 'item_syntheses')[0].verdict).toBeNull();
  });

  it('sorts worst first, so the three that matter are not below fourteen that do not', () => {
    const doc = {
      syntheses: [
        { item_id: 'A', synthesis: 'a'.repeat(300), verdict: 'clean' },
        { item_id: 'B', synthesis: 'b'.repeat(300), verdict: null },
        { item_id: 'C', synthesis: 'c'.repeat(300), verdict: 'blocking' },
        { item_id: 'D', synthesis: 'd'.repeat(300), verdict: 'needs-discussion' },
      ],
    };

    expect(primaryItems(doc, 'item_syntheses').map((r) => r.label)).toEqual(['C', 'D', 'A', 'B']);
  });

  it('keeps the given order when nothing stated a verdict', () => {
    const doc = {
      syntheses: [
        { item_id: 'A', synthesis: 'a'.repeat(300) },
        { item_id: 'B', synthesis: 'b'.repeat(300) },
      ],
    };

    expect(primaryItems(doc, 'item_syntheses').map((r) => r.label)).toEqual(['A', 'B']);
  });
});

describe('verdictTone', () => {
  it('maps the vocabulary to severity', () => {
    expect(verdictTone('blocking')).toBe('danger');
    expect(verdictTone('needs-discussion')).toBe('attention');
    expect(verdictTone('clean')).toBe('ok');
  });

  it('gives an unstated verdict no colour at all', () => {
    expect(verdictTone(null)).toBeNull();
    expect(verdictTone('whatever-the-agent-invented')).toBeNull();
  });
});

describe('primaryItems — a short write-up is still a write-up', () => {
  it('keeps an entry whose prose is brief', () => {
    // The 200-character floor is for deciding which leaf of a document is
    // content. Applied to per-item entries it silently drops exactly the
    // concise answers the verdict contract is trying to encourage.
    const doc = {
      syntheses: [{ item_id: 'ITEM-1', synthesis: 'Nothing to raise.', verdict: 'clean' }],
    };

    const rows = primaryItems(doc, 'item_syntheses');

    expect(rows).toHaveLength(1);
    expect(rows[0].text).toBe('Nothing to raise.');
  });

  it('picks the body over the labels around it', () => {
    const doc = {
      syntheses: [
        { item_id: 'ITEM-1', ticket_id: 'r/t-1', verdict: 'clean', synthesis: 'The body.' },
      ],
    };

    expect(primaryItems(doc, 'item_syntheses')[0].text).toBe('The body.');
  });

  it('still drops an entry with no prose at all', () => {
    const doc = { syntheses: [{ item_id: 'ITEM-1', verdict: 'clean' }] };

    expect(primaryItems(doc, 'item_syntheses')).toEqual([]);
  });
});
