# Spec: `committee-eval` — how good a finished committee review was

## Goal

Score one finished `committee` run on six dimensions, each backed by cited and verified evidence,
so that runs compare with each other and with the user's hand-scored anchors. It is the yardstick
for the committee feedback loops (voice, selection, one-on-ones). Its two baselines are run-9 in
`~/.hermes` and run-2 in `/data/users/anshulverma/committee-spin/home`. It never gates or feeds
the accept/reject ruling, never tunes a prompt, and writes nothing to the evaluated run except
its `eval.json`.

This is the design as built. The code is `playbooks/committee/eval.py` (the playbook and every
rule), `playbooks/committee/eval_cli.py` (the CLI), `playbooks/committee/voice.py` (the voice
rules and the one word counter) and `_evaluation` in `playbooks/committee/view.py` (the Metrics
tab). Where this doc and the code disagree, the code wins and this doc is the bug.

## How later loops score their live run

```bash
cd ~/workspace/hermes    # the checkout: playbooks/ is imported from here, not installed in .venv
export HERMES_HOME=$HOME/.hermes    # the control plane's home (its default)
.venv/bin/python -m playbooks.committee.eval_cli run <run-id>    # one judge ticket, then the score table
.venv/bin/python -m playbooks.committee.eval_cli compare         # every evaluated run in one table
```

Run them exactly so: from the hermes checkout, with `.venv/bin/python` (there is no bare
`python` on the user's PATH, and `playbooks` is not installed in the venv, so `-m` finds it only
from the checkout). `HERMES_HOME` must be the home the run lives in, which for a live run is the
control plane's home, `~/.hermes` (also the default when it is unset). Run ids are per home, so
the wrong home scores a different run, or none. For a run in another home, keep `HERMES_HOME` as
the eval home and add `--home <path>` to `run`; that home is read strictly read-only.

Only a finished run can be scored: one whose chair delivered a verdict. A meeting still in
progress, a run whose chair failed, a non-committee run, and a legacy run without its thread.md
are refused with the reason and exit 2 (see the target section). The ruling itself need not have
happened.

`run` does five things:
- It exits 2 with the reason, having created nothing, when the run is not evaluable.
- It sets `HERMES_COMMITTEE_EVAL_RUN` and `HERMES_COMMITTEE_EVAL_HOME`.
- It appends `playbooks.committee` to `HERMES_PLAYBOOK_MODULES`.
- It calls the engine CLI in-process with `run committee-eval --site local --wait`, so the eval
  run shows in the control plane like any other. The judge runs on `--agent A`, else `HERMES_AGENT`.
- It prints the eval run's id, its end state and its score table, and exits 0 when the eval run
  ended `done`, 1 otherwise.

`show <run-id>` prints one run's table again, and `anchor` records the user's own scores (see
the next section and CLI). The older spelling `.venv/bin/python -m playbooks.committee.eval <cmd>`
calls the same `main`, with runpy's warning on stderr, so it never exits 0 having done nothing.

## Calibrating the judge: the user's anchors

The judge's three scores read `uncalibrated` until the user has hand-scored at least two runs and
the judge lands within ±1 of each. The two baselines are those two runs. Nothing in the pipeline
writes an anchor or waits for one.

```bash
cd ~/workspace/hermes
export HERMES_HOME=$HOME/.hermes    # the eval home: run-9 lives here, and the ledger goes here
# 1. Read each transcript against the rubric below, then enter your own scores.
.venv/bin/python -m playbooks.committee.eval_cli anchor run-9 \
    verdict_grounded=<1-5> edits_address_concerns=<1-5> concern_coverage=<1-5> --rater <you> --note "<why>"
.venv/bin/python -m playbooks.committee.eval_cli anchor run-2 --home /data/users/anshulverma/committee-spin/home \
    verdict_grounded=<1-5> edits_address_concerns=<1-5> concern_coverage=<1-5> --rater <you>
# 2. Score both baselines. Each run is one live judge ticket, and prints the judge's scores.
.venv/bin/python -m playbooks.committee.eval_cli run run-9
.venv/bin/python -m playbooks.committee.eval_cli run run-2 --home /data/users/anshulverma/committee-spin/home
# 3. Read the judge against your scores.
.venv/bin/python -m playbooks.committee.eval_cli compare
```

- Enter a run's anchors before you see the judge's scores for it: before its `run` output,
  `show`, `compare` or its Metrics tab. Scores you have already seen pull your own toward them.
  An anchor needs only an evaluable run, not an eval, so step 1 can always come first.
- Give run-2's anchor the same `--home` its eval used. The anchor and the eval then share the
  target key (home realpath, run, `created_at`), which is how they are matched.
- `anchor` accepts any subset of the six ids. Only the three judge dimensions calibrate; an anchor
  on a deterministic one is recorded and shown in `compare`, and never calibrates anything.
- Both the evals and the anchors land in the eval home's `evals.jsonl` (`~/.hermes/evals.jsonl`).
  run-9's `eval.json` is `~/.hermes/runs/run-9/eval.json`. run-2's goes to
  `~/.hermes/evals/<8 hex>-run-2.json`, so the committee-spin home gets no write at all.
- In `compare`, each cell shows your score beside the judge's as `(a:N)`, and the closing
  `calibration` row labels each judge dimension `calibrated` (both baselines within ±1),
  `off (Δn)` (some target 2 or more apart), or `uncalibrated`.
- ±1 per target can pass a judge that cannot tell runs apart: one that gives your 3 and your 5
  both a 4. So under the calibration row, `compare` prints one note per pair of targets your
  anchors put 2 or more apart that the judge ties or reverses, for example
  `verdict_grounded: judge ties run-2 and run-9; your anchors differ by 2`.
- Re-anchoring a target replaces your earlier score at that version: the latest anchor line per
  (target, dimension, version) wins, in `compare` and in the calibration row.
- An anchor stays valid while its dimension's version is unchanged. When a later loop bumps a
  judge dimension, `compare` marks that dimension's cells `(re-score needed)` for the targets you
  anchored only at older versions. Re-read, re-anchor that dimension, and re-run the eval.

## Phases

`CommitteeEvalPlaybook` (name `committee-eval`) lives in `playbooks/committee/eval.py`.
`playbooks/committee/__init__.py` imports it after the committee playbook, so
`HERMES_PLAYBOOK_MODULES=playbooks.committee` registers both. It registers only when
`__name__ != "__main__"`. It has no instance state and no `view_asset`/`view_data`, so its runs
get the control plane's generic tabs. `phases = ["measure", "judge", "score"]`.

| phase | seed | reduce |
|---|---|---|
| measure | `[]` | Validates the target, snapshots the inputs, and computes the metrics, the flags and the three deterministic scores. Returns `Reduction(kind="eval_target")`. On failure it returns `{"target": {"home", "run"}, "error": <reason>}`; a failed validation has written nothing. |
| judge | One goal-only ticket, `<eval-run>/judge`, built from the `eval_target` reduction alone. `[]` when that reduction carries `error` or is malformed. | `[]` on an error target. Otherwise it re-hashes, scores against `inputs/` only, writes `eval.json` and one ledger line, and returns `Reduction(kind="eval")`, never with `needs_human_ticket_ids`. |
| score | `[]` | `[]` |

- **A bad target ends the run `failed`; it never strands it.** `cmd_run` seeds phase 0 right
  after it creates the run, and it only logs a seed exception, which would leave the run
  `running`. So measure's `seed` does nothing, and validation lives in its `reduce`. judge's
  `seed` likewise returns `[]`, never raises, on a malformed `eval_target`.
- **No reduce ever raises.** measure's catches everything as the error
  `measure failed: <Type>: <message>`. judge's turns an internal error into a failed eval
  (`judge reduce: <Type>: <message>`) rebuilt from the `eval_target`: the judge dimensions null,
  the deterministic half and measure's flags kept. That eval.json and ledger line are each tried
  once, on their own, so a failed ledger write never leaves an `ok` eval.json behind.
- **`next_phase` is a static map**: measure→judge→score→None. It is handed the run with the
  prior phase's reductions, so it cannot see the phase it is leaving. `is_done` reads the judge's
  reduction from the zero-ticket `score` sentinel, the committee's `ruling` trick. It is true when
  `run.phase == "score"` and some `eval` reduction has `judge.status == "ok"`, and it never raises
  on a malformed reduction.
