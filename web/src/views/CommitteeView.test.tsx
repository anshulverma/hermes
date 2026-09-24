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
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { setToken, clearToken } from '../api/auth';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import CommitteeView from '../../../playbooks/committee/view/src/CommitteeView';
import { run2, midRun, edgeTurns } from '../../../playbooks/committee/view/src/run2.fixture';
import ArtifactDiff, { diffLines } from '../../../playbooks/committee/view/src/Diff';
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
    artifacts: { original: null, revised: null },
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
      artifacts: { original: null, revised: null },
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

const ARTIFACTS = {
  original: { name: 'docs/specs/federation-future.md', bytes: 11397 },
  revised: { name: 'runs/run-2/revised-federation-future.md', bytes: 19100 },
};

describe('ArtifactDiff', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn((url: string) =>
      String(url).includes('which=original')
        ? ok({ text: 'intro\nold clause\ntail' })
        : ok({ text: 'intro\nnew clause\nextra clause\ntail' }),
    );
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('states that the original is never modified, before any diff is loaded', () => {
    render(<ArtifactDiff runId="run-2" artifacts={ARTIFACTS} intact={true} />);
    const banner = screen.getByTestId('diff-original-untouched');
    expect(banner).toHaveTextContent('The original is never modified');
    expect(banner).toHaveTextContent('docs/specs/federation-future.md');
    expect(banner).toHaveTextContent('runs/run-2/revised-federation-future.md');
    expect(banner).toHaveTextContent('a recommendation, not a landed change');
  });

  it('says a delegated edit lands in the revised copy, not that it landed', () => {
    // WB-I2, and finding 3.2's defect reprinted in the UI: the past tense is a
    // claim about THIS run's outcome, and the e2e screenshot printed it
    // directly under `turn 07 · junior_ic DID NOT APPLY`.
    render(<ArtifactDiff runId="run-2" artifacts={ARTIFACTS} intact={true} />);
    const banner = screen.getByTestId('diff-original-untouched');
    expect(banner).toHaveTextContent('Every delegated edit lands in the revised copy');
    expect(banner).not.toHaveTextContent('landed in the revised copy');
  });

  it('does not promise byte-for-byte before a decision has re-checked it', () => {
    // null is "nothing has checked", which is not "yes". The design rule is
    // still true and still worth saying; the measurement is not in yet.
    render(<ArtifactDiff runId="run-2" artifacts={ARTIFACTS} intact={null} />);
    const banner = screen.getByTestId('diff-original-untouched');
    expect(banner).toHaveTextContent('is meant to be byte-for-byte');
    expect(banner).not.toHaveTextContent('federation-future.md is byte-for-byte');
  });

  it('does not fetch either artifact until asked', () => {
    render(<ArtifactDiff runId="run-2" artifacts={ARTIFACTS} intact={true} />);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /show the diff/i })).toHaveTextContent(
      '11.1 KB → 18.7 KB',
    );
  });

  it('fetches both sides and renders the changed lines', async () => {
    render(<ArtifactDiff runId="run-2" artifacts={ARTIFACTS} intact={true} />);
    fireEvent.click(screen.getByRole('button', { name: /show the diff/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/runs/run-2/view/artifact?which=original',
        expect.anything(),
      ),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/runs/run-2/view/artifact?which=revised',
      expect.anything(),
    );

    const rows = await screen.findByTestId('diff-rows');
    expect(rows).toHaveTextContent('- old clause');
    expect(rows).toHaveTextContent('+ new clause');
    expect(rows).toHaveTextContent('+ extra clause');
    expect(screen.getByTestId('diff-counts')).toHaveTextContent(
      '2 lines added, 1 removed — all of it in the revised copy',
    );
  });

  it('says "1 line added", not "1 lines added"', async () => {
    // 9.10 / WB-m7, visible in the e2e screenshot.
    fetchMock.mockImplementation((url: string) =>
      String(url).includes('which=original') ? ok({ text: 'a\nc' }) : ok({ text: 'a\nb\nc' }),
    );
    render(<ArtifactDiff runId="run-2" artifacts={ARTIFACTS} intact={true} />);
    fireEvent.click(screen.getByRole('button', { name: /show the diff/i }));

    expect(await screen.findByTestId('diff-counts')).toHaveTextContent('1 line added, 0 removed');
  });

  it('caps how many rows reach the DOM, and says it did', async () => {
    // 9.6: `diffLines` is hard-bounded and fast; the RENDER is what does not
    // scale — one <div> per line, measured at 20,001 nodes and 3.4 s to mount.
    const big = Array.from({ length: 6000 }, (_, i) => `line ${i}`).join('\n');
    fetchMock.mockImplementation((url: string) =>
      String(url).includes('which=original') ? ok({ text: big }) : ok({ text: `${big}\nextra` }),
    );
    render(<ArtifactDiff runId="run-2" artifacts={ARTIFACTS} intact={true} />);
    fireEvent.click(screen.getByRole('button', { name: /show the diff/i }));

    const rows = await screen.findByTestId('diff-rows');
    expect(rows.children).toHaveLength(5001); // 5000 rows plus the footer
    expect(screen.getByTestId('diff-rows-capped')).toHaveTextContent('1001 more rows');
    expect(screen.getByTestId('diff-counts')).toHaveTextContent('1 line added');
  });

  it('says so when the server cut one of the copies short', async () => {
    // The `truncated` key the artifact route grew: a diff of two prefixes
    // presented as a diff of two files is the same confident partial claim
    // this card exists to stop.
    fetchMock.mockImplementation((url: string) =>
      String(url).includes('which=original')
        ? ok({ text: 'intro\nold clause', truncated: true })
        : ok({ text: 'intro\nnew clause', truncated: false }),
    );
    render(<ArtifactDiff runId="run-2" artifacts={ARTIFACTS} intact={true} />);
    fireEvent.click(screen.getByRole('button', { name: /show the diff/i }));

    expect(await screen.findByTestId('diff-truncated')).toHaveTextContent('diff of two prefixes');
  });

  it('claims nothing about truncation when neither copy was cut', async () => {
    render(<ArtifactDiff runId="run-2" artifacts={ARTIFACTS} intact={true} />);
    fireEvent.click(screen.getByRole('button', { name: /show the diff/i }));

    await screen.findByTestId('diff-rows');
    expect(screen.queryByTestId('diff-truncated')).toBeNull();
  });

  it('reports a failed fetch instead of an empty diff', async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve({ ok: false, status: 400, json: () => Promise.resolve({ detail: 'bad which' }) }),
    );
    render(<ArtifactDiff runId="run-2" artifacts={ARTIFACTS} intact={true} />);
    fireEvent.click(screen.getByRole('button', { name: /show the diff/i }));

    expect(await screen.findByTestId('diff-error')).toHaveTextContent('bad which');
  });

  it('says there is no revised copy rather than showing an empty one', () => {
    render(<ArtifactDiff runId="run-2" artifacts={{ original: ARTIFACTS.original, revised: null }} intact={null} />);
    expect(screen.getByTestId('diff-no-revised')).toHaveTextContent(
      'No edit has been delegated yet',
    );
    expect(screen.queryByRole('button', { name: /show the diff/i })).toBeNull();
  });

  it('survives an original nothing has named yet', () => {
    // `_artifacts` returns {"original": None, "revised": None} when no reduction
    // carries a path — which is every run in phase `open`, and `original.name`
    // would throw straight into the error boundary. The whole view's empty state
    // normally catches this, but the type says null, so the branch must exist.
    render(<ArtifactDiff runId="run-2" artifacts={{ original: null, revised: null }} intact={null} />);
    expect(screen.getByTestId('diff-no-artifacts')).toHaveTextContent(
      'No artifact has been recorded for this run yet',
    );
    expect(screen.queryByTestId('diff-original-untouched')).toBeNull();
    expect(screen.queryByRole('button', { name: /show the diff/i })).toBeNull();
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
