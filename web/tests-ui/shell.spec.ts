/**
 * The app shell: the top bar must be immovable and the document must not scroll.
 *
 * This is the suite jsdom could not provide. The bar rubber-banded in the real
 * browser while every unit test passed, because the failure is a layout and
 * compositor behaviour and jsdom models neither.
 */
import { test, expect, type Page } from '@playwright/test';

async function ready(page: Page) {
  await page.goto('/');
  await expect(page.getByLabel('Hermes')).toBeVisible();
}

test('the document itself cannot scroll', async ({ page }) => {
  await ready(page);

  // The shell is exactly one viewport tall and every view scrolls inside its own
  // pane, so a scrollable document can only mean the top bar can move.
  const doc = await page.evaluate(() => {
    const el = document.scrollingElement as HTMLElement;
    return { scrollHeight: el.scrollHeight, clientHeight: el.clientHeight };
  });
  expect(doc.scrollHeight).toBeLessThanOrEqual(doc.clientHeight);
});

test('overscroll-behavior is on the element that propagates it', async ({ page }) => {
  await ready(page);

  // Unlike overflow, overscroll-behavior reaches the viewport only from <html>.
  // Declared on <body> it reads as correct and does nothing.
  const applied = await page.evaluate(() => ({
    html: getComputedStyle(document.documentElement).overscrollBehaviorY,
    scroller: getComputedStyle(document.scrollingElement as HTMLElement).overscrollBehaviorY,
  }));
  expect(applied.html).toBe('none');
  expect(applied.scroller).toBe('none');
});

test('the top bar does not move when the page is scrolled', async ({ page }) => {
  await ready(page);
  const bar = page.locator('header');
  const before = await bar.boundingBox();

  await page.mouse.move(720, 500);
  for (let i = 0; i < 6; i++) await page.mouse.wheel(0, 400);
  await page.waitForTimeout(400);

  const after = await bar.boundingBox();
  expect(after!.y).toBe(before!.y);
  expect(after!.height).toBe(before!.height);
});

test('scrolling past the end of a view does not drag the top bar', async ({ page }) => {
  await ready(page);
  // Tickets is the long one -- scroll its pane to the bottom, then keep going.
  // Leftover delta chaining up into the viewport is what produced the elastic
  // movement.
  await page.goto('/#board');
  await expect(page.getByLabel('Hermes')).toBeVisible();
  await page.waitForTimeout(600);

  const bar = page.locator('header');
  const before = await bar.boundingBox();

  await page.mouse.move(720, 600);
  for (let i = 0; i < 12; i++) await page.mouse.wheel(0, 800);
  await page.waitForTimeout(400);

  const after = await bar.boundingBox();
  expect(after!.y).toBe(before!.y);
});

test('the top bar spans the window and sits flush at the top', async ({ page }) => {
  await ready(page);
  const box = (await page.locator('header').boundingBox())!;
  const width = page.viewportSize()!.width;

  expect(box.x).toBe(0);
  expect(box.y).toBe(0);
  expect(box.width).toBe(width);
});