- **`verify()` returns True.** A False would park the judge ticket in `needs_human` and block
  the run. The no-trust checks live in judge.reduce instead.
- **The environment is read once**, in measure.reduce. Everything a later phase needs rides on a
  reduction or on a digest-pinned file under `runs/<eval-run>/inputs/`. So
  `HERMES_PLAYBOOK_MODULES=playbooks.committee .venv/bin/python -m engine.cli run resume <eval-run> --wait`
  works in a fresh process, with the one exception under Edge cases.
- **`--dry-run` leaves nothing.** It seeds phase 0 only, measure's seed writes nothing, the run
  settles `stopped`, and the engine removes `runs/<eval-run>/`.
- **The site must be `local` or `fan-*`**, because the judge reads files under the eval home on
  the master. Any other site is the error `site must be local or fan-*: <name>`, checked before
  the target.
- The driver is goal-only: `Driver(command=None, args={}, loop=None)`. The ticket's
  `resource_req` is `cpu`.

## The target: a source home and a run id, read strictly read-only

- **Eval home** = `os.path.realpath(config.resolve_home())`. The eval run and everything it
  creates live there: tickets, attempts, events, traces, `inputs/` and the ledger.
- **Source home** = the realpath of `HERMES_COMMITTEE_EVAL_HOME`, defaulting to the eval home.
  - Its `queue.db` is opened only through `connect_ro`:
    `sqlite3.connect("file:" + urllib.parse.quote(f"{home}/queue.db") + "?mode=ro", uri=True)`.
  - Its files are read only through plain `Path` joins and `thread.read_regular`, which uses
    `O_NOFOLLOW` and returns regular files only.
  - These are never called on it, because each one creates files or resolves the eval home:
    `migrate.connect`, `thread.path`, `thread.revised_path`, `thread.run_file`,
    `config.state_dir` and `engine.trace.trace_path`.
- **Evaluable** means `validate_target(home, run_id)` returns None: `queue.db` is a regular file
  (it is never created) that SQLite can read; the id matches `^[A-Za-z0-9][A-Za-z0-9._-]*$`; the
  run exists with `playbook == "committee"`; its latest `decision` reduction by id has `delivered`
  true; and a legacy run still has its `thread.md`. Otherwise it returns exactly one of these,
  checked in this order (an SQLite error at any step is the `unreadable` one):
  `HERMES_COMMITTEE_EVAL_RUN is not set`, `no queue.db in <home>`, `bad run id: <id>`,
  `run not found: <id>`, `not a committee run: <id> (<playbook>)`,
  `queue.db unreadable in <home>: <sqlite error>`, `no delivered decision: <id>`,
  `legacy run without thread.md`. It never raises.
- `runs.state` and `review_state` never gate. run-2 is `done` at phase `decision` with its ruling
  pending, and a run awaiting its ruling is `running`. `review_state` is reported.
- **Legacy** means any `turn` reduction lacks `body` (run-2 is one). A legacy run needs its
  `thread.md`.
- A read-only open of a WAL database may create an empty `queue.db-wal` and a `queue.db-shm`
  beside the source's `queue.db`. `queue.db` itself and the run's files stay byte-identical.

## Reading the run

`load_target(home, run_id)` builds a `Target`. It never raises on malformed reduction JSON, and
every file it decodes is read as `utf-8` with `errors="replace"`. The precedence is reduction
fields first, then `thread.md`, then the fixed layout.

- **Turns.** The `turn` reductions with an int `turn`, keyed by that value; the last one by id per
  number wins. `take` reductions and the losing duplicates count in `metrics.extra_takes`. Every
  other kind except `decision` counts in `metrics.other_kinds` (`lost` now; later `selection`,
  `one_on_one_plan`, `one_on_one`) and never raises.
- **Bodies** (`body(target, n)`). The reduction's `body`. A legacy run uses its thread entry.
- **thread.md** (`parse_thread(text)`).
  - The header is every line before the first line matching `^## `.
  - Entry boundaries match only `^## turn (\d{2,}) — (.+) \((\w+)\)$` and `^## decision — .+$`.
    After the first boundary every other line is body, including `## ` headings.
  - Lines after the header and before the first entry belong to no entry, so they are never
    header or body evidence. Examples are selection's `## selection N: …` and
    `## committee seated`, and one-on-ones' `## 1:1 …`.
  - Lines are 1-based and inclusive, and only `"\n"` ends one: a CRLF counts once, and
    `str.splitlines` is never used, because it also splits at a form feed, U+0085 or U+2028 and
    would shift every later line number. An entry runs from its `## ` heading to the line before
    the next boundary.
- **Header labels** match `^(?:\*\*)?(Charge|Artifact|Committee):(?:\*\*)?\s*(.*)$`, so bold and
  plain labels parse alike.
- **Roster** (`roster(target)`).
  - It is built from the `^- (\w+) — (.+)$` items of the `Committee:` block, first per slug, with
    blank lines skipped. The block ends at the first non-blank line that is not a `- ` item, so
    `Seat library:` seats nobody.
  - That list is unioned with the roles on turn reductions, in first-appearance order.
  - `reviewers(target)` is the roster minus `cast.OWNER` and `cast.JUNIOR`.
  - eval.py never imports `cast.CAST`, `cast.SENIORITY` or `cast.persona`, and never assumes the
    nine-seat cast or the tNN alternation.
- **Chair prose** (`chair_prose(decision)`). The decision's `body` when present. Otherwise its
  `verdict`, minus every line matching `^- (re-check of |dropped_)` and minus the
  `playbook._SIMULATION` paragraph. That strip removes the footer `_reduce_decision` appends,
  whose APPLIED lines would otherwise satisfy any count check. Consistency checks, and the
  judge's view of the verdict, use chair prose only.
- **Artifact path A.** The latest non-empty `artifact` on any reduction (a relative path resolves
  against the source home), else the header's `Artifact:` value.
- **Original.** `runs/<id>/` joined with `thread.snapshot_key(A, None)` when that is a regular
  file (`original_source: "snapshot"`). Otherwise it is A itself (`"live"`), which may have
  drifted since the run, and that cannot be checked.
- **Revised.** `runs/<id>/revised/<basename(A)>`, rebuilt from the home. The recorded host path
  is never used.
- **ended.** The decision's `ended`. Otherwise `owner closed` when the latest delivered owner turn
  has `close` true, else `unknown`.
- **Per-edit diffs.**
  - Steps are the junior_ic turns in ascending `turn`. Step N's file is `runs/<id>/` joined with
    `thread.snapshot_key(A, N)`. Its predecessor is the previous step's file, or the original
    snapshot for the first step.
  - `changed(before, after)` runs `difflib.unified_diff(a, b, n=0)` over the utf-8 lines with
    their endings kept (`splitlines(keepends=True)`) and skips the two file-header lines.
    `lines_added` counts the lines starting `+`, and `lines_removed` the lines starting `-`.
    Because endings are kept, adding a missing final newline counts: `changed(b"a", b"a\n")` is
    `(1, 1)`, where doc-diff's backfill script (which strips endings) counts `(0, 0)`.
  - A step whose file or predecessor is unreadable gets null counts.
  - `per_edit` is `snapshot` when every step has counts, and `partial` when some are null. It is
    `unavailable` with `steps: []` when there is no original snapshot (run-2).
  - `edits.total` counts original→revised, and is null when either is missing.
  - The eval never replays traces and never imports `replay.py`. Replay sees only Edit tool
    calls, and run-2 has no recorded git rev.
- **Answered reviewer turns** (`unanswered_reviewer_turns(target)`).
  - When the owner turns carry doc-diff's `answers_turn` key (present, even as null, means
    recorded), a delivered reviewer turn N is answered iff a delivered owner turn has
    `answers_turn == N`.
  - Otherwise it is answered iff the first later turn whose role is not junior_ic is a delivered
    owner turn.
  - The rule is order-based, never N-1 arithmetic.
- **The prose population P** (`_prose_population`) is the delivered turns whose role is not
  junior_ic, minus any turn whose reduction says `voice: null` (voice's undelivered or
  signals-only take). The reviewer/owner median and the voice shares both read P, so they always
  count the same turns.
