# Spec: Metrics expansion (real-data-derivable metrics)

## Goal

Expand the run metrics — API + UI — with the additional metrics the design
prototype (`web/prototype/app/MetricsView.jsx`) shows, **limited to what is
derivable from the engine's real recorded data** (the `attempts` / `tickets`
tables). Add summary aggregates + a per-phase breakdown; wire matching UI
(stat tiles + a "By phase" table) styled like the prototype. Definition of done:
`GET /api/runs/{id}/metrics` returns the new fields computed from real rows, the
Metrics view renders them, and the full suite (py + web) is green.

## Background / real data model (ground truth)

`attempts` columns: `id, ticket_id, phase, host, attempt, started_at, ended_at,
outcome, termination_reason, result_ref, error_summary, error_detail`.
`outcome ∈ {ok, driver_failed, infra_failed}`; `attempt` is the 1-based try index.
`tickets` has `phase, state, priority`. The existing metrics endpoint already
aggregates `attempts` (ended_at/outcome) + crew events into time buckets and
returns `{run_id, bucket_s, buckets:[…]}`.

Everything below is computed from these real rows only — **no fabricated data**.

## Requirements

### 1. Extend `GET /api/runs/{id}/metrics` (additive — keep `buckets` unchanged)
Add these top-level fields to the response, all derived from this run's `attempts`
(joined via `tickets.run_id`) — never invented:

- `totals`: object
  - `attempts`: total attempt rows for the run.
  - `done`: attempts with `outcome == "ok"`.
  - `failed`: attempts with `outcome IN ("driver_failed","infra_failed")`.
  - `results`: `done + failed` (attempts with a terminal outcome; equals `attempts`
    when every attempt has an outcome).
  - `tickets`: distinct `ticket_id`s that have ≥1 attempt.
- `retry_rate`: float in [0,1] — of tickets with ≥1 attempt, the fraction whose
  max `attempt` index is > 1 (i.e. needed a second try). `0.0` when no such tickets.
- `mean_time_to_result_s`: float — mean of `(ended_at - started_at)` over attempts
  where both are non-null; `null` when there are none.
- `by_phase`: list, one entry per distinct `attempts.phase` for the run, ordered by
  first appearance (ascending min `attempts.id` in the phase — deterministic and
  null-safe), each:
  - `phase`: str.
  - `tickets`: distinct `ticket_id`s with an attempt in that phase.
  - `mean_time_s`: mean `(ended_at - started_at)` over that phase's attempts with
    both non-null; `null` when none.
  - `failure_pct`: float in [0,100] — that phase's failed attempts / total attempts
    in the phase × 100; `0.0` when the phase has no attempts (cannot occur — a phase
    only appears if it has ≥1 attempt).
- Empty run (no attempts): `totals` all-zero, `retry_rate: 0.0`,
  `mean_time_to_result_s: null`, `by_phase: []`. `buckets` behavior unchanged.

Compute in stdlib Python over the fetched rows (mirror the existing endpoint's
in-Python aggregation; do not add SQL the codebase style avoids). 404 unchanged.

### 2. Client types (`web/src/api/client.ts`)
Extend `RunMetrics` with the new fields:
`totals: { attempts; done; failed; results; tickets }`,
`retry_rate: number`, `mean_time_to_result_s: number | null`,
`by_phase: Array<{ phase: string; tickets: number; mean_time_s: number | null; failure_pct: number }>`.

### 3. UI (`web/src/views/MetricsView.tsx`)
Keep the existing charts. Add, styled like the prototype:
- Stat tiles (real data): add **retry rate** (`{(retry_rate*100).toFixed(0)}%`,
  delta "tickets retried once+") and **time to result**
  (humanized `mean_time_to_result_s`, delta "mean claim→result", `—` when null) to
  the tile row. Keep the existing throughput/done/failed/error-rate tiles.
- A **"By phase"** card/table mirroring the prototype's layout — columns
  `phase · tickets · mean_time · failure_pct` (NO `gpu_hours` column — no data).
  Highlight the run's current phase; color `failure_pct` danger when > 5.
- Use the shared `fmtTime`/duration helpers where relevant; a small duration
  formatter for seconds (e.g. `42s`, `3m 5s`, `1h 2m`).

### 4. Explicitly OUT of scope — DELTAs with no data source (do NOT fabricate)
The prototype also shows metrics the engine has **no instrumentation for**; adding
them would require fabricating data, which is forbidden. These are deferred, not
implemented:
- GPU/CPU **hours**, **budgets**, **burn rates**, budget runout — the engine tracks
  no resource-hour accounting or budgets.
- Agent **$ spend**, **cost per ticket**, **token rate** — no token/cost telemetry.
- The prototype's **Budget**, **Resources**, and **Agent usage** sections (they
  depend on the above).
Record these as accepted limitations (future work needs resource + cost
instrumentation first). The UI must not display placeholder/fake values for them.

## Tests (TDD)

### Backend (`tests/unit/test_server.py`)
Seed a run with real `attempts` rows (multiple phases; one ticket with attempt=1
and attempt=2; a mix of ok/driver_failed outcomes with started_at/ended_at) and
assert `GET /api/runs/{id}/metrics` returns:
- `totals` matching the seeded counts (attempts/done/failed/results/tickets).
- `retry_rate` = (tickets with max attempt>1)/(tickets with attempts) for the seed.
- `mean_time_to_result_s` = the exact mean of the seeded durations.
- `by_phase` with the right per-phase tickets/mean_time_s/failure_pct.
- Empty run → zeros / null / `[]` as specified; `buckets` still present.

### Frontend (`web/src/views/MetricsView.test.tsx`)
Extend the mock metrics with the new fields and assert the retry-rate tile, the
time-to-result tile, and the "By phase" table (a phase name, its ticket count, its
failure %) render. Assert no GPU/budget/$/token text appears (out-of-scope guard).

## Invariants
- No fabricated data — every new number derives from real `attempts`/`tickets` rows.
- Additive API change — existing `buckets` shape + existing metrics tests unchanged.
- Stdlib-only backend aggregation. Code self-contained (no doc references in code).
- Full suite green: `./.venv/bin/python -m pytest -m "not docker" -q` and `web` vitest.
