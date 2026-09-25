# LEASH-133: Run-scoped cockpit

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: S
**Milestone**: M5 — Hosted API and release
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-129
**Task ID**: 129-T4
**Blocked by**: none
**Blocks**: LEASH-128, LEASH-143, LEASH-150, LEASH-153
**Updated**: 2026-09-25

## Description
Make payments, spending totals and status counts use the same selected run instead of mixing all payments with the latest run's spending.

## Business Value
The cockpit remains truthful when judges or operators run more than one scenario without resetting the database.

## Acceptance Criteria
- [x] The app loads the current run ID and passes it to payments and spending queries.
- [x] A customer can select an earlier run when more than one exists.
- [x] Payment rows, counts, spending and limits always describe the selected run.
- [x] Stream events refresh the selected run without switching it unexpectedly.
- [x] Empty and finished-run states are explicit.

## Technical Approach
Introduce a shared run selection query/state and include `run_id` in both React Query keys and API calls.

### Dependencies
- Blocks LEASH-128.
- Blocks LEASH-143.
- Blocks LEASH-150.
- Blocks LEASH-153.

## Testing Requirements
Write a failing cockpit test with two runs whose payment counts and spending differ. Add an end-to-end journey that switches runs.

## Related Files
- `solution/app/src/screens/Cockpit.tsx`
- `solution/app/src/api/client.ts`
- `solution/engine/src/leash/adapters/http/query_api.py`

## Out of scope
- Cross-run analytics.

## Implementation note (2026-09-24)
- No engine change: `GET /api/payments` and `GET /api/spending` already take `run_id`, and `GET /api/runs` gives the runs and `current_run_id`.
- `Cockpit.tsx`:
  - `useSelectedRun` loads `/api/runs`, shows the current run first (else the newest), and pins that choice, so a newer run starting later never switches the screen by itself.
  - Payments and spending queries carry the run in their React Query key and URL (`?run_id=`), and only run once a run is known.
  - A run card: a "Run" select when more than one run exists (scenario · run · state), a state chip, and an explicit line for a finished or stopped run.
  - No runs: "No runs yet. Start one from your permission." and no payment or spending request. An empty run: "No agent payments in this run yet."
  - Stream events and reconnects invalidate runs, payments and spending; the selected run's queries refetch.
- Tests (red first), `Cockpit.test.tsx` "Cockpit per run": two runs with different payments and spending; loading the current run only; selecting the earlier run moves rows, counts and spending; stream events refresh without switching, also when a newer run appears; no-runs and finished states. Existing tests now also answer `/api/runs`. 86 app tests pass, `tsc` clean.
- End to end, `e2e/journey.spec.ts`: step 7 starts the later run from the app's "Start a run" card (LEASH-066); new step 7b switches the cockpit between the two runs (the order confirmed in the first run is blocked in the later one). `npx playwright test` passes (isolated `leash-e2e` Compose project).
- Also fixed in the journey: `getByText("Version 2")` also matched the LEASH-066 card hint, so it is now exact. That regression came from LEASH-066, whose review didn't run the browser journey.

## Review log

### 2026-09-24 — independent agent review
- [x] met — criterion 1: run from `/api/runs`, `run_id` in both queries' keys and URLs, queries wait for a run; removing each piece turns tests red (5, 2 and 3 tests).
- [x] met — criterion 2: the Run select appears with 2+ runs; unit test and browser step 7b switch runs; dropping the run from either query key turns tests red.
- [x] met — criterion 3: rows, counts, spending and limits come from the selected run; the server filters payments by run and builds spending from that run's snapshot and mandate; switching never shows the previous run's numbers.
- [x] met — criterion 4: events reload the selected run; the pin holds when a newer run appears (removing it fails 4 tests).
- [x] met with a gap — criterion 5: the empty-run and stopped-run messages had no test.
- Observation: a failed payments request showed "No agent payments in this run yet." instead of an error.
Verdict: all met.

### Fixes after review (2026-09-24)
- Test `an empty run and a stopped run each say so` now pins both messages.
- A failed payments request now shows "Payments couldn't be loaded right now." and never the empty-run message (test first: `payments that fail to load are an error, never an empty run`).
- 88 app tests pass, `tsc` clean. Moved to review.
