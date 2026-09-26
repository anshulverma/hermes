/**
 * The committee view, end to end, in a real browser.
 *
 * This is the only layer that can prove the loader chain: the SPA injects a
 * <script> tag, the UMD bundle reads window.React and window.ReactJSXRuntime off
 * the host, and the component renders on the host's single React instance. jsdom
 * cannot show any of it -- a second React copy fails at runtime with "Invalid
 * hook call", an error no unit test ever sees.
 *
 * It needs a committee run to look at. There is no live `claude` here, so the
 * fixture rows below go straight into the server's queue.db. `make
 * ui-test-committee` starts a throwaway control plane on its own HERMES_HOME,
 * points HERMES_URL and HERMES_E2E_HOME at it, and tears it down after.
 * Without HERMES_E2E_HOME there is nothing to seed, so the file skips rather
 * than failing a plain `make ui-test`.
 */
import { test, expect, type Page } from '@playwright/test';
import { DatabaseSync } from 'node:sqlite';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

/** Where the home is on THIS machine -- where the fixture is written. The
 *  container sees the same directory at /hermes-home. */
const HOME = process.env.HERMES_E2E_HOME ?? '';

const RUN = 'committee-e2e';
/** Host paths, as the master records them -- and, like the real thing, paths no
 *  process in the container can open: the artifact lives outside the home and
 *  the revised copy is named by the HOST's home. The view and the route must
 *  find every version by the run's own doc/ layout instead, which is the
 *  container 404 this spec exists to catch. */
const ORIGINAL = '/nonexistent-host/workspace/proposal.md';
const REVISED = `${HOME}/runs/${RUN}/revised/proposal.md`;

/** A real edit's shape: one line deep in a long document, so an unfolded diff
 *  opened at the top would show only the title, and Edit 1 must open on it. */
const BODY = (staffing: string) =>
  [
    '# Consolidate the ingest pipelines',
    '',
    ...Array.from({ length: 150 }, (_, i) => `Background, paragraph ${i + 1}.`),
    `Staffing: ${staffing} engineers for two quarters.`,
    ...Array.from({ length: 50 }, (_, i) => `Risks, paragraph ${i + 1}.`),
    '',
  ].join('\n');
const ORIGINAL_TEXT = BODY('six');
const REVISED_TEXT = BODY('two');

const ACTION_1 = 'Cut the staffing ask from six engineers to two.';
const ACTION_2 = 'Name the Q3 migration freeze in the sequencing section.';

// Seven turns, not the twenty of the measured run: enough to prove ordering, a
// delegation that applied, one that did not, a turn nobody delivered, a floor
// request nobody got to, and two personas holding stances.
//
// CAP is 7, not the default 30, so the meeting really did run out of turns:
// with cap 30 the Progress card read "turn 7 of 30" directly above "Ended: turn
// cap. The meeting ran out of turns", the component's own gate disagreed with
// the note it was printing, and line 205 below asserted that incoherence as
// passing. `reduce` puts the cap on every turn reduction (`_cap` prefers it
// over the environment), so seeding it here is what a real run does.
const CAP = 7;

// `answers_turn` and `delegated_by_turn` exactly as the playbook writes them:
// always present, an int only on an owner turn (the reviewer it answers) and a
// junior turn (the owner turn it applied), null everywhere else.
const TURNS = [
  { turn: 1, role: 'senior_director', delivered: true,
    body: 'The bet is plausible. The staffing line is fiction.',
    stance: 'Leaning no while the ask is six engineers.',
    request_floor: false, delegate: false, close: false, action: null, verified: null,
    answers_turn: null, delegated_by_turn: null },
  { turn: 2, role: 'owner', delivered: true,
    body: 'Conceded. I will cut the ask and say so in the copy.',
    stance: 'Willing to cut scope to land this quarter.',
    request_floor: false, delegate: true, close: false, action: ACTION_1, verified: null,
    answers_turn: 1, delegated_by_turn: null },
  { turn: 3, role: 'junior_ic', delivered: true,
    body: 'Applied the staffing cut to the revised copy.',
    stance: null,
    request_floor: false, delegate: false, close: false, action: null, verified: true,
    answers_turn: null, delegated_by_turn: 2 },
  { turn: 4, role: 'manager', delivered: false,
    body: '', stance: null,
    request_floor: false, delegate: false, close: false, action: null, verified: null,
    answers_turn: null, delegated_by_turn: null },
  { turn: 5, role: 'tpm', delivered: true,
    body: 'Sequencing still collides with the Q3 migration freeze.',
    stance: 'No until the freeze window is named in the plan.',
    request_floor: true, delegate: false, close: false, action: null, verified: null,
    answers_turn: null, delegated_by_turn: null },
  { turn: 6, role: 'owner', delivered: true,
    body: 'Fair. Delegating the freeze-window edit.',
    stance: 'Willing to cut scope to land this quarter.',
    request_floor: false, delegate: true, close: false, action: ACTION_2, verified: null,
    answers_turn: 5, delegated_by_turn: null },
  { turn: 7, role: 'junior_ic', delivered: true,
    body: 'Re-read the sequencing section and made no change.',
    stance: null,
    request_floor: false, delegate: false, close: false, action: null, verified: false,
    answers_turn: null, delegated_by_turn: 6 },
];

