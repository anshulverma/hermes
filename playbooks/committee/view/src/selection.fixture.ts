/**
 * Selection-era committee payloads, in the shape `view_data` returns (C6).
 *
 * One committee throughout. Maya (owner) proposes the TPM and the data
 * scientist. Ruth (her manager) keeps the TPM, drops the data scientist and
 * adds the owner of the team-owned crews the proposal would federate. Dana
 * (the chair) ratifies those two and adds the staff engineer. So the seated
 * roster names all three selectors as nominators and holds library and
 * derived seats, and `considered` holds a dropped seat plus a stakeholder the
 * chair named without seating.
 *
 * The fixed four and the library seats carry cast.py's names and titles. The
 * derived seat is a worker's invention, as every derived seat is. The fixed
 * rationales stand in for cast.FIXED_RATIONALE: the view renders whatever
 * string arrives, so nothing here pins that wording.
 */
import type { CommitteeData, Considered, Entry, Persona, SelectionStage } from './CommitteeView';
import type { DocumentBlock } from './Diff';

/** role -> [name, title]: cast.py's, except the derived crew_owner and zone_owner. */
const WHO: Record<string, [string, string]> = {
  owner: ['Maya Okonkwo', 'Staff Engineer & proposal owner'],
  senior_director: ['Dana Whitfield', 'Senior Director of Engineering'],
  manager: ['Ruth Delgado', 'Engineering Manager'],
  tpm: ['Sam Iyer', 'Technical Program Manager'],
  pm: ['Elena Vargas', 'Product Manager'],
  tl: ['Marcus Feld', 'Tech Lead'],
  staff_ic: ['Priya Raman', 'Staff Engineer'],
  data_scientist: ['Tobias Lin', 'Data Scientist'],
  crew_owner: ['Noor Haddad', 'Owner, team-owned crews'],
  zone_owner: ['Lena Brandt', 'Owner, eu-west security zone'],
  junior_ic: ['Alex Moreau', 'Software Engineer'],
};

/** Stand-ins for cast.FIXED_RATIONALE. */
const FIXED_WHY: Record<string, string> = {
  owner: 'wrote the proposal and answers for it',
  senior_director: 'chairs the review and rules on it',
  manager: "manages the owner and signs her team's commitments",
  junior_ic: 'applies the edits the owner delegates',
};

/** Each seat's rationale as the chair gave it: stage 3 is authoritative. */
const WHY: Record<string, string> = {
  tpm: 'the deferral needs dates, and someone has to own them',
  data_scientist: 'the triggers are measurements that need checking',
  crew_owner: 'owns the team-owned crews the proposal would federate',
  staff_ic: 'checks the seams the spec claims already exist',
};

const SELECTORS = ['owner', 'manager', 'senior_director'];

function row(
  role: string,
  rationale: string,
  nominated_by: Persona['nominated_by'],
  source: Persona['source'],
): Persona {
  return {
    role,
    name: WHO[role][0],
    title: WHO[role][1],
    state: 'idle',
    stance: null,
    rationale,
    nominated_by,
    // `_roster`: the selector's name for a person's nomination, null for a
    // fixed or a default seat.
    nominated_by_name: nominated_by && SELECTORS.includes(nominated_by) ? WHO[nominated_by][0] : null,
    source,
  };
}

const fixed = (role: string): Persona => row(role, FIXED_WHY[role], 'fixed', 'fixed');

/** `_seats` in "selecting" and "lost": selection.fixed_seats(), and nobody has the floor. */
const FIXED_FOUR: Persona[] = ['owner', 'senior_director', 'manager', 'junior_ic'].map(fixed);

/** `proposed` items are [slug, rationale]. Their name and title come off WHO, as `_selection` carries them. */
function stage(n: number, role: string, body: string, proposed: Array<[string, string]>): SelectionStage {
  return {
    stage: n,
    role,
    name: WHO[role][0],
    delivered: true,
    body,
    proposed: proposed.map(([slug, rationale]) => ({
      role: slug,
      name: WHO[slug][0],
      title: WHO[slug][1],
      rationale,
    })),
    proposed_dropped: 0,
    segments: [{ kind: 'text', text: body }],
    badges: [],
    take: 1,
    takes: 1,
    violations: [],
    flags: [],
  };
}

const PROPOSES = stage(
  1,
  'owner',
  'Sam should sit for the dates and Tobias for the numbers the triggers rest on.',
  [['tpm', WHY.tpm], ['data_scientist', WHY.data_scientist]],
);

