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
  /**
   * selection C6: why this seat is in the room and who put it there. Null on
   * every row of a run from before selection, which shows neither line.
   * Optional, because such a payload may not carry the keys at all.
   */
  rationale?: string | null;
  nominated_by?: 'owner' | 'manager' | 'senior_director' | 'fixed' | 'default' | null;
  /** The selector's name for an owner, manager or senior_director nomination, else null. */
  nominated_by_name?: string | null;
  source?: 'fixed' | 'library' | 'derived' | null;
};

/** One kept selection stage, as `view._stage` builds it (C6). */
export type SelectionStage = {
  stage: number;
  role: string;
  name: string;
  delivered: boolean;
  /** The selector's prose with both fences stripped; thread.NO_TURN when undelivered. */
  body: string;
  /**
   * `source` is the seat's own, so a derived seat the chair dropped is still
   * marked (the roster knows only seated ones). Optional: older payloads lack it.
   */
  proposed: Array<{ role: string; name: string; title: string; rationale: string; source?: 'library' | 'derived' }>;
  /** How many proposed seats the reduction cut past its cap; absent reads as 0. */
  proposed_dropped?: number;
  /** selection.stage_code: why this list could seat nobody (no_answer, no_block, too_few, unparseable), else null. */
  code?: string | null;
  /** The stakeholders this selector left out, the first thread.LIST_MAX; absent on older payloads. */
  not_seated?: Array<Omit<Considered, 'role'>>;
  /** How many more it left out, and how many of its entries validate refused; absent reads as 0. */
  not_seated_dropped?: number;
  invalid_count?: number;
  segments: Segment[];
  badges: string[];
  take: number | null;
  takes: number | null;
  violations: string[];
  flags: string[];
};

/** A stakeholder the selectors named and did not seat. */
export type Considered = {
  stakeholder: string;
  role: string | null;
  reason: string;
  represented_by: string | null;
  represented_by_name: string | null;
};

