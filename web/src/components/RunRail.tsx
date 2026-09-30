/**
 * RunRail - every run in three groups (Needs you, Active, Finished) beside the
 * run pane. Presentational: App owns the runs list, the route and the rail's
 * view state (useRailState) and hands in railGroups' result; nothing here fetches.
 */

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type FocusEvent,
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
} from 'react';
import { Badge, Button, Divider, IconButton, Input } from '../ds';
import type { Run } from '../api/client';
import { buildRoute, type RunTab } from '../hooks/useRoute';
import { useNow } from '../hooks/useNow';
import { fmtAgo, fmtTime } from '../util/time';

const HIDDEN_KEY = 'hermes.rail.hiddenPlaybooks';
const COLLAPSED_KEY = 'hermes.rail.collapsed';
const FINISHED_CAP = 10;
const ACTIVE_STATES = new Set(['running', 'paused']);

export type RailGroups = {
  needsYou: Run[];
  active: Run[];
  /** Already capped, plus the selected run when it falls beyond the cap. */
  finished: Run[];
  moreFinished: number;
  hiddenCount: number;
  hiddenAwaiting: number;
};

const byIdDesc = (a: Run, b: Run) => (a.id < b.id ? 1 : a.id > b.id ? -1 : 0);
const byCreatedDesc = (a: Run, b: Run) => b.created_at - a.created_at || byIdDesc(a, b);
const byUpdatedDesc = (a: Run, b: Run) => b.updated_at - a.updated_at || byIdDesc(a, b);

function matchesFilter(run: Run, filter: string): boolean {
  const needle = filter.toLowerCase();
  return [run.id, run.playbook, run.phase, run.subject].some(
    (field) => field != null && field.toLowerCase().includes(needle),
  );
}

export function railGroups(
  runs: Run[],
  hidden: ReadonlySet<string>,
  filter: string,
  showAllFinished: boolean,
  selectedId: string | null,
): RailGroups {
  const needsYou: Run[] = [];
  const active: Run[] = [];
  const allFinished: Run[] = [];
  let hiddenCount = 0;
  let hiddenAwaiting = 0;
  for (const run of runs) {
    if (hidden.has(run.playbook) || (filter !== '' && !matchesFilter(run, filter))) {
      hiddenCount += 1;
      hiddenAwaiting += run.awaiting;
    } else if (run.awaiting > 0) {
      needsYou.push(run);
    } else if (ACTIVE_STATES.has(run.state)) {
      active.push(run);
    } else {
      allFinished.push(run);
    }
  }
  needsYou.sort(byCreatedDesc);
  active.sort(byCreatedDesc);
  allFinished.sort(byUpdatedDesc);
  if (filter !== '' || showAllFinished) {
    return { needsYou, active, finished: allFinished, moreFinished: 0, hiddenCount, hiddenAwaiting };
  }
  const finished = allFinished.slice(0, FINISHED_CAP);
  const selected = allFinished.findIndex((r) => r.id === selectedId);
  if (selected >= FINISHED_CAP) finished.push(allFinished[selected]);
  return {
    needsYou,
    active,
    finished,
    moreFinished: allFinished.length - finished.length,
    hiddenCount,
    hiddenAwaiting,
  };
}

/**
 * The run to open when the address names none: the first Needs you run, else
 * the first Active run, else the newest; over the runs the chips show, or over
 * every run when the chips hide them all. Ignores the filter text.
 */
export function defaultRunId(runs: Run[], hidden: ReadonlySet<string>): string | null {
  const onChips = runs.filter((r) => !hidden.has(r.playbook));
  const pool = onChips.length > 0 ? onChips : runs;
  const { needsYou, active } = railGroups(pool, new Set(), '', true, null);
  return (needsYou[0] ?? active[0] ?? [...pool].sort(byCreatedDesc)[0])?.id ?? null;
}

/** 'starting' / 'not started' stand in for a phase that is still null. */
export function phaseLabel(run: Pick<Run, 'phase' | 'state'>): string {
  return run.phase ?? (ACTIVE_STATES.has(run.state) ? 'starting' : 'not started');
}