/** What each snapshot under runs/<RUN>/doc/ holds. t07 DID NOT APPLY, so it is t03's text. */
const SNAPSHOTS: Record<string, string> = {
  '00-original.md': ORIGINAL_TEXT,
  't03.md': REVISED_TEXT,
  't07.md': REVISED_TEXT,
};

/** Verbatim `playbooks/committee/playbook.py:109-112`. */
const SIMULATION =
  'This verdict is a simulation produced by AI personas reading one file. It is ' +
  'not an approval, not a sign-off, and carries no authority: a human decides.';

const DECISION = {
  verdict: [
    'Approve with conditions: the ask is two engineers and the freeze is acknowledged.',
    `- re-check of turn 03 (junior_ic): APPLIED — delegated: ${ACTION_1}`,
    `- re-check of turn 07 (junior_ic): DID NOT APPLY — delegated: ${ACTION_2}`,
    // tpm, because turn 5 is the only `request_floor` in the fixture. It said
    // `pm`, so the verdict card and the roster named different people.
    '- dropped_floor_requests (the review ended before their turn came): tpm',
    SIMULATION,
  ].join('\n\n'),
  delivered: true,
  rechecks: [
    { turn: 3, action: ACTION_1, verified: true },
    { turn: 7, action: ACTION_2, verified: false },
  ],
  artifact_intact: true,
  dropped_delegation: null,
  dropped_delegation_turn: null,
  dropped_floor_requests: ['tpm'],
  error: null,
  artifact: ORIGINAL,
  revised: REVISED,
  ended: 'turn cap',
};

/** Idempotent: the run's rows are deleted before they are written again. */
function seed(): void {
  // The snapshots the playbook writes at `open` and after each junior turn --
  // and nothing at ORIGINAL or REVISED, so a server that still opened a
  // recorded path would 404 here exactly as it did in the container. 0700 and
  // 0600, as `state_dir` and `write_snapshot` make them: the container has to
  // read the private files production writes, not world-readable ones.
  rmSync(`${HOME}/runs/${RUN}`, { recursive: true, force: true });
  mkdirSync(`${HOME}/runs/${RUN}/doc`, { recursive: true, mode: 0o700 });
  for (const [name, text] of Object.entries(SNAPSHOTS)) {
    writeFileSync(`${HOME}/runs/${RUN}/doc/${name}`, text, { mode: 0o600 });
  }

  const db = new DatabaseSync(`${HOME}/queue.db`);
  try {
    const now = Date.now() / 1000;
    db.prepare('DELETE FROM reductions WHERE run_id = ?').run(RUN);
    db.prepare('DELETE FROM runs WHERE id = ?').run(RUN);
    db.prepare(
      `INSERT INTO runs (id, playbook, site, base_ref, config_json, state, phase,
                         created_at, updated_at)
       VALUES (?, 'committee', 'local', 'main', '{}', 'done', 'decision', ?, ?)`,
    ).run(RUN, now, now);

    // `phase` is the one `record_reduction` writes: the run's phase at the
    // time, so `t{NN}-{role}` for a turn and `decision` for the decision. The
    // verdict card no longer filters on it (it reads every reduction and takes
    // the last `decision`, so a verdict kept under `decision-take2` is found),
    // but seeding the real value keeps the fixture honest.
    const insert = db.prepare(
      `INSERT INTO reductions (run_id, phase, kind, json, review_state, created_at, updated_at)
       VALUES (?, ?, ?, ?, 'pending', ?, ?)`,
    );
    TURNS.forEach((t, i) => {
      const json = { ...t, cap: CAP, error: null, artifact: ORIGINAL, revised: REVISED };
      const phase = `t${String(t.turn).padStart(2, '0')}-${t.role}`;
      insert.run(RUN, phase, 'turn', JSON.stringify(json), now + i, now + i);
    });
    insert.run(
      RUN, 'decision', 'decision', JSON.stringify(DECISION),
      now + TURNS.length, now + TURNS.length,
    );
  } finally {
    db.close();
  }
}

