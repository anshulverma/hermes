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
 * emits now. Three personas state no stance on purpose: absent has to stay
 * absent.
 */
import type { CommitteeData, Entry, Persona } from './CommitteeView';

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
 * The delegated edit named on each owner turn that delegated one, off the same
 * run's `action` keys. Kept as a lookup rather than a sixth column on TURNS:
 * six of twenty rows carry one, and widening every tuple to say `null` fourteen
 * times is diff for nothing.
 */
const ACTIONS: Record<number, string> = {
  2: 'Rewrite §2 "When to reach for it" so each trigger is a measurable threshold with a named declarer.',
  5: 'Rewrite §14.1 — delete the batch-submit claim and restate the remaining seam as the events-since-cursor invariant.',
  8: 'Delete the false "same endpoint the UI uses to inject externally-created tickets" claim from §4\'s Push bullet.',
  11: 'Record the amendments already conceded on the floor, in §2 and §14.1.',
  14: 'Cut the delegation half from the spec — §5, §8, the delegation ledger, capability advertisement.',
  17: 'Record the DESIGN correction in §14.1: drop the batch-submit endpoint from the federation-seam bullet.',
};

const STANCES: Record<string, string> = {
  senior_director: "Drop it — every reason I had for deferring died in this thread.",
  owner: "Defer a smaller document, with the trigger made falsifiable.",
  manager: "Defer; I cannot staff it this half and a solo build is not a plan.",
  pm: "Cut the delegation half and keep aggregation, or drop the whole thing.",
  tl: "The two halves are separable and the delegation half fails its own trigger.",
  staff_ic: "Do not fund: §4 asserts a credential scoping this system does not have.",
};

const STANCE_TURN: Record<string, number> = {
  senior_director: 1, owner: 14, manager: 4, pm: 10, tl: 13, staff_ic: 16,
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
}));

const roster: Persona[] = Object.keys(CAST).map((role) => ({
  role,
  name: CAST[role][0],
  title: CAST[role][1],
  state: 'spoke',
  stance: STANCES[role] ?? null,
}));

export const run2: CommitteeData = {
  kind: 'committee',
  roster,
  progress: { turn: 20, cap: 20, holder: null, queue: [], ended: 'owner closed' },
  timeline,
  stances: Object.fromEntries(
    Object.entries(STANCES).map(([role, text]) => [role, [{ turn: STANCE_TURN[role], text }]]),
  ),
  verdict: {
    text: "I've read the artifact, the revised copy, and all twenty turns.\n\n---\n\n# Decision — Hermes federation layer\n\n**Chair: Dana Whitfield, Senior Director of Engineering**\n**Charge: fund now / defer again / drop**\n\n## Verdict: do not approve. Drop.\n\n`docs/specs/federation-future.md` is retired whole — frame included, not renamed, not re-scoped, not deferred a third time. Nothing is funded. The successor, if one exists, is a new proposal with a new author.\n\nI opened this review with defer, a date and a named owner. I am ruling against my own turn-01 position, and I'll say why in the record rather than let it be inferred.\n\n---\n\n## Why defer no longer survives\n\nMy turn-01 defer rested on three things\n\n…",
    checks: [
      { turn: 3, action: "Rewrite §2 \"When to reach for it\" so each trigger is a measurable threshold with a named declarer, folding the organizat…", verified: true },
      { turn: 6, action: "Rewrite §14.1 — delete the batch-submit claim (it is federation-build cost, not a seam), restate the remaining seam as t…", verified: true },
      { turn: 9, action: "Delete the false \"same endpoint the UI uses to inject externally-created tickets\" claim from §4's Push bullet — state pl…", verified: true },
      { turn: 12, action: "Record the amendments already conceded on the floor — in §2 restore trigger 2's reachability half as a discovered predic…", verified: true },
      { turn: 15, action: "Cut the delegation half from the spec — §5, §8, the delegation ledger, capability advertisement, the shard-submit endpoi…", verified: true },
      { turn: 18, action: "In DESIGN.md's \"Control plane & status\" section (lines 575-579), delete the false claim that a batch-submit endpoint for…", verified: true },
    ],
    artifact_intact: true,
    dropped_delegation: null,
    dropped_floor_requests: [],
    simulation: true,
  },
  artifacts: {
    original: { name: 'federation-future.md', bytes: 11397 },
    revised: { name: 'federation-future.revised.md', bytes: 19100 },
  },
};

/**
 * The same committee eight turns in: the TPM has the floor, two members are
 * queued behind him, three have not spoken, and there is no verdict yet.
 */
export const midRun: CommitteeData = {
  ...run2,
  roster: run2.roster.map((p) => ({
    ...p,
    state:
      p.role === 'tpm'
        ? 'holds_floor'
        : p.role === 'tl' || p.role === 'staff_ic'
          ? 'queued'
          : p.role === 'pm' || p.role === 'data_scientist' || p.role === 'junior_ic'
            ? 'idle'
            : 'spoke',
    stance: p.role === 'tpm' || p.role === 'tl' ? null : p.stance,
  })),
  progress: { turn: 8, cap: 20, holder: 'tpm', queue: ['tl', 'staff_ic'], ended: null },
  timeline: run2.timeline.filter((e) => e.n <= 8),
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
  },
  {
    n: 23,
    role: 'tl',
    name: 'Marcus Feld',
    title: 'Tech Lead',
    body: '_(no turn delivered — the worker produced nothing)_',
    action: null,
    badges: ['no_turn'],
    verified: null,
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
  },
];
