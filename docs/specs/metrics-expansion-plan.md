# Hermes metrics expansion — implementation plan

Status: **draft**. Spec: `docs/specs/metrics-expansion.md` (hardened). Depends on:
the existing `GET /api/runs/{id}/metrics` endpoint in `server/app.py` and the real
`attempts`/`tickets` tables — **already built**.

Two dependency-ordered TDD slices (backend contract first, then UI). Each is
independently testable, follows **TDD** (failing test first → minimal code → green),
and ends GREEN. Runner: backend `./.venv/bin/python -m pytest -m "not docker" -q`;
web `cd web && npx vitest run`. Commit after each slice.

---

## Global constraints (apply to every slice)

- **No fabricated data.** Every new number derives from real `attempts`/`tickets`
  rows for the run. No GPU/budget/$/token metrics (no data source — deferred deltas).
- **Additive API.** The existing `buckets` field + shape are unchanged; existing
  metrics tests must stay green. New fields are added alongside.
- **Stdlib-only backend aggregation**, mirroring the existing endpoint's in-Python
  style (fetch rows, aggregate in Python).
- **Code self-contained** — no doc references in code (`§`, `Slice N`, `docs/…`,
  "per the spec/plan") in comments/strings.
- **Never fake test data or tautological assertions** — seed real rows, assert exact
  derived values.

---

## Slice 1 — Backend: extend the metrics endpoint

**Scope.** Add `totals`, `retry_rate`, `mean_time_to_result_s`, `by_phase` to the
`GET /api/runs/{id}/metrics` response, computed from the run's `attempts`.

**Files.**
- `server/app.py` (edit `get_run_metrics`): after the existing bucket computation,
  fetch the run's attempts (`SELECT a.id, a.phase, a.ticket_id, a.attempt,
  a.started_at, a.ended_at, a.outcome FROM attempts a JOIN tickets t ON
  a.ticket_id=t.id WHERE t.run_id=? ORDER BY a.id`) and compute in Python:
  - `totals.attempts` = len(rows); `done` = outcome=="ok"; `failed` = outcome in
    ("driver_failed","infra_failed"); `results` = done+failed; `tickets` =
    len(distinct ticket_id).
  - `retry_rate` = (distinct tickets whose max `attempt` > 1) / (distinct tickets
    with attempts); `0.0` if denominator 0.
  - `mean_time_to_result_s` = mean(ended_at-started_at) over rows with both non-null;
    `None` if none.
  - `by_phase`: group rows by `phase` preserving first-`id` order; per phase
    `tickets` (distinct ticket_id), `mean_time_s` (mean dur over rows w/ both ts, else
    None), `failure_pct` (failed/total*100 for that phase's rows).
  - Add all four to the returned dict (both the empty-run early-return AND the normal
    return path — empty run: zeros / 0.0 / None / []).

**Tests to write first** (`tests/unit/test_server.py`, new tests):
- `test_metrics_totals_and_retry_and_mean`: seed a run + tickets + attempts:
  ticket A phase "work" attempt1 ok (started 0 ended 10); ticket A phase "work"
  attempt2 ok (started 20 ended 50); ticket B phase "work" attempt1 driver_failed
  (started 0 ended 4); ticket C phase "reduce" attempt1 ok (started 0 ended 6).
  Assert: totals = {attempts:4, done:3, failed:1, results:4, tickets:3};
  retry_rate == 1/3 (only A retried); mean_time_to_result_s == (10+30+4+6)/4 == 12.5.
- `test_metrics_by_phase`: from the same seed, `by_phase` == two entries: "work"
  {tickets:2, mean_time_s:(10+30+4)/3, failure_pct: 1/3*100} then "reduce"
  {tickets:1, mean_time_s:6.0, failure_pct:0.0}; order work-before-reduce (first id).
- `test_metrics_empty_run_aggregates`: a run with no attempts → totals all 0,
  retry_rate 0.0, mean_time_to_result_s None, by_phase [] (and buckets []).
- Existing metrics tests still pass (buckets unchanged).

**DoD.** New tests pass; existing `test_server.py` metrics tests unchanged+green;
full backend suite green.

---

## Slice 2 — Frontend: tiles + By-phase table

**Scope.** Surface the new metrics in the Metrics view, styled like the prototype.

**Files.**
- `web/src/api/client.ts` (edit): extend `RunMetrics` with `totals` (attempts/done/
  failed/results/tickets: number), `retry_rate: number`,
  `mean_time_to_result_s: number | null`, `by_phase: Array<{ phase: string;
  tickets: number; mean_time_s: number | null; failure_pct: number }>`.
- `web/src/util/time.ts` (edit): add `fmtSeconds(s: number | null): string` →
  `—` when null; `Ns` (<60), `Mm Ss` (<3600), `Hh Mm` otherwise.
- `web/src/views/MetricsView.tsx` (edit): add two tiles — **retry rate**
  (`${Math.round(retry_rate*100)}%`, delta "tickets retried once+") and **time to
  result** (`fmtSeconds(mean_time_to_result_s)`, delta "mean claim→result") — to the
  existing tile row. Add a **By phase** `Card` with a header row
  (`phase · tickets · mean_time · failure_pct`) and one row per `by_phase` entry
  (mono), highlighting `metrics`-derived current phase if available and coloring
  `failure_pct > 5` with `--status-danger`. No GPU/budget/$/token content.

**Tests to write first** (`web/src/views/MetricsView.test.tsx`, extend the existing
mock):
- Add `totals`, `retry_rate: 0.25`, `mean_time_to_result_s: 125`, `by_phase:
  [{phase:'work', tickets:3, mean_time_s:12, failure_pct:10}]` to the mock metrics.
- Assert the retry-rate tile renders `25%` (and label), the time-to-result tile
  renders `2m 5s`, and the By-phase table shows `work`, its ticket count, and its
  failure %. Assert no `gpu`/`budget`/`token`/`spend` text is present.

**DoD.** New assertions pass; existing MetricsView tests green; `tsc` + `vite build`
clean; full web suite green.

---

## Acceptance
- `GET /api/runs/{id}/metrics` returns totals/retry_rate/mean_time_to_result_s/
  by_phase from real rows (Slice 1 tests).
- Metrics view renders the two new tiles + the By-phase table (Slice 2 tests).
- No fabricated GPU/budget/$/token metrics anywhere.
- `pytest -m "not docker"` + web vitest + build all green.
