/**
 * The chair's ruling, read in the order a person needs it.
 *
 * The ruling itself is 8 KB of structured markdown, so the two things a reader
 * must not scroll past go above it: that this is a simulation, and what the
 * independent re-checks actually found. The prose follows, expanded, in a
 * <details> so it can be collapsed to reach the diff below.
 *
 * `text` is the assembled decision text the playbook banks — the chair's prose
 * with the re-check lines and the disclaimer appended (playbook.py:_reduce_decision).
 * The card never renders it: the prose comes from `segments`, that text split
 * the way a turn body is (view._verdict), so no image reference the chair wrote
 * ever reaches Markdown. The re-checks are rendered from `checks` as well,
 * because a list of six outcomes is a table, not a paragraph.
 */

import { useEffect, useState } from 'react';
import { apiGet, apiPost } from './host';
import { Segments, violationText, type Segment } from './Voice';

export type VerdictData = {
  text: string;
  checks: Array<{ turn: number; action: string; verified: boolean | null }>;
  artifact_intact: boolean | null;
  dropped_delegation: string | null;
  dropped_floor_requests: string[];
  /** voice: how many takes the chair needed, and the rules its kept take broke. */
  takes?: number | null;
  violations?: string[];
  voice?: Record<string, unknown> | null;
  /** `text` split like a turn body, every file image refused. */
  segments?: Segment[];
  // `view_data` also sends `simulation`, and this card deliberately does not
  // read it. `_verdict` hardcodes it True, so gating the banner on it would
  // move the most important safety sentence on the page behind a value that
  // crosses a process boundary and can only ever fail open. Declared nowhere so
  // a mutation of a dead field cannot look like a tested one.
};

const card: React.CSSProperties = {
  background: 'var(--surface-card)',
  border: '1px solid var(--border-hairline)',
  borderRadius: 'var(--radius-md)',
  padding: 16,
  display: 'flex',
  flexDirection: 'column',
  gap: 12,
};

const note = (tone: 'ok' | 'danger' | 'attention' | 'muted'): React.CSSProperties => ({
  padding: '8px 12px',
  borderRadius: 'var(--radius-sm)',
  fontSize: 12.5,
  lineHeight: 1.5,
  color: 'var(--text-primary)',
  background: tone === 'muted' ? 'var(--wash-subtle)' : `var(--status-${tone}-tint)`,
  border: `1px solid ${tone === 'muted' ? 'var(--border-hairline)' : `var(--status-${tone}-edge)`}`,
});

function Rechecks({ checks }: { checks: VerdictData['checks'] }) {
  if (checks.length === 0) {
    return (
      <div data-testid="rechecks-none" style={note('muted')}>
        No edit was delegated, so there was nothing to re-check.
      </div>
    );
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
        {checks.length} delegated {checks.length === 1 ? 'edit' : 'edits'}, each re-checked
        master-side by comparing the revised copy&rsquo;s digest before and after the turn. The
        worker&rsquo;s own claim is not what is reported here.
      </div>
      {checks.map((check) => {
        const applied = check.verified === true;
        const outcome =
          check.verified === null ? 'NOT CHECKED' : applied ? 'APPLIED' : 'DID NOT APPLY';
        return (
          <div
            key={check.turn}
            // `verdict-` prefixed: the timeline renders timeline-recheck-{n}
            // for the same turn numbers, and this card is mounted inside it.
            data-testid={`verdict-recheck-${check.turn}`}
            style={{
              ...note(check.verified === null ? 'muted' : applied ? 'ok' : 'danger'),
              display: 'flex',
              gap: 10,
              alignItems: 'baseline',
            }}
          >
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, whiteSpace: 'nowrap' }}>
              turn {String(check.turn).padStart(2, '0')} · junior_ic
            </span>
            <strong style={{ fontSize: 11.5, whiteSpace: 'nowrap' }}>{outcome}</strong>
            <span style={{ color: 'var(--text-secondary)' }}>{check.action}</span>
          </div>
        );
      })}
    </div>
  );
}

