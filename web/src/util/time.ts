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

/** Format a number of seconds: "—" when null/undefined; "42s" / "3m 5s" / "2h 15m". */
export function fmtSeconds(s: number | null | undefined): string {
  if (s == null) return '—';
  const sec = Math.round(s);
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  if (sec < 3600) return `${m}m ${sec % 60}s`;
  const h = Math.floor(sec / 3600);
  const remainingM = Math.floor((sec % 3600) / 60);
  return `${h}h ${remainingM}m`;
}

const RELATIVE = new Intl.RelativeTimeFormat('en', { numeric: 'always' });

/**
 * How long before `now` an epoch-second stamp was, both in epoch seconds (`now`
 * comes from useNow): 'just now' under 60 s, else the largest whole unit of
 * minutes, hours or days ('3 minutes ago', '2 hours ago', '5 days ago'). A
 * negative difference (clock skew between server and browser) counts as 0.
 * Render it as
 *   <time dateTime={new Date(ts * 1000).toISOString()} title={fmtTime(ts)}>
 *     {fmtAgo(ts, now)}
 *   </time>
 */
export function fmtAgo(ts: number, now: number): string {
  const s = Math.max(0, now - ts);
  if (s < 60) return 'just now';
  if (s < 3600) return RELATIVE.format(-Math.floor(s / 60), 'minute');
  if (s < 86400) return RELATIVE.format(-Math.floor(s / 3600), 'hour');
  return RELATIVE.format(-Math.floor(s / 86400), 'day');
}
