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

import { memo, useEffect, useRef, useState } from 'react';
import type { Entry, OneOnOne } from './CommitteeView';
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

/**
 * The same rows, side by side. A `same` row fills both columns; each run of
 * removals followed by a run of additions pairs up line by line, the shorter
 * side padded with an empty cell; a lone run leaves the other column empty.
 */
export function splitRows(rows: DiffRow[]): Array<[DiffRow | null, DiffRow | null]> {
  const out: Array<[DiffRow | null, DiffRow | null]> = [];
  let i = 0;
  while (i < rows.length) {
    if (rows[i].kind === 'same') {
      out.push([rows[i], rows[i]]);
      i++;
      continue;
    }
    const dels: DiffRow[] = [];
    while (i < rows.length && rows[i].kind === 'del') dels.push(rows[i++]);
    const adds: DiffRow[] = [];
    while (i < rows.length && rows[i].kind === 'add') adds.push(rows[i++]);
    for (let k = 0; k < Math.max(dels.length, adds.length); k++) {
      out.push([dels[k] ?? null, adds[k] ?? null]);
    }
  }
  return out;
}

/** Unchanged lines kept either side of a change; the rest of a run folds away. */
const CONTEXT = 3;

/** A run of unchanged rows folded to one row; `start` indexes the whole diff. */
export type Fold = { start: number; count: number };

/**
 * What an edit diff draws: every change with CONTEXT unchanged lines either
 * side, and each longer unchanged run as one Fold -- unless its `start` is in
 * `opened`. A committee edit is a few lines deep in a long document, and
 * unfolded the pane opened on the document's title every time.
 *
 * Returns runs of rows between folds, so the side-by-side layout pairs each run
 * on its own: a fold only ever replaces `same` rows, which pair with
 * themselves, so both layouts fold the same lines.
 */
export function foldRows(rows: DiffRow[], opened: ReadonlySet<number>): Array<DiffRow[] | Fold> {
  const out: Array<DiffRow[] | Fold> = [];
  let shown: DiffRow[] = [];
  for (let i = 0; i < rows.length; ) {
    let j = i;
    while (j < rows.length && rows[j].kind === 'same') j++;
    if (j === i) {
      shown.push(rows[i++]);
      continue;
    }
    // Unchanged rows i..j-1: CONTEXT after the change before them, CONTEXT
    // before the change after them, and neither at the document's two ends.
    const from = i === 0 ? 0 : i + CONTEXT;
    const to = j === rows.length ? j : j - CONTEXT;
    if (to > from && !opened.has(from)) {
      shown.push(...rows.slice(i, from));
      if (shown.length) out.push(shown);
      out.push({ start: from, count: to - from });
      shown = rows.slice(to, j);
    } else {
      shown.push(...rows.slice(i, j));
    }
    i = j;
  }
  if (shown.length) out.push(shown);
  return out;
}

