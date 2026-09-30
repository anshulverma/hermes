/**
 * Tests for fmtAgo: relative times at minute granularity.
 */

import { describe, it, expect } from 'vitest';
import { fmtAgo } from './time';

const NOW = 1_750_000_000; // epoch seconds

describe('fmtAgo', () => {
  it("reads 'just now' under 60 s", () => {
    expect(fmtAgo(NOW, NOW)).toBe('just now');
    expect(fmtAgo(NOW - 59, NOW)).toBe('just now');
    expect(fmtAgo(NOW - 59.9, NOW)).toBe('just now');
  });

  it('reads whole minutes from 60 s', () => {
    expect(fmtAgo(NOW - 60, NOW)).toBe('1 minute ago');
    expect(fmtAgo(NOW - 3 * 60 - 59, NOW)).toBe('3 minutes ago');
    expect(fmtAgo(NOW - 3599, NOW)).toBe('59 minutes ago');
  });

  it('reads whole hours from 3600 s', () => {
    expect(fmtAgo(NOW - 3600, NOW)).toBe('1 hour ago');
    expect(fmtAgo(NOW - 2 * 3600 - 59 * 60, NOW)).toBe('2 hours ago');
    expect(fmtAgo(NOW - 86399, NOW)).toBe('23 hours ago');
  });

  it('reads whole days from 86400 s', () => {
    expect(fmtAgo(NOW - 86400, NOW)).toBe('1 day ago');
    expect(fmtAgo(NOW - 5 * 86400 - 23 * 3600, NOW)).toBe('5 days ago');
    expect(fmtAgo(NOW - 400 * 86400, NOW)).toBe('400 days ago');
  });

  it("clamps a negative difference (clock skew) to 0: 'just now'", () => {
    expect(fmtAgo(NOW + 1, NOW)).toBe('just now');
    expect(fmtAgo(NOW + 7200, NOW)).toBe('just now');
  });
});
