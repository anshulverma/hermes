/**
 * 1:1s in the shape `view_data` returns them (one-on-ones C8), for the
 * committee view's tests. run2.fixture.ts stays the legacy payload: run-2 held
 * no 1:1s, so everything here is layered over it, never written into it.
 *
 * The story is one the playbook can produce. Before the opening round the owner
 * met the TPM (aligned in one round) and the manager met the PM (four
 * exchanges, not aligned). On turn 04 the manager called `align: tl staff_ic`;
 * the owner replied on 05 and delegated, the junior IC applied it on 06 (a
 * delegation outranks a pending 1:1), and only then did the pause run. The
 * manager sat in neither seat, so she hosted it and owed the closing exchange,
 * which never arrived: the members' `aligned` stands, with no outcome recorded.
 */
import type { CommitteeData, OneOnOne, OneOnOneExchange, OneOnOnePerson } from './CommitteeView';
import { midRun, run2 } from './run2.fixture';

/** A seat as view_data names it, off run-2's roster. */
const person = (role: string): OneOnOnePerson => {
  const p = run2.roster.find((r) => r.role === role)!;
  return { role, name: p.name, title: p.title };
};

/** One kept exchange: delivered, one text segment, unless `more` says otherwise. */
const exchange = (
  n: number | null,
  role: string,
  text: string,
  more: Partial<OneOnOneExchange> = {},
): OneOnOneExchange => ({
  exchange: n,
  speaker: role,
  name: person(role).name,
  body: text,
  segments: [{ kind: 'text', text }],
  delivered: true,
  aligned: null,
  closing: false,
  badges: [],
  ...more,
});

const OWNER = person('owner');
const MANAGER = person('manager');

/** Three backticks, built so no line of this file (or of the plan) holds a literal fence. */
const FENCE = '`'.repeat(3);

/** Up-front 1:1 1, hosted by the owner: both said aligned after one round. */
const withTpm: OneOnOne = {
  seq: 1,
  origin: 'upfront',
  called_by: 'owner',
  after_turn: 0,
  host: OWNER,
  members: [person('tpm'), OWNER],
  topic: 'who owns the relay through week 6',
  exchanges: [
    exchange(1, 'tpm', 'I can back week 6 only if the relay has a named owner.', { aligned: true }),
    exchange(2, 'owner', 'I will own the relay myself through week 6.', {
      body: [
        'I will own the relay myself through week 6.',
        '',
        FENCE + 'mermaid',
        'graph LR; relay-->shard',
        FENCE,
        'Figure: the relay',
        'Description: one relay feeding the shard',
      ].join('\n'),
      segments: [
        { kind: 'text', text: 'I will own the relay myself through week 6.' },
        {
          kind: 'mermaid',
          source: 'graph LR; relay-->shard',
          caption: 'the relay',
          description: 'one relay feeding the shard',
        },
      ],
      aligned: true,
    }),
  ],
  ended: 'aligned',
  aligned: true,
  agreed: 'Maya owns the relay through week 6',
  still_open: null,
  delegated_action: null,
};

/** Up-front 1:1 2, hosted by the manager: stopped at the exchange cap, not aligned. */
const withPm: OneOnOne = {
  seq: 2,
  origin: 'upfront',
  called_by: 'owner',
  after_turn: 0,
  host: MANAGER,
  members: [person('pm'), MANAGER],
  topic: 'whether a pilot customer exists',
  exchanges: [
    exchange(1, 'pm', 'I cannot sign off on a pilot nobody has named.', { aligned: false }),
    exchange(2, 'manager', 'Two teams asked; neither has signed.'),
    exchange(3, 'pm', 'Then the pilot is a hope, not a plan.', { aligned: false }),
    exchange(4, 'manager', 'Agreed that it is unsigned; not that it is a hope.'),
  ],
  ended: 'exchange cap',
  aligned: false,
  agreed: null,
  still_open: 'whether the pilot customer signs before Q3',
  delegated_action: null,
};

/**
 * The pause after turn 06, called and hosted by the manager, who is neither
 * member. An undelivered exchange is kept with an empty body (reduce stores
 * "" and only the private file gets NO_TURN), so it has no segments.
 */