/** How every diff on the card is laid out; held by the view, never persisted. */
export type DiffMode = 'unified' | 'split';

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
  /**
   * The seq of the 1:1 whose owner delegated this edit; null or absent for a
   * meeting delegation. When set, `provenance` is "recorded" and both turn
   * links are null: the edit was raised and delegated in that 1:1.
   */
  origin_one_on_one?: number | null;
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
  // No run state reaches the view, so a stopped meeting and a live one look the
  // same here; the ProgressBar hedges the same way.
  in_session: 'Latest so far — no verdict yet (in session, or stopped before the chair ruled)',
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
const heading: React.CSSProperties = { fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' };

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
  // Bumped by `retry`, so the effect runs again with the key no longer asked.
  const [attempt, setAttempt] = useState(0);
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
  }, [runId, wanted, attempt]);

  const retry = (key: string) => {
    asked.current.delete(key);
    setFailures((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
    setAttempt((n) => n + 1);
  };

  return { copies, failures, retry };
}

function Goto({ n, onOpenTurn }: { n: number; onOpenTurn: (n: number) => void }) {
  return (
    <button
      type="button"
      data-testid={`goto-${tNN(n)}`}
      aria-label={`Open ${tNN(n)} in the transcript`}
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
  derived,
  oneOnOnes,
  onOpenOneOnOne,
}: {
  step: DocStep;
  timeline: Entry[];
  onOpenTurn: (n: number) => void;
  derived?: Set<string>;
  /** Host, members, topic and delegated action are read from here by seq, never copied into steps. */
  oneOnOnes: OneOnOne[];
  onOpenOneOnOne: (seq: number) => void;
}) {
  // The LAST entry for a turn, as `view_data` keeps the last reduction for it:
  // a turn settled twice pairs its diff and verdict with the take that made them.
  const at = (n: number | null) => (n === null ? undefined : timeline.findLast((e) => e.n === n));
  const reviewer = at(step.reviewer_turn);
  const owner = at(step.owner_turn);
  const junior = at(step.turn);
  const confirmation = junior?.body.split('\n').find((l) => l.trim()) ?? '';
  // An edit from a 1:1 was raised and delegated there, not on a meeting turn.
  // Checked before the turn links, which are both null on such a step.
  const oneOnOneSeq = typeof step.origin_one_on_one === 'number' ? step.origin_one_on_one : null;
  const oneOnOne = oneOnOnes.find((g) => g.seq === oneOnOneSeq);
  // A derived seat's name is a selector's words; the slug says whose seat it is.
  const member = (p: OneOnOne['members'][number]) =>
    derived?.has(p.role) ? `${p.name} (${p.role} · derived seat)` : p.name;
  const line: React.CSSProperties = { fontSize: 12.5, color: 'var(--text-secondary)', lineHeight: 1.5 };
  // Only who raised it and who delegated it come from turn order; the junior's
  // own turn is the step itself, so the mark goes on those two lines alone.
  const inferred = step.provenance === 'inferred' && (
    <>
      {' '}
      <span data-testid="step-provenance" style={{ ...muted, fontSize: 11.5 }}>
        (inferred from turn order)
      </span>
    </>
  );

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
            : 'not recorded'}
      </div>
      {oneOnOneSeq !== null ? (
        <>
          <div data-testid="step-raised" style={line}>
            raised in 1:1{' '}
            {oneOnOne ? `${member(oneOnOne.members[0])} ↔ ${member(oneOnOne.members[1])}` : oneOnOneSeq}{' '}
            <button
              type="button"
              data-testid={`goto-one-on-one-${oneOnOneSeq}`}
              aria-label={`Open 1:1 ${oneOnOneSeq} in the transcript`}
              onClick={() => onOpenOneOnOne(oneOnOneSeq)}
              style={{ ...mono, ...chip(false), padding: '0 6px', fontSize: 11 }}
            >
              1:1 {oneOnOneSeq}
            </button>
          </div>
          {oneOnOne && (
            <div data-testid="step-why" style={line}>
              why: {oneOnOne.topic}
            </div>
          )}
          <div data-testid="step-delegated" style={line}>
            delegated: {oneOnOne?.delegated_action ?? 'no action recorded'}
          </div>
        </>
      ) : (
        <>
          <div data-testid="step-raised" style={line}>
            {step.reviewer_turn !== null ? (
              <>
                raised by {reviewer?.name ?? 'a seat the transcript does not name'}
                {/* A derived seat's name is a selector's words; the slug says whose turn it was. */}
                {reviewer && derived?.has(reviewer.role) && ` (${reviewer.role} · derived seat)`}
                {reviewer?.stance ? ` — ${reviewer.stance}` : ''}{' '}
                <Goto n={step.reviewer_turn} onOpenTurn={onOpenTurn} />
                {inferred}
              </>
            ) : (
              'who raised this was not recorded'
            )}
          </div>
          {step.owner_turn !== null && (
            <div data-testid="step-delegated" style={line}>
              {owner ? `delegated by ${owner.name}: ` : 'delegated: '}
              {owner?.action ?? 'no action recorded'}{' '}
              <Goto n={step.owner_turn} onOpenTurn={onOpenTurn} />
              {inferred}
            </div>
          )}
        </>
      )}
      <div data-testid="step-confirmed" style={line}>
        {junior ? `${junior.name}: ` : ''}
        {step.delivered ? confirmation || 'no prose recorded for this turn' : 'no turn delivered'}{' '}
        <Goto n={step.turn} onOpenTurn={onOpenTurn} />
      </div>
    </div>
  );
}

