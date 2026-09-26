# Spec: `committee` playbook — one artifact reviewed by a simulated committee

## Goal

Review one text file — a doc, an article, a source file — through a cast of AI personas with
distinct altitude, goals and ambitions, talking in a single thread where exactly one participant
holds the floor at a time. An **owner** persona answers every reviewer and delegates edits to a
junior IC; a chair closes with a verdict. One `hermes run` drives an opening round, a floor queue
and a decision phase, then holds the chair's verdict for a human to rule on: accept ends the run
`done`, reject ends it `failed`. It leaves a transcript, every version of the document under
`doc/`, and, where an edit was delegated, a revised copy.

## Phases

`phases = ["open", "decision", "ruling"]`; turn phases are minted at runtime as `t{NN:02d}-{role}`, NN from 01.

- **open** — zero tickets. `seed` resolves configuration, builds the cast, writes
  `doc/00-original<ext>` and then the thread header (charge, artifact path, roster), and returns
  `[]`. A failure to write either fails the run, so no header claims a meeting whose original was
  not kept. No worker runs.
- **t{NN}-{role}** — one ticket, one speaker: the opening round in seniority order, the owner's
  reply after every *delivered* reviewer turn, then whoever asked for the floor, FIFO. A turn whose
  worker produced nothing is answered by nobody — its thread entry is the `NO_TURN` stub, and
  sending the owner to reply to it yields a hallucinated answer or a burnt turn — so the next
  speaker after a failed turn is the next reviewer.
- **decision** — one ticket for the chair. Its ticket is held `needs_human` until a human rules.
- **ruling** — zero tickets, reached once the human has ruled. It exists so the engine hands
  `is_done` the decision's reduction (`run.reductions` carries only the prior phase): `done` iff
  the chair delivered a verdict and it was accepted.

One speaker per phase is a rule, not a habit: two would race for the thread file, and a repeated
phase name deadlocks the run silently. The review ends when the owner closes, the queue empties or
the cap is hit.

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

`senior_director` through `data_scientist` are the opening round, in that order; `owner` and
`junior_ic` join neither it nor the floor queue. The chair speaks twice — as the reviewer
`senior_director`, then as author of the decision under the sentinel role key `chair`. The cast
is not configurable.

## Configuration

Environment only. The charge comes from `--goals` (a file, one goal per line, joined); absent, it
is *Decide whether to approve this proposal.*

| Var | Default | Meaning |
|---|---|---|
| `HERMES_COMMITTEE_ARTIFACT` | — (**required**) | Absolute path to the file under review |
| `HERMES_COMMITTEE_MAX_TURNS` | `30` | Hard time-box on turn phases |
| `HERMES_COMMITTEE_DRIVER` | unset | Optional methodology slash command |

`ARTIFACT` and `MAX_TURNS` are read once, at `open` seed time, so a mid-run change cannot swap the
cap or the artifact; an `ARTIFACT` that is unset or is not an existing readable file fails the run
on the spot, naming the variable. A `MAX_TURNS` that does not parse — *and one below `1`, which
would mint a committee that never speaks* — falls back to `30`. `DRIVER` is read on every
`driver()` call, which may run in another process.

The charge is clipped to 400 characters (`cast.CHARGE_MAX`) with an ellipsis rather than cut
mid-word, a delegated `action` to 200 (`turnblock.ACTION_MAX`) and a `stance` to 200
(`turnblock.STANCE_MAX`); the assembled goal is asserted under 3600.

## The turn block

Every speaker answers in prose and ends with one fenced block:

````
```hermes-turn
request_floor: yes|no
delegate: yes|no          # owner turns only; the target is always junior_ic
action: <one line>        # required iff delegate is yes
close: yes|no             # owner turns only
stance: <one line>        # where you currently stand and why
```
````

Absent stays absent: a missing or malformed block means "said their piece, nothing further". The
gates are master-side. `delegate` and `close` count only from the `owner`, and `delegate: yes` with
no `action` is dropped whole. `request_floor` counts only from a reviewer, and never from a role
already queued or still to speak in the opening round. A delegation outranks `close` — the edit
still happens, and costs a turn — and the cap outranks both, naming in the decision any delegation
it drops.

