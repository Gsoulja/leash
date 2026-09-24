# LEASH-054: Outbox sender

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: S
**Milestone**: M3 — Durable fake-API integration
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-004
**Task ID**: 004-T5
**Blocked by**: LEASH-044, LEASH-050
**Blocks**: LEASH-056, LEASH-127, LEASH-128
**Updated**: 2026-09-23

## Description
Send pending outbox rows (decision, resolve) and mark them sent; resend on restart.

## Business Value
No decision is lost if the process crashes after committing.

## Acceptance Criteria
- [x] Unsent rows are sent in order; success sets sent_at.
- [x] Failures increase attempts and retry with backoff.
- [x] Resending an already accepted decision is harmless.
- [x] The outbox sender only retries rows the worker could not send; it never delays the first send.

## Technical Approach
`adapters/viseca_api/outbox_sender.py`.

### Dependencies
- Needs LEASH-044.
- Needs LEASH-050.
- Blocks LEASH-056.
- Blocks LEASH-127.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_unsent_row_is_resent_after_restart`.

## Related Files
- `solution/engine/src/leash/adapters/viseca_api/outbox_sender.py`
- `solution/engine/tests/adapters/test_outbox_sender.py`

## Notes
- Migration 0003 adds `outbox.last_attempt_at` and `last_error` so backoff survives restarts.
- `mark_sent()` is the Postgres side of the use case's mark-sent step (LEASH-052).

## Out of scope
- Exactly-once delivery guarantees beyond idempotency.

## Review log

### 2026-09-23 — independent agent review
- [ ] not met — criterion 1: order held only while nothing failed; a resolve could overtake its own backing-off decision, get 409 not_waiting_for_customer and be closed for good (the customer's approval lost). Real now that LEASH-045 writes resolve rows.
- [x] met — criterion 2: every error class checked (network/5xx/429/408 retried; other 4xx closed with the error); backoff doubles to the cap and survives restarts.
- [x] met — criterion 3 against the fake platform (decision and resolve resends accepted once); the real platform's repeat behaviour is undocumented.
- [x] met — criterion 4: grace period and mark_sent; a slow worker send racing the sender resends the same body harmlessly.
Verdict: returned to in-progress. Fix: a row is eligible only when no earlier unsent row for the same authorization is pending (`test_a_resolve_never_overtakes_its_own_decision`). 589 pass; mypy clean.

### 2026-09-23 — independent agent review (round 2)
- [x] met — criterion 1: per-authorization order holds under failures, backoff, restarts and 4 concurrent senders; unrelated rows go ahead.
- [ ] not met — criterion 2: backoff was measured from the start of an attempt, so a failure slower than the backoff was retried at once in the same pass and held up unrelated rows.
- [x] met — criteria 3 and 4.
Verdict: returned to in-progress. Fix: `last_attempt_at` is taken when the attempt finished (`test_backoff_counts_from_when_a_slow_attempt_failed`).

### 2026-09-23 — independent agent review (round 3)
- [x] met — criteria 1, 3, 4; per-row backoff now counts from the failure.
- [ ] not met — criterion 2: a pass kept re-picking slow-failing rows whose backoff had run out mid-pass, starving a healthy row; with 7 rows timing out at 10 s the pass never ended.
Verdict: returned to in-progress. Fix: a pass tries each row at most once (`test_one_pass_tries_each_row_at_most_once`). 605 pass.

### 2026-09-23 — independent agent review (round 4)
- [x] met — criterion 1: 4 concurrent senders, 6 authorizations with failing decisions: no resolve ever before its decision; all rows sent.
- [x] met — criterion 2: 14 slow failures then a healthy row → healthy sent in the same pass; 7 × 10 s timeouts finish; backoff grows 1→2→4→8→16 s across restarts. Caveat: a pass never ended while new failing rows kept arriving — fixed after review: a pass covers only rows that existed when it started (`test_a_pass_only_covers_rows_that_existed_when_it_started`).
- [x] met — criteria 3 and 4.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
