/**
 * The revised copy against the original — the surface the first live run got
 * wrong, and the reason this exists.
 *
 * The chair opened the repository file, found it unchanged, wrote "six
 * delegations, zero bytes" and partly ruled on that basis. All six had landed:
 * the revised copy went 11,397 → 19,100 bytes and every re-check reports
 * APPLIED. The original is unchanged because that is the playbook's central
 * safety guarantee, not because the edits failed. So this leads with the
 * invariant and puts the diff second.
 *
 * Fetched on demand, never with the view data: the pair is ~30 KB for the
 * measured run and the view refetches on every reduction.
 */

import { useState } from 'react';
import { apiGet } from './host';

/** One rendered line of a unified diff. */
export type DiffRow = { kind: 'same' | 'del' | 'add'; text: string };

/**
 * Past this the LCS table is not worth allocating.
 *
 * ponytail: 4M cells is ~16 MB as an Int32Array, which covers any artifact a
 * committee reviews (the measured run needs 70k). Beyond it the changed middle
 * is reported as one whole-block replacement — true, just coarse. Upgrade to a
 * Myers diff only if a real artifact ever trips it.
 */
const MAX_CELLS = 4_000_000;

export function diffLines(original: string, revised: string): DiffRow[] {
  const a = original.split('\n');
  const b = revised.split('\n');

  // A revised copy shares most of both ends with its original; trimming them
  // first is what keeps the table small enough to allocate at all.
  let head = 0;
  while (head < a.length && head < b.length && a[head] === b[head]) head++;
  let tail = 0;
  while (
    tail < a.length - head &&
    tail < b.length - head &&
    a[a.length - 1 - tail] === b[b.length - 1 - tail]
  ) {
    tail++;
  }

  const rows: DiffRow[] = [];
  for (let i = 0; i < head; i++) rows.push({ kind: 'same', text: a[i] });

  const am = a.slice(head, a.length - tail);
  const bm = b.slice(head, b.length - tail);

  if (am.length * bm.length > MAX_CELLS) {
    for (const line of am) rows.push({ kind: 'del', text: line });
    for (const line of bm) rows.push({ kind: 'add', text: line });
  } else {
    const w = bm.length + 1;
    const lcs = new Int32Array((am.length + 1) * w);
    for (let i = am.length - 1; i >= 0; i--) {
      for (let j = bm.length - 1; j >= 0; j--) {
        lcs[i * w + j] =
          am[i] === bm[j]
            ? lcs[(i + 1) * w + j + 1] + 1
            : Math.max(lcs[(i + 1) * w + j], lcs[i * w + j + 1]);
      }
    }
    let i = 0;
    let j = 0;
    while (i < am.length && j < bm.length) {
      if (am[i] === bm[j]) {
        rows.push({ kind: 'same', text: am[i] });
        i++;
        j++;
      } else if (lcs[(i + 1) * w + j] >= lcs[i * w + j + 1]) {
        rows.push({ kind: 'del', text: am[i] });
        i++;
      } else {
        rows.push({ kind: 'add', text: bm[j] });
        j++;
      }
    }
    while (i < am.length) rows.push({ kind: 'del', text: am[i++] });
    while (j < bm.length) rows.push({ kind: 'add', text: bm[j++] });
  }

  for (let i = b.length - tail; i < b.length; i++) rows.push({ kind: 'same', text: b[i] });
  return rows;
}

type Artifact = { name: string; bytes: number };
// `original` is nullable, matching `view_data`'s `_artifacts`, which returns
// {"original": None, "revised": None} when no reduction names a path — the
// state of every run in phase `open`, which is when the tab first appears.
type Artifacts = { original: Artifact | null; revised: Artifact | null };

const kb = (bytes: number) => `${(bytes / 1024).toFixed(1)} KB`;

const ROW_STYLE: Record<DiffRow['kind'], { sign: string; background: string; color: string }> = {
  same: { sign: ' ', background: 'transparent', color: 'var(--text-muted)' },
  del: { sign: '-', background: 'var(--status-danger-tint)', color: 'var(--text-primary)' },
  add: { sign: '+', background: 'var(--status-ok-tint)', color: 'var(--text-primary)' },
};

