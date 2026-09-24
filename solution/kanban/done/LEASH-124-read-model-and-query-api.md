# LEASH-124: Read model and query API

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M4 — Customer-control journey
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-005
**Task ID**: 005-T11
**Blocked by**: LEASH-043, LEASH-118
**Blocks**: LEASH-125, LEASH-128
**Updated**: 2026-09-23

## Description
Durable read endpoints for the app: payments with engine and final verdicts, checks, evidence, the payload sent to Viseca, open asks with expiry, spending totals, mandate versions.

## Business Value
The app needs initial state; the event stream only carries changes.

## Acceptance Criteria
- [x] A reconnecting app gets all current state from the API.
- [x] Spending totals match the ledger.
- [x] Engine verdict and customer outcome are separate fields.

## Technical Approach
Projections in Postgres + FastAPI routes.

### Dependencies
- Needs LEASH-043.
- Needs LEASH-118.
- Blocks LEASH-125.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_open_asks_include_expiry`.

## Related Files
- `solution/engine/src/leash/adapters/http/query_api.py`
- `solution/engine/tests/adapters/test_query_api.py`

## Notes
- Implemented: `/api/payments` (+ `run_id`), `/api/payments/{id}`, `/api/asks` (with `can_approve` re-checked now, DEC-012), `/api/spending` (+ `run_id`, latest run by default), `/api/mandates/{id}/versions`. Each response validates against contracts/policy-api.yaml.
- `/api/mandates` (plain-language rule view, current mandate) needs the mandate serializer/service (LEASH-060/061) and is left to it.
- Decisions now also store which fact reader produced them (for the detail view).

## Out of scope
- Analytics.

## Review log

### 2026-09-23 — independent agent review
- [x] met — criterion 1: a full run through the real transactions (approvals, declines, customer answers, sweeper timeouts, open and expired asks, a received purchase, a repeat delivery) — every endpoint matched the tables, validated against the contract, and was identical on reconnect; shop text returned as plain JSON strings.
- [ ] not met — criterion 2: totals matched the ledger, but `mismatch` compared the platform counter (spend *before* the last purchase) with the total including it → false alarms in normal runs; without a period rule it compared against the all-time sum.
- [x] met — criterion 3: every verdict/outcome/resolver combination separate; `can_approve` agrees with a real approval both ways.
- Minor: a purchase still `received` shows as `waiting` with a null engine verdict (the contract has no `received` state).
Verdict: returned to in-progress. Fix: the counter is compared with our ledger at the same point (the window ending at the last purchase, without it); no comparison without a period rule. `test_the_platform_counter_is_compared_with_spend_before_that_purchase`.

### 2026-09-23 — independent agent review (round 2)
- [x] met — criteria 1 and 3; criterion 2 totals equal an independent SQL sum in every case; round-1 false alarms fixed.
- [ ] not met — criterion 2: `mismatch` still compared the counter with today's ledger, not the ledger when the purchase arrived: an ask approved after the next purchase arrived raised a false alarm. With several period rules it compared `periods[0]`, unlike the engine.
Verdict: returned to in-progress. Fix: compare with approvals recorded (decision_events order) before the last purchase was received; only a single period rule is compared, as in the engine. `test_an_ask_approved_after_the_next_purchase_arrived_is_not_a_mismatch`; fixture counters made realistic. 605 pass.

### 2026-09-23 — independent agent review (round 3)
- [x] met — criterion 1: full run incl. sweeper timeout, repeat delivery, expired ask; all endpoints validate against the contract; identical on reconnect.
- [x] met — criterion 2: 49 probes (asks resolved before/after later purchases, right and wrong counters, repeats with differing counters, two period rules, no rule, null counter, empty run, out-of-window, exact 7-day boundary): flag exact both ways; approved_chf equals an independent SQL sum.
- [x] met — criterion 3: every verdict/outcome/resolver combination.
Note: "before the purchase arrived" means before we logged it as received, not when Viseca queued it (can't be staged offline).
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
