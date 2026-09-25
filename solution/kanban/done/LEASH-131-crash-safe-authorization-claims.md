# LEASH-131: Crash-safe authorization claims

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M7 — Production hardening
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-129
**Task ID**: 129-T2
**Blocked by**: none
**Blocks**: LEASH-128, LEASH-142, LEASH-143
**Updated**: 2026-09-25

## Description
Replace the in-memory meaning of `in_flight` with a durable processing claim that can be reclaimed after a worker dies.

## Business Value
No authorization may remain unanswered merely because a worker crashed after recording receipt.

## Acceptance Criteria
- [x] A received authorization has a claim owner and lease expiry, or an equivalent durable claim.
- [x] A concurrent live owner prevents duplicate decision work.
- [x] A redelivery reclaims an expired claim and completes the decision.
- [x] A worker refreshes or releases its claim during normal handling and graceful shutdown.
- [x] Reclaiming work preserves per-card serialization and idempotency.
- [x] A crash at every boundary from receive through commit has a documented recovery path.

## Technical Approach
Use an atomic database claim with a bounded lease. Treat a missing response as recoverable state, not proof that another process is alive.

### Dependencies
- Blocks LEASH-128.
- Blocks LEASH-142.
- Blocks LEASH-143.

## Testing Requirements
Write failing tests for crash-after-receive, two-worker contention, lease expiry, reclaim, and redelivery after restart.

## Related Files
- `solution/engine/src/leash/application/decide_purchase.py`
- `solution/engine/src/leash/adapters/postgres/repository.py`
- `solution/engine/src/leash/adapters/postgres/unit_of_work.py`
- `solution/engine/src/leash/adapters/viseca_api/worker.py`

## Out of scope
- General distributed job scheduling unrelated to authorizations.

## Implementation note (2026-09-24)
- Migration `0006_authorization_claims.py`: `authorizations.claim_owner`, `authorizations.claim_expires_at`; `decision_events.kind` also allows `reclaimed`.
- `PostgresRepository.receive(..., owner, lease_seconds)` claims atomically in one `insert … on conflict do update … where` on the database clock:
  - a new row is claimed;
  - a row still `received` whose claim expired (or has none) is taken over, logged and recorded as `reclaimed`;
  - a live claim returns "in flight"; an answered row returns the saved decision.
  - Without an owner it behaves as before.
- `refresh_claim` (owner and state `received` only) and `release_claim`. `PostgresDecisionStore` has an owner per process (`host:pid:random`) and a 3 s lease; the in-memory store has no-op claims.
- `DecidePurchase`: once it holds the claim, a heartbeat refreshes it every `claim_refresh_seconds` (worker: lease / 3) while the work runs; the claim is released when handling ends, after the watchdog, and on cancellation (the inner work is cancelled too). A failing refresh or release is logged and never stops the answer.
- Per-card serialization and idempotency are unchanged: a reclaimed decision goes through the same advisory-locked transaction, and a stale owner's commit is refused by the `received → …` transition, after which it sends the stored decision.
- Recovery for every crash point: RUNBOOK.md section 6a.
- Tests (red first):
  - `tests/adapters/test_claims.py`: owner and lease on receive; live claim blocks a second worker; expired claim reclaimed on redelivery; only one of two concurrent reclaims wins; answered rows never reclaimed; stale owner can't commit and spend/outbox count once; refresh/release; crash after receive then a redelivery after restart completes the decision.
  - `tests/application/test_decide_purchase.py`: refresh while working, release after handling, after the watchdog and on cancellation, no refresh/release for work in flight elsewhere, a failing refresh never stops the decision.
- Registry re-pinned (shared code and migrations; no field meaning changed). 1386 tests pass, mypy clean; the browser journey passes.

## Review log

### 2026-09-24 — independent agent review
- [x] met — criterion 1: owner and lease on the database clock (migration 0006); pinned by the owner/lease and column tests.
- [x] met — criterion 2: one atomic claim statement; removing the expiry condition turns the contention tests red. No path found where two workers decide under live claims.
- [x] met as worded — criterion 3: reclaim and completion tested, but only with a manually expired lease.
- [x] met — criterion 4: heartbeat and release tested (mutations red); the worker shields the event in hand on stop.
- [x] met — criterion 5: same advisory-locked transaction; stale owner refused; one decided event and one outbox row; clocks don't mix. Gap: dropping the owner check from `release_claim` failed no test.
- [ ] not met — criterion 6: a redelivery arriving *inside* a dead owner's lease returned `in_flight` and sent nothing; without a third delivery the purchase was never answered, and RUNBOOK 6a said otherwise.
- Observation: if recording the watchdog's step_up fails, the released claim lets a redelivery decide again (no double commit).
Verdict: returned to in-progress.

### Fixes after review (2026-09-24)
- A delivery that finds the work claimed elsewhere no longer gives up: it re-checks every 0.2 s until the owner's answer is stored (sent as a repeat) or the lease lapses (taken over and decided); the watchdog still sends a safe step_up before the deadline. The `in_flight` path is gone.
- Tests (red first): waits for the owner's answer and sends it; takes over when the dead owner's lease lapses; never an answer → safe step_up before the deadline. Pinned: a lease that isn't refreshed runs out by itself; a stale owner's release never frees the new owner's claim.
- RUNBOOK 6a row corrected. Registry re-pinned. 1390 tests pass, mypy clean, browser journey passes.

### 2026-09-24 — independent agent review, round 2
- [x] met — criteria 1–6. Checked against real Postgres: a redelivery inside a live 3 s lease waited, took over and approved (`received, reclaimed, decided`); an owner lease longer than the watchdog gave a safe step_up and the stale owner's commit was refused; two concurrent redeliveries gave one decision and one outbox row; a live owner's commit was sent as a repeat. Disabling the re-check loop and dropping the owner check in `release_claim` each turn tests red.
- Notes (not failing any criterion): the worker handles one event at a time, so a waiting redelivery holds the poll loop up to the lease (3 s) after a crash, or up to its watchdog if another worker is alive but stalled; a queued purchase past its watchdog then gets the safe step_up. The INTEGRITY line for a mandate mismatch repeats on each re-check. A cancellation exactly as `receive` returns leaves the claim to expire by itself (3 s).
Verdict: all met; moved to review.
