# LEASH-044: Decision transaction with lock, log, outbox and notify

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M3 — Durable fake-API integration
**Rule source**: Engineering
**Decisions**: DEC-007
**Parent**: LEASH-003
**Task ID**: 003-T5
**Blocked by**: LEASH-043, LEASH-027
**Blocks**: LEASH-045, LEASH-053, LEASH-054, LEASH-064, LEASH-128
**Updated**: 2026-09-23

## Description
One transaction per decision: per-card advisory lock, snapshot, save verdict, append event, write outbox row, NOTIFY for step_up.

## Business Value
Prevents two approvals slipping under a limit at once and makes crashes recoverable.

## Acceptance Criteria
- [x] Two concurrent decisions on one card are serialised.
- [x] Decision, event and outbox row commit together or not at all.
- [x] A step_up emits NOTIFY on channel `asks`.
- [x] Laya runs before the transaction, never inside the lock.
- [x] Order is: lock → rebuild snapshot → decide → save → commit; facts are read before the lock.
- [x] Lock wait is bounded by lock_timeout so the deadline can still be met.

## Technical Approach
`adapters/postgres/unit_of_work.py`.

### Dependencies
- Needs LEASH-043.
- Needs LEASH-027.
- Blocks LEASH-045.
- Blocks LEASH-053.
- Blocks LEASH-054.
- Blocks LEASH-064.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_concurrent_approvals_respect_period_limit`.

## Related Files
- `solution/engine/src/leash/adapters/postgres/unit_of_work.py`
- `solution/engine/tests/adapters/test_decision_transaction.py`

## Out of scope
- HTTP sending.

## Review log

### 2026-09-23 — independent agent review
- [x] met — serialised: 10 and 20 concurrent CHF 50 purchases under a CHF 300 week limit (8 runs) always approved exactly 6; with a per-purchase lock key the probe approved all 15, so it detects missing serialisation; other cards unblocked (~21 ms while card A was locked).
- [x] met — atomic: failures injected at snapshot, decide, explain, save, event, outbox, NOTIFY, COMMIT and a cancellation all left the purchase `received`, no outbox row, only the `received` event, no notification; pooled connection returned clean.
- [x] met — NOTIFY `asks` only for step_up and only on commit.
- [x] met — facts are an input; only Postgres and the pure core run inside the transaction.
- [x] met — stage order lock → snapshot → decide → save → commit.
- [x] met — lock waits bounded (100/300/800 ms measured), transaction-local, failed attempt leaves `received`.
Risks found and fixed after review: serialisation depended on the server's default isolation (under `repeatable read` CHF 600 was approved against CHF 300) — READ COMMITTED is now pinned (`test_serialisation_does_not_depend_on_the_database_default_isolation`, which fails without the pin); a row-lock timeout surfaced as a raw error — any lock timeout in the transaction is now `LockTimeout` (`test_a_row_lock_timeout_is_also_a_lock_timeout`).
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