/** A second run whose owner turn carries one checked image. The reduction
 *  records names only, never a host path: the server finds the file under its
 *  own home (the container's /hermes-home) by the run's images/ layout. */
const VOICE_RUN = 'committee-e2e-voice';
const SVG =
  '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20"><rect width="40" height="20" fill="#6ea8fe"/></svg>';

function seedVoice(): void {
  // 0700 and 0600, as `thread.images_dir` and a worker's own write leave them.
  rmSync(`${HOME}/runs/${VOICE_RUN}`, { recursive: true, force: true });
  mkdirSync(`${HOME}/runs/${VOICE_RUN}/images`, { recursive: true, mode: 0o700 });
  writeFileSync(`${HOME}/runs/${VOICE_RUN}/images/t02-owner.svg`, SVG, { mode: 0o600 });

  // What `check_images` records for the owner's own file: `ok` true, so the
  // view merges it onto the reference by position and renders an <img>, and the
  // sha256 of the bytes it checked, which the image route then insists on.
  const image = {
    kind: 'image', name: 't02-owner.svg', ref: 'images/t02-owner.svg',
    caption: 'staffing curve', description: 'engineers per week, flat after week 6', ok: true,
    sha256: createHash('sha256').update(SVG).digest('hex'),
  };
  const diagram = {
    kind: 'mermaid', name: '', ref: '', caption: 'the pipeline', description: 'two stages', ok: true,
  };
  const turn = (n: number, role: string, body: string, images: unknown[]) => ({
    turn: n, role, delivered: true, body, stance: null, request_floor: false, delegate: false,
    close: false, action: null, verified: null, answers_turn: null, delegated_by_turn: null,
    cap: CAP, error: null, artifact: ORIGINAL, revised: REVISED,
    take: 1, takes: 1, kept: true, voice: { words: 6, images }, violations: [], flags: [],
  });

  const db = new DatabaseSync(`${HOME}/queue.db`);
  try {
    const now = Date.now() / 1000;
    db.prepare('DELETE FROM reductions WHERE run_id = ?').run(VOICE_RUN);
    db.prepare('DELETE FROM runs WHERE id = ?').run(VOICE_RUN);
    db.prepare(
      `INSERT INTO runs (id, playbook, site, base_ref, config_json, state, phase,
                         created_at, updated_at)
       VALUES (?, 'committee', 'local', 'main', '{}', 'running', 't03-tpm', ?, ?)`,
    ).run(VOICE_RUN, now, now);
    const insert = db.prepare(
      `INSERT INTO reductions (run_id, phase, kind, json, review_state, created_at, updated_at)
       VALUES (?, ?, 'turn', ?, 'pending', ?, ?)`,
    );
    insert.run(VOICE_RUN, 't01-senior_director', JSON.stringify(turn(1, 'senior_director',
      'Defer it: the staffing line is fiction.\nFigure: the pipeline\n```mermaid\ngraph TD; A-->B\n```\n'
      + 'Description: two stages', [diagram])), now, now);
    insert.run(VOICE_RUN, 't02-owner', JSON.stringify(turn(2, 'owner',
      'Conceded: staffing is the risk.\n![staffing curve](images/t02-owner.svg)\n'
      + 'Description: engineers per week, flat after week 6', [image])), now + 1, now + 1);
  } finally {
    db.close();
  }
}

/** A third run: its committee is seated and nobody has spoken yet. The chair's
 *  ratification has reduced, `next_phase` minted t01 and that worker has not
 *  answered, so there is one final `selection` reduction and no turn. That is
 *  the state that used to render "Nothing said yet". */