- **Attempts.** `SELECT a.id, a.started_at, a.ended_at, a.outcome FROM attempts a JOIN tickets t
  ON a.ticket_id=t.id WHERE t.run_id=? ORDER BY a.id`.
- **Traces.** `runs/<id>/traces/<attempt id>.jsonl`, read in ascending attempt id.

## Metrics and flags

`compute_metrics(target)` returns the keys below. `measure_target(home, run_id)` bundles the
target, the metrics, the flags and the deterministic scores. Pins are exact, with no tolerance:
`test_run9_metrics_pinned` and `test_run2_legacy_metrics_pinned` in
`tests/unit/test_committee_eval.py` assert the whole dict on the fixtures under
`tests/data/committee-eval/`. run-2's values come from its thread.md, because it is legacy.

| key | rule | run-9 | run-2 |
|---|---|---|---|
| `turns` / `turns_by_role` | distinct `turn` values / `{role: n}` | 24 / owner 8, junior_ic 8, senior_director 2, the six other reviewers 1 each | 20 / owner 7, junior_ic 6, the seven reviewers 1 each |
| `undelivered_turns` | delivered false | 0 | 0 |
| `owner_turns_delivered` / `delegations` | delegations = delivered owner turns with `delegate` and an action | 8 / 8 | 7 / 6 |
| `rechecks` / `rechecks_verified` | decision `rechecks` / those with verified true | 8 / 8 | 6 / 6 |
| `floor_requests` | `[{turn, role}]` for every turn with `request_floor`, delivered or not | `[{1, senior_director}]` | `[]` |
| `errors` | turn and decision reductions with a non-null `error` | 0 | 0 |
| `ended` / `cap` / `artifact_intact` | as above / the cap of the latest turn that records one, or null / the decision's field | queue empty / 30 / true | owner closed / null / true |
| `dropped` | `{delegation, floor_requests}` | null, [] | null, [] |
| `seats` | `{roster, reviewers, spoken, unheard}` in roster order; spoken = reviewers with a delivered turn | unheard [] | unheard [] |
| `unanswered_reviewer_turns` | as above | [] | [] |
| `outside_room_mentions` | `[{line, quote}]` for lines in turn or decision entries matching `OUTSIDE_ROOM`, `(?i)\b(outside\|not in) this room\b`; without thread.md, bodies and chair prose with line null | lines 29, 37, 253, 309 | lines 43, 315 |
| `words` | `{prose_total, median_reviewer_owner, chair_entry, chair_prose}`. prose_total = every delivered body plus the full decision entry. The median is a float over P, null when P is empty. | 15498 / 825.0 / 1862 / 1518 | 21728 / 1393.5 / 2202 / 1934 |
| `voice` | `{n, pointer_share, walls_share, example_share, filler_per_turn}` over P (see voice.py) | 16 / 0.9375 / 0.625 / 0.875 / 0.0 | 14 / 0.9286 / 0.7143 / 1.0 / 0.0 |
| `bytes` | `{original, revised}` | 11397 / 14931 | 11397 / 19100 |
| `edits` | `{per_edit, steps: [{turn, lines_added, lines_removed}], total}` | snapshot; t03 +7/−2, t06 +13/−6, t09 +27/−0, t12 +8/−2, t15 +18/−11, t18 +6/−5, t21 +4/−2, t24 +17/−13; total +87/−28 | unavailable; []; total +208/−88 |
| `time` | every attempt on the run's tickets: `{summed_attempt_s, wall_clock_s, unmeasured}`, rounded to 0.1 s | 3284.0 / 3619.0 / 0 | 3279.4 / 3516.0 / 0 |
| `cost_usd` | the sum of each trace's cost, 4 dp; null unless every attempt has a trace with a known cost | 30.3875 | null |
| `tokens` | `{input, output, cache_creation, cache_read}` | 502 / 287400 / 4378394 / 13727431 | 214 / 183920 / 1768249 / 6785620 |
| `tokens_source` | `modelUsage`, `transcript`, `mixed`, or null when no trace was found | modelUsage | transcript |
| `traces` | `{expected, found, with_cost}`; expected = the attempt count | 25 / 25 / 25 | 21 / 21 / 0 |
| `other_kinds` / `extra_takes` | as above | {} / 0 | {} / 0 |

**Time.** An attempt is unmeasured when it lacks a numeric `started_at` or `ended_at`, or when it
did not end `ok` and has `ended_at == started_at`: that is how the engine records a timeout or a
contract failure, after running for an unknown time. `unmeasured` counts them. Any unmeasured
attempt, or no attempt at all, makes both times null, never a partial sum that would let a failing
run look cheaper.

**Cost and tokens.** `trace_totals(traces)` serves both the metrics and judge.reduce. It takes one
entry per expected trace (None for a trace that does not exist).
- A cost-state line is a JSON object with `type == "cost-state"`. The last one per trace decides
  that trace's cost: its numeric top-level `totalCostUSD`, or no cost when it has
  `hasUnknownModelCost: true`.
- Tokens come from that trace's last cost-state `modelUsage`, summed over models:
  input←`inputTokens`, output←`outputTokens`, cache_creation←`cacheCreationInputTokens` and
  cache_read←`cacheReadInputTokens`. These are Claude Code's own totals, which match
  `totalCostUSD`.
- A trace with no `modelUsage` (legacy run-2) falls back to its transcript: `type == "assistant"`
  lines at `message.id` and `message.usage`, the last line per `message.id` winning, with
  input←`input_tokens`, output←`output_tokens`, cache_creation←`cache_creation_input_tokens` and
  cache_read←`cache_read_input_tokens`. This undercounts cache creation, which is why it is only
  the fallback. `tokens_source` says which one each run used.
- A missing key counts 0, a non-JSON line is skipped, and `tokens` is null when no trace was
  found.
- Costs and token counts fail closed. A `totalCostUSD` that is NaN, infinite or negative (JSON
  `NaN` and `-Infinity` parse in Python) means that trace has no cost, so it can never make the
  bill look smaller. Such a token count counts 0, so no NaN reaches a reduction or eval.json.
  judge.reduce's own cost goes through the same rule.

**Flags** (`compute_flags(target, metrics)`) are computed by measure only, so the judge can
neither add nor remove one. Each flag is `{id, turn, line, quote}`. They are ordered by this list,
then by turn, then by line (nulls last), and every `line` is null when thread.md is missing.
- `delegation_truncated_but_applied`: a junior_ic turn whose body has a line matching
  `TRUNCATION` while its `verified` is true. `TRUNCATION` is
  `(?i)\b(message|delegation|action|request|instruction)s?\b.{0,40}\b(cut off|truncated|stopped at)\b`,
  so it catches a cut-off message, never a domain phrase such as "cut off from the root".
  - `line` is the first thread.md line inside that turn's entry that matches.
  - `quote` is that stripped line, clipped to 300.
  - It is report-only, never scored. The claim that the edit applied is the re-check footer's,
    never the chair's (chair prose strips the footer), so verdict_consistency does not count it.
    The judge reads it in `metrics.json` for edits_address_concerns.
  - run-9 has it at t06, t09, t15 and t18, on lines 130, 244, 424 and 519.
- `action_clipped`: a decision re-check whose delegating owner turn has
  `voice.action_chars > turnblock.ACTION_MAX` (200). When that owner turn has no `voice` dict, the
  test is `len(action) >= ACTION_MAX` instead.
  - The delegating owner turn is the junior's `delegated_by_turn`, else the nearest earlier
    delivered owner turn with `delegate`.
  - `turn` is the re-check's turn. `quote` is the action's last 40 chars. `line` is the decision
    entry's line starting `- re-check of turn NN`, else null.
  - It is report-only, never scored. run-9 has it at t03, t06, t09, t15, t18 and t24 (lines 861
    to 875), and run-2 at t03 to t18 (lines 966 to 976).
