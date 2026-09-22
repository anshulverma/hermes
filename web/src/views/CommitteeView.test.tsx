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
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import CommitteeView from '../../../playbooks/committee/view/src/CommitteeView';
import { run2, midRun, edgeTurns } from '../../../playbooks/committee/view/src/run2.fixture';
import ArtifactDiff, { diffLines } from '../../../playbooks/committee/view/src/Diff';
import Verdict from '../../../playbooks/committee/view/src/Verdict';

const noop = () => {};

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

  it('distinguishes a cap from a close', () => {
    // run-2 itself ended `owner closed` — turn 20 carries `close: true`, and a
    // close outranks the cap even on the turn the cap would have stopped
    // (playbooks/committee/playbook.py, `_decision`). The cap wording therefore
    // needs a fixture of its own.
    show({ ...run2, progress: { ...run2.progress, ended: 'turn cap' } });

    expect(screen.getByTestId('ended-reason')).toHaveTextContent(
      'Ended: turn cap. The meeting ran out of turns before anyone closed it.',
    );
  });

  it('shows who holds the floor and who is behind them mid-run', () => {
    show(midRun);

    expect(screen.getByTestId('turn-count')).toHaveTextContent('turn 8 of 20');
    expect(screen.getByTestId('floor-holder')).toHaveTextContent('tpm has the floor');
    expect(screen.getByTestId('floor-queue')).toHaveTextContent('tl · staff_ic');
    expect(screen.getByTestId('ended-reason')).toHaveTextContent('Still in session.');
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
    expect(screen.getByTestId('roster-tl')).toHaveTextContent('waiting to speak');
    expect(screen.getByTestId('roster-pm')).toHaveTextContent('has not spoken');
    expect(screen.getByTestId('roster-owner')).toHaveTextContent('spoke');
  });

  it('carries each persona their current stance', () => {
    show();

    expect(screen.getByTestId('stance-staff_ic')).toHaveTextContent(
      'Do not fund: §4 asserts a credential scoping this system does not have.',
    );
  });

  it('shows a persona who stated no stance as having none, not as neutral', () => {
    show();

    expect(screen.getByTestId('stance-tpm')).toHaveTextContent('no stance stated');
    expect(screen.getByTestId('stance-tpm')).not.toHaveTextContent('neutral');
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
  simulation: true as const,
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
    fetchMock = vi.fn(() => ok([DECISION_ROW]));
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
    render(<ArtifactDiff runId="run-2" artifacts={ARTIFACTS} />);
    const banner = screen.getByTestId('diff-original-untouched');
    expect(banner).toHaveTextContent('The original is never modified');
    expect(banner).toHaveTextContent('docs/specs/federation-future.md');
    expect(banner).toHaveTextContent('runs/run-2/revised-federation-future.md');
    expect(banner).toHaveTextContent('a recommendation, not a landed change');
  });

  it('does not fetch either artifact until asked', () => {
    render(<ArtifactDiff runId="run-2" artifacts={ARTIFACTS} />);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /show the diff/i })).toHaveTextContent(
      '11.1 KB → 18.7 KB',
    );
  });

  it('fetches both sides and renders the changed lines', async () => {
    render(<ArtifactDiff runId="run-2" artifacts={ARTIFACTS} />);
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

  it('reports a failed fetch instead of an empty diff', async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve({ ok: false, status: 400, json: () => Promise.resolve({ detail: 'bad which' }) }),
    );
    render(<ArtifactDiff runId="run-2" artifacts={ARTIFACTS} />);
    fireEvent.click(screen.getByRole('button', { name: /show the diff/i }));

    expect(await screen.findByTestId('diff-error')).toHaveTextContent('bad which');
  });

  it('says there is no revised copy rather than showing an empty one', () => {
    render(<ArtifactDiff runId="run-2" artifacts={{ original: ARTIFACTS.original, revised: null }} />);
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
    render(<ArtifactDiff runId="run-2" artifacts={{ original: null, revised: null }} />);
    expect(screen.getByTestId('diff-no-artifacts')).toHaveTextContent(
      'No artifact has been recorded for this run yet',
    );
    expect(screen.queryByTestId('diff-original-untouched')).toBeNull();
    expect(screen.queryByRole('button', { name: /show the diff/i })).toBeNull();
  });
});