const SELECTION_RUN = 'committee-e2e-selection';
/** 2 x 4 reviewers + 16. The container runs without HERMES_COMMITTEE_MAX_TURNS,
 *  so its env fallback is 30: a 24 can only have come off the reduction. */
const SELECTION_CAP = 24;
const SECURITY_WHY = 'the federation layer opens a trust boundary between teams';
/** A derived seat's rationale is a selector's words, stored as written: the tag
 *  must show as typed and its image must never load. */
const CREW_WHY =
  'owns a crew the federation layer would schedule work onto <img src="https://outside.example/crew.png">';
/** The chair's own figure points off-site, so voice never passed it: it stays a
 *  placeholder and the browser never fetches it. */
const PAGER = 'https://outside.example/pager.png';

type Nominator = 'owner' | 'manager' | 'senior_director' | 'fixed' | 'default';

/** A C3 seat record, as `_apply_selection` installs it and the final reduction
 *  carries it. The view reads role, name, title, rationale, nominated_by and
 *  source, so the brief fields stay empty here. */
function seatRecord(
  role: string, name: string, title: string, rationale: string,
  nominated_by: Nominator, source: 'fixed' | 'library' | 'derived',
) {
  return {
    role, name, title, altitude: '', goal: '', ambition: '', stake: '', lens: '', style: '',
    rationale, nominated_by, source,
  };
}

/** Roster order: owner, the reviewers in opening order, junior_ic. */
const SEATED = [
  seatRecord('owner', 'Maya Okonkwo', 'Staff Engineer & proposal owner',
    'wrote the proposal and answers every reviewer', 'fixed', 'fixed'),
  seatRecord('senior_director', 'Dana Whitfield', 'Senior Director of Engineering',
    'chairs the committee and delivers its decision', 'fixed', 'fixed'),
  seatRecord('manager', 'Ruth Delgado', 'Engineering Manager',
    'manages the owner and staffs whatever is decided', 'fixed', 'fixed'),
  seatRecord('security', 'Nadia Haddad', 'Security Engineer', SECURITY_WHY, 'owner', 'library'),
  seatRecord('crew_owner', 'Iris Kovacs', 'Engineering Lead, crew owner team', CREW_WHY,
    'manager', 'derived'),
  seatRecord('junior_ic', 'Alex Moreau', 'Software Engineer',
    'makes the edits the owner delegates', 'fixed', 'fixed'),
];

/** The chair's stage-3 take, kept on her third take with the off-site figure
 *  flagged (voice keeps the last take and runs on): C5's per-stage keys plus the
 *  final ones. voice.words is the prose alone; the figure lines are not prose. */
const RATIFIED = {
  stage: 3, role: 'senior_director', final: true, delivered: true,
  body: 'Seat both. Security signs off the trust boundary and the crew owner carries the work.\n'
    + `![pager rota](${PAGER})\nDescription: who carries the pager each week`,
  parsed: true, code: null,
  proposed: SEATED.filter((s) => s.source !== 'fixed')
    .map(({ role, name, title, rationale }) => ({ role, name, title, rationale })),
  error: null, cap: SELECTION_CAP, take: 3, takes: 3, kept: true,
  voice: {
    words: 15,
    images: [{
      kind: 'image', name: PAGER, ref: PAGER, caption: 'pager rota',
      description: 'who carries the pager each week', ok: false,
    }],
  },
  violations: ['image_missing'], flags: [],
  seated: SEATED,
  reviewers: ['senior_director', 'manager', 'security', 'crew_owner'],
  considered: [{
    stakeholder: 'On-call SRE', role: null,
    reason: 'the crews keep their own pager, so their owner speaks for on-call',
    represented_by: 'crew_owner',
  }],
  fallback: null,
};

/** Idempotent, like `seed()`. Rows only: the off-site figure has no file. */
function seedSelection(): void {
  const db = new DatabaseSync(`${HOME}/queue.db`);
  try {
    const now = Date.now() / 1000;
    db.prepare('DELETE FROM reductions WHERE run_id = ?').run(SELECTION_RUN);
    db.prepare('DELETE FROM runs WHERE id = ?').run(SELECTION_RUN);
    db.prepare(
      `INSERT INTO runs (id, playbook, site, base_ref, config_json, state, phase,
                         created_at, updated_at)
       VALUES (?, 'committee', 'local', 'main', '{}', 'running', 't01-senior_director', ?, ?)`,
    ).run(SELECTION_RUN, now, now);
    // The phase `record_reduction` writes for the chair's ratification.
    db.prepare(
      `INSERT INTO reductions (run_id, phase, kind, json, review_state, created_at, updated_at)
       VALUES (?, 's3-senior_director-take3', 'selection', ?, 'pending', ?, ?)`,
    ).run(SELECTION_RUN, JSON.stringify(RATIFIED), now, now);
  } finally {
    db.close();
  }
}

