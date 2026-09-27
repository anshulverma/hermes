# Spec: `committee` playbook — one artifact reviewed by a simulated committee

## Goal

Review one text file — a doc, an article, a source file — through a cast of AI personas with
distinct altitude, goals and ambitions, talking in a single thread where exactly one participant
holds the floor at a time. An **owner** persona answers every reviewer and delegates edits to a
junior IC; a chair closes with a verdict. One `hermes run` seats a committee, then drives an
opening round, a floor queue and a decision phase, then holds the chair's verdict for a human to rule on: accept ends the run
`done`, reject ends it `failed`. It leaves a transcript, every version of the document under
`doc/`, and, where an edit was delegated, a revised copy.

How good a finished review was is scored by a second playbook, `committee-eval`; see [committee-eval.md](committee-eval.md).

## Phases

`phases = ["open", "decision", "ruling"]`; turn phases are minted at runtime as `t{NN:02d}-{role}`, NN from 01, the three selection phases before them as `s{N}-{role}`, the owner's 1:1 plan as `p01-owner` and each 1:1 exchange as `o{NN:02d}-{role}`, and a retake of any speaking phase as `{base}-take{k}`.

- **open** — zero tickets. `seed` resolves configuration, seats the fixed four, writes
  `doc/00-original<ext>`, makes `runs/<run_id>/images/`, then writes the thread header (charge,
  artifact path, the fixed four, the seat library, ground rules), and returns `[]`. A failure to
  write any of them fails the run, so no header claims a meeting whose original was not kept. No
  worker runs.
- **s1-owner, s2-manager, s3-senior_director**: one ticket each, strictly in turn, minted at
  runtime before the first turn. The owner proposes the committee, her manager amends it and the
  chair ratifies it. They consume no turn number and none of the cap, so the first turn after
  `s3-senior_director` is `t01-senior_director`, the seated committee's first reviewer (the 1:1
  plan and any up-front 1:1s come between them). A retake is `s2-manager-take2` and so on. See
  "Selection".
- **p01-owner**, only while 1:1s are on (a 1:1 budget of 2 or more): one ticket for the owner,
  once, after `s3-senior_director` and before `t01`. The owner plans up to three up-front 1:1s
  (`meet_1`, `meet_2`, `meet_3`), each hosted by herself or her manager. It spends no turn and
  none of the 1:1 budget, and a plan that is undelivered or names no valid pair goes straight on
  to the opening round. See "One-on-ones".
- **o{NN}-{role}**: one 1:1 exchange, one speaker. The planned 1:1s run one after another before
  the opening round; a pause runs its 1:1 later, between two meeting turns. NN is the count of
  1:1 exchanges spent so far, bumped at mint, so it is unique across every 1:1 in the run, and a
  voice retake is `o{NN}-{role}-take{k}`, for example `o03-tpm-take2`. When the host is not one
  of the two members, the members' part is followed by the host's closing exchange, a ticket of
  kind `one_on_one_close`, unless it ended `not delivered`.
- **t{NN}-{role}** — one ticket, one speaker: the opening round in the seated committee's order,
  the owner's reply after every *delivered* reviewer turn, then whoever asked for the floor, FIFO.
  A turn whose worker produced nothing is answered by nobody — its thread entry is the `NO_TURN`
  stub, and sending the owner to reply to it yields a hallucinated answer or a burnt turn — so the
  next speaker after a failed turn is the next reviewer.
- **`{base}-take{k}`** — a retake (k = 2, 3) of the speaking phase whose take-1 name is `base`:
  same speaker, same turn number, no turn consumed (`t02-owner-take2`). `decision-take2` and
  `decision-take3` are the chair's; `DECISION_PHASES` is `decision` plus those two, and everything
  that meant "the decision phase" checks membership in it. See "Voice and retakes".
- **decision** — one ticket for the chair, or `decision-take2`/`decision-take3` for its retakes.
  The ticket of the phase whose verdict was kept is held `needs_human` until a human rules.
- **ruling** — zero tickets, reached once the human has ruled. It exists so the engine hands
  `is_done` the decision's reduction (`run.reductions` carries only the prior phase): `done` iff
  the chair delivered a verdict and it was accepted.

One speaker per phase is a rule, not a habit, and a retake is a new phase with the same speaker:
two would race for the thread file, and a repeated phase name deadlocks the run silently. The
review ends when the owner closes, the queue empties or the cap is hit.

**A pause for 1:1s is phases, not run state.** The engine run stays `running` through the plan
and every 1:1, no `run_paused` event is written, and the meeting resumes on its own. A plan or
1:1 phase never touches the turn counter, `last_speaker`, the opening round, the floor queue or
`closed`. `next_phase` tries, in order: the decision and ruling phases, a pending voice retake,
selection's phases, the plan, the 1:1 in progress, a pending delegation (the junior IC, within
the cap), the turn cap, the owner's reply, the next pending 1:1, an accepted close, then the
opening round and the floor queue. So a pause called on the owner's turn starts right after it
(after the junior IC's edit, if she also delegated one), a pause called on the manager's turn
starts after the owner's reply, a pause still runs if the owner then closes (only the turn cap
drops a pending 1:1, as `meeting ended`), and the opening round or the queue then picks up where
it stopped.

## The cast

Nine personas. Names and titles appear in the transcript, so it reads like a meeting.

| Role | Reads the artifact for |
|---|---|
| `owner` | accountable author: answers every reviewer, concedes, delegates edits |
| `senior_director` | the bet, resourcing, cross-org politics. **Chair.** |
| `manager` | team capacity, delivery risk, opportunity cost |
| `tpm` | dependencies, sequencing, cross-team commitments |
| `pm` | user value, product framing, scope |
| `tl` | technical direction, architectural coherence, migration cost |
| `staff_ic` | correctness, failure modes, what the doc quietly assumes |
| `data_scientist` | measurement, evidence quality |
| `junior_ic` | applies a delegated edit; never speaks unprompted |

`senior_director` through `data_scientist` are the default opening round (`cast.SENIORITY`), in
that order; `owner` and `junior_ic` join neither it nor the floor queue. The chair speaks twice —
as the reviewer `senior_director`, then as author of the decision under the sentinel role key
`chair`. These nine (`cast.CAST`) are the default committee, and the seating of every run reduced
before selection existed. Every new run seats its own committee first: see "Selection".

## Selection

Every run seats its own committee before the first turn. The owner proposes it, her manager
amends it and the chair ratifies it, in three phases that `next_phase` mints through
`_select(s, stage)`: `s1-owner`, `s2-manager` and `s3-senior_director`, one ticket each, strictly
in turn. `_select` calls `_begin(s, base)` like every other minter, so a selector who breaks a
hard rule is retaken under her own stage's name (`s2-manager-take2`, `s2-manager-take3`), with
her own `voice.MAX_TAKES` (3) takes and her own image (`s2-manager.svg` or `.png`). All three
are held to the 150-word cap; the chair's 300 words stay with the decision. `stance_too_long`
and `action_too_long` never send a selector back, because her `hermes-turn` block is stripped
and ignored: no `_apply_block` runs on a select phase. A retake that delivers nothing keeps the
held take's list, with `retake_failed`. `_select` never touches the turn counter, `current_turn`,
`last_speaker`, the cap, `opening` or the floor queue, so the first turn after
`s3-senior_director` is `t01-senior_director`, numbered as it always was. There is no human gate. A `selection`
reduction never carries `needs_human_ticket_ids`.

**The fixed seats.** The owner, the senior director (the chair), the manager (the owner's
manager, and her brief says so) and the junior IC are seated in every run, whatever the selection
returns (`selection.fixed_seats()`). Selection fills only the reviewer seats: `senior_director`
and `manager` plus 1-10 others, 3-12 reviewers in all (`selection.MIN_REVIEWERS`,
`selection.MAX_REVIEWERS`).