const AMENDS = stage(
  2,
  'manager',
  'I keep Sam. The triggers have no numbers yet, so not Tobias. The crews this would federate have an owner, and she is not in the room.',
  [['tpm', WHY.tpm], ['crew_owner', WHY.crew_owner]],
);

const RATIFIES = stage(
  3,
  'senior_director',
  'Ratified: Noor and Sam as Ruth has them, and Priya for the seams the spec says already exist.',
  [['crew_owner', WHY.crew_owner], ['tpm', WHY.tpm], ['staff_ic', WHY.staff_ic]],
);

/** `thread.NO_TURN`, verbatim: the chair's worker failed, so the run fell back. */
const NO_TURN = '_(no turn delivered — the worker failed; see hermes show)_';

const CHAIR_FAILED: SelectionStage = {
  ...stage(3, 'senior_director', NO_TURN, []),
  delivered: false,
  badges: ['no_turn'],
};

/**
 * Before t01, `_document` names the file off the thread header. This run's
 * snapshot is not readable. The pre-t01 layout shows no Document card either
 * way (C6), and a test swaps in a captured one to prove it.
 */
const DOCUMENT: DocumentBlock = {
  name: 'federation-future.md',
  captured: false,
  original: { path: 'doc/00-original.md', bytes: null },
  steps: [],
  final: null,
  dropped_delegation: null,
};

/** Roster order: owner, the reviewers in opening order, junior_ic. */
const SEATED_ROSTER: Persona[] = [
  fixed('owner'),
  fixed('senior_director'),
  fixed('manager'),
  row('crew_owner', WHY.crew_owner, 'manager', 'derived'),
  row('tpm', WHY.tpm, 'owner', 'library'),
  row('staff_ic', WHY.staff_ic, 'senior_director', 'library'),
  fixed('junior_ic'),
];

const CONSIDERED: Considered[] = [
  // A stage-1 seat that the manager's usable list omitted, with no not_seated entry of hers.
  {
    stakeholder: 'Data Scientist',
    role: 'data_scientist',
    reason: 'dropped by Ruth Delgado',
    represented_by: null,
    represented_by_name: null,
  },
  // The chair's own not_seated entry.
  {
    stakeholder: 'Security',
    role: null,
    reason: 'no change to how hosts authenticate',
    represented_by: 'staff_ic',
    represented_by_name: 'Priya Raman',
  },
];

const IDLE = { turn: 0, holder: null, queue: [], ended: null };

/** resolve's caps cut nothing in these runs. */
const UNCUT = { considered_dropped: 0, invalid_dropped: 0 };

/** Mid-selection: the owner's list is in, and the manager is on s2-manager. */
export const selectingData: CommitteeData = {
  kind: 'committee',
  roster: FIXED_FOUR,
  // The provisional cap on the owner's selection reduction: DEFAULT_MAX_TURNS.
  progress: { ...IDLE, cap: 30 },
  timeline: [],
  verdict: null,
  document: DOCUMENT,
  selection: { state: 'selecting', stages: [PROPOSES], fallback: null, considered: [], ...UNCUT },
};

/** The chair has ratified and t01 has not settled. The cap is 2 x 5 reviewers + 16 = 26. */
export const seatedData: CommitteeData = {
  kind: 'committee',
  roster: SEATED_ROSTER,
  progress: { ...IDLE, cap: 26 },
  timeline: [],
  verdict: null,
  document: DOCUMENT,
  selection: {
    state: 'seated',
    stages: [PROPOSES, AMENDS, RATIFIES],
    fallback: null,
    considered: CONSIDERED,
    ...UNCUT,
  },
};

const FALLBACK_WHY = 'default committee (selection fell back: chair_failed)';

/** The chair's worker failed, so today's seven reviewers sit: 2 x 7 + 16 = 30. */
export const fallbackData: CommitteeData = {
  kind: 'committee',
  roster: [
    fixed('owner'),
    fixed('senior_director'),
    fixed('manager'),
    ...['tpm', 'pm', 'tl', 'staff_ic', 'data_scientist'].map((r) =>
      row(r, FALLBACK_WHY, 'default', 'library'),
    ),
    fixed('junior_ic'),
  ],
  progress: { ...IDLE, cap: 30 },
  timeline: [],
  verdict: null,
  document: DOCUMENT,
  selection: {
    state: 'fallback',
    stages: [PROPOSES, AMENDS, CHAIR_FAILED],
    fallback: 'chair_failed',
    // The stage 1-2 seats outside the default committee. tpm and data_scientist are in it.
    considered: [
      {
        stakeholder: 'Owner, team-owned crews',
        role: 'crew_owner',
        reason: 'not in the default committee (fallback: chair_failed)',
        represented_by: null,
        represented_by_name: null,
      },
    ],
    ...UNCUT,
  },
};

