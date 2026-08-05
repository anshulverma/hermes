/**
 * Screenshots of every view, written to web/screenshots/.
 *
 * Not assertions -- these exist so a change can be LOOKED at. Run with
 * `make shots`. The directory is gitignored; these are review artefacts, not
 * golden files (a golden-image suite is a different, much noisier commitment).
 */
import { test, expect, type Page } from '@playwright/test';

const VIEWS = ['overview', 'metrics', 'board', 'crew', 'findings', 'activity'] as const;

const DIR = 'screenshots';

async function settle(page: Page) {
  await expect(page.getByLabel('Hermes')).toBeVisible();
  // Let the live data land and the spinners clear.
  await page.waitForTimeout(1200);
}

for (const view of VIEWS) {
  test(`@shot ${view}`, async ({ page }) => {
    await page.goto(`/#${view}`);
    await settle(page);
    await page.screenshot({ path: `${DIR}/${view}.png` });
  });
}

test('@shot wordmark-closeup', async ({ page }) => {
  await page.goto('/');
  await settle(page);
  // Crop tight on the lockup and blow it up: the spacing being checked is a
  // couple of px, invisible in a full-page shot.
  await page.locator('header').screenshot({
    path: `${DIR}/wordmark.png`,
    clip: { x: 0, y: 0, width: 260, height: 56 },
  });
});

test('@shot topbar-after-scroll', async ({ page }) => {
  await page.goto('/#board');
  await settle(page);
  await page.mouse.move(720, 600);
  for (let i = 0; i < 12; i++) await page.mouse.wheel(0, 800);
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${DIR}/topbar-after-scroll.png` });
});
