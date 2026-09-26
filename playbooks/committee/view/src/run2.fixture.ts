/**
 * run-2 — the first live committee run, in the shape `view_data` returns.
 *
 * The personas, the turn numbers, the six delegations and all six re-check
 * outcomes are that run's, captured from its reductions. Each turn's prose is
 * its real opening, cut short so the fixture stays readable in a diff; turn 16
 * keeps enough length to be worth collapsing.
 *
 * `progress.ended` is `owner closed`: turn 20 carries `close: true`, and
 * `_decision` prefers a close over the cap even on the turn the cap would have
 * stopped anyway. `turn cap` is rendered from a synthetic override in the test,
 * because run-2 never produced it.
 *
 * `stance` postdates that run, so those are written to the shape the playbook
 * emits now — but the TEXTS are the positions those personas actually took, off
 * `fixtures/thread.md`, at the turns they took them. A fixture that inverts what
 * the transcript says is the same defect class as the view it is testing.
 * `junior_ic` is the one seat that filed nothing: absent has to stay absent, and
 * he is the only honest place to prove it.
 */
import type { CommitteeData, Entry, Persona } from './CommitteeView';
import type { DocumentBlock } from './Diff';

/** role → [name, title], from `playbooks/committee/cast.py`. */
const CAST: Record<string, [string, string]> = {
  owner: ["Maya Okonkwo", "Staff Engineer & proposal owner"],
  senior_director: ["Dana Whitfield", "Senior Director of Engineering"],
  manager: ["Ruth Delgado", "Engineering Manager"],
  tpm: ["Sam Iyer", "Technical Program Manager"],
  pm: ["Elena Vargas", "Product Manager"],
  tl: ["Marcus Feld", "Tech Lead"],
  staff_ic: ["Priya Raman", "Staff Engineer"],
  data_scientist: ["Tobias Lin", "Data Scientist"],
  junior_ic: ["Alex Moreau", "Software Engineer"],
};