- `verdict_count_mismatch`: each claim `edit_claims` finds in chair prose, line by line, whose
  number differs from `rechecks_verified`. It adds `{claimed, recorded}`, and a claim equal to the
  record adds nothing.
  - A claim is a match of `EDIT_CLAIM`, `(?i)\b(<number>) edits? (landed|applied|were made)\b`.
  - Right after "N of (the|these|all)" the claim is N, the number before "of", so "Seven of the
    eight edits landed" claims seven. "of …" with no number before it claims nothing. Only the
    64 characters before the claim are searched for that "of", so a line of repeated claims stays
    linear.
  - A match followed by "(only) partially", "partly" or "in part" claims nothing.
  - A number is digits or a `NUMBER_WORDS` entry: one through twenty, twenty-one through
    twenty-nine (hyphen or space), and thirty. The longest alternative is tried first.
  - `turn` is null, and `line` is the decision-entry line that contains the chair-prose line.
  - run-9 has one: `{claimed 7, recorded 8, line 820}`, on "Seven edits landed".
- `thread_missing`: a non-legacy run with no thread.md. `quote` is `""`, and the roster comes from
  the turn roles.

`target_changed_during_eval` is not a measure flag. judge.reduce appends it to eval.json's `flags`
only.

## Rubric

| id | scorer | rule |
|---|---|---|
| `verdict_grounded` | judge | 1-5 per `rubric.md` |
| `edits_address_concerns` | judge | 1-5 per `rubric.md` |
| `concern_coverage` | judge, capped | The judge's score, capped at 3 by `concern_cap` unless `seats.unheard` and `unanswered_reviewer_turns` are both empty lists. Missing or malformed metrics cap too, because unknown is never "all heard". |
| `efficiency` | deterministic | Start at 5 and subtract 1 for each of: `cost_usd` unknown or `> 20`; `summed_attempt_s` unknown or `> 3000`; `turns >= cap` (meeting turns only, skipped when cap is null); any dropped delegation or floor request. Floor 1. An unknown cost or time fails its check, so a run that hides its bill never scores better. |
| `concision` | deterministic | Band on `words.median_reviewer_owner`: ≤150→5, ≤300→4, ≤500→3, ≤800→2, else 1. Then subtract 1 for each of: `walls_share > 0.25`; `pointer_share < 0.5`; `example_share < 0.5`; `filler_per_turn > 1`. A null share never subtracts. Floor 1. A null median (P is empty) makes the score null with the error `no measured reviewer/owner prose`. |
| `verdict_consistency` | deterministic | 5 − 2 × `verdict_count_mismatch` flags. Floor 1. Only the chair's own claims count; `delegation_truncated_but_applied` is report-only. |

- `JUDGE_DIMS` and `DETERMINISTIC_DIMS` split the six ids in this order.
- The baselines (`test_deterministic_scores_pinned`): efficiency, concision and
  verdict_consistency are 3, 1 and 3 for run-9, and 3, 1 and 5 for run-2. run-2's efficiency loses
  a point for its unknown cost (it has no cost-state line). run-9's verdict_consistency loses two
  points for "Seven edits landed" against eight verified re-checks.
- **Judge anchors.** The `RUBRIC` constant holds them, and `rubric.md` gets it verbatim:

  ```text
  verdict_grounded
  5: every claim in the chair prose traces to a turn or to the document, and the verdict follows from the arguments.
  3: mostly grounded, with some unsupported claims.
  1: asserts things nobody said, or contradicts the thread.

  edits_address_concerns
  5: each edit does what its delegation asked and resolves the concern behind it.
  3: some edits resolve their concern, others only partly.
  1: cosmetic or unrelated edits, or edits that leave the concern unresolved.
  Read the per-edit snapshots under inputs/doc/ when present; cite the delegating owner turn, the junior_ic report, or the edited text itself (`where:"original"|"revised"`, C3).

  concern_coverage
  5: every seated member's main concerns were answered by the owner or by an edit, and the thread names no needed stakeholder missing from the room.
  1: major concerns went unanswered, or a missing function is named repeatedly.
  Concerns come from each member's own turns, never from persona config. The judge also gets `seats`, `unanswered_reviewer_turns` and `outside_room_mentions`.

  Evidence: every quote is verbatim and contiguous from the place it cites (no ellipses, no paraphrase).
  ```

  - The text is pinned: `test_voice_measure_and_version` asserts the first 8 hex of its sha256
    (`96377104`). An edit fails that test until the affected judge dimension's `@n` is bumped and
    the hash re-pinned. The same change updates the block above and this hash.
  - The planning spec's closing sentence ("The run-9 baseline for absent stakeholders includes at
    least Security and on-call/SRE.") is left out of `RUBRIC` on purpose (G13): it is an
    acceptance note about one run, and giving it to the judge would bias concern_coverage on every
    other run. The same test asserts neither "Security" nor "run-9" appears in it.
- **Deterministic evidence** (`score_deterministic(metrics, flags)`).
  - efficiency and concision carry one evidence item per input their rule reads, in the table's
    order:
    `{turn: null, where: "metric", line: null, quote: "<dotted key>=<json.dumps(value)>", verified: true}`,
    for example `"words.median_reviewer_owner=825.0"`. efficiency reads `cost_usd`,
    `time.summed_attempt_s`, `turns`, `cap`, `dropped.delegation` and `dropped.floor_requests`;
    concision reads `words.median_reviewer_owner` and the four `voice` shares.
  - verdict_consistency carries its `verdict_count_mismatch` flags (`where: "decision"`), each
    with its turn, line and quote. So `show` and the view's verdict_consistency row quote the
    chair's contradicting sentence; the headline does too when verdict_consistency is the unique
    weakest dimension (ties go to table order, where it is last). Only when no flag counts is its
    evidence the single metric item `rechecks_verified=<n>`.
  - `rationale` is `"; ".join` of the steps applied, for example
    `"start 5; cost_usd 30.3875 > 20: -1; summed_attempt_s 3284.0 > 3000: -1"` (an unknown input
    reads `cost_usd unknown: -1`, and a drop reads `dropped delegation: -1`). concision starts
    `"start 1 (median_reviewer_owner 825.0 > 800)"`. It ends `"; floor 1"` when the floor bit.
- **Versions.**
  - `DIMENSIONS` maps each id to an explicit `"<id>@<n>"`. Today `edits_address_concerns@2` and
    `verdict_consistency@2`, the rest `@1`. edits_address_concerns@2 rewrote anchors 3 and 1,
    which both said "partial" at @1. verdict_consistency@2 counts only the chair's claims; @1
    also took up to 2 points for `delegation_truncated_but_applied` flags (run-9 scored 1).
  - `dimension_versions(rules=RULES)` returns `DIMENSIONS` with concision suffixed
    `"+" + sha256("\n".join(rules).encode()).hexdigest()[:8]`. So a rules swap can never silently
    compare.
  - `rubric_version(versions)` is
    `"r" + sha256(json.dumps(versions, sort_keys=True).encode()).hexdigest()[:8]`.
  - eval.json and every ledger line carry both.
  - The bands are defaults, and any change to one bumps that dimension's version.
  - An anchor stays valid while its dimension's version is unchanged, so a voice swap keeps the
    user's judge-dimension anchors.

## The judge and the no-trust checks

- **Snapshot** (`write_inputs`). measure copies the inputs into
  `<eval home>/runs/<eval-run>/inputs/`:
  - `thread.md` when present, and `entries.json`;
  - `original<ext>` and `revised<ext>` when present, where `<ext>` is
    `Path(thread.snapshot_key(A, None)).suffix`;
  - `doc/<snapshot names>` for every readable step;
  - `metrics.json` and `rubric.md`.

  Every file is mode 0600, written without following a symlink, and directories are made only by
  `config.state_dir` in the eval home. `digests` records each source file's sha256, and
  `inputs_digests` records the sha256 of every file written under `inputs/`.
  - `inputs/thread.md` is the exact bytes `load_target` read and measured, never a re-read, so it
    cannot differ from what the metrics describe.
  - `entries.json` (`build_entries`) is
    `{header: {text, line_start, line_end}, turns: {"<n>": {role, body, line_start, line_end}}, decision: {chair_prose, line_start, line_end}}`.
    With no thread.md it is built from the reductions, with every line null and `header.text`
    set to `""`.
  - `metrics.json` is byte-identical to the deterministic block (see Results).
  - `rubric.md` (`rubric_text`): line 1 is `rubric_version: <version>`. Then comes one
    `<id>: <dimension version>` line per dimension, a blank line, and `RUBRIC` verbatim.