/** Open the committee tab for the seeded run and wait for real content. */
async function openCommittee(page: Page): Promise<void> {
  await page.goto(`/#playbook?run=${RUN}`);
  await expect(page.getByLabel('Hermes')).toBeVisible();
  await expect(page.getByText('Dana Whitfield').first()).toBeVisible({ timeout: 15000 });
}

test.skip(HOME === '', 'set HERMES_E2E_HOME -- use `make ui-test-committee`');

test.beforeAll(() => {
  if (!HOME) return;
  seed();
  seedVoice();
  seedSelection();
});

test('the seeded run is served with a view', async ({ request }) => {
  const detail = await (await request.get(`/api/runs/${RUN}`)).json();
  expect(detail.playbook).toBe('committee');
  // False here means the server process has no `committee` registered: the
  // container needs HERMES_PLAYBOOK_MODULES=playbooks.committee (`make up`).
  expect(detail.has_view).toBe(true);

  const asset = await request.get('/api/playbooks/committee/view.js');
  expect(asset.status()).toBe(200);
  // Not content-length: GZipMiddleware(minimum_size=500) compresses this.
  expect(asset.headers()['content-type']).toContain('text/javascript');
  expect(asset.headers()['x-content-type-options']).toBe('nosniff');
  expect(await asset.text()).toContain('HermesView_committee');

  const data = await (await request.get(`/api/runs/${RUN}/view`)).json();
  expect(data.kind).toBe('committee');
  expect(data.timeline).toHaveLength(7);
  expect(data.timeline[0].name).toBe('Dana Whitfield');
  expect(data.progress.ended).toBe('turn cap');
  // The cap rides on the reduction, so the server process answers with the
  // run's own cap and not with whatever HERMES_COMMITTEE_MAX_TURNS it was
  // started without. turn === cap is what makes "turn cap" a true sentence.
  expect(data.progress.cap).toBe(CAP);
  expect(data.progress.turn).toBe(CAP);
  // Reconstructed from the turns by `_floor`, not read from the decision: the
  // one request_floor in the fixture is tpm's.
  expect(data.verdict.dropped_floor_requests).toEqual(['tpm']);

  // Every version, found by the run's own doc/ layout under the server's home.
  const doc = data.document;
  expect(doc.name).toBe('proposal.md');
  expect(doc.captured).toBe(true);
  expect(doc.original).toEqual({ path: 'doc/00-original.md', bytes: ORIGINAL_TEXT.length });
  expect(doc.steps.map((s: { turn: number }) => s.turn)).toEqual([3, 7]);
  expect(doc.steps[0]).toMatchObject({
    path: 'doc/t03.md', bytes: REVISED_TEXT.length, verified: true,
    owner_turn: 2, reviewer_turn: 1, provenance: 'recorded',
  });
  expect(doc.steps[1]).toMatchObject({
    path: 'doc/t07.md', verified: false, owner_turn: 6, reviewer_turn: 5, provenance: 'recorded',
  });
  // t07 did not apply, so Final is what t03 left.
  expect(doc.final).toEqual({
    path: 'doc/t03.md', turn: 3, bytes: REVISED_TEXT.length, ruling: 'awaiting_ruling',
  });

  for (const version of [doc.original, ...doc.steps, doc.final]) {
    const response = await request.get(`/api/runs/${RUN}/view/artifact?path=${version.path}`);
    expect(response.status(), version.path).toBe(200);
    expect((await response.json()).text).toBe(SNAPSHOTS[version.path.slice('doc/'.length)]);
  }
  expect((await request.get(`/api/runs/${RUN}/view/artifact?path=..%2F..%2Fetc%2Fpasswd`)).status())
    .toBe(400);
});

