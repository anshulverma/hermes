/**
 * CommitteeView — a committee run read as the meeting it was.
 *
 * Three surfaces, in the order a reader needs them: where the meeting got to
 * and why it stopped, who is in the room and where each of them stands, and
 * then the conversation itself.
 *
 * The timeline reads OLDEST-FIRST. `web/src/views/Outputs.tsx` sorts newest-id
 * first and is right to: a pipeline's newest reduction is its most aggregated.
 * A conversation is the opposite — turn 1 is the premise every later turn
 * argues with — and reading it backwards is the confusion this view exists to
 * remove.
 *
 * Entries are collapsed to their first line by default. The measured run is
 * 130 KB of prose across twenty turns; expanded by default it is a wall nobody
 * scrolls, and the turn numbers, the badges and the re-check outcomes — the
 * things a reader scans for — are what the collapsed row shows.
 *
 * The host's React, design system and Markdown all arrive on globals and this
 * bundle imports none of them. A second React copy breaks hooks, a second
 * design-system copy doubles 146 KB of vendored bundle, and importing Markdown
 * would inline react-markdown, remark-gfm and the whole unified stack into a
 * committed, unminified artifact.
 */

import { useState } from 'react';
import Verdict, { type VerdictData } from './Verdict';
import { Segments, violationText, type Segment } from './Voice';
import DocumentHistory, { type DiffMode, type DocumentBlock, type StepId } from './Diff';

// --- the data, exactly as `CommitteePlaybook.view_data` returns it -----------

export type Persona = {
  role: string;
  name: string;
  title: string;
  /** spoke · holds_floor · queued · idle */
  state: string;
  stance: string | null;
};

export type Entry = {
  n: number;
  role: string;
  name: string;
  title: string;
  body: string;
  /**
   * The edit this turn delegated, verbatim; null on every turn that delegated
   * none. Criterion 7 needs it here and not only in the verdict card: the card
   * does not exist until the chair rules.
   */
  action: string | null;
  /** Turn-reduction key names the turn set, plus the three derived ones. */
  badges: string[];
  /** The master-side re-check of a junior-IC edit; null on every other turn. */
  verified: boolean | null;
  /** What the speaker said they stand for on this turn; null when they said nothing. */
  stance: string | null;
  /**
   * voice C10. Optional because a payload from before voice has none of them;
   * `view_data` sends them on every entry now, null or empty on a legacy turn.
   */
  take?: number | null;
  takes?: number | null;
  violations?: string[];
  flags?: string[];
  voice?: Record<string, unknown> | null;
  /** The body split into text, image and mermaid, in order. */
  segments?: Segment[];
};

/** voice.summary, C11: every key is always present, null when its population is empty. */
export type VoiceSummary = Record<string, number | null | Record<string, number | null>>;

export type Progress = {
  turn: number;
  cap: number;
  holder: string | null;
  queue: string[];
  /** owner closed · queue empty · turn cap · chair turn failed */
  ended: string | null;
};

/** One row of the Evaluation block: `view_data`'s `evaluation.dimensions[id]`. */
export type EvaluationDimension = {
  score: number | null;
  scorer: 'judge' | 'deterministic';
  /** The first verified evidence quote; null when nothing verified. */
  quote: string | null;
  /** calibrated · off (Δn) · uncalibrated · unknown on a judge row; null on a deterministic one. */
  calibration: string | null;
  /** Why the scorer gave that score, clipped by the server; null when none. Optional, like the next: older payloads lack both. */
  rationale?: string | null;
  /** Scored under an older definition of the dimension than the current one. */
  stale?: boolean;
};

/**
 * `view_data()["evaluation"]` for a run that has an eval.json (C7). The server
 * sends a field it could not type (a hand-edited file) as null, never as an
 * object React cannot render.
 */
export type Evaluation =
  | { state: 'error'; error: string }
  | {
      state: 'ok';
      rubric_version: string | null;
      evaluated_at: number | null;
      headline: string | null;
      judge_status: 'ok' | 'partial' | 'unparseable' | 'failed' | null;
      judge_error: string | null;
      dimensions: Record<string, EvaluationDimension>;
      flags: string[];
    };

export type CommitteeData = {
  kind: string;
  roster: Persona[];
  progress: Progress;
  timeline: Entry[];
  verdict: VerdictData | null;
  /** null for a run reduced before voice: "not measured for this run". */
  voice?: VoiceSummary | null;
  /**
   * Every version of the document, by run-relative path. `name` is null until
   * some reduction names the file, which in phase `open` is never -- exactly
   * when the tab first appears -- so `tsc` forces that branch downstream.
   */
  document: DocumentBlock;
  /**
   * What committee-eval concluded, from runs/<id>/eval.json; null when the run
   * was never scored. Optional because a payload from before the eval carries
   * no such key, and the block reads absent exactly as null.
   */
  evaluation?: Evaluation | null;
};