const tlAndStaff: OneOnOne = {
  seq: 3,
  origin: 'pause',
  called_by: 'manager',
  after_turn: 6,
  host: MANAGER,
  members: [person('tl'), person('staff_ic')],
  topic: 'whether the shard API ships as v1 or waits for v2',
  exchanges: [
    exchange(1, 'tl', 'v1 ships; v2 is a rename we cannot afford now.', { aligned: true }),
    exchange(2, 'staff_ic', 'Fine by me if v2 is written down as deferred.', { aligned: true }),
    exchange(null, 'manager', '', { closing: true, delivered: false, segments: [], badges: ['no_turn'] }),
  ],
  ended: 'aligned',
  aligned: true,
  agreed: null,
  still_open: null,
  delegated_action: null,
};

/** midRun (seven turns) with all three 1:1s behind it: 9 of 16 exchanges spent. */
export const oneOnOneRun: CommitteeData = {
  ...midRun,
  progress: { ...midRun.progress, paused: null, one_on_one: { used: 9, budget: 16 } },
  one_on_ones: [withTpm, withPm, tlAndStaff],
};

/** `_floor` at turn 06 plus the two members of the running 1:1 (the host waits outside). */
const PAUSED_STATE: Record<string, string> = {
  senior_director: 'spoke',
  owner: 'spoke',
  junior_ic: 'spoke',
  manager: 'queued',
  tl: 'in_one_on_one',
  staff_ic: 'in_one_on_one',
};

/** The same run during the pause: the TL has spoken, exchange 2 (the staff IC) is running. */
export const pausedRun: CommitteeData = {
  ...midRun,
  // The TPM first speaks on turn 07, so at turn 06 he has no stance yet.
  roster: midRun.roster.map((p) => ({
    ...p,
    state: PAUSED_STATE[p.role] ?? 'idle',
    stance: p.role === 'tpm' ? null : p.stance,
  })),
  progress: {
    ...midRun.progress,
    turn: 6,
    holder: null,
    paused: {
      pairs: [{ seq: 3, host: MANAGER, members: [person('tl'), person('staff_ic')] }],
      current: { seq: 3, exchange: 2 },
    },
    one_on_one: { used: 7, budget: 16 },
  },
  timeline: midRun.timeline.filter((e) => e.n <= 6),
  one_on_ones: [
    withTpm,
    withPm,
    { ...tlAndStaff, exchanges: tlAndStaff.exchanges.slice(0, 1), ended: null, aligned: null },
  ],
};

/**
 * Before t01: selection has seated the committee, up-front 1:1 1 is finished
 * and 1:1 2 is scheduled but has kept no exchange yet (the '1:1s next' lag).
 */
export const upfrontRun: CommitteeData = {
  ...run2,
  roster: run2.roster.map((p) => ({ ...p, state: 'idle', stance: null })),
  progress: {
    turn: 0,
    cap: 30,
    holder: null,
    queue: [],
    ended: null,
    paused: { pairs: [{ seq: 2, host: MANAGER, members: [person('pm'), MANAGER] }], current: null },
    one_on_one: { used: 2, budget: 16 },
  },
  timeline: [],
  verdict: null,
  document: { name: null, captured: false, original: null, steps: [], final: null, dropped_delegation: null },
  selection: { state: 'seated', stages: [], fallback: null, considered: [] },
  one_on_ones: [withTpm],
};

// --- the Metrics '1:1s' line, and an edit that came out of a 1:1 -------------

/** Up-front 1:1 1: the staff IC and the owner aligned in one round. */
const settledUpfront: OneOnOne = {
  seq: 1,
  origin: 'upfront',
  called_by: 'owner',
  after_turn: 0,
  host: OWNER,
  members: [person('staff_ic'), OWNER],
  topic: 'cost of the first phase',
  exchanges: [
    exchange(1, 'staff_ic', 'I can live with it if the first phase is capped at one quarter.', { aligned: true }),
    exchange(2, 'owner', 'One quarter, and the proposal will say so.', { aligned: true }),
  ],
  ended: 'aligned',
  aligned: true,
  agreed: 'The first phase is capped at one quarter.',
  still_open: null,
  delegated_action: null,
};

