/**
 * The committee view, against the first live run's own data.
 *
 * The view's source lives in the playbook package because the playbook ships
 * it; the test lives here because vitest's root is `web/` and a spec outside it
 * cannot resolve `@testing-library/react`.
 *
 * `../ds` is imported for its side effect: it sets the design-system namespace
 * on `window`, which is how the view reads Card, Badge and EmptyState in the
 * browser too.
 */
import '../ds';
import { useState } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach, onTestFinished } from 'vitest';
import { setToken, clearToken } from '../api/auth';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import CommitteeView from '../../../playbooks/committee/view/src/CommitteeView';
import { run2, midRun, edgeTurns } from '../../../playbooks/committee/view/src/run2.fixture';
import {
  selectingData,
  seatedData,
  fallbackData,
  cardData,
  lostData,
  seatedWithTurnsData,
} from '../../../playbooks/committee/view/src/selection.fixture';
import type { CommitteeData, Entry, Evaluation } from '../../../playbooks/committee/view/src/CommitteeView';
import DocumentHistory, {
  diffLines,
  splitRows,
  type DiffMode,
  type DiffRow,
  type DocumentBlock,
  type StepId,
} from '../../../playbooks/committee/view/src/Diff';
import Verdict from '../../../playbooks/committee/view/src/Verdict';
import { violationText } from '../../../playbooks/committee/view/src/Voice';
import { imageUrl } from '../../../playbooks/committee/view/src/host';

const noop = () => {};

// Every mount of the whole view mounts <Stamp>, which fetches on mount. With no
// stub the lookup rejects (Node's fetch cannot parse a relative URL) and the
// catch writes state outside act() — 21 warnings vitest's console interception
// swallows, so the suite only looks clean. The plan's Step 18 prescribed this
// stub and it was never added. A promise that never settles is the right one:
// the describes that care about the lookup install their own over the top.
beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function show(data = run2) {
  return render(<CommitteeView runId="run-2" data={data} refetch={noop} />);
}

/**
 * jsdom has no `scrollIntoView`. Stub it for one test and put the prototype
 * back when that test ends, so no later test runs against a stale spy.
 */
function stubScroll() {
  const scrolled = vi.fn();
  const had = Object.getOwnPropertyDescriptor(Element.prototype, 'scrollIntoView');
  Element.prototype.scrollIntoView = scrolled;
  onTestFinished(() => {
    if (had) Object.defineProperty(Element.prototype, 'scrollIntoView', had);
    else delete (Element.prototype as Partial<Element>).scrollIntoView;
  });
  return scrolled;
}

/** What `view_data` returns before any reduction names a file. */
const EMPTY_DOC: DocumentBlock = {
  name: null,
  captured: false,
  original: null,
  steps: [],
  final: null,
  dropped_delegation: null,
};

describe('CommitteeView timeline', () => {
  it('reads oldest-first, which is the opposite of Outputs', () => {
    const { container } = show();
    const order = [...container.querySelectorAll('[data-testid^="entry-"]')].map(
      (el) => el.getAttribute('data-testid'),
    );

    expect(order[0]).toBe('entry-1');
    expect(order[order.length - 1]).toBe('entry-20');
    expect(order).toHaveLength(20);
  });

  it('sorts by turn number even when the data arrives out of order', () => {
    const shuffled = { ...run2, timeline: [...run2.timeline].reverse() };
    const { container } = show(shuffled);
    const order = [...container.querySelectorAll('[data-testid^="entry-"]')].map(
      (el) => el.getAttribute('data-testid'),
    );

    expect(order[0]).toBe('entry-1');
    expect(order[1]).toBe('entry-2');
  });

  it('attributes every turn to its named persona and number', () => {
    show();
    const first = screen.getByTestId('entry-1');

    expect(within(first).getByText('t01')).toBeInTheDocument();
    expect(within(first).getByText('Dana Whitfield')).toBeInTheDocument();
    expect(within(first).getByText('Senior Director of Engineering')).toBeInTheDocument();
  });

  it('collapses a long turn to one line and expands it on click', () => {
    show();
    const long = screen.getByTestId('entry-16');

    expect(within(long).queryByText(/your question to me first/)).toBeNull();

    fireEvent.click(within(long).getByRole('button'));

    expect(within(long).getByText(/your question to me first/)).toBeInTheDocument();
  });

  it('opens and closes every turn at once', () => {
    show();

    fireEvent.click(screen.getByTestId('expand-all'));
    expect(screen.getByText(/your question to me first/)).toBeInTheDocument();
    expect(screen.getByTestId('expand-all')).toHaveTextContent('Collapse all');

    fireEvent.click(screen.getByTestId('expand-all'));
    expect(screen.queryByText(/your question to me first/)).toBeNull();
  });

  it('shows the chair’s ruling below the turns', () => {
    show();

    expect(screen.getByTestId('verdict-prose')).toHaveTextContent('Verdict: do not approve. Drop.');
  });
});

describe('CommitteeView badges and re-checks', () => {
  it('names what the owner asked for on the turn they asked', () => {
    show();

    expect(within(screen.getByTestId('entry-2')).getByText('delegated an edit')).toBeInTheDocument();
    expect(within(screen.getByTestId('entry-20')).getByText('moved to close')).toBeInTheDocument();
  });

  it('names the delegated edit on the turn that delegated it', () => {
    // Criterion 7's first half. Until the chair rules there is no verdict card,
    // so this row is the only place the action can appear at all.
    show();

    expect(screen.getByTestId('action-2')).toHaveTextContent(
      'Rewrite §2 "When to reach for it"',
    );
    expect(screen.queryByTestId('action-1')).toBeNull();
  });

  it('names the same edit on the delegating turn and in its re-check', () => {
    // 8.9: the timeline's `action` and the verdict's `checks[].action` are one
    // string off one run — the junior IC re-checks on turn N+1 what the owner
    // delegated on turn N. They used to be a paraphrase and the real text, so
    // the two halves of one fixture disagreed about what had been delegated.
    // Turn 17 was the visible one: its real action is the DESIGN.md correction,
    // and the fixture wrote turn 18's report of it instead.
    show();

    const delegated = screen.getByTestId('action-17').textContent!.replace('delegated: ', '');
    expect(delegated).toContain("In DESIGN.md's");
    expect(screen.getByTestId('verdict-recheck-18')).toHaveTextContent(delegated);
  });

  it('shows the re-check outcome on a delegated edit and nowhere else', () => {
    show();

    // `timeline-` prefixed: the verdict card renders its own `verdict-recheck-3`
    // for the same turn, and this component mounts that card.
    expect(screen.getByTestId('timeline-recheck-3')).toHaveTextContent('re-check: APPLIED');
    expect(screen.queryByTestId('timeline-recheck-1')).toBeNull();
  });

  it('makes a failed re-check read as a failure', () => {
    show({ ...run2, timeline: edgeTurns });

    expect(screen.getByTestId('timeline-recheck-24')).toHaveTextContent(
      're-check: DID NOT APPLY',
    );
  });

  it('badges a floor request, a signals-only turn and a missing turn', () => {
    show({ ...run2, timeline: edgeTurns });

    expect(within(screen.getByTestId('entry-21')).getByText('asked for the floor')).toBeInTheDocument();
    expect(
      within(screen.getByTestId('entry-22')).getByText('signals only, no prose'),
    ).toBeInTheDocument();
    expect(within(screen.getByTestId('entry-23')).getByText('no turn delivered')).toBeInTheDocument();
    // 8.8: the body is `thread.NO_TURN` verbatim (playbooks/committee/thread.py).
    // The fixture used to invent "the worker produced nothing", a string no run
    // can produce, right beside a signals-only stub that matched exactly.
    expect(screen.getByTestId('entry-23')).toHaveTextContent(
      'no turn delivered — the worker failed; see hermes show',
    );
  });

  it('keeps the danger colour on an undelivered turn', () => {
    // 8.5: `no_turn: 'danger'` → undefined left 18/18 green, and the comment
    // under BADGE_TONE names this exact failure as the reason the two tables
    // must stay in step.
    show({ ...run2, timeline: edgeTurns });

    const badge = within(screen.getByTestId('entry-23')).getByText('no turn delivered');
    expect(badge.getAttribute('style')).toContain('--status-danger');
  });

  it('renders an unrecognised badge slug as itself', () => {
    // 8.6: `{BADGE_LABEL[b] ?? b}` → `{BADGE_LABEL[b]}` left 18/18 green, so a
    // slug the Python grows before the TypeScript does would render as an empty
    // badge rather than as the documented "renders as itself".
    show({ ...run2, timeline: [{ ...edgeTurns[0], badges: ['brand_new_slug'] }] });

    expect(within(screen.getByTestId('entry-21')).getByText('brand_new_slug')).toBeInTheDocument();
  });
});

describe('CommitteeView and its host globals', () => {
  it('resolves the host Markdown at render time, not at module scope', () => {
    // 8.4: hoisting host.tsx's `window.HermesUI` read to module scope survived
    // the whole suite, against a docstring that makes render-time resolution an
    // explicit invariant. `../ds` publishes HermesUI before this module
    // evaluates, so a hoisted read captures the real component and never sees
    // the one installed here.
    const real = (window as any).HermesUI;
    (window as any).HermesUI = {
      ...real,
      Markdown: ({ children }: { children: string }) => <div>HOST-MARKDOWN:{children}</div>,
    };
    try {
      show();
      fireEvent.click(screen.getByTestId('expand-all'));

      expect(screen.getAllByText(/HOST-MARKDOWN/).length).toBeGreaterThan(0);
    } finally {
      (window as any).HermesUI = real;
    }
  });

  it('degrades to unstyled rather than throwing when the design system is gone', () => {
    // WB-m10: `ds()` destructured the namespace with no guard, while the host's
    // getComponent warns and returns `() => null` and host.tsx falls back to
    // preformatted text. A throw here lands in PlaybookView's error boundary,
    // which is set once and never cleared — the pane is red for the session.
    const w = window as any;
    const real = w.MonoDarkDashDesignSystem_66fdfe;
    const compat = w.DSNS;
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    delete w.MonoDarkDashDesignSystem_66fdfe;
    delete w.DSNS;
    try {
      expect(() => show()).not.toThrow();
      expect(screen.getByTestId('entry-1')).toBeInTheDocument();
      expect(warn).toHaveBeenCalled();
    } finally {
      w.MonoDarkDashDesignSystem_66fdfe = real;
      w.DSNS = compat;
      warn.mockRestore();
    }
  });
});

describe('CommitteeView progress', () => {
  it('says why a finished meeting ended', () => {
    show();

    expect(screen.getByTestId('turn-count')).toHaveTextContent('turn 20 of 20');
    expect(screen.getByTestId('ended-reason')).toHaveTextContent(
      'Ended: owner closed. The owner moved to close and the chair ruled.',
    );
  });

  // 8.3: two of the four notes were asserted nowhere — replacing `queue empty`
  // or `chair turn failed` with 'XXX' left the whole suite green. Python pins
  // the four slugs; nothing pinned the sentence an operator actually reads.
  // run-2 itself ended `owner closed` (turn 20 carries `close: true`, and a
  // close outranks the cap even on the turn the cap would have stopped), so the
  // other three need an override.
  it.each([
    ['owner closed', 'The owner moved to close and the chair ruled.'],
    ['queue empty', 'Everyone who asked for the floor got it.'],
    ['turn cap', 'The meeting ran out of turns before anyone closed it.'],
    ['chair turn failed', 'The chair produced no decision, so the run ended failed.'],
  ])('reads the "%s" ending back as a sentence', (ended, note) => {
    show({ ...run2, progress: { ...run2.progress, ended } });

    expect(screen.getByTestId('ended-reason')).toHaveTextContent(`Ended: ${ended}. ${note}`);
  });

  it('shows who holds the floor and who is behind them mid-run', () => {
    show(midRun);

    // Turn 07, the TPM's own: `_floor` returns the most recent speaker, so a
    // holder who is not the last speaker is a shape the server cannot send.
    expect(screen.getByTestId('turn-count')).toHaveTextContent('turn 7 of 20');
    expect(screen.getByTestId('floor-holder')).toHaveTextContent('tpm has the floor');
    expect(screen.getByTestId('floor-queue')).toHaveTextContent('manager');
    // 8.10: not "Still in session." — `ended: null` also covers a run stopped,
    // parked or failed before the chair ruled, and `view_data` carries no run
    // status to tell them apart. The line has to say which it cannot say.
    expect(screen.getByTestId('ended-reason')).toHaveTextContent(
      'still in session or stopped before the chair ruled',
    );
  });

  it('does not paint a closed meeting with the ran-out-of-turns colour', () => {
    // 8.7 at the source. run-2 is turn 20 of 20 AND `ended: owner closed`, so
    // `turn >= cap` alone painted the bar amber directly beside the note saying
    // the owner closed it. The cap is now truthful; the colour has to follow
    // the ending, not the arithmetic.
    show();

    expect(screen.getByTestId('turn-bar').getAttribute('style')).toContain('--status-live');
  });

  it('paints a meeting that really ran out of turns amber', () => {
    show({ ...run2, progress: { ...run2.progress, ended: 'turn cap' } });

    expect(screen.getByTestId('turn-bar').getAttribute('style')).toContain('--status-attention');
  });
});

describe('CommitteeView on a run that predates it', () => {
  // WB-I3. Over the REAL run-2 capture — not the fixture, which synthesises the
  // four new keys on top — `view_data` returns `ended: null`, both artifacts
  // null, no stance on any seat and `body: ""` on all twenty turns, because
  // those keys postdate the run. Unqualified, that is four reassuring falsehoods on one
  // screen for every committee run already in the database.
  const legacyRun = {
    ...run2,
    progress: { ...run2.progress, ended: null },
    roster: run2.roster.map((p) => ({ ...p, stance: null })),
    timeline: run2.timeline.map((e) => ({ ...e, body: '' })),
    document: EMPTY_DOC,
  };

  it('does not call a run that already ruled "still in session"', () => {
    show(legacyRun);

    const ended = screen.getByTestId('ended-reason');
    expect(ended).not.toHaveTextContent('Still in session');
    expect(ended).toHaveTextContent('predates the committee view');
  });

  it('says a stance was never recorded rather than never stated', () => {
    show(legacyRun);

    expect(screen.getByTestId('stance-owner')).toHaveTextContent('stance not recorded');
    expect(screen.getByTestId('stance-owner')).not.toHaveTextContent('no stance stated');
  });

  it('does not leave twenty rows blank with no explanation', () => {
    show(legacyRun);

    expect(screen.getByTestId('entry-1')).toHaveTextContent('no prose recorded for this turn');
  });

  it('does not report an 11 KB reviewed file as never recorded', () => {
    show(legacyRun);

    const card = screen.getByTestId('diff-no-artifacts');
    expect(card).toHaveTextContent('never recorded which file the committee was handed');
    expect(card).not.toHaveTextContent('No artifact has been recorded for this run yet');
  });
});

describe('CommitteeView roster', () => {
  it('lists all nine personas with name and title', () => {
    show();

    expect(screen.getByTestId('roster-owner')).toHaveTextContent('Maya Okonkwo');
    expect(screen.getByTestId('roster-owner')).toHaveTextContent('Staff Engineer & proposal owner');
    expect(screen.getByText('Committee — 9')).toBeInTheDocument();
  });

  it('marks the floor holder, the queue and who has not spoken', () => {
    show(midRun);

    expect(screen.getByTestId('roster-tpm')).toHaveTextContent('has the floor');
    expect(screen.getByTestId('roster-manager')).toHaveTextContent('waiting to speak');
    expect(screen.getByTestId('roster-tl')).toHaveTextContent('has not spoken');
    expect(screen.getByTestId('roster-owner')).toHaveTextContent('spoke');
  });

  it('never says a seat has not spoken above its own turns', () => {
    // 8.1: the old midRun marked `junior_ic` idle while the transcript below
    // carried his turns 3 and 6 — the roster contradicting the transcript on
    // one screen, which is the exact failure this view exists to prevent.
    show(midRun);

    expect(screen.getByTestId('entry-3')).toHaveTextContent('Alex Moreau');
    expect(screen.getByTestId('roster-junior_ic')).toHaveTextContent('spoke');
    expect(screen.getByTestId('roster-junior_ic')).not.toHaveTextContent('has not spoken');
  });

  it('carries each persona their current stance', () => {
    show();

    // The LAST position, which for the owner is turn 20's drop and not the
    // defer she opened with at turn 02.
    expect(screen.getByTestId('stance-owner')).toHaveTextContent(
      'Position: drop the artifact.',
    );
    expect(screen.getByTestId('stance-owner')).not.toHaveTextContent('My position is defer');
    expect(screen.getByTestId('stance-staff_ic')).toHaveTextContent('Position: drop.');
  });

  it('carries the position a persona held at the turn shown, not a later one', () => {
    show(midRun);

    expect(screen.getByTestId('stance-owner')).toHaveTextContent('My position is defer');
    expect(screen.getByTestId('stance-tpm')).toHaveTextContent('the deferral needs an expiry date');
    // Turn 13 has not happened yet at turn 07.
    expect(screen.getByTestId('stance-tl')).toHaveTextContent('no stance stated');
  });

  it('shows a persona who stated no stance as having none, not as neutral', () => {
    // `junior_ic` is the only seat in run-2 that filed no position — the tpm,
    // whom this was anchored on, said "My position is defer" at turn 07.
    show();

    expect(screen.getByTestId('stance-junior_ic')).toHaveTextContent('no stance stated');
    expect(screen.getByTestId('stance-junior_ic')).not.toHaveTextContent('neutral');
  });
});

