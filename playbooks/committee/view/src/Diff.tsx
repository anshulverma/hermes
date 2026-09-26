/**
 * The document as the committee changed it: the original, each junior-IC edit
 * as its own diff with who asked for it and why, then the final version.
 *
 * The first live run's chair read the unchanged repository file as proof the
 * edits had failed, so this card still leads with the invariant: the original
 * is never modified. A later run showed nothing at all, because the control
 * plane opened the master's host paths inside a container that mounts only the
 * home. So every version here is a snapshot under the run's own directory,
 * named by `view_data` and read through the run-file route.
 *
 * Text is fetched on demand, one selected step at a time, never with the view
 * data: the view refetches on every reduction.
 */

import { useEffect, useRef, useState } from 'react';
import type { Entry } from './CommitteeView';
import { Markdown, apiGet } from './host';

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

// --- the data, exactly as `view_data`'s `_document` returns it ---------------

/** A run-relative file under `runs/<id>/`; `bytes` null = not readable on the server. */
export type DocVersion = { path: string; bytes: number | null };

export type DocStep = DocVersion & {
  turn: number;
  delivered: boolean;
  verified: boolean | null;
  owner_turn: number | null;
  reviewer_turn: number | null;
  provenance: 'recorded' | 'inferred' | 'unknown';
};

export type Ruling = 'in_session' | 'awaiting_ruling' | 'accepted' | 'rejected' | 'no_ruling';

export type DocumentBlock = {
  /** null until some reduction names the file under review. */
  name: string | null;
  captured: boolean;
  original: DocVersion | null;
  steps: DocStep[];
  final: (DocVersion & { turn: number | null; ruling: Ruling }) | null;
  dropped_delegation: { owner_turn: number | null; action: string } | null;
};

/** A step is held by id, so a data tick that appends steps never moves it. */
export type StepId = 'original' | 'final' | number;

/** `GET /view/artifact` — `truncated` is true when the server hit its read cap. */
type Copy = { text: string; truncated?: boolean };

/**
 * How many diff rows to put in the DOM.
 *
 * ponytail: `diffLines` is hard-bounded and fast (415 rows in 1.9 ms on the real
 * pair); the RENDER is what does not scale — one <div> per line, measured at
 * 20,001 nodes and 3.4 s to mount for a 20,000-line artifact. A cap plus a
 * footer beats virtualization until a real artifact trips it.
 */
const MAX_ROWS = 5000;

const FINAL_LABEL: Record<Ruling, string> = {
  in_session: 'Latest so far — the meeting is still in session',
  awaiting_ruling: 'Proposed — awaiting your ruling',
  accepted: 'Accepted',
  rejected: 'Rejected',
  no_ruling: 'The meeting ended without a ruling',
};

const ROW_STYLE: Record<DiffRow['kind'], { sign: string; background: string; color: string }> = {
  same: { sign: ' ', background: 'transparent', color: 'var(--text-muted)' },
  del: { sign: '-', background: 'var(--status-danger-tint)', color: 'var(--text-primary)' },
  add: { sign: '+', background: 'var(--status-ok-tint)', color: 'var(--text-primary)' },
};

const tNN = (n: number) => `t${String(n).padStart(2, '0')}`;
const cacheKey = (v: DocVersion) => `${v.path}:${v.bytes}`;
const mono = { fontFamily: 'var(--font-mono)' } as const;
const pane: React.CSSProperties = {
  ...mono,
  fontSize: 11.5,
  lineHeight: 1.5,
  maxHeight: 420,
  overflow: 'auto',
  border: '1px solid var(--border-hairline)',
  borderRadius: 'var(--radius-sm)',
};
const muted: React.CSSProperties = { fontSize: 12.5, color: 'var(--text-muted)', lineHeight: 1.5 };

const note = (tone: 'danger' | 'attention' | 'live'): React.CSSProperties => ({
  padding: '8px 12px',
  borderRadius: 'var(--radius-sm)',
  background: `var(--status-${tone}-tint)`,
  border: `1px solid var(--status-${tone}-edge)`,
  fontSize: 12.5,
  lineHeight: 1.55,
  color: 'var(--text-primary)',
});

const chip = (active: boolean): React.CSSProperties => ({
  padding: '3px 10px',
  fontSize: 12,
  borderRadius: 'var(--radius-sm)',
  border: '1px solid var(--border-hairline)',
  background: active ? 'var(--wash-subtle)' : 'transparent',
  color: 'var(--text-primary)',
  fontWeight: active ? 600 : 400,
  cursor: 'pointer',
});

/**
 * Fetch each version through the run-file route, once, cached by path and size.
 *
 * ponytail: a re-settled turn whose snapshot keeps the same size is served
 * stale until reload; key on a digest in `view_data` if that ever matters.
 */