/** The pause the manager called at t04: four exchanges, and the pm never came round. */
const stalledPause: OneOnOne = {
  seq: 2,
  origin: 'pause',
  called_by: 'manager',
  after_turn: 6,
  host: MANAGER,
  members: [person('pm'), MANAGER],
  topic: 'scope of the first launch',
  exchanges: [
    exchange(1, 'pm', 'The first launch needs the batch path or nobody adopts it.', { aligned: false }),
    exchange(2, 'manager', 'Batch doubles the work. Can the first launch ship without it?'),
    exchange(3, 'pm', 'Not for the two teams that asked for this.', { aligned: false }),
    exchange(4, 'manager', 'Then it goes back to the room as open.'),
  ],
  ended: 'exchange cap',
  aligned: false,
  agreed: null,
  still_open: 'Whether the first launch includes the batch path.',
  delegated_action: null,
};

/** A pause the owner called at t02: she and the TPM aligned, and her delegation became t03. */
const aligningPause: OneOnOne = {
  seq: 2,
  origin: 'pause',
  called_by: 'owner',
  after_turn: 2,
  host: OWNER,
  members: [person('tpm'), OWNER],
  topic: 'when to reach for federation',
  exchanges: [
    exchange(1, 'tpm', 'Nobody can plan against a trigger nobody can measure.', { aligned: true }),
    exchange(2, 'owner', 'Agreed. Each trigger in §2 becomes a threshold read off hermes status.', { aligned: true }),
  ],
  ended: 'aligned',
  aligned: true,
  agreed: 'The §2 triggers become measurable thresholds with a named declarer.',
  still_open: null,
  delegated_action:
    'Rewrite §2 "When to reach for it" so each trigger is a measurable threshold with a named declarer',
};

/** midRun with both 1:1s behind it: 2 finished, 1 aligned, 6 of 16 exchanges spent. */
export const metricsOneOnOnes: CommitteeData = {
  ...midRun,
  progress: { ...midRun.progress, one_on_one: { used: 6, budget: 16 } },
  one_on_ones: [settledUpfront, stalledPause],
};

/** Before t01: no turn yet, and up-front 1:1 1 has kept its first exchange. */
export const metricsBeforeT01: CommitteeData = {
  ...run2,
  roster: run2.roster.map((p) => ({ ...p, state: 'idle', stance: null })),
  progress: {
    turn: 0, cap: 30, holder: null, queue: [], ended: null, one_on_one: { used: 1, budget: 16 },
  },
  timeline: [],
  verdict: null,
  document: {
    name: null, captured: false, original: null, steps: [], final: null, dropped_delegation: null,
  },
  one_on_ones: [
    {
      ...settledUpfront,
      exchanges: settledUpfront.exchanges.slice(0, 1),
      ended: null,
      aligned: null,
      agreed: null,
    },
  ],
};

/**
 * midRun, except that the owner's t02 reply delegated nothing and her 1:1 with
 * the TPM did. t03 applied that edit (step 1, attributed to 1:1 2), and t06
 * applied her t05 meeting delegation (step 2), so the two kinds of step sit
 * side by side in one stepper.
 */
export const editFromOneOnOne: CommitteeData = {
  ...midRun,
  timeline: midRun.timeline.map((e) =>
    e.n === 2 ? { ...e, action: null, badges: e.badges.filter((b) => b !== 'delegate') } : e,
  ),
  progress: { ...midRun.progress, one_on_one: { used: 4, budget: 16 } },
  one_on_ones: [settledUpfront, aligningPause],
  document: {
    name: 'federation-future.md',
    captured: true,
    original: { path: 'doc/00-original.md', bytes: 30 },
    steps: [
      { turn: 3, path: 'doc/t03.md', bytes: 31, delivered: true, verified: true,
        owner_turn: null, reviewer_turn: null, provenance: 'recorded', origin_one_on_one: 2 },
      { turn: 6, path: 'doc/t06.md', bytes: 45, delivered: true, verified: true,
        owner_turn: 5, reviewer_turn: 4, provenance: 'recorded', origin_one_on_one: null },
    ],
    final: { path: 'doc/t06.md', turn: 6, bytes: 45, ruling: 'in_session' },
    dropped_delegation: null,
  },
};
