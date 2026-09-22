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
import { mkdirSync, writeFileSync } from 'node:fs';

/** Where the home is on THIS machine -- where the fixture is written. */
const HOME = process.env.HERMES_E2E_HOME ?? '';
/** The same directory as the SERVER sees it. The container bind-mounts the home
 *  at /hermes-home, and view_data stats the artifact paths off the reductions
 *  inside that process, so the paths stored below must be the server's. */
const SERVER_HOME = process.env.HERMES_E2E_SERVER_HOME ?? '/hermes-home';

const RUN = 'committee-e2e';
const ORIGINAL = `${SERVER_HOME}/e2e/proposal.md`;
const REVISED = `${SERVER_HOME}/runs/${RUN}/revised/proposal.md`;

const ORIGINAL_TEXT =
  '# Consolidate the ingest pipelines\n\nStaffing: six engineers for two quarters.\n';
const REVISED_TEXT =
  '# Consolidate the ingest pipelines\n\nStaffing: two engineers for two quarters.\n';

const ACTION_1 = 'Cut the staffing ask from six engineers to two.';
const ACTION_2 = 'Name the Q3 migration freeze in the sequencing section.';

// Seven turns, not the twenty of the measured run: enough to prove ordering, a
// delegation that applied, one that did not, a turn nobody delivered, a floor
// request nobody got to, and two personas holding stances.
const TURNS = [
  { turn: 1, role: 'senior_director', delivered: true,
    body: 'The bet is plausible. The staffing line is fiction.',
    stance: 'Leaning no while the ask is six engineers.',
    request_floor: false, delegate: false, close: false, action: null, verified: null },
  { turn: 2, role: 'owner', delivered: true,
    body: 'Conceded. I will cut the ask and say so in the copy.',
    stance: 'Willing to cut scope to land this quarter.',
    request_floor: false, delegate: true, close: false, action: ACTION_1, verified: null },
  { turn: 3, role: 'junior_ic', delivered: true,
    body: 'Applied the staffing cut to the revised copy.',
    stance: null,
    request_floor: false, delegate: false, close: false, action: null, verified: true },
  { turn: 4, role: 'manager', delivered: false,
    body: '', stance: null,
    request_floor: false, delegate: false, close: false, action: null, verified: null },
  { turn: 5, role: 'tpm', delivered: true,
    body: 'Sequencing still collides with the Q3 migration freeze.',
    stance: 'No until the freeze window is named in the plan.',
    request_floor: true, delegate: false, close: false, action: null, verified: null },
  { turn: 6, role: 'owner', delivered: true,
    body: 'Fair. Delegating the freeze-window edit.',
    stance: 'Willing to cut scope to land this quarter.',
    request_floor: false, delegate: true, close: false, action: ACTION_2, verified: null },
  { turn: 7, role: 'junior_ic', delivered: true,
    body: 'Re-read the sequencing section and made no change.',
    stance: null,
    request_floor: false, delegate: false, close: false, action: null, verified: false },
];

/** Verbatim `playbooks/committee/playbook.py:109-112`. */
const SIMULATION =
  'This verdict is a simulation produced by AI personas reading one file. It is ' +
  'not an approval, not a sign-off, and carries no authority: a human decides.';

const DECISION = {
  verdict: [
    'Approve with conditions: the ask is two engineers and the freeze is acknowledged.',
    `- re-check of turn 03 (junior_ic): APPLIED — delegated: ${ACTION_1}`,
    `- re-check of turn 07 (junior_ic): DID NOT APPLY — delegated: ${ACTION_2}`,
    '- dropped_floor_requests (the review ended before their turn came): pm',
    SIMULATION,
  ].join('\n\n'),
  delivered: true,
  rechecks: [
    { turn: 3, action: ACTION_1, verified: true },
    { turn: 7, action: ACTION_2, verified: false },
  ],
  artifact_intact: true,
  dropped_delegation: null,
  dropped_floor_requests: ['pm'],
  error: null,
  artifact: ORIGINAL,
  revised: REVISED,
  ended: 'turn cap',
};

/** Idempotent: the run's rows are deleted before they are written again. */
function seed(): void {
  mkdirSync(`${HOME}/e2e`, { recursive: true });
  writeFileSync(`${HOME}/e2e/proposal.md`, ORIGINAL_TEXT);
  mkdirSync(`${HOME}/runs/${RUN}/revised`, { recursive: true });
  writeFileSync(`${HOME}/runs/${RUN}/revised/proposal.md`, REVISED_TEXT);

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

    // `phase` is NOT optional here, though the column allows NULL. The verdict
    // card looks its reduction up through
    // GET /api/runs/{id}/reductions?phase=decision, and that route appends
    // `AND phase=?` (server/app.py:978) — a decision row with phase NULL matches
    // nothing, the card renders its error state instead of accept/reject, and
    // the spec below would pass with the surface broken. The values are the ones
    // `record_reduction` writes: the run's phase at the time, so `t{NN}-{role}`
    // for a turn and `decision` for the decision.
    const insert = db.prepare(
      `INSERT INTO reductions (run_id, phase, kind, json, review_state, created_at, updated_at)
       VALUES (?, ?, ?, ?, 'pending', ?, ?)`,
    );
    TURNS.forEach((t, i) => {
      const json = { ...t, error: null, artifact: ORIGINAL, revised: REVISED };
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
  expect(data.verdict.simulation).toBe(true);
  expect(data.artifacts.original.bytes).toBe(ORIGINAL_TEXT.length);
  expect(data.artifacts.revised.bytes).toBe(REVISED_TEXT.length);

  const original = await request.get(`/api/runs/${RUN}/view/artifact?which=original`);
  expect((await original.json()).text).toBe(ORIGINAL_TEXT);
  expect((await request.get(`/api/runs/${RUN}/view/artifact?which=..%2F..%2Fetc%2Fpasswd`)).status())
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
  await expect(page.getByText(/turn cap/i).first()).toBeVisible();

  // The delegated action on the turn that delegated it -- criterion 7's first
  // half, and the one surface that exists only mid-run.
  await expect(page.locator('[data-testid="action-2"]')).toContainText(ACTION_1);
  await expect(page.locator('[data-testid="timeline-recheck-3"]')).toContainText('APPLIED');
  await expect(page.locator('[data-testid="timeline-recheck-7"]')).toContainText('DID NOT APPLY');

  // The verdict card found ITS reduction. This is the assertion that catches a
  // seeded `phase` of NULL: the card looks the row up through
  // ?phase=decision, and without it renders `stamp-error` instead. Nothing else
  // in this file would notice.
  await expect(page.locator('[data-testid="stamp-note"]')).toBeVisible();
  await expect(page.locator('[data-testid="stamp-error"]')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /accept/i })).toBeVisible();
  await expect(page.locator('[data-testid="verdict-recheck-3"]')).toContainText('APPLIED');
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