export type CommitteeViewProps = {
  runId: string;
  data: CommitteeData;
  refetch: () => void;
  /** Set by the host on another tab; only the ones in `variants` are drawn. */
  variant?: string;
};

// --- host globals, read at render time --------------------------------------
//
// At render time rather than at module scope: this bundle is injected by a
// script tag, and where that lands relative to the host's own module graph is
// not something the view gets to decide.
//
// `Markdown` comes from ./host, which is the bundle's only reader of
// window.HermesUI. A second reader here drifted from it on the fallback: this
// one threw when the host published nothing, host.tsx degrades to preformatted
// text.

/**
 * What a missing design system degrades to.
 *
 * `web/src/ds/index.ts:getComponent` warns and returns `() => null`, and
 * `host.tsx` falls back to preformatted text rather than throwing. This mirrors
 * that: an unstyled view beats a throw into `PlaybookView`'s error boundary,
 * which is set once and never cleared, so one missing global would leave the
 * pane red for the session.
 */
const PLAIN: Record<string, any> = {
  Card: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Badge: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
  EmptyState: ({ title, description }: { title: string; description: string }) => (
    <div>
      <strong>{title}</strong> {description}
    </div>
  ),
};

/**
 * The design-system namespace, resolved exactly as `web/src/ds/index.ts` does.
 * The bundle publishes the hashed name and nothing publishes `DSNS`, so the
 * fallback is the compatibility half of the same expression, not a guess.
 */
function ds(): Record<string, any> {
  const w = window as unknown as Record<string, Record<string, any>>;
  const found = w.MonoDarkDashDesignSystem_66fdfe || w.DSNS;
  if (found) return found;
  console.warn('[committee view] design-system globals missing; rendering unstyled');
  return PLAIN;
}

// --- badges ------------------------------------------------------------------
//
// The slugs are the turn reduction's own key names plus two derived from it, so
// nothing has to agree on prose across the Python/TypeScript seam. An unknown
// slug renders as itself rather than disappearing.

const BADGE_LABEL: Record<string, string> = {
  request_floor: 'asked for the floor',
  delegate: 'delegated an edit',
  close: 'moved to close',
  signals_only: 'signals only, no prose',
  no_turn: 'no turn delivered',
  unattributed: 'speaker not identified',
  error: 'error on this turn',
  voice_flag: 'broke the ground rules',
  retaken: 'retaken',
  no_pointer: 'no pointer',
  no_example: 'no example',
};

const BADGE_TONE: Record<string, string | undefined> = {
  no_turn: 'danger',
  error: 'danger',
  unattributed: 'danger',
  signals_only: 'attention',
  voice_flag: 'attention',
};

// Every key above is a slug `view_data`'s `_badges` actually emits — the turn
// reduction's own key names. Keep the two lists in step: a slug with no entry
// renders as itself with no tone, which is green on both sides of the seam and
// wrong on screen (an undelivered turn silently loses its danger colour).

/** spoke · holds_floor · queued · idle, as a reader would say it. */
const ROSTER_STATE: Record<string, string> = {
  holds_floor: 'has the floor',
  queued: 'waiting to speak',
  spoke: 'spoke',
  idle: 'has not spoken',
};

const ENDED_NOTE: Record<string, string> = {
  'owner closed': 'The owner moved to close and the chair ruled.',
  'queue empty': 'Everyone who asked for the floor got it.',
  'turn cap': 'The meeting ran out of turns before anyone closed it.',
  'chair turn failed': 'The chair produced no decision, so the run ended failed.',
};

const mono = { fontFamily: 'var(--font-mono)' } as const;

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const { Card } = ds();
  return (
    <Card padding="md">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{title}</div>
        {children}
      </div>
    </Card>
  );
}

// --- progress ----------------------------------------------------------------

