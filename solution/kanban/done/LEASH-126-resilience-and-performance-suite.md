# LEASH-126: Resilience and performance suite

**Status**: DONE
**Priority**: P0
**Type**: test
**Estimated Effort**: M
**Milestone**: M5 — Hosted API and release
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-004
**Task ID**: 004-T10
**Blocked by**: LEASH-056, LEASH-122
**Blocks**: LEASH-128
**Updated**: 2026-09-23

## Description
Final cross-component suite: deadline percentiles under queue delay, restart mid-run, API errors and slow responses, lock contention, reader failure.

## Business Value
Evidence that the system stays inside deadlines and never double-counts when things go wrong.

## Acceptance Criteria
- [x] p95 time from queueing to accepted decision is reported and below deadline minus margin.
- [x] Restart mid-run resends unsent outbox rows and resumes polling.
- [x] Reader failure never produces a less strict verdict.

## Technical Approach
Extends the fake API with fault injection.

### Dependencies
- Needs LEASH-056.
- Needs LEASH-122.
- Blocks LEASH-128.

## Testing Requirements
Run `uv run pytest tests/resilience`.

## Related Files
- `solution/engine/tests/resilience/`

## Out of scope
- Load beyond one team's traffic.

## Implementation note (2026-09-23)
- **Fault injection in the fake platform** (`tests/fake_api/app.py`): `decision_delay_seconds`, `poll_delay_seconds`, and `fail_decisions` (the first N decision POSTs per source ID refused with 503 before they are recorded). The defaults leave every existing test unchanged.
- **`tests/resilience/test_resilience.py`** (run `uv run pytest tests/resilience -s`):
  - **Deadline report (criterion 1):**
    - Setup: all five scenarios at once (45 purchases, runs queueing together), 0.5 s queue delay, 0.2 s delivery lag, 0.15 s slower answers, 0.05 s slower polls, and three answers refused once with 503 and resent by the outbox.
    - Reported: p50/p95/max from queueing to the accepted decision, printed, attached as test properties, and written to `$LEASH_RESILIENCE_REPORT` when set.
    - Asserted: p95 < deadline − watchdog margin (8 − 1 s), nothing late, one `decided` event per purchase, every refused answer delivered.
    - Last run: p50 0.43 s, p95 1.08 s, max 1.88 s.
  - **Restart mid-run (criterion 2):** the first process loses the POSTs of committed decisions and goes down mid-run. The restarted process (new pool, worker and outbox) resends them before their deadlines (each delivered only once by the platform), resumes polling to the run's end, and leaves no unsent outbox row and no double count.
  - **Lock contention:** another transaction holds a card lock past the whole deadline; the purchase still gets a safe step_up in time.
  - **Reader failure (criterion 3):** a model reader that raises, times out, or lies (reads every text as permissively as possible) never gives a verdict less strict than the regex reader alone, on all 45 purchases (FallbackReader, DEC-009 guard).
- 6 tests, about 17 s.

## Review log

### 2026-09-23 — independent agent review
- [x] met — criterion 1: stable 3/3 (p95 1.05–1.08 s against 7 s). Latency runs from queueing to the platform's acceptance. A slow decide-path mutation turns it red.
- [x] met — criterion 2: a missing outbox row or an outbox that never resends both turn it red.
- [x] met — criterion 3: a FallbackReader that trusts a lying model turns it red.
- Test-strength notes, addressed afterwards:
  - the injected 503s are now asserted to have happened;
  - repeat delivery is enabled in the load test (re-delivered while unanswered);
  - the restart test's docstring now matches what happens (one lost POST, a graceful stop between events).
- Not addressed (outside the criteria): a `watchdog_margin = 0` mutation survives, because the held-lock test takes the lock-timeout path.
Verdict: all met. Moved to done on the product owner's standing instruction for this run.