describe('CommitteeView with nothing yet', () => {
  it('says so rather than rendering empty furniture', () => {
    // The real shape of "nothing yet": `view_data` in phase `open` returns all
    // nine roster rows (they come off cast.CAST, not off the reductions), an
    // empty timeline, and BOTH artifacts null. The timeline is the only field
    // that is actually empty, so it is the only one the guard may test — and
    // the null artifacts are why the guard has to fire, because the sections
    // below dereference them.
    show({
      ...run2,
      timeline: [],
      verdict: null,
      document: EMPTY_DOC,
    });

    expect(screen.getByText('Nothing said yet')).toBeInTheDocument();
    expect(screen.queryByTestId('committee-view')).toBeNull();
    expect(screen.queryByTestId('doc-stepper')).toBeNull();
  });

  it('shows the original while the first member is still speaking, once open kept it', () => {
    // `open` wrote doc/00-original before any turn settled, and t01 can run
    // for an hour: the document under review is readable from the start.
    vi.stubGlobal('fetch', vi.fn((u: string) =>
      String(u).includes('/view/artifact') ? ok({ text: '# Proposal\n\nold clause\n' }) : new Promise(() => {}),
    ));
    show({
      ...run2,
      timeline: [],
      verdict: null,
      document: { ...DOC, steps: [], final: null },
    });

    expect(screen.getByText('Nothing said yet')).toBeInTheDocument();
    expect(screen.getByText('Document — federation-future.md · no edits')).toBeInTheDocument();
    expect(screen.getByTestId('step-original')).toHaveAttribute('aria-current', 'step');
    expect(screen.getByTestId('doc-no-edits')).toBeInTheDocument();
  });

  it('keeps the document off the Metrics tab, which draws only its own section', () => {
    render(
      <CommitteeView
        runId="run-2"
        data={{ ...run2, timeline: [], verdict: null, document: { ...DOC, steps: [], final: null } }}
        refetch={noop}
        variant="metrics"
      />,
    );
    expect(screen.getByText('Nothing said yet')).toBeInTheDocument();
    expect(screen.queryByTestId('doc-stepper')).toBeNull();
  });
});

describe('diffLines', () => {
  it('reports identical text as all-same', () => {
    expect(diffLines('a\nb\nc', 'a\nb\nc')).toEqual([
      { kind: 'same', text: 'a' },
      { kind: 'same', text: 'b' },
      { kind: 'same', text: 'c' },
    ]);
  });

  it('reports a changed line as a removal followed by an addition', () => {
    expect(diffLines('a\nb\nc', 'a\nB\nc')).toEqual([
      { kind: 'same', text: 'a' },
      { kind: 'del', text: 'b' },
      { kind: 'add', text: 'B' },
      { kind: 'same', text: 'c' },
    ]);
  });

  it('reports a pure insertion without inventing a removal', () => {
    expect(diffLines('a\nc', 'a\nb\nc')).toEqual([
      { kind: 'same', text: 'a' },
      { kind: 'add', text: 'b' },
      { kind: 'same', text: 'c' },
    ]);
  });

  it('keeps a long shared prefix out of the changed region', () => {
    const shared = Array.from({ length: 50 }, (_, i) => `line ${i}`).join('\n');
    const rows = diffLines(`${shared}\ntail`, `${shared}\nTAIL`);
    expect(rows.filter((r) => r.kind === 'same')).toHaveLength(50);
    expect(rows.filter((r) => r.kind === 'del')).toEqual([{ kind: 'del', text: 'tail' }]);
    expect(rows.filter((r) => r.kind === 'add')).toEqual([{ kind: 'add', text: 'TAIL' }]);
  });
});

/** Trimmed from the real run-2 decision reduction. */
const VERDICT_TEXT = [
  '# Decision — Hermes federation layer',
  '',
  '## Verdict: do not approve. Drop.',
  '',
  'I am ruling against my own turn-01 position, and I will say why in the record.',
].join('\n');

const VERDICT = {
  text: VERDICT_TEXT,
  // What `view._verdict` sends beside it; the card renders the prose from this.
  segments: [{ kind: 'text' as const, text: VERDICT_TEXT }],
  checks: [
    { turn: 3, action: 'Rewrite §2 "When to reach for it"', verified: true },
    { turn: 6, action: 'Rewrite §14.1 — delete the batch-submit claim', verified: true },
    { turn: 21, action: 'Fold §9 into §8', verified: false },
  ],
  artifact_intact: true,
  dropped_delegation: null as string | null,
  dropped_floor_requests: [] as string[],
};

const DECISION_ROW = {
  id: 21,
  run_id: 'run-2',
  phase: 'decision',
  kind: 'decision',
  json: { delivered: true },
  review_state: 'pending',
  member_ticket_ids: [],
  member_tickets: [],
};

function ok(body: unknown) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
}