function ProgressBar({ progress, legacy }: { progress: Progress; legacy: boolean }) {
  const { Badge } = ds();
  const { turn, cap, holder, queue, ended } = progress;
  const pct = cap > 0 ? Math.min(100, Math.round((turn / cap) * 100)) : 0;
  // Amber is the "ran out of turns" colour, so it follows the ending and not
  // the arithmetic. run-2 finished at turn 20 of 20 because the owner closed;
  // colouring that bar amber says the opposite of the note beside it.
  const outOfTurns = ended === 'turn cap' || (ended === null && cap > 0 && turn >= cap);

  return (
    <Section title="Progress">
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span
          data-testid="turn-count"
          style={{ ...mono, fontSize: 13, color: 'var(--text-primary)' }}
        >
          turn {turn} of {cap}
        </span>
        <div
          aria-hidden
          style={{
            flex: 1,
            minWidth: 120,
            height: 4,
            borderRadius: 2,
            background: 'var(--wash-subtle)',
            overflow: 'hidden',
          }}
        >
          <div
            data-testid="turn-bar"
            style={{
              width: `${pct}%`,
              height: '100%',
              background: outOfTurns
                ? 'var(--status-attention, #e3b341)'
                : 'var(--status-live, #6ea8fe)',
            }}
          />
        </div>
        {holder ? (
          <Badge size="sm" variant="solid" tone="live" data-testid="floor-holder">
            {holder} has the floor
          </Badge>
        ) : null}
      </div>

      {queue.length > 0 && (
        <div data-testid="floor-queue" style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
          Waiting to speak: <span style={mono}>{queue.join(' · ')}</span>
        </div>
      )}

      {/* Why it stopped. The first live run ended at turn 20 of a cap of 20 --
          the owner closed on the turn the cap would have stopped anyway -- and
          nothing on screen said which of the two it was. That is the whole
          reason this line exists. */}
      {ended ? (
        <div
          data-testid="ended-reason"
          style={{
            fontSize: 12,
            padding: '6px 8px',
            borderRadius: 'var(--radius-md)',
            background: 'var(--wash-subtle)',
            border: '1px solid var(--border-hairline)',
            color:
              ended === 'turn cap' || ended === 'chair turn failed'
                ? 'var(--status-attention, #e3b341)'
                : 'var(--text-secondary)',
          }}
        >
          Ended: {ended}. {ENDED_NOTE[ended] ?? ''}
        </div>
      ) : (
        <div data-testid="ended-reason" style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          {legacy
            ? 'This run predates the committee view: its reductions never recorded why the meeting ended, so the record does not say.'
            : 'No ending recorded — the meeting is either still in session or stopped before the chair ruled.'}
        </div>
      )}
    </Section>
  );
}

// --- roster ------------------------------------------------------------------

function Roster({ roster, legacy }: { roster: Persona[]; legacy: boolean }) {
  const { Badge } = ds();
  return (
    <Section title={`Committee — ${roster.length}`}>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {roster.map((p) => (
          <div
            key={p.role}
            data-testid={`roster-${p.role}`}
            style={{
              display: 'flex',
              gap: 10,
              alignItems: 'baseline',
              padding: '6px 0',
              borderTop: '1px solid var(--border-hairline)',
              flexWrap: 'wrap',
            }}
          >
            <span style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 600 }}>
              {p.name}
            </span>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{p.title}</span>
            <span style={{ ...mono, fontSize: 10, color: 'var(--text-muted)' }}>{p.role}</span>
            <span style={{ marginLeft: 'auto', flex: 'none' }}>
              <Badge
                size="sm"
                variant={p.state === 'holds_floor' ? 'solid' : 'outline'}
                tone={
                  p.state === 'holds_floor' ? 'live' : p.state === 'queued' ? 'attention' : undefined
                }
              >
                {ROSTER_STATE[p.state] ?? p.state}
              </Badge>
            </span>
            {/* Absent stays absent: a persona that stated no stance is shown as
                having none, never as neutral. On a run that predates the stance
                signal every seat is absent, and "no stance stated" would be
                nine false statements rather than one honest one. */}
            <div
              data-testid={`stance-${p.role}`}
              style={{
                flexBasis: '100%',
                fontSize: 12,
                color: p.stance ? 'var(--text-secondary)' : 'var(--text-muted)',
                fontStyle: p.stance ? 'normal' : 'italic',
              }}
            >
              {p.stance ?? (legacy ? 'stance not recorded — this run predates the signal' : 'no stance stated')}
            </div>
          </div>
        ))}
      </div>
    </Section>
  );
}

// --- timeline ----------------------------------------------------------------