- **Why a snapshot.** The judge runs `claude -p "/goal …" --permission-mode bypassPermissions`,
  so "read only" in its goal is not a guarantee. It could edit a source, or edit a copy to forge
  a verified quote.
- **Goal** (`judge_goal`). It is at most `cast.GOAL_MAX` (3600) for an inputs directory of up to
  300 chars, and holds, in order:
  - the role line;
  - the inputs directory, once, then the files present (an absent original or revised copy is
    called unavailable, and with no revised copy the judge is told to judge the edits from the
    delegations and the junior_ic reports);
  - "This is read only: write, edit or create nothing.";
  - the quote rule, `VERBATIM` ("every quote is verbatim and contiguous from the place it cites
    (no ellipses, no paraphrase)"), plus that a `decision` quote comes from the chair's prose,
    never from the re-check lines under it;
  - the output contract.

  The rubric is never inlined; the goal tells the judge to read `rubric.md` first.
- **Output contract.**
  - The payload schema requires exactly `role`, `title`, `goal` and `kind`, with
    `additionalProperties: false` and `kind: "judge"`. The ticket sets `role: "judge"`.
  - The result schema is `{answer: string}` with `additionalProperties: true`. The contract
    validator has no integer type, so 1-5 cannot live in the schema, and a contract failure is
    terminal.
  - The answer ends with a `hermes-eval` fenced block of JSON. A fence opens on a line holding
    only ```` ```hermes-eval ```` and closes on a line holding only ```` ``` ````, so a
    ```` ``` ```` inside a JSON string can never close it early and hand the win to a block
    echoed from the transcript.
  - Each judge dimension is `{score, rationale, evidence: [{turn, where, quote}]}`, with at most
    5 evidence items, each quote at most 300 characters and the rationale at most 4000.
    concern_coverage may add `concerns` and `absent_stakeholders`, which go under its `detail`.
  - `where` is one of turn, decision, header, original or revised. Unknown keys are ignored.
  - `parse_answer` takes the last fence whose body parses as a JSON object, so a restated answer
    wins and a broken last fence falls back to the one before it. The fences are found in one
    pass over the answer's lines (an opener line, then the next bare ```` ``` ```` line), so an
    answer that repeats an opener line thousands of times stays linear.
- **judge.reduce** reads only the eval_target reduction, `inputs/` and the eval run's own traces,
  plus, read-only for the re-hash, the target's sources, rows and run-directory listing. In order:
  1. **Re-hash.**
     - Every path in `digests` and `inputs_digests` is read through `thread.read_regular`
       (`O_NOFOLLOW|O_NONBLOCK`). A file that has gone, or is now a symlink (even to identical
       bytes), a FIFO or a directory, counts as changed, and a FIFO never blocks the reduce.
     - `target_state(home, run)` is recomputed and compared with the eval_target's. Its `rows` is
       a sha256 over the target's rows read over `mode=ro`: `runs.created_at`, each reduction's
       `(id, kind, json)` and its attempts. `review_state` is left out, so a ruling during the
       eval is no change. Its `files` is a sha256 over a listing of `runs/<run>/` (relative name,
       file type, and size for anything but a directory), minus `eval.json` and its `.eval.json.*`
       temp files. A changed `rows` names `<home>/queue.db`, and a changed `files` names
       `<home>/runs/<run>`.
     - Any change appends
       `{id: "target_changed_during_eval", turn: null, line: null, quote: "", paths: [...]}`, and
       the answer is never even parsed, so a quote planted in an `inputs/` copy is never read.
  2. **Parse** the last non-empty `answer` among the findings with `parse_answer`.
  3. **Score** (`score_judge`). It reads each `inputs/` file a quote may cite (entries.json,
     thread.md, the original and revised copies) once, and a file whose sha256 is not the one
     `inputs_digests` records reads as absent. Per judge dimension:
     - absent from the answer: null, `missing from the answer`; no parseable fence at all: null,
       `no parseable hermes-eval fence`.
     - At most 5 evidence items are read (`EVIDENCE_MAX`); extras are dropped and not counted.
       A malformed item (not an object, an unknown `where`, a non-string quote, a turn that is
       neither an int nor null) is dropped and counted in `judge.evidence_rejected`.
     - A quote is clipped to 300 chars (`QUOTE_MAX`) and its whitespace collapsed. It is
       `verified` iff it has at least 3 words (counted by `words`) and 12 characters, and is a
       substring, whitespace collapsed on both sides, of the place it cites in entries.json: the
       turn's body (matched by `turn`), `chair_prose`, or `header.text`. For original and revised
       it must be a substring of the whole inputs copy. A shorter quote such as "." or "e" would
       match anything, so it never verifies.
     - `line` is the line the quote starts on, in inputs/thread.md within the entry's range, or
       in the original or revised copy. The range's lines are collapsed and joined with single
       spaces, and the quote's offset in that text maps back to its line, so a quote that crosses
       a hard wrap still gets one. When the whole quote is not in thread.md (it verified against
       entries.json), its first 40 characters are looked for, and failing that it is
       `line_start`. It is null without thread.md or when unverified.
     - Unverified items stay, with `verified: false`, and count in `judge.evidence_rejected`.
     - The score counts only when it is an int 1-5 (`isinstance(v, int) and not
       isinstance(v, bool) and 1 <= v <= 5`; 4.0, "4" and true are not scores) AND at least one of
       its quotes verified. Otherwise it is null with `score is not an integer 1-5` (checked
       first) or `no verifiable evidence`.
     - A rationale is clipped to 4000 chars (`RATIONALE_MAX`), ending `…` when cut. The output
       contract tells the judge that limit.
     - concern_coverage gets `concern_cap`, and a capped score records `detail.capped_from`. Its
       `detail` is `{concerns: [{member, concern, raised_turn, answered_turn}],
       absent_stakeholders: [{who, turn, quote, line, verified}]}`: object items only, at most 20
       of each (`DETAIL_MAX`), texts clipped to 300, turns an int or null. An absent
       stakeholder's quote is verified against its turn like evidence, but it is never evidence:
       it neither scores nor counts as rejected.
  4. **Status.**
     - `failed` when the target changed (error `target changed during eval: <paths>`) or there is
       no finding (`the judge returned no result (driver_failed or timeout)`; terminal, no
       retry). A failed status nulls every judge score with that error.
     - `unparseable` when no fence parses (`no parseable hermes-eval fence`).
     - `partial` when some judge dimension is null, with the error `<id>: <error>; …`.
     - `ok` when all three are scored.
  5. **Judge cost and tokens** come from `trace_totals` over
     `<eval home>/runs/<eval-run>/traces/*.jsonl`; `cost_usd` is null when no trace was found.
  6. Write eval.json, append one ledger line, and return the `eval` reduction.
- **Failure still writes.** Once measure has succeeded, eval.json and the ledger line are written
  for every status. A non-ok judge ends the eval run `failed`, and the deterministic half is kept.

## Results

- **eval.json path** (`eval_json_path(eval_home, source_home, run_id)`).
  - When the two realpaths are equal, it is `<home>/runs/<run>/eval.json`. That is the one file
    the eval creates under the target's run directory. The writer makes that directory with
    `config.state_dir("runs", <run>)` if it is missing (G11).
  - Otherwise it is `<eval home>/evals/<sha1(source realpath)[:8]>-<run>.json`, so a foreign home
    gets zero writes and one run id in two homes never collides.
- **Writing it.** `write_eval_json` accepts only those two shapes under the eval home, and raises
  `ValueError` for any other path, a `..` included. It writes a 0600 temp file in the same
  directory, fsyncs it, and `os.replace`s it into place. The file holds the latest evaluation, and
  the history lives in the ledger. The view refuses one over `EVAL_JSON_MAX` (256 KB).
- **Body** (schema 1):
  `{schema, rubric_version, rubric: {<id>: <version>}, target: {home, run, created_at, playbook, state, review_state, legacy}, eval_run, evaluated_at, original_source, metrics, flags, dimensions: {<id>: {scorer, score, rationale, evidence: [{turn, where, line, quote, verified}], error, detail?}}, headline, judge: {status, evidence_rejected, cost_usd, tokens, error}}`.
