/**
 * NeedsYou — every decision waiting on a person, across all runs.
 *
 * This is the human end of the no-trust invariant. Nothing auto-ships: when a
 * playbook's `reduce` or the master's independent re-verify routes a ticket to
 * `needs_human`, the reduction that did it lands here, and the decision
 * resolves the ticket — accept settles it to `done`, reject to `failed`.
 *
 * One page for every run, grouped by run with the longest wait first, so a
 * decision never sits unseen because its run was not the one on screen. A
 * reduction that is pure output holds no ticket and never appears here; read
 * those in the run's Outputs.
 */

import { useEffect, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import { fetchNeedsYou, acceptReduction, rejectReduction } from '../api/client';
import type { Event, NeedsYouItem, Run } from '../api/client';
import { normalizeReduction } from '../api/normalize';
import { Button } from '../ds';
import { LoadingOverlay } from '../components/Spinner';
import ReductionCard from '../components/ReductionCard';
import { reductionHeadline } from '../util/reduction';
import { fmtAgo, fmtSeconds, fmtTime } from '../util/time';
import { useNow } from '../hooks/useNow';
import { useStreamTrigger } from '../hooks/useStreamTrigger';
import { buildRoute, useRoute } from '../hooks/useRoute';

type NeedsYouProps = {
  runFilter: string | null;
  /** App's run list (null until it loads, or while it fails): the group headers' state labels. */
  runs: Run[] | null;
  streamEvents: Event[];
  onDecided: () => void;
  announce: (message: string) => void;
};

/**
 * One item's own request. `posting`: its accept / reject is in flight, and no
 * refetch may remove it. `conflict`: a 409 said it was decided elsewhere and
 * the refetch that settles it has not landed (already announced; the buttons
 * stay off until it does).
 */
type ItemState = { phase?: 'posting' | 'conflict'; note?: string; error?: string };
type ItemStates = Record<number, ItemState>;
type Group = { runId: string; playbook: string; items: NeedsYouItem[] };

const REJECT_CONFIRM = 'Reject this reduction? This will fail the tickets it is holding.';
const DECIDED_ELSEWHERE = 'Already decided elsewhere';
const ALL_RUNS = buildRoute({ page: 'needs-you', run: null });

const MUTED: CSSProperties = { color: 'var(--text-muted)', fontSize: 12 };
const ALERT: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  padding: '10px 14px',
  background: 'var(--status-danger-tint)',
  border: '1px solid var(--status-danger-edge)',
  borderRadius: 'var(--radius-md)',
  color: 'var(--status-danger)',
  fontSize: 13,
};
const TOGGLE: CSSProperties = {
  padding: 0,
  border: 'none',
  background: 'none',
  cursor: 'pointer',
  textAlign: 'left',
  fontFamily: 'inherit',
  fontSize: 14,
  color: 'var(--text-primary)',
};

const runHref = (runId: string) =>
  buildRoute({ page: 'run', runId, tab: 'summary', ticket: null });
const oldestFirst = (a: NeedsYouItem, b: NeedsYouItem) =>
  a.created_at - b.created_at || a.id - b.id;
const isRunEvent = (e: Event) => e.run_id != null;

/** Items come oldest first, so first-seen order puts the longest-waiting run first. */
function groupByRun(items: NeedsYouItem[], runFilter: string | null): Group[] {
  const groups = new Map<string, Group>();
  for (const item of items) {
    if (runFilter && item.run_id !== runFilter) continue;
    const group: Group = groups.get(item.run_id) ?? {
      runId: item.run_id,
      playbook: item.playbook,
      items: [],
    };
    group.items.push(item);
    groups.set(item.run_id, group);
  }
  return [...groups.values()];
}

/** The refetch a 409 asked for has settled: its item keeps the message and gets its buttons back. */
function settleConflicts(states: ItemStates): ItemStates {
  const next: ItemStates = {};
  for (const [id, state] of Object.entries(states)) {
    next[Number(id)] = state.phase === 'conflict' ? { note: state.note } : state;
  }
  return next;
}