function UnifiedRow({ row, ref }: { row: DiffRow; ref?: React.Ref<HTMLDivElement> }) {
  const style = ROW_STYLE[row.kind];
  return (
    <div
      ref={ref}
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

function SplitCell({
  row,
  side,
  ref,
}: {
  row: DiffRow | null;
  side: 'left' | 'right';
  ref?: React.Ref<HTMLDivElement>;
}) {
  const style = row ? ROW_STYLE[row.kind] : null;
  return (
    <div
      ref={ref}
      data-testid={`split-${side}`}
      style={{
        background: style ? style.background : 'transparent',
        color: style ? style.color : undefined,
        padding: '0 8px',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        borderLeft: side === 'right' ? '1px solid var(--border-hairline)' : undefined,
      }}
    >
      {row && style ? `${style.sign} ${row.text}` : ''}
    </div>
  );
}

function FoldRow({ fold, onOpen }: { fold: Fold; onOpen: (start: number) => void }) {
  return (
    <button
      type="button"
      data-testid="diff-fold"
      onClick={() => onOpen(fold.start)}
      style={{
        gridColumn: '1 / -1',
        display: 'block',
        width: '100%',
        textAlign: 'left',
        padding: '0 8px',
        font: 'inherit',
        color: 'var(--text-muted)',
        background: 'var(--wash-subtle)',
        border: 'none',
        cursor: 'pointer',
      }}
    >
      {`⋯ ${fold.count} unchanged ${fold.count === 1 ? 'line' : 'lines'}`}
    </button>
  );
}

/** One drawn row: a fold, a unified row, or a side-by-side pair. */
type Line = Fold | DiffRow | [DiffRow | null, DiffRow | null];

// Memoised on its plain string props: the view re-renders on every data tick
// and transcript click, and re-diffing unchanged text each time is the
// expensive part of the card. Keyed by the versions it shows, so each step
// mounts afresh: its folds closed and its first change brought into view.
const DiffView = memo(function DiffView({
  before,
  after,
  mode,
}: {
  before: string;
  after: string;
  mode: DiffMode;
}) {
  const [opened, setOpened] = useState<ReadonlySet<number>>(new Set());
  const first = useRef<HTMLDivElement>(null);
  // Once per step, and `nearest`: a change already on screen moves nothing.
  useEffect(() => {
    first.current?.scrollIntoView?.({ block: 'nearest' });
  }, []);

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

  const open = (start: number) => setOpened((prev) => new Set(prev).add(start));
  const lines: Line[] = foldRows(rows, opened).flatMap((run): Line[] =>
    Array.isArray(run) ? (mode === 'split' ? splitRows(run) : run) : [run],
  );
  const firstRow = rows.find((r) => r.kind !== 'same');
  const mark = (row: DiffRow | null) => (row !== null && row === firstRow ? first : undefined);

  // MAX_ROWS caps what reaches the DOM in either layout, a fold counting as one
  // row; the counts above it always come from the whole diff.
  const total = lines.length;
  const capped = total > MAX_ROWS && (
    <div
      data-testid="diff-rows-capped"
      style={{ gridColumn: '1 / -1', padding: '4px 8px', color: 'var(--text-muted)' }}
    >
      … {total - MAX_ROWS} more rows are in the diff and not on screen. The counts above are
      the whole diff; this pane stops at {MAX_ROWS}.
    </div>
  );
  const drawn = lines.slice(0, MAX_ROWS);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div data-testid="diff-counts" style={{ fontSize: 12, color: 'var(--text-muted)' }}>
        {adds} {adds === 1 ? 'line' : 'lines'} added, {dels} removed.{' '}
        <span style={mono}>-</span> is a line only the earlier version has,{' '}
        <span style={mono}>+</span> a line only the later one has.
      </div>
      {mode === 'split' ? (
        <div
          data-testid="diff-split"
          style={{ ...pane, display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)' }}
        >
          {drawn.flatMap((line, i) =>
            Array.isArray(line)
              ? [
                  <SplitCell key={`${i}-l`} row={line[0]} side="left" ref={mark(line[0])} />,
                  <SplitCell key={`${i}-r`} row={line[1]} side="right" ref={mark(line[1])} />,
                ]
              : 'start' in line
                ? [<FoldRow key={i} fold={line} onOpen={open} />]
                : [],
          )}
          {capped}
        </div>
      ) : (
        <div data-testid="diff-rows" style={pane}>
          {drawn.map((line, i) =>
            Array.isArray(line) ? null : 'start' in line ? (
              <FoldRow key={i} fold={line} onOpen={open} />
            ) : (
              <UnifiedRow key={i} row={line} ref={mark(line)} />
            ),
          )}
          {capped}
        </div>
      )}
    </div>
  );
});

/**
 * A whole version: rendered markdown for a markdown file, preformatted
 * otherwise. Memoised like DiffView, so a data tick does not re-parse it.
 */
const WholeDocument = memo(function WholeDocument({ name, text }: { name: string; text: string }) {
  const frame: React.CSSProperties = {
    maxHeight: 480,
    overflow: 'auto',
    border: '1px solid var(--border-hairline)',
    borderRadius: 'var(--radius-sm)',
    padding: '8px 12px',
  };
  // No live images. Every version after Edit 1 is text a junior worker wrote,
  // and the host Markdown passes an <img> src straight through, so a remote src
  // would make the operator's browser fetch it. A zero-width space after `!`
  // leaves no image syntax for the parser to find -- the alt text reads as a
  // link to the src instead -- and changes nothing a reader can see.
  return /\.(md|markdown)$/i.test(name) ? (
    <div data-testid="doc-markdown" style={frame}>
      <Markdown fontSize={12.5}>{text.replaceAll('![', '!\u200B[')}</Markdown>
    </div>
  ) : (
    <pre
      data-testid="doc-plain"
      style={{ ...frame, ...mono, fontSize: 11.5, whiteSpace: 'pre-wrap', margin: 0 }}
    >
      {text}
    </pre>
  );
});

export default function DocumentHistory({
  runId,
  document: doc,
  timeline,
  intact,
  legacy,
  selected,
  onSelect,
  diffMode,
  onDiffMode,
  onOpenTurn,
  derived,
  oneOnOnes,
  onOpenOneOnOne,
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
  diffMode: DiffMode;
  onDiffMode: (mode: DiffMode) => void;
  onOpenTurn: (n: number) => void;
  /** Roles whose seat a selector invented (the roster's `source`). */
  derived?: Set<string>;
  /** view_data's `one_on_ones`, read by seq for a step that came out of a 1:1. */
  oneOnOnes: OneOnOne[];
  /** A step's 1:1 link: open that group in the transcript and bring it on screen. */
  onOpenOneOnOne: (seq: number) => void;
}) {
  // Off until asked for. Local, because the card stays mounted while stepping:
  // it is still on when the reader comes back to Final.
  const [finalDiff, setFinalDiff] = useState(false);
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
          ? finalDiff
            ? [original, final]
            : [final]
          : [original];
  // Card state 4 covers EVERY version the step needs, its baseline included:
  // never fetch a file the server already said it cannot read, and never fall
  // back to the last readable one.
  const unreadable = versions.find((v) => v.bytes === null);
  const { copies, failures, retry } = useCopies(runId, unreadable ? [] : versions);

  // No card of its own: the view wraps this in its titled Section.
  const shell: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: 12 };

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
        Could not load <code style={mono}>{failed.path}</code>: {failures[cacheKey(failed)]}{' '}
        <button
          type="button"
          data-testid="doc-retry"
          onClick={() => retry(cacheKey(failed))}
          style={chip(false)}
        >
          Retry
        </button>
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
          <DiffView
            key={versions.map(cacheKey).join(' ')}
            before={texts[0].text}
            after={texts[1].text}
            mode={diffMode}
          />
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

      {/* No cause claimed: a run from before doc/ existed and a worker that
          deleted it read the same here. */}
      {!captured ? (
        <div data-testid="doc-not-captured" style={muted}>
          No snapshot of this document is readable on the server — not the original's (
          <code style={mono}>{original.path}</code>) nor any edit's — so there is nothing to step
          through.
        </div>
      ) : (
        <>
          <div
            role="group"
            aria-label="Versions of the document"
            data-testid="doc-stepper"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
              e.preventDefault();
              const next = ids[index + (e.key === 'ArrowLeft' ? -1 : 1)];
              if (next === undefined) return;
              onSelect(next);
              // Focus follows the selection, so a screen reader announces the new step.
              e.currentTarget.querySelector<HTMLElement>(`[data-testid="step-${next}"]`)?.focus();
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

          {/* Only where a diff is on screen: on a whole version it would change nothing. */}
          {versions.length === 2 && (
            <div role="group" aria-label="Diff layout" style={{ display: 'flex', gap: 4 }}>
              <button
                type="button"
                data-testid="diff-mode-unified"
                aria-pressed={diffMode === 'unified'}
                onClick={() => onDiffMode('unified')}
                style={chip(diffMode === 'unified')}
              >
                Unified
              </button>
              <button
                type="button"
                data-testid="diff-mode-split"
                aria-pressed={diffMode === 'split'}
                onClick={() => onDiffMode('split')}
                style={chip(diffMode === 'split')}
              >
                Side by side
              </button>
            </div>
          )}
          {/* True whether nothing was delegated or the cap dropped the one that was. */}
          {steps.length === 0 && (
            <div data-testid="doc-no-edits" style={muted}>
              No edit was made. The original stands as it was.
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

          {current === 'original' && (
            <div data-testid="original-label" style={heading}>
              Original — as the committee was handed it
            </div>
          )}
          {step && (
            <StepContext
              step={step}
              timeline={timeline}
              onOpenTurn={onOpenTurn}
              derived={derived}
              oneOnOnes={oneOnOnes}
              onOpenOneOnOne={onOpenOneOnOne}
            />
          )}
          {current === 'final' && final && (
            <div data-testid="final-label" style={heading}>
              {FINAL_LABEL[final.ruling]}
              <span style={{ fontWeight: 400, color: 'var(--text-muted)' }}>
                {final.turn === null
                  ? ' — no edit applied, so this is the original'
                  : ` — as the last applied edit (${tNN(final.turn)}) left it`}
              </span>{' '}
              <button
                type="button"
                data-testid="final-diff-toggle"
                aria-pressed={finalDiff}
                onClick={() => setFinalDiff(!finalDiff)}
                style={chip(finalDiff)}
              >
                Original → final diff
              </button>
            </div>
          )}
          {body}
        </>
      )}
    </div>
  );
}