- **Headline** (`headline(dimensions, judge_error)`):
  `weakest: <id> <score>/5: <first verified quote, ≤120 chars>`, over every scored dimension,
  deterministic ones included. Ties go to table order. When nothing is scored it is
  `not scored: <judge error>`.
- **Deterministic block.** `deterministic_block` is
  `canonical({"metrics": …, "flags": …, "deterministic": …})`, taken from the eval_target
  reduction, so `flags` holds measure's flags only.
  - `canonical` is `json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))`.
  - The block holds no timestamp, no eval run id and no eval-home path. USD has 4 dp, seconds
    0.1, and medians are floats. So two evals of one target give byte-identical blocks.
- **Ledger.** `ledger_path(home)` is `<eval home>/evals.jsonl`.
  - `append_ledger` opens it `O_RDWR|O_APPEND|O_CREAT|O_NOFOLLOW`, mode 0600, and does one
    `os.write` of `canonical(line) + "\n"`, then an fsync. When the file does not end in a newline
    (a crash or a full disk tore its last line), the same write starts with one, so the torn line
    never swallows the new one. A short write raises. The file is never truncated or rewritten.
  - A line (`eval_line`, `anchor_line`) is
    `{ts, source: "eval"|"anchor", target: {home, run, created_at}, rubric_version, dimensions: {<id>: {version, score}}, eval_run, judge_status, rater, note}`.
    Eval lines carry all six dimensions, and anchor lines only the entered ones.
  - `read_ledger(path, limit)` returns the JSON-object lines in file order, splitting on `"\n"`
    only (a canonical line may hold a literal U+2028). It returns `[]` only when the file is
    missing, and None (unknown) past `limit` bytes, for a symlink, a non-regular or an
    unreadable file, and for a line nested past json's recursion limit (it may be an anchor no
    one can read). Other lines that are not a JSON object are skipped. It creates nothing. The
    view passes `LEDGER_MAX` (2 MB).
  - A resume that re-reduces judge can append a second line with the same `eval_run`, and a
    recreated queue.db mints the same `eval_run` again for another target. So `latest_evals` keeps
    the last line per (`eval_run`, target key), then the latest eval line per target key
    (home, run, created_at).
- **Reductions.** They land on the eval run only; the target gets none.
  - `eval_target` is
    `{target, legacy, digests, inputs_digests, target_state: {rows, files}, inputs: {dir, thread, entries, original, revised, doc, metrics, rubric}, rubric, rubric_version, metrics, flags, deterministic, original_source, error: null}`.
    measure takes `target_state` before it reads the target, so a change during the read shows
    too.
    Its `inputs` names are relative to `dir`, and None when absent.
  - `eval` is the eval.json body.

## Calibration

`calibration(ledger_lines)` returns `{judge dimension version: label}`. It is computed at read
time, never stored, and shared by the CLI and the view.

For each judge version V, the anchored targets are those with both:
- an anchor score at V. Anchors are keyed by (target, dimension, version), and the latest wins per
  key, so an older-version anchor appended later never hides one at V;
- an eval score at V, from the latest eval line per target. A null eval score is not a score at
  V, so a later failed eval hides an earlier ok one for that dimension.

The labels:
- `off (Δn)`: any |Δ| ≥ 2, where n is the largest difference.
- `calibrated`: otherwise, at least `MIN_ANCHORS` (2) anchored targets, all within ±1.
- `uncalibrated`: everything else.

Every judge version in the current `dimension_versions()` gets a label, and so does every judge
version in any eval line, so an older eval.json still finds its own. Deterministic versions are
absent. An anchor at an older version never counts.

## CLI

`.venv/bin/python -m playbooks.committee.eval_cli <cmd>`, run from the checkout, is
`main(argv) -> int`, built on stdlib argparse.
It returns the exit code and never raises; a usage error is 2. `engine/cli.py` cannot host it, for
two reasons: the guard against committee code in engine/ would fail, and `engine.cli run` exits 0
whatever state the run ends in. `playbooks/committee/__init__.py` does not import it.

- **`run <run> [--home H] [--agent A]`**, in order:
  1. It runs `validate_target` on the realpath of H, or of the eval home. On failure it prints
     the reason to stderr, exits 2, and creates nothing; the environment is untouched.
  2. It sets `HERMES_COMMITTEE_EVAL_RUN` and `HERMES_COMMITTEE_EVAL_HOME`, and appends
     `playbooks.committee` to `HERMES_PLAYBOOK_MODULES` (comma-separated, never duplicated).
  3. It calls
     `engine.cli.main(["run", "committee-eval", "--site", "local", "--wait", *agent_args])`.
  4. It finds the committee-eval run it started, over `connect_ro`, prints its id and end state,
     then prints that evaluation as `show` does.
  5. It exits 0 iff that run ended `done`, and 1 otherwise.
- **`show <run> [--home H]`** prints the stored evaluation of that target: one row per dimension,
  in table order, with its score (`—` when null), its scorer, its calibration label (judge rows
  only; `unknown` when the ledger cannot be read) and its first verified quote clipped to 80
  chars. Then come the flags (`<id>@tNN`, or none), the headline and the judge status with its
  error. Each judge dimension's rationale follows the table, wrapped to 100 columns, since one
  quote cannot say why a score is not a 5. Every control character (ESC, CR, BEL…) in a quote, a
  rationale, a flag id, the headline or the judge error prints as a space, so worker text in a
  transcript never drives the terminal. It exits 1 when the target has no readable eval.json.
- **`compare [--rubric R …]`** prints one row per target, from the latest eval lines in the eval
  home's ledger, sorted by label, and exits 1 when the ledger cannot be read.
  - The label is `<run>` for the eval home, and `<parent>/<basename>:<run>` otherwise, for
    example `committee-spin/home:run-2`.
  - A cell scored under an older definition than the current `dimension_versions()` is starred,
    with the footnote
    ``* older definition; re-run `.venv/bin/python -m playbooks.committee.eval_cli run <target>` ``.
    So a concision bump stars only the concision cells.
  - A cell reads `4 (a:3)` when the user's anchor exists at the cell's version, deterministic
    cells included (shown, never calibrated). A judge cell reads `4 (re-score needed)` when the
    target has anchors for that dimension but none at its current version. A starred cell whose
    target is anchored at the current version reads `4*` alone: the eval needs re-running, not a
    re-score.
  - A `calibration` row closes the table, then the tie-or-reverse notes (see Calibrating the
    judge). `--rubric` keeps only the evaluations whose rubric version is one of those given;
    anchors, the calibration row and the notes always read the whole ledger.
- **`anchor <run> [--home H] <id>=<1-5>... [--rater R] [--note T]`**.
  - It accepts any non-empty subset of the six ids, each with an integer 1 to 5.
  - It exits 2 on an unknown id, any other value, no scores, or a target `validate_target`
    rejects (the same checks as `run`).
  - It reads `created_at` read-only and appends one anchor line to the eval home's ledger,
    carrying the current dimension versions. It exits 1 when the ledger cannot be appended to.
  - Anchors are the user's to enter. Nothing in the pipeline writes one or waits for one.

## View: the Evaluation block on the Metrics tab

`view_data(run, reductions)["evaluation"]` comes from `_evaluation(run.id)` in
`playbooks/committee/view.py`. The helper imports eval lazily (a module-scope import would be a
cycle), never raises, and creates nothing. It reads `thread.run_file(run.id, "eval.json")`
through `thread.read_regular`, after `lstat`ing `runs/<id>/` (a directory) and eval.json (a
regular file) as `_size` does, and the ledger through
`read_ledger(config.resolve_home()/"evals.jsonl", LEDGER_MAX)`. The value is one of:
- `null` when `runs/<id>/` or its eval.json is missing, which includes a run only ever scored
  from a foreign home.