/** `view_data`'s `selection` block. It is null on a run from before selection. */
export type Selection = {
  state: 'selecting' | 'seated' | 'fallback' | 'lost';
  stages: SelectionStage[];
  fallback: string | null;
  considered: Considered[];
  /** What resolve's caps cut (spec amendment FIX_SA); absent reads as 0. */
  considered_dropped?: number;
  invalid_dropped?: number;
  /** The selector working now, only while `selecting`; absent on older payloads. */
  current?: { role: string; name: string; verb: 'proposing' | 'amending' | 'ratifying' } | null;
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
  /** owner closed · queue empty · turn cap · chair turn failed · chair retake failed */
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
   * selection C6: the stages, the stakeholders considered and any fallback.
   * null for a run from before selection, and absent on a payload older than
   * the key. Every guard reads it with `== null` / `!= null`, so absent is null.
   */
  selection?: Selection | null;
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
  tells: 'AI tells',
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

/** voice.tells' non-zero counts as plain text, "process 2, turn refs 1": the tells badge's title. */
function tellsText(voice: Entry['voice']): string | undefined {
  const tells = voice?.tells;
  if (!tells || typeof tells !== 'object') return undefined;
  return Object.entries(tells)
    .filter(([, n]) => typeof n === 'number' && n > 0)
    .map(([kind, n]) => `${kind.replaceAll('_', ' ')} ${n}`)
    .join(', ');
}

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
  'chair retake failed':
    "The chair's retake failed, so its earlier take is recorded unruled and the run ended failed.",
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
              ended === 'turn cap' || ended === 'chair turn failed' || ended === 'chair retake failed'
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

/** Who put a seat forward, as the roster says it. Null when the row records nobody. */
function nominated(p: Persona): string | null {
  if (p.nominated_by === 'fixed') return 'fixed seat';
  if (p.nominated_by === 'default') return 'default seat';
  if (p.nominated_by) return `put forward by ${p.nominated_by_name ?? p.nominated_by}`;
  return null;
}

function Roster({ roster, legacy }: { roster: Persona[]; legacy: boolean }) {
  const { Badge } = ds();
  return (
    <Section title={`Committee — ${roster.length}`}>
      <ul
        aria-label="Committee"
        style={{ display: 'flex', flexDirection: 'column', listStyle: 'none', margin: 0, padding: 0 }}
      >
        {roster.map((p) => (
          <li
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
            {/* The slug is the seat's identity; the name and title beside it
                are, for a derived seat, a selector's words. So a derived seat
                says so here, and one that copies the owner's name and title
                still cannot pass for her. */}
            <span style={{ ...mono, fontSize: 10, color: 'var(--text-muted)' }}>
              {p.role}
              {p.source === 'derived' && ' · derived seat'}
            </span>
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
            {/* Why the seat is in the room and who put it there. Only a run
                that went through selection records either. A legacy row
                carries nulls and shows neither, never a blank "why:". Plain
                text: a rationale is worker-written. */}
            {p.rationale != null && (
              <div style={{ flexBasis: '100%', display: 'flex', gap: 8, flexWrap: 'wrap', fontSize: 12 }}>
                <span data-testid={`roster-why-${p.role}`} style={{ color: 'var(--text-secondary)' }}>
                  why: {p.rationale}
                </span>
                {nominated(p) !== null && (
                  <span data-testid={`roster-nominated-${p.role}`} style={{ color: 'var(--text-muted)' }}>
                    {nominated(p)}
                  </span>
                )}
              </div>
            )}
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
          </li>
        ))}
      </ul>
    </Section>
  );
}

// --- selection ---------------------------------------------------------------
//
// How this committee came to be seated: each selector's words and list, the
// stakeholders named but not seated and who speaks for them, and why the run
// fell back when it did. Each seat's reason and nominator are on the roster
// above; this card is the exchange that produced them. It sits directly under
// the roster on both layouts, so it is on screen before anyone has spoken.
// Every string but the stage prose is worker-written plain text; the prose
// goes through Segments only, as a turn's does.

const STAGE_VERB: Record<number, string> = { 1: 'proposes', 2: 'amends', 3: 'ratifies' };

const selectionNotice = {
  fontSize: 12,
  padding: '6px 8px',
  borderRadius: 'var(--radius-md)',
  background: 'var(--wash-subtle)',
  border: '1px solid var(--border-hairline)',
  color: 'var(--status-attention, #e3b341)',
} as const;

const selectionHeading = { margin: 0, fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' } as const;
const selectionList = { margin: 0, paddingLeft: 18, fontSize: 12, color: 'var(--text-secondary)' } as const;
const selectionCount = { fontSize: 11.5, fontStyle: 'italic', color: 'var(--text-muted)' } as const;

/** A derived seat's marker (decision 12): its name is a selector's words, the slug is not. */
const derivedSeat = (role: string) => `${role} · derived seat`;

/**
 * Who speaks for a stakeholder nobody seated, or that nobody does. The name
 * check is exact, so a lookalike name passes it: a derived seat's slug is the defence.
 */
function represented(slug: string | null, name: string | null, isDerived: boolean): string {
  if (!slug) return 'Not represented.';
  return `Represented by ${name ?? slug}${isDerived ? ` (${derivedSeat(slug)})` : ''}.`;
}

/** selection.fallback_words: a stage or fallback code as thread.md says it; an unknown code is itself. */
const WORDS: Record<string, string> = {
  chair_failed: 'the chair gave no usable list',
  no_block: 'no hermes-selection block',
  unparseable: 'a hermes-selection block that did not parse',
  too_few: 'no valid seats',
};

/** "kept take 2 of 2; broke: …" when a take was retaken or kept flagged, else nothing. */
function KeptTake({
  take,
  takes,
  violations,
  testId,
}: {
  take?: number | null;
  takes?: number | null;
  violations: string[];
  testId: string;
}) {
  if (take == null || takes == null || (takes <= 1 && violations.length === 0)) return null;
  return (
    <div data-testid={testId} style={{ fontSize: 11.5, marginBottom: 6, color: 'var(--text-muted)' }}>
      kept take {take} of {takes}
      {violations.length > 0 && `; broke: ${violationText(violations)}`}
    </div>
  );
}

function SelectionCard({
  selection,
  runId,
  derived,
}: {
  selection: Selection;
  runId: string;
  derived: Set<string>;
}) {
  const { Badge } = ds();
  // Only the final reduction settles who was considered. Before it (selecting,
  // lost) the list is empty because nothing is resolved yet, and "Everyone
  // considered was seated." would be a confident falsehood.
  const settled = selection.state === 'seated' || selection.state === 'fallback';
  const considered = selection.considered_dropped ?? 0;
  const invalid = selection.invalid_dropped ?? 0;
  return (
    <div data-testid="selection-card">
      <Section title="Selection">
        {selection.fallback && (
          <div data-testid="selection-fallback" style={selectionNotice}>
            Default committee: selection fell back ({WORDS[selection.fallback] ?? selection.fallback})
          </div>
        )}
        {selection.state === 'lost' && (
          <div data-testid="selection-lost" style={selectionNotice}>
            Selection stopped: the meeting was lost.
          </div>
        )}
        {selection.stages.map((st, i) => (
          <div
            key={i}
            data-testid={`selection-stage-${st.stage}`}
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 6,
              paddingTop: 8,
              borderTop: '1px solid var(--border-hairline)',
            }}
          >
            <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap' }}>
              {/* Not an h3: Section's title is no heading, so there is no level for it to sit under. */}
              <div style={selectionHeading}>
                {st.name} ({st.role}) {STAGE_VERB[st.stage] ?? ''}
              </div>
              {/* Exactly as a timeline entry badges its turn. */}
              {st.badges.map((b) => (
                <Badge key={b} size="sm" variant="outline" tone={BADGE_TONE[b]}>
                  {BADGE_LABEL[b] ?? b}
                </Badge>
              ))}
            </div>
            <KeptTake
              take={st.take}
              takes={st.takes}
              violations={st.violations}
              testId={`selection-kept-take-${st.stage}`}
            />
            <Segments segments={st.segments} runId={runId} />
            {/* The body arrives with its hermes-selection fence stripped, so
                the list the selector gave is drawn here from the reduction. */}
            {st.proposed.length > 0 && (
              <ul
                data-testid={`selection-proposed-${st.stage}`}
                aria-label={`Seats ${st.name} listed`}
                style={selectionList}
              >
                {st.proposed.map((p, j) => (
                  <li key={j}>
                    {p.source === 'derived' || derived.has(p.role) ? derivedSeat(p.role) : p.role}: {p.name},{' '}
                    {p.title}. Why: {p.rationale}
                  </li>
                ))}
              </ul>
            )}
            {(st.proposed_dropped ?? 0) > 0 && <div style={selectionCount}>{st.proposed_dropped} more not listed.</div>}
            {/* A representative is on this stage's list or the fixed four, so a
                derived one the chair later dropped is marked off that list. */}
            {!!st.not_seated?.length && (
              <ul data-testid={`selection-left-out-${st.stage}`} aria-label={`Left out by ${st.name}`} style={selectionList}>
                {st.not_seated.map((n, j) => (
                  <li key={j}>
                    Left out: {n.stakeholder}: {n.reason.replace(/\.$/, '')}.{' '}
                    {represented(
                      n.represented_by,
                      n.represented_by_name,
                      derived.has(n.represented_by ?? '') ||
                        st.proposed.some((p) => p.role === n.represented_by && p.source === 'derived'),
                    )}
                  </li>
                ))}
              </ul>
            )}
            {(st.not_seated_dropped ?? 0) > 0 && (
              <div style={selectionCount}>{st.not_seated_dropped} more left out, not listed.</div>
            )}
            {(st.invalid_count ?? 0) > 0 && <div style={selectionCount}>{st.invalid_count} invalid entries, not listed.</div>}
            {/* As its thread entry says it; an undelivered stage says so through its badge and body. */}
            {st.code && st.code !== 'no_answer' && (
              <div data-testid={`selection-code-${st.stage}`} style={selectionCount}>
                no usable seat list: {WORDS[st.code] ?? st.code}
              </div>
            )}
          </div>
        ))}
        {/* The stage in progress, after the ones kept: its selector's worker is still writing. */}
        {selection.current && (
          <div data-testid="selection-current" style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
            {selection.current.name} is {selection.current.verb} the committee.
          </div>
        )}
        {settled && (
          <div
            data-testid="selection-considered"
            style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: 'var(--text-secondary)' }}
          >
            {/* As thread.append_seated says it: "everyone was seated" only when nothing was cut either. */}
            {selection.considered.length === 0 && considered + invalid === 0 ? (
              'Everyone considered was seated.'
            ) : (
              <>
                <div style={selectionHeading}>Considered, not seated</div>
                {/* No empty list when only the counts below were cut. */}
                {selection.considered.length > 0 && (
                  <ul aria-label="Considered, not seated" style={selectionList}>
                    {selection.considered.map((c, j) => (
                      <li key={j}>
                        {c.stakeholder}: {c.reason.replace(/\.$/, '')}.{' '}
                        {represented(c.represented_by, c.represented_by_name, derived.has(c.represented_by ?? ''))}
                      </li>
                    ))}
                  </ul>
                )}
                {considered > 0 && <div style={selectionCount}>{considered} more considered, not listed.</div>}
                {invalid > 0 && <div style={selectionCount}>{invalid} more invalid entries, not listed.</div>}
              </>
            )}
          </div>
        )}
      </Section>
    </div>
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
  derived,
}: {
  runId: string;
  entry: Entry;
  open: boolean;
  onToggle: () => void;
  /** The 1-based edit step this turn delegated or applied, if any. */
  edit?: number;
  onSeeEdit: () => void;
  /** The speaker's seat is one a selector invented (the roster's `source`). */
  derived: boolean;
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
        {/* A derived seat's name and title are a selector's words: the slug
            and the marker say whose turn it is, as the roster row does. */}
        {derived && (
          <span style={{ ...mono, fontSize: 10, color: 'var(--text-muted)' }}>{entry.role} · derived seat</span>
        )}
        {entry.badges.map((b) => (
          <Badge
            key={b}
            size="sm"
            variant="outline"
            tone={BADGE_TONE[b]}
            title={b === 'tells' ? tellsText(entry.voice) : undefined}
          >
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
          <KeptTake take={entry.take} takes={entry.takes} violations={violations} testId={`kept-take-${entry.n}`} />
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
  derived,
}: {
  runId: string;
  timeline: Entry[];
  /** Held by the view, so a step's `tNN` link can open an entry from outside. */
  open: Set<number>;
  setOpen: React.Dispatch<React.SetStateAction<Set<number>>>;
  /** turn -> [1-based edit number, that step's junior turn], for reviewer, owner and junior rows. */
  edits: Map<number, [number, number]>;
  onSeeEdit: (turn: number) => void;
  /** Roles whose seat a selector invented. */
  derived: Set<string>;
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
          derived={derived.has(entry.role)}
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

/** Every voice.summary key, in C11 order, as a reader would say it. */
const VOICE_LABEL: Array<[string, string]> = [
  ['owner_reviewer_median_words', 'median words, owner and reviewers'],
  ['owner_reviewer_pct_within_cap', '% owner and reviewer turns within the cap'],
  ['median_words_by_role', 'median words by role'],
  ['chair_words', 'chair words'],
  ['chair_headers', 'chair headers'],
  ['chair_tables', 'chair tables'],
  ['junior_turns', 'junior IC reports'],
  ['junior_pct_compliant', '% junior IC reports in one sentence of 40 words or fewer'],
  ['pct_clean_format', '% turns with no bold, headers, tables or nesting'],
  ['pct_first_line_le_25', '% owner and reviewer first lines of 25 words or fewer'],
  ['unquoted_dashes', 'dashes outside quotes'],
  ['reviewer_pct_with_pointer', '% reviewer turns with a pointer'],
  ['max_turn_refs', 'most turn-number references in one turn'],
  ['unchanged_mentions_junior_chair', 'mentions of the original being unchanged, junior IC and chair'],
  ['total_takes', 'takes dispatched'],
  ['retakes_by_role', 'retakes by role'],
  ['kept_flagged', 'turns kept with broken rules'],
];

/** A number as itself, a missing one as a dash, a per-role map as `role n, role n`. */
function voiceValue(value: VoiceSummary[string] | undefined): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'object') {
    return Object.entries(value)
      .map(([role, n]) => `${role} ${n ?? '—'}`)
      .join(', ');
  }
  return String(value);
}

function MeetingMetrics({ data, derived }: { data: CommitteeData; derived: Set<string> }) {
  const turns = [...data.timeline].sort((a, b) => a.n - b.n);
  const delivered = (e: Entry) => !e.badges.includes('no_turn');
  const over = data.verdict !== null;
  const voice = data.voice ?? null;

  // Turns per seat, every seat included; a turn nobody can be named for gets
  // its own row rather than vanishing from the total.
  const seats = [
    ...data.roster.map((p) => ({
      key: p.role,
      name: p.name,
      derived: p.source === 'derived',
      of: (e: Entry) => e.role === p.role,
    })),
    {
      key: 'unattributed',
      name: 'speaker not identified',
      derived: false,
      of: (e: Entry) => e.badges.includes('unattributed'),
    },
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
              <span style={{ width: 130, flex: 'none', color: 'var(--text-primary)' }}>
                {s.name}
                {/* A derived seat's name is a selector's words; the slug says whose row it is. */}
                {s.derived && (
                  <span style={{ ...mono, display: 'block', fontSize: 10, color: 'var(--text-muted)' }}>
                    {s.key} · derived seat
                  </span>
                )}
              </span>
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
              {a.name}
              {derived.has(a.role) && ` (${derivedSeat(a.role)})`} asked on turn {a.asked} ·{' '}
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

      {/* Never hidden: a run reduced before voice says so instead. */}
      <Section title="Voice">
        {voice ? (
          <div data-testid="voice-metrics" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {VOICE_LABEL.map(([key, label]) => (
              <div key={key} data-testid={`voice-metric-${key}`} style={row}>
                <span style={{ flex: 1, color: 'var(--text-secondary)' }}>{label}</span>
                <span style={{ ...mono, flex: 'none' }}>{voiceValue(voice[key])}</span>
              </div>
            ))}
          </div>
        ) : (
          <div data-testid="voice-not-measured" style={quiet}>
            not measured for this run
          </div>
        )}
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
  // Seats a selector invented, by role: their rows say so wherever they appear.
  const derived = new Set(data.roster.filter((p) => p.source === 'derived').map((p) => p.role));

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
        derived={derived}
      />
    </Section>
  );

  // An empty timeline, NOT `&& roster.length === 0`: `view_data` always sends
  // roster rows (the fixed four while a committee is being seated), so a
  // roster-length test can never fire on real data. This guard is for a run
  // with nothing to show yet: phase `open`, or a run from before selection
  // whose first turn has not settled (`selection` null, or absent on an older
  // payload). A run that is seating its committee does have something to show,
  // and falls through to the pre-t01 layout below. The Metrics tab is the
  // exception: it counts turns, and there are none.
  if (data.timeline.length === 0 && (data.selection == null || variant === 'metrics')) {
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
        <MeetingMetrics data={data} derived={derived} />
        <EvaluationBlock runId={runId} evaluation={data.evaluation ?? null} scorable={!!data.verdict?.text} />
      </div>
    );

  // Before t01, on a run that is seating its committee (the gate above has
  // returned for every other empty timeline). Nothing has been said in the
  // meeting yet, but who is in the room, why, and who put them there is
  // already known, so the tab shows that. There is no transcript and no
  // verdict card, which would only restate "nothing yet". No Document card
  // either (C6): it comes with t01, like the transcript, even though `open`
  // has already kept the original. doc-diff's pre-t01 card stays on the gate's
  // empty-state branch above, for runs with `selection` null.
  if (data.timeline.length === 0) {
    // The selector at work holds the floor, which only a turn sets on the server's rows.
    const current = data.selection?.current;
    const roster = data.roster.map((p) => (p.role === current?.role ? { ...p, state: 'holds_floor' } : p));
    return (
      <div data-testid="committee-view" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <ProgressBar progress={data.progress} legacy={legacy} />
        <Roster roster={roster} legacy={legacy} />
        {data.selection != null && <SelectionCard selection={data.selection} runId={runId} derived={derived} />}
      </div>
    );
  }

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
      {data.selection != null && <SelectionCard selection={data.selection} runId={runId} derived={derived} />}
      <Timeline
        runId={runId}
        timeline={data.timeline}
        open={open}
        setOpen={setOpen}
        edits={edits}
        onSeeEdit={seeEdit}
        derived={derived}
      />
      <Verdict runId={runId} verdict={data.verdict} />
      {history}
    </div>
  );
}

// On the function, not a second export: the UMD global IS this function, and
// the host reads the sections it may ask for off it.
CommitteeView.variants = ['metrics'];