function useCopies(runId: string, versions: DocVersion[]) {
  const [copies, setCopies] = useState<Record<string, Copy>>({});
  const [failures, setFailures] = useState<Record<string, string>>({});
  const asked = useRef(new Set<string>());
  // The identity of `versions`, which is a new array on every render.
  const wanted = versions.map(cacheKey).join('\n');

  useEffect(() => {
    for (const key of wanted ? wanted.split('\n') : []) {
      if (asked.current.has(key)) continue;
      asked.current.add(key);
      const path = key.slice(0, key.lastIndexOf(':'));
      apiGet<Copy>(`/api/runs/${runId}/view/artifact?path=${path}`)
        .then((copy) => setCopies((prev) => ({ ...prev, [key]: copy })))
        .catch((err) =>
          setFailures((prev) => ({
            ...prev,
            [key]: err instanceof Error ? err.message : String(err),
          })),
        );
    }
  }, [runId, wanted]);

  return { copies, failures };
}

function Goto({ n, onOpenTurn }: { n: number; onOpenTurn: (n: number) => void }) {
  return (
    <button
      type="button"
      data-testid={`goto-${tNN(n)}`}
      onClick={() => onOpenTurn(n)}
      style={{ ...mono, ...chip(false), padding: '0 6px', fontSize: 11 }}
    >
      {tNN(n)}
    </button>
  );
}

/** Who raised it, who delegated it, what the junior said, what the re-check found. */
function StepContext({
  step,
  timeline,
  onOpenTurn,
}: {
  step: DocStep;
  timeline: Entry[];
  onOpenTurn: (n: number) => void;
}) {
  const at = (n: number | null) => (n === null ? undefined : timeline.find((e) => e.n === n));
  const reviewer = at(step.reviewer_turn);
  const owner = at(step.owner_turn);
  const junior = at(step.turn);
  const confirmation = junior?.body.split('\n').find((l) => l.trim()) ?? '';
  const line: React.CSSProperties = { fontSize: 12.5, color: 'var(--text-secondary)', lineHeight: 1.5 };

  return (
    <div data-testid="step-context" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div
        data-testid="step-verdict"
        style={{
          fontSize: 12,
          fontWeight: 600,
          color:
            step.verified === true
              ? 'var(--status-ok, #7ee787)'
              : step.verified === false
                ? 'var(--status-danger, #f85149)'
                : 'var(--text-muted)',
        }}
      >
        re-check:{' '}
        {step.verified === true
          ? 'APPLIED'
          : step.verified === false
            ? 'DID NOT APPLY'
            : 're-check not recorded'}
      </div>
      <div data-testid="step-raised" style={line}>
        {step.reviewer_turn !== null ? (
          <>
            raised by {reviewer?.name ?? 'a seat the transcript does not name'}
            {reviewer?.stance ? ` — ${reviewer.stance}` : ''}{' '}
            <Goto n={step.reviewer_turn} onOpenTurn={onOpenTurn} />
          </>
        ) : (
          'who raised this was not recorded'
        )}
      </div>
      {step.owner_turn !== null && (
        <div data-testid="step-delegated" style={line}>
          delegated: {owner?.action ?? 'no action recorded'}{' '}
          <Goto n={step.owner_turn} onOpenTurn={onOpenTurn} />
        </div>
      )}
      <div data-testid="step-confirmed" style={line}>
        {step.delivered ? confirmation || 'no prose recorded for this turn' : 'no turn delivered'}{' '}
        <Goto n={step.turn} onOpenTurn={onOpenTurn} />
      </div>
      {step.provenance === 'inferred' && (
        <div data-testid="step-provenance" style={{ ...muted, fontSize: 11.5 }}>
          (inferred from turn order)
        </div>
      )}
    </div>
  );
}

