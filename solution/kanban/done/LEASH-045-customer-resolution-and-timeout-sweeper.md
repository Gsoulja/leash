# LEASH-045: Customer resolution and timeout sweeper

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M3 — Durable fake-API integration
**Rule source**: Engineering
**Decisions**: DEC-012, DEC-016
**Parent**: LEASH-003
**Task ID**: 003-T6
**Blocked by**: LEASH-044, LEASH-122
**Blocks**: LEASH-056, LEASH-063, LEASH-128
**Updated**: 2026-09-23

## Description
Record the customer's answer under the same per-card lock, and time out waiting purchases after 120 s.

## Business Value
Covers the human approval and rejection path.

## Acceptance Criteria
- [x] Approve moves waiting → approved and adds spend; decline → declined.
- [x] Resolving a non-waiting purchase fails.
- [x] Each resolution writes an outbox row for /resolve.
- [x] The answer window comes from bootstrap and is stored as an explicit expiry per ask.
- [x] Hard rules are re-checked under the lock when the customer answers; a now-failing limit can't be approved and the record stays truthful.
- [x] After the configured window a waiting purchase becomes timed_out and is not spend.

## Technical Approach
`application/resolve.py`, sweeper task. Timeout treatment is an assumption until LEASH-110.

### Dependencies
- Needs LEASH-044.
- Needs LEASH-122.
- Blocks LEASH-056.
- Blocks LEASH-063.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_customer_approval_adds_spend`, `test_ask_times_out_after_120s`.

## Related Files
- `solution/engine/src/leash/application/resolve.py`
- `solution/engine/tests/application/test_resolve.py`

## Notes
- Postgres side: `ResolutionTransaction` (resolve, sweep) in adapters/postgres/unit_of_work.py, under the same per-card lock as decisions. The run's compiled mandate comes through a `MandateSource` port (the mandate serializer, LEASH-060, is still blocked).
- The expiry per ask is written when the decision transaction records a step_up (`ask_expires_at`, from the bootstrap window via DecidePurchase).

## Out of scope
- Push notifications to phones.

## Review log

### 2026-09-23 — independent agent review
- [x] met — approve → approved and counts as spend for later decisions; decline → declined and doesn't.
- [x] met — resolving received, timed_out, engine-declined, approved or already-answered purchases raises IllegalTransition (unknown ID → KeyError, bad answer → ValueError); no state change, no outbox row.
- [x] met — exactly one /resolve outbox row per accepted answer; body {decision, customer_message, evidence}.
- [x] met — expiry per ask stored from the bootstrap window (BootstrapSettings → RuntimeSettings → DecidePurchase → ask_expires_at); resolve and sweep use the stored value. Caveat: no production code constructs DecidePurchase yet (worker wiring, LEASH-053).
- [x] met — hard rules re-checked under the card lock: period and per-order limits block with the reason, nothing recorded, only decline remains; racing approvals under one limit → one approved. Warnings (duplicate, single purchase) don't block (DEC-012).
- [x] met — expired asks become timed_out (not spend); sweeper idempotent; answer-vs-sweeper races leave exactly one outcome.
Note: a lock timeout on one card no longer stops the sweep for others (fixed after review, `test_a_locked_card_does_not_stop_the_sweep_for_others`).
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