export default function NeedsYou({
  runFilter,
  runs,
  streamEvents,
  onDecided,
  announce,
}: NeedsYouProps) {
  const now = useNow();
  const { navigate } = useRoute();
  const [items, setItems] = useState<NeedsYouItem[] | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [open, setOpen] = useState<ReadonlySet<number>>(new Set());
  const [itemStates, setItemStates] = useState<ItemStates>({});

  // A refetch and a POST's outcome land after the render that started them;
  // they read the latest items, open set and item states from these.
  const itemsRef = useRef<NeedsYouItem[]>([]);
  const openRef = useRef<ReadonlySet<number>>(open);
  const statesRef = useRef<ItemStates>({});
  const filterRef = useRef(runFilter);
  const loadSeq = useRef(0);
  const h1Ref = useRef<HTMLHeadingElement>(null);
  const rowRefs = useRef(new Map<number, HTMLLIElement>());
  const toggleRefs = useRef(new Map<number, HTMLButtonElement>());
  const focusTarget = useRef<number | 'h1' | null>(null);
  const autoOpenedFor = useRef<string | null | undefined>(undefined);

  useEffect(() => {
    filterRef.current = runFilter;
  }, [runFilter]);

  const showItems = (next: NeedsYouItem[]) => {
    itemsRef.current = next;
    setItems(next);
  };
  const showOpen = (next: ReadonlySet<number>) => {
    openRef.current = next;
    setOpen(next);
  };
  const showStates = (next: ItemStates) => {
    statesRef.current = next;
    setItemStates(next);
  };
  const patchState = (id: number, state: ItemState | null) => {
    const next = { ...statesRef.current };
    if (state) next[id] = state;
    else delete next[id];
    showStates(next);
  };
  const focusHeading = () => h1Ref.current?.focus();

  /**
   * Before rows go: when focus is inside one of them (or `always`, after the
   * reader's own decision), aim it at the next remaining row's toggle, else
   * the previous one, else the page heading. The effect below moves it once
   * the rows are gone.
   */
  const planFocus = (removed: ReadonlySet<number>, next: NeedsYouItem[], always: boolean) => {
    const order = groupByRun(itemsRef.current, filterRef.current).flatMap((g) =>
      g.items.map((i) => i.id),
    );
    const active = document.activeElement;
    const from = order.find(
      (id) => removed.has(id) && (always || !!rowRefs.current.get(id)?.contains(active)),
    );
    if (from === undefined) return;
    const left = new Set(next.map((i) => i.id));
    const at = order.indexOf(from);
    focusTarget.current =
      order.slice(at + 1).find((id) => left.has(id)) ??
      order
        .slice(0, at)
        .reverse()
        .find((id) => left.has(id)) ??
      'h1';
  };

  useEffect(() => {
    const target = focusTarget.current;
    if (target === null) return;
    focusTarget.current = null;
    if (target === 'h1') h1Ref.current?.focus();
    else toggleRefs.current.get(target)?.focus();
  }, [items]);

  const load = async () => {
    const seq = ++loadSeq.current;
    try {
      const fetched = await fetchNeedsYou();
      if (seq !== loadSeq.current) return; // a newer refetch owns the page
      const states = statesRef.current;
      const returned = new Set(fetched.map((i) => i.id));
      const missing = itemsRef.current.filter((i) => !returned.has(i.id));
      // A refetch never removes an item whose accept / reject is in flight:
      // accept_reduction emits its event in its own commit, so this can land
      // first. The request's own outcome removes it and announces it.
      const inFlight = missing.filter((i) => states[i.id]?.phase === 'posting');
      const dropped = missing.filter((i) => states[i.id]?.phase !== 'posting');
      const next = [...fetched, ...inFlight].sort(oldestFirst);
      for (const item of dropped) {
        // Speak only for what the reader had open, and not twice after a 409.
        if (openRef.current.has(item.id) && states[item.id]?.phase !== 'conflict') {
          announce(`${item.run_id}: decided elsewhere`);
        }
      }
      planFocus(new Set(dropped.map((i) => i.id)), next, false);
      const nextStates = settleConflicts(states);
      for (const item of dropped) delete nextStates[item.id];
      showStates(nextStates);
      setError(null);
      showItems(next);
    } catch (err) {
      if (seq !== loadSeq.current) return;
      showStates(settleConflicts(statesRef.current));
      setError(err instanceof Error ? err : new Error(String(err)));
    }
  };

  useEffect(() => {
    void load();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useStreamTrigger(streamEvents, isRunEvent, load);

  // With ?run= and exactly one item, that item starts open: once per filter,
  // so a refetch never reopens what the reader closed.
  useEffect(() => {
    if (items === null || autoOpenedFor.current === runFilter) return;
    autoOpenedFor.current = runFilter;
    const mine = runFilter ? items.filter((i) => i.run_id === runFilter) : [];
    if (mine.length === 1) showOpen(new Set([...openRef.current, mine[0].id]));
  }, [items, runFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = (id: number) => {
    const next = new Set(openRef.current);
    if (!next.delete(id)) next.add(id);
    showOpen(next);
  };

  const decide = async (item: NeedsYouItem, accept: boolean) => {
    if (!accept && !window.confirm(REJECT_CONFIRM)) return;
    patchState(item.id, { phase: 'posting' });
    try {
      await (accept ? acceptReduction(item.id) : rejectReduction(item.id));
    } catch (err) {
      // fetchJSON's errors carry the HTTP status (Task 7).
      if ((err as { status?: number }).status === 409) {
        // Decided elsewhere: the CLI, another tab, a verdict inside Summary.
        announce(`${item.run_id}: decided elsewhere`);
        patchState(item.id, { phase: 'conflict', note: DECIDED_ELSEWHERE });
        void load();
      } else {
        patchState(item.id, {
          error: err instanceof Error ? err.message : 'Failed to record the decision',
        });
      }
      return;
    }
    const next = itemsRef.current.filter((i) => i.id !== item.id);
    planFocus(new Set([item.id]), next, true);
    patchState(item.id, null);
    showItems(next);
    announce(`${accept ? 'Accepted' : 'Rejected'}: ${reductionHeadline(item.json, item.kind)}`);
    onDecided();
    void load();
  };

  const groups = items ? groupByRun(items, runFilter) : [];

  return (
    <div
      style={{
        flex: 1,
        minHeight: 0,
        overflow: 'auto',
        padding: 20,
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
      }}
    >
      <h1
        ref={h1Ref}
        tabIndex={-1}
        style={{ margin: 0, fontSize: 20, color: 'var(--text-primary)' }}
      >
        Needs you
      </h1>
      <span style={MUTED}>
        A decision settles its tickets now; the run moves on when its master is running.
      </span>

      {runFilter && (
        <span
          data-testid="needs-you-run-chip"
          style={{
            alignSelf: 'flex-start',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 4,
            padding: '2px 4px 2px 10px',
            fontSize: 12,
            fontFamily: 'var(--font-mono)',
            color: 'var(--text-primary)',
            background: 'var(--wash-subtle)',
            border: '1px solid var(--border-hairline)',
            borderRadius: 'var(--radius-md)',
          }}
        >
          <span>run {runFilter}</span>
          <button
            type="button"
            aria-label={`Remove run filter ${runFilter}`}
            onClick={() => {
              navigate({ page: 'needs-you', run: null });
              // The chip is about to go: focus the page heading, not <body>.
              focusHeading();
            }}
            style={{
              border: 'none',
              background: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              padding: '0 4px',
            }}
          >
            ×
          </button>
        </span>
      )}

      {error && (
        <div role="alert" style={ALERT}>
          <span>Couldn't load what needs you: {error.message}</span>
          <Button size="sm" onClick={() => void load()}>
            Retry
          </Button>
        </div>
      )}

      {items === null && !error && (
        <div style={{ position: 'relative', minHeight: 160 }}>
          <LoadingOverlay label="Loading decisions…" />
        </div>
      )}

      {items !== null && groups.length === 0 && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', fontSize: 14 }}>
          <span style={{ color: 'var(--text-muted)' }}>
            {runFilter
              ? `Nothing from ${runFilter} is waiting on you.`
              : 'Nothing is waiting on you.'}
          </span>
          {runFilter && (
            <a href={ALL_RUNS} onClick={focusHeading}>
              Show all runs
            </a>
          )}
        </div>
      )}

      {groups.map((group) => {
        const headingId = `needs-you-run-${encodeURIComponent(group.runId)}`;
        const state = runs?.find((r) => r.id === group.runId)?.state;
        return (
          <section
            key={group.runId}
            aria-labelledby={headingId}
            style={{ display: 'flex', flexDirection: 'column', gap: 8 }}
          >
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
              <h2
                id={headingId}
                style={{ margin: 0, fontSize: 15, fontFamily: 'var(--font-mono)' }}
              >
                <a href={runHref(group.runId)} style={{ color: 'var(--text-primary)' }}>
                  {group.runId}
                </a>
              </h2>
              <span style={MUTED}>{group.playbook}</span>
              {state && <span style={MUTED}>{state}</span>}
              {/* The shared clock ticks every 30 s: a decision can arrive stamped after it. */}
              <span style={MUTED}>
                waiting {fmtSeconds(Math.max(0, now - group.items[0].created_at))}
              </span>
            </div>
            <ul
              style={{
                listStyle: 'none',
                margin: 0,
                padding: 0,
                display: 'flex',
                flexDirection: 'column',
                gap: 8,
              }}
            >
              {group.items.map((item) => {
                const isOpen = open.has(item.id);
                const st: ItemState = itemStates[item.id] ?? {};
                const bodyId = `needs-you-item-${item.id}`;
                return (
                  <li
                    key={item.id}
                    ref={(el) => {
                      if (el) rowRefs.current.set(item.id, el);
                      else rowRefs.current.delete(item.id);
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                      <button
                        type="button"
                        ref={(el) => {
                          if (el) toggleRefs.current.set(item.id, el);
                          else toggleRefs.current.delete(item.id);
                        }}
                        aria-expanded={isOpen}
                        aria-controls={bodyId}
                        onClick={() => toggle(item.id)}
                        style={TOGGLE}
                      >
                        {reductionHeadline(item.json, item.kind)}
                      </button>
                      <time
                        dateTime={new Date(item.created_at * 1000).toISOString()}
                        title={fmtTime(item.created_at)}
                        style={MUTED}
                      >
                        {fmtAgo(item.created_at, now)}
                      </time>
                    </div>
                    {st.note && <div style={{ ...MUTED, marginTop: 4 }}>{st.note}</div>}
                    {st.error && (
                      <div role="alert" style={{ ...ALERT, marginTop: 4 }}>
                        {st.error}
                      </div>
                    )}
                    {isOpen && (
                      <div id={bodyId} style={{ marginTop: 8 }}>
                        <ReductionCard
                          reduction={normalizeReduction(item)}
                          actions={
                            <>
                              <Button
                                variant="primary"
                                size="sm"
                                disabled={!!st.phase}
                                onClick={() => void decide(item, true)}
                              >
                                Accept
                              </Button>
                              <Button
                                variant="danger"
                                size="sm"
                                disabled={!!st.phase}
                                onClick={() => void decide(item, false)}
                              >
                                Reject
                              </Button>
                              <a
                                href={runHref(item.run_id)}
                                style={{ marginLeft: 'auto', alignSelf: 'center', fontSize: 13 }}
                              >
                                Open in run
                              </a>
                            </>
                          }
                        />
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