test('the committee tab renders the meeting oldest-first', async ({ page }) => {
  await openCommittee(page);
  await expect(page.locator('[data-testid="tab-playbook"]')).toBeVisible();

  // Every persona who spoke is named, including the one whose turn failed.
  for (const name of ['Dana Whitfield', 'Maya Okonkwo', 'Alex Moreau', 'Ruth Delgado', 'Sam Iyer']) {
    await expect(page.getByText(name).first()).toBeVisible();
  }

  // Oldest-first, measured in the layout rather than in the DOM: Outputs sorts
  // newest-id-first and that is exactly backwards for a conversation.
  const first = await page.getByText(TURNS[0].body).first().boundingBox();
  const later = await page.getByText(TURNS[4].body).first().boundingBox();
  expect(first!.y).toBeLessThan(later!.y);

  // A stance that was stated, and the verdict's disclaimer.
  await expect(page.getByText('Leaning no while the ask is six engineers.').first()).toBeVisible();
  await expect(page.getByText(/simulation/i).first()).toBeVisible();
  // "Ended: turn cap" AND "turn 7 of 7" on the same card. Asserting the note
  // alone pinned a state the progress bar contradicted.
  await expect(page.getByText(/turn cap/i).first()).toBeVisible();
  await expect(page.locator('[data-testid="turn-count"]')).toHaveText(`turn ${CAP} of ${CAP}`);

  // The delegated action on the turn that delegated it -- criterion 7's first
  // half, and the one surface that exists only mid-run.
  await expect(page.locator('[data-testid="action-2"]')).toContainText(ACTION_1);
  await expect(page.locator('[data-testid="timeline-recheck-3"]')).toContainText('APPLIED');
  await expect(page.locator('[data-testid="timeline-recheck-7"]')).toContainText('DID NOT APPLY');

  // The verdict card found ITS reduction: it reads the run's reductions and
  // stamps the last `decision` one, and without one renders `stamp-error`.
  await expect(page.locator('[data-testid="stamp-note"]')).toBeVisible();
  await expect(page.locator('[data-testid="stamp-error"]')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /accept/i })).toBeVisible();
  await expect(page.locator('[data-testid="verdict-recheck-3"]')).toContainText('APPLIED');
});

test('the document stepper walks every version, served inside the container', async ({ page }) => {
  await openCommittee(page);
  const verdict = page.locator('[data-testid="step-verdict"]');
  const whole = page.locator('[data-testid="doc-markdown"]');

  // Edit 1: a diff against the original, raised by turn 1's senior director,
  // delegated by the owner and made by the junior IC, each named.
  await page.locator('[data-testid="step-3"]').click();
  await expect(page.locator('[data-testid="step-3"]')).toHaveAttribute('aria-current', 'step');
  const rows = page.locator('[data-testid="diff-rows"]');
  await expect(rows).toContainText('- Staffing: six engineers for two quarters.');
  await expect(rows).toContainText('+ Staffing: two engineers for two quarters.');
  // The change is 150 lines down, and it is on screen with nobody scrolling:
  // the unchanged lines fold away and the step opens on its first change.
  await expect(rows.getByText('- Staffing: six engineers for two quarters.', { exact: true }))
    .toBeInViewport();
  await expect(rows.locator('[data-testid="diff-fold"]').first())
    .toHaveText('⋯ 149 unchanged lines');
  await expect(verdict).toContainText('APPLIED');
  await expect(page.locator('[data-testid="step-raised"]')).toContainText('Dana Whitfield');
  await expect(page.locator('[data-testid="step-delegated"]'))
    .toContainText(`delegated by Maya Okonkwo: ${ACTION_1}`);
  await expect(page.locator('[data-testid="step-confirmed"]')).toContainText('Alex Moreau:');
  await expect(page.locator('[data-testid="doc-unreadable"]')).toHaveCount(0);

  // Edit 2 did not apply: t07 is t03's bytes, so there is nothing to diff.
  await page.locator('[data-testid="step-7"]').click();
  await expect(page.locator('[data-testid="step-7"]')).toHaveAttribute('aria-current', 'step');
  await expect(page.locator('[data-testid="diff-none"]')).toBeVisible();
  await expect(verdict).toContainText('DID NOT APPLY');

  // Final: the whole document as t03 left it, under the pending ruling.
  await page.locator('[data-testid="step-final"]').click();
  await expect(page.locator('[data-testid="final-label"]')).toContainText('Proposed — awaiting your ruling');
  await expect(whole).toContainText('Staffing: two engineers for two quarters.');

  // Original: the whole document as the committee was handed it.
  await page.locator('[data-testid="step-original"]').click();
  await expect(page.locator('[data-testid="original-label"]'))
    .toHaveText('Original — as the committee was handed it');
  await expect(whole).toContainText('Staffing: six engineers for two quarters.');
});