// localStorage can throw (storage disabled, a sandboxed frame). The React state
// in useRailState is then the only copy, so the choice holds for the session.
function readStored(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStored(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Kept in memory only.
  }
}

/** The HIDDEN playbooks, so a playbook seen for the first time is shown. */
function readHidden(): ReadonlySet<string> {
  try {
    const parsed: unknown = JSON.parse(readStored(HIDDEN_KEY) ?? '[]');
    if (Array.isArray(parsed) && parsed.every((p) => typeof p === 'string')) return new Set(parsed);
  } catch {
    // Not JSON: the default below.
  }
  return new Set();
}

/** '1' collapsed, '0' expanded, anything else the viewport default, read once. */
function readCollapsed(): boolean {
  const stored = readStored(COLLAPSED_KEY);
  if (stored === '1') return true;
  if (stored === '0') return false;
  return window.innerWidth < 1024;
}

export function useRailState() {
  const [hidden, setHiddenState] = useState<ReadonlySet<string>>(readHidden);
  const [collapsed, setCollapsedState] = useState(readCollapsed);
  const [filter, setFilter] = useState('');
  const [showAllFinished, setShowAllFinished] = useState(false);

  const setHidden = useCallback((next: ReadonlySet<string>) => {
    setHiddenState(next);
    writeStored(HIDDEN_KEY, JSON.stringify([...next]));
  }, []);

  const setCollapsed = useCallback((next: boolean) => {
    setCollapsedState(next);
    writeStored(COLLAPSED_KEY, next ? '1' : '0');
  }, []);

  return { hidden, setHidden, filter, setFilter, showAllFinished, setShowAllFinished, collapsed, setCollapsed };
}

// One shape per state, so the state never rests on colour alone.
const STATE_SHAPES: Record<string, ReactNode> = {
  running: (
    <circle cx="6" cy="6" r="3.5" fill="var(--status-live)" style={{ animation: 'fm-pulse 1.6s ease-out infinite' }} />
  ),
  paused: (
    <>
      <rect x="3" y="2.5" width="2" height="7" fill="currentColor" />
      <rect x="7" y="2.5" width="2" height="7" fill="currentColor" />
    </>
  ),
  done: <path d="M2.5 6.5l2.5 2.5 4.5-5" fill="none" stroke="var(--status-ok)" strokeWidth="1.6" />,
  failed: <path d="M3 3l6 6M9 3l-6 6" fill="none" stroke="var(--status-danger)" strokeWidth="1.6" />,
  stopped: <rect x="3" y="3" width="6" height="6" fill="currentColor" />,
};

/** The run state as an icon, named by the state word (RunHeader draws it too). */
export function RunStateIcon({ state }: { state: string }) {
  return (
    <span role="img" aria-label={state} title={state} style={{ display: 'inline-flex', flex: 'none' }}>
      <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
        {STATE_SHAPES[state]}
      </svg>
    </span>
  );
}

type GroupKey = 'needsYou' | 'active' | 'finished';

const GROUPS: { key: GroupKey; label: string }[] = [
  { key: 'needsYou', label: 'Needs you' },
  { key: 'active', label: 'Active' },
  { key: 'finished', label: 'Finished' },
];

type FocusedRow = { id: string; group: GroupKey; index: number; el: HTMLAnchorElement };

type RunRailProps = {
  groups: RailGroups;
  playbooks: string[];
  rail: ReturnType<typeof useRailState>;
  error: Error | null;
  onRetry: () => void;
  selectedRunId: string | null;
  tab: RunTab;
  filterRef: RefObject<HTMLInputElement | null>;
};

const linkButton = {
  background: 'none',
  border: 'none',
  padding: 0,
  color: 'var(--text-secondary)',
  font: 'inherit',
  textDecoration: 'underline',
  cursor: 'pointer',
} as const;