function TimelineEntry({
  runId,
  entry,
  open,
  onToggle,
  edit,
  onSeeEdit,
}: {
  runId: string;
  entry: Entry;
  open: boolean;
  onToggle: () => void;
  /** The 1-based edit step this turn delegated or applied, if any. */
  edit?: number;
  onSeeEdit: () => void;
}) {
  const { Badge } = ds();
  // A payload from before voice carries no segments: its body is all text.
  const segments: Segment[] = entry.segments ?? (entry.body ? [{ kind: 'text', text: entry.body }] : []);
  const firstText = segments.find((seg) => seg.kind === 'text');
  const firstLine = (firstText?.kind === 'text' ? firstText.text : '').split('\n').find((l) => l.trim()) ?? '';
  const violations = entry.violations ?? [];
  // A run captured before the view existed banks no `body`, so every row would
  // be a blank line with no explanation. Say which it is.
  const noProse = (
    <span style={{ fontStyle: 'italic' }}>no prose recorded for this turn</span>
  );

  return (
    <div
      data-testid={`entry-${entry.n}`}
      style={{ borderTop: '1px solid var(--border-hairline)', padding: '8px 0' }}
    >
      <button
        type="button"
        aria-expanded={open}
        onClick={onToggle}
        style={{
          display: 'flex',
          gap: 8,
          alignItems: 'baseline',
          width: '100%',
          textAlign: 'left',
          background: 'none',
          border: 'none',
          padding: 0,
          cursor: 'pointer',
          flexWrap: 'wrap',
        }}
      >
        <span aria-hidden style={{ color: 'var(--text-muted)', fontSize: 10, width: 10 }}>
          {open ? '▾' : '▸'}
        </span>
        <span style={{ ...mono, fontSize: 11, color: 'var(--text-muted)' }}>
          t{String(entry.n).padStart(2, '0')}
        </span>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
          {entry.name}
        </span>
        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{entry.title}</span>
        {entry.badges.map((b) => (
          <Badge key={b} size="sm" variant="outline" tone={BADGE_TONE[b]}>
            {BADGE_LABEL[b] ?? b}
          </Badge>
        ))}
        {entry.verified !== null && (
          <span
            // `timeline-` prefixed: the verdict card below renders one row per
            // re-check with the same turn numbers, and this component mounts
            // that card. A bare `recheck-3` matches both and getByTestId throws.
            data-testid={`timeline-recheck-${entry.n}`}
            style={{
              fontSize: 11,
              fontWeight: 600,
              color: entry.verified ? 'var(--status-ok, #7ee787)' : 'var(--status-danger, #f85149)',
            }}
          >
            {entry.verified ? 're-check: APPLIED' : 're-check: DID NOT APPLY'}
          </span>
        )}
      </button>

      {/* Criterion 7's first half, and it has to be outside the collapse: a
          delegated turn must say WHAT was delegated without being opened, and
          the verdict card that repeats it does not exist until the chair
          rules. */}
      {entry.action !== null && (
        <div
          data-testid={`action-${entry.n}`}
          style={{
            marginTop: 4,
            marginLeft: 18,
            padding: '4px 8px',
            fontSize: 11.5,
            lineHeight: 1.45,
            color: 'var(--text-secondary)',
            background: 'var(--wash-subtle)',
            borderLeft: '2px solid var(--border-hairline)',
            borderRadius: 'var(--radius-sm)',
          }}
        >
          delegated: {entry.action}
        </div>
      )}

      {edit !== undefined && (
        <button
          type="button"
          data-testid={`see-edit-${entry.n}`}
          onClick={onSeeEdit}
          style={{
            marginTop: 4,
            marginLeft: 18,
            padding: '0 6px',
            fontSize: 11,
            color: 'var(--text-primary)',
            background: 'none',
            border: '1px solid var(--border-hairline)',
            borderRadius: 'var(--radius-sm)',
            cursor: 'pointer',
          }}
        >
          see edit {edit}
        </button>
      )}

      {open ? (
        <div style={{ marginTop: 6, paddingLeft: 18, color: 'var(--text-muted)' }}>
          {entry.take != null && entry.takes != null && (entry.takes > 1 || violations.length > 0) && (
            <div data-testid={`kept-take-${entry.n}`} style={{ fontSize: 11.5, marginBottom: 6 }}>
              kept take {entry.take} of {entry.takes}
              {violations.length > 0 && `; broke: ${violationText(violations)}`}
            </div>
          )}
          {segments.length > 0 ? <Segments segments={segments} runId={runId} /> : noProse}
        </div>
      ) : (
        <div
          style={{
            marginTop: 2,
            paddingLeft: 18,
            fontSize: 12,
            color: 'var(--text-muted)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {firstLine || noProse}
        </div>
      )}
    </div>
  );
}

function Timeline({
  runId,
  timeline,
  open,
  setOpen,
  edits,
  onSeeEdit,
}: {
  runId: string;
  timeline: Entry[];
  /** Held by the view, so a step's `tNN` link can open an entry from outside. */
  open: Set<number>;
  setOpen: React.Dispatch<React.SetStateAction<Set<number>>>;
  /** turn -> [1-based edit number, that step's junior turn], for reviewer, owner and junior rows. */
  edits: Map<number, [number, number]>;
  onSeeEdit: (turn: number) => void;
}) {
  const allOpen = timeline.length > 0 && open.size === timeline.length;

  // Oldest first — see the module docstring.
  const ordered = [...timeline].sort((a, b) => a.n - b.n);

  return (
    <Section title={`Transcript — ${timeline.length} turns, oldest first`}>
      <button
        type="button"
        data-testid="expand-all"
        onClick={() => setOpen(allOpen ? new Set() : new Set(ordered.map((e) => e.n)))}
        style={{
          alignSelf: 'flex-start',
          padding: '2px 8px',
          fontSize: 11,
          color: 'var(--text-primary)',
          background: 'var(--wash-subtle)',
          border: '1px solid var(--border-hairline)',
          borderRadius: 'var(--radius-md)',
          cursor: 'pointer',
        }}
      >
        {allOpen ? 'Collapse all' : 'Expand all'}
      </button>
      {ordered.map((entry) => (
        <TimelineEntry
          key={entry.n}
          runId={runId}
          entry={entry}
          open={open.has(entry.n)}
          edit={edits.get(entry.n)?.[0]}
          onSeeEdit={() => onSeeEdit(edits.get(entry.n)![1])}
          onToggle={() =>
            setOpen((prev) => {
              const next = new Set(prev);
              if (next.has(entry.n)) next.delete(entry.n);
              else next.add(entry.n);
              return next;
            })
          }
        />
      ))}
    </Section>
  );
}

// --- the Metrics tab ---------------------------------------------------------
//
// Counts over the same turns the transcript shows, and nothing else: the
// reductions carry no timestamps, so every interval here is in turns.

function Bar({ value, max }: { value: number; max: number }) {
  return (
    <div aria-hidden style={{ flex: 1, height: 4, borderRadius: 2, background: 'var(--wash-subtle)' }}>
      <div
        style={{
          width: `${max > 0 ? (value / max) * 100 : 0}%`,
          height: '100%',
          borderRadius: 2,
          background: 'var(--status-live, #6ea8fe)',
        }}
      />
    </div>
  );
}

const quiet = { fontSize: 12, color: 'var(--text-secondary)' } as const;
const row = { display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 } as const;

function MeetingMetrics({ data }: { data: CommitteeData }) {
  const turns = [...data.timeline].sort((a, b) => a.n - b.n);
  const delivered = (e: Entry) => !e.badges.includes('no_turn');
  const over = data.verdict !== null;

  // Turns per seat, every seat included; a turn nobody can be named for gets
  // its own row rather than vanishing from the total.
  const seats = [
    ...data.roster.map((p) => ({ key: p.role, name: p.name, of: (e: Entry) => e.role === p.role })),
    { key: 'unattributed', name: 'speaker not identified', of: (e: Entry) => e.badges.includes('unattributed') },
  ]
    .map((s) => ({ ...s, took: turns.filter(s.of) }))
    .filter((s) => s.key !== 'unattributed' || s.took.length > 0);
  const most = Math.max(...seats.map((s) => s.took.length));

  // Only a delivered owner turn could have delegated, and `_apply_block` wants
  // the badge AND a named edit before it counts.
  const ownerTurns = turns.filter((e) => e.role === 'owner' && delivered(e));
  const delegated = ownerTurns.filter((e) => e.badges.includes('delegate') && e.action !== null);
  const checked = turns.filter((e) => e.verified !== null);
  const applied = checked.filter((e) => e.verified).length;

  // The floor queue replayed: `next_phase` grants a request on the asker's next
  // turn, minted whether or not it was then delivered.
  const asks: Array<{ name: string; role: string; asked: number; got: number | null }> = [];
  for (const e of turns) {
    if (e.badges.includes('unattributed')) continue;
    const waiting = asks.find((a) => a.role === e.role && a.got === null);
    if (waiting) waiting.got = e.n;
    if (delivered(e) && e.badges.includes('request_floor') && !['owner', 'junior_ic'].includes(e.role)) {
      asks.push({ name: e.name, role: e.role, asked: e.n, got: null });
    }
  }

  // A signals-only turn's body is a placeholder, not prose anyone wrote.
  let sofar = 0;
  const growth = turns.map((e) => {
    if (delivered(e) && !e.badges.includes('signals_only')) sofar += Array.from(e.body).length;
    return { n: e.n, sofar };
  });

  return (
    <div data-testid="committee-metrics" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {!over && (
        <div data-testid="metrics-partial" style={quiet}>
          Through turn {turns[turns.length - 1].n}; no verdict yet.
        </div>
      )}

      <Section title="Turns taken">
        {seats.map((s) => {
          const missed = s.took.filter((e) => !delivered(e)).length;
          return (
            <div key={s.key} data-testid={`turns-${s.key}`} style={row}>
              <span style={{ width: 130, flex: 'none', color: 'var(--text-primary)' }}>{s.name}</span>
              <Bar value={s.took.length} max={most} />
              <span style={{ ...mono, flex: 'none' }}>
                {s.took.length}
                {missed > 0 && ` · ${missed} not delivered`}
              </span>
            </div>
          );
        })}
      </Section>

      <Section title="Delegated edits">
        <div data-testid="delegation-rate" style={quiet}>
          {ownerTurns.length > 0
            ? `${delegated.length} of ${ownerTurns.length} delivered owner turns delegated an edit`
            : 'The owner has not spoken yet.'}
        </div>
        <div data-testid="edit-rechecks" style={quiet}>
          {checked.length > 0
            ? `${checked.length} re-checked: ${applied} applied · ${checked.length - applied} did not apply`
            : 'No edit has been re-checked yet.'}
        </div>
        {data.verdict?.dropped_delegation && (
          <div data-testid="edit-dropped" style={quiet}>
            Cut off by the turn cap: {data.verdict.dropped_delegation}
          </div>
        )}
      </Section>

      <Section title="Floor requests">
        <div data-testid="floor-asks" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {asks.length === 0 && <div style={quiet}>Nobody asked for the floor.</div>}
          {asks.map((a) => (
            <div key={a.asked} data-testid={`floor-ask-${a.asked}`} style={quiet}>
              {a.name} asked on turn {a.asked} ·{' '}
              {a.got !== null
                ? `got the floor on turn ${a.got}, ${a.got - a.asked} turns later`
                : over
                  ? 'the meeting ended first'
                  : 'still waiting'}
            </div>
          ))}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
          Counted in turns: the record keeps no clock.
        </div>
      </Section>

      <Section title="Thread growth">
        <div data-testid="thread-growth" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {sofar === 0 ? (
            <div style={quiet}>No prose recorded for these turns.</div>
          ) : (
            <>
              <div style={quiet}>
                {sofar.toLocaleString('en-US')} characters of prose over {turns.length} turns
              </div>
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 48 }}>
                {growth.map((g) => (
                  <div
                    key={g.n}
                    data-testid={`growth-${g.n}`}
                    title={`turn ${g.n}: ${g.sofar.toLocaleString('en-US')} characters so far`}
                    style={{
                      flex: 1,
                      height: `${(g.sofar / sofar) * 100}%`,
                      minHeight: 1,
                      background: 'var(--status-live, #6ea8fe)',
                    }}
                  />
                ))}
              </div>
            </>
          )}
        </div>
      </Section>
    </div>
  );
}

