/**
 * Time formatting helpers shared across views.
 *
 * The API emits timestamps as epoch SECONDS (floats). fmtTime also tolerates ISO
 * strings so it works for any timestamp field regardless of source.
 */

/** Epoch seconds (or ISO string) → local "MMM D, HH:MM:SS"; "—" when missing. */
export function fmtTime(ts: number | string | null | undefined): string {
  if (ts == null || ts === '') return '—';
  const n = typeof ts === 'string' ? Number(ts) : ts;
  const d = Number.isFinite(n) ? new Date((n as number) * 1000) : new Date(String(ts));
  if (isNaN(d.getTime())) return String(ts);
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

/** Whole-second duration between two epoch-second stamps, e.g. "42s" / "3m 5s". */
export function fmtDuration(
  start: number | null | undefined,
  end: number | null | undefined,
): string | null {
  if (start == null || end == null) return null;
  const s = Math.max(0, Math.round(end - start));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return `${m}m ${s % 60}s`;
}
