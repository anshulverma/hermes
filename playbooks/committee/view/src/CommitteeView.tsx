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
import { Markdown } from './host';
import Verdict from './Verdict';
import ArtifactDiff from './Diff';

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
};

export type Progress = {
  turn: number;
  cap: number;
  holder: string | null;
  queue: string[];
  /** owner closed · queue empty · turn cap · chair turn failed */
  ended: string | null;
};

export type CommitteeData = {
  kind: string;
  roster: Persona[];
  progress: Progress;
  timeline: Entry[];
  stances: Record<string, Array<{ turn: number; text: string }>>;
  verdict: {
    text: string;
    checks: Array<{ turn: number; action: string; verified: boolean | null }>;
    artifact_intact: boolean | null;
    dropped_delegation: string | null;
    dropped_floor_requests: string[];
    simulation: boolean;
  } | null;
  artifacts: {
    /**
     * Null until some reduction names a path, which in phase `open` is never —
     * `view_data`'s `_artifacts` returns `{"original": None, "revised": None}`
     * for a run with no reductions, and that is exactly when the tab first
     * appears. Typed honestly here so `tsc` forces the branch downstream
     * instead of letting `original.name` throw into the error boundary.
     */
    original: { name: string; bytes: number } | null;
    revised: { name: string; bytes: number } | null;
  };
};

export type CommitteeViewProps = {
  runId: string;
  data: CommitteeData;
  refetch: () => void;
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
 * The design-system namespace, resolved exactly as `web/src/ds/index.ts` does.
 * The bundle publishes the hashed name and nothing publishes `DSNS`, so the
 * fallback is the compatibility half of the same expression, not a guess.
 */
function ds(): Record<string, any> {
  const w = window as unknown as Record<string, Record<string, any>>;
  return w.MonoDarkDashDesignSystem_66fdfe || w.DSNS;
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
};

const BADGE_TONE: Record<string, string | undefined> = {
  no_turn: 'danger',
  error: 'danger',
  unattributed: 'danger',
  signals_only: 'attention',
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

      {/* Why it stopped. The first live run hit the turn cap and nothing on
          screen said so, which is the whole reason this line exists. */}
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
  entry,
  open,
  onToggle,
}: {
  entry: Entry;
  open: boolean;
  onToggle: () => void;
}) {
  const { Badge } = ds();
  const firstLine = entry.body.split('\n').find((l) => l.trim()) ?? '';
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

      {open ? (
        <div style={{ marginTop: 6, paddingLeft: 18, color: 'var(--text-muted)' }}>
          {entry.body ? <Markdown fontSize={12}>{entry.body}</Markdown> : noProse}
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

function Timeline({ timeline }: { timeline: Entry[] }) {
  const [open, setOpen] = useState<Set<number>>(new Set());
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
          entry={entry}
          open={open.has(entry.n)}
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

// --- the view ----------------------------------------------------------------

export default function CommitteeView({ runId, data }: CommitteeViewProps) {
  const { EmptyState } = ds();

  // The timeline alone, NOT `&& roster.length === 0`. `view_data`'s `_roster`
  // walks `cast.CAST`, so it returns all nine rows from the first poll onward
  // and a roster-length test can never fire on real data. The state this guard
  // exists for is a run in phase `open`: no reductions, so no timeline, no
  // verdict and BOTH artifacts null — and it is exactly when the tab first
  // appears.
  if (data.timeline.length === 0) {
    return (
      <div style={{ padding: 32 }}>
        <EmptyState
          title="Nothing said yet"
          description="The committee view fills in as each member takes the floor."
          icon="inbox"
        />
      </div>
    );
  }

  // A run captured before this view existed. Its reductions predate `body`,
  // `stance`, `ended`, `artifact` and `revised`, so `view_data` returns those
  // five as null/empty and every card would render a confident, reassuring
  // falsehood from a partial input: "Still in session." for a `done` run, nine
  // seats with "no stance stated", twenty blank rows, and "no artifact has been
  // recorded" for a run that reviewed an 11,397-byte file. Neither signal is a
  // flag the master sets; both are shapes `reduce` can no longer produce.
  const legacy =
    (data.timeline.length > 0 && data.artifacts.original === null) ||
    (data.verdict !== null && data.progress.ended === null);

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
      <Timeline timeline={data.timeline} />
      <Verdict runId={runId} verdict={data.verdict} />
      {/* `intact` and not just `artifacts`: the diff card guarantees the
          original was untouched, and only the verdict knows whether it was. */}
      <ArtifactDiff
        runId={runId}
        artifacts={data.artifacts}
        intact={data.verdict?.artifact_intact ?? null}
        legacy={legacy}
      />
    </div>
  );
}