/** turn · role · badges · re-check outcome · prose */
const TURNS: Array<[number, string, string[], boolean | null, string]> = [
  [1, "senior_director", [], null,
   "Maya — I'll go early and short. I'd rather the room react to a position than to a hedge."],
  [2, "owner", ["delegate"], null,
   "I've read both. Dana Whitfield opened with \"defer, with a date and a named owner,\" three objections, and two questions aimed straight at me. Here is my turn."],
  [3, "junior_ic", [], true,
   "Rewrote §2 into two triggers — each now a numeric threshold read off `hermes status` with a named declarer (root on-call; zone/credential owner) — folding the credential-domain case into the geography trigger and deleting the orga…"],
  [4, "manager", [], null,
   "Maya — I'm with Dana on defer, but not for Dana's reason. I don't think the cost estimate is the interesting disagreement. Mine is narrower: this work lands on a pair of hands I've already committed, and nobody in this thread has…"],
  [5, "owner", ["delegate"], null,
   "I read the artifact, the thread, and — because Ruth's first question is checkable — the two documents it's a question about."],
  [6, "junior_ic", [], true,
   "Rewrote §14.1: dropped batch-submit from the seam list (restated as federation build cost, with the reason it prevents no rewrite), made the remaining seam the `events since(cursor)` invariant — monotonic cursor, no pruning within…"],
  [7, "tpm", [], null,
   "I've read the artifact and all six turns. Here's my turn."],
  [8, "owner", ["delegate"], null,
   "I've read the artifact and all seven turns. Sam's last turn is mostly plan mechanics, but one link in his chain is wrong in a way that changes his risk register. Here is my turn."],
  [9, "junior_ic", [], true,
   "Replaced §4's Push bullet claim: the shard-submit endpoint is now stated as not existing and not in sub-project-3 scope — a thin endpoint over the existing seeding callable, counted as federation build cost — with the false \"same…"],
  [10, "pm", [], null,
   "I've read the artifact and all nine turns. Here's my turn."],
  [11, "owner", ["delegate"], null,
   "I've read the artifact and all ten turns. Elena's floor is the first one that attacks the shape of the proposal rather than its price, and her two questions are the ones that decide it. Here is my turn."],
  [12, "junior_ic", [], true,
   "Recorded the four backlogged concessions: §2's trigger-2 reachability half is now a discovered boolean predicate (no host count, no baseline, no declarer — observed by whoever's bootstrap is refused) with the §2 preamble and decla…"],
  [13, "tl", [], null,
   "I've read the spec and all twelve turns. Maya routed the separability question to me and said she'd hold the cut until I answered it, so I'll lead with that and then say where I think the whole thing sits."],
  [14, "owner", ["delegate"], null,
   "I've read the spec and all thirteen turns. Marcus answered the separability question I routed to him, and it changes what I have to do this turn rather than what I have to argue. Here is my turn."],
  [15, "junior_ic", [], true,
   "Cut the delegation half: §5 and §8 are now removal records (numbers kept so the thread's references still land), §4's push bullet and SSH provisioning of deputies are gone (replaced by \"deputies register, they are not installed\",…"],
  [16, "staff_ic", [], null,
   "I've read the spec, all fifteen turns, and — because three of the load-bearing claims in this thread are checkable against the repository — the repository.\n\n---\n\n**Priya Raman — Staff Engineer**\n\nMaya — your question to me first, because it's short and the answer conditions everything else I'm going to say.\n\n**Yes, we've drifted.** But the drift isn't the damage, and \"should the committee decide reader-versus-mirror\" is the wrong frame for it. Separate two things: a *fact that prices the option* is in this committee's charge; a *choice that implements it* is not. Reader-versus-mirror is a choice — leave it. What actually happened is that a factual premise rode in attached to that choice, went unchallenged because it was bundled with an architecture argument nobody wanted to relitigate, and has now been endorsed by the owner as \"the strongest single thing anyone has said about cost.\"\n\nThat premise is wrong. I'll show you.\n\n**1. The artifact has not changed.**\n\nBefore the substance, the mechanism, because it bears directly on defer-versus-drop.\n\n…"],
  [17, "owner", ["delegate"], null,
   "I read the artifact, the full thread, and — because Priya said three minutes and named line numbers — the repository. Here is my turn."],
  [18, "junior_ic", [], true,
   "Recorded the DESIGN correction in §14.1: the forward-looking flag is replaced by the correction itself — DESIGN's \"Control plane & status\" federation-seam bullet drops the batch-submit endpoint and the \"both already needed by the…"],
  [19, "data_scientist", [], null,
   "Maya — you asked me two questions and both are about whether a number can carry the weight being put on it. I'll answer them, then give you the one correction I think is worth more than my vote, then vote."],
  [20, "owner", ["close"], null,
   "I read the artifact, the full thread, and — because turn 17 set a test on the mechanism and Tobias's live item is checkable — the repository again."],
];

/**
 * The six re-checks off the real decision reduction, truncation and all.
 *
 * The junior IC re-checks on turn N+1 the edit the owner delegated on turn N,
 * so one list is both the verdict card's `checks` and the timeline's `action`
 * keys. They used to be paraphrases sitting beside these exact texts, which had
 * the two halves of one fixture disagreeing about what was delegated.
 */
const CHECKS: Array<{ turn: number; action: string; verified: boolean }> = [
  { turn: 3, action: "Rewrite §2 \"When to reach for it\" so each trigger is a measurable threshold with a named declarer, folding the organizat…", verified: true },
  { turn: 6, action: "Rewrite §14.1 — delete the batch-submit claim (it is federation-build cost, not a seam), restate the remaining seam as t…", verified: true },
  { turn: 9, action: "Delete the false \"same endpoint the UI uses to inject externally-created tickets\" claim from §4's Push bullet — state pl…", verified: true },
  { turn: 12, action: "Record the amendments already conceded on the floor — in §2 restore trigger 2's reachability half as a discovered predic…", verified: true },
  { turn: 15, action: "Cut the delegation half from the spec — §5, §8, the delegation ledger, capability advertisement, the shard-submit endpoi…", verified: true },
  { turn: 18, action: "In DESIGN.md's \"Control plane & status\" section (lines 575-579), delete the false claim that a batch-submit endpoint for…", verified: true },
];

