# LEASH-056: End-to-end test against the fake API

**Status**: DONE
**Priority**: P0
**Type**: test
**Estimated Effort**: M
**Milestone**: M3 — Durable fake-API integration
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-004
**Task ID**: 004-T7
**Blocked by**: LEASH-053, LEASH-054, LEASH-055, LEASH-045
**Blocks**: LEASH-057, LEASH-112, LEASH-126, LEASH-128
**Updated**: 2026-09-23

## Description
Full run: create and confirm mandate, start run, worker decides all purchases, a customer resolves one ask.

## Business Value
Proves the pieces work together before event day.

## Acceptance Criteria
- [x] All purchases get a decision before their deadline.
- [x] Repeat delivery doesn't double-count.
- [x] The resolve path reaches the fake API.
- [x] Covers late customer approval after a limit changed.
- [x] Covers restart between commit and POST.

## Technical Approach
`tests/e2e/test_full_run.py`.

### Dependencies
- Needs LEASH-053.
- Needs LEASH-054.
- Needs LEASH-055.
- Needs LEASH-045.
- Blocks LEASH-057.
- Blocks LEASH-112.
- Blocks LEASH-126.
- Blocks LEASH-128.

## Testing Requirements
This is the test. Run `uv run pytest tests/e2e`.

## Related Files
- `solution/engine/tests/e2e/test_full_run.py`

## Out of scope
- Live API.

## Implementation note (2026-09-23)
- `tests/e2e/test_full_run.py` runs a full SCEN0001 run against the fake platform and a throw-away Postgres:
  - The mandate is created and confirmed at the platform (fixture hard_rules) and the run is started.
  - `Worker` + `DecidePurchase` + `PostgresDecisionStore` decide every purchase, with a recovery outbox loop running alongside, as `leash-worker` does.
- How the criteria are read:
  - **Restart between commit and POST:** AU0005's first POST fails after its commit. The platform delivers it again (`repeat=`), and the repeat path or the recovery outbox answers it before its deadline. Every purchase has exactly one `decided` event and approved spend is CHF 300.00, so nothing is counted twice.
  - **Late approval after a limit changed:** later approvals used up the 7-day CHF 300 limit. Approving the earlier ask AU0006 is then refused (`over_period_limit`, DEC-012), and nothing reaches /resolve.
  - **Resolve path:** rejecting AU0007 reaches the fake through the outbox.
  - A tightened mandate (PATCH) is LEASH-062 and isn't built yet.
- The test loads the run's mandate snapshot from Postgres itself; a production MandateSource comes with the resolve endpoint (LEASH-063).

## Review log

### 2026-09-23 — independent agent review, round 1
- [x] met — criteria 1–4, each confirmed by a mutation that turns it red. The "limit changed" reading (the remaining limit changed; DEC-012 wording) is accepted; tightening is LEASH-062.
- [~] partly met — criterion 5: the platform's immediate re-delivery answered AU0005 before the outbox's grace period ended, so the recovery outbox was never exercised (disabling it stayed green), and nothing actually restarted.
Verdict: returned to in-progress. Fix: new test `test_a_restart_between_commit_and_post_is_recovered_by_the_outbox`:
- no repeat delivery;
- the first process (worker and pool) commits AU0005's decision, loses its POST and stops;
- a new process (new pool, new worker, recovery outbox) must deliver the committed verdict before its deadline, and the run completes.
- It asserts one delivery, the saved verdict, `attempts == 1`, no deadline refusals, and exactly one `decided` event per purchase.
- Mutation check: with the recovery outbox disabled, the test fails (AU0005 is never answered).
- The first test's docstring now says the repeat path answers there. Both e2e tests are green 3/3 (≈2.3 s).

### 2026-09-23 — independent agent review, round 2
- [x] met — criterion 1: a skipped event turns it red; the restart test also checks AU0005's deadline and that nothing was refused as late.
- [x] met — criterion 2: repeat delivered twice, one `decided` event each, CHF 300.00 spend. The Postgres state machine alone also prevents double counting.
- [x] met — criterion 3: an outbox that skips resolve rows turns it red.
- [x] met — criterion 4: removing the DEC-012 re-check turns it red (365.00).
- [x] met — criterion 5: only the new process's outbox can answer AU0005. Every outbox mutation turns it red (no loop, `send_pending` doing nothing, a send that always fails, a failed send marked sent, no outbox row, a 10 s grace, repeat delivery added back, the lost send counted as an attempt).
Verdict: all met. Moved to done on the product owner's standing instruction for this run.