describe('Verdict', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    // Never settles. These tests are about what the card says, not about the
    // stamp lookup, and a lookup that resolves after a synchronous test has
    // ended writes state outside act(). `not.toHaveBeenCalled()` still works.
    fetchMock = vi.fn(() => new Promise(() => {}));
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('says the verdict is a simulation, not an approval', () => {
    render(<Verdict runId="run-2" verdict={VERDICT} />);
    expect(screen.getByTestId('verdict-simulation')).toHaveTextContent(
      'not an approval, not a sign-off, and carries no authority',
    );
    expect(screen.getByTestId('verdict-simulation')).toHaveTextContent(
      'No repository was written to',
    );
  });

  it('names every junior-IC re-check with its outcome', () => {
    render(<Verdict runId="run-2" verdict={VERDICT} />);
    // `verdict-` prefixed: the timeline emits timeline-recheck-3 for the same
    // turn, and Step 16 mounts this card inside that component.
    expect(screen.getByTestId('verdict-recheck-3')).toHaveTextContent('APPLIED');
    expect(screen.getByTestId('verdict-recheck-3')).toHaveTextContent(
      'Rewrite §2 "When to reach for it"',
    );
    expect(screen.getByTestId('verdict-recheck-6')).toHaveTextContent('APPLIED');
    expect(screen.getByTestId('verdict-recheck-21')).toHaveTextContent('DID NOT APPLY');
  });

  it('confirms the original was re-checked and found unchanged', () => {
    render(<Verdict runId="run-2" verdict={VERDICT} />);
    expect(screen.getByTestId('artifact-intact')).toHaveTextContent(
      'Original artifact unchanged',
    );
  });

  it('reports a changed original as the failure it is', () => {
    render(<Verdict runId="run-2" verdict={{ ...VERDICT, artifact_intact: false }} />);
    expect(screen.getByTestId('artifact-intact')).toHaveTextContent(
      'CHANGED DURING THE REVIEW',
    );
  });

  it('shows a dropped delegation and dropped floor requests', () => {
    render(
      <Verdict
        runId="run-2"
        verdict={{
          ...VERDICT,
          dropped_delegation: 'Cut §5 from the spec',
          dropped_floor_requests: ['pm', 'tl'],
        }}
      />,
    );
    expect(screen.getByTestId('dropped-delegation')).toHaveTextContent('Cut §5 from the spec');
    expect(screen.getByTestId('dropped-floor-requests')).toHaveTextContent('pm, tl');
  });

  it('keeps the chair’s ruling on screen rather than behind a click', () => {
    render(<Verdict runId="run-2" verdict={VERDICT} />);
    const prose = screen.getByTestId('verdict-prose');
    expect(prose).toHaveTextContent('Verdict: do not approve. Drop.');
    expect(prose.closest('details')).toHaveAttribute('open');
  });

  it('says NOT CHECKED when a re-check carries no outcome', () => {
    // 9.4 / WB-m2, resolved by keeping the branch rather than narrowing the
    // type: `view.py:_verdict` passes `rechecks` through with no validation
    // beyond `isinstance(c, dict)`, so a malformed or future-shaped reduction
    // reaches this card. Both two-way collapses are claims — APPLIED and DID
    // NOT APPLY are each a statement about an edit nobody measured.
    render(
      <Verdict
        runId="run-2"
        verdict={{ ...VERDICT, checks: [{ turn: 4, action: 'Fold §9 into §8', verified: null }] }}
      />,
    );
    expect(screen.getByTestId('verdict-recheck-4')).toHaveTextContent('NOT CHECKED');
    expect(screen.getByTestId('verdict-recheck-4')).not.toHaveTextContent('APPLIED');
  });

  it('says nothing was re-checked when nothing was delegated', () => {
    // WB-m4: `rechecks-none` was asserted by no test in any of the three suites.
    render(<Verdict runId="run-2" verdict={{ ...VERDICT, checks: [] }} />);
    expect(screen.getByTestId('rechecks-none')).toHaveTextContent(
      'No edit was delegated, so there was nothing to re-check',
    );
  });

  it('says there is no verdict yet, and offers no decision, mid-run', () => {
    render(<Verdict runId="run-2" verdict={null} />);
    expect(screen.getByTestId('verdict-pending')).toHaveTextContent(
      'The chair has not ruled yet',
    );
    expect(screen.queryByRole('button', { name: /accept/i })).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('Verdict accept/reject', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    // The lookup is `/api/runs/<run>/reductions`; the accept POST goes to
    // /api/reductions/21/accept, which also contains "/reductions" — matched
    // loosely, the mock answers the POST with the lookup array and the accept
    // test can never pass. So match the lookup by its `/api/runs/` prefix.
    fetchMock = vi.fn((url: string) =>
      String(url).startsWith('/api/runs/') ? ok([DECISION_ROW]) : ok({ review_state: 'accepted' }),
    );
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('finds the decision reduction through the reductions route', async () => {
    render(<Verdict runId="run-2" verdict={VERDICT} />);
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/runs/run-2/reductions',
        expect.anything(),
      ),
    );
  });

  it('is accurate about what the stamp settles', async () => {
    // Since the chair's ticket is held for review, accept_reduction settles it
    // done and the run ends done; reject settles it failed and the run fails.
    render(<Verdict runId="run-2" verdict={VERDICT} />);
    const stampNote = await screen.findByTestId('stamp-note');
    expect(stampNote).toHaveTextContent(
      'Accepting settles the chair’s ticket and ends the run done; rejecting ends it failed.',
    );
    expect(stampNote).toHaveTextContent('lands nothing and reverts nothing');
    expect(stampNote).not.toHaveTextContent('settles no tickets');
  });

  it('accepts through the existing endpoint and shows the recorded state', async () => {
    render(<Verdict runId="run-2" verdict={VERDICT} />);
    fireEvent.click(await screen.findByRole('button', { name: /accept/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/reductions/21/accept',
        expect.objectContaining({ method: 'POST' }),
      ),
    );
    expect(await screen.findByTestId('stamp-state')).toHaveTextContent('Recorded as accepted.');
  });

  it('rejects without a confirm prompt', async () => {
    fetchMock.mockImplementation((url: string) =>
      String(url).startsWith('/api/runs/') ? ok([DECISION_ROW]) : ok({ review_state: 'rejected' }),
    );
    render(<Verdict runId="run-2" verdict={VERDICT} />);
    fireEvent.click(await screen.findByRole('button', { name: /reject/i }));

    expect(await screen.findByTestId('stamp-state')).toHaveTextContent('Recorded as rejected.');
  });

  it('offers no buttons on a reduction already resolved', async () => {
    fetchMock.mockImplementation(() => ok([{ ...DECISION_ROW, review_state: 'accepted' }]));
    render(<Verdict runId="run-2" verdict={VERDICT} />);

    expect(await screen.findByTestId('stamp-state')).toHaveTextContent('Recorded as accepted.');
    expect(screen.queryByRole('button', { name: /accept/i })).toBeNull();
  });

  it('carries the bearer token on both the lookup and the stamp', async () => {
    // 9.1. `host.tsx` exists for this and nothing pinned it: replacing the
    // header builder with `return {};` left all 466 green, and on any
    // non-loopback bind the lookup and the stamp would 401 with a clean suite.
    // The existing assertions use expect.anything() and see straight through it.
    setToken('remote-typed-token');
    try {
      render(<Verdict runId="run-2" verdict={VERDICT} />);
      fireEvent.click(await screen.findByRole('button', { name: /accept/i }));

      await waitFor(() =>
        expect(fetchMock).toHaveBeenCalledWith(
          '/api/reductions/21/accept',
          expect.objectContaining({
            method: 'POST',
            headers: { Authorization: 'Bearer remote-typed-token' },
          }),
        ),
      );
      expect(fetchMock).toHaveBeenCalledWith('/api/runs/run-2/reductions', {
        headers: { Authorization: 'Bearer remote-typed-token' },
      });
    } finally {
      clearToken();
    }
  });

  it('sends no Authorization header when there is no token', async () => {
    // The loopback half: an empty object, not `Bearer null`.
    render(<Verdict runId="run-2" verdict={VERDICT} />);

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith('/api/runs/run-2/reductions', {
        headers: {},
      }),
    );
  });

  it('sends one POST for three rapid clicks', async () => {
    // 9.2. `disabled={busy}` was the only double-stamp guard: with it three
    // clicks give 1 POST, without it 3. `decide` now refuses re-entry too, so
    // the invariant does not live only in JSX.
    let release!: () => void;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    fetchMock.mockImplementation((url: string) =>
      String(url).startsWith('/api/runs/')
        ? ok([DECISION_ROW])
        : held.then(() => ({
            ok: true,
            status: 200,
            json: () => Promise.resolve({ review_state: 'accepted' }),
          })),
    );
    render(<Verdict runId="run-2" verdict={VERDICT} />);
    const accept = await screen.findByRole('button', { name: /accept/i });

    fireEvent.click(accept);
    fireEvent.click(accept);
    fireEvent.click(accept);

    expect(fetchMock.mock.calls.filter(([u]) => String(u).includes('/accept'))).toHaveLength(1);
    release();
    expect(await screen.findByTestId('stamp-state')).toHaveTextContent('Recorded as accepted.');
  });

  it('shows the state the server recorded, not the one it was asked for', async () => {
    // 9.3. Both existing stamp tests stub the server to echo the request, so an
    // optimistic card is indistinguishable from an honest one. Make them differ.
    fetchMock.mockImplementation((url: string) =>
      String(url).startsWith('/api/runs/') ? ok([DECISION_ROW]) : ok({ review_state: 'rejected' }),
    );
    render(<Verdict runId="run-2" verdict={VERDICT} />);
    fireEvent.click(await screen.findByRole('button', { name: /accept/i }));

    expect(await screen.findByTestId('stamp-state')).toHaveTextContent('Recorded as rejected.');
  });

  it('stamps the last decision reduction, the one the verdict was read from', async () => {
    // 9.5. The route returns ORDER BY id ascending and `view_data` deliberately
    // takes the LAST; `rows.find` took the first. Given two, the operator reads
    // one ruling and stamps another.
    fetchMock.mockImplementation((url: string) =>
      String(url).startsWith('/api/runs/')
        ? ok([{ ...DECISION_ROW, id: 7 }, { ...DECISION_ROW, id: 21 }])
        : ok({ review_state: 'accepted' }),
    );
    render(<Verdict runId="run-2" verdict={VERDICT} />);
    fireEvent.click(await screen.findByRole('button', { name: /accept/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith('/api/reductions/21/accept', expect.anything()),
    );
    expect(fetchMock).not.toHaveBeenCalledWith('/api/reductions/7/accept', expect.anything());
  });

  it('re-reads the review state after a stamp the server refused', async () => {
    // 9.9 and WB-m4's second orphan testid. Another operator stamped first, so
    // the POST 409s; with the lookup pinned to [runId] the card kept offering a
    // button that could only ever 409 again until the page was reloaded.
    let stamped = false;
    fetchMock.mockImplementation((url: string) => {
      if (String(url).startsWith('/api/runs/')) {
        return ok([{ ...DECISION_ROW, review_state: stamped ? 'accepted' : 'pending' }]);
      }
      stamped = true;
      return Promise.resolve({
        ok: false,
        status: 409,
        json: () => Promise.resolve({ detail: 'reduction 21 is already resolved' }),
      });
    });
    render(<Verdict runId="run-2" verdict={VERDICT} />);
    fireEvent.click(await screen.findByRole('button', { name: /accept/i }));

    expect(await screen.findByTestId('stamp-action-error')).toHaveTextContent(
      'reduction 21 is already resolved',
    );
    expect(await screen.findByTestId('stamp-state')).toHaveTextContent('Recorded as accepted.');
    expect(screen.queryByRole('button', { name: /accept/i })).toBeNull();
  });

  it('offers the buttons rather than "Recorded as ." on a stateless reply', async () => {
    // 9.8
    fetchMock.mockImplementation((url: string) =>
      String(url).startsWith('/api/runs/') ? ok([DECISION_ROW]) : ok({}),
    );
    render(<Verdict runId="run-2" verdict={VERDICT} />);
    fireEvent.click(await screen.findByRole('button', { name: /accept/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(screen.queryByTestId('stamp-state')).toBeNull();
    expect(screen.getByRole('button', { name: /accept/i })).toBeInTheDocument();
  });

  // The server stamps any pending reduction, so a button here would record a
  // ruling on a verdict the chair never delivered; the run ends failed either way.
  const expectNoStamp = async () => {
    expect(await screen.findByTestId('stamp-undelivered')).toHaveTextContent(
      'The chair delivered no verdict, so there is nothing to accept or reject.',
    );
    expect(screen.queryByRole('button', { name: /accept|reject/i })).toBeNull();
    expect(screen.queryByTestId('stamp-note')).toBeNull();
  };

  it('offers no stamp when the chair turn failed', async () => {
    fetchMock.mockImplementation(() =>
      ok([{ ...DECISION_ROW, json: { delivered: false, needs_human_ticket_ids: [], ended: 'chair turn failed' } }]),
    );
    render(<Verdict runId="run-2" verdict={VERDICT} />);
    await expectNoStamp();
  });

  it('offers no stamp when the chair retake delivered nothing', async () => {
    // The held first take is recorded unruled under decision-take2.
    fetchMock.mockImplementation(() =>
      ok([
        { ...DECISION_ROW, id: 20, kind: 'take', json: { delivered: true, kept: false } },
        { ...DECISION_ROW, id: 21, phase: 'decision-take2',
          json: { delivered: false, needs_human_ticket_ids: [], ended: 'chair retake failed' } },
      ]),
    );
    render(<Verdict runId="run-2" verdict={VERDICT} />);
    await expectNoStamp();
  });
});

/**
 * A captured document with one edit of each provenance: t03 recorded and
 * applied, t06 inferred and did not apply, t09 unknown, undelivered and never
 * re-checked. Names, stances and prose come from run-2's timeline by turn.
 */
const DOC: DocumentBlock = {
  name: 'federation-future.md',
  captured: true,
  original: { path: 'doc/00-original.md', bytes: 30 },
  steps: [
    { turn: 3, path: 'doc/t03.md', bytes: 31, delivered: true, verified: true,
      owner_turn: 2, reviewer_turn: 1, provenance: 'recorded' },
    { turn: 6, path: 'doc/t06.md', bytes: 45, delivered: true, verified: false,
      owner_turn: 5, reviewer_turn: 4, provenance: 'inferred' },
    { turn: 9, path: 'doc/t09.md', bytes: 45, delivered: false, verified: null,
      owner_turn: null, reviewer_turn: null, provenance: 'unknown' },
  ],
  final: { path: 'doc/t03.md', turn: 3, bytes: 31, ruling: 'awaiting_ruling' },
  dropped_delegation: null,
};

const TEXT: Record<string, string> = {
  'doc/00-original.md': '# Proposal\n\nold clause\ntail',
  'doc/t03.md': '# Proposal\n\nnew clause\ntail',
  'doc/t06.md': '# Proposal\n\nnew clause\nextra clause\ntail',
  'doc/t09.md': '# Proposal\n\nnew clause\nextra clause\ntail',
};

const url = (path: string) => `/api/runs/run-2/view/artifact?path=${path}`;
const pathOf = (u: string) => String(u).split('path=')[1];

/**
 * Every one of 6000 lines replaced by another: past MAX_CELLS, so 12,000
 * unified rows but 6000 side-by-side pairs. The cap tests need the two counts
 * to differ, or they cannot tell which one a cap was computed from.
 */
const replacedAll = (u: string) =>
  ok({
    text: Array.from({ length: 6000 }, (_, i) => `${pathOf(u) === 'doc/00-original.md' ? 'a' : 'b'}${i}`).join('\n'),
  });

/** The view's own wiring, minus the rest of the view: it holds the selection. */
function History({
  doc = DOC,
  start = 'original',
  intact = true,
  mode = 'unified',
  onOpenTurn = noop,
  timeline = run2.timeline,
}: {
  doc?: DocumentBlock;
  start?: StepId;
  intact?: boolean | null;
  mode?: DiffMode;
  onOpenTurn?: (n: number) => void;
  timeline?: CommitteeData['timeline'];
}) {
  const [selected, setSelected] = useState<StepId>(start);
  const [diffMode, setDiffMode] = useState<DiffMode>(mode);
  return (
    <DocumentHistory
      runId="run-2"
      document={doc}
      timeline={timeline}
      intact={intact}
      selected={selected}
      onSelect={setSelected}
      diffMode={diffMode}
      onDiffMode={setDiffMode}
      onOpenTurn={onOpenTurn}
    />
  );
}

describe('DocumentHistory', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn((u: string) => ok({ text: TEXT[pathOf(u)] }));
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  // --- the seven card states, first match wins ---

  it('says no artifact was recorded while the document names none', () => {
    render(<History doc={EMPTY_DOC} intact={null} />);
    expect(screen.getByTestId('diff-no-artifacts')).toHaveTextContent(
      'No artifact has been recorded for this run yet',
    );
    expect(screen.queryByTestId('diff-original-untouched')).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('says no snapshot is readable, claiming no cause, and fetches nothing', () => {
    render(<History doc={{ ...DOC, captured: false }} />);
    const card = screen.getByTestId('doc-not-captured');
    expect(card).toHaveTextContent(
      "No snapshot of this document is readable on the server — not the original's " +
        "(doc/00-original.md) nor any edit's — so there is nothing to step through.",
    );
    // A worker can delete doc/ on a new run too; the card must not blame the run's age.
    expect(card).not.toHaveTextContent('reduced before');
    expect(screen.queryByTestId('doc-stepper')).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('shows the original and says no edit was made when there are no steps', async () => {
    render(<History doc={{ ...DOC, steps: [], final: null }} />);
    expect(screen.getByTestId('doc-no-edits')).toHaveTextContent(
      /^No edit was made\. The original stands as it was\.$/,
    );
    expect(await screen.findByTestId('doc-markdown')).toHaveTextContent('old clause');
    expect(fetchMock).toHaveBeenCalledWith(url('doc/00-original.md'), expect.anything());
  });

  it('an unreadable step says Could not read, never No edit has been delegated yet', () => {
    const doc = { ...DOC, steps: DOC.steps.map((s) => (s.turn === 3 ? { ...s, bytes: null } : s)) };
    render(<History doc={doc} start={3} />);
    expect(screen.getByTestId('doc-unreadable')).toHaveTextContent(
      'Could not read doc/t03.md on the server.',
    );
    expect(screen.queryByText(/No edit has been delegated yet/)).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('says so about an unreadable baseline, rather than diffing against an older version', () => {
    const doc = { ...DOC, steps: DOC.steps.map((s) => (s.turn === 3 ? { ...s, bytes: null } : s)) };
    render(<History doc={doc} start={6} />);
    expect(screen.getByTestId('doc-unreadable')).toHaveTextContent(
      'Could not read doc/t03.md on the server.',
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('says Loading… while a version is on its way', () => {
    fetchMock.mockImplementation(() => new Promise(() => {}));
    render(<History start={3} />);
    expect(screen.getByTestId('doc-loading')).toHaveTextContent('Loading…');
  });

  it('reports a failed fetch with its path and the server detail', async () => {
    fetchMock.mockImplementation((u: string) =>
      pathOf(u) === 'doc/t03.md'
        ? Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ detail: 'gone' }) })
        : ok({ text: TEXT[pathOf(u)] }),
    );
    render(<History start={3} />);
    expect(await screen.findByTestId('doc-error')).toHaveTextContent('Could not load doc/t03.md: gone');
  });

  it('retries a failed version on request, rather than until a reload', async () => {
    let fails = 1;
    fetchMock.mockImplementation((u: string) =>
      pathOf(u) === 'doc/t03.md' && fails-- > 0
        ? Promise.resolve({ ok: false, status: 502, json: () => Promise.resolve({ detail: 'busy' }) })
        : ok({ text: TEXT[pathOf(u)] }),
    );
    render(<History start={3} />);
    const error = await screen.findByTestId('doc-error');
    fireEvent.click(within(error).getByTestId('doc-retry'));

    expect(await screen.findByTestId('diff-rows')).toHaveTextContent('+ new clause');
    expect(fetchMock.mock.calls.filter(([u]) => pathOf(u) === 'doc/t03.md')).toHaveLength(2);
    // Only the failed version is fetched again; the baseline stays cached.
    expect(fetchMock.mock.calls.filter(([u]) => pathOf(u) === 'doc/00-original.md')).toHaveLength(1);
  });

  it('warns when the server cut a version short at its read cap', async () => {
    fetchMock.mockImplementation((u: string) =>
      ok({ text: TEXT[pathOf(u)], truncated: pathOf(u) === 'doc/t03.md' }),
    );
    render(<History start={3} />);
    expect(await screen.findByTestId('diff-truncated')).toHaveTextContent('read cap');
  });

  // --- the invariant it leads with ---

  it('states that the original is never modified, in the past tense once checked', () => {
    render(<History intact={true} />);
    const banner = screen.getByTestId('diff-original-untouched');
    expect(banner).toHaveTextContent('The original is never modified');
    expect(banner).toHaveTextContent('federation-future.md is byte-for-byte');
    expect(banner).toHaveTextContent('Every delegated edit lands in the revised copy');
    expect(banner).toHaveTextContent('a recommendation, not a landed change');
  });

  it('does not promise byte-for-byte before a decision has re-checked it', () => {
    render(<History intact={null} />);
    const banner = screen.getByTestId('diff-original-untouched');
    expect(banner).toHaveTextContent('is meant to be byte-for-byte');
    expect(banner).not.toHaveTextContent('federation-future.md is byte-for-byte');
  });

  // --- the stepper ---

  it('lists Original, one Edit per step and Final, and opens on Original', () => {
    render(<History />);
    expect(screen.getByTestId('step-original')).toHaveTextContent('Original');
    expect(screen.getByTestId('step-3')).toHaveTextContent('Edit 1 (t03)');
    expect(screen.getByTestId('step-6')).toHaveTextContent('Edit 2 (t06)');
    expect(screen.getByTestId('step-9')).toHaveTextContent('Edit 3 (t09)');
    expect(screen.getByTestId('step-final')).toHaveTextContent('Final');
    expect(screen.getByTestId('step-original')).toHaveAttribute('aria-current', 'step');
    expect(screen.getByTestId('step-3')).not.toHaveAttribute('aria-current');
  });

  it('moves with Prev, Next and the arrow keys on the focused stepper', () => {
    render(<History />);
    expect(screen.getByTestId('step-prev')).toBeDisabled();
    fireEvent.click(screen.getByTestId('step-next'));
    expect(screen.getByTestId('step-3')).toHaveAttribute('aria-current', 'step');
    fireEvent.keyDown(screen.getByTestId('doc-stepper'), { key: 'ArrowRight' });
    expect(screen.getByTestId('step-6')).toHaveAttribute('aria-current', 'step');
    // Focus follows the selection, so a screen reader announces the new step.
    expect(document.activeElement).toBe(screen.getByTestId('step-6'));
    fireEvent.keyDown(screen.getByTestId('step-6'), { key: 'ArrowLeft' });
    expect(screen.getByTestId('step-3')).toHaveAttribute('aria-current', 'step');
    expect(document.activeElement).toBe(screen.getByTestId('step-3'));
    fireEvent.click(screen.getByTestId('step-prev'));
    expect(screen.getByTestId('step-original')).toHaveAttribute('aria-current', 'step');
  });

  it('keeps the selected step by id when a data tick appends a step', () => {
    const { rerender } = render(<History />);
    fireEvent.click(screen.getByTestId('step-6'));
    const more = {
      ...DOC,
      steps: [...DOC.steps, { ...DOC.steps[0], turn: 12, path: 'doc/t12.md' }],
    };
    rerender(<History doc={more} />);
    expect(screen.getByTestId('step-6')).toHaveAttribute('aria-current', 'step');
    expect(screen.getByTestId('step-12')).toHaveTextContent('Edit 4 (t12)');
  });

  // --- what is fetched, and when ---

  it('fetches only what the selected step shows: the previous version and its own', async () => {
    render(<History />);
    await screen.findByTestId('doc-markdown');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(url('doc/00-original.md'), expect.anything());

    fireEvent.click(screen.getByTestId('step-6'));
    await screen.findByTestId('diff-rows');
    expect(fetchMock).toHaveBeenCalledWith(url('doc/t03.md'), expect.anything());
    expect(fetchMock).toHaveBeenCalledWith(url('doc/t06.md'), expect.anything());
    expect(fetchMock).not.toHaveBeenCalledWith(url('doc/t09.md'), expect.anything());
  });

  it('fetches through the host apiGet, carrying the bearer token', async () => {
    // Every other stepper test accepts any fetch options, so a bare fetch
    // would stay green and 401 on every non-loopback bind.
    setToken('remote-typed-token');
    try {
      render(<History />);
      await screen.findByTestId('doc-markdown');
      expect(fetchMock).toHaveBeenCalledWith(url('doc/00-original.md'), {
        headers: { Authorization: 'Bearer remote-typed-token' },
      });
    } finally {
      clearToken();
    }
  });

  it('caches by path and size, and fetches a version again when its size changes', async () => {
    const { rerender } = render(<History start={3} />);
    await screen.findByTestId('diff-rows');
    expect(fetchMock).toHaveBeenCalledTimes(2);

    fireEvent.click(screen.getByTestId('step-original'));
    fireEvent.click(screen.getByTestId('step-3'));
    await screen.findByTestId('diff-rows');
    expect(fetchMock).toHaveBeenCalledTimes(2);

    const retaken = { ...DOC, steps: DOC.steps.map((s) => (s.turn === 3 ? { ...s, bytes: 99 } : s)) };
    rerender(<History doc={retaken} start={3} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(fetchMock).toHaveBeenLastCalledWith(url('doc/t03.md'), expect.anything());
  });

  // --- an edit step ---

  it('shows an edit as the diff from the previous version to this one, with APPLIED', async () => {
    render(<History start={3} />);
    const rows = await screen.findByTestId('diff-rows');
    expect(rows).toHaveTextContent('- old clause');
    expect(rows).toHaveTextContent('+ new clause');
    expect(screen.getByTestId('diff-counts')).toHaveTextContent('1 line added, 1 removed');
    expect(screen.getByTestId('step-verdict')).toHaveTextContent('re-check: APPLIED');
  });

  it('takes the verdict from verified alone and shows the diff whatever it says', async () => {
    render(<History start={6} />);
    expect(await screen.findByTestId('diff-rows')).toHaveTextContent('+ extra clause');
    expect(screen.getByTestId('step-verdict')).toHaveTextContent('DID NOT APPLY');
    // Delivered but did not apply: the junior's prose still stands. Keyed on
    // `verified` instead of `delivered`, this would say "no turn delivered".
    expect(screen.getByTestId('step-confirmed')).toHaveTextContent('Rewrote §14.1');

    fireEvent.click(screen.getByTestId('step-9'));
    expect(screen.getByTestId('step-verdict')).toHaveTextContent(/^re-check: not recorded$/);
  });

  it('says not recorded for a delivered edit whose re-check is missing, never APPLIED', () => {
    const doc = { ...DOC, steps: DOC.steps.map((s) => (s.turn === 6 ? { ...s, verified: null } : s)) };
    render(<History doc={doc} start={6} />);
    expect(screen.getByTestId('step-verdict')).toHaveTextContent(/^re-check: not recorded$/);
  });

  it('says No changes between these two versions for identical text', async () => {
    render(<History start={9} />);
    expect(await screen.findByTestId('diff-none')).toHaveTextContent(
      'No changes between these two versions.',
    );
  });

  it('names who raised it and their stance, the delegation and the confirmation, each linked', () => {
    const onOpenTurn = vi.fn();
    render(<History start={3} onOpenTurn={onOpenTurn} />);
    expect(screen.getByTestId('step-raised')).toHaveTextContent(
      'raised by Dana Whitfield — Position: defer.',
    );
    // Who delegated it and who made it, by name: the owner and the junior IC.
    expect(screen.getByTestId('step-delegated')).toHaveTextContent(
      'delegated by Maya Okonkwo: Rewrite §2 "When to reach for it"',
    );
    expect(screen.getByTestId('step-confirmed')).toHaveTextContent(
      'Alex Moreau: Rewrote §2 into two triggers',
    );
    expect(screen.queryByTestId('step-provenance')).toBeNull();

    // Announced as what it does, not as a bare "t01".
    expect(screen.getByTestId('goto-t01')).toHaveAccessibleName('Open t01 in the transcript');
    fireEvent.click(screen.getByTestId('goto-t01'));
    fireEvent.click(screen.getByTestId('goto-t02'));
    fireEvent.click(screen.getByTestId('goto-t03'));
    expect(onOpenTurn.mock.calls).toEqual([[1], [2], [3]]);
  });

  it('says a link was inferred from turn order, and when who raised it was not recorded', () => {
    const { unmount } = render(<History start={6} />);
    // On the two lines turn order inferred, not under the junior's own turn,
    // which is the one line here that is certain.
    const raised = screen.getByTestId('step-raised');
    const delegated = screen.getByTestId('step-delegated');
    expect(raised).toHaveTextContent('raised by Ruth Delgado');
    expect(within(raised).getByTestId('step-provenance')).toHaveTextContent('(inferred from turn order)');
    expect(within(delegated).getByTestId('step-provenance')).toHaveTextContent('(inferred from turn order)');
    expect(screen.getAllByTestId('step-provenance')).toHaveLength(2);

    // Unknown provenance is not inferred: it says nothing was recorded instead.
    fireEvent.click(screen.getByTestId('step-9'));
    expect(screen.queryByTestId('step-provenance')).toBeNull();
    expect(screen.getByTestId('step-raised')).toHaveTextContent('who raised this was not recorded');
    expect(screen.queryByTestId('step-delegated')).toBeNull();
    expect(screen.getByTestId('step-confirmed')).toHaveTextContent('Alex Moreau: no turn delivered');
    unmount();

    // The mark follows `provenance`, not whether a turn happens to be linked.
    const unknown = DOC.steps.map((s) => (s.turn === 6 ? { ...s, provenance: 'unknown' as const } : s));
    render(<History doc={{ ...DOC, steps: unknown }} start={6} />);
    expect(screen.getByTestId('step-delegated')).toBeInTheDocument();
    expect(screen.queryByTestId('step-provenance')).toBeNull();
  });

  it('falls back to the bare lines when the transcript has no entry for a linked turn', () => {
    const stray: DocumentBlock = {
      ...DOC,
      steps: [{ turn: 30, path: 'doc/t30.md', bytes: 31, delivered: true, verified: true,
                owner_turn: 29, reviewer_turn: 28, provenance: 'recorded' }],
    };
    const { unmount } = render(<History doc={stray} start={30} />);
    expect(screen.getByTestId('step-delegated')).toHaveTextContent(/^delegated: no action recorded t29$/);
    expect(screen.getByTestId('step-confirmed')).toHaveTextContent(/^no prose recorded for this turn t30$/);
    unmount();

    render(<History doc={{ ...stray, steps: [{ ...stray.steps[0], delivered: false }] }} start={30} />);
    expect(screen.getByTestId('step-confirmed')).toHaveTextContent(/^no turn delivered t30$/);
  });

  it("pairs a turn settled twice with its last take, the one the step's diff and verdict are", () => {
    // `view_data` keeps the last reduction per turn; so does the step context.
    const retake = { ...run2.timeline[2], body: 'Second take: rewrote §2 once more.' };
    const timeline = [...run2.timeline.slice(0, 3), retake, ...run2.timeline.slice(3)];
    render(<History start={3} timeline={timeline} />);
    expect(screen.getByTestId('step-confirmed')).toHaveTextContent(
      'Alex Moreau: Second take: rewrote §2 once more.',
    );
  });

  // --- Original and Final ---

  it('renders a whole version as markdown for a markdown file, preformatted otherwise', async () => {
    const { unmount } = render(<History />);
    // The host Markdown renders a heading as a styled block, so the `#` is gone.
    const md = await screen.findByTestId('doc-markdown');
    expect(md).toHaveTextContent('Proposal');
    expect(md).not.toHaveTextContent('# Proposal');
    unmount();

    render(<History doc={{ ...DOC, name: 'Makefile' }} />);
    expect(await screen.findByTestId('doc-plain')).toHaveTextContent('# Proposal');
  });

  it('renders a .markdown file as markdown too', async () => {
    render(<History doc={{ ...DOC, name: 'proposal.markdown' }} />);
    expect(await screen.findByTestId('doc-markdown')).not.toHaveTextContent('# Proposal');
  });

  it('never loads an image a worker wrote into the document: its alt text stands in', async () => {
    // Every version after Edit 1 is text a junior worker wrote, and a live
    // <img> would make the operator's browser fetch whatever src it names.
    fetchMock.mockImplementation(() =>
      ok({ text: '# Proposal\n\n![a tracking pixel](https://example.invalid/p.png?run=9)\n' }),
    );
    render(<History />);
    const md = await screen.findByTestId('doc-markdown');
    expect(md.querySelector('img')).toBeNull();
    expect(md).toHaveTextContent('a tracking pixel');
  });

  it('heads the Original step with what it is', () => {
    render(<History />);
    expect(screen.getByTestId('original-label')).toHaveTextContent(
      'Original — as the committee was handed it',
    );
    fireEvent.click(screen.getByTestId('step-3'));
    expect(screen.queryByTestId('original-label')).toBeNull();
  });

  it('offers the diff layout only where a diff is shown', async () => {
    render(<History />);
    expect(screen.queryByTestId('diff-mode-split')).toBeNull(); // Original: one whole version
    fireEvent.click(screen.getByTestId('step-3'));
    expect(screen.getByTestId('diff-mode-split')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('step-final'));
    expect(screen.queryByTestId('diff-mode-split')).toBeNull(); // Final, the whole version
    fireEvent.click(screen.getByTestId('final-diff-toggle'));
    expect(screen.getByTestId('diff-mode-split')).toBeInTheDocument();
  });

  it.each([
    ['in_session', 'Latest so far — no verdict yet (in session, or stopped before the chair ruled)'],
    ['awaiting_ruling', 'Proposed — awaiting your ruling'],
    ['accepted', 'Accepted'],
    ['rejected', 'Rejected'],
    ['no_ruling', 'The meeting ended without a ruling'],
  ] as const)('labels Final by the ruling: %s', (ruling, label) => {
    render(<History doc={{ ...DOC, final: { ...DOC.final!, ruling } }} start="final" />);
    expect(screen.getByTestId('final-label')).toHaveTextContent(label);
  });

  it('shows Final as the last applied edit left it, or as the original when none applied', async () => {
    const { unmount } = render(<History start="final" />);
    expect(screen.getByTestId('final-label')).toHaveTextContent('as the last applied edit (t03) left it');
    expect(await screen.findByTestId('doc-markdown')).toHaveTextContent('new clause');
    unmount();

    const none = { ...DOC, final: { path: 'doc/00-original.md', turn: null, bytes: 30, ruling: 'accepted' as const } };
    render(<History doc={none} start="final" />);
    expect(screen.getByTestId('final-label')).toHaveTextContent('no edit applied, so this is the original');
    expect(await screen.findByTestId('doc-markdown')).toHaveTextContent('old clause');
  });

  it('notes a dropped delegation under the stepper, naming its owner turn when known', () => {
    const { unmount } = render(
      <History doc={{ ...DOC, dropped_delegation: { owner_turn: 20, action: 'Fold §9 into §8' } }} />,
    );
    expect(screen.getByTestId('doc-dropped')).toHaveTextContent(
      'The turn cap dropped a delegation from t20: Fold §9 into §8',
    );
    expect(screen.queryByTestId('step-21')).toBeNull();
    unmount();

    render(<History doc={{ ...DOC, dropped_delegation: { owner_turn: null, action: 'Fold §9 into §8' } }} />);
    expect(screen.getByTestId('doc-dropped')).toHaveTextContent(
      'The turn cap dropped a delegation: Fold §9 into §8',
    );
  });

  it('notes a dropped delegation when the cap cut the first one, before any edit', () => {
    // max_turns=2 and t02 delegating: no step at all, and both lines stay true.
    render(
      <History doc={{ ...DOC, steps: [], final: null, dropped_delegation: { owner_turn: 2, action: 'x' } }} />,
    );
    expect(screen.getByTestId('doc-no-edits')).toHaveTextContent('No edit was made.');
    expect(screen.getByTestId('doc-dropped')).toHaveTextContent(
      'The turn cap dropped a delegation from t02: x',
    );
  });

  it('caps how many rows reach the DOM, and says it did', async () => {
    // `diffLines` is hard-bounded and fast; the RENDER is what does not scale.
    fetchMock.mockImplementation(replacedAll);
    render(<History start={3} />);
    const rows = await screen.findByTestId('diff-rows');
    expect(rows.children).toHaveLength(5001); // 5000 rows plus the footer
    expect(screen.getByTestId('diff-rows-capped')).toHaveTextContent('… 7000 more rows');
    expect(screen.getByTestId('diff-counts')).toHaveTextContent('6000 lines added, 6000 removed');
  });
});

describe('splitRows', () => {
  it('pairs each removal run with the addition run after it, padding the shorter side', () => {
    const row = (kind: DiffRow['kind'], text: string): DiffRow => ({ kind, text });
    const a = row('same', 'a');
    const b = row('del', 'b');
    const c = row('del', 'c');
    const B = row('add', 'B');
    const d = row('same', 'd');
    const e = row('add', 'e');
    const f = row('del', 'f');

    expect(splitRows([a, b, c, B, d, e, f])).toEqual([
      [a, a],
      [b, B],
      [c, null],
      [d, d],
      [null, e],
      [f, null],
    ]);
  });

  it('caps side-by-side rows at the same limit, counting pairs rather than lines', async () => {
    // The fixture the unified cap test says "7000 more rows" of.
    vi.stubGlobal('fetch', vi.fn(replacedAll));
    render(<History start={3} mode="split" />);
    const split = await screen.findByTestId('diff-split');
    expect(split.children).toHaveLength(10001); // 5000 rows of two cells, plus the footer
    expect(screen.getByTestId('diff-rows-capped')).toHaveTextContent('… 1000 more rows');
    vi.unstubAllGlobals();
  });
});

describe('an edit diff opens on what changed', () => {
  // The shape of a real committee edit: a couple of lines deep in a long
  // document. Unfolded, a 420px pane opened at the top shows only the title.
  const LONG = Array.from({ length: 200 }, (_, i) => `line ${i + 1}`);
  const rewrite = (n: number, lines: string[]) =>
    lines.map((l, i) => (i === n - 1 ? `${l}, rewritten` : l));
  const T03 = rewrite(150, LONG);
  const LONG_TEXT: Record<string, string> = {
    'doc/00-original.md': LONG.join('\n'),
    'doc/t03.md': T03.join('\n'),
    'doc/t06.md': rewrite(20, T03).join('\n'),
  };

  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn((u: string) => ok({ text: LONG_TEXT[pathOf(u)] })));
  });

  it('folds unchanged lines to three either side of each change, counting from the whole diff', async () => {
    render(<History start={3} />);
    const rows = await screen.findByTestId('diff-rows');
    expect([...rows.children].map((el) => el.textContent)).toEqual([
      '⋯ 146 unchanged lines',
      '  line 147', '  line 148', '  line 149',
      '- line 150',
      '+ line 150, rewritten',
      '  line 151', '  line 152', '  line 153',
      '⋯ 47 unchanged lines',
    ]);
    expect(screen.getByTestId('diff-counts')).toHaveTextContent('1 line added, 1 removed');
  });

  it('expands a fold in place, and folds side by side the same way', async () => {
    render(<History start={3} />);
    const rows = await screen.findByTestId('diff-rows');
    fireEvent.click(within(rows).getByText('⋯ 47 unchanged lines'));
    expect(rows.children).toHaveLength(9 + 47);
    expect(rows.firstElementChild).toHaveTextContent('⋯ 146 unchanged lines');
    expect(rows.lastElementChild).toHaveTextContent('line 200');

    // The same folds, the opened one still open: they are cut before the
    // rows are paired, so both layouts show the same lines.
    fireEvent.click(screen.getByTestId('diff-mode-split'));
    const split = screen.getByTestId('diff-split');
    expect(within(split).getAllByTestId('diff-fold').map((el) => el.textContent)).toEqual([
      '⋯ 146 unchanged lines',
    ]);
    expect(split.children).toHaveLength(1 + 2 * (3 + 1 + 3 + 47)); // a fold spans both columns
  });

  it('brings the first change into view as each step opens, with no hand scroll', async () => {
    const scrolled = stubScroll();
    render(<History start={3} />);
    await screen.findByTestId('diff-rows');
    expect(scrolled.mock.contexts).toHaveLength(1);
    expect(scrolled.mock.contexts[0]).toHaveTextContent(/^- line 150$/);
    expect(scrolled.mock.calls).toEqual([[{ block: 'nearest' }]]);

    fireEvent.click(screen.getByTestId('step-next'));
    await waitFor(() => expect(scrolled.mock.contexts).toHaveLength(2));
    expect(scrolled.mock.contexts[1]).toHaveTextContent(/^- line 20$/);

    // Back to a step already fetched: no Loading… in between to remount the
    // diff, and it still opens on its own change, its folds closed.
    fireEvent.click(screen.getByTestId('step-prev'));
    expect(scrolled.mock.contexts).toHaveLength(3);
    expect(scrolled.mock.contexts[2]).toHaveTextContent(/^- line 150$/);
  });
});

describe('CommitteeView document stepper', () => {
  const captured = { ...run2, document: DOC };

  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn((u: string) =>
      String(u).includes('/view/artifact') ? ok({ text: TEXT[pathOf(u)] }) : new Promise(() => {}),
    ));
  });

  it("opens a step's linked turn in the transcript and brings it on screen", () => {
    const scrolled = stubScroll();
    show(captured);
    fireEvent.click(screen.getByTestId('step-3'));
    fireEvent.click(screen.getByTestId('goto-t02'));

    expect(
      within(screen.getByTestId('entry-2')).getByRole('button', { expanded: true }),
    ).toBeInTheDocument();
    // That turn's row, centred -- not the stepper, not merely something.
    expect(scrolled.mock.contexts).toEqual([screen.getByTestId('entry-2')]);
    expect(scrolled.mock.calls).toEqual([[{ block: 'center' }]]);
  });

  it('opens the last take of a turn settled twice, as the step context reads it', () => {
    const scrolled = stubScroll();
    const retake = { ...run2.timeline[1], body: 'Second take.' };
    show({ ...captured, timeline: [...run2.timeline, retake] });
    fireEvent.click(screen.getByTestId('step-3'));
    fireEvent.click(screen.getByTestId('goto-t02'));
    expect(scrolled.mock.contexts).toEqual([screen.getAllByTestId('entry-2')[1]]);
  });

  it('switches every diff to side by side, and the choice survives stepping and data ticks', async () => {
    const { rerender } = show(captured);
    fireEvent.click(screen.getByTestId('step-3'));
    await screen.findByTestId('diff-rows');
    fireEvent.click(screen.getByTestId('diff-mode-split'));

    expect(screen.queryByTestId('diff-rows')).toBeNull();
    const lefts = screen.getAllByTestId('split-left').map((el) => el.textContent);
    const rights = screen.getAllByTestId('split-right').map((el) => el.textContent);
    expect(lefts).toContain('- old clause');
    expect(rights).toContain('+ new clause');
    // Side by side means the replacement sits beside what it replaced.
    expect(lefts.indexOf('- old clause')).toBe(rights.indexOf('+ new clause'));

    fireEvent.click(screen.getByTestId('step-6'));
    expect(await screen.findByTestId('diff-split')).toBeInTheDocument();
    rerender(
      <CommitteeView
        runId="run-2"
        data={{ ...captured, progress: { ...captured.progress, turn: 21 } }}
        refetch={noop}
      />,
    );
    expect(screen.getByTestId('diff-split')).toBeInTheDocument();
    expect(screen.getByTestId('diff-mode-split')).toHaveAttribute('aria-pressed', 'true');
  });

  it('toggles the original → final diff on Final: off by default, in the chosen layout, kept on return', async () => {
    show(captured);
    fireEvent.click(screen.getByTestId('step-final'));
    // One fixed label; aria-pressed carries the state. A label that swaps as
    // well reads "Show the final version, pressed".
    const toggle = screen.getByTestId('final-diff-toggle');
    expect(toggle).toHaveAccessibleName('Original → final diff');
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
    expect(await screen.findByTestId('doc-markdown')).toHaveTextContent('new clause');

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
    expect(toggle).toHaveAccessibleName('Original → final diff');
    const rows = await screen.findByTestId('diff-rows');
    expect(rows).toHaveTextContent('- old clause');
    expect(rows).toHaveTextContent('+ new clause');

    fireEvent.click(screen.getByTestId('diff-mode-split'));
    expect(screen.getByTestId('diff-split')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('step-3'));
    fireEvent.click(screen.getByTestId('step-final'));
    expect(screen.getByTestId('final-diff-toggle')).toHaveAttribute('aria-pressed', 'true');
    expect(await screen.findByTestId('diff-split')).toBeInTheDocument();
  });

  it('clicking a delegated row selects its step, brings the stepper to the top and focuses it', () => {
    // `block: 'nearest'` left the stepper at the viewport's bottom edge with
    // the edit below the fold, and focus on the transcript button.
    const scrolled = stubScroll();
    show(captured);

    expect(screen.getByTestId('see-edit-2')).toHaveTextContent('see edit 1'); // the owner's row
    expect(screen.getByTestId('see-edit-3')).toHaveTextContent('see edit 1'); // the junior's row
    expect(screen.getByTestId('see-edit-5')).toHaveTextContent('see edit 2');
    expect(screen.getByTestId('see-edit-9')).toHaveTextContent('see edit 3');
    expect(screen.queryByTestId('see-edit-8')).toBeNull(); // t09's owner is unknown
    expect(screen.queryByTestId('see-edit-7')).toBeNull(); // and so is who raised it

    fireEvent.click(screen.getByTestId('see-edit-5'));
    expect(screen.getByTestId('step-6')).toHaveAttribute('aria-current', 'step');
    const stepper = screen.getByTestId('doc-stepper');
    expect(scrolled.mock.contexts).toEqual([stepper]);
    expect(scrolled.mock.calls).toEqual([[{ block: 'start' }]]);
    expect(document.activeElement).toBe(stepper);
  });

  it('links the reviewer who raised an edit back to its step, the way back from "raised by"', () => {
    stubScroll();
    show(captured);
    expect(screen.getByTestId('see-edit-1')).toHaveTextContent('see edit 1'); // raised Edit 1
    expect(screen.getByTestId('see-edit-4')).toHaveTextContent('see edit 2'); // raised Edit 2

    fireEvent.click(screen.getByTestId('see-edit-4'));
    expect(screen.getByTestId('step-6')).toHaveAttribute('aria-current', 'step');
  });

  it('titles the document card with its name and how many edits it went through', () => {
    const { unmount } = show(captured);
    expect(screen.getByText('Document — federation-future.md · 3 edits')).toBeInTheDocument();
    unmount();

    show({ ...captured, document: { ...DOC, steps: DOC.steps.slice(0, 1) } });
    expect(screen.getByText('Document — federation-future.md · 1 edit')).toBeInTheDocument();
  });

  it('links no transcript row to a step when there are no snapshots to show', () => {
    show(run2);
    expect(screen.queryByTestId('see-edit-2')).toBeNull();
    expect(screen.queryByTestId('see-edit-3')).toBeNull();
  });

  it('keeps the selected step across a data tick', () => {
    const { rerender } = show(captured);
    fireEvent.click(screen.getByTestId('step-6'));
    rerender(
      <CommitteeView
        runId="run-2"
        data={{ ...captured, progress: { ...captured.progress, turn: 21 } }}
        refetch={noop}
      />,
    );
    expect(screen.getByTestId('step-6')).toHaveAttribute('aria-current', 'step');
  });
});

describe('CommitteeView when the original changed under the committee', () => {
  // The test WB-C1 says was missing. `artifact_intact: false` was only ever
  // rendered against <Verdict> in isolation, so nothing ever put the two cards
  // on one page — and the diff card was guaranteeing the file untouched, in the
  // calmest colour available, beside a red card saying it CHANGED.
  const changed = { ...run2, verdict: { ...run2.verdict!, artifact_intact: false } };

  it('drops the untouched guarantee from the diff card', () => {
    show(changed);

    expect(screen.queryByTestId('diff-original-untouched')).toBeNull();
    expect(screen.getByTestId('diff-original-changed')).toHaveTextContent(
      'The original CHANGED during this review',
    );
  });

  it('stops claiming no repository was written to', () => {
    show(changed);

    const sim = screen.getByTestId('verdict-simulation');
    expect(sim).not.toHaveTextContent('No repository was written to');
    expect(sim).toHaveTextContent('A repository file DID change during this review');
  });

  it('leaves the two cards saying the same thing about the same file', () => {
    show(changed);

    expect(screen.getByTestId('artifact-intact')).toHaveTextContent('CHANGED DURING THE REVIEW');
    expect(screen.getByTestId('diff-original-changed')).toHaveTextContent(
      'CHANGED during this review',
    );
    expect(screen.queryByText(/is never modified/)).toBeNull();
    // The one sentence that must not survive: the unqualified byte-for-byte
    // promise. The failure card says "is NOT byte-for-byte", which is the point.
    expect(screen.queryByText(/ is byte-for-byte what the committee was handed/)).toBeNull();
  });

  it('still says nothing landed, because nothing this playbook does can', () => {
    show(changed);

    expect(screen.getByTestId('verdict-simulation')).toHaveTextContent('Nothing was landed');
  });
});

// --- the Metrics tab ----------------------------------------------------------

describe('CommitteeView on the Metrics tab', () => {
  const metrics = (data = run2) =>
    render(<CommitteeView runId="run-2" data={data} refetch={noop} variant="metrics" />);

  // Turn 8 is an owner reply and turn 9 is the manager's floor request being
  // granted: the queue pops on the turn it mints.
  const granted = {
    ...midRun,
    timeline: [
      ...midRun.timeline,
      { ...run2.timeline[1], n: 8, badges: [], action: null },
      { ...run2.timeline[3], n: 9, badges: [] },
    ],
  };

  it('declares the section on the component itself, the only export there is', () => {
    expect((CommitteeView as any).variants).toEqual(['metrics']);
  });

  it('draws only its numbers there, not the whole tab a second time', () => {
    metrics();

    expect(screen.getByTestId('committee-metrics')).toBeInTheDocument();
    expect(screen.queryByTestId('committee-view')).toBeNull();
    expect(screen.queryByTestId('entry-1')).toBeNull();
  });

  it('keeps the numbers off the tab that already has the transcript', () => {
    show();

    expect(screen.queryByTestId('committee-metrics')).toBeNull();
  });

  it('counts every seat, the ones that never spoke included', () => {
    metrics(midRun);

    expect(screen.getByTestId('turns-owner')).toHaveTextContent(/^Maya Okonkwo\s*2$/);
    expect(screen.getByTestId('turns-junior_ic')).toHaveTextContent(/2$/);
    expect(screen.getByTestId('turns-tpm')).toHaveTextContent(/1$/);
    expect(screen.getByTestId('turns-staff_ic')).toHaveTextContent(/0$/);
  });

  it('counts turns per persona over the whole run-2 meeting', () => {
    metrics();

    expect(screen.getByTestId('turns-owner')).toHaveTextContent(/7$/);
    expect(screen.getByTestId('turns-junior_ic')).toHaveTextContent(/6$/);
    for (const role of ['senior_director', 'manager', 'tpm', 'pm', 'tl', 'staff_ic', 'data_scientist']) {
      expect(screen.getByTestId(`turns-${role}`)).toHaveTextContent(/1$/);
    }
    expect(screen.queryByTestId('turns-unattributed')).toBeNull();
  });

  it('says which turns a seat took but never delivered', () => {
    metrics({ ...run2, timeline: [...run2.timeline, ...edgeTurns] });

    expect(screen.getByTestId('turns-tl')).toHaveTextContent('2 · 1 not delivered');
  });

  it('counts a turn nobody can be named for on its own row, not a persona\'s', () => {
    const ghost = { ...run2.timeline[0], n: 21, role: 'ghost', name: 'unattributed', badges: ['unattributed'] };
    metrics({ ...run2, timeline: [...run2.timeline, ghost] });

    expect(screen.getByTestId('turns-unattributed')).toHaveTextContent(/1$/);
    expect(screen.getByTestId('turns-senior_director')).toHaveTextContent(/1$/);
  });

  it('rates delegation against the owner turns that could have delegated', () => {
    metrics();

    expect(screen.getByTestId('delegation-rate')).toHaveTextContent(
      '6 of 7 delivered owner turns delegated an edit',
    );
  });

  it('counts a delegation only when it named the edit, as the gate does', () => {
    // `_apply_block` wants `delegate` AND a non-empty action; the badge alone
    // is what the owner asked for, not what the meeting did.
    const unnamed = { ...run2.timeline[1], n: 25, action: null };
    metrics({ ...run2, timeline: [...run2.timeline, unnamed] });

    expect(screen.getByTestId('delegation-rate')).toHaveTextContent('6 of 8 delivered owner turns');
  });

  it('leaves an owner turn nobody delivered out of the denominator', () => {
    const silent = { ...run2.timeline[1], n: 25, body: '', badges: ['no_turn'], action: null };
    metrics({ ...run2, timeline: [...run2.timeline, silent] });

    expect(screen.getByTestId('delegation-rate')).toHaveTextContent('6 of 7 delivered owner turns');
  });

  it('counts the edits that passed and failed the independent re-check', () => {
    metrics({ ...run2, timeline: [...run2.timeline, ...edgeTurns] });

    expect(screen.getByTestId('edit-rechecks')).toHaveTextContent('7 re-checked: 6 applied · 1 did not apply');
  });

  it('names a delegation the turn cap cut off', () => {
    metrics({ ...run2, verdict: { ...run2.verdict!, dropped_delegation: 'add a rollback plan' } });

    expect(screen.getByTestId('edit-dropped')).toHaveTextContent('add a rollback plan');
  });

  it('measures floor latency in turns, because the record has no clock', () => {
    metrics(granted);

    expect(screen.getByTestId('floor-ask-4')).toHaveTextContent(
      'Ruth Delgado asked on turn 4 · got the floor on turn 9, 5 turns later',
    );
  });

  it('grants the floor on the turn it was minted, delivered or not', () => {
    const silent = { ...granted.timeline[8], body: '', badges: ['no_turn'] };
    metrics({ ...granted, timeline: [...granted.timeline.slice(0, 8), silent] });

    expect(screen.getByTestId('floor-ask-4')).toHaveTextContent('got the floor on turn 9');
  });

  it('says nobody asked rather than showing an empty list', () => {
    metrics();

    expect(screen.getByTestId('floor-asks')).toHaveTextContent('Nobody asked for the floor.');
  });

  it('shows a request still waiting mid-run, and one the meeting ended on', () => {
    const waiting = metrics(midRun);
    expect(screen.getByTestId('floor-ask-4')).toHaveTextContent('Ruth Delgado asked on turn 4 · still waiting');
    waiting.unmount();

    metrics({ ...midRun, verdict: { ...run2.verdict!, dropped_floor_requests: ['manager'] } });
    expect(screen.getByTestId('floor-ask-4')).toHaveTextContent('asked on turn 4 · the meeting ended first');
  });

  it('ignores a floor request from a seat the state machine never queues', () => {
    const owner = { ...run2.timeline[1], n: 8, badges: ['request_floor'], action: null };
    // `_floor` skips a turn nobody can be named for, as `_reduce_turn` does.
    const ghost = { ...run2.timeline[3], n: 9, role: 'ghost', name: 'unattributed', badges: ['unattributed', 'request_floor'] };
    metrics({ ...midRun, timeline: [...midRun.timeline, owner, ghost] });

    expect(screen.queryByTestId('floor-ask-8')).toBeNull();
    expect(screen.queryByTestId('floor-ask-9')).toBeNull();
  });

  it('grows the thread by the prose each turn added, cumulatively', () => {
    metrics(midRun);
    const total = midRun.timeline.reduce((sum, e) => sum + e.body.length, 0);

    expect(screen.getByTestId('thread-growth')).toHaveTextContent(
      `${total.toLocaleString('en-US')} characters of prose over 7 turns`,
    );
    expect(screen.getByTestId('growth-1')).toHaveAttribute(
      'title',
      `turn 1: ${midRun.timeline[0].body.length.toLocaleString('en-US')} characters so far`,
    );
    expect(screen.getByTestId('growth-7')).toHaveAttribute(
      'title',
      `turn 7: ${total.toLocaleString('en-US')} characters so far`,
    );
  });

  it('counts no prose for a signals-only or an undelivered turn', () => {
    const twoEdges = edgeTurns.filter((e) => e.n === 22 || e.n === 23);
    metrics({ ...midRun, timeline: [...midRun.timeline, ...twoEdges] });
    const total = midRun.timeline.reduce((sum, e) => sum + e.body.length, 0);

    expect(screen.getByTestId('growth-23')).toHaveAttribute(
      'title',
      `turn 23: ${total.toLocaleString('en-US')} characters so far`,
    );
  });

  it('says a run with no recorded prose has none, rather than drawing a flat line', () => {
    metrics({ ...run2, timeline: run2.timeline.map((e) => ({ ...e, body: '' })) });

    expect(screen.getByTestId('thread-growth')).toHaveTextContent('No prose recorded for these turns.');
    expect(screen.queryByTestId('growth-1')).toBeNull();
  });

  it('marks an unfinished meeting as partial', () => {
    metrics(midRun);
    expect(screen.getByTestId('metrics-partial')).toHaveTextContent('Through turn 7; no verdict yet.');
  });

  it('does not mark a finished meeting as partial', () => {
    metrics();
    expect(screen.queryByTestId('metrics-partial')).toBeNull();
  });

  it('says nothing was said yet on a run that has no turns', () => {
    metrics({ ...midRun, timeline: [] });
    expect(screen.getByText('Nothing said yet')).toBeInTheDocument();
  });
});

describe('CommitteeView evaluation on the Metrics tab', () => {
  type EvalOk = Extract<Evaluation, { state: 'ok' }>;

  const dim = (
    score: number | null,
    scorer: 'judge' | 'deterministic',
    quote: string | null,
    calibration: string | null,
  ) => ({ score, scorer, quote, calibration });

  // Deterministic first and judge last on purpose: eval.json's key order is not
  // the rubric's, and the table reads in D5 order whatever order it arrives in.
  const EVAL_OK: EvalOk = {
    state: 'ok',
    rubric_version: 'r1a2b3c4d',
    evaluated_at: 1790000000.5,
    headline: 'weakest: concision 1/5: words.median_reviewer_owner=825.0',
    judge_status: 'ok',
    judge_error: null,
    dimensions: {
      verdict_consistency: dim(1, 'deterministic', 'flags.verdict_count_mismatch=1', null),
      concision: dim(1, 'deterministic', 'words.median_reviewer_owner=825.0', null),
      efficiency: dim(3, 'deterministic', 'cost_usd=30.3875', null),
      concern_coverage: dim(3, 'judge', 'Reading this as a staffing question first.', 'calibrated'),
      edits_address_concerns: dim(3, 'judge', 'Fair point; here is where I land on it.', 'off (Δ2)'),
      verdict_grounded: dim(
        4,
        'judge',
        'Approve with changes: fund the migration once the rollback plan lands.',
        'uncalibrated',
      ),
    },
    flags: [
      'delegation_truncated_but_applied',
      'delegation_truncated_but_applied',
      'action_clipped',
      'verdict_count_mismatch',
    ],
  };

  const D5 = [
    'verdict_grounded',
    'edits_address_concerns',
    'concern_coverage',
    'efficiency',
    'concision',
    'verdict_consistency',
  ];

  // `undefined` leaves the key out entirely: run2.fixture.ts predates the eval.
  const metrics = (evaluation?: Evaluation | null) =>
    render(
      <CommitteeView
        runId="run-2"
        data={evaluation === undefined ? run2 : { ...run2, evaluation }}
        refetch={noop}
        variant="metrics"
      />,
    );

  const COMMAND = '.venv/bin/python -m playbooks.committee.eval_cli run run-2';

  it('says a run nobody has scored is not evaluated, and how to score it, runnable as written', () => {
    const { unmount } = metrics();

    const empty = screen.getByTestId('evaluation-empty');
    expect(empty.textContent).toBe(
      `Not evaluated. Score it with ${COMMAND} from the hermes checkout, ` +
        "with HERMES_HOME set to this control plane's home.",
    );
    expect(within(empty).getByText(COMMAND).tagName).toBe('CODE');
    expect(screen.queryByTestId('evaluation-headline')).toBeNull();
    unmount();

    metrics(null);
    expect(screen.getByTestId('evaluation-empty')).toBeInTheDocument();
    expect(screen.queryAllByTestId(/^eval-dim-/)).toHaveLength(0);
  });

  it('offers no command for a run that cannot be scored yet: mid-meeting, or a chair that delivered nothing', () => {
    const NOT_YET = 'Not evaluated: a run can be scored once the chair has delivered its verdict.';
    for (const data of [midRun, { ...run2, verdict: { ...run2.verdict!, text: '' } }]) {
      const { unmount } = render(
        <CommitteeView runId="run-2" data={{ ...data, evaluation: null }} refetch={noop} variant="metrics" />,
      );
      expect(screen.getByTestId('evaluation-empty').textContent).toBe(NOT_YET);
      expect(screen.queryByText(/eval_cli/)).toBeNull();
      unmount();
    }
  });

  it("shows each dimension's scorer and verified quote in full, and says when none verified", () => {
    metrics({
      ...EVAL_OK,
      dimensions: { ...EVAL_OK.dimensions, efficiency: dim(0, 'deterministic', null, null) },
    });

    const row = (id: string) => within(screen.getByTestId(`eval-dim-${id}`)).getAllByRole('cell');
    const quote = EVAL_OK.dimensions.verdict_grounded.quote!;
    expect(row('verdict_grounded').map((c) => c.textContent)).toEqual([
      'verdict grounded',
      '4uncalibrated',
      'judge',
      quote,
    ]);
    expect(row('concision')[2]).toHaveTextContent(/^deterministic$/);
    // Read in full, wrapped: not cut to one line with the rest only in a tooltip.
    const evidence = row('verdict_grounded')[3];
    expect(evidence).not.toHaveAttribute('title');
    expect(evidence).not.toHaveStyle({ whiteSpace: 'nowrap' });
    expect(row('efficiency')[3]).toHaveTextContent(/^no verified quote$/);
    // 0 is a score, not a missing one.
    expect(screen.getByTestId('eval-score-efficiency')).toHaveTextContent(/^0$/);
    expect(screen.queryAllByLabelText('not scored')).toHaveLength(0);
  });

  it("puts the judge's reason under its quote, folded behind a why, as plain text, and nothing when it gave none", () => {
    const why = 'Cites <b>t03</b> and t07;\nthe rollback plan is the condition.';
    metrics({
      ...EVAL_OK,
      dimensions: {
        ...EVAL_OK.dimensions,
        verdict_grounded: { ...EVAL_OK.dimensions.verdict_grounded, rationale: why },
        concern_coverage: { ...EVAL_OK.dimensions.concern_coverage, rationale: null },
      },
    });

    const evidence = within(screen.getByTestId('eval-dim-verdict_grounded')).getAllByRole('cell')[3];
    const details = within(evidence).getByTestId('eval-why-verdict_grounded');
    expect(evidence.firstChild!.textContent).toBe(EVAL_OK.dimensions.verdict_grounded.quote);
    expect(details.tagName).toBe('DETAILS');
    // A native disclosure: its summary takes focus and opens it from the keyboard.
    const summary = details.firstElementChild as HTMLElement;
    expect(summary.tagName).toBe('SUMMARY');
    expect(summary.textContent).toBe('why');
    expect(details).not.toHaveAttribute('open');
    fireEvent.click(summary);
    expect(details).toHaveAttribute('open');
    // Text, never markup: the judge wrote it.
    expect(details.textContent).toBe(`why${why}`);
    expect(details.querySelector('b')).toBeNull();

    // null, and a payload from before the eval sent a rationale at all.
    expect(screen.getAllByTestId(/^eval-why-/)).toHaveLength(1);
    expect(within(screen.getByTestId('eval-dim-concern_coverage')).getAllByRole('cell')[3].textContent).toBe(
      EVAL_OK.dimensions.concern_coverage.quote,
    );
  });

  it('stars a score taken under an older definition, and says once under the table how to re-score it', () => {
    const { unmount } = metrics({
      ...EVAL_OK,
      dimensions: {
        ...EVAL_OK.dimensions,
        verdict_grounded: { ...EVAL_OK.dimensions.verdict_grounded, stale: true },
        concision: { ...EVAL_OK.dimensions.concision, stale: true },
        efficiency: { ...EVAL_OK.dimensions.efficiency, stale: false },
      },
    });

    expect(screen.getByTestId('eval-score-verdict_grounded')).toHaveTextContent(/^4\*$/);
    expect(screen.getByTestId('eval-score-concision')).toHaveTextContent(/^1\*$/);
    expect(screen.getByTestId('eval-score-efficiency')).toHaveTextContent(/^3$/);
    expect(screen.getByTestId('eval-score-concern_coverage')).toHaveTextContent(/^3$/);
    const notes = screen.getAllByTestId('eval-stale-note');
    expect(notes).toHaveLength(1);
    expect(notes[0].textContent).toBe(`* older definition; re-run ${COMMAND}`);
    expect(within(notes[0]).getByText(COMMAND).tagName).toBe('CODE');
    const table = screen.getByRole('table', { name: 'Evaluation scores' });
    expect(table.compareDocumentPosition(notes[0]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    unmount();

    // Nothing stale, or a payload from before the eval said: no star, no note.
    for (const stale of [undefined, false]) {
      const dimensions = Object.fromEntries(
        Object.entries(EVAL_OK.dimensions).map(([id, d]) => [id, stale === undefined ? d : { ...d, stale }]),
      );
      const { unmount: done } = metrics({ ...EVAL_OK, dimensions });
      expect(screen.queryByTestId('eval-stale-note')).toBeNull();
      expect(screen.getByRole('table', { name: 'Evaluation scores' }).textContent).not.toContain('*');
      done();
    }
  });

  it('badges a judge score as unknown when the calibration ledger could not be read', () => {
    metrics({
      ...EVAL_OK,
      dimensions: { ...EVAL_OK.dimensions, verdict_grounded: dim(4, 'judge', 'q', 'unknown') },
    });

    expect(screen.getByTestId('eval-uncalibrated-verdict_grounded')).toHaveTextContent(/^unknown$/);
  });

  it('draws a dimension this bundle does not know yet after the six it does, whatever order it arrives in', () => {
    const { verdict_consistency, ...rest } = EVAL_OK.dimensions;
    metrics({
      ...EVAL_OK,
      dimensions: {
        voice_register: dim(2, 'deterministic', 'hedges=9', null),
        ...rest,
        voice_turns: dim(5, 'deterministic', 'turns=3', null),
        verdict_consistency,
      },
    });

    expect(screen.getAllByTestId(/^eval-dim-/).map((r) => r.getAttribute('data-testid'))).toEqual(
      [...D5, 'voice_register', 'voice_turns'].map((id) => `eval-dim-${id}`),
    );
    expect(within(screen.getByTestId('eval-dim-voice_register')).getAllByRole('cell')[0]).toHaveTextContent(
      /^voice register$/,
    );
  });

  it('names the table and reads a missing score as not scored', () => {
    const noJudge = dim(null, 'judge', null, 'uncalibrated');
    metrics({
      ...EVAL_OK,
      judge_status: 'unparseable',
      judge_error: null,
      dimensions: { ...EVAL_OK.dimensions, verdict_grounded: noJudge, concern_coverage: noJudge },
    });

    const table = screen.getByRole('table', { name: 'Evaluation scores' });
    const missing = within(table).getAllByLabelText('not scored');
    expect(missing.map((m) => m.textContent)).toEqual(['—', '—']);
    expect(within(screen.getByTestId('eval-score-verdict_grounded')).getByLabelText('not scored')).toBe(
      missing[0],
    );
    // An unparseable answer has no error to append: the status alone.
    expect(screen.getByTestId('evaluation-judge-status').textContent).toBe('Judge unparseable');
  });

  it('draws a payload whose fields the server could not type as unknown, not as a crash', () => {
    metrics({ ...EVAL_OK, headline: null, rubric_version: null, evaluated_at: null, judge_status: null });

    expect(screen.getByTestId('evaluation-judge-status').textContent).toBe('Judge status unknown');
    expect(screen.getByTestId('evaluation-rubric')).toHaveTextContent(/^rubric unknown$/);
    expect(screen.getAllByTestId(/^eval-dim-/)).toHaveLength(6);
  });

  it('shows the scores in rubric order under the meeting metrics, badging only uncalibrated judge scores', () => {
    const { unmount } = metrics(EVAL_OK);

    const block = screen.getByTestId('evaluation');
    const counts = screen.getByTestId('committee-metrics');
    expect(counts.compareDocumentPosition(block) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getAllByTestId(/^eval-dim-/).map((r) => r.getAttribute('data-testid'))).toEqual(
      D5.map((id) => `eval-dim-${id}`),
    );
    expect(screen.getByTestId('eval-score-verdict_grounded')).toHaveTextContent(/^4$/);
    expect(screen.getByTestId('eval-score-efficiency')).toHaveTextContent(/^3$/);
    expect(screen.getByTestId('eval-score-concision')).toHaveTextContent(/^1$/);
    expect(screen.getByTestId('evaluation-headline')).toHaveTextContent(EVAL_OK.headline!);
    expect(screen.getByTestId('evaluation-rubric')).toHaveTextContent('r1a2b3c4d');

    expect(screen.getByTestId('eval-uncalibrated-verdict_grounded')).toHaveTextContent('uncalibrated');
    expect(screen.getByTestId('eval-uncalibrated-edits_address_concerns')).toHaveTextContent('off (Δ2)');
    for (const id of ['concern_coverage', 'efficiency', 'concision', 'verdict_consistency']) {
      expect(screen.queryByTestId(`eval-uncalibrated-${id}`)).toBeNull();
    }
    expect(screen.getByTestId('eval-flags')).toHaveTextContent(
      'delegation_truncated_but_applied ×2 · action_clipped · verdict_count_mismatch',
    );
    expect(screen.queryByTestId('evaluation-judge-status')).toBeNull();
    expect(screen.queryByTestId('evaluation-empty')).toBeNull();

    // Scores and their quotes only: every count here is MeetingMetrics' to show.
    expect(block.textContent).not.toMatch(/turns|delegated|re-check|characters of prose/i);
    unmount();

    // The Metrics tab's, not the transcript tab's.
    show({ ...run2, evaluation: EVAL_OK });
    expect(screen.queryByTestId('evaluation')).toBeNull();
  });

  it('keeps the deterministic scores and says why the judge scored nothing when it failed or was partial', () => {
    const noJudge = dim(null, 'judge', null, 'uncalibrated');
    const { unmount } = metrics({
      ...EVAL_OK,
      judge_status: 'failed',
      judge_error: 'driver_error: the judge exited 1',
      dimensions: {
        ...EVAL_OK.dimensions,
        verdict_grounded: noJudge,
        edits_address_concerns: noJudge,
        concern_coverage: noJudge,
      },
    });

    for (const id of ['verdict_grounded', 'edits_address_concerns', 'concern_coverage']) {
      expect(screen.getByTestId(`eval-score-${id}`)).toHaveTextContent(/^—$/);
    }
    expect(screen.getByTestId('eval-score-efficiency')).toHaveTextContent(/^3$/);
    expect(screen.getByTestId('eval-score-concision')).toHaveTextContent(/^1$/);
    expect(screen.getByTestId('eval-score-verdict_consistency')).toHaveTextContent(/^1$/);
    expect(screen.getByTestId('evaluation-judge-status')).toHaveTextContent(
      'Judge failed: driver_error: the judge exited 1',
    );
    unmount();

    metrics({
      ...EVAL_OK,
      judge_status: 'partial',
      judge_error: 'concern_coverage: no verifiable evidence',
      dimensions: { ...EVAL_OK.dimensions, concern_coverage: noJudge },
    });
    expect(screen.getByTestId('eval-score-concern_coverage')).toHaveTextContent(/^—$/);
    expect(screen.getByTestId('eval-score-verdict_grounded')).toHaveTextContent(/^4$/);
    expect(screen.getByTestId('evaluation-judge-status')).toHaveTextContent(
      'Judge partial: concern_coverage: no verifiable evidence',
    );
  });

  it('shows the message, and no score table, when eval.json cannot be read', () => {
    metrics({ state: 'error', error: 'eval.json is not JSON' });

    expect(screen.getByTestId('evaluation-error')).toHaveTextContent('eval.json is not JSON');
    expect(screen.queryAllByTestId(/^eval-dim-/)).toHaveLength(0);
    expect(screen.queryByTestId('evaluation-empty')).toBeNull();
    expect(screen.getByTestId('committee-metrics')).toBeInTheDocument();
  });
});

// --- voice (committee-voice T15) -----------------------------------------------

/** run-2's turn 2 as voice records it: retaken, flagged, with both kinds of figure. */
const VOICED: Entry = {
  ...run2.timeline[1],
  body: 'Conceded.',
  badges: ['voice_flag', 'retaken', 'no_pointer', 'no_example'],
  take: 3,
  takes: 3,
  violations: ['over_cap', 'bold'],
  flags: ['no_pointer', 'no_example'],
  voice: { words: 212 },
  segments: [
    { kind: 'text', text: 'Conceded: the staffing line is fiction.' },
    { kind: 'image', name: 't02-owner.svg', ref: 'images/t02-owner.svg', caption: 'staffing curve',
      description: 'engineers per week, flat after week 6', ok: true },
    { kind: 'image', name: 'http://evil.example/x.png', ref: 'http://evil.example/x.png',
      caption: 'their chart', description: 'a chart from elsewhere', ok: false },
    { kind: 'mermaid', source: 'graph TD; A-->B', caption: 'the pipeline', description: 'two stages' },
  ],
};

function withVoice(entry: Entry = VOICED) {
  return { ...run2, timeline: run2.timeline.map((e) => (e.n === entry.n ? entry : e)) };
}

function expand(n: number) {
  fireEvent.click(within(screen.getByTestId(`entry-${n}`)).getAllByRole('button')[0]);
  return screen.getByTestId(`entry-${n}`);
}

/** Point the host shelf's renderMermaid at `render` for one test. */
function shelf(render: ((source: string) => Promise<string>) | undefined) {
  const real = (window as any).HermesUI;
  (window as any).HermesUI = { ...real, renderMermaid: render };
  return () => {
    (window as any).HermesUI = real;
  };
}

describe('CommitteeView voice', () => {
  // vitest's jsdom URL has its own createObjectURL. The tests that draw a
  // diagram assign vi.fn()s; every test puts the originals back. Never delete
  // them: Node's native URL.createObjectURL then throws on a jsdom Blob, and
  // the unhandled rejection fails the run while every test reports passed.
  const realCreate = (URL as any).createObjectURL;
  const realRevoke = (URL as any).revokeObjectURL;
  afterEach(() => {
    (URL as any).createObjectURL = realCreate;
    (URL as any).revokeObjectURL = realRevoke;
  });

  it('badges a kept take that broke the rules and one that was retaken', () => {
    show(withVoice());
    const entry = screen.getByTestId('entry-2');

    expect(within(entry).getByText('broke the ground rules')).toBeInTheDocument();
    expect(within(entry).getByText('retaken')).toBeInTheDocument();
    expect(within(entry).getByText('no pointer')).toBeInTheDocument();
    expect(within(entry).getByText('no example')).toBeInTheDocument();
  });

  it('says which take was kept and what it broke, in words', () => {
    // entry 2 carries a mermaid segment: keep the renderer off the real mermaid
    const restore = shelf(() => new Promise(() => {}));
    try {
      show(withVoice());
      expand(2);

      expect(screen.getByTestId('kept-take-2')).toHaveTextContent(
        'kept take 3 of 3; broke: over the word cap; bold',
      );
    } finally {
      restore();
    }
  });

  it('collapses to the first line of the first text segment', () => {
    show(withVoice());

    expect(within(screen.getByTestId('entry-2')).getByText('Conceded: the staffing line is fiction.'))
      .toBeInTheDocument();
  });

  it('draws a checked image from the run images folder, with its caption and the token', () => {
    setToken('remote-typed-token');
    const restore = shelf(() => new Promise(() => {}));
    try {
      show(withVoice());
      const entry = expand(2);
      const img = within(entry).getByAltText('staffing curve');

      expect(img).toHaveAttribute(
        'src',
        '/api/runs/run-2/view/artifact?path=images%2Ft02-owner.svg&token=remote-typed-token',
      );
      expect(within(entry).getByText('engineers per week, flat after week 6')).toBeInTheDocument();
    } finally {
      restore();
      clearToken();
    }
  });

  it('shows an unchecked image as its caption and "image unavailable", and fetches nothing', () => {
    const restore = shelf(() => new Promise(() => {}));
    try {
      show(withVoice());
      const entry = expand(2);

      expect(within(entry).getByText('their chart')).toBeInTheDocument();
      expect(within(entry).getByText('a chart from elsewhere')).toBeInTheDocument();
      expect(within(entry).getByTestId('image-unavailable')).toHaveTextContent('image unavailable');
      expect(within(entry).queryByAltText('their chart')).toBeNull();
    } finally {
      restore();
    }
  });

  it('never renders an img whose src is not the run images route or a blob', async () => {
    (URL as any).createObjectURL = vi.fn(() => 'blob:hermes-1');
    (URL as any).revokeObjectURL = vi.fn();
    const restore = shelf(async () => '<svg xmlns="http://www.w3.org/2000/svg"></svg>');
    try {
      // references voice.segments leaves in text (committee-voice Task 1 review): alt text
      // across a line break, an escaped backtick, an unbalanced code span. On the turn as well
      // as the verdict, so Segments' own disarm is what keeps them out of Markdown, and in a
      // refused image's caption and description, which render as plain text.
      const leaky = {
        kind: 'text' as const,
        text: 'See ![a\nb](http://evil.example/x.png) and \\`![x](http://evil.example/y.png)` and ``![z](http://evil.example/z.png)` here.',
      };
      const refused = { kind: 'image' as const, name: 'x', ref: 'http://evil.example/v.png',
        caption: 'v ![c](http://evil.example/c.png)', description: 'd ![e](http://evil.example/e.png)', ok: false };
      // `text` carries an image too: the card renders `segments` only, so a
      // fallback to the raw text through Markdown would draw this one.
      const verdict = {
        ...run2.verdict!,
        text: 'Approve. ![x](http://evil.example/verdict.png)',
        segments: [{ kind: 'text' as const, text: 'Approve with changes.' }, leaky, refused],
      };
      const { container } = show({
        ...withVoice({ ...VOICED, segments: [...VOICED.segments!, leaky, refused] }),
        verdict,
      });
      fireEvent.click(screen.getByTestId('expand-all'));
      await screen.findByAltText('the pipeline');

      const srcs = [...container.querySelectorAll('img')].map((img) => img.getAttribute('src') ?? '');
      expect(srcs.length).toBeGreaterThan(0);
      for (const src of srcs) {
        expect(src.startsWith('/api/runs/run-2/view/artifact?path=images%2F') || src.startsWith('blob:'))
          .toBe(true);
        // an unchecked http image must not reach the route either, even encoded
        expect(src).not.toContain('http');
      }
    } finally {
      restore();
    }
  });

  it('says a diagram is rendering while the host renders it', () => {
    const restore = shelf(() => new Promise(() => {}));
    try {
      show(withVoice());
      const entry = expand(2);

      // a live region, so a screen reader hears the drawing arrive or fail
      expect(within(entry).getByText('rendering diagram…')).toHaveAttribute('role', 'status');
      expect(within(entry).getByText('the pipeline')).toBeInTheDocument();
    } finally {
      restore();
    }
  });

  it('draws a rendered diagram as a blob image, revoked when its source changes and on unmount', async () => {
    const create = vi.fn().mockReturnValueOnce('blob:hermes-1').mockReturnValueOnce('blob:hermes-2');
    const revoke = vi.fn();
    (URL as any).createObjectURL = create;
    (URL as any).revokeObjectURL = revoke;
    const render = vi.fn(async () => '<svg xmlns="http://www.w3.org/2000/svg"></svg>');
    const restore = shelf(render);
    try {
      const { rerender, unmount } = show(withVoice());
      const entry = expand(2);

      expect(await screen.findByAltText('the pipeline')).toHaveAttribute('src', 'blob:hermes-1');
      expect(render).toHaveBeenCalledWith('graph TD; A-->B');
      expect(create.mock.calls[0][0].type).toBe('image/svg+xml');
      // an <img> of the markup, never the markup itself in the page
      expect(within(entry).getByTestId('figure-mermaid').querySelector('svg')).toBeNull();

      const edited = VOICED.segments!.map((seg) =>
        seg.kind === 'mermaid' ? { ...seg, source: 'graph TD; A-->C' } : seg,
      );
      rerender(<CommitteeView runId="run-2" data={withVoice({ ...VOICED, segments: edited })} refetch={noop} />);
      expect(revoke).toHaveBeenCalledWith('blob:hermes-1');
      await waitFor(() => expect(screen.getByAltText('the pipeline')).toHaveAttribute('src', 'blob:hermes-2'));
      expect(render).toHaveBeenLastCalledWith('graph TD; A-->C');

      unmount();
      expect(revoke).toHaveBeenLastCalledWith('blob:hermes-2');
    } finally {
      restore();
    }
  });

  it('makes no blob URL for a diagram that finishes drawing after it is gone', async () => {
    // Created after the cleanup ran, the URL would never be revoked: a leak per
    // diagram the reader scrolled past or collapsed while mermaid was drawing.
    const create = vi.fn(() => 'blob:hermes-late');
    (URL as any).createObjectURL = create;
    (URL as any).revokeObjectURL = vi.fn();
    let finish!: (svg: string) => void;
    const restore = shelf(() => new Promise<string>((resolve) => { finish = resolve; }));
    try {
      const { unmount } = show(withVoice());
      expand(2);
      unmount();

      finish('<svg xmlns="http://www.w3.org/2000/svg"></svg>');
      await new Promise((resolve) => setTimeout(resolve, 0));
      expect(create).not.toHaveBeenCalled();
    } finally {
      restore();
    }
  });

  it('shows the source and the reason when a diagram fails to render, rejected or thrown', async () => {
    // The host's renderer rejects; one that throws instead must not escape the
    // effect into PlaybookView's error boundary, which never clears.
    const failures = [
      () => Promise.reject(new Error('Parse error on line 1')),
      () => {
        throw new Error('Parse error on line 1');
      },
    ];
    for (const fail of failures) {
      const restore = shelf(fail);
      try {
        const { unmount } = show(withVoice());
        const entry = expand(2);

        const error = await within(entry).findByTestId('mermaid-error');
        expect(error).toHaveTextContent('diagram failed to render: Parse error on line 1');
        expect(error).toHaveAttribute('role', 'status');
        expect(within(entry).getByTestId('mermaid-source')).toHaveTextContent('graph TD; A-->B');
        unmount();
      } finally {
        restore();
      }
    }
  });

  it('shows the source as code when the host has no renderer', async () => {
    const restore = shelf(undefined);
    try {
      show(withVoice());
      const entry = expand(2);

      expect(await within(entry).findByTestId('mermaid-source')).toHaveTextContent('graph TD; A-->B');
      expect(within(entry).queryByText('rendering diagram…')).toBeNull();
    } finally {
      restore();
    }
  });

  it('paints a kept take that broke the rules in the attention tone', () => {
    show(withVoice());

    expect(within(screen.getByTestId('entry-2')).getByText('broke the ground rules').getAttribute('style'))
      .toContain('--status-attention');
  });

  it('shows no take line for a first take kept clean', () => {
    show(withVoice({ ...VOICED, badges: [], take: 1, takes: 1, violations: [], flags: [],
      segments: [VOICED.segments![0]] }));
    expand(2);

    expect(screen.queryByTestId('kept-take-2')).toBeNull();
  });

  it('names the two newest rules in words', () => {
    expect(violationText(['filler', 'stance_too_long'])).toBe('filler phrases; a stance over its cap');
  });

  it('says an over-long caption or description is what image_uncaptioned also means', () => {
    expect(violationText(['image_uncaptioned'])).toBe('an image caption or description missing or too long');
  });

  it('badges AI tells with the kinds it found and how often, as plain text', () => {
    show(withVoice({ ...VOICED, badges: ['tells'],
      voice: { words: 212, tells: { process: 2, turn_refs: 1, unchanged: 0, hedge: 3, filler: 0 } } }));

    expect(within(screen.getByTestId('entry-2')).getByText('AI tells'))
      .toHaveAttribute('title', 'process 2, turn refs 1, hedge 3');
  });

  it('asks for the exact bytes the master checked when the image carries their sha256', () => {
    const sha256 = 'ab'.repeat(32);
    const segments = VOICED.segments!.map((seg) => (seg.kind === 'image' && seg.ok ? { ...seg, sha256 } : seg));
    const restore = shelf(() => new Promise(() => {}));
    try {
      show(withVoice({ ...VOICED, segments }));
      const entry = expand(2);

      expect(within(entry).getByAltText('staffing curve')).toHaveAttribute(
        'src',
        `/api/runs/run-2/view/artifact?path=images%2Ft02-owner.svg&sha256=${sha256}`,
      );
    } finally {
      restore();
    }
  });

  it('encodes the run id into an image URL', () => {
    expect(imageUrl('run #2/x', 't02-owner.svg')).toBe(
      '/api/runs/run%20%232%2Fx/view/artifact?path=images%2Ft02-owner.svg',
    );
  });

  it('says a diagram is rendering again when its source changes, not the old drawing', async () => {
    (URL as any).createObjectURL = vi.fn(() => 'blob:hermes-1');
    (URL as any).revokeObjectURL = vi.fn();
    const render = vi
      .fn()
      .mockResolvedValueOnce('<svg xmlns="http://www.w3.org/2000/svg"></svg>')
      .mockReturnValueOnce(new Promise(() => {}));
    const restore = shelf(render);
    try {
      const { rerender } = show(withVoice());
      const entry = expand(2);
      expect(await within(entry).findByAltText('the pipeline')).toHaveAttribute('src', 'blob:hermes-1');

      const edited = VOICED.segments!.map((seg) =>
        seg.kind === 'mermaid' ? { ...seg, source: 'graph TD; A-->C' } : seg,
      );
      rerender(<CommitteeView runId="run-2" data={withVoice({ ...VOICED, segments: edited })} refetch={noop} />);

      expect(within(entry).getByText('rendering diagram…')).toBeInTheDocument();
      expect(within(entry).queryByAltText('the pipeline')).toBeNull();
    } finally {
      restore();
    }
  });

  it('shows no voice badge and no take line on a turn from before voice', () => {
    show();
    const entry = expand(2);

    expect(within(entry).queryByText('broke the ground rules')).toBeNull();
    expect(within(entry).queryByText('retaken')).toBeNull();
    expect(screen.queryByTestId('kept-take-2')).toBeNull();
  });
});

const SUMMARY = {
  owner_reviewer_median_words: 120.0, owner_reviewer_pct_within_cap: 93.8,
  median_words_by_role: { owner: 118.0, tl: 131.0, chair: 280.0 },
  chair_words: 280, chair_headers: 0, chair_tables: 0,
  junior_turns: 0, junior_pct_compliant: null,
  pct_clean_format: 96.0, pct_first_line_le_25: 100.0, unquoted_dashes: 0,
  reviewer_pct_with_pointer: 87.5, max_turn_refs: 1, unchanged_mentions_junior_chair: 0,
  total_takes: 27, retakes_by_role: { owner: 2, tl: 0, chair: 0 }, kept_flagged: 1,
};

describe('CommitteeView voice metrics and verdict', () => {
  const metrics = (data: typeof run2) =>
    render(<CommitteeView runId="run-2" data={data} refetch={noop} variant="metrics" />);

  it('lists every voice figure, a dash for an empty population, a map as role and count', () => {
    metrics({ ...run2, voice: SUMMARY });
    const section = screen.getByTestId('voice-metrics');

    expect(within(section).getAllByTestId(/^voice-metric-/)).toHaveLength(Object.keys(SUMMARY).length);
    // Keyed off the payload, not the view's own label list, so a key renamed on
    // either side has no row to find.
    for (const [key, value] of Object.entries(SUMMARY)) {
      const shown =
        value === null ? '—'
        : typeof value === 'object' ? Object.entries(value).map(([r, n]) => `${r} ${n}`).join(', ')
        : String(value);
      expect(screen.getByTestId(`voice-metric-${key}`).lastElementChild?.textContent).toBe(shown);
    }
  });

  it('says a run from before voice was not measured, and hides nothing', () => {
    metrics({ ...run2, voice: null });

    expect(screen.getByTestId('voice-not-measured')).toHaveTextContent('not measured for this run');
    expect(screen.queryByTestId('voice-metrics')).toBeNull();
  });

  it('flags a verdict kept after retakes with the rules it broke', () => {
    render(<Verdict runId="run-2" verdict={{ ...VERDICT, takes: 3, violations: ['over_cap', 'headers'] }} />);

    expect(screen.getByTestId('verdict-voice')).toHaveTextContent(
      'The chair took 3 takes. The kept verdict broke the ground rules: over the word cap; headers.',
    );
    render(<Verdict runId="run-2" verdict={VERDICT} />);
    expect(screen.getAllByTestId('verdict-voice')).toHaveLength(1);
  });

  it('tints the verdict note for broken rules, and leaves retakes alone muted', () => {
    const { unmount } = render(<Verdict runId="run-2" verdict={{ ...VERDICT, violations: ['headers'] }} />);
    expect(screen.getByTestId('verdict-voice').style.background).toBe('var(--status-attention-tint)');
    unmount();

    render(<Verdict runId="run-2" verdict={{ ...VERDICT, takes: 2 }} />);
    expect(screen.getByTestId('verdict-voice').style.background).toBe('var(--wash-subtle)');
  });

  it('explains a failed chair retake in the attention tone', () => {
    show({ ...run2, progress: { ...run2.progress, ended: 'chair retake failed' } });
    const ended = screen.getByTestId('ended-reason');

    expect(ended).toHaveTextContent(
      "Ended: chair retake failed. The chair's retake failed, so its earlier take is recorded unruled and the run ended failed.",
    );
    expect(ended.style.color).toBe('var(--status-attention, #e3b341)');
  });

  it('stamps a verdict banked under decision-take2 through that reduction', async () => {
    // The mock filters on `?phase=` the way the server does, so the old
    // `?phase=decision` lookup finds nothing here and renders stamp-error.
    const rows = [
      { id: 30, kind: 'take', phase: 't02-owner-take2', review_state: 'pending' },
      { id: 31, kind: 'decision', phase: 'decision-take2', review_state: 'pending', json: { delivered: true } },
    ];
    const fetchMock = vi.fn((url: string) => {
      if (!String(url).startsWith('/api/runs/')) return ok({ review_state: 'accepted' });
      const phase = new URL(String(url), 'http://x').searchParams.get('phase');
      return ok(phase ? rows.filter((r) => r.phase === phase) : rows);
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<Verdict runId="run-2" verdict={VERDICT} />);

    expect(await screen.findByRole('button', { name: /reject/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /accept/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/reductions/31/accept',
        expect.objectContaining({ method: 'POST' }),
      ),
    );
  });
});

// --- selection (committee-selection Task 14) -----------------------------------

describe('CommitteeView before t01 and the seated roster', () => {
  it('shows the roster, not "Nothing said yet", while the committee is being selected', () => {
    show(selectingData);

    expect(screen.queryByText('Nothing said yet')).toBeNull();
    expect(screen.getByTestId('committee-view')).toBeInTheDocument();
    // `_seats` while selecting is the fixed four: no reviewer is seated yet.
    expect(screen.getByText('Committee — 4')).toBeInTheDocument();
    // The manager is amending the list, so she holds the floor; nobody has spoken.
    for (const role of ['owner', 'senior_director', 'junior_ic']) {
      expect(screen.getByTestId(`roster-${role}`)).toHaveTextContent('has not spoken');
    }
    expect(screen.queryByTestId('roster-tpm')).toBeNull();
    expect(screen.queryByTestId('floor-holder')).toBeNull();
  });

  it('the progress bar shows the cap from the latest selection reduction', () => {
    // Provisional while selecting (DEFAULT_MAX_TURNS), resolved once the chair
    // ratified: 2 x 5 reviewers + 16.
    const { unmount } = show(selectingData);
    expect(screen.getByTestId('turn-count')).toHaveTextContent('turn 0 of 30');
    unmount();

    show(seatedData);
    expect(screen.getByTestId('turn-count')).toHaveTextContent('turn 0 of 26');
    expect(screen.getByTestId('ended-reason')).not.toHaveTextContent('predates');
  });

  it('a seated run before t01 shows no document card and no timeline', () => {
    const { unmount } = show(seatedData);
    expect(screen.getByTestId('roster-crew_owner')).toBeInTheDocument();
    expect(screen.queryByTestId('expand-all')).toBeNull();
    expect(screen.queryByText(/^Transcript/)).toBeNull();
    expect(screen.queryByTestId('verdict-pending')).toBeNull();
    // doc-diff's placeholders never sit under a seated committee: neither the
    // "names the file it is reviewing on its first reduction" text nor the
    // not-captured card.
    expect(screen.queryByTestId('diff-no-artifacts')).toBeNull();
    expect(screen.queryByTestId('doc-not-captured')).toBeNull();
    unmount();

    // C6: the Document card comes with t01 even once `open` kept the original,
    // which it does on every live run. The fetch stub only makes a regression
    // that draws the card fail on these assertions, not on a network error.
    vi.stubGlobal('fetch', vi.fn((u: string) =>
      String(u).includes('/view/artifact') ? ok({ text: '# Proposal\n\nold clause\n' }) : new Promise(() => {}),
    ));
    show({ ...seatedData, document: { ...DOC, steps: [], final: null } });
    expect(screen.getByTestId('roster-crew_owner')).toBeInTheDocument();
    expect(screen.queryByText(/^Document/)).toBeNull();
    expect(screen.queryByTestId('step-original')).toBeNull();
    expect(screen.queryByTestId('diff-no-artifacts')).toBeNull();
    expect(screen.queryByTestId('expand-all')).toBeNull();
  });

  it('roster rows say why each seat is there and who put it forward', () => {
    const { unmount } = show(seatedData);

    // One labelled list, one item per seat: a screen reader hears "Committee, list, 7 items".
    expect(
      within(screen.getByRole('list', { name: 'Committee' })).getAllByRole('listitem').map((li) => li.dataset.testid),
    ).toEqual(seatedData.roster.map((p) => `roster-${p.role}`));

    expect(screen.getByTestId('roster-crew_owner')).toHaveTextContent('Noor Haddad');
    expect(screen.getByTestId('roster-crew_owner')).toHaveTextContent('Owner, team-owned crews');
    expect(screen.getByTestId('roster-why-crew_owner')).toHaveTextContent(
      'why: owns the team-owned crews the proposal would federate',
    );
    // The earliest selector whose list held the seat, by name.
    expect(screen.getByTestId('roster-nominated-tpm')).toHaveTextContent('put forward by Maya Okonkwo');
    expect(screen.getByTestId('roster-nominated-crew_owner')).toHaveTextContent(
      'put forward by Ruth Delgado',
    );
    expect(screen.getByTestId('roster-nominated-staff_ic')).toHaveTextContent(
      'put forward by Dana Whitfield',
    );
    expect(screen.getByTestId('roster-nominated-owner')).toHaveTextContent('fixed seat');
    expect(screen.getByTestId('roster-why-junior_ic')).toHaveTextContent(
      'why: applies the edits the owner delegates',
    );
    unmount();

    show(fallbackData);
    expect(screen.getByTestId('roster-nominated-pm')).toHaveTextContent('default seat');
    expect(screen.getByTestId('roster-why-pm')).toHaveTextContent(
      'why: in the default committee (the chair gave no usable list)',
    );
    expect(screen.getByTestId('roster-nominated-manager')).toHaveTextContent('fixed seat');
  });

  it('the metrics variant keeps its empty state before t01', () => {
    // The Metrics tab counts turns, and there are none yet.
    render(<CommitteeView runId="run-2" data={seatedData} refetch={noop} variant="metrics" />);

    expect(screen.getByText('Nothing said yet')).toBeInTheDocument();
    expect(screen.queryByTestId('committee-metrics')).toBeNull();
    expect(screen.queryByTestId('committee-view')).toBeNull();
  });

  it('a legacy run shows no why and no put forward', () => {
    const { unmount } = show(run2);
    for (const p of run2.roster) {
      expect(screen.getByTestId(`roster-${p.role}`)).toBeInTheDocument();
      expect(screen.queryByTestId(`roster-why-${p.role}`)).toBeNull();
      expect(screen.queryByTestId(`roster-nominated-${p.role}`)).toBeNull();
    }
    unmount();

    // A payload from before selection has no `selection` key at all. Every
    // guard reads it as null, so an empty one is still "Nothing said yet".
    const before: CommitteeData = { ...run2, timeline: [], verdict: null, document: EMPTY_DOC };
    delete before.selection;
    show(before);
    expect(screen.getByText('Nothing said yet')).toBeInTheDocument();
    expect(screen.queryByTestId('committee-view')).toBeNull();
  });

  it("a seat's worker-written text stays plain text, and a derived seat cannot pass for the owner", () => {
    // A derived seat's name, title and rationale are a selector's words. This
    // one copies the owner's name and title and carries markup, a Markdown
    // image, a link and bold: all of it must read as the literal text, never
    // as an element, and its slug and "derived seat" must sit beside it.
    const hostile = '<img src=x onerror=alert(1)> ![x](http://evil.test/x.png) [owner](javascript:alert(1)) **bold**';
    const impostor = {
      ...seatedData.roster.find((p) => p.role === 'crew_owner')!,
      name: 'Maya Okonkwo',
      title: 'Staff Engineer & proposal owner',
      rationale: hostile,
    };
    show({
      ...seatedData,
      roster: seatedData.roster.map((p) => (p.role === 'crew_owner' ? impostor : p)),
    });

    const row = screen.getByTestId('roster-crew_owner');
    expect(screen.getByTestId('roster-why-crew_owner')).toHaveTextContent(`why: ${hostile}`);
    expect(row.querySelector('img, a, strong, script, iframe')).toBeNull();
    expect(row).toHaveTextContent('crew_owner · derived seat');
    // The real owner's row carries no such marker, and neither does a library seat.
    expect(screen.getByTestId('roster-owner')).not.toHaveTextContent('derived');
    expect(screen.getByTestId('roster-tpm')).not.toHaveTextContent('derived');
  });
});

// --- the Selection card (committee-selection Task 15) --------------------------

describe('CommitteeView selection card', () => {
  // vitest's jsdom URL has its own createObjectURL; restore, never delete
  // (deleting exposes Node's, which throws on a jsdom Blob). The mermaid case
  // assigns vi.fn()s.
  const realCreate = (URL as any).createObjectURL;
  const realRevoke = (URL as any).revokeObjectURL;
  afterEach(() => {
    (URL as any).createObjectURL = realCreate;
    (URL as any).revokeObjectURL = realRevoke;
  });

  /** `selection.current` on s3, once the owner's and the manager's stages are kept. */
  const RATIFYING = { role: 'senior_director', name: 'Dana Whitfield', verb: 'ratifying' as const };

  /** `b` comes after `a` in document order. */
  const follows = (a: Element, b: Element) =>
    Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);

  it('the selection card shows each stage with its proposed seats', () => {
    const { unmount } = show(cardData);
    const card = screen.getByTestId('selection-card');
    const listed = (n: number) =>
      within(within(card).getByTestId(`selection-proposed-${n}`))
        .getAllByRole('listitem')
        .map((li) => li.textContent);

    expect(within(card).getByTestId('selection-stage-1')).toHaveTextContent('Maya Okonkwo (owner) proposes');
    expect(within(card).getByTestId('selection-stage-1')).toHaveTextContent(
      'Federation lands on the program, the roadmap and one security zone.',
    );
    expect(within(card).getByTestId('selection-stage-2')).toHaveTextContent('Ruth Delgado (manager) amends');
    expect(within(card).getByTestId('selection-stage-3')).toHaveTextContent(
      'Dana Whitfield (senior_director) ratifies',
    );
    expect(listed(1)[1]).toBe('pm: Elena Vargas, Product Manager. Why: owns the roadmap slot it takes');
    // The derived seat says so beside its slug (orchestrator decision 12).
    expect(listed(3)).toEqual([
      'tpm: Sam Iyer, Technical Program Manager. Why: owns the schedule this would move',
      'staff_ic: Priya Raman, Staff Engineer. Why: carries the on-call cost of a second crew',
      'zone_owner · derived seat: Lena Brandt, Owner, eu-west security zone. Why: federation crosses her zone boundary',
    ]);
    // Under the roster before t01, where it is the last card ...
    expect(follows(screen.getByTestId('roster-owner'), card)).toBe(true);
    unmount();

    // ... and from t01 on, still under the roster and above the transcript.
    show({ ...seatedWithTurnsData, selection: cardData.selection });
    const populated = screen.getByTestId('selection-card');
    expect(follows(screen.getByTestId('roster-owner'), populated)).toBe(true);
    expect(follows(populated, screen.getByTestId('expand-all'))).toBe(true);
  });

  it('a stage that broke the rules shows the voice flag badge and renders its mermaid figure', async () => {
    (URL as any).createObjectURL = vi.fn(() => 'blob:selection-1');
    (URL as any).revokeObjectURL = vi.fn();
    const real = (window as any).HermesUI;
    const draw = vi.fn(async () => '<svg xmlns="http://www.w3.org/2000/svg"></svg>');
    (window as any).HermesUI = { ...real, renderMermaid: draw };
    const sel = cardData.selection!;
    const flagged = {
      ...cardData,
      selection: {
        ...sel,
        stages: sel.stages.map((st) =>
          st.stage === 2
            ? {
                ...st,
                badges: ['voice_flag', 'retaken'],
                take: 2,
                takes: 2,
                violations: ['over_cap'],
                segments: [
                  ...st.segments,
                  {
                    kind: 'mermaid' as const,
                    source: 'graph TD; zone-->crew',
                    caption: 'who carries the cost',
                    description: 'the zone feeds the crew',
                  },
                ],
              }
            : st,
        ),
      },
    };
    const { unmount } = show(flagged);
    try {
      const s2 = screen.getByTestId('selection-stage-2');

      expect(within(s2).getByText('broke the ground rules')).toBeInTheDocument();
      expect(within(s2).getByText('retaken')).toBeInTheDocument();
      expect(await within(s2).findByAltText('who carries the cost')).toHaveAttribute('src', 'blob:selection-1');
      expect(draw).toHaveBeenCalledWith('graph TD; zone-->crew');
      expect(within(screen.getByTestId('selection-stage-1')).queryByText('broke the ground rules')).toBeNull();
    } finally {
      // Before afterEach restores the originals: unmounting revokes the blob URL.
      unmount();
      (window as any).HermesUI = real;
    }
  });

  it('the considered list names who represents each stakeholder, or says everyone was seated', () => {
    const { unmount } = show(cardData);
    const items = within(screen.getByTestId('selection-considered')).getAllByRole('listitem');

    // The reason's own full stop is not doubled, and no representative means no sentence.
    expect(items.map((li) => li.textContent)).toEqual([
      "Product Manager: the roadmap slot is Sam's call this half. Represented by Sam Iyer.",
      'Legal: no contract or licence question in this proposal. Not represented.',
    ]);
    unmount();

    show({ ...cardData, selection: { ...cardData.selection!, considered: [] } });
    expect(screen.getByTestId('selection-considered')).toHaveTextContent('Everyone considered was seated.');
    expect(within(screen.getByTestId('selection-considered')).queryAllByRole('listitem')).toHaveLength(0);
  });

  it('a fallback shows the default committee banner', () => {
    const { unmount } = show(cardData);
    expect(screen.queryByTestId('selection-fallback')).toBeNull();
    unmount();

    show({ ...cardData, selection: { ...cardData.selection!, state: 'fallback', fallback: 'chair_failed' } });
    expect(screen.getByTestId('selection-fallback')).toHaveTextContent(
      'Default committee: selection fell back (the chair gave no usable list)',
    );
  });

  it('a lost selection says the meeting was lost', () => {
    show(lostData);
    const card = screen.getByTestId('selection-card');

    expect(within(card).getByTestId('selection-lost')).toHaveTextContent('Selection stopped: the meeting was lost.');
    // Nobody was seated, so the card says nothing about who was considered.
    expect(within(card).queryByTestId('selection-considered')).toBeNull();
    expect(within(card).queryByTestId('selection-fallback')).toBeNull();
  });

  it("a derived seat's turn counts in the metrics turns per seat", () => {
    render(<CommitteeView runId="run-2" data={seatedWithTurnsData} refetch={noop} variant="metrics" />);
    const crew = seatedWithTurnsData.roster.find((p) => p.role === 'crew_owner');

    expect(crew).toBeDefined();
    expect(screen.getByTestId('turns-crew_owner')).toHaveTextContent(crew!.name);
    // `/1$/`, not `1`: a turn taken but not delivered would end "1 not delivered".
    expect(screen.getByTestId('turns-crew_owner')).toHaveTextContent(/1$/);
    expect(screen.queryByTestId('selection-card')).toBeNull();
  });

  it("a derived seat is marked on its transcript row and its turns-taken row, even under the owner's name", () => {
    // From t01 a transcript row and a Metrics row show only the speaker's name
    // (and title), both a selector's words for a derived seat. The name check
    // is exact, so "Maya Okonkwo." with a full stop passes it: only the slug
    // and the marker beside it tell this seat from the owner (decision 12).
    const copy = { name: 'Maya Okonkwo.', title: 'Staff Engineer & proposal owner.' };
    const impostor: CommitteeData = {
      ...seatedWithTurnsData,
      roster: seatedWithTurnsData.roster.map((p) => (p.role === 'crew_owner' ? { ...p, ...copy } : p)),
      timeline: seatedWithTurnsData.timeline.map((e) => (e.role === 'crew_owner' ? { ...e, ...copy } : e)),
    };
    const { unmount } = show(impostor);

    expect(screen.getByTestId('entry-5')).toHaveTextContent('Maya Okonkwo.');
    expect(screen.getByTestId('entry-5')).toHaveTextContent('crew_owner · derived seat');
    for (const n of [1, 2, 3, 4]) expect(screen.getByTestId(`entry-${n}`)).not.toHaveTextContent('derived');
    // The stage lists mark the seat too, and only that seat.
    const ratified = within(screen.getByTestId('selection-proposed-3')).getAllByRole('listitem');
    expect(ratified.map((li) => li.textContent?.split(':')[0])).toEqual([
      'crew_owner · derived seat',
      'tpm',
      'staff_ic',
    ]);
    unmount();

    render(<CommitteeView runId="run-2" data={impostor} refetch={noop} variant="metrics" />);
    expect(screen.getByTestId('turns-crew_owner')).toHaveTextContent('Maya Okonkwo.');
    expect(screen.getByTestId('turns-crew_owner')).toHaveTextContent('crew_owner · derived seat');
    expect(screen.getByTestId('turns-crew_owner')).toHaveTextContent(/1$/);
    for (const role of ['owner', 'senior_director', 'manager', 'tpm']) {
      expect(screen.getByTestId(`turns-${role}`)).not.toHaveTextContent('derived');
    }
  });

  it('the card counts the seats and stakeholders its caps cut, and only when they cut some', () => {
    const { unmount } = show(cardData);
    expect(within(screen.getByTestId('selection-card')).queryByText(/not listed/)).toBeNull();
    unmount();

    const sel = cardData.selection!;
    const cut = (over: Partial<typeof sel>, dropped = 0) =>
      show({
        ...cardData,
        selection: {
          ...sel,
          stages: sel.stages.map((st) => (st.stage === 1 ? { ...st, proposed_dropped: dropped } : st)),
          ...over,
        },
      });

    const second = cut({ considered_dropped: 3, invalid_dropped: 2 }, 4);
    expect(within(screen.getByTestId('selection-stage-1')).getByText('4 more not listed.')).toBeInTheDocument();
    expect(within(screen.getByTestId('selection-stage-2')).queryByText(/not listed/)).toBeNull();
    // The list items stay exactly the entries: a count is not a seat.
    expect(within(screen.getByTestId('selection-proposed-1')).getAllByRole('listitem')).toHaveLength(3);
    const considered = screen.getByTestId('selection-considered');
    expect(within(considered).getAllByRole('listitem')).toHaveLength(2);
    expect(considered).toHaveTextContent('3 more considered, not listed.');
    expect(considered).toHaveTextContent('2 more invalid entries, not listed.');
    second.unmount();

    // Nothing listed but something cut is not "everyone was seated" (thread.append_seated).
    cut({ considered: [], invalid_dropped: 2 });
    expect(screen.getByTestId('selection-considered')).not.toHaveTextContent('Everyone considered was seated.');
    expect(screen.getByTestId('selection-considered')).toHaveTextContent('2 more invalid entries, not listed.');
    expect(screen.getByTestId('selection-considered')).not.toHaveTextContent('more considered');
  });

  it('every worker-written string on the card stays plain text, and no image leaves the run', () => {
    // Seat names, titles and rationales, stakeholders, reasons and a
    // representative's name are all worker-written (a derived seat names
    // itself). The stage prose is too, and a reference voice's scan missed
    // reaches the card undisarmed here, so only Segments stands in its way.
    const hostile = '<img src=x onerror=alert(1)> ![x](http://evil.test/x.png) [owner](javascript:alert(1)) **bold**';
    const sel = cardData.selection!;
    show({
      ...cardData,
      selection: {
        ...sel,
        stages: sel.stages.map((st) => ({
          ...st,
          body: hostile,
          segments: [{ kind: 'text' as const, text: hostile }],
          proposed: st.proposed.map((p) => ({ ...p, name: hostile, title: `${hostile} lead`, rationale: hostile })),
          not_seated: st.not_seated?.map((n) => ({
            ...n,
            stakeholder: hostile,
            reason: hostile,
            represented_by_name: n.represented_by_name && hostile,
          })),
        })),
        considered: sel.considered.map((c) => ({
          ...c,
          stakeholder: hostile,
          reason: hostile,
          represented_by_name: c.represented_by_name && hostile,
        })),
      },
    });
    const card = screen.getByTestId('selection-card');

    for (const n of [1, 2, 3]) {
      const list = within(card).getByTestId(`selection-proposed-${n}`);
      expect(list).toHaveTextContent(`: ${hostile}, ${hostile} lead. Why: ${hostile}`);
      expect(list.querySelector('img, a, strong, script, iframe')).toBeNull();
    }
    const considered = within(card).getByTestId('selection-considered');
    expect(considered).toHaveTextContent(`${hostile}: ${hostile}. Represented by ${hostile}`);
    expect(considered.querySelector('img, a, strong, script, iframe')).toBeNull();
    const leftOut = within(card).getByTestId('selection-left-out-2');
    expect(leftOut).toHaveTextContent(`Left out: ${hostile}: ${hostile}. Represented by ${hostile}`);
    expect(leftOut.querySelector('img, a, strong, script, iframe')).toBeNull();
    // The prose is Markdown, as a turn's is, but it draws no image and runs no script.
    expect(card.querySelector('img, script, iframe')).toBeNull();
    for (const a of card.querySelectorAll('a')) expect(a.getAttribute('href') ?? '').not.toMatch(/^javascript:/i);
  });

  it('a seat named from its title shows the title once on a stage list, as cast.label does', () => {
    // validate names a nameless derived seat from its title (clipped with "…"
    // past NAME_MAX), so "Crew Owner, Crew Owner" would be the reduction's
    // name and title side by side.
    const long = 'Crew fleet owner for the federated scheduling layer and every region';
    const seat = (role: string, name: string, title: string) => ({
      role, name, title, rationale: 'runs the crews', source: 'derived' as const,
    });
    const sel = cardData.selection!;
    show({
      ...cardData,
      selection: {
        ...sel,
        stages: sel.stages.map((st) =>
          st.stage === 1
            ? {
                ...st,
                proposed: [
                  seat('crew_owner', 'Crew Owner', 'Crew Owner'),
                  seat('crew_lead', 'Crew Lead.', 'Crew Lead'),
                  seat('long_ops', `${long.slice(0, 59).trimEnd()}…`, long),
                  seat('kai_ops', 'Kai Brandt', 'Crew Owner'),
                ],
              }
            : st,
        ),
      },
    });

    expect(
      within(screen.getByTestId('selection-proposed-1'))
        .getAllByRole('listitem')
        .map((li) => li.textContent),
    ).toEqual([
      'crew_owner · derived seat: Crew Owner. Why: runs the crews',
      'crew_lead · derived seat: Crew Lead. Why: runs the crews',
      `long_ops · derived seat: ${long}. Why: runs the crews`,
      'kai_ops · derived seat: Kai Brandt, Crew Owner. Why: runs the crews',
    ]);
  });

  it('a derived proposal is marked while selecting and after the chair dropped it', () => {
    // The roster marks only a seated derived seat, so each listed seat carries its own source.
    const listed = (n: number) =>
      within(screen.getByTestId(`selection-proposed-${n}`))
        .getAllByRole('listitem')
        .map((li) => li.textContent?.split(':')[0]);
    const two = seatedData.selection!.stages.slice(0, 2);

    // On s3: the fixed four are in the room and nobody else is seated yet.
    const { unmount } = show({ ...selectingData, selection: { ...selectingData.selection!, stages: two, current: RATIFYING } });
    expect(listed(2)).toEqual(['tpm', 'crew_owner · derived seat']);
    unmount();

    // The chair's worker failed, so the default committee sits without the manager's seat.
    const fell = show(fallbackData);
    expect(listed(2)).toEqual(['tpm', 'crew_owner · derived seat']);
    fell.unmount();

    // Seated, but the chair dropped a stage-1 seat, so it never reached the roster.
    const sel = cardData.selection!;
    const ops = {
      role: 'ops_owner', name: 'Ines Park', title: 'Owner, ops tooling',
      rationale: 'runs the tooling', source: 'derived' as const,
    };
    show({
      ...cardData,
      selection: {
        ...sel,
        stages: sel.stages.map((st) => (st.stage === 1 ? { ...st, proposed: [...st.proposed, ops] } : st)),
      },
    });
    expect(listed(1)).toEqual(['tpm', 'pm', 'zone_owner · derived seat', 'ops_owner · derived seat']);
  });

  it("a derived representative is marked beside its name, even one spelled like the owner's", () => {
    // A Cyrillic "а": the name passes an exact check, so only the slug tells it from the owner.
    const lookalike = 'Mаya Okonkwo';
    const sel = cardData.selection!;
    show({
      ...cardData,
      roster: cardData.roster.map((p) => (p.role === 'zone_owner' ? { ...p, name: lookalike } : p)),
      selection: {
        ...sel,
        considered: sel.considered.map((c) =>
          c.role === null ? { ...c, represented_by: 'zone_owner', represented_by_name: lookalike } : c,
        ),
      },
    });

    expect(
      within(screen.getByTestId('selection-considered')).getAllByRole('listitem').map((li) => li.textContent),
    ).toEqual([
      "Product Manager: the roadmap slot is Sam's call this half. Represented by Sam Iyer.",
      `Legal: no contract or licence question in this proposal. Represented by ${lookalike} (zone_owner · derived seat).`,
    ]);
  });

  it("keeps the danger colour on a stage's undelivered badge, as a timeline row does", () => {
    show(fallbackData);

    const badge = within(screen.getByTestId('selection-stage-3')).getByText('no turn delivered');
    expect(badge.getAttribute('style')).toContain('--status-danger');
  });

  it("a derived seat's floor request is marked beside its name on the Metrics tab", () => {
    const asked: CommitteeData = {
      ...seatedWithTurnsData,
      timeline: seatedWithTurnsData.timeline.map((e) =>
        e.n === 3 || e.n === 5 ? { ...e, badges: ['request_floor'] } : e,
      ),
    };
    render(<CommitteeView runId="run-2" data={asked} refetch={noop} variant="metrics" />);

    expect(screen.getByTestId('floor-ask-5')).toHaveTextContent(
      'Noor Haddad (crew_owner · derived seat) asked on turn 5 · still waiting',
    );
    expect(screen.getByTestId('floor-ask-3')).toHaveTextContent('Ruth Delgado asked on turn 3 · still waiting');
  });

  it('the Document card marks a derived reviewer who raised an edit', () => {
    const step = { delivered: true, verified: true, owner_turn: null, provenance: 'recorded' as const };
    const doc: DocumentBlock = {
      name: 'federation-future.md',
      captured: true,
      original: { path: 'doc/00-original.md', bytes: 30 },
      steps: [
        { ...step, turn: 7, path: 'doc/t07.md', bytes: 31, reviewer_turn: 5 },
        { ...step, turn: 8, path: 'doc/t08.md', bytes: 32, reviewer_turn: 3 },
      ],
      final: null,
      dropped_delegation: null,
    };
    show({ ...seatedWithTurnsData, document: doc });

    fireEvent.click(screen.getByTestId('step-7'));
    expect(screen.getByTestId('step-raised')).toHaveTextContent('raised by Noor Haddad (crew_owner · derived seat)');
    fireEvent.click(screen.getByTestId('step-8'));
    expect(screen.getByTestId('step-raised')).toHaveTextContent('raised by Ruth Delgado');
    expect(screen.getByTestId('step-raised')).not.toHaveTextContent('derived');
  });

  it('a stage kept after a retake says which take and what it broke, as a transcript row does', () => {
    const sel = cardData.selection!;
    show({
      ...cardData,
      selection: {
        ...sel,
        stages: sel.stages.map((st) => (st.stage === 2 ? { ...st, take: 2, takes: 2, violations: ['over_cap'] } : st)),
      },
    });

    expect(screen.getByTestId('selection-kept-take-2')).toHaveTextContent(
      `kept take 2 of 2; broke: ${violationText(['over_cap'])}`,
    );
    // A first take kept clean says nothing.
    expect(screen.queryByTestId('selection-kept-take-1')).toBeNull();
  });

  it('the considered list is labelled, and no empty list stands in for counts alone', () => {
    const { unmount } = show(cardData);
    expect(screen.getByRole('list', { name: 'Considered, not seated' })).toBeInTheDocument();
    // Section's title is no heading, so nothing on the card claims a level under it.
    expect(within(screen.getByTestId('selection-card')).queryAllByRole('heading')).toHaveLength(0);
    unmount();

    show({ ...cardData, selection: { ...cardData.selection!, considered: [], considered_dropped: 3 } });
    const considered = screen.getByTestId('selection-considered');
    expect(considered).toHaveTextContent('3 more considered, not listed.');
    expect(within(considered).queryByRole('list')).toBeNull();
  });

  it("a stage whose list could seat nobody says why, in its thread entry's words", () => {
    const sel = cardData.selection!;
    const code: Record<number, string> = { 1: 'too_few', 2: 'no_block', 3: 'unparseable' };
    const { unmount } = show({
      ...cardData,
      selection: { ...sel, stages: sel.stages.map((st) => ({ ...st, proposed: [], code: code[st.stage] })) },
    });

    // selection.fallback_words, as the thread entry says it.
    expect(screen.getByTestId('selection-code-1')).toHaveTextContent('no usable seat list: no valid seats');
    expect(screen.getByTestId('selection-code-2')).toHaveTextContent('no usable seat list: no hermes-selection block');
    expect(screen.getByTestId('selection-code-3')).toHaveTextContent(
      'no usable seat list: a hermes-selection block that did not parse',
    );
    unmount();

    // A usable list says nothing, and an undelivered stage (no_answer) says it through its badge and body.
    show(fallbackData);
    expect(screen.queryByTestId('selection-code-1')).toBeNull();
    expect(screen.queryByTestId('selection-code-3')).toBeNull();
  });

  it('while a selector works, the card says who is choosing and that seat holds the floor', () => {
    const { unmount } = show(selectingData);
    const card = screen.getByTestId('selection-card');

    // After the stage already kept: the manager's is the one being written.
    expect(within(card).getByTestId('selection-current')).toHaveTextContent('Ruth Delgado is amending the committee.');
    expect(follows(within(card).getByTestId('selection-stage-1'), within(card).getByTestId('selection-current'))).toBe(
      true,
    );
    expect(screen.getByTestId('roster-manager')).toHaveTextContent('has the floor');
    expect(screen.getByTestId('roster-owner')).toHaveTextContent('has not spoken');
    unmount();

    // Once seated, or once lost, nobody is choosing.
    const seated = show(cardData);
    expect(screen.queryByTestId('selection-current')).toBeNull();
    expect(screen.getByTestId('roster-manager')).toHaveTextContent('has not spoken');
    seated.unmount();
    show(lostData);
    expect(screen.queryByTestId('selection-current')).toBeNull();
    expect(screen.getByTestId('roster-manager')).toHaveTextContent('has not spoken');
  });

  it('each stage lists who it left out and who speaks for them, and counts what it cut', () => {
    const items = (n: number) =>
      within(screen.getByTestId(`selection-left-out-${n}`))
        .getAllByRole('listitem')
        .map((li) => li.textContent);
    const { unmount } = show(cardData);

    // Under the stage's own list, with the reason's full stop not doubled.
    expect(items(2)).toEqual(["Left out: Product Manager: the roadmap slot is Sam's call this half. Represented by Sam Iyer."]);
    expect(items(3)).toEqual(['Left out: Legal: no contract or licence question in this proposal. Not represented.']);
    expect(screen.getByRole('list', { name: 'Left out by Ruth Delgado' })).toBeInTheDocument();
    expect(follows(screen.getByTestId('selection-proposed-2'), screen.getByTestId('selection-left-out-2'))).toBe(true);
    // A stage that left nobody out draws no list, and nothing was cut.
    expect(screen.queryByTestId('selection-left-out-1')).toBeNull();
    expect(within(screen.getByTestId('selection-card')).queryByText(/left out, not listed|invalid entries/)).toBeNull();
    unmount();

    // While selecting only the fixed four are seated, so a derived representative
    // is marked off the stage's own list; and each count shows only when it cut some.
    const sel = seatedData.selection!;
    const amends = {
      ...sel.stages[1],
      not_seated: [
        { ...cardData.selection!.stages[1].not_seated![0], represented_by: 'crew_owner', represented_by_name: 'Noor Haddad' },
      ],
      not_seated_dropped: 2,
      invalid_count: 3,
    };
    show({ ...selectingData, selection: { ...selectingData.selection!, stages: [sel.stages[0], amends], current: RATIFYING } });
    expect(items(2)).toEqual([
      "Left out: Product Manager: the roadmap slot is Sam's call this half. Represented by Noor Haddad (crew_owner · derived seat).",
    ]);
    const s2 = screen.getByTestId('selection-stage-2');
    expect(within(s2).getByText('2 more left out, not listed.')).toBeInTheDocument();
    expect(within(s2).getByText('3 invalid entries, not listed.')).toBeInTheDocument();
    expect(within(screen.getByTestId('selection-stage-1')).queryByText(/not listed/)).toBeNull();
  });

  it('a fallback card lists what it could not seat, and no seat list for a chair that gave none', () => {
    show(fallbackData);

    expect(
      within(screen.getByTestId('selection-considered')).getAllByRole('listitem').map((li) => li.textContent),
    ).toEqual(['Owner, team-owned crews: not in the default committee (the chair gave no usable list). Not represented.']);
    expect(screen.queryByTestId('selection-proposed-3')).toBeNull();
    expect(screen.getByTestId('selection-proposed-2')).toBeInTheDocument();
  });
});