export default function ArtifactDiff({
  runId,
  artifacts,
  intact,
  legacy,
}: {
  runId: string;
  artifacts: Artifacts;
  /**
   * `verdict.artifact_intact`, passed down rather than assumed.
   *
   * The headline below used to guarantee the original was untouched
   * unconditionally, while the verdict card two cards up could be saying in red
   * that it CHANGED DURING THE REVIEW. `_reduce_decision` computes that flag
   * precisely because the guarantee is one sentence of prose against a worker
   * running bypassPermissions, so the one surface built to stop a confident
   * false claim about a file has to read it.
   *
   * null is "no decision has re-checked it yet", which is not the same as yes.
   */
  intact: boolean | null;
  /** This run's reductions predate `artifact`, so a null path is not an absence. */
  legacy?: boolean;
}) {
  const [rows, setRows] = useState<DiffRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { original, revised } = artifacts;

  const load = () => {
    if (!revised) return;
    setLoading(true);
    setError(null);
    Promise.all([
      apiGet<{ text: string }>(`/api/runs/${runId}/view/artifact?which=original`),
      apiGet<{ text: string }>(`/api/runs/${runId}/view/artifact?which=revised`),
    ])
      .then(([a, b]) => setRows(diffLines(a.text, b.text)))
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  };

  const adds = rows ? rows.filter((r) => r.kind === 'add').length : 0;
  const dels = rows ? rows.filter((r) => r.kind === 'del').length : 0;

  const shell: React.CSSProperties = {
    background: 'var(--surface-card)',
    border: '1px solid var(--border-hairline)',
    borderRadius: 'var(--radius-md)',
    padding: 16,
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
  };

  // Nothing has named an artifact yet, so there is no name to print and no
  // digest claim to make. Same shape of guard as `!revised` below, and the one
  // the type demands: `_artifacts` really does return null here.
  if (!original) {
    return (
      <div style={shell}>
        <div
          data-testid="diff-no-artifacts"
          style={{ fontSize: 12.5, color: 'var(--text-muted)', lineHeight: 1.5 }}
        >
          {legacy
            ? 'This run predates the committee view: its reductions never recorded which file the committee was handed, so there is nothing to show either side of. The record does not say the file is gone — it says nothing about it.'
            : 'No artifact has been recorded for this run yet. The committee names the file it is reviewing on its first reduction; until then there is nothing to show either side of.'}
        </div>
      </div>
    );
  }

  const name = (a: Artifact) => (
    <code style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5 }}>{a.name}</code>
  );

  return (
    <div style={shell}>
      {intact === false ? (
        <div
          data-testid="diff-original-changed"
          style={{
            padding: '8px 12px',
            borderRadius: 'var(--radius-sm)',
            background: 'var(--status-danger-tint)',
            border: '1px solid var(--status-danger-edge)',
            fontSize: 12.5,
            lineHeight: 1.55,
            color: 'var(--text-primary)',
          }}
        >
          <strong>The original CHANGED during this review.</strong> {name(original)} is not
          byte-for-byte what the committee was handed: the playbook re-checked its digest at the
          decision and it did not match. The safety guarantee this card normally states did not
          hold on this run, so read the diff below against a file that moved under it, and treat
          every re-check in the verdict as unreliable.
        </div>
      ) : (
        <div
          data-testid="diff-original-untouched"
          style={{
            padding: '8px 12px',
            borderRadius: 'var(--radius-sm)',
            background: 'var(--status-live-tint)',
            border: '1px solid var(--status-live-edge)',
            fontSize: 12.5,
            lineHeight: 1.55,
            color: 'var(--text-primary)',
          }}
        >
          <strong>The original is never modified.</strong> {name(original)}{' '}
          {/* Only the decision's digest re-check can promise this in the past tense.
              Before it lands the honest word is the design rule, not the measurement. */}
          {intact === true ? 'is' : 'is meant to be'} byte-for-byte what the committee was handed;
          the playbook re-checks its digest at the decision and says so in the verdict. Every
          delegated edit lands in the revised copy,{' '}
          {revised ? name(revised) : 'which does not exist yet'}, which the committee offers as a
          recommendation, not a landed change. Reading the repository file and finding it unchanged
          does not mean the edits failed.
        </div>
      )}

      {!revised ? (
        <div
          data-testid="diff-no-revised"
          style={{ fontSize: 12.5, color: 'var(--text-muted)', lineHeight: 1.5 }}
        >
          No edit has been delegated yet, so there is no revised copy to compare. The original
          stands as it was.
        </div>
      ) : rows === null ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-start' }}>
          <button
            type="button"
            disabled={loading}
            onClick={load}
            style={{
              padding: '6px 14px',
              fontSize: 12.5,
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-hairline)',
              background: 'var(--wash-subtle)',
              color: 'var(--text-primary)',
              cursor: loading ? 'default' : 'pointer',
            }}
          >
            {loading ? 'Loading both copies…' : `Show the diff (${kb(original.bytes)} → ${kb(revised.bytes)})`}
          </button>
          {error && (
            <div
              data-testid="diff-error"
              style={{
                padding: '8px 12px',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--status-danger-tint)',
                border: '1px solid var(--status-danger-edge)',
                fontSize: 12.5,
                color: 'var(--text-primary)',
              }}
            >
              Could not load the two copies: {error}
            </div>
          )}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div data-testid="diff-counts" style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            {adds} lines added, {dels} removed — all of it in the revised copy.{' '}
            <span style={{ fontFamily: 'var(--font-mono)' }}>-</span> is a line only the original
            has, <span style={{ fontFamily: 'var(--font-mono)' }}>+</span> a line only the revised
            copy has.
          </div>
          <div
            data-testid="diff-rows"
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11.5,
              lineHeight: 1.5,
              maxHeight: 420,
              overflow: 'auto',
              border: '1px solid var(--border-hairline)',
              borderRadius: 'var(--radius-sm)',
            }}
          >
            {rows.map((row, i) => {
              const style = ROW_STYLE[row.kind];
              return (
                <div
                  key={i}
                  style={{
                    background: style.background,
                    color: style.color,
                    padding: '0 8px',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                  }}
                >
                  {style.sign} {row.text}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
