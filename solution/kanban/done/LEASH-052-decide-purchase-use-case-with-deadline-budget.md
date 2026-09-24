# LEASH-052: Decide-purchase use case with deadline budget

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M3 — Durable fake-API integration
**Rule source**: Engineering
**Decisions**: DEC-007, DEC-008, DEC-009
**Parent**: LEASH-004
**Task ID**: 004-T3
**Blocked by**: LEASH-027, LEASH-043, LEASH-020, LEASH-122
**Blocks**: LEASH-053, LEASH-102, LEASH-128
**Updated**: 2026-09-23

## Description
Pipeline: validate → dedupe → read facts (outside the lock) → lock → rebuild snapshot → decide → persist with outbox → commit → POST immediately → mark sent. A deadline budget from deadline_at drives a watchdog that sends a safe step_up when remaining time falls below the margin.

## Business Value
Guarantees an answer before the 8 s deadline even when something stalls.

## Acceptance Criteria
- [x] Each stage is timed and logged.
- [x] A reader that times out yields regex facts marked 'model unavailable'.
- [x] Repeat delivery short-circuits to the saved verdict.
- [x] The watchdog margin accounts for lock wait and send time, not only reader time.
- [x] Decisions always use the event's mandate snapshot, never the current local mandate.

## Technical Approach
`application/decide_purchase.py`, tested with fakes for repository and reader.

### Dependencies
- Needs LEASH-027.
- Needs LEASH-043.
- Needs LEASH-020.
- Needs LEASH-122.
- Blocks LEASH-053.
- Blocks LEASH-102.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_watchdog_sends_step_up_when_reader_hangs`.

## Related Files
- `solution/engine/src/leash/application/decide_purchase.py`
- `solution/engine/tests/application/test_decide_purchase.py`

## Notes
- The use case talks to a `DecisionStore` port (receive, decide, record_fallback, mark_sent) and a `Sender`; tested with fakes as the ticket specifies. The Postgres `record_fallback`/`mark_sent` and the HTTP sender are wired with the worker and outbox (LEASH-053/054).

## Out of scope
- HTTP polling (LEASH-053).

## Review log

### 2026-09-23 — independent agent review
- [x] met — every stage timed and logged with the authorization ID (normal, watchdog and repeat paths).
- [x] met — a timed-out reader yields regex facts marked model unavailable (real FallbackReader); a raw hanging reader is covered by the watchdog; a hung reader thread blocks neither the loop nor shutdown.
- [x] met — repeat delivery resends the saved body; an in-flight repeat does nothing.
- [ ] not met — criterion 4: the reader budget was right, but the watchdog margin covered only the send: a slow `record_fallback` (+0.70 s) or slow rollback cleanup after cancellation (+0.20 s) pushed the step_up past the deadline; a commit landing at the watchdog boundary could leave a committed approve while step_up was sent. The sender had no timeout.
- [x] met — decisions use the event's mandate only.
- Minor: a `mark_sent` failure after a successful send raised.
Verdict: returned to in-progress. Fix: watchdog margin = fallback + send; the stalled work is cancelled without waiting for its cleanup; `record_fallback` is bounded and conditional (only if nothing committed — otherwise the committed decision is returned and sent), a failure to record is logged as an integrity problem and the step_up still goes out; sends are bounded; mark_sent failures are logged. Five new tests; 563 pass (×3); mypy clean.

### 2026-09-23 — independent agent review (round 2)
- [x] met — criteria 1, 2, 3, 5; the round-1 timing fixes hold (every path answered before the deadline; sent always equals stored across a commit swept around the watchdog).
- [ ] not met — criterion 4: a LockTimeout (or any failure) from the decision work got no answer at all; dedupe (`receive`) was outside the watchdog (a slow receive answered after the deadline); a late cleanup exception could go unretrieved.
- Residual by design: if locks stay held longer than `fallback_seconds`, the sent step_up can differ from what later commits — logged as an integrity error.
Verdict: returned to in-progress. Fix: the watchdog now covers dedupe through commit; any failure of that work takes the same safe step_up path (recorded conditionally, so repeats resend it); abandoned work gets a done-callback that retrieves its exception. Tests for all three; 589 pass; mypy clean.

### 2026-09-23 — independent agent review (round 3)
- [x] met — all five criteria. Every path timed against the deadline with fakes and real Postgres: slow/hanging/failing receive, slow/stalled/failing decide, fake and real LockTimeout (0.30 s), a lock wait longer than the watchdog (step_up at 1.42 s; the server query was cancelled, row stays `received`), slow cleanup, hanging sender, failing mark_sent. Commit swept 1.30–1.45 s around the watchdog: sent always equalled stored. No unretrieved exceptions or thread warnings; repeats after a fallback resend it.
- By design (documented): if recording the fallback hangs or fails, the step_up is still sent and an INTEGRITY error logged. Minor: a store raising CancelledError on its own is re-raised (not realistic with asyncpg).
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