function UnifiedRow({ row }: { row: DiffRow }) {
  const style = ROW_STYLE[row.kind];
  return (
    <div
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
}

function DiffView({ before, after }: { before: string; after: string }) {
  const rows = diffLines(before, after);
  const adds = rows.filter((r) => r.kind === 'add').length;
  const dels = rows.filter((r) => r.kind === 'del').length;

  if (adds === 0 && dels === 0) {
    return (
      <div data-testid="diff-none" style={muted}>
        No changes between these two versions.
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div data-testid="diff-counts" style={{ fontSize: 12, color: 'var(--text-muted)' }}>
        {adds} {adds === 1 ? 'line' : 'lines'} added, {dels} removed.{' '}
        <span style={mono}>-</span> is a line only the earlier version has,{' '}
        <span style={mono}>+</span> a line only the later one has.
      </div>
      <div data-testid="diff-rows" style={pane}>
        {rows.slice(0, MAX_ROWS).map((row, i) => (
          <UnifiedRow key={i} row={row} />
        ))}
        {rows.length > MAX_ROWS && (
          <div data-testid="diff-rows-capped" style={{ padding: '4px 8px', color: 'var(--text-muted)' }}>
            … {rows.length - MAX_ROWS} more rows are in the diff and not on screen. The counts
            above are the whole diff; this pane stops at {MAX_ROWS}.
          </div>
        )}
      </div>
    </div>
  );
}

/** A whole version: rendered markdown for a markdown file, preformatted otherwise. */
function WholeDocument({ name, text }: { name: string; text: string }) {
  const frame: React.CSSProperties = {
    maxHeight: 480,
    overflow: 'auto',
    border: '1px solid var(--border-hairline)',
    borderRadius: 'var(--radius-sm)',
    padding: '8px 12px',
  };
  return /\.(md|markdown)$/i.test(name) ? (
    <div data-testid="doc-markdown" style={frame}>
      <Markdown fontSize={12.5}>{text}</Markdown>
    </div>
  ) : (
    <pre
      data-testid="doc-plain"
      style={{ ...frame, ...mono, fontSize: 11.5, whiteSpace: 'pre-wrap', margin: 0 }}
    >
      {text}
    </pre>
  );
}

export default function DocumentHistory({
  runId,
  document: doc,
  timeline,
  intact,
  legacy,
  selected,
  onSelect,
  onOpenTurn,
}: {
  runId: string;
  document: DocumentBlock;
  /** Names, stances and prose are read from here by turn, never copied into steps. */
  timeline: Entry[];
  /**
   * `verdict.artifact_intact`, passed down rather than assumed. The banner below
   * would otherwise promise the original untouched beside a verdict card saying
   * in red that it CHANGED DURING THE REVIEW. null is "no decision has
   * re-checked it yet", which is not the same as yes.
   */
  intact: boolean | null;
  /** This run's reductions predate `artifact`, so a null name is not an absence. */
  legacy?: boolean;
  selected: StepId;
  onSelect: (id: StepId) => void;
  onOpenTurn: (n: number) => void;
}) {
  const { name, captured, original, steps, final } = doc;
  const ids: StepId[] = original
    ? ['original', ...steps.map((s) => s.turn), ...(final ? (['final'] as const) : [])]
    : [];
  const current: StepId = ids.includes(selected) ? selected : 'original';
  const index = ids.indexOf(current);
  const step = typeof current === 'number' ? (steps.find((s) => s.turn === current) ?? null) : null;
  const previous = step ? (index > 1 ? steps[index - 2] : original) : null;

  // What the selected step shows, in diff order: [before, after] for an edit,
  // one whole version otherwise.
  const versions: DocVersion[] =
    !name || !captured || !original
      ? []
      : step && previous
        ? [previous, step]
        : current === 'final' && final
          ? [final]
          : [original];
  // Card state 4 covers EVERY version the step needs, its baseline included:
  // never fetch a file the server already said it cannot read, and never fall
  // back to the last readable one.
  const unreadable = versions.find((v) => v.bytes === null);
  const { copies, failures } = useCopies(runId, unreadable ? [] : versions);

  const shell: React.CSSProperties = {
    background: 'var(--surface-card)',
    border: '1px solid var(--border-hairline)',
    borderRadius: 'var(--radius-md)',
    padding: 16,
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
  };

  // Card state 1: nothing has named a document yet, so there is no name to
  // print and no digest claim to make.
  if (!name || !original) {
    return (
      <div style={shell}>
        <div data-testid="diff-no-artifacts" style={muted}>
          {legacy
            ? 'This run predates the committee view: its reductions never recorded which file the committee was handed, so there is nothing to show either side of. The record does not say the file is gone — it says nothing about it.'
            : 'No artifact has been recorded for this run yet. The committee names the file it is reviewing on its first reduction; until then there is nothing to show either side of.'}
        </div>
      </div>
    );
  }

  const fileName = <code style={{ ...mono, fontSize: 11.5 }}>{name}</code>;
  const label = (id: StepId) =>
    id === 'original'
      ? 'Original'
      : id === 'final'
        ? 'Final'
        : `Edit ${steps.findIndex((s) => s.turn === id) + 1} (${tNN(id)})`;
  const go = (delta: number) => {
    const next = ids[index + delta];
    if (next !== undefined) onSelect(next);
  };

  const pending = versions.find((v) => !copies[cacheKey(v)] && failures[cacheKey(v)] === undefined);
  const failed = versions.find((v) => failures[cacheKey(v)] !== undefined);
  const texts = versions.map((v) => copies[cacheKey(v)]);

  // Card states 4-7, first match wins. Nothing to show is state 2's business.
  let body: React.ReactNode = null;
  if (versions.length === 0) {
    body = null;
  } else if (unreadable) {
    body = (
      <div data-testid="doc-unreadable" style={note('danger')}>
        Could not read <code style={mono}>{unreadable.path}</code> on the server.
      </div>
    );
  } else if (pending) {
    body = (
      <div data-testid="doc-loading" style={muted}>
        Loading…
      </div>
    );
  } else if (failed) {
    body = (
      <div data-testid="doc-error" style={note('danger')}>
        Could not load <code style={mono}>{failed.path}</code>: {failures[cacheKey(failed)]}
      </div>
    );
  } else {
    body = (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {texts.some((t) => t.truncated) && (
          <div data-testid="diff-truncated" style={note('attention')}>
            The server cut at least one version short at its read cap, so what follows is a
            prefix and any counts below are not the whole file.
          </div>
        )}
        {texts.length === 2 ? (
          <DiffView before={texts[0].text} after={texts[1].text} />
        ) : (
          <WholeDocument name={name} text={texts[0].text} />
        )}
      </div>
    );
  }

  return (
    <div style={shell}>
      {intact === false ? (
        <div data-testid="diff-original-changed" style={note('danger')}>
          <strong>The original CHANGED during this review.</strong> {fileName} is not
          byte-for-byte what the committee was handed: the playbook re-checked its digest at the
          decision and it did not match. The safety guarantee this card normally states did not
          hold on this run, so read every version below against a file that moved under it, and
          treat every re-check in the verdict as unreliable.
        </div>
      ) : (
        <div data-testid="diff-original-untouched" style={note('live')}>
          <strong>The original is never modified.</strong> {fileName}{' '}
          {/* Only the decision's digest re-check can promise this in the past tense.
              Before it lands the honest word is the design rule, not the measurement. */}
          {intact === true ? 'is' : 'is meant to be'} byte-for-byte what the committee was handed;
          the playbook re-checks its digest at the decision and says so in the verdict. Every
          delegated edit lands in the revised copy, which the committee offers as a
          recommendation, not a landed change. Reading the repository file and finding it
          unchanged does not mean the edits failed.
        </div>
      )}

      {!captured ? (
        <div data-testid="doc-not-captured" style={muted}>
          Document snapshots were not captured for this run. It was reduced before the playbook
          kept a copy of each version, so there is nothing to step through.
        </div>
      ) : (
        <>
          <div
            role="group"
            aria-label="Versions of the document"
            data-testid="doc-stepper"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'ArrowLeft') {
                e.preventDefault();
                go(-1);
              } else if (e.key === 'ArrowRight') {
                e.preventDefault();
                go(1);
              }
            }}
            style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}
          >
            <button
              type="button"
              data-testid="step-prev"
              disabled={index <= 0}
              onClick={() => go(-1)}
              style={chip(false)}
            >
              ‹ Prev
            </button>
            {ids.map((id) => (
              <button
                key={String(id)}
                type="button"
                data-testid={`step-${id}`}
                aria-current={id === current ? 'step' : undefined}
                onClick={() => onSelect(id)}
                style={chip(id === current)}
              >
                {label(id)}
              </button>
            ))}
            <button
              type="button"
              data-testid="step-next"
              disabled={index >= ids.length - 1}
              onClick={() => go(1)}
              style={chip(false)}
            >
              Next ›
            </button>
          </div>

          {steps.length === 0 && (
            <div data-testid="doc-no-edits" style={muted}>
              No edit has been delegated yet. The original stands as it was.
            </div>
          )}
          {doc.dropped_delegation && (
            <div data-testid="doc-dropped" style={note('attention')}>
              The turn cap dropped a delegation
              {doc.dropped_delegation.owner_turn !== null
                ? ` from ${tNN(doc.dropped_delegation.owner_turn)}`
                : ''}
              : {doc.dropped_delegation.action}
            </div>
          )}

          {step && <StepContext step={step} timeline={timeline} onOpenTurn={onOpenTurn} />}
          {current === 'final' && final && (
            <div
              data-testid="final-label"
              style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}
            >
              {FINAL_LABEL[final.ruling]}
              <span style={{ fontWeight: 400, color: 'var(--text-muted)' }}>
                {final.turn === null
                  ? ' — no edit applied, so this is the original'
                  : ` — as the last applied edit (${tNN(final.turn)}) left it`}
              </span>
            </div>
          )}
          {body}
        </>
      )}
    </div>
  );
}
