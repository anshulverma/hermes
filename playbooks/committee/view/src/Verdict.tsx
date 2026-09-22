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
 * The re-checks are rendered from `checks` as well, because a list of six
 * outcomes is a table, not a paragraph.
 */

import { useEffect, useState } from 'react';
import { Markdown, apiGet, apiPost } from './host';

export type VerdictData = {
  text: string;
  checks: Array<{ turn: number; action: string; verified: boolean | null }>;
  artifact_intact: boolean | null;
  dropped_delegation: string | null;
  dropped_floor_requests: string[];
  simulation: boolean;
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
  const [stamp, setStamp] = useState<{ id: number; review_state: string } | null>(null);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    apiGet<Array<{ id: number; kind: string; review_state: string }>>(
      `/api/runs/${runId}/reductions?phase=decision`,
    )
      .then((rows) => {
        const row = rows.find((r) => r.kind === 'decision');
        if (!live) return;
        if (row) setStamp({ id: row.id, review_state: row.review_state });
        else setLookupError('no decision reduction is banked for this run');
      })
      .catch((err) => {
        if (live) setLookupError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      live = false;
    };
  }, [runId]);

  const decide = async (accept: boolean) => {
    if (!stamp) return;
    setBusy(true);
    setActionError(null);
    try {
      const res = await apiPost<{ review_state: string }>(
        `/api/reductions/${stamp.id}/${accept ? 'accept' : 'reject'}`,
      );
      setStamp({ id: stamp.id, review_state: res.review_state });
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not record the decision');
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div data-testid="stamp-note" style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>
        Accepting or rejecting stamps this reduction in the audit trail and emits an event. It
        settles no tickets and changes no run state — the committee&rsquo;s decision holds no
        needs_human ticket — and it lands nothing and reverts nothing. It records that a person
        read the verdict.
      </div>
      {stamp.review_state !== 'pending' ? (
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
          <Markdown>{verdict.text}</Markdown>
        </div>
      </details>

      <Stamp runId={runId} />
    </div>
  );
}