`stance` is not a gate. It is free text, recorded on the turn's reduction and accumulated per
role so the committee tab can show where each persona currently stands. Absent stays absent: a
persona that states no stance is shown as having none, never as neutral. Only the owner and the
seven reviewers are issued a block, so the junior IC and the chair state no stance. It is the one
key asked for in prose rather than shown in the worked example `turnblock.instruction` hands a
speaker — a copied `stance: <one line>` would mint that placeholder as what the persona said, and
unlike a flag a stance is rendered back verbatim.

**The owner cannot close before the opening round drains.** A `close: yes` on a turn where any
reviewer has still to take its opening turn is recorded on the reduction and then discarded: the
owner is told so in its goal, and `_apply_block` enforces it. Without the gate the owner — whose
persona wants "a clear decision" and "concedes fast on small things" — can end a nine-persona
committee at turn 02, producing a two-turn transcript that reaches `done` looking healthy. The
owner may close again on any later turn.

## Where things land

Under `$HERMES_HOME` (default `~/.hermes`), mode 0700:

- `runs/<run_id>/thread.md` — the transcript, append-only: the `open` header, one
  `## turn NN — <name>, <title> (<role>)` entry per settled turn, then `## decision`. A turn whose
  worker failed still gets a stub — `_(no turn delivered — the worker failed; see hermes show)_`.
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

Every turn reduction also carries `answers_turn` (on an owner turn, the reviewer turn it answered)
and `delegated_by_turn` (on a junior-IC turn, the owner turn whose delegation it applied), and the
decision carries `dropped_delegation_turn`. All three are always written, null where they do not
apply, so an absent key marks a reduction from before they existed. The recorded `artifact` and
`revised` stay the master's absolute host paths; nothing that serves the view opens them.

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
on Original, under "Nothing said yet".

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
timestamps), and cumulative prose per turn, with signals-only and undelivered turns adding none.

The server must have the playbook registered, so the control-plane process needs
`HERMES_PLAYBOOK_MODULES=playbooks.committee` exactly as `hermes run` does. `make up` sets it (the
`PLAYBOOK_MODULES` variable); a server started by hand does not, and an unregistered playbook is a
404 on the view routes and `has_view: false` — no tab, no error.

Registered or not, the **Run tab's phase rail** lists every phase that minted tickets, in the
order it did — each turn included. A registered run at a declared phase also lists the declared
phases after it, so at `decision` the rail shows `ruling` ahead; a turn phase is not declared, so
mid-meeting nothing is listed ahead. The turn-by-turn reading lives on the Playbook tab, with names
and prose attached.

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
  accept ends the run `done`, reject ends it `failed`. One artifact per run, one cast.
- **The meeting is not resumable; the ruling is.** The floor queue and the cast live in the
  master's memory, so a process lost mid-meeting cannot pick the meeting up again: a
  `hermes run resume <id> --wait` there records a `lost` reduction saying so and ends the run
  `failed`, with `thread.md` intact up to the last turn. Once the verdict
  waits, nothing in memory is needed: without `--wait`, `hermes run` returns and
  `hermes run resume <id> --wait` finishes the run after the ruling, reading it from the database.
- `MockAgent` cannot serve this playbook — it echoes the request payload back as the result — so
  exercising a whole run needs an agent double that actually talks.

## Invariants

- `verify()` returns `True` unconditionally, and no turn's reduction carries
  `needs_human_ticket_ids`: a `needs_human` ticket mid-conversation blocks advancement for good.
  The re-check lives in `reduce` instead.
- **Only the decision reduction routes to review**, and only the chair's own ticket
  (`<run>/decision`). The decision is terminal and the verdict is written before the hold, so
  holding it blocks nothing but `done`. A chair turn that failed routes nothing: there is nothing to
  rule on, and the run ends `failed`.
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