- `{"state": "error", "error": str}` when either is a symlink (dangling too) or not the right
  kind of file, or the file is over 256 KB (checked again after the read), unreadable, not UTF-8
  JSON (including nesting past json's recursion limit), not an object, has `schema != 1`, or
  holds junk inside that breaks the read. No message names an absolute path: an OS error shows
  its `strerror`.
- Otherwise `{"state": "ok", rubric_version, evaluated_at, headline, judge_status, judge_error,
  dimensions: {<id>: {score, scorer, quote, calibration, rationale, stale}}, flags: [<id>, …]}`,
  where:
  - each field reaches the UI as the type it renders, or null when the file holds anything
    else: `score` an int (eval's `_score`), `evaluated_at` a finite number (json.loads reads
    `NaN` and `1e999`, which the route's `allow_nan=False` serialiser would turn into a 500 on
    every poll), the text fields a str, and
    `flags` only the string ids.
  - `scorer` comes from `JUDGE_DIMS`, never from the file.
  - `quote` is the first quote whose `verified` is exactly `true`, or null.
  - `calibration` is the label for eval.json's own version of a judge dimension, or
    `uncalibrated` when it has none. It is `unknown` for every judge dimension when
    `read_ledger` returns None, and null for a deterministic dimension.
  - `rationale` is the dimension's rationale clipped to `RATIONALE_MAX` (4000) characters, as eval.json holds it,
    ending `…` when cut, or null when empty or not a string. `stale` is true when eval.json's
    version of the dimension is not today's `dimension_versions()`, which `show` and `compare`
    star. Both extend C7.
  - `judge_error` extends the planning spec's C7 payload. The UI shows the judge's error, and the
    payload otherwise carried none. It is shown as written: judge.reduce writes it in the master.

`CommitteeView.tsx` renders `MeetingMetrics` and then `EvaluationBlock`, inside the committee
view's existing `metrics` variant. So no tab appears or hides for any playbook, and the block never
repeats the turns, delegations, re-checks or prose counts. It has four states:
- not evaluated, once the chair has delivered a verdict (`verdict.text` is non-empty): "Not
  evaluated. Score it with `.venv/bin/python -m playbooks.committee.eval_cli run <run>` from the
  hermes checkout, with HERMES_HOME set to this control plane's home." That runs as written, as
  at the top of this spec.
- not evaluated, before that (a meeting in progress, a chair that delivered nothing, which
  `run` would refuse with exit 2): "Not evaluated: a run can be scored once the chair has
  delivered its verdict." No command is offered.
- ok: the headline, a table (`aria-label="Evaluation scores"`) of dimension, score, scorer and
  evidence quote, wrapped in full ("no verified quote" when null), each dimension's rationale
  under its quote, a `*` on each stale score with the CLI's footnote, the flags (a repeated id
  shows `×n`), the rubric version, and a badge with the calibration label on each judge dimension
  not labelled `calibrated`. A null field shows as unknown ("Judge status unknown", "rubric
  unknown").
- judge failed, partial or unparseable: the same, with `—` (read as "not scored") for each null
  score and a "Judge <status>" line, with ": <error>" when there is one.
- error: the message.

A new eval shows on the page's next load, because nothing lands on the target to trigger a
refetch. The eval playbook itself has no view, so its runs get the generic tabs.

## voice.py: the interim rules source

`playbooks/committee/voice.py` holds `RULES`, `FILLER` and `measure(body, role="reviewer")`.
- `RULES` is one line per element, distilled once from the diff-authoring skill in the playbook's
  own words: lead with the point; bullets of about 1.5 lines or less; no walls of text; no
  defending decisions; concrete examples and pointers. No element contains `**`, an en dash or
  an em dash, and the skill is never read at runtime.
- eval.py imports only `RULES`, `measure` and `summary`, and `words(text)` is
  `measure(text)["words"]`. eval.py has no other word counter.
- The wall threshold, 120 words, is `_WALL_WORDS` in eval.py, not a voice.py name, because eval
  imports nothing else from voice.

`measure` is pure and never raises; a non-str counts as `""`. `role` is unused until
committee-voice gives each role its own cap. It returns
`{words, pointers, examples, longest_paragraph_words, filler_hits}`:
- `words` is `len(body.split())`.
- `longest_paragraph_words` is the most words in one paragraph, a maximal run of non-blank lines.
  A wall is over 120.
- `pointers` counts matches of `(?<![\w./-])[\w./-]+\.\w+:\d+(-\d+)?` plus
  `§\s?\d+(\.\d+)*|\b[Ss]ection \d+(\.\d+)*`. The lookbehind starts a path match only at a
  token's first char, so one long token stays linear time.
- `examples` adds up these counts:
  - `for example`, `e.g.`, `for instance` and `such as`, as case-insensitive substrings;
  - inline code spans, matching `` `[^`\n]+` `` with fenced contents removed;
  - fenced blocks, counted as the lines whose `lstrip()` starts with three backticks,
    integer-divided by 2;
  - matches of `\b\d+(\.\d+)?\s?(ms|s|min|h|%|KB|MB|GB|x|QPS)\b`.
- `filler_hits` is `text.lower().count(p)` summed over the 15 phrases in `FILLER`, so "delved"
  counts as "delve".

`metrics.voice` is `voice_shares(rows)` over P, one measure dict per turn.
- A reduction's `voice` dict is used verbatim, and every other turn in P is measured with
  `measure(body, role)`. A `voice: null` turn is not in P.
- The result is `{n, pointer_share, walls_share, example_share, filler_per_turn}`: the share of
  turns with a pointer, with a wall, and with an example, and the mean filler hits per turn. Each
  is rounded to 4 dp, and is null when n == 0.

## Environment and files

| var | default | meaning |
|---|---|---|
| `HERMES_COMMITTEE_EVAL_RUN` | none (required) | the target run id |
| `HERMES_COMMITTEE_EVAL_HOME` | the eval `HERMES_HOME` | the source home, read-only |
| `HERMES_PLAYBOOK_MODULES` | must include `playbooks.committee` | `run` appends it |

They are read in measure.reduce and the CLI only. Every file is written in the eval home, except
a same-home eval.json:

| path | writer |
|---|---|
| `runs/<eval-run>/inputs/…` | measure.reduce, for a valid target |
| `runs/<eval-run>/traces/<attempt>.jsonl` | the engine, for the judge attempt |
| `runs/<run>/eval.json` (same home), else `evals/<sha1[:8]>-<run>.json` | judge.reduce |
| `evals.jsonl` | judge.reduce and `anchor` |

## Edge cases

| case | behaviour |
|---|---|
| `HERMES_COMMITTEE_EVAL_RUN` unset (a bare `engine.cli run committee-eval`) | an eval_target error; no judge ticket; the run ends failed; nothing is written outside `runs/<eval-run>/` |
| the source home is mistyped, has no queue.db or an unreadable one; the run is missing; it is not a committee run (an eval run included); it has no delivered decision; it is legacy without thread.md; the site is not local or fan-* | an error naming the reason. The `run` wrapper exits 2 before any eval run exists. No file is created in the source home. |
| a non-legacy run without thread.md | evaluated from the reductions, with entries.json built from them so the judge still gets a transcript; every `line` is null; flag `thread_missing` |
| the original or revised copy is missing | `bytes.*` are null; that inputs name is null, so the judge is told it is unavailable; edits are judged from the delegations and junior reports |
| traces missing or partial | `cost_usd` is null; `traces.found < expected`; tokens are summed over what was found; efficiency loses the cost point |
| a failed attempt with no measured length, or no attempts | `time.*` are null and `time.unmeasured` counts them; efficiency loses the time point |
| no delivered reviewer or owner prose (P empty) | `words.median_reviewer_owner` and the voice shares are null; concision is null with `no measured reviewer/owner prose` |
| the judge ends driver_failed or times out | status failed; the judge dimensions are null; eval.json and the ledger line are still written; the eval run ends failed |
| no fence, bad JSON, or a score of 0, 6, 4.5 or true | unparseable, or that dimension null with status partial |
| an invented quote, or one under 3 words or 12 characters | `verified: false`; the dimension is null if nothing verifies |
| the judge's answer quotes a `hermes-eval` block from the transcript | the fence must stand on its own lines, and the last parseable fence wins, so an echoed block inside a JSON string never outvotes the answer |
| the judge writes, deletes or swaps (a symlink, a FIFO) a source file or an inputs/ copy; edits the target's reductions or attempts; adds or resizes a file under `runs/<run>/` | `target_changed_during_eval`; the answer is not parsed; status failed; a FIFO never blocks the reduce |
| a trace's `totalCostUSD` is NaN, infinite or negative | that trace has no cost, so `cost_usd` is null and efficiency loses the cost point |
| judge.reduce hits an internal error | a failed eval rebuilt from the eval_target is written to eval.json and the ledger, each tried on its own; the run ends failed |
| a malformed eval_target | judge seeds nothing and reduces nothing; the run ends failed |
| two evals of one target at once | eval.json: the last `os.replace` wins; both ledger lines are kept |
| a torn last ledger line (crash, full disk) | the next append starts with a newline; readers skip the torn line |
| a crash after the judge ticket settled, before or during judge.reduce | `HERMES_PLAYBOOK_MODULES=playbooks.committee .venv/bin/python -m engine.cli run resume <eval-run> --wait` re-reduces judge from its findings. A duplicate ledger line is deduped by `eval_run`. |
| a crash while the judge worker is running | Resume cannot settle while the orphaned ticket's lease keeps being renewed, which every crew sweep does for a live lease. Once the lease TTL lapses, it may re-dispatch the judge. The safe advice is to start a new eval. |
| the same run id in two homes, or a recreated queue.db that reuses an id | distinct keys (home realpath, run, created_at) |
| `take` reductions, unknown kinds, a seat absent from `cast.CAST`, `voice: null` | takes and duplicate turns count in `extra_takes`, other kinds in `other_kinds`; the roster comes from the header and the reductions; a null `voice` is unmeasured; nothing raises |
| `--dry-run` | measure seeds nothing and writes nothing; the run settles `stopped` |
| SQLite `mode=ro` on a WAL database | may create an empty `queue.db-wal` and a `queue.db-shm`; queue.db and the run files stay byte-identical |

## Downstream: what the next loops build on

The build order is doc-diff → eval → voice → selection → one-on-ones, with each branch stacked on
the previous one. Each behaviour loop scores its live run with the two commands at the top of this
spec, and compares it against run-9 and run-2.

- **Names.**
  - eval.py's only voice import is `from playbooks.committee.voice import RULES, measure, summary`.
  - Build on `words`, `DIMENSIONS`, `JUDGE_DIMS`, `DETERMINISTIC_DIMS`, `dimension_versions(rules)`,
    `rubric_version(versions)`, `compute_metrics(target)` and `calibration(ledger_lines)`.
  - Quote verification is two calls, never one that reads the disk itself:
    `read_snapshot(inputs, digests) -> {entries, thread, original, revised}` reads each
    `inputs/` copy once and treats any whose sha256 is not in `digests` (the eval_target's
    `inputs_digests`, by absolute path) as absent; then `verify_evidence(item, snap)` checks one
    item against that snapshot. `score_judge(parsed, inputs, digests, metrics)` does both for a
    whole answer. A loop that cites a new source (a 1:1 outcome, say) builds its `snap` the same
    way, e.g. `{"entries": entries, "thread": text, "original": None, "revised": None}`, from
    digest-checked copies. A `verify_evidence` that reads `inputs/` from disk unchecked would let
    a judge that edits a copy forge a verified quote.
  - `target_state(home, run)` is what the re-hash compares beyond the copies. A loop that adds a
    table the target owns and the judge must not touch adds it there.
  - `metrics["voice"]` is exactly `{n, pointer_share, walls_share, example_share, filler_per_turn}`.
  - `metrics["extra_takes"]` is the `take` reductions plus the losing duplicate `turn` reductions.
  - The fixtures live under `tests/data/committee-eval/{run-9,run-2}/`, and
    `build_home(tmp_path, name)` in `tests/unit/test_committee_eval.py` builds them into a
    throwaway home.
  - The pins are `test_run9_metrics_pinned`, `test_run2_legacy_metrics_pinned`,
    `test_deterministic_scores_pinned` and `test_voice_measure_and_version`.
- **Where the seams sit.**
  - `metrics["voice"]` is computed by `_prose_voice(target)`, via `_prose_metrics(target)`, inside
    `compute_metrics(target)`. measure's reduce only calls `measure_target`, which calls it.
  - The reviewer/owner median and the voice shares share one population, `_prose_population`.
    A loop that changes who counts changes it there, for both.
  - `test_run9_metrics_pinned` and `test_run2_legacy_metrics_pinned` compare the whole
    `compute_metrics` dict with `==`: a new metrics key goes into `compute_metrics` and into both
    expected dicts in the same change.
  - `Target.turns` is `{int: the last turn doc by id}` and `Target.decision` is the latest decision
    doc. `Target` keeps no raw reduction rows, and `load_target` keeps no non-turn reduction doc (it
    only counts them in `other_kinds`). A loop that needs one, such as the final `selection`, adds a
    `Target` field filled in `load_target`'s reduction loop.
  - The entries dict is `build_entries(target)`, with str turn keys. The header roster is
    `parse_thread(text)["roster"]`. `seats` is built inline in `compute_metrics` from
    `roster(target)` and `reviewers(target)`, and the judge sees it only through
    `inputs/metrics.json` (= `deterministic_block`).
- **Version-bump rule.** A loop that changes a dimension's definition, bands or inputs bumps that
  dimension's `@n` in `DIMENSIONS`, and re-pins the affected metrics in the same change; no
  tolerance absorbs a moved pin. concision's version also carries a hash of `RULES`, so a rules
  swap bumps it without anyone remembering to. A `RUBRIC` edit fails
  `test_voice_measure_and_version` until the affected judge dimension's `@n` is bumped and the
  hash re-pinned. That test spells each dimension's version as a literal
  (`"verdict_consistency@2"`), so grep for the old one to find it. The same change updates the
  verbatim `RUBRIC` block and its hash in this doc, and the current versions listed under
  Versions. `compare` stars the stale cells.
- **committee-voice** rewrites voice.py in place.
  - It keeps `RULES`, `measure` and a superset of `measure`'s keys.
  - It keeps `_PATH_LINE`'s lookbehind form, `(?<![\w./-])[\w./-]+\.\w+:\d+(-\d+)?`; the plain
    form is quadratic on one long token.
  - It records `voice` on kept reductions, and eval uses that verbatim.
  - Its `RULES` change bumps concision's version through the hash.
  - It must re-pin `metrics.voice` explicitly in T1 and T2, because its `filler_hits`
    redefinition moves `filler_per_turn`.
  - `extra_takes` already counts its `take` reductions, and a turn recorded with `voice: null`
    is already out of P.
- **committee-selection** takes `seats.roster` and `seats.reviewers` from its final `selection`
  reduction when present, and bumps concern_coverage. If it edits `RUBRIC` (a concern_coverage
  sentence, say), the bump and the hash re-pin go in the same change. The header parser already
  ignores its pre-t01 lines, and `outside_room_mentions` counts only turn and decision entries.
- **committee-one-on-ones.**
  - Up-front `## 1:1 …` outcome lines before t01 belong to no entry, so they are never header
    evidence.
  - Mid-review `## 1:1 — …` lines inside a turn's line range may count in
    `outside_room_mentions`. That is report-only and never scored.
  - Efficiency's cost, tokens, traces and time already cover every attempt on the run's tickets,
    1:1s included. So efficiency's definition and version do not change, and `turns >= cap`
    counts meeting turns only.
  - Its separate `one_on_ones` block must not split attempts out of `time`, `cost_usd`, `tokens`
    or `traces`.
- **Live-run comparisons use the amended bill.** Tokens come from `modelUsage`, so run-9's are
  502/287400/4378394/13727431, and an unmeasured failed attempt makes `time` null rather than
  short.
- **Rebuild the view bundle after rebasing.** Every loop changes
  `playbooks/committee/view/dist/committee.umd.js`. After a rebase, rebuild it
  (`cd web && ./node_modules/.bin/vite build --config vite.playbook-view.config.ts`) and run
  `tests/unit/test_committee_view_build.py`.

## Invariants

- No production file under engine/, server/ or web/src changes. engine/ stays stdlib-only and
  holds no committee literal.
- The evaluated run gets no reduction and no row. Its only write is its same-home eval.json, and a
  foreign home gets none.
- `evals.jsonl`, reductions, attempts and events are append-only.
- No eval `reduce` ever raises. A malformed reduction, file or answer becomes an error value.
- The eval never gates or feeds the accept/reject ruling and never tunes a prompt. Nothing ships.