/** The master lost the meeting on s2-manager: the stages so far, and the fixed four. */
export const lostData: CommitteeData = {
  ...selectingData,
  selection: { state: 'lost', stages: [PROPOSES], fallback: null, considered: [], ...UNCUT },
};

/** turn · role · prose: the opening round up to the derived seat's first turn. */
const TURNS: Array<[number, string, string]> = [
  [1, 'senior_director', 'Maya, I will go first and keep it short: defer, with a date.'],
  [2, 'owner', 'Dana opened with defer and a date. Here is my turn.'],
  [3, 'manager', 'This lands on hands I have already committed this half.'],
  [4, 'owner', 'Ruth is right about the staffing line. Here is my turn.'],
  [5, 'crew_owner', 'My crews would carry the federated hosts, and nobody has asked them.'],
];

const timeline: Entry[] = TURNS.map(([n, role, body]) => ({
  n,
  role,
  name: WHO[role][0],
  title: WHO[role][1],
  body,
  action: null,
  badges: [],
  verified: null,
  stance: null,
}));

// `_floor`: every turn was delivered, so each speaker spoke, and the last one holds the floor.
const spoke = new Set(TURNS.map(([, role]) => role));

/** Five turns in: the derived crew_owner took t05 and holds the floor. */
export const seatedWithTurnsData: CommitteeData = {
  ...seatedData,
  roster: SEATED_ROSTER.map((p) => ({
    ...p,
    state: p.role === 'crew_owner' ? 'holds_floor' : spoke.has(p.role) ? 'spoke' : 'idle',
  })),
  progress: { turn: 5, cap: 26, holder: 'crew_owner', queue: [], ended: null },
  timeline,
};

// --- the Selection card ------------------------------------------------------

/** What the chair ratified, as [slug, why]: the manager's amended list. */
const CARD_RATIFIED: Array<[string, string]> = [
  ['tpm', 'owns the schedule this would move'],
  ['staff_ic', 'carries the on-call cost of a second crew'],
  ['zone_owner', 'federation crosses her zone boundary'],
];

/**
 * A committee seated before t01, for the Selection card. The owner proposes
 * three seats, the manager swaps the PM for the staff engineer and names who
 * speaks for the PM, and the chair ratifies the manager's list. `zone_owner` is
 * a derived seat, and the roster says so. One stakeholder considered has a
 * representative and one has none, and the represented one's reason ends in a
 * full stop the card must not double.
 */
export const cardData: CommitteeData = {
  ...seatedData,
  roster: [
    fixed('owner'),
    fixed('senior_director'),
    fixed('manager'),
    row('tpm', CARD_RATIFIED[0][1], 'owner', 'library'),
    row('staff_ic', CARD_RATIFIED[1][1], 'manager', 'library'),
    row('zone_owner', CARD_RATIFIED[2][1], 'owner', 'derived'),
    fixed('junior_ic'),
  ],
  selection: {
    state: 'seated',
    fallback: null,
    stages: [
      stage(1, 'owner', 'Federation lands on the program, the roadmap and one security zone.', [
        CARD_RATIFIED[0],
        ['pm', 'owns the roadmap slot it takes'],
        CARD_RATIFIED[2],
      ]),
      stage(2, 'manager', 'Priya carries the on-call cost, so she sits instead of Elena.', CARD_RATIFIED),
      stage(3, 'senior_director', 'Ratified as amended.', CARD_RATIFIED),
    ],
    considered: [
      {
        stakeholder: 'Product Manager',
        role: 'pm',
        reason: "the roadmap slot is Sam's call this half.",
        represented_by: 'tpm',
        represented_by_name: 'Sam Iyer',
      },
      {
        stakeholder: 'Legal',
        role: null,
        reason: 'no contract or licence question in this proposal',
        represented_by: null,
        represented_by_name: null,
      },
    ],
    ...UNCUT,
  },
};
