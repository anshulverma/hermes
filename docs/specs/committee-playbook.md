# Spec: `committee` playbook — one artifact reviewed by a simulated committee

## Goal

Review one text file — a doc, an article, a source file — through a cast of AI personas with
distinct altitude, goals and ambitions, talking in a single thread where exactly one participant
holds the floor at a time. An **owner** persona answers every reviewer and delegates edits to a
junior IC; a chair closes with a verdict. One `hermes run` drives an opening round, a floor queue
and a decision phase to `done` unattended, leaving a transcript and, where an edit was delegated,
a revised copy.

## Phases

`phases = ["open", "decision"]`; turn phases are minted at runtime as `t{NN:02d}-{role}`, NN from 01.

- **open** — zero tickets. `seed` resolves configuration, builds the cast, writes the thread header
  (charge, artifact path, roster) and returns `[]`. No worker runs.
- **t{NN}-{role}** — one ticket, one speaker: the opening round in seniority order, the owner's
  reply after every *delivered* reviewer turn, then whoever asked for the floor, FIFO. A turn whose
  worker produced nothing is answered by nobody — its thread entry is the `NO_TURN` stub, and
  sending the owner to reply to it yields a hallucinated answer or a burnt turn — so the next
  speaker after a failed turn is the next reviewer.
- **decision** — one ticket for the chair. Terminal.

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
mid-word, and a delegated `action` to 200 (`turnblock.ACTION_MAX`); the assembled goal is asserted
under 3600.

## The turn block

Every speaker answers in prose and ends with one fenced block:

````
```hermes-turn
request_floor: yes|no
delegate: yes|no          # owner turns only; the target is always junior_ic
action: <one line>        # required iff delegate is yes
close: yes|no             # owner turns only
```
````

Absent stays absent: a missing or malformed block means "said their piece, nothing further". The
gates are master-side. `delegate` and `close` count only from the `owner`, and `delegate: yes` with
no `action` is dropped whole. `request_floor` counts only from a reviewer, and never from a role
already queued or still to speak in the opening round. A delegation outranks `close` — the edit
still happens, and costs a turn — and the cap outranks both, naming in the decision any delegation
it drops.

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
  junior IC's first edit. After each junior-IC turn the master re-checks it — does it exist, did
  its SHA-256 move — and records `verified: true|false` on that turn's reduction, which the
  decision repeats when it failed.

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
`HERMES_REPO` at a real git repo containing
`--base-ref` (default `main`) even though the committee never touches a worktree — `crew.add`
provisions one and health-gates the host on `workspace_ready`, so a missing one fails host
admission before the first turn, with an error that says nothing about the committee.

## Limitations

- **The site must be `local` or `fan-*`.** No site can push a file to a remote host, so on a remote
  worker the master's `thread.md` would not exist; `seed` refuses any other site, naming it.
- **Do not dispatch a committee run from a separate `hermes serve --host` process.** The floor
  queue and the cast live on the playbook instance in the master; the four methods the transport
  path calls (`payload_schema`, `driver`, `result_schema`, `verify`) would see an empty state dict
  in a second process. Use `hermes run`, which drives the loop in-process.
- **The verdict is a simulation, not an approval.** Nothing is ever shipped. The decision text
  says so itself; `hermes reduction accept|reject` on it is an audit stamp, not a gate.
- **The original artifact is never mutated.** Edits land in the revised copy; a run that delegated
  nothing leaves no copy at all.
- **The turn cap is literal.** At a low `HERMES_COMMITTEE_MAX_TURNS` the run stops mid-exchange —
  at `3`, on a reviewer's turn, with no owner reply after it — and goes straight to the decision.
  That is the cap working, not a lost turn.
- **The turn cap has no upper bound, but `hermes run` does.** `master_loop` is called with
  `max_cycles=1000` (`engine/cli.py:451`), so a `MAX_TURNS` in the high hundreds can exhaust the
  cycle budget and leave the run `running` with no decision. Nothing rejects such a value; pick one
  the loop can actually reach.
- **A chair turn that produces no result ends the run `failed`** — the one deliberate non-`done`
  terminal state. A committee that produced no decision did not finish, and fabricating a verdict
  would be worse; `thread.md` survives either way.
- **`--dry-run` deletes the run's state directory when it settles**, so the seeded header is not
  there to read afterwards.
- A run is not resumable. One artifact per run, one cast, no human in the loop mid-run.
- `MockAgent` cannot serve this playbook — it echoes the request payload back as the result — so
  exercising a whole run needs an agent double that actually talks.

## Invariants

- `verify()` returns `True` unconditionally and no reduction carries `needs_human_ticket_ids`: a
  `needs_human` ticket would block advancement for good. The re-check lives in `reduce` instead.
- `reduce` never raises; file-IO failures ride on the reduction as `error`.
- No phase name and no ticket id repeats, and the highest turn never exceeds the cap.
- Stdlib-only. Nothing is written outside the run's own directory under `$HERMES_HOME`.