test('a turn image loads through the run images route, served inside the container', async ({ page, request }) => {
  const direct = await request.get(`/api/runs/${VOICE_RUN}/view/artifact?path=images/t02-owner.svg`);
  expect(direct.status()).toBe(200);
  expect(direct.headers()['content-type']).toBe('image/svg+xml');
  expect(direct.headers()['content-security-policy']).toContain('sandbox');
  // Opened directly it downloads; an <img> ignores the header, as below proves.
  expect(direct.headers()['content-disposition']).toContain('attachment');
  expect(await direct.text()).toBe(SVG);

  // Image requests only: the design system's Inter @font-face is an outside
  // fetch of its own, unrelated to what a worker's turn can make the browser load.
  const images: string[] = [];
  page.on('request', (r) => { if (r.resourceType() === 'image') images.push(r.url()); });

  await page.goto(`/#playbook?run=${VOICE_RUN}`);
  await expect(page.getByText('Maya Okonkwo').first()).toBeVisible({ timeout: 15000 });
  const entry = page.locator('[data-testid="entry-2"]');
  await entry.locator('button').first().click();

  const img = entry.locator('img[alt="staffing curve"]');
  await expect(img).toHaveAttribute(
    'src', new RegExp(`/api/runs/${VOICE_RUN}/view/artifact\\?path=images%2Ft02-owner\\.svg`));
  // Decoded, not merely requested: a 400, a 404 or a CSP block leaves naturalWidth 0.
  await expect
    .poll(() => img.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth > 0))
    .toBe(true);
  await expect(entry.getByText('engineers per week, flat after week 6')).toBeVisible();

  // The listener saw the image load (so an empty list below is not vacuous),
  // and nothing on the page fetched an image from another origin.
  const origin = new URL(page.url()).origin;
  expect(images.some((u) => u.includes(`/api/runs/${VOICE_RUN}/view/artifact?path=images%2Ft02-owner.svg`))).toBe(true);
  const outside = images.filter((u) => /^https?:/.test(u) && new URL(u).origin !== origin);
  expect(outside, outside.join('\n')).toEqual([]);
});

test('a mermaid diagram draws as a decoded blob image in a real browser', async ({ page }) => {
  await page.goto(`/#playbook?run=${VOICE_RUN}`);
  await expect(page.getByText('Dana Whitfield').first()).toBeVisible({ timeout: 15000 });
  const entry = page.locator('[data-testid="entry-1"]');
  await entry.locator('button').first().click();

  // The host's mermaid chunk loads, draws, passes the markup screen, and the
  // blob decodes: a failed draw shows the source instead and has no <img>.
  const img = entry.locator('[data-testid="figure-mermaid"] img[src^="blob:"]');
  await expect(img).toHaveAttribute('alt', 'the pipeline', { timeout: 15000 });
  await expect
    .poll(() => img.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth > 0))
    .toBe(true);
  await expect(entry.locator('[data-testid="mermaid-error"]')).toHaveCount(0);
  await expect(entry.getByText('two stages')).toBeVisible();
});

test('one injected script tag, and the host React is the only React', async ({ page }) => {
  const fatal: string[] = [];
  page.on('pageerror', (err) => fatal.push(String(err)));

  await openCommittee(page);

  const tag = page.locator('script[src*="/api/playbooks/committee/view.js"]');
  await expect(tag).toHaveCount(1);

  // The UMD evaluated and published its global -- proof the tag loaded, not that
  // a bundler inlined it.
  expect(await page.evaluate(() => (window as any).HermesView_committee != null)).toBe(true);

  // Leaving the tab and coming back must not inject a second copy.
  await page.evaluate((run) => { window.location.hash = `outputs?run=${run}`; }, RUN);
  await expect(page.locator('[data-testid="tab-playbook"]')).toBeVisible();
  await page.evaluate((run) => { window.location.hash = `playbook?run=${run}`; }, RUN);
  await expect(page.getByText('Dana Whitfield').first()).toBeVisible();
  await expect(tag).toHaveCount(1);

  // A second React copy does not fail a build or a jsdom test -- it throws here.
  const hookErrors = fatal.filter((e) => /Invalid hook call|Minified React error/i.test(e));
  expect(hookErrors, hookErrors.join('\n')).toEqual([]);
});