/** turn that delegated it → the edit, keyed off the turn that re-checked it. */
const ACTIONS: Record<number, string> = Object.fromEntries(
  CHECKS.map((c) => [c.turn - 1, c.action]),
);

/**
 * Every position anyone took, in turn order, quoted from `fixtures/thread.md`.
 *
 * A list and not one string per seat, because `_roster` renders the LAST stance
 * as the current one and the owner moved: defer at turn 02, drop from turn 14
 * on. Collapsing her to one line is how the fixture came to say she wanted to
 * defer a document she spent six turns arguing to drop.
 */
const STANCES: Record<string, Array<{ turn: number; text: string }>> = {
  senior_director: [
    { turn: 1, text: "Position: defer. But put a date and a named owner on the deferral this time. Not fund, not drop." },
  ],
  owner: [
    { turn: 2, text: "My position is defer — but defer a smaller document than the one in front of you, with the trigger made falsifiable." },
    { turn: 14, text: "Position: drop, and you're right that the rename was the weakest version of your point." },
    { turn: 17, text: "Position unchanged: drop. Your two additions go in the record." },
    { turn: 20, text: "Position: drop the artifact. docs/specs/federation-future.md is retired whole — frame included, not renamed." },
  ],
  manager: [
    { turn: 4, text: "I'm with Dana on defer, but not for Dana's reason: this work lands on a pair of hands I've already committed, and nobody in this thread has said whose." },
  ],
  tpm: [
    { turn: 7, text: "My position is defer, same as Dana and Ruth, with one amendment: the deferral needs an expiry date, not just an expiry condition." },
  ],
  pm: [
    { turn: 10, text: "My vote: defer. My amendment is about what is being deferred: defer the roll-up, and treat delegation as a separate, later, separately-justified proposal." },
  ],
  tl: [
    { turn: 13, text: "My position: drop this artifact. Not defer it smaller — let aggregation re-enter as a read-layer item sized against sub-project 3." },
  ],
  staff_ic: [
    { turn: 16, text: "Position: drop. And what I'd have the chair write down." },
  ],
  data_scientist: [
    { turn: 19, text: "My position is drop, and my reasons are measurement reasons that don't overlap much with Marcus's or Priya's." },
  ],
};

/** What `_roster` shows: the last position filed by `upTo`, or none. */
const stanceAt = (role: string, upTo: number): string | null => {
  const said = (STANCES[role] ?? []).filter((s) => s.turn <= upTo);
  return said.length > 0 ? said[said.length - 1].text : null;
};

const timeline: Entry[] = TURNS.map(([n, role, badges, verified, body]) => ({
  n,
  role,
  name: CAST[role][0],
  title: CAST[role][1],
  body,
  action: ACTIONS[n] ?? null,
  badges,
  verified,
  stance: STANCES[role]?.find((s) => s.turn === n)?.text ?? null,
}));

/**
 * What `view_data` returns for run-2 today. It predates doc/ snapshots and was
 * never backfilled, so no size is known and `captured` is false; its steps are
 * placed by turn order (reviewer N-2, owner N-1), as `_provenance` does for
 * reductions without the recorded keys.
 */
const runDocument: DocumentBlock = {
  name: 'federation-future.md',
  captured: false,
  original: { path: 'doc/00-original.md', bytes: null },
  steps: CHECKS.map((c) => ({
    turn: c.turn,
    path: `doc/t${String(c.turn).padStart(2, '0')}.md`,
    bytes: null,
    delivered: true,
    verified: c.verified,
    owner_turn: c.turn - 1,
    reviewer_turn: c.turn - 2,
    provenance: 'inferred' as const,
  })),
  final: { path: 'doc/t18.md', turn: 18, bytes: null, ruling: 'awaiting_ruling' },
  dropped_delegation: null,
};

const roster: Persona[] = Object.keys(CAST).map((role) => ({
  role,
  name: CAST[role][0],
  title: CAST[role][1],
  state: 'spoke',
  stance: stanceAt(role, 20),
}));

