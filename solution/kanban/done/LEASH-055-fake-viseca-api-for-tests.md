# LEASH-055: Fake Viseca API for tests

**Status**: DONE
**Priority**: P0
**Type**: test
**Estimated Effort**: M
**Milestone**: M3 — Durable fake-API integration
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-004
**Task ID**: 004-T6
**Blocked by**: LEASH-030
**Blocks**: LEASH-056, LEASH-128
**Updated**: 2026-09-23

## Description
A local FastAPI app that mimics the hosted API for a scenario: mandates, runs, long-poll with deadlines, 204s, repeat delivery, decision and resolve endpoints.

## Business Value
End-to-end tests and rehearsals without the event-day key.

## Acceptance Criteria
- [x] Serves pack scenarios in replay_order with live IDs.
- [x] Can inject repeat delivery and slow queues.
- [x] Records received decisions for assertions.
- [x] Simulates ask expiry, conflicting answers, run progress and queue delay.

## Technical Approach
`tests/fake_api/app.py`.

### Dependencies
- Needs LEASH-030.
- Blocks LEASH-056.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_fake_api_serves_scenario_in_order`.

## Related Files
- `solution/engine/tests/fake_api/app.py`
- `solution/engine/tests/fake_api/test_fake_api.py`

## Out of scope
- Perfect fidelity to undocumented platform behaviour.

## Review log

### 2026-09-23 — independent agent review
- [ ] not met — criterion 1: all 45 events of the five scenarios validate against the official schema and match the pack field by field, but `related_authorization_id` was passed through as the pack ID; technical_details.md says the API rewrites it to the related purchase's live ID in that run (SCEN0004 AU0042 → AU0037).
- [x] met — criterion 2: repeat delivery (same live ID and deadline) and slow queues (deadline still counts from queueing).
- [x] met — criterion 3: accepted decisions and answers recorded (caveat: rejected posts weren't).
- [x] met — criterion 4: ask expiry, conflicting answers, run progress, queue delay; long-poll holds for `wait`.
- Minor doc contradiction: a mid-run revoke still queued later purchases (step 8: the platform rejects revoked mandates before queueing).
Verdict: returned to in-progress. Fix: related IDs rewritten to live IDs; a revoked mandate stops further queueing (run status "stopped"); refused posts recorded in `rejected` with their error code. Three new tests; 18 fake-API tests pass.

### 2026-09-23 — independent agent review (round 2)
- [x] met — all five scenarios (twice, approve and decline passes): counts match `event_count`, order matches replay_order, every event validates against the official schema, every field matches the CSVs with the documented types; related IDs rewritten to live IDs; live IDs change between runs; PATCH mid-run leaves the run snapshot unchanged.
- [x] met — repeat delivery and slow queues (deadline counts from queueing).
- [x] met — `received`, `resolutions` and `rejected` (status + error code). Reset now clears `rejected` too (fixed after review).
- [x] met — ask expiry, conflicting answers, not-waiting resolve, queue delay, long poll, run progress incl. "stopped" after revoke.
Notes (out of scope): `related_authorization_status` passes the pack value through; `approved_spend_in_period_chf` sums all approvals to the current simulated time because the docs don't define the period.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
