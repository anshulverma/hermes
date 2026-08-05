/**
 * The wordmark: the mark stands in for the leading "H", so it has to sit like a
 * glyph -- on the baseline, one letter-space from the "e".
 *
 * The gap that had to be fixed here was INSIDE the svg's viewBox (the favicon's
 * tile padding), not between DOM boxes, so comparing element rects finds
 * nothing. These tests project the artwork's own coordinates through the
 * viewBox to work out where the ink actually lands.
 */
import { test, expect, type Page } from '@playwright/test';

/** Where a viewBox x-coordinate lands on screen, in px. */
async function inkX(page: Page, viewBoxX: number): Promise<number> {
  return page.evaluate((x) => {
    const svg = document.querySelector('header svg[viewBox]') as SVGSVGElement;
    const [minX, , vbWidth] = svg.getAttribute('viewBox')!.split(/\s+/).map(Number);
    const box = svg.getBoundingClientRect();
    return box.left + ((x - minX) / vbWidth) * box.width;
  }, viewBoxX);
}

/** The rendered height of the H stems (y 7 -> 25 in artwork units), in px. */
async function capHeight(page: Page): Promise<number> {
  return page.evaluate(() => {
    const svg = document.querySelector('header svg[viewBox]') as SVGSVGElement;
    const [, minY, , vbHeight] = svg.getAttribute('viewBox')!.split(/\s+/).map(Number);
    const box = svg.getBoundingClientRect();
    void minY;
    return ((25 - 7) / vbHeight) * box.height;
  });
}

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await expect(page.getByLabel('Hermes')).toBeVisible();
});

test('the gap between the H and the "e" is a letter-space, not tile padding', async ({ page }) => {
  // x=23.5 is the outer edge of the H's right stem (centre 22, 3-wide stroke).
  const stemRight = await inkX(page, 23.5);
  const textLeft = await page.evaluate(
    () => document.querySelector('header [aria-hidden="true"]')!.getBoundingClientRect().left,
  );
  const cap = await capHeight(page);

  const gap = textLeft - stemRight;

  // Measured against cap height so this holds at any font size. A normal letter
  // gap is ~0.1-0.2 of cap height; the favicon's tile padding made it 0.57.
  expect(gap).toBeGreaterThan(0);
  expect(gap / cap).toBeLessThan(0.3);
});

test('the mark sits on the text baseline', async ({ page }) => {
  // The H's feet are flush with the bottom of the cropped viewBox, so the svg's
  // bottom edge is the baseline. Compare against where the text's baseline
  // actually falls, measured from a zero-width range at its start.
  const delta = await page.evaluate(() => {
    const svg = document.querySelector('header svg[viewBox]') as SVGSVGElement;
    const text = document.querySelector('header [aria-hidden="true"]') as HTMLElement;

    // A one-character range gives the glyph box; its bottom is the descender
    // line, so use the parent's baseline via a probe element instead.
    const probe = document.createElement('span');
    probe.style.cssText = 'display:inline-block;width:0;height:0;overflow:hidden;';
    text.prepend(probe);
    const baseline = probe.getBoundingClientRect().bottom;
    probe.remove();

    return svg.getBoundingClientRect().bottom - baseline;
  });

  // Sub-pixel rounding and hinting make exact equality wrong to demand.
  expect(Math.abs(delta)).toBeLessThan(1.5);
});

test('the mark is cap-height, matching the letters beside it', async ({ page }) => {
  const cap = await capHeight(page);
  const fontSize = await page.evaluate(
    () => parseFloat(getComputedStyle(document.querySelector('header [aria-hidden="true"]')!).fontSize),
  );

  // Inter's cap height is 0.727em. Allow a little slack for the fallback stack.
  expect(cap / fontSize).toBeGreaterThan(0.62);
  expect(cap / fontSize).toBeLessThan(0.82);
});