export default function RunRail({
  groups,
  playbooks,
  rail,
  error,
  onRetry,
  selectedRunId,
  tab,
  filterRef,
}: RunRailProps) {
  const now = useNow();
  const listId = useId();
  const rows = useRef(new Map<string, HTMLAnchorElement>());
  const focusedRow = useRef<FocusedRow | null>(null);
  const beforeFilter = useRef<HTMLElement | null>(null);
  const shownBeforeMore = useRef<Set<string> | null>(null);
  const visible = [...groups.needsYou, ...groups.active, ...groups.finished];
  const total = visible.length + groups.moreFinished + groups.hiddenCount;
  const selectedShown = visible.some((r) => r.id === selectedRunId);

  // A new selection scrolls into view, and takes focus when a row had it
  // (`[` / `]` pressed on a row). A background refetch does neither.
  useEffect(() => {
    const el = selectedRunId == null ? undefined : rows.current.get(selectedRunId);
    if (!el) return;
    el.scrollIntoView({ block: 'nearest' });
    const focused = document.activeElement;
    if (focused !== el && [...rows.current.values()].some((row) => row === focused)) el.focus();
  }, [selectedRunId, selectedShown]);

  // A refetch that moves the focused row to another group or behind the cap
  // unmounts it: focus follows the run, else the row now in its old place in
  // that group, else the filter box. Nothing scrolls.
  useEffect(() => {
    const was = focusedRow.current;
    if (!was || was.el.isConnected) return;
    focusedRow.current = null;
    if (document.activeElement !== document.body) return;
    const inPlace = groups[was.group][was.index];
    const next = rows.current.get(was.id) ?? (inPlace && rows.current.get(inPlace.id)) ?? filterRef.current;
    next?.focus({ preventScroll: true });
  }, [groups, filterRef]);

  // After "show N more", focus goes to the first row it revealed.
  useEffect(() => {
    const before = shownBeforeMore.current;
    if (!before) return;
    shownBeforeMore.current = null;
    const first = groups.finished.find((r) => !before.has(r.id));
    if (first) rows.current.get(first.id)?.focus();
  }, [groups]);

  function onFilterFocus(e: FocusEvent<HTMLInputElement>) {
    const from = e.relatedTarget;
    beforeFilter.current = from instanceof HTMLElement && from !== document.body ? from : null;
  }

  function onFilterKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      if (visible.length > 0) rows.current.get(visible[0].id)?.click();
    } else if (e.key === 'Escape') {
      if (rail.filter !== '') {
        rail.setFilter('');
      } else {
        const back = beforeFilter.current;
        (back?.isConnected ? back : document.querySelector<HTMLElement>('main h1'))?.focus();
      }
    }
  }

  function togglePlaybook(playbook: string) {
    const next = new Set(rail.hidden);
    if (next.has(playbook)) next.delete(playbook);
    else next.add(playbook);
    rail.setHidden(next);
  }

  function showAll() {
    rail.setFilter('');
    rail.setHidden(new Set());
  }

  function showMore() {
    shownBeforeMore.current = new Set(groups.finished.map((r) => r.id));
    rail.setShowAllFinished(true);
  }

  function rowRef(id: string) {
    return (el: HTMLAnchorElement | null) => {
      if (el) rows.current.set(id, el);
      else rows.current.delete(id);
    };
  }

  const waitingRuns = groups.needsYou.length;

  return (
    <nav
      aria-label="Runs"
      style={{
        width: rail.collapsed ? 48 : 232,
        flex: 'none',
        boxSizing: 'border-box',
        display: 'flex',
        flexDirection: 'column',
        alignItems: rail.collapsed ? 'center' : 'stretch',
        gap: 12,
        minHeight: 0,
        overflowY: 'auto',
        padding: rail.collapsed ? '16px 8px' : '16px 12px',
        borderRight: '1px solid var(--border-hairline)',
      }}
    >
      <IconButton
        icon={rail.collapsed ? 'panel-left-open' : 'panel-left-close'}
        label={rail.collapsed ? 'Show runs' : 'Hide runs'}
        size="sm"
        aria-expanded={!rail.collapsed}
        aria-controls={listId}
        onClick={() => rail.setCollapsed(!rail.collapsed)}
        style={{ alignSelf: rail.collapsed ? 'center' : 'flex-end' }}
      >
        <span aria-hidden="true">{rail.collapsed ? '»' : '«'}</span>
      </IconButton>
      {rail.collapsed ? (
        waitingRuns > 0 && (
          <Badge tone="attention" size="sm" role="img" aria-label={`${waitingRuns} runs waiting on you`}>
            {waitingRuns}
          </Badge>
        )
      ) : (
        <div id={listId} style={{ display: 'flex', flexDirection: 'column', gap: 12, minHeight: 0 }}>
          {error && (
            <div role="alert" style={{ display: 'flex', flexDirection: 'column', gap: 6, color: 'var(--status-danger)', fontSize: 12 }}>
              <span>Couldn't load runs: {error.message}</span>
              <Button size="sm" variant="secondary" onClick={onRetry}>
                Retry
              </Button>
            </div>
          )}
          {total === 0 ? (
            !error && <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: 13 }}>No runs yet</p>
          ) : (
            <>
              <Input
                ref={filterRef}
                type="search"
                aria-label="Filter runs"
                placeholder="Filter runs (/)"
                aria-keyshortcuts="/"
                value={rail.filter}
                onChange={(e: any) => rail.setFilter(e.target?.value ?? e)}
                onFocus={onFilterFocus}
                onKeyDown={onFilterKeyDown}
              />
              <div role="group" aria-label="Playbooks" style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {playbooks.map((playbook) => {
                  const on = !rail.hidden.has(playbook);
                  return (
                    <button
                      key={playbook}
                      type="button"
                      aria-pressed={on}
                      onClick={() => togglePlaybook(playbook)}
                      style={{
                        display: 'inline-flex',
                        gap: 4,
                        padding: '2px 8px',
                        borderRadius: 'var(--radius-full)',
                        border: '1px solid var(--border-hairline)',
                        background: on ? 'var(--wash-selected)' : 'transparent',
                        color: on ? 'var(--text-primary)' : 'var(--text-muted)',
                        font: '400 12px var(--font-sans)',
                        cursor: 'pointer',
                      }}
                    >
                      {on && <span aria-hidden="true">✓</span>}
                      <span style={{ textDecoration: on ? 'none' : 'line-through' }}>{playbook}</span>
                    </button>
                  );
                })}
              </div>
              {groups.hiddenCount > 0 && (
                <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: 12 }}>
                  {groups.hiddenAwaiting > 0
                    ? `${groups.hiddenCount} hidden, ${groups.hiddenAwaiting} waiting on you`
                    : `${groups.hiddenCount} hidden by filters`}
                  {' · '}
                  <button type="button" onClick={showAll} style={linkButton}>
                    Show all
                  </button>
                </p>
              )}
              <Divider />
              {GROUPS.map(({ key, label }) =>
                groups[key].length === 0 ? null : (
                  <div key={key} style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                    <h2 style={{ margin: 0, padding: '0 4px 6px', color: 'var(--text-muted)', fontSize: 12, fontWeight: 400 }}>
                      {label}
                    </h2>
                    <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
                      {groups[key].map((run, index) => (
                        <RailRow
                          key={run.id}
                          run={run}
                          ended={key === 'finished'}
                          selected={run.id === selectedRunId}
                          href={buildRoute({ page: 'run', runId: run.id, tab, ticket: null })}
                          now={now}
                          rowRef={rowRef(run.id)}
                          onFocus={(el) => {
                            focusedRow.current = { id: run.id, group: key, index, el };
                          }}
                          onBlur={(movedTo) => {
                            if (movedTo) focusedRow.current = null;
                          }}
                        />
                      ))}
                    </ul>
                    {key === 'finished' && groups.moreFinished > 0 && (
                      <button type="button" onClick={showMore} style={{ ...linkButton, alignSelf: 'flex-start', padding: '4px' }}>
                        show {groups.moreFinished} more
                      </button>
                    )}
                  </div>
                ),
              )}
            </>
          )}
        </div>
      )}
    </nav>
  );
}