function Stamp({ runId }: { runId: string }) {
  const [stamp, setStamp] = useState<{ id: number; review_state: string; delivered: boolean } | null>(
    null,
  );
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    let live = true;
    // Every reduction, not `?phase=decision`: a verdict kept after a retake is
    // banked under `decision-take2`, and the reverse find below still lands on
    // the last decision reduction whatever phase it carries.
    apiGet<Array<{ id: number; kind: string; review_state: string; json?: { delivered?: unknown } }>>(
      `/api/runs/${runId}/reductions`,
    )
      .then((rows) => {
        // The LAST decision reduction, matching `view_data`, which takes
        // `next((r.json for r in reversed(reductions) ...))`. The route returns
        // ORDER BY id ascending, so `find` took the oldest: given two, the card
        // rendered verdict #2 and stamped reduction #1 — the operator reads one
        // ruling and stamps another.
        const row = [...rows].reverse().find((r) => r.kind === 'decision');
        if (!live) return;
        if (row) {
          setStamp({ id: row.id, review_state: row.review_state, delivered: Boolean(row.json?.delivered) });
        } else {
          setLookupError('no decision reduction is banked for this run');
        }
      })
      .catch((err) => {
        if (live) setLookupError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      live = false;
    };
  }, [runId, reloads]);

  const decide = async (accept: boolean) => {
    // Not only `disabled={busy}` on the buttons: that attribute was the entire
    // double-stamp guard, and an invariant that lives only in JSX is one tidy-up
    // away from gone. Three rapid clicks send one POST either way.
    if (!stamp || busy) return;
    setBusy(true);
    setActionError(null);
    try {
      const res = await apiPost<{ review_state: string }>(
        `/api/reductions/${stamp.id}/${accept ? 'accept' : 'reject'}`,
      );
      // The SERVER's state, never the requested one. An optimistic card would
      // be indistinguishable here and would lie the moment the two differ.
      setStamp({ ...stamp, review_state: res.review_state });
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not record the decision');
      // Re-read it. The lookup ran once on mount, so if another operator
      // stamped first this card would keep offering a button that can only
      // ever 409, until the page is reloaded.
      setReloads((n) => n + 1);
    } finally {
      setBusy(false);
    }
  };

  if (lookupError) {
    return (
      <div data-testid="stamp-error" style={note('muted')}>
        Could not read this verdict&rsquo;s review state: {lookupError}
      </div>
    );
  }
  if (!stamp) return null;
  // A failed chair turn, or a chair retake that delivered nothing, holds no
  // ticket and the run ends failed; the server would still stamp the pending
  // reduction, recording a ruling on a verdict nobody delivered.
  if (!stamp.delivered) {
    return (
      <div data-testid="stamp-undelivered" style={note('muted')}>
        The chair delivered no verdict, so there is nothing to accept or reject.
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div data-testid="stamp-note" style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>
        Accepting settles the chair&rsquo;s ticket and ends the run done; rejecting ends it failed.
        Either way it stamps this reduction in the audit trail and emits an event, and it lands
        nothing and reverts nothing.
      </div>
      {/* `review_state &&`: a malformed server response with no state rendered
          "Recorded as ." — falling back to the buttons says less and no lies. */}
      {stamp.review_state && stamp.review_state !== 'pending' ? (
        <div data-testid="stamp-state" style={note(stamp.review_state === 'accepted' ? 'ok' : 'attention')}>
          Recorded as {stamp.review_state}.
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            type="button"
            disabled={busy}
            onClick={() => decide(true)}
            style={{
              padding: '6px 14px',
              fontSize: 12.5,
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--status-ok-edge)',
              background: 'var(--status-ok-tint)',
              color: 'var(--text-primary)',
              cursor: busy ? 'default' : 'pointer',
            }}
          >
            Accept
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => decide(false)}
            style={{
              padding: '6px 14px',
              fontSize: 12.5,
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--status-danger-edge)',
              background: 'var(--status-danger-tint)',
              color: 'var(--text-primary)',
              cursor: busy ? 'default' : 'pointer',
            }}
          >
            Reject
          </button>
        </div>
      )}
      {actionError && (
        <div data-testid="stamp-action-error" style={note('danger')}>
          {actionError}
        </div>
      )}
    </div>
  );
}

export default function Verdict({
  runId,
  verdict,
}: {
  runId: string;
  verdict: VerdictData | null;
}) {
  if (!verdict) {
    return (
      <div style={card}>
        <div data-testid="verdict-pending" style={note('muted')}>
          The chair has not ruled yet. A verdict appears here once the meeting ends — when the
          owner closes it, the queue empties, or the turn cap is reached.
        </div>
      </div>
    );
  }

  const takes = verdict.takes ?? 1;
  const broke = verdict.violations ?? [];

  return (
    <div style={card}>
      <div data-testid="verdict-simulation" style={note('attention')}>
        <strong>Simulation — not an approval.</strong> This verdict is a simulation produced by AI
        personas reading one file. It is not an approval, not a sign-off, and carries no
        authority: a human decides.{' '}
        {/* "No repository was written to" cannot be printed above a card that
            says a repository file changed mid-review. The landing claim still
            holds either way: nothing this playbook does can land. */}
        {verdict.artifact_intact === false
          ? 'A repository file DID change during this review — see below. Nothing was landed,'
          : 'No repository was written to, nothing was landed,'}{' '}
        and nothing here binds any person, team or budget.
      </div>

      {(takes > 1 || broke.length > 0) && (
        <div data-testid="verdict-voice" style={note(broke.length > 0 ? 'attention' : 'muted')}>
          {takes > 1 && `The chair took ${takes} takes. `}
          {broke.length > 0 && `The kept verdict broke the ground rules: ${violationText(broke)}.`}
        </div>
      )}

      <Rechecks checks={verdict.checks} />

      {verdict.artifact_intact !== null && (
        <div
          data-testid="artifact-intact"
          style={note(verdict.artifact_intact ? 'ok' : 'danger')}
        >
          {verdict.artifact_intact
            ? 'Original artifact unchanged — re-checked by digest at the decision, against the digest taken before the meeting opened.'
            : 'Original artifact CHANGED DURING THE REVIEW — it was promised untouched. Treat every re-check above as unreliable and read the diff.'}
        </div>
      )}

      {verdict.dropped_delegation && (
        <div data-testid="dropped-delegation" style={note('attention')}>
          <strong>Dropped delegation</strong> — the turn cap cut it off and no edit was made:{' '}
          {verdict.dropped_delegation}
        </div>
      )}

      {verdict.dropped_floor_requests.length > 0 && (
        <div data-testid="dropped-floor-requests" style={note('attention')}>
          <strong>Dropped floor requests</strong> — the review ended before their turn came:{' '}
          {verdict.dropped_floor_requests.join(', ')}
        </div>
      )}

      <details open>
        <summary style={{ cursor: 'pointer', fontSize: 12, color: 'var(--text-muted)' }}>
          The chair&rsquo;s ruling in full
        </summary>
        <div data-testid="verdict-prose" style={{ marginTop: 8 }}>
          {/* `segments` only, never `text`: a payload without them shows no
              prose rather than the chair's raw markdown. */}
          <Segments segments={verdict.segments ?? []} runId={runId} fontSize={13} />
        </div>
      </details>

      <Stamp runId={runId} />
    </div>
  );
}