/** run-2's decision text, trimmed. */
const VERDICT_TEXT =
  "I've read the artifact, the revised copy, and all twenty turns.\n\n---\n\n# Decision — Hermes federation layer\n\n**Chair: Dana Whitfield, Senior Director of Engineering**\n**Charge: fund now / defer again / drop**\n\n## Verdict: do not approve. Drop.\n\n`docs/specs/federation-future.md` is retired whole — frame included, not renamed, not re-scoped, not deferred a third time. Nothing is funded. The successor, if one exists, is a new proposal with a new author.\n\nI opened this review with defer, a date and a named owner. I am ruling against my own turn-01 position, and I'll say why in the record rather than let it be inferred.\n\n---\n\n## Why defer no longer survives\n\nMy turn-01 defer rested on three things\n\n…";

export const run2: CommitteeData = {
  kind: 'committee',
  roster,
  progress: { turn: 20, cap: 20, holder: null, queue: [], ended: 'owner closed' },
  timeline,
  verdict: {
    text: VERDICT_TEXT,
    // What `view._verdict` sends beside it; the card renders the ruling from this.
    segments: [{ kind: 'text', text: VERDICT_TEXT }],
    checks: CHECKS,
    artifact_intact: true,
    dropped_delegation: null,
    dropped_floor_requests: [],
  },
  document: runDocument,
};

/**
 * The same committee seven turns in, in a shape `view_data` can actually emit.
 *
 * Every field is derived from the truncated timeline the way `_floor` derives
 * it, because the previous version was three impossibilities at once: it marked
 * `junior_ic` idle above his own turns 3 and 6, gave the floor to `tpm` when
 * the most recent speaker was the owner, and queued two seats no `request_floor`
 * had earned. Truncating at 07 makes the TPM the last speaker honestly, and the
 * manager's floor request on turn 04 is midRun's own — run-2 has none, so the
 * badge is added here rather than to the shared TURNS table.
 */
const MID_TURN = 7;

const midTimeline: Entry[] = run2.timeline
  .filter((e) => e.n <= MID_TURN)
  .map((e) => (e.n === 4 ? { ...e, badges: [...e.badges, 'request_floor'] } : e));

// `_floor`: spoken comes off the delivered turns themselves, the queue off
// `request_floor` minus whoever has since been granted it, the holder is the
// most recent speaker. The owner and the junior IC never queue.
const midSpoke = new Set(midTimeline.map((e) => e.role));

export const midRun: CommitteeData = {
  ...run2,
  roster: run2.roster.map((p) => ({
    ...p,
    state:
      p.role === 'tpm'
        ? 'holds_floor'
        : p.role === 'manager'
          ? 'queued'
          : midSpoke.has(p.role)
            ? 'spoke'
            : 'idle',
    stance: stanceAt(p.role, MID_TURN),
  })),
  progress: { turn: MID_TURN, cap: 20, holder: 'tpm', queue: ['manager'], ended: null },
  timeline: midTimeline,
  verdict: null,
};

/**
 * The four turn shapes run-2 never produced: a reviewer asking for the floor, a
 * turn that carried only its signal block, a turn whose worker never answered,
 * and a delegated edit whose re-check says it did not land.
 */
export const edgeTurns: Entry[] = [
  {
    n: 21,
    role: 'data_scientist',
    name: 'Tobias Lin',
    title: 'Data Scientist',
    body: 'I want the floor once Priya is done.',
    action: null,
    badges: ['request_floor'],
    verified: null,
    stance: null,
  },
  {
    n: 22,
    role: 'pm',
    name: 'Elena Vargas',
    title: 'Product Manager',
    body: '_(the speaker sent signals only, no prose)_',
    action: null,
    badges: ['signals_only'],
    verified: null,
    stance: null,
  },
  {
    n: 23,
    role: 'tl',
    name: 'Marcus Feld',
    title: 'Tech Lead',
    // `playbooks/committee/thread.py:NO_TURN`, verbatim. The invented string it
    // replaced is one no run can produce.
    body: '_(no turn delivered — the worker failed; see hermes show)_',
    action: null,
    badges: ['no_turn'],
    verified: null,
    stance: null,
  },
  {
    n: 24,
    role: 'junior_ic',
    name: 'Alex Moreau',
    title: 'Software Engineer',
    body: 'I could not find the section the owner named, so I changed nothing.',
    action: null,
    badges: [],
    verified: false,
    stance: null,
  },
];