type RailRowProps = {
  run: Run;
  ended: boolean;
  selected: boolean;
  href: string;
  now: number;
  rowRef: (el: HTMLAnchorElement | null) => void;
  onFocus: (el: HTMLAnchorElement) => void;
  onBlur: (movedTo: EventTarget | null) => void;
};

function RailRow({ run, ended, selected, href, now, rowRef, onFocus, onBlur }: RailRowProps) {
  const id = useId();
  const [hover, setHover] = useState(false);
  const total = Object.values(run.tickets).reduce((sum, n) => sum + n, 0);
  const done = run.tickets.done ?? 0;
  const ts = ended ? run.updated_at : run.created_at;
  const waiting = run.awaiting > 0 ? `, ${run.awaiting} waiting on you` : '';
  const describedBy = [`${id}-phase`, `${id}-age`, `${id}-progress`]
    .concat(run.subject != null ? [`${id}-subject`] : [])
    .join(' ');
  const track = { flex: 1, height: 3, borderRadius: 2, background: 'var(--border-hairline)', overflow: 'hidden' };

  return (
    <li>
      <a
        ref={rowRef}
        href={href}
        aria-label={`${run.id}, ${run.playbook}, ${run.state}${waiting}`}
        aria-describedby={describedBy}
        aria-current={selected ? 'page' : undefined}
        onFocus={(e) => onFocus(e.currentTarget)}
        onBlur={(e) => onBlur(e.relatedTarget)}
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
        style={{
          position: 'relative',
          display: 'flex',
          flexDirection: 'column',
          gap: 3,
          padding: '6px 8px',
          borderRadius: 'var(--radius-lg)',
          background: selected ? 'var(--wash-selected)' : hover ? 'var(--wash-hover)' : 'transparent',
          color: 'var(--text-secondary)',
          fontSize: 12,
          textDecoration: 'none',
        }}
      >
        {selected && (
          <span
            aria-hidden="true"
            data-testid="rail-selected-bar"
            style={{ position: 'absolute', left: 0, top: 6, bottom: 6, width: 2, borderRadius: 1, background: 'var(--text-primary)' }}
          />
        )}
        <span style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
          <RunStateIcon state={run.state} />
          <span style={{ color: 'var(--text-primary)', fontSize: 13, fontWeight: selected ? 600 : 400 }}>{run.id}</span>
          <span style={{ color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {run.playbook}
          </span>
        </span>
        <span style={{ color: 'var(--text-muted)' }}>
          <span id={`${id}-phase`}>{phaseLabel(run)}</span>
          {' · '}
          <span id={`${id}-age`}>
            {ended ? 'ended' : 'started'}{' '}
            <time dateTime={new Date(ts * 1000).toISOString()} title={fmtTime(ts)}>
              {fmtAgo(ts, now)}
            </time>
          </span>
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {total > 0 ? (
            <span
              role="progressbar"
              aria-valuenow={done}
              aria-valuemin={0}
              aria-valuemax={total}
              aria-valuetext={`${done} of ${total} done`}
              style={track}
            >
              <span style={{ display: 'block', height: '100%', width: `${(done / total) * 100}%`, background: 'var(--status-ok)' }} />
            </span>
          ) : (
            <span aria-hidden="true" data-testid="rail-empty-track" style={track} />
          )}
          <span id={`${id}-progress`}>{total > 0 ? `${done}/${total}` : 'no tickets yet'}</span>
          {run.awaiting > 0 && (
            <Badge tone="attention" size="sm">
              {run.awaiting} waiting
            </Badge>
          )}
        </span>
        {run.subject != null && (
          <span id={`${id}-subject`} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {run.subject}
          </span>
        )}
      </a>
    </li>
  );
}
