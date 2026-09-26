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
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { setToken, clearToken } from '../api/auth';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import CommitteeView from '../../../playbooks/committee/view/src/CommitteeView';
import { run2, midRun, edgeTurns } from '../../../playbooks/committee/view/src/run2.fixture';
import DocumentHistory, {
  diffLines,
  type DocumentBlock,
  type StepId,
} from '../../../playbooks/committee/view/src/Diff';
import Verdict from '../../../playbooks/committee/view/src/Verdict';

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
const VERDICT = {
  text: [
    '# Decision — Hermes federation layer',
    '',
    '## Verdict: do not approve. Drop.',
    '',
    'I am ruling against my own turn-01 position, and I will say why in the record.',
  ].join('\n'),
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
  json: {},
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
    // `/reductions?` with the question mark, not `/reductions`. The accept POST
    // goes to /api/reductions/21/accept, which CONTAINS "/reductions" — matched
    // loosely, the mock answers the POST with the lookup array and the
    // accept test can never pass.
    fetchMock = vi.fn((url: string) =>
      String(url).includes('/reductions?') ? ok([DECISION_ROW]) : ok({ review_state: 'accepted' }),
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
        '/api/runs/run-2/reductions?phase=decision',
        expect.anything(),
      ),
    );
  });

  it('is accurate that the stamp settles nothing', async () => {
    render(<Verdict runId="run-2" verdict={VERDICT} />);
    const stampNote = await screen.findByTestId('stamp-note');
    expect(stampNote).toHaveTextContent('settles no tickets and changes no run state');
    expect(stampNote).toHaveTextContent('lands nothing and reverts nothing');
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

  it('rejects without a confirm prompt, because it fails nothing', async () => {
    fetchMock.mockImplementation((url: string) =>
      String(url).includes('/reductions?') ? ok([DECISION_ROW]) : ok({ review_state: 'rejected' }),
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
      expect(fetchMock).toHaveBeenCalledWith('/api/runs/run-2/reductions?phase=decision', {
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
      expect(fetchMock).toHaveBeenCalledWith('/api/runs/run-2/reductions?phase=decision', {
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
      String(url).includes('/reductions?')
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
      String(url).includes('/reductions?') ? ok([DECISION_ROW]) : ok({ review_state: 'rejected' }),
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
      String(url).includes('/reductions?')
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
      if (String(url).includes('/reductions?')) {
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
      String(url).includes('/reductions?') ? ok([DECISION_ROW]) : ok({}),
    );
    render(<Verdict runId="run-2" verdict={VERDICT} />);
    fireEvent.click(await screen.findByRole('button', { name: /accept/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(screen.queryByTestId('stamp-state')).toBeNull();
    expect(screen.getByRole('button', { name: /accept/i })).toBeInTheDocument();
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

/** The view's own wiring, minus the rest of the view: it holds the selection. */
function History({
  doc = DOC,
  start = 'original',
  intact = true,
  onOpenTurn = noop,
}: {
  doc?: DocumentBlock;
  start?: StepId;
  intact?: boolean | null;
  onOpenTurn?: (n: number) => void;
}) {
  const [selected, setSelected] = useState<StepId>(start);
  return (
    <DocumentHistory
      runId="run-2"
      document={doc}
      timeline={run2.timeline}
      intact={intact}
      selected={selected}
      onSelect={setSelected}
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

  it('says snapshots were not captured, and fetches nothing', () => {
    render(<History doc={{ ...DOC, captured: false }} />);
    expect(screen.getByTestId('doc-not-captured')).toHaveTextContent(
      'Document snapshots were not captured for this run.',
    );
    expect(screen.queryByTestId('doc-stepper')).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('shows the original and says no edit was delegated when there are no steps', async () => {
    render(<History doc={{ ...DOC, steps: [], final: null }} />);
    expect(screen.getByTestId('doc-no-edits')).toHaveTextContent(
      'No edit has been delegated yet. The original stands as it was.',
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
    fireEvent.keyDown(screen.getByTestId('doc-stepper'), { key: 'ArrowLeft' });
    expect(screen.getByTestId('step-3')).toHaveAttribute('aria-current', 'step');
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

    fireEvent.click(screen.getByTestId('step-9'));
    expect(screen.getByTestId('step-verdict')).toHaveTextContent('re-check not recorded');
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
    expect(screen.getByTestId('step-delegated')).toHaveTextContent(
      'delegated: Rewrite §2 "When to reach for it"',
    );
    expect(screen.getByTestId('step-confirmed')).toHaveTextContent('Rewrote §2 into two triggers');
    expect(screen.queryByTestId('step-provenance')).toBeNull();

    fireEvent.click(screen.getByTestId('goto-t01'));
    fireEvent.click(screen.getByTestId('goto-t02'));
    fireEvent.click(screen.getByTestId('goto-t03'));
    expect(onOpenTurn.mock.calls).toEqual([[1], [2], [3]]);
  });

  it('says a link was inferred from turn order, and when who raised it was not recorded', () => {
    render(<History start={6} />);
    expect(screen.getByTestId('step-provenance')).toHaveTextContent('(inferred from turn order)');
    expect(screen.getByTestId('step-raised')).toHaveTextContent('raised by Ruth Delgado');

    fireEvent.click(screen.getByTestId('step-9'));
    expect(screen.getByTestId('step-raised')).toHaveTextContent('who raised this was not recorded');
    expect(screen.queryByTestId('step-delegated')).toBeNull();
    expect(screen.getByTestId('step-confirmed')).toHaveTextContent('no turn delivered');
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

  it.each([
    ['in_session', 'Latest so far — the meeting is still in session'],
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

  it('caps how many rows reach the DOM, and says it did', async () => {
    // `diffLines` is hard-bounded and fast; the RENDER is what does not scale.
    const big = Array.from({ length: 6000 }, (_, i) => `line ${i}`).join('\n');
    fetchMock.mockImplementation((u: string) =>
      ok({ text: pathOf(u) === 'doc/00-original.md' ? big : `${big}\nextra` }),
    );
    render(<History start={3} />);
    const rows = await screen.findByTestId('diff-rows');
    expect(rows.children).toHaveLength(5001); // 5000 rows plus the footer
    expect(screen.getByTestId('diff-rows-capped')).toHaveTextContent('1001 more rows');
    expect(screen.getByTestId('diff-counts')).toHaveTextContent('1 line added');
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
    const scrolled = vi.fn();
    Element.prototype.scrollIntoView = scrolled;
    show(captured);
    fireEvent.click(screen.getByTestId('step-3'));
    fireEvent.click(screen.getByTestId('goto-t02'));

    expect(
      within(screen.getByTestId('entry-2')).getByRole('button', { expanded: true }),
    ).toBeInTheDocument();
    expect(scrolled).toHaveBeenCalled();
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