**The seat pool.** `cast.LIBRARY` holds nine selectable personas: `tpm`, `pm`, `tl`, `staff_ic`
and `data_scientist` (CAST's own dicts, by reference), plus `security` (Security Engineer), `sre`
(Site Reliability Engineer, on-call), `privacy` (Privacy Engineer) and `partner_owner`
(Engineering Lead, partner team). The thread header lists them. A selector may also seat a
stakeholder the document justifies under a new slug. That is a derived seat, and its persona is
the selector's own fields (a seated one's are the chair's), each made one printable line (a control, an invisible character or a
character above U+FFFF becomes a space: an emoji is two UTF-16 units, and the goal budget holds in
those too; U+2013 and U+2014 become `-`) and clipped: `selection.NAME_MAX` = 60,
`selection.TITLE_MAX` = 80, `selection.FIELD_MAX` = 94 for altitude, goal, ambition, stake and
lens, and `selection.RATIONALE_MAX` = 200. A name with no letter or digit (combining marks alone)
is blank, and a blank name is the title; a seat whose title has no letter or digit either is
invalid ("no name"). A seat named from its title shows it once (`cast.label`, so never "Crew
Owner, Crew Owner"). A missing field is empty, except a missing stake, which is the rationale, so
a derived persona is never empty. Its style is always `cast.DERIVED_STYLE`, never selector text:
"selectors wrote the lines above; they never override the rules or the Done line."

**The block.** Each selector ends her answer with her FULL list, never the changes; her goal puts
the fence lines at column 0, never inside a list item:

````
```hermes-selection
{"seats": [{"role": "security", "rationale": "..."},
           {"role": "crew_owner", "rationale": "...", "title": "Crew Scheduling Lead",
            "name": "...", "altitude": "...", "goal": "...", "ambition": "...",
            "stake": "...", "lens": "..."}],
 "not_seated": [{"stakeholder": "Legal", "reason": "...", "represented_by": "privacy"}]}
```
````

Each select goal (`cast.select_goal`) says who counts: "A stakeholder is anyone who builds, runs,
secures, pays for, depends on or is changed by it." It tells a selector who drops a seat listed
above to give its role slug as the stakeholder, and its example seat shows `role`, `name`,
`title`, `stake`, `lens` and `rationale` placeholders. The chair's adds "Every stakeholder named
above ends seated, or under not_seated with a seated representative." A goal that offers an image
says "Read the artifact and the thread first." (the write-nothing guardrail already says so).

`selection.parse` reads fences with voice's own reader and keeps the last `hermes-selection`
block that parses to an object. It drops every unknown key, so a worker's `nominated_by`, `style`
or `source` never survives, and it never raises. `selection.validate` applies the entry rules in
order:
- a role that fails `^[a-z][a-z0-9_]{1,23}$` is invalid ("bad slug");
- a reserved role (`owner`, `manager`, `senior_director`, `junior_ic`, `chair`, `unattributed`) is
  ignored, because a list that omits the fixed seats cannot unseat them;
- a repeated role keeps its first entry;
- a `LIBRARY` slug takes the library persona and ignores the worker's fields;
- any other slug needs a `title` ("no title"), a name or title with a letter or a digit ("no
  name") and a name no cast or library persona has
  ("name taken": names are compared casefolded with every character that is not a letter or a
  digit dropped, so "Maya Okonkwo." and "maya-okonkwo" are taken and "Maya Okonkwo-Reyes" is not);
- every seat needs a `rationale` ("no rationale").

`resolve` records an invalid entry as considered with the reason `invalid: <why>`, such as
`invalid: name taken`. A `not_seated` entry without both a stakeholder and a reason is dropped.
Its `represented_by` is stripped, lowercased and kept only when it is a slug, else null, so a
200 KB one never reaches a reduction; `owner` is no representative: the proposal's owner is not
the voice of someone reviewing her proposal. Each stage gets a code from `selection.stage_code`:
`no_answer` (the take was undelivered), `no_block`, `unparseable`, `too_few` (no valid seat), or
null. `selection.fallback_words(code)` says each in words, for the thread, a seat's reason and a
retake note: "the chair gave no usable list" (`chair_failed`), "no hermes-selection block",
"a hermes-selection block that did not parse", "no valid seats", and for `no_answer` and `lost`
likewise.

**The chair's retake.** A chair's delivered take whose code is `no_block`, `unparseable` or
`too_few` is discarded while she has a take left, through `_discard(..., extra={"stage": 3,
"code": <code>})`, with the playbook's own note in place of voice's: "Retake 2 of 3. No usable
seat list: <words>. End your answer with the ```hermes-selection block at column 0, 1 to 10
seats besides the fixed four." (the block's own count, as the seat rule's "the 1-10 others").
Only her third take falls back, with its own code; an undelivered take falls back at
once (`chair_failed`), or keeps the held take. Stages 1-2 are never asked again for a list, since
their failure never costs the run its committee.

**Resolution.** `selection.resolve` runs in the reduce of the chair's kept take.
- The chair's list is authoritative. Stages 1-2 feed only who put a seat forward and who was
  considered, and their failure never causes a fallback.
- `reviewers` is `senior_director`, `manager`, then the chair's valid seats in her order. Past
  twelve, the rest are considered with the reason "over the 12-seat bound". Each is represented by
  the seat the chair's `not_seated` entry for that slug names when that seat is seated, else by
  `senior_director`, so an overflow seat always has a representative.
- `nominated_by` is computed master-side: the earliest selector whose valid list held the seat
  (`owner`, `manager` or `senior_director`), `fixed` for the fixed four and `default` for a
  fallback seat.
- `considered` collects every stage's invalid entries and `not_seated` entries, the earlier seats
  the final roster left out (the reason is the dropping stage's `not_seated` entry for that slug,
  else "dropped by <Name>") and the overflow. It is keyed on a seat's slug or a stakeholder's
  lowercased name, the latest stage winning, and a seated slug is never in it. A note that names a
  listed seat by its slug, title or persona name (casefolded letters and digits, or its words in
  any order, so "Staff Engineer" is `staff_ic` and "Partner team engineering lead" is
  `partner_owner`) is keyed on that seat's slug, so a dropped seat and the note about it are one
  entry. When listed seats share that name (a selector re-slugged a derived stakeholder), the
  note is about the one its own stage dropped, else the first listed. A note naming a seated
  seat that way is dropped, since that stakeholder is seated.
  Outside the overflow, `represented_by` names a seated slug other than the owner, or is null. It
  keeps the first
  `selection.CONSIDERED_MAX` (40) entries and each stage's first `selection.INVALID_MAX` (20)
  invalid ones, and counts the rest as `considered_dropped` and `invalid_dropped`.
- **Fallback.** When the chair's code is not null, the run seats the default committee:
  `selection.fallback(code)`, the fixed four plus `tpm`, `pm`, `tl`, `staff_ic` and
  `data_scientist`, with `cast.SENIORITY` as the reviewers. `fallback` is `chair_failed` (her
  take was undelivered), `no_block`, `unparseable` or `too_few`. The five default seats say
  "in the default committee (<words>)", the chair's list adds nothing to `considered`, and an
  earlier seat no later usable list dropped is considered as "not in the default committee
  (<words>)", <words> being `selection.fallback_words(code)`. A raise inside `resolve`, or a result that cannot be
  installed, counts as `unparseable`, with its text on `error`. `reduce` never raises, and a
  roster holding every reviewer is installed on every path, so a fallback run's phases after
  `s3-senior_director` are a default committee's.
- **Lost.** Selection lives in the master's memory, like the meeting. A process that picks the
  run up at `open` without having opened it records a `lost` reduction ("the meeting cannot be
  started here", `_LOST_OPEN`), and one that picks it up at a selection phase records the
  meeting's own `lost`; either way the run ends failed and thread.md keeps what was written.
- `_apply_selection(s, resolved)` installs the result, from one resolved dict, and is the only
  code after `open` that sets `s["roster"]`, `s["reviewers"]`, `s["considered"]` and the cap; it
  resets `s["opening"]` to a copy of the reviewers. One exception: 1:1 finalize
  (`_apply_one_on_one`) is the cap's second writer, adding one when a 1:1 hands the junior IC an
  edit and the cap is unset.

**Who a seat speaks for.** Seed hands each turn goal the considered stakeholders whose
`represented_by` is that seat (`cast.goal(..., speaks_for=...)`), rendered in the brief as one
line, `You also speak for: <stakeholder>, <stakeholder>.`, of at most `cast.SPEAKS_FOR_MAX` (150)
characters: whole names only, ending ` (full list under ## committee seated).` when some are cut,
and no line for a seat that speaks for nobody. A library seat's goal also says `Why you hold this
seat: <rationale>.`, because a library persona is hand-written and lacks this run's reason; a
derived seat's fields are its reason. Fixed seats get no Why line (their reason is
`FIXED_RATIONALE`), but `senior_director`, `manager` and `junior_ic` get the speaks-for line when
they represent someone; the chair's decision gets neither, and the owner never speaks for anyone.
Both lines are selector text, so they sit above the brief's `style:` line: on a derived seat
`cast.DERIVED_STYLE` follows them, and a hand-written brief (a library or fixed seat) adds that
same sentence on its own line under them, before its own style. Eval's `concern_coverage@4`
counts such a stakeholder as represented only when its representative's turns raise its concern.

**The cap.** With `HERMES_COMMITTEE_MAX_TURNS` unset, the cap is 2 × reviewers + 16, fixed when the
chair ratifies: 22 for three reviewers, 30 for the default seven (so a fallback keeps 30), 40 for
twelve. Until then it is 30, provisionally. Each edit delegated from a 1:1 then raises it by
one (see "One-on-ones"). When every owner reply delegates, reviewer k opens at
turn 3k-2, so every seated reviewer gets an opening turn. An explicit value is used as-is
(`s["cap_explicit"]`), even one below 3 × reviewers - 2, which cuts the opening round short.

**The thread.** The `open` header's `Committee:` block lists the fixed four in the legacy form
(`- owner — Name, Title`), then `- Reviewer seats: chosen below`, then `Seat library:` with one
`- slug: Title. Lens: <lens>` line per `LIBRARY` slug, then the ground rules. Each kept stage
appends:

```
## selection N: Name, Title (role) proposes|amends|ratifies

<the prose, its hermes-selection and hermes-turn fences stripped>

Seats:
- slug: Name, Title. Why: <rationale>.

Not seated:
- stakeholder: reason. Represented by <Name> (<slug>). | Not represented.
```

`Not seated:` appears only when the list has entries. A note ends "Represented by <Name>
(<slug>)." only when the seat it names is on that stage's `Seats:` list or is one of the fixed
four (never the owner), and "Not represented." otherwise; the slug follows the name, so a
look-alike name cannot pass for the owner's. Each list shows its first `thread.LIST_MAX` (20)
lines and then `- N more not listed.`. A delivered stage with no usable list gets one line in
place of its lists, in `fallback_words`: `_(no usable seat list: no hermes-selection block)_`,
`a hermes-selection block that did not parse` or `no valid seats`. An answer that is its seat
list and nothing else gets the prose stub `_(the seat list was the whole answer)_`, not "signals
only". An undelivered stage is the `NO_TURN` stub alone. After the chair's kept take, and before
`t01` is minted:

```
## committee seated

- <slug>: Name, Title. Why: <rationale>. Put forward by <Name>. | A fixed seat. | In the default committee.

Considered, not seated:
- stakeholder: reason. Represented by <Name> (<slug>). | Not represented.

Fallback: the default committee (<words>).
```

`Considered, not seated:` becomes `Everyone considered was seated.` when nobody was left out and
nothing was cut (the cut ones are one `- N more not listed.` line), and the `Fallback:` line
appears only on a fallback. Every line the master renders from worker text is dash-mapped onto
one line, and the `- slug:` form keeps every one of them out of eval's header roster pattern
(`^- (\w+) — (.+)$`). In a body (a turn's, the decision's or a selector's prose) a line that
starts with up to three spaces and `#` is escaped with a backslash after any line separator
`str.splitlines` knows (`\n`, `\r`, `\x0b`, `\x0c`, `\x1c`-`\x1e`, `\x85`, U+2028, U+2029), so
no text-mode or Markdown reader sees a forged entry; inside a fenced code block a `# comment`
stays as written and only a `## ` line (every entry heading's level) is escaped, because eval's
reader does not skip fences. The view and eval take the committee from the final `selection`
reduction, not from these lines.

**The reductions.** Each kept stage is one `selection` reduction:
`{stage, role, final, delivered, body, parsed, code, proposed, proposed_dropped, not_seated,
not_seated_dropped, invalid_count, error, cap, take, takes, kept, voice, violations, flags}`.
`proposed` is the stage's first 20 valid seats as `[{role, name, title, rationale}]`,
`proposed_dropped` counts the rest, `not_seated` is the stage's first 20 notes as
`selection.not_seated` cleans them (`[{stakeholder, reason, represented_by}]`, the stakeholder and
reason clipped as `validate` clips, `represented_by` a slug or null), `not_seated_dropped` counts
the rest, `invalid_count` is how many of its entries were invalid, and `cap` is the master's cap at that
moment, so the view never guesses it before `t01`. The chair's reduction
(`final: true`) adds
`{seated, reviewers, considered, considered_dropped, invalid_dropped, fallback}`, and its `cap`
is the resolved one. `seated` holds the seat records in roster order, each `{role, name, title,
altitude, goal, ambition, stake, lens, style, rationale, nominated_by, source}` with `source` one
of `fixed`, `library` or `derived`. No selection reduction carries `artifact`, `revised` or
`turn`. A discarded selector take is voice's `take` reduction with `stage` added and
`turn: null`, and `code` too when it was the chair's unusable list. Readers take the latest
`selection` reduction with `final: true`. Selection reductions count under eval's
`metrics.other_kinds`, never as turns. eval reads `metrics.seats` from the final one (a malformed
one fails closed, so concern coverage caps), and `concern_coverage@4` counts a considered
stakeholder as represented only when its representative's turns raise that stakeholder's
concern, and as missing otherwise: see [committee-eval.md](committee-eval.md).

**The view.** `view_data` resolves every name through the run's own seats (`view._seats`). Those
are the final reduction's `seated`; the fixed four while selection runs or after it was lost; and
`cast.CAST` for a run reduced before selection. A role it cannot resolve renders "unattributed".
The view treats a run as selecting only when its phase is one of `view.SELECTION_PHASES` (the
three stages and their `-take2`/`-take3`, compared, never parsed) or a `selection` reduction
exists, so a run from before selection keeps today's nine seats and a null `selection` block
before its first turn as after it. Roster rows add `rationale`, `nominated_by`,
`nominated_by_name` (a selector's name, null for `fixed` and `default`) and `source`, all null on
a legacy run. The top-level `selection` block is null or
`{state, current, stages, fallback, considered, considered_dropped, invalid_dropped}`. `state` is
`selecting`, `seated`, `fallback` or `lost`. `current` is `{role, name, verb}` (`proposing`,
`amending` or `ratifying`) while a stage is in progress, from a static map of
`SELECTION_PHASES` to its selector, and null otherwise. Each stage carries its `code`, its
`proposed` list (each item with `source`, `library` or `derived`), `proposed_dropped`, its
`not_seated` notes (`{stakeholder, reason, represented_by, represented_by_name}`, represented only
as its thread entry says, so an unresolved representative is null), `not_seated_dropped`,
`invalid_count` (a reduction from before these reads as none), and voice's segments, badges,
take, takes, violations and flags, as a timeline entry does, except that a stage never shows
voice's soft-flag badges (`no_pointer`, `no_example`, `tells`), since a selector is asked for no
pointer or example, nor `signals_only`, since for a selector the list is the answer. Each
`considered` entry names its `represented_by_name`.

On the committee tab, a run that is seating its committee or holding its up-front 1:1s never shows
"Nothing said yet": the empty-state gate is
`data.timeline.length === 0 && ((data.selection == null && oneOnOnes.length === 0) || variant === 'metrics')`,
`oneOnOnes` being the payload's `one_on_ones`.
Before `t01` the tab shows the progress bar (its cap read off the latest `selection` reduction
once one exists), the roster with each seat's "why:" and "put forward by <Name>", "fixed seat" or
"default seat", and the Selection card. The transcript, the verdict card and the Document card
come with `t01`, even though `open` has already kept the original. The Selection card stays right
under the roster after that. While a stage runs it says "<Name> is <verb> the committee". It
shows each stage's words, badges and proposed seats (`slug: Name, Title. Why: <rationale>`, the
title alone for a seat named from it, as `cast.label` says it), then who that stage left out
("Left out: <stakeholder>: <reason>." with "Represented by <Name>." (for a derived seat
"Represented by <Name> (<slug> · derived seat).") or "Not represented."); "kept
take N of M; broke: …" when the take was retaken or kept breaking a rule; "no usable seat list:
<why>" in the thread's words when the stage's code says its list could seat nobody; each count
that is more than zero ("N more not listed.", "N more considered, not listed.", "N more invalid
entries, not listed."); the considered list with who represents each stakeholder, or "Not
represented.", or "Everyone considered was seated."; "Default committee: selection fell back
(<words>)" on a fallback, <words> being `selection.fallback_words(code)`; and "Selection stopped:
the meeting was lost." when the master lost the meeting mid-selection. No tab is added. The Metrics tab keeps its empty state until `t01` or the first kept 1:1 exchange, and it counts
a derived seat's turns like any other seat's.

A derived seat's name and title are a selector's words, and the name check above compares only
letters and digits, so a look-alike name (an added surname, a letter from another script) passes
it. The defence is the slug: every surface that shows a derived seat's name marks it
`<slug> · derived seat` (the roster, its transcript rows, a stage's proposed list, "Represented
by", the Metrics turns-taken and floor-request rows, and the Document card's "raised by"), so a
derived seat cannot pass for a cast or library persona.

**The contract one-on-ones builds on.** A later loop must not rename these:
- `s["roster"]`: slug to seat record, ordered owner, reviewers in opening order, junior_ic. It is
  `{}` before `open`, the fixed four from `open`, and the ratified committee from the chair's
  kept take. Pass `s["roster"] or None` to `cast.persona`, `cast.brief`, `cast.title`,
  `cast.goal` and `thread.append_turn`; None means `cast.CAST`.
- `s["reviewers"]`: the reviewer slugs in opening order, never popped. The default seven until
  the chair's list is installed.
- `s["cap_explicit"]`: whether `HERMES_COMMITTEE_MAX_TURNS` set the cap. When it did not, the cap
  is 2 × reviewers + 16 and a later loop may add to it.
- `s["current_kind"]`: default `None`; `None`, `"select"`, `"turn"` or `"decision"`, plus a later
  loop's own kinds (one-on-ones appends `"plan"`, `"one_on_one"` and `"one_on_one_close"`, as it
  does to the payload's `kind` enum). Junior turns are `"turn"`. `seed` and `reduce` tell a
  selection stage from a turn by it (the decision by `DECISION_PHASES` membership) and never parse the phase name.
- `s["base"]`: the take-1 name, set by every minter through `_begin(s, base)`, `_select`
  included. Reuse it rather than add a second phase key. `_retake` has no select branch.
- `s["selection_next"]`: the next stage, 1-3, and 4 once selection is done. 4 is the default, so
  a state that never saw `open` mints no s-phase, and `_lost` reads 4 at `open` as a process that
  never opened the run. `next_phase` checks it after a pending retake and before delegation; a
  later loop's up-front phases go once `selection_next > 3`, before the delegation rule.
- The `## committee seated` line `- <slug>: Name, Title. Why: <rationale>.` and its seat's
  `Put forward by <Name>.`, `A fixed seat.` or `In the default committee.`, which a goal may point
  a worker at for the seated role keys (a speaks-for line cut short already does).
- `s["considered"]`: the final `considered` list, and `cast.goal(..., speaks_for=...)` with the
  stakeholders a seat represents; a later loop's goal for a seated member passes the same.
- `test_the_manager_is_the_owners_manager`: the manager's stake says she manages Maya, the
  proposal owner.
- The SPA empty-state gate `data.timeline.length === 0 && ((data.selection == null && oneOnOnes.length === 0) || variant === 'metrics')`.

## Configuration

Environment only. The charge comes from `--goals` (a file, one goal per line, joined); absent, it
is *Decide whether to approve this proposal.*

| Var | Default | Meaning |
|---|---|---|
| `HERMES_COMMITTEE_ARTIFACT` | — (**required**) | Absolute path to the file under review |
| `HERMES_COMMITTEE_MAX_TURNS` | 2 × reviewers + 16 (`30` for the default seven) | Hard time-box on turn phases; an explicit value is used as-is; unset, it also grows by one per edit delegated from a 1:1 |
| HERMES_COMMITTEE_MAX_ONE_ON_ONE_TURNS | 16 | Budget of 1:1 exchanges per run, separate from MAX_TURNS; 0 turns 1:1s off; junk or negative falls back to 16 |
| `HERMES_COMMITTEE_DRIVER` | unset | Optional methodology slash command |

`ARTIFACT` and `MAX_TURNS` are read once, at `open` seed time, so a mid-run change cannot swap the
cap or the artifact; an `ARTIFACT` that is unset or is not an existing readable file fails the run
on the spot, naming the variable. A `MAX_TURNS` that does not parse — *and one below `1`, which
would mint a committee that never speaks* — counts as unset. Unset, the cap is 30 until the chair
ratifies, then 2 × reviewers + 16 (see "Selection"), plus one per edit delegated from a 1:1; an
explicit value is used as-is, even one too small for the opening round. `DRIVER` is read on
every `driver()` call, which may run in another process.

`HERMES_COMMITTEE_MAX_ONE_ON_ONE_TURNS` is read once, at `open`, beside `MAX_TURNS`; unset, one
that does not parse and one below `0` all mean 16. It counts exchange tickets, closing exchanges
included and retakes not, and `1` is off too, since a 1:1 needs two exchanges. With 1:1s off
there is no plan phase and no `align` offer, so the run's phases are exactly those of a run
without 1:1s. At the default of 16 the up-front 1:1s can spend at most 12, which leaves at least
4 for pauses. The other 1:1 bounds are constants: `ONE_ON_ONE_MAX_EXCHANGES = 4` member
exchanges per 1:1 and `UPFRONT_MAX = 3` planned 1:1s (`playbook.py`), a topic clipped to
`TOPIC_MAX = 160` characters (`cast.py`), and `PAIR_MAX = 200` for an `align` or `meet_N` line
and `OUTCOME_MAX = 200` for `agreed` and `still_open` (`turnblock.py`).

The charge is clipped to 400 characters (`cast.CHARGE_MAX`) with an ellipsis rather than cut
mid-word. A delegated `action` and a `stance` are cut to 200 (`turnblock.ACTION_MAX`,
`turnblock.STANCE_MAX`) by `turnblock._clip`: at the last space before the cap when that keeps at
least half of it, else mid-word, then `…`. That is a backstop, since the goal asks for one sentence
within the cap and an owner's action or an owner's or reviewer's stance over it sends the take back
(`action_too_long`, `stance_too_long`), so only a take kept while breaking that rule is ever cut:
take 3, or a held take 1 or 2 kept because its retake delivered nothing (`retake_failed`). The raw
lengths go on the turn's `voice` as `action_chars` and `stance_chars`. The
assembled goal is asserted under 3600 in every shape (see "Goal headroom").

## The turn block

Every speaker answers in prose and ends with one fenced block:

````
```hermes-turn
request_floor: yes|no
delegate: yes|no                                  # owner turns only; the target is always junior_ic
action: <one sentence, 200 characters or fewer>   # required iff delegate is yes
close: yes|no                                     # owner turns only
stance: <20 words or fewer>                       # where you currently stand and why
```
````

Absent stays absent: a missing or malformed block means "said their piece, nothing further". The
gates are master-side. `delegate` and `close` count only from the `owner`, and `delegate: yes` with
no `action` is dropped whole. `request_floor` counts only from a reviewer, and never from a role
already queued or still to speak in the opening round. A delegation outranks `close` — the edit
still happens, and costs a turn — and the cap outranks both, naming in the decision any delegation
it drops.

Before any of that, `turnblock._one` turns every non-printable character in a value (a control
such as NUL, an invisible or bidi mark, a lone surrogate) into a space and strips the ends, so no
text key (`action`, `stance`, `agreed`, `still_open`, `align`, `meet_N`) carries one into a goal,
a file or the committee tab. A NUL in a goal would kill the master at dispatch, and a lone
surrogate cannot be written to thread.md. A value left blank is absent.

`stance` is not a gate. It is free text, recorded on the turn's reduction and accumulated per
role so the committee tab can show where each persona currently stands. Absent stays absent: a
persona that states no stance is shown as having none, never as neutral. Only the owner and the
seated reviewers are issued a block (a selector is not), so the junior IC and the chair state no
stance. It is the one
key asked for in prose rather than shown in the worked example `turnblock.instruction` hands a
speaker — a copied `stance: <20 words or fewer>` would mint that placeholder as what the persona
said, and unlike a flag a stance is rendered back verbatim.

**The owner cannot close before the opening round drains.** A `close: yes` on a turn where any
reviewer has still to take its opening turn is recorded on the reduction and then discarded: the
owner is told so in its goal, and `_apply_block` enforces it. Without the gate the owner — whose
persona wants "a clear decision" and "concedes fast on small things" — can end the committee at
turn 02, producing a two-turn transcript that reaches `done` looking healthy. The
owner may close again on any later turn.

**1:1 keys.** The block also carries the 1:1 keys, all in `turnblock.KEYS`. Each is honoured only
where this table says, and recorded but ignored anywhere else. The owner's and the manager's
meeting goals offer `align` (`turnblock.instruction(..., align=True)`) only while 1:1s are on.
The plan and the 1:1 exchanges get their own worked examples (`turnblock.plan_instruction`,
`turnblock.one_on_one_instruction`), and a 1:1 goal never shows `request_floor`, `close`,
`align`, `meet_N` or `stance`.

| key | honoured on | from |
|---|---|---|
| `align: <role> <role>: <topic>`, one per turn (a repeated line: the last wins) | a delivered meeting turn | owner, manager |
| `meet_1`, `meet_2`, `meet_3`, each `<host> <guest>: <topic>` | the plan | owner |
| `aligned: yes\|no` | a 1:1 member exchange | either member |
| `agreed`, `still_open`, one line each | a 1:1 exchange or closing exchange | the host |
| `delegate`, `action` | a 1:1 exchange or closing exchange, held until the 1:1 ends | owner |
| `request_floor`, `close`, `align`, `meet_N` | never inside a 1:1, which records no `stance` either | nobody |

A pair line is read by `turnblock.pair`: it is split at the first `:` into roles and topic, and
the roles are split on commas or spaces and lowercased. The seated roles are the keys of
`s["roster"]`, the seats listed under `## committee seated`, so a library or derived seat
qualifies and the `chair` sentinel does not. A plan line's host is `owner` or `manager` and its
guest another seated role, never `owner` or `junior_ic`; an `align` names two distinct seated
roles, neither of them `junior_ic`. A dropped line is recorded with the first reason that
applies, in this order: `one-on-ones off` (align only: the budget is below 2),
`not owner or manager` (align only), `malformed` (no `:`, or not exactly two roles), `no topic`,
`unknown role`, `invalid host` (plan only), `owner as guest` (plan only), `same member`,
`junior_ic`, `duplicate` and `budget`. An `align` is a `duplicate` of a pair already pending (a
pair may meet again once its 1:1 is done); a plan line is also a `duplicate` of an earlier line
that passed the role checks, whether that line was scheduled or dropped for `budget`. A pair is
dropped for `budget` when the budget cannot hold it once every pending pair and the closing
exchange of the 1:1 in progress are reserved (see "One-on-ones"). Only the decision drops a
scheduled pair, as `meeting ended`. Like `stance`, `agreed`, `still_open` and `action` are asked
for in prose. The plan's worked example is the one placeholder line
`meet_1: <host> <guest>: <topic>`, which names no seated role, so a verbatim copy schedules
nothing. A member exchange's worked example is `aligned: no` alone, so a verbatim copy never ends
a 1:1, and a closing exchange has none. The owner is asked for `delegate` in prose too and is
never shown `delegate: no`: her latest `delegate` stands, so a template copied on a later
exchange would withdraw an edit she holds. A `delegate: no` she writes on purpose still
withdraws it.

## Voice and retakes

Members talk like engineers in a meeting, not like memo writers. The rules live in
`playbooks/committee/voice.py` (`voice.RULES`, versioned by `voice.RULES_VERSION`), distilled once
from the operator's diff-authoring skill; nothing reads the skill at runtime. `open` writes them
into the thread header after the roster, under `Ground rules for every speaker:`, and every goal
carries one pointer line with the speaker's cap (`cast._RULES_POINTER`). The header labels are
plain (`Charge:`, `Artifact:`, `Committee:`), with no bold. The thirteen numbered rules ask for a
path:line and one example (rules 8 and 9 name the category, then one checkable instance), and one
blank line ends the list, so Markdown never folds the unnumbered additions into rule 13. The
additions name filler and hedging with examples (never 'Great question', 'Hope this helps', 'It's
worth noting' or 'To be clear'; Bad: 'I think this might perhaps break.') and show one good turn
whole: `Defer it: the retry loop at engine/dispatch.py:284 never backs off, so one dead host pages
all night. For example, h3 failed 40 times in 10 min.`

| seat (`voice.kind`) | cap | bullets | images |
|---|---|---|---|
| owner, and every reviewer (any seat not below, a generated one too) | 150 words | 5 | 1 |
| junior IC | one sentence of 40 words or fewer, on one line | one line | 0 |
| chair | 300 words | 8: one list of conditions, each with an owner and a date | 0 |

Nobody may use headers, bold, tables or nested bullets. An image is either a file the speaker
writes as `runs/<run_id>/images/{base}.svg` or `.png` (`base` is its take-1 phase name, so
`t02-owner.svg`) or a mermaid block, each with a caption of 15 words or fewer and a `Description:`
line of 40 words or fewer that later speakers read as text. The goal names the folder as "the
images folder beside the thread (not your working directory)": a worker's cwd is wherever it was
launched, and a relative `images/` there would write into that checkout. Either of these is one
image:

````
![Retry path before and after](images/t02-owner.svg)
Description: the old path retries forever; the new one stops after 3 tries.

Figure: Rollout order
```mermaid
flowchart LR
  canary --> region --> global
```
Description: canary first, then one region, then everywhere.
````

**Every take is measured.** `voice.measure(body, role)` runs on the speaker's own prose
(`turnblock.strip(answer)`), never on thread.md. Fenced blocks, image references and the
`Figure:`/`Description:` lines add no words and break no formatting rule, so a snippet holding
`# x` or `**kw` is safe. A fence is what CommonMark renders as one: indented by up to three spaces
(a tab or a no-break space makes it prose), and a backtick fence's info string holds no backtick;
an unclosed fence is prose. The one tab that does indent a fence is a lone tab right under a line
of a list item whose text starts by column 4 (a bullet, its indented continuation, or a blank line
inside it), where Markdown reads the fence as the item's own; its closer must be tab-indented too.
A tab-indented `#` is never a heading. A dash inside a quoted span, from `"` or `“` to the next matching close
on that line, is not counted: `Ship “a — “b” c” now.` has none. Bold and sentence ends inside a
double- or single-quoted span are the artifact's, not the speaker's, so neither counts there;
bold on a `>` blockquote line does not count either, nor does a `**` with a digit on both sides
(`2**10`). A sentence end skips `e.g.`, `i.e.`, `vs.`, `etc.`, `cf.`, `sec.`, `approx.`, `no.`,
`a.m.`, `p.m.`, `U.S.` and the month abbreviations (`Jan.` to `Dec.`, `Sept.`), past any opening
bracket or quote (`(e.g.`), so `Renamed the 'Why now?' heading.` is one sentence. A setext
underline (a `===` or `---` line right under a prose line) counts as a header, because Markdown
draws one; under a bullet or a `>` blockquote line, or under a list item's continuation unless
indented to the item's text, Markdown draws a thematic break (or an empty item) instead, and it
does not count. `first_line_words` is the first sentence of the first line.
`voice.check_images` is the only IO. A file image is ok only when it is referenced as exactly
`images/<name>`, named for this speaker's `base`, and is a regular file (not a symlink, not a FIFO)
of at most 2 MB with PNG or SVG magic, in an images folder that exists and is not a symlink; a
passing one also records `sha256`, of the bytes checked. `images` keeps the first 8 records and
`images_count` counts them all, so one oversized answer stores 8, never thousands. Every take's
metrics stay on its reduction under `voice`.

**A take that breaks a hard rule is sent back.** The hard rules, in `voice.violations` order:
`over_cap`; `multi_line` and `multi_sentence` (junior IC); `headers`; `bold`; `tables`; `nested`;
`too_many_bullets`; `too_many_images` (on `images_count`); `image_uncaptioned` (a caption over 15
words, a description over 40, or either missing); `image_missing` (a file image that is not ok,
and every http, reference-style or shortcut `![label]` image); `action_too_long` (an owner action
over 200 characters); `stance_too_long` (an owner's or a reviewer's stance over 200 characters);
`filler` (2 or more `voice.STOCK_FILLER` phrases; one is only counted). That list is stock filler
nobody says in a meeting: `great question`, `hope this helps`, `I hope this helps`, `it's worth
noting`, `it is worth noting`, `I'd be happy to help`, `happy to help`, `let's dive in`, `let's
dive into`, `as an AI`. They are matched as whole words, case-insensitively, in the speaker's own
prose (quoted spans, inline code and `>` lines left out, `’` read as `'`), and where two overlap
the longer counts once, so `I'd be happy to help` is one phrase and `I'd be happy to pair`, `to be
cleared` or `unhappy to` are none. The phrases found ride on `voice.filler_phrases` (phrase to
count). `no_pointer`, `no_example`, `dashes`, `long_first_line` (a first sentence over 25 words),
`stance_clipped` (a kept take whose stance was cut to 200: take 3, or a held take 1 or 2 kept via
`retake_failed`) and `tells` are flags: shown, never sent back. `tells` is any process narration
(`I checked`, `I've reviewed`, `Having read`, `Let me`, `I can confirm`), turn number (`turn 5`,
`turns 3`, `t04`), unchanged-original narration (`the original is intact`, `nothing was
modified`), hedging (`I think`, `I believe`, `perhaps`, `might`, `could potentially`, `arguably`,
`it seems`) or any of eval's broader `voice.FILLER` phrases, counted as substrings anywhere in the
prose (`to be clear`, `that said`, `in summary`, `delve`, and the stock ones); the counts ride on
`voice.tells`, and `tells.filler` is the count eval reads.

`reduce` grades each take with `_grade` before any side effect. With violations and fewer than
`voice.MAX_TAKES` (3) takes so far, `_discard` records it as `kind="take"` and holds it: nothing
reaches thread.md, no gate is applied, no re-check or snapshot runs and no ticket is held. Its body
(never its turn block) is written to `runs/<run_id>/takes/{base}-take{n}.md`, 0600 in a 0700
folder, by the master only (`thread.write_take`: atomic, and `thread.takes_dir` refuses a folder
that is a symlink or a file, which leaves the take's `error` as `takes: …` and names no file). The
server never serves `takes/`. `next_phase` then mints the same speaker again, and the goal carries
`voice.note`, image rules first, clipped to 200 characters, and one line naming that file:

```
Retake 2 of 3. Rules broken: 205 words (cap 150); 3 bold. Say it again within them.
Your last take is in takes/t02-owner-take1.md beside the thread; keep its substance.
```

When the speaker was offered an image, `image_missing` names the one reference that passes (`an
image not at images/t02-owner.svg or .png`); a speaker offered none (the chair, the junior IC, a
refused folder) reads `an image missing or not your own file`. `filler` names the phrases found:
`2 filler phrases: 'great question', 'hope this helps'`. Both image rules, the word cap and one
more count fit the clip whole, and so do an image rule, the word cap and two named filler phrases;
a longer list loses its last counts, which the speaker can reread for.

| phase | what happens |
|---|---|
| `t02-owner` | 205 words and 3 bold: a `take` reduction, nothing in thread.md |
| `t02-owner-take2` | 140 words: kept as turn 02 with `take: 2, takes: 2`, badged "retaken" |
| `t03-manager` | the turn counter never moved: retakes cost no turns |

Take 3 is kept verbatim whatever it says, its prose never clipped (only an over-long stance is
cut, and flagged `stance_clipped`), with the rules it broke. An undelivered or signals-only take
is never sent back; its `voice` is null.

- **Names and precedence (C8).** Take 1 is `t{NN}-{role}`, `s{N}-{role}`, `p01-owner`,
  `o{NN}-{role}` or `decision`; take k is `{base}-take{k}`, where `s["base"]` is the take-1 name.
  Every mint of a speaking phase, here and in any later loop, calls `_begin(s, base)`. `_retake` reads only `base` and `take`, so the
  turn counter, `current_turn`, `last_speaker` and HERMES_COMMITTEE_MAX_TURNS are untouched.
  `next_phase` checks `_lost`, then a pending retake, then a pending selection stage, then the
  1:1 plan and the 1:1 in progress, then delegation, the cap and the rest (the whole order is
  under "Phases"), so a retake runs before a pending delegation and before the cap. At a
  `DECISION_PHASES` phase a pending retake mints `decision-take{k}`, otherwise `ruling`.
- **A retake that delivers nothing** (its worker failed, or it sent signals only) keeps the held
  take, graded again, with `retake_failed` added; that take is then written, gated, re-checked and
  snapshotted once. Its over-long stance or action is cut as take 3's would be, and the stance
  flagged `stance_clipped`. For the chair the held verdict is written to thread.md but routes nothing
  (`delivered: false`, `ended: "chair retake failed"`, `needs_human_ticket_ids: []`), and the run
  ends failed.
- **A fresh process mid-retake** has no meeting in memory, so the meeting is lost: thread.md ends
  at the last kept turn, a chair retake goes on to `ruling` with no kept verdict, and the run ends
  failed.
- **The junior IC's retake only reports.** Only take 1 edits. A retake's `seed` makes no copy and
  takes no pre-edit digest, and its goal says "Do not edit the revised copy again; whatever your
  first take changed stands." The kept report's re-check still measures take 1's edit. If the copy
  differs from what the discarded take 1 left, that turn's `error` says
  `retake modified the revised copy`, whichever take is kept.
- **The C4 contract**, for this loop and every later one. A discarded take is `kind="take"` with
  `{phase (the base), role, turn, take, kept: false, delivered: true, body, stance, action, voice,
  violations, flags, error}` plus the caller's `extra` keys, and never `artifact`, `revised` or
  `cap` (the keys the kind-agnostic readers scan). Its `body` is the prose without the turn
  block, and its `error` is `takes: …` when the take file could not be written, else null. A kept
  take goes under its own kind (`turn`, `decision`, `selection`, `one_on_one_plan`, `one_on_one`) with
  `{take, takes, kept: true, voice, violations, flags}`; `voice` is null on an undelivered take,
  and a decision adds `body`, the chair's prose before the footer.
- **Helpers later loops reuse**, none of which restates a rule: `_begin`;
  `_grade(run, s, role, answer, *, file_images=True)`, which never raises (pass
  `file_images=False` where an images/ name could collide, as one-on-ones' o-phases must: every
  file image is then refused); `_discard(run, s, role, answer, metrics, violations, flags, turn,
  extra=None)`, which writes the take file and sets `s["last_take"]`; `_keep(..., *,
  file_images=True)`, given the same `file_images` as `_grade`; `view._segments(doc)` (never
  `voice.segments(body)`) and the view's `Segments`. `_begin` resets `last_take` and `image`; seed
  sets `s["image"]` to the stem its goal offers ("" for none) and passes `last_take=s["last_take"]`
  to `cast.goal`, so a later loop's seed that sets neither gets no file line and no named
  reference.
- **Model invariants (T11, `check_invariants` in tests/unit/test_committee_playbook.py).** Phase
  names are unique, the last phase is in `DECISION_PHASES`, exactly one decision is kept, NN is
  unique, ordered and within the cap among non-`-take` phases, and every delivered reviewer turn
  that was kept is answered by a kept owner turn. Every check after the first leaves out the
  selection phases, `p01-owner` and every `o{NN}-*` phase; the 1:1 phases have their own (see
  "Invariants").
- **The summary.** `voice.summary` over the kept rows (the last turn reduction per number, plus
  the latest decision) is the view's top-level `voice` and eval's `metrics.voice_summary`; eval
  measures a pre-voice run's bodies itself, on copies. Voice changed concision's inputs, so it is
  `concision@2`, and eval's legacy `action_clipped` also counts an action ending `…` as clipped.
  See [committee-eval.md](committee-eval.md).

**Goal headroom** at the worst case (charge 5000, action 5000, image stem 48, retake note 5000,
the last-take line with that 48-character stem, deep paths) against `cast.GOAL_MAX` 3600. Every
goal shape must fit it. For the cast's own shapes, voice's rule stands: if one goes over, shorten
`_GUARDRAIL_IMAGE` first (the owner's and every reviewer's goal carries it). Selection's shapes
keep a 20-character margin (3580), in characters and in UTF-16 units, and spec D7 governs them:
a select goal or a library seat that goes over shortens its own fixed text, since
`selection.FIELD_MAX` clips only a derived seat's fields; for a derived seat,
lower `selection.FIELD_MAX`, never raise `GOAL_MAX`. The tightest shape is the owner's retake
with the align offer, 30 characters under at this worst case (a real stem such as
`t12-data_scientist` is 30 shorter). One-on-ones paid for that offer out of the owner's own fixed
text: `_GUARDRAIL_IMAGE` went from 228 to 182 characters before format, and `_FLOOR_OWNER` and
the thread's channel paragraph gave up 32 more. The same worst case is why the goal names the
takes file and the images folder relative to the thread rather than by absolute path.

| shape | take 1 | retake |
|---|---|---|
| owner | 3127 (473 left) | 3453 (147 left) |
| senior_director | 2826 (774 left) | 3152 (448 left) |
| manager | 2732 (868 left) | 3058 (542 left) |
| tpm | 2691 (909 left) | 3017 (583 left) |
| pm | 2708 (892 left) | 3034 (566 left) |
| tl | 2716 (884 left) | 3042 (558 left) |
| staff_ic | 2741 (859 left) | 3067 (533 left) |
| data_scientist | 2687 (913 left) | 3013 (587 left) |
| junior_ic | 2868 (732 left) | 2893 (707 left) |
| chair | 2553 (1047 left) | 2879 (721 left) |
| s1-owner (select) | 3007 (593 left) | 3293 (307 left) |
| s2-manager (select) | 2965 (635 left) | 3253 (347 left) |
| s3-senior_director (select) | 3214 (386 left) | 3510 (90 left) |
| derived reviewer (24-char slug, clip limits) | 3190 (410 left) | 3496 (104 left) |
| library seat (the longest: sre) | 3189 (411 left) | 3474 (126 left) |
| fixed reviewer speaking for others (senior_director, the longer) | 3029 (571 left) | 3326 (274 left) |
| junior_ic speaking for others | 3100 (500 left) | 3090 (510 left) |
| 1:1 plan | 2347 (1253 left) | exempt from retakes |
| 1:1 owner host | 2937 (663 left) | 3224 (376 left) |
| 1:1 manager host | 2900 (700 left) | 3189 (411 left) |
| 1:1 library guest (the longest library seat) | 2969 (631 left) | 3254 (346 left) |
| 1:1 derived guest | 2968 (632 left) | 3274 (326 left) |
| 1:1 library member of a pause (the longest library seat) | 3044 (556 left) | 3329 (271 left) |
| 1:1 derived member of a pause | 2988 (612 left) | 3294 (306 left) |
| 1:1 owner closing | 2772 (828 left) | 3059 (541 left) |
| 1:1 manager closing | 2733 (867 left) | 3022 (578 left) |
| owner meeting, align offered | 3244 (356 left) | 3570 (30 left) |
| manager meeting, align offered (speaking for others) | 3081 (519 left) | 3407 (193 left) |

The select rows are `cast.select_goal` for each stage, each naming its own image (`s1-owner.svg`)
and, on a retake, its own last take (`takes/s1-owner-take2.md`). The derived reviewer is the
longest persona a selector can seat: a 24-character slug, every field at its clip limit
(`selection.FIELD_MAX` = 94, cut from 120 so its retake fit within 3580 once
`cast.DERIVED_STYLE` and a 150-character speaks-for line joined it), image `t99-<slug>` and last
take `takes/t99-<slug>-take2.md`. Since one-on-ones shortened `_GUARDRAIL_IMAGE`, that retake has
84 characters to spare under 3580 (each character of `FIELD_MAX` is five of the goal, so 110
would still fit), and `FIELD_MAX` stays 94; at the cast rows' 48-character stem the retake is
3536, still within 3580. A derived seat with no stake measures the same,
its stake being the rationale clipped to `selection.FIELD_MAX`. Each library row carries its
rationale at `selection.RATIONALE_MAX` in its "Why you hold this seat" line, the same speaks-for
line and the `cast.DERIVED_STYLE` sentence under them; the fixed rows carry the speaks-for line
and that sentence, at `t99-<role>` (the junior IC's goal offers no image). In
every row UTF-16 units equal characters: worker text above U+FFFF is blanked, and the fixed text
has none. The 1:1 rows are `_assert_one_on_one_goals_fit()`'s, at the same worst case plus a
5000-character topic and a 1:1 file under the deep run directory: the seated roster with the
derived seat at its clip limits and every library seat's rationale at `selection.RATIONALE_MAX`,
a 150-character speaks-for line on every seat but the owner, and a retake naming
`takes/o99-<role>-take2.md`. A library row is its longest library seat. The align rows are the
owner's and the manager's meeting goals with `align=True` at the cast rows' 48-character stem, on
that roster, the manager speaking for others. The plan is exempt from retakes, so it has no
retake shape. `test_every_goal_stays_under_the_budget_at_maximum_size` holds every one of these
under `GOAL_MAX`, and the selection, 1:1 and align rows within 3580 in both units; a later loop
that adds a goal shape adds it there and here.

## One-on-ones

Before the opening round the owner, or her manager (`manager`), holds 1:1s with key members, and
later in the review the owner or the manager can pause the meeting for more. It all lives in the
playbook; `engine/` and `server/` know nothing of it.

- **Scheduling.** Every scheduling and budget decision is made in `reduce`, by one of three pure
  gates: `_apply_plan` (the plan's `meet_N` lines), `_apply_block` (an `align` on a meeting turn,
  through `_align`) and `_apply_one_on_one` (the only place a 1:1 ends). `next_phase` only mints,
  and through `_decision` drops whatever the turn cap leaves pending. A pair needs 2 exchanges, or
  3 when its host is not a member (`_need`), and is scheduled only if the budget still holds it
  once every pending pair, and the closing exchange of the 1:1 in progress, are reserved
  (`_free`). So a scheduled pair always starts, and `one_on_one_used` never passes the budget.
  Scheduled pairs wait in `s["pending_one_on_ones"]`, first in, first out, one 1:1 at a time.
- **Who meets.** A 1:1 has two members who exchange, and a host who is always the owner or the
  manager. A planned 1:1 is its guest and its host, guest first. A pause names a pair: the owner
  hosts if she is in it, else the manager if she is, else the caller. A host who is not a member
  reads the 1:1 file once the members finish and records the outcome in one closing exchange
  (`one_on_one_close`), which counts against the budget but not the 4-exchange cap.
- **How it ends.** The first member opens and the two alternate. After each exchange by the
  second member (the host, when the host is a member) the 1:1 ends at the first of: `aligned`
  (both members' latest `aligned` is yes; an absent key reads as no), `exchange cap` (4 member
  exchanges) or `budget` (fewer than 2 exchanges of the budget left unreserved). An undelivered
  exchange with no held take ends it at once as `not delivered`, with no closing exchange.
- **Outcome.** A 1:1 is aligned when it ended `aligned`. `agreed` and `still_open` are the
  host's latest stated values (an exchange that omits one keeps the last), and with whether it
  aligned they are all the room reads of it. A pair has met, for the verdict footer
  (`s["one_on_ones_met"]`), only when both members spoke, so a 1:1 that ended `not delivered`
  counts only once it reached its third exchange.
- **Edits.** The owner may state `delegate` and `action` on any 1:1 exchange she speaks, closing
  exchanges included, and the latest block that states `delegate` stands (her worked example
  states none, so copying it keeps the edit she holds). A 1:1 that ends with an
  action held hands it to the junior IC, who applies it as an ordinary `tNN-junior_ic` turn before
  anything else runs, with `origin_one_on_one` set to that 1:1's `seq` and `delegated_by_turn`
  null. It costs one `MAX_TURNS` turn, and with the cap unset it raises the cap by one, so a 1:1
  edit never takes a reviewer's opening turn. The cap never drops it: a 1:1 starts only while a
  turn is left, and no plan or 1:1 phase spends one. A 1:1 without the owner makes no edit, and
  one that ends with nothing held hands nothing over.
- **Voice.** An exchange keeps the owner's or reviewer's cap and every hard rule in "Voice and
  retakes". A take that breaks one is retaken as `o{NN}-{role}-take{k}`, which spends neither the
  budget nor an exchange, and a retake that delivers nothing keeps the held take. Plan and
  exchange goals say "write no file at all": the master grades 1:1 takes with
  `_grade(..., file_images=False)`, so any file image is `image_missing` and retaken, because
  `images/` is the whole room's. A mermaid figure stays in the exchange. The plan is not speech in
  the room: it is graded but never retaken. As a meeting goal does, an exchange goal says whom a
  seated member speaks for, and a retake's goal names its kept take
  (`cast.one_on_one_goal(..., last_take=, speaks_for=)`). Every plan and exchange goal shape has
  its row in the goal headroom table.
- **Privacy.** Only a 1:1's participants' goals name its file. The file is 0600 in a 0700
  `one-on-ones/` folder, appended through `O_NOFOLLOW` and only as a regular file, and named only
  from seat slugs, so a planted symlink, file or FIFO, or a role that is not a slug, is refused
  rather than written through. A refused folder never stalls the meeting: the goal still names
  the path, the exchange's `error` records the refusal, and the 1:1 goes on.

## Where things land

Under `$HERMES_HOME` (default `~/.hermes`), mode 0700:

- `runs/<run_id>/thread.md` — the transcript, append-only: the `open` header (charge, artifact,
  the fixed four, the seat library, ground rules), one `## turn NN — <name>, <title> (<role>)` entry per settled turn (its
  kept take only), then `## decision`. Before the first turn come one `## selection N: ...` entry
  per kept selection stage and `## committee seated` (see "Selection"), then, with 1:1s on, the
  1:1 plan and each up-front 1:1's outcome; a pause's outcome lands between the two meeting turns
  its 1:1 ran between (see below). A turn whose worker failed
  still gets a stub —
  `_(no turn delivered — the worker failed; see hermes show)_`.
- `runs/<run_id>/revised/<basename>` — the revised copy, byte-copied from the original before the
  junior IC's first edit. After each junior-IC turn the master re-checks it — is it a regular file
  (a symlink or a FIFO is not), did its SHA-256 move — and records `verified: true|false` on that
  turn's reduction, which the decision repeats when it failed.
- `runs/<run_id>/doc/` — every version of the document, mode 0600 in a 0700 directory, each
  written as a dot-prefixed temp file and renamed into place. `00-original<ext>` is the bytes
  `open` hashed, written before the thread header; the first edit copies from it rather than from
  the live file, so an original touched mid-review cannot change what the junior IC edits. Only
  while it still hashes to the digest `open` took, though: workers can write `doc/` too, and a
  `00-original` that is gone, a symlink or rewritten is not used — the first edit copies the live
  file, which the decision's `artifact_intact` re-check covers, and that junior turn's `error`
  says `snapshot: …`.
  `tNN<ext>` is the revised copy as junior-IC turn NN left it, written after every junior-IC turn,
  delivered or not, and overwritten if that turn settles again. `<ext>` is the artifact's suffix
  when it is a dot and 1-16 letters or digits, and nothing otherwise. A revised copy that is
  missing, a symlink or a FIFO leaves no file and puts `snapshot: …` in that turn's `error`.
- `runs/<run_id>/images/` — mode 0700, made at `open` and again before any owner, reviewer or
  selector turn if it is missing (a run opened before voice has none). It holds the one image each
  owner, reviewer or selector take may write, named `{base}.svg` or `{base}.png` for its take-1 phase and overwritten
  by that phase's retakes. `thread.images_dir` refuses a folder that is a symlink or a file (that
  turn is then offered no image), and grading calls it with `create=False`, so grading never makes
  the folder. The master checks each referenced file ("Voice and retakes") and records only names,
  never a host path. The control plane serves one at
  `GET /api/runs/{id}/view/artifact?path=images/<name>` as raw bytes: only `.svg` or `.png` (400
  otherwise), reached by the same `O_NOFOLLOW` walk as `doc/`, 413 over 2 MB, 404 on a magic
  mismatch, under `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; sandbox`,
  `X-Content-Type-Options: nosniff`, `Cache-Control: no-store` and `Content-Disposition:
  attachment`, so an SVG opened directly downloads instead of rendering. With a `sha256` query
  parameter (the view always sends the one the master recorded) it is a 404 unless the bytes read
  hash to it, so an image a later worker overwrote is never served as the earlier speaker's.
- `runs/<run_id>/takes/` — mode 0700: the body of each take the rules sent back, as
  `{base}-take{n}.md` (0600), written by the master so the retake can reread it ("Voice and
  retakes"). No route serves it.
- `runs/<run_id>/one-on-ones/<seq:02d>-<m0>-<m1>.md`: one private file per 1:1, for example
  `runs/<run_id>/one-on-ones/01-tpm-manager.md`, `m0` and `m1` being its members in speaking
  order. Only `reduce` writes it, append-only and kept takes only: exchange 1 first writes the
  header `# 1:1 <seq>: <M0> ↔ <M1>, hosted by <Host>`, `Topic: <topic>` and the ground rules, then
  each kept exchange appends `## exchange N: Name, Title (role)`, and a closing exchange
  `## outcome: Name, Title (role)`. No reduction records its path, no route serves it, and the
  view never reads it (see "One-on-ones" for how it is kept private).

Every turn reduction also carries `answers_turn` (on an owner turn, the reviewer turn it answered)
and `delegated_by_turn` (on a junior-IC turn, the owner turn whose delegation it applied), and the
decision carries `dropped_delegation_turn`. All three are always written, null where they do not
apply, so an absent key marks a reduction from before they existed. The recorded `artifact` and
`revised` stay the master's absolute host paths; nothing that serves the view opens them.

thread.md gets each 1:1's outcome, never its exchanges. The plan writes
`## 1:1 plan: Name, Title (owner)`, one `- Host ↔ Guest: <topic>` line per scheduled pair (or
`_(no up-front 1:1s: no plan delivered)_`, or `_(no up-front 1:1s: no valid pairs)_`), and one
`- dropped: <line> (<reason>)` line per dropped plan line. A 1:1 writes its outcome entry the
moment it ends, so the entry comes before the next `## turn` entry and before `## decision`:
`## 1:1 <seq>: <Host> ↔ <Guest> (aligned)` or `(not aligned)` (`<A> ↔ <B>, hosted by <Host>`
when the host is not a member), then `Agreed: …` and `Still open: …`, each only when stated.
When the host stated neither, it reads `_(no outcome recorded: <ended>)_`, or
`_(no outcome recorded: the host's closing exchange was not delivered)_`. committee-eval takes
`## 1:1 N: ` and `## 1:1 plan: ` as entry boundaries: an outcome is its own entry, citable as
`where:"one_on_one"`, and the plan belongs to none. `verdict_grounded@2` and
`concern_coverage@4` count a claim or a concern settled in an outcome entry as grounded or
answered; see [committee-eval.md](committee-eval.md).

The plan is reduced as `one_on_one_plan` (`delivered`, `body`, `one_on_ones_scheduled`,
`one_on_ones_dropped`, `fallback`, `one_on_one_budget`, `error` and voice's kept-take fields),
and each kept exchange as `one_on_one`, with `seq`, `origin` (`upfront` or `pause`),
`called_by`, `after_turn` (0 for an up-front 1:1), `host`, `members`, `topic`, `speaker`,
`exchange` (null on a closing exchange), `closing`, `delivered`, `body`, `aligned`, `agreed`,
`still_open`, `delegate`, `action`, `final`, `ended`, `outcome` (`{aligned, agreed, still_open}`,
on the final exchange only), `delegated_action`, `one_on_one_budget`, `one_on_one_used`, `error`
and voice's kept-take fields. Neither kind carries `cap`, `artifact`, `revised`, `role` or
`turn`, because kind-blind readers pick those up. A discarded exchange is voice's `take`
reduction plus `seq` and `exchange`. A meeting turn adds `align` (as asked),
`one_on_ones_scheduled`, `one_on_ones_dropped` and `one_on_one_budget`, and every turn reduction
and every `rechecks` entry adds `origin_one_on_one`: the seq a junior turn's edit came from, null
otherwise. The decision adds `dropped_one_on_ones`, every drop of every reason, and its verdict
names the pairs that never met, `- dropped_one_on_ones (they never met): <role> ↔ <role> (<reason>)`,
for the reasons `budget` and `meeting ended` only, leaving out a pair that met in another 1:1.

A run reduced before `doc/` existed can be backfilled once from its junior-IC traces, from the repo
root: `python scripts/backfill_doc_snapshots.py --run <id> --rev <commit> --path <repo path>
[--dry-run]`. It replays each turn's recorded Edit calls onto `git show <commit>:<path>`, aborts
unless every re-check agrees and the result equals `revised/` byte for byte, refuses a run that
already has `doc/`, and writes every version or none. It opens `queue.db` read-only and changes no
database row.

The original is re-checked too, and symmetrically: `open` snapshots its SHA-256 and the decision
re-hashes it, recording `artifact_intact: true|false` and naming a mismatch in the verdict text.
Every worker runs under `--permission-mode bypassPermissions`, so without that check the only thing
holding "the original is never mutated" in a live run is the goal's prose.

## Running it

There is no `hermes` console script in this repo's `.venv`: `pip install -e '.[dev,server]'` to
get one, or call the module directly.

```bash
export HERMES_HOME=~/.hermes                       # pin it — see below
export HERMES_PLAYBOOK_MODULES=playbooks.committee
export HERMES_REPO=/abs/path/to/a/git/repo         # see below
export HERMES_COMMITTEE_ARTIFACT=/abs/path/proposal.md

.venv/bin/python -m engine.cli run committee --site local --agent claude \
    --goals charge.txt          # add --dry-run to preview the seed only
```

`HERMES_PLAYBOOK_MODULES` is what makes `committee` resolvable; it is deliberately not in the
engine's hardcoded import list. Pin `HERMES_HOME`: everything under `$HERMES_HOME/local` is
auto-imported *before* those modules, so an unpinned home can drag a private adapter in. Point
`HERMES_REPO` at a real git repo containing the ref named by `--base-ref` (default `main`), even
though the committee never touches a worktree — `crew.add` provisions one and health-gates the host
on `workspace_ready`, so a missing one fails host admission before the first turn, with an error
that says nothing about the committee.

## The committee tab

A committee run gets its own tab in the control plane: where the meeting got to and why it
stopped, the roster with each persona's current stance, the meeting oldest-first with every turn
attributed by name, each delegation and its re-check outcome, the verdict card, and the document as
it changed. The view states that the original is never modified — reading an unchanged repository
file as a failed edit mechanism is what swung a live verdict.

**The document card is a stepper: Original · Edit 1 (tNN) … · Final.** It is titled like the
other surfaces, "Document — <name> · N edits". An edit step shows that edit alone, the previous
version against this one, with the re-check's verdict (APPLIED, DID NOT APPLY, or re-check not
recorded) and its context, each line with a `tNN` link that opens that turn in the transcript:
"raised by <reviewer> — <their stance>", "delegated by <owner>: <action>" and "<junior IC>: <their
confirmation>" (or "no turn delivered"). When a step is placed by turn order rather than by the
recorded keys, its raised-by and delegated lines each say "(inferred from turn order)".

An edit's diff opens on what changed. It keeps three unchanged lines either side of each change
and folds every longer unchanged run into a "⋯ N unchanged lines" row that expands in place, and
it brings the first change into view as each step opens, so pressing Next shows the next edit
rather than the document's title again. Every diff can be unified or side by side, and the choice
holds as you step; the folds are cut before lines are paired, so both layouts fold the same lines,
and the added/removed counts always come from the whole diff. The layout switch appears only where
a diff is on screen.

Original ("as the committee was handed it") and Final show the whole document, rendered as
markdown for a `.md` or `.markdown` file. Neither loads an image the document names — every version
after Edit 1 is text a worker wrote, and a live image would make the operator's browser fetch its
URL — so its alt text stands in, as a link. Final is the version after the last edit that applied,
or the original if none did, labelled by the ruling — "Proposed — awaiting your ruling",
"Accepted", "Rejected", "Latest so far — no verdict yet (in session, or stopped before the chair
ruled)" or "The meeting ended without a ruling" — and has an "Original → final diff" toggle, off
by default, that shows the whole diff instead. When the run has snapshots to show, the reviewer row
that raised an edit, the owner row that delegated it and the junior row that applied it each have a
"see edit k" link that selects that step, scrolls the stepper into view and focuses it, so the
arrow keys step from there.

Text is fetched per step from `GET /api/runs/<id>/view/artifact?path=doc/<name>`, which reads only
`runs/<id>/doc/` under the server's own `HERMES_HOME`, so it works in the container that mounts only
the home. The server walks there from its `runs/` one directory at a time with `O_NOFOLLOW`, so no
symlink below `runs/` is followed, and it serves only a regular file; `view_data` sizes each version
by the same rule. A snapshot the server cannot read says "Could not read …", never that no edit was
made; a fetch that fails says so with a Retry button. A run with no readable snapshot at all — one
from before snapshots, or one whose `doc/` a worker emptied — says none is readable without
guessing why; one edit still readable is enough to step through, and only the versions that are
gone say "Could not read". A run with no edits says "No edit was made. The original stands as it
was.", which stays true beside a note that the turn cap dropped a delegation.

Before the first turn settles no reduction names the document, but `open` has already kept the
original and the first worker can run for an hour. The view names the file from the thread
header's artifact line meanwhile, and once `doc/00-original` is readable it shows the card, opened
on Original, under "Nothing said yet". On a run that is seating its committee it waits for the
first turn, as the transcript does (see "Selection").

**1:1s render inside the transcript and the Metrics section, and no tab is added.** Each 1:1 is
a collapsed group headed `1:1 <seq>: Host ↔ Guest · <outcome>` (`A ↔ B, hosted by H` when the
host is not a member) beside its topic, where the outcome reads `in progress`, `aligned` or
`not aligned (<ended>)`. A 1:1 with no final reduction reads `in progress` only while
`progress.paused.pairs` lists its seq; one cut off by a lost, decided or chaired run reads
`stopped before it finished` instead, and is still not counted as finished. Its `Agreed:` and
`Still open:` lines (or "no outcome recorded: …", "in progress" or "stopped before it
finished") show even while it is collapsed, and the header is the toggle that shows every
kept exchange, rendered through `Segments` and badged like a turn. A group sits after the turn
it followed, and up-front groups sit before the first turn. Before `t01` exists they render under
the Selection card as "1:1s before the opening round", so an up-front 1:1 is on screen as soon
as its first exchange is reduced. While 1:1s are pending, the progress card reads "Paused for
1:1s: A ↔ B (exchange x of 4)", with "(closing)" on a closing exchange, or "1:1s next: …" while
none of them has a kept exchange yet. While a 1:1 runs nobody holds the floor, and the roster
rows of its two members (of the host alone during a closing exchange) read "in a 1:1", a solid
live badge that outranks every floor state. The Metrics section's 1:1s block is never hidden:
"K 1:1s · E of B exchanges · A aligned" (K the finished 1:1s), or "1:1s were off for this run"
when the budget was below 2, or "1:1s not recorded for this run" for a run reduced before 1:1s
existed. The verdict card's `dropped-one-on-ones` note lists the pairs that never met, for the
reasons `budget` and `meeting ended`, as the verdict footer does. An edit delegated in a 1:1 is a
stepper step "raised in 1:1 M0 ↔ M1", with "why: <topic>", "delegated: <action>" and a
`1:1 <seq>` link that opens the group and scrolls it into view, and the group's "see edit k"
selects the step. A derived seat's name carries its marker on every 1:1 surface. All of it is
built from reductions: `view_data` carries `one_on_ones`, `progress.paused` (`{pairs, current}`,
null when no 1:1 is pending or the meeting is over), `progress.one_on_one` (`{used, budget}`,
null for a run reduced before 1:1s) and `verdict.dropped_one_on_ones`, and reads neither the 1:1
files nor the server's environment. `timeline`, the floor and the turn metrics stay turns only.

The view is the playbook's, not the control plane's. `playbooks/committee/view/dist/committee.umd.js`
is built from `playbooks/committee/view/src/` with the toolchain in `web/` and committed, so
running it needs no Node — only rebuilding does
(`cd web && ./node_modules/.bin/vite build --config vite.playbook-view.config.ts`). The server
finds it through two optional methods on the registered playbook object, `view_asset()` and
`view_data()`; `engine/` knows nothing about either, and a playbook without them simply has no tab.

**A view can also put a section on another tab, but only one it declares.** The bundle's global is
the component itself, so the one way to say more without a named export is a static property on
it: `View.variants = ['metrics']`. The host renders the view on its own tab with no `variant`
prop. On another tab it passes `variant="<tab>"` — today only the Metrics tab, as `"metrics"` —
and renders the view there only if that name is in `View.variants`, in a fixed 380px column beside
the host's own section. A view that declares nothing, or ignores `variant`, never appears outside
its own tab, so it cannot draw its whole tab a second time. On another tab the section shows
nothing until the view and its data have loaded, and a failed asset load is left for the view's
own tab to report. The committee view declares `metrics` and shows the meeting's numbers there:
turns per seat (undelivered ones called out), delegations out of delivered owner turns, junior
edits applied or not by the master's re-check, floor latency in turns (reductions carry no
timestamps), and cumulative prose per turn, with signals-only and undelivered turns adding none,
and the 1:1s block described above.

**A turn renders only through `Segments`** (`playbooks/committee/view/src/Voice.tsx`), never as one
Markdown blob: Markdown passes an image's `src` through raw, so `images/x.svg` would resolve
against the SPA's path and an http src would make the operator's browser fetch it. Image syntax
is disarmed twice, by `view._segments` (every `![` in a text, caption or description gets a
U+200B after its `!`) and again in `Segments`, so a reference the scan missed never loads.
Captions and descriptions are plain text. `view._segments` makes at most 8 image and mermaid
segments (the rest of the body, from the line holding the ninth, is one text segment) and never
splits a body over 64 KB (it is one text segment), so one oversized answer costs neither the
request nor the browser. A file image is drawn only when the master checked it (`ok`), as an
`<img>` of `view/artifact?path=images/<name>&sha256=<the recorded hash>` (with `&token=` on a
remote bind); an unchecked one shows its caption, description and "image unavailable", and
requests nothing. A
mermaid block goes to the host's `HermesUI.renderMermaid` (`web/src/components/renderMermaid.ts`)
and is shown only as an `<img>` of a `blob:` URL, never as inline markup. It says "rendering
diagram…" while it draws, and shows its source as code when it fails (with `diagram failed to
render: <message>`) or when the shelf has no renderer. mermaid lives on the host shelf and is never
bundled into `committee.umd.js`.

The renderer runs mermaid with `securityLevel: 'strict'`, `htmlLabels: false` and
`suppressErrorRendering`, and its `secure` list stops a diagram's own directives from changing
those or setting `themeCSS`, `fontFamily` or `altFontFamily`. It rejects output that still holds
script, a `javascript:` URL, an event attribute or `foreignObject`, or that is not well-formed XML
(a diagram with a link), so the view shows the source instead of a broken image. A diagram's
`<style>` still applies to the page while it draws, so `web/index.html` sets
`Content-Security-Policy: img-src 'self' blob: data:`, and a classDef's `fill:url(...)` fetches
nothing.

A kept take that broke a rule is badged "broke the ground rules", a retaken one "retaken", one
with no pointer or no example says so, and one flagged `tells` is badged "AI tells", its tooltip
listing each kind found with its count; the expanded row reads `kept take k of n` and what it
broke. The Metrics section gains a Voice block listing every `voice.summary` figure, or "not
measured for this run" for a run reduced before voice. The verdict card says how many takes the
chair needed and what its kept ruling broke, and renders the ruling through `Segments` with
nothing drawn: a chair's file image is refused, and its mermaid block is shown as its source,
fenced, in a text segment, so a kept take 3 cannot draw a fake "accepted" tile above the real
buttons. The card finds its reduction among all of the run's reductions, not `?phase=decision`,
so a verdict kept under `decision-take2` is stamped through its own id. A run that ended `chair
retake failed` says so in attention tone. The document stepper does not use `Segments`: it stays
image-free, as above. A ticket's answer and a trace, which render a worker's raw text through the
host Markdown, disarm `![` the same way, so neither loads an image a worker named, and a diagram
that fails to draw leaves no element behind in the page.

The server must have the playbook registered, so the control-plane process needs
`HERMES_PLAYBOOK_MODULES=playbooks.committee` exactly as `hermes run` does. `make up` sets it (the
`PLAYBOOK_MODULES` variable); a server started by hand does not, and an unregistered playbook is a
404 on the view routes and `has_view: false` — no tab, no error.

Registered or not, the **Run tab's phase rail** lists every phase that minted tickets, in the
order it did — each turn included. A registered run at a declared phase also lists the declared
phases after it, so at `decision` the rail shows `ruling` ahead; a turn phase is not declared, so
mid-meeting nothing is listed ahead. A retake is its own phase there (`t02-owner-take2`,
`decision-take2`), undeclared like a turn. The turn-by-turn reading lives on the Playbook tab,
with names and prose attached.

**Runs created before the view renders as a legacy run, and says so.** `ended`, the artifact paths,
the per-turn `stance` and the turn body are all carried on the reductions, and a run reduced by an
older build has none of them. The view does not guess: the progress card says *"This run predates
the committee view: its reductions never recorded why the meeting ended, so the record does not
say"*, each persona reads *"stance not recorded — this run predates the signal"*, and the diff
panel says no artifact path was recorded rather than that no artifact exists. Re-running is the
only way to get the full surface for an old run.

**`HERMES_PLAYBOOK_VIEWS=0` turns the feature off entirely.** All three view routes 404 and
`has_view` is false on every run, so no tab appears and no view data is served. There is no partial
setting: half-disabled is a worse state than either end. `0`, `false`, `no` and `off` all turn it
off, case and surrounding space ignored. An empty value does not: `-e HERMES_PLAYBOOK_VIEWS` with
nothing behind it is a variable you did not set, and it reads as unset.

Set it if the control plane is bound anywhere but loopback. A playbook already runs Python in the
master process under the operator's account, so on a loopback bind its JavaScript running in the
operator's browser is the same trust one process over, not an escalation. Past loopback it is one:
anyone holding the read token now also executes playbook-authored JavaScript with the control
plane's origin. The asset is served `text/javascript` with `X-Content-Type-Options: nosniff`, and
its path comes from the registered playbook object rather than from the URL — the URL only names a
playbook, and an unregistered name 404s before anything touches the filesystem.

One consequence worth knowing rather than discovering. A `<script>` tag carries no `Authorization`
header, so the SPA passes the token on the asset URL and the tag stays in `document.head` for the
session. On a loopback bind that changes nothing — the server already puts the token on
`window.__HERMES_TOKEN__`. Past loopback the token is otherwise held in a module closure and never
written to the DOM, and this is the one thing that materialises it there, readable by any script on
the page including the playbook's own bundle. That bundle can then make write calls. It is inside
the trust already stated above, not beyond it, but it means "a playbook you trust to run Python in
the master" also means "a playbook you trust with the operator's API token".

## Limitations

- **Run it from a neutral directory.** `engine/transport.py` execs the worker with no `cwd=`, so a
  live worker inherits whatever directory `hermes run` was typed in — and the line above tells you
  to point `HERMES_REPO` at a real git repo, which is exactly where you will be standing. Every
  persona would then load that repo's `CLAUDE.md` as project context while reviewing an unrelated
  proposal. `cd` somewhere empty first; only `HERMES_COMMITTEE_ARTIFACT` and `HERMES_HOME` decide
  what the run reads and writes.
- **The site must be `local` or `fan-*`.** No site can push a file to a remote host, so on a remote
  worker the master's `thread.md` would not exist; `seed` refuses any other site, naming it.
- **Do not dispatch a committee run from a separate `hermes serve --host` process.** The floor
  queue and the cast live on the playbook instance in the master; the four methods the transport
  path calls (`payload_schema`, `driver`, `result_schema`, `verify`) would see an empty state dict
  in a second process. Use `hermes run`, which drives the loop in-process.
- **The verdict is a simulation, not an approval.** Nothing is ever shipped. The decision text
  says so itself, because thread.md and the Outputs tab show it before and regardless of any
  `hermes reduction accept|reject`.
- **The original artifact is never mutated.** Edits land in the revised copy; a run that delegated
  nothing leaves no revised copy, only `doc/00-original<ext>`.
- **The turn cap is literal.** At a low `HERMES_COMMITTEE_MAX_TURNS` the run stops mid-exchange —
  at `3`, on a reviewer's turn, with no owner reply after it — and goes straight to the decision.
  That is the cap working, not a lost turn.
- **The turn cap has no upper bound, but `hermes run` without `--wait` does.** Its loop stops
  after `max_cycles=1000` (`engine/cli.py`, `_drive`), so a `MAX_TURNS` in the high hundreds can
  exhaust the cycle budget mid-meeting, and the meeting cannot be resumed (below). Nothing rejects
  such a value; for a long meeting use `hermes run --wait`, which has no cycle limit.
- **A chair turn that produces no result ends the run `failed`**, as do a rejected verdict and a
  lost meeting (below). A committee that produced no decision did not finish, and fabricating a verdict
  would be worse; `thread.md` survives either way.
- **`--dry-run` deletes the run's state directory when it settles**, so the seeded header is not
  there to read afterwards.
- **A human rules at the end, never mid-run.** Nobody is asked anything while the committee talks.
  Once the verdict is written, the chair's ticket waits in `needs_human` with the run `running`:
  accept ends the run `done`, reject ends it `failed`. One artifact per run, one committee.
- **The meeting is not resumable; the ruling is.** The floor queue and the cast live in the
  master's memory, so a process lost mid-meeting cannot pick the meeting up again: a
  `hermes run resume <id> --wait` there records a `lost` reduction saying so and ends the run
  `failed`, with `thread.md` intact up to the last turn. Once the verdict
  waits, nothing in memory is needed: without `--wait`, `hermes run` returns and
  `hermes run resume <id> --wait` finishes the run after the ruling, reading it from the database.
- `MockAgent` cannot serve this playbook — it echoes the request payload back as the result — so
  exercising a whole run needs an agent double that actually talks.
- **A 1:1 is private by prompt only.** Workers run under `bypassPermissions`, so nothing but the
  goal stops a worker from reading a 1:1 file it is not in. The room reads only the outcome
  entries in thread.md.
- **1:1 state is not resumable either.** The plan, the pending pairs and the 1:1 in progress
  live in the master's memory beside the floor queue. A process lost mid-1:1 records `lost` and
  ends the run `failed`, and the view then shows no pause.
- **1:1s need a local site**, like the rest of the meeting: the 1:1 files live on the master,
  and remote sites are out of scope.

## Invariants

- `verify()` returns `True` unconditionally, and no turn's reduction carries
  `needs_human_ticket_ids`: a `needs_human` ticket mid-conversation blocks advancement for good.
  The re-check lives in `reduce` instead.
- **Only the kept decision reduction routes to review**, and only the chair's own ticket for the
  phase it was kept in (`<run>/decision` or `<run>/decision-take{k}`). A discarded take routes
  nothing. The decision is terminal and the verdict is written before the hold, so holding it
  blocks nothing but `done`. A chair turn that failed routes nothing, and neither does a chair
  retake that delivered nothing: there is nothing to rule on, and the run ends `failed`.
- A discarded take never reaches thread.md: the room reads only kept takes, and every take's
  metrics stay on its reduction. Its body is written only to `takes/`, for its own retake, and no
  route serves that folder.
- `reduce` never raises; file-IO failures ride on the reduction as `error`.
- No phase name and no ticket id repeats, and the highest turn never exceeds the cap.
- **The turn counter advances in `next_phase` and never in `reduce`.** Advanced in `reduce` it
  would stall on a turn that produced no finding and re-emit that phase name, which `_phase_reduced`
  (`engine/dispatch.py:311-321`) reads as "already reduced" — a deadlock with no error anywhere.
- **The four transport-path methods stay pure functions of their arguments.** `payload_schema`,
  `driver`, `result_schema` and `verify` may run in a worker process that never called `seed`, where
  `_state_by_run` is empty: no `self._state(run)`, no file IO, no parsing of the runtime phase name.
  Adding state to any of them breaks a split deployment silently rather than failing a test.
- Stdlib-only. Nothing is written outside the run's own directory under `$HERMES_HOME`.
- **Plan and 1:1 phases carry their own names.** `p01-owner` is minted at most once, and the
  `o{NN}-{role}` names are unique and strictly increasing (1, 2, 3, … with no gap), with NN never
  above the 1:1 budget and `one_on_one_used` never above it either. The test model's NN checks
  (`check_invariants`) skip `p01-owner` and every `oNN-*` name, their `-take{k}` forms included,
  and check oNN on their own.
- A 1:1 never sets run state. The run stays `running`, and no plan or 1:1 reduction carries
  `needs_human_ticket_ids`: only the decision reduction does.
- Every scheduled 1:1 either finishes or is listed once in `dropped_one_on_ones` as
  `meeting ended`, and every 1:1 has at most 4 member exchanges and at most one closing exchange.
  The turn cap never drops an edit delegated from a 1:1.