test('the committee tab shows the seated roster before the first turn', async ({ page, request }) => {
  // The server half, inside the container: the baked view.py builds the roster
  // and the selection block from the one reduction, with no turn to lean on.
  const data = await (await request.get(`/api/runs/${SELECTION_RUN}/view`)).json();
  expect(data.timeline).toEqual([]);
  expect(data.selection?.state).toBe('seated');
  expect(data.progress.cap).toBe(SELECTION_CAP);
  expect(data.roster.map((p: { role: string }) => p.role)).toEqual(SEATED.map((s) => s.role));
  expect(data.roster.find((p: { role: string }) => p.role === 'crew_owner')).toMatchObject({
    name: 'Iris Kovacs', rationale: CREW_WHY, nominated_by: 'manager',
    nominated_by_name: 'Ruth Delgado', source: 'derived',
  });

  // Image requests only, attached before the page loads (as the voice case does).
  const images: string[] = [];
  page.on('request', (r) => { if (r.resourceType() === 'image') images.push(r.url()); });

  await page.goto(`/#playbook?run=${SELECTION_RUN}`);
  await expect(page.getByLabel('Hermes')).toBeVisible();
  const why = (role: string) => page.locator(`[data-testid="roster-why-${role}"]`);
  const by = (role: string) => page.locator(`[data-testid="roster-nominated-${role}"]`);
  await expect(why('security')).toBeVisible({ timeout: 15000 });

  // A library seat and a derived seat: why each is there and who put it forward.
  // The derived rationale's tag is text: textContent keeps it only if nothing parsed it.
  await expect(why('security')).toContainText(`why: ${SECURITY_WHY}`);
  await expect(by('security')).toContainText('put forward by Maya Okonkwo');
  await expect(page.locator('[data-testid="roster-security"]')).not.toContainText('derived seat');
  const crew = page.locator('[data-testid="roster-crew_owner"]');
  await expect(crew).toContainText('Iris Kovacs');
  await expect(crew).toContainText('crew_owner · derived seat');
  await expect(why('crew_owner')).toContainText(`why: ${CREW_WHY}`);
  await expect(by('crew_owner')).toContainText('put forward by Ruth Delgado');
  // A seat nobody had to put forward.
  await expect(by('owner')).toContainText('fixed seat');
  // The cap the master resolved, not the server's env guess of 30.
  await expect(page.locator('[data-testid="turn-count"]')).toHaveText(`turn 0 of ${SELECTION_CAP}`);

  // The Selection card: the chair's ratification, its seats, who was considered.
  await expect(page.locator('[data-testid="selection-card"]')).toBeVisible();
  const stage = page.locator('[data-testid="selection-stage-3"]');
  await expect(stage).toContainText('Dana Whitfield');
  await expect(stage).toContainText('ratifies');
  await expect(stage).toContainText('broke the ground rules');
  await expect(stage).toContainText('Security signs off the trust boundary');
  // Her off-site figure reached the card as a figure, and was not drawn.
  await expect(stage.locator('[data-testid="image-unavailable"]')).toBeVisible();
  await expect(stage.getByText('who carries the pager each week')).toBeVisible();
  const proposed = page.locator('[data-testid="selection-proposed-3"]');
  await expect(proposed).toContainText('crew_owner · derived seat: Iris Kovacs');
  await expect(proposed).toContainText(CREW_WHY);
  const considered = page.locator('[data-testid="selection-considered"]');
  await expect(considered).toContainText('On-call SRE');
  await expect(considered).toContainText('Represented by Iris Kovacs');

  // Neither worker-written image became an <img>, and nothing on the page asked
  // another origin for one. The DOM check holds even where the CSP would have
  // blocked the request before the listener saw it.
  await expect(page.locator('img[src*="outside.example"]')).toHaveCount(0);
  const origin = new URL(page.url()).origin;
  const outside = images.filter((u) => /^https?:/.test(u) && new URL(u).origin !== origin);
  expect(outside, outside.join('\n')).toEqual([]);

  // Asserted only once the roster has rendered, so it cannot pass on a blank page.
  await expect(page.getByText('Nothing said yet')).toHaveCount(0);
});