// --- the evaluation ----------------------------------------------------------
//
// What committee-eval concluded about this run, under the counts above and
// never repeating them: a score per dimension, the quote that carries it, and
// whether the user's own scores have calibrated the judge yet. Always drawn:
// "Not evaluated" is a state of the run, not a reason to hide the section.

/** D5, the rubric's order: the three judge dimensions, then the three deterministic ones. */
const EVAL_ORDER = [
  'verdict_grounded',
  'edits_address_concerns',
  'concern_coverage',
  'efficiency',
  'concision',
  'verdict_consistency',
];

const cell = {
  padding: '4px 10px 4px 0',
  borderTop: '1px solid var(--border-hairline)',
  textAlign: 'left',
  verticalAlign: 'baseline',
} as const;

function EvaluationBlock({
  runId,
  evaluation,
  scorable,
}: {
  runId: string;
  evaluation: Evaluation | null;
  /** The chair delivered a verdict: `eval_cli run` refuses (exit 2) anything else. */
  scorable: boolean;
}) {
  const { Badge } = ds();
  // Runnable as written: no bare `python` on the user's PATH, `playbooks` is
  // importable only from the checkout, and run ids are per home.
  const command = <code style={mono}>{`.venv/bin/python -m playbooks.committee.eval_cli run ${runId}`}</code>;
  let body: React.ReactNode;

  if (evaluation === null && !scorable) {
    body = (
      <div data-testid="evaluation-empty" style={quiet}>
        Not evaluated: a run can be scored once the chair has delivered its verdict.
      </div>
    );
  } else if (evaluation === null) {
    body = (
      <div data-testid="evaluation-empty" style={quiet}>
        Not evaluated. Score it with {command} from the hermes checkout, with HERMES_HOME set to this control
        plane's home.
      </div>
    );
  } else if (evaluation.state === 'error') {
    body = (
      <div data-testid="evaluation-error" style={{ ...quiet, color: 'var(--status-danger, #f85149)' }}>
        {evaluation.error}
      </div>
    );
  } else {
    const dims = evaluation.dimensions;
    // eval.json's key order is not the rubric's. A dimension this bundle does
    // not know yet still gets its row, after the six it does.
    const ids = [
      ...EVAL_ORDER.filter((id) => id in dims),
      ...Object.keys(dims).filter((id) => !EVAL_ORDER.includes(id)),
    ];
    const flags = new Map<string, number>();
    for (const f of evaluation.flags) flags.set(f, (flags.get(f) ?? 0) + 1);

    body = (
      <>
        <div data-testid="evaluation-headline" style={{ fontSize: 12, color: 'var(--text-primary)' }}>
          {evaluation.headline}
        </div>
        {evaluation.judge_status !== 'ok' && (
          <div
            data-testid="evaluation-judge-status"
            style={{ ...quiet, color: 'var(--status-attention, #e3b341)' }}
          >
            Judge {evaluation.judge_status ?? 'status unknown'}
            {evaluation.judge_error ? `: ${evaluation.judge_error}` : ''}
          </div>
        )}
        <table aria-label="Evaluation scores" style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
          <thead>
            <tr>
              {['dimension', 'score', 'scorer', 'evidence'].map((h) => (
                <th
                  key={h}
                  style={{ ...cell, borderTop: 'none', fontSize: 11, fontWeight: 500, color: 'var(--text-muted)' }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ids.map((id) => {
              const d = dims[id];
              return (
                <tr key={id} data-testid={`eval-dim-${id}`}>
                  <td style={{ ...cell, whiteSpace: 'nowrap', color: 'var(--text-primary)' }}>
                    {id.replace(/_/g, ' ')}
                  </td>
                  <td style={{ ...cell, whiteSpace: 'nowrap' }}>
                    <span data-testid={`eval-score-${id}`} style={mono}>
                      {d.score === null ? <span aria-label="not scored">—</span> : d.score}
                      {d.stale && '*'}
                    </span>
                    {d.scorer === 'judge' && d.calibration !== 'calibrated' && (
                      <span style={{ marginLeft: 6 }}>
                        <Badge
                          data-testid={`eval-uncalibrated-${id}`}
                          size="sm"
                          variant="outline"
                          tone="attention"
                        >
                          {d.calibration ?? 'uncalibrated'}
                        </Badge>
                      </span>
                    )}
                  </td>
                  <td style={{ ...cell, color: 'var(--text-muted)' }}>{d.scorer}</td>
                  {/* Wrapped, never cut to one line: a tooltip is out of reach
                      of the keyboard and of touch. A quote is at most 300 chars. */}
                  <td
                    style={{
                      ...cell,
                      width: '100%',
                      overflowWrap: 'anywhere',
                      color: d.quote ? 'var(--text-secondary)' : 'var(--text-muted)',
                    }}
                  >
                    {d.quote ?? 'no verified quote'}
                    {/* Folded: up to ~1000 chars per row would bury the scores. */}
                    {d.rationale && (
                      <details data-testid={`eval-why-${id}`}>
                        <summary style={{ cursor: 'pointer', color: 'var(--text-muted)' }}>why</summary>
                        <div style={{ whiteSpace: 'pre-wrap', color: 'var(--text-secondary)' }}>{d.rationale}</div>
                      </details>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {/* eval_cli's STALE_NOTE, with this run for its <target>. */}
        {ids.some((id) => dims[id].stale) && (
          <div data-testid="eval-stale-note" style={quiet}>
            * older definition; re-run {command}
          </div>
        )}
        <div data-testid="eval-flags" style={quiet}>
          Flags:{' '}
          {flags.size === 0
            ? 'none'
            : [...flags].map(([id, n]) => (n > 1 ? `${id} ×${n}` : id)).join(' · ')}
        </div>
        <div data-testid="evaluation-rubric" style={{ ...mono, fontSize: 11, color: 'var(--text-muted)' }}>
          rubric {evaluation.rubric_version ?? 'unknown'}
        </div>
      </>
    );
  }

  return (
    <div data-testid="evaluation">
      <Section title="Evaluation">{body}</Section>
    </div>
  );
}

// --- the view ----------------------------------------------------------------

export default function CommitteeView({ runId, data, variant }: CommitteeViewProps) {
  const { EmptyState } = ds();
  // Above the empty-state return, as the rules of hooks require. Held here and
  // not in the cards so a data tick keeps the selected step and the open turns.
  // Verdict's Stamp never calls `refetch` for the same reason: that remounts
  // the view (PlaybookView keys it on `reloads`) and would throw all of it away.
  const [selected, setSelected] = useState<StepId>('original');
  const [open, setOpen] = useState<Set<number>>(new Set());
  const [diffMode, setDiffMode] = useState<DiffMode>('unified');

  // A run captured before this view existed. Its reductions predate `body`,
  // `stance`, `ended`, `artifact` and `revised`, so `view_data` returns those
  // five as null/empty and every card would render a confident, reassuring
  // falsehood from a partial input: "Still in session." for a `done` run, nine
  // seats with "no stance stated", twenty blank rows, and "no artifact has been
  // recorded" for a run that reviewed an 11,397-byte file. Neither signal is a
  // flag the master sets; both are shapes `reduce` can no longer produce.
  const legacy =
    (data.timeline.length > 0 && data.document.name === null) ||
    (data.verdict !== null && data.progress.ended === null);

  // A step's `tNN` link: open that turn in the transcript and bring it on screen
  // -- its last row, the take the step context reads for a turn settled twice.
  const openTurn = (n: number) => {
    setOpen((prev) => new Set(prev).add(n));
    const rows = window.document.querySelectorAll(`[data-testid="entry-${n}"]`);
    rows[rows.length - 1]?.scrollIntoView?.({ block: 'center' });
  };

  // Titled like every other surface: this card sits last, below the transcript
  // and the verdict, and it is where a reader comes looking for the document.
  const edited = data.document.steps.length;
  const history = (
    <Section
      title={
        data.document.name
          ? `Document — ${data.document.name} · ${edited === 0 ? 'no edits' : edited === 1 ? '1 edit' : `${edited} edits`}`
          : 'Document'
      }
    >
      {/* `intact` as well as the document: the card guarantees the original
          was untouched, and only the verdict knows whether it was. */}
      <DocumentHistory
        runId={runId}
        document={data.document}
        timeline={data.timeline}
        intact={data.verdict?.artifact_intact ?? null}
        legacy={legacy}
        selected={selected}
        onSelect={setSelected}
        diffMode={diffMode}
        onDiffMode={setDiffMode}
        onOpenTurn={openTurn}
      />
    </Section>
  );

  // The timeline alone, NOT `&& roster.length === 0`. `view_data`'s `_roster`
  // walks `cast.CAST`, so it returns all nine rows from the first poll onward
  // and a roster-length test can never fire on real data. The state this guard
  // exists for is a run whose first turn has not settled: no reductions, so no
  // timeline and no verdict -- and it is exactly when the tab first appears.
  if (data.timeline.length === 0) {
    // No padding of its own, for the same reason the populated branch has none:
    // PlaybookView.tsx already wraps this component in `padding: 20`, and 32
    // inside 20 is 52px on one branch and 20 on the other.
    const empty = (
      <EmptyState
        title="Nothing said yet"
        description="The committee view fills in as each member takes the floor."
        icon="inbox"
      />
    );
    // `open` keeps the original before the first worker runs, and that worker
    // can take an hour: once the original is readable, so is the document under
    // review. Never on another tab, which draws only its own section.
    if (!data.document.captured || variant === 'metrics') return empty;
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {empty}
        {history}
      </div>
    );
  }

  // The evaluation under the counts, never instead of them.
  if (variant === 'metrics')
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <MeetingMetrics data={data} />
        <EvaluationBlock runId={runId} evaluation={data.evaluation ?? null} scorable={!!data.verdict?.text} />
      </div>
    );

  // The other direction: the reviewer who raised an edit, the owner turn that
  // delegated it and the junior turn that applied it all link to its step --
  // the way back after "raised by" opened the reviewer's turn. A reviewer turn
  // is answered by one owner turn, so no turn maps to two steps. Only when
  // there are snapshots to show -- otherwise the link would land on "not
  // captured".
  const edits = new Map<number, [number, number]>();
  if (data.document.captured) {
    data.document.steps.forEach((step, i) => {
      if (step.reviewer_turn !== null) edits.set(step.reviewer_turn, [i + 1, step.turn]);
      if (step.owner_turn !== null) edits.set(step.owner_turn, [i + 1, step.turn]);
      edits.set(step.turn, [i + 1, step.turn]);
    });
  }
  // The stepper to the top of the viewport, so the edit's context and diff
  // below it are on screen, and focus with it so the arrow keys step from there.
  const seeEdit = (turn: number) => {
    setSelected(turn);
    const stepper = window.document.querySelector<HTMLElement>('[data-testid="doc-stepper"]');
    stepper?.scrollIntoView?.({ block: 'start' });
    stepper?.focus({ preventScroll: true });
  };

  return (
    // No `flex: 1; overflow: auto; padding: 20` here: PlaybookView.tsx already
    // wraps this component in exactly that, and a second scroll container
    // inside the first is two scrollbars and double padding.
    <div
      data-testid="committee-view"
      style={{ display: 'flex', flexDirection: 'column', gap: 16 }}
    >
      <ProgressBar progress={data.progress} legacy={legacy} />
      <Roster roster={data.roster} legacy={legacy} />
      <Timeline
        runId={runId}
        timeline={data.timeline}
        open={open}
        setOpen={setOpen}
        edits={edits}
        onSeeEdit={seeEdit}
      />
      <Verdict runId={runId} verdict={data.verdict} />
      {history}
    </div>
  );
}

// On the function, not a second export: the UMD global IS this function, and
// the host reads the sections it may ask for off it.
CommitteeView.variants = ['metrics'];
