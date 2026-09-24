# LEASH-028: Purchase and mandate state machines

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: S
**Milestone**: M1 — SCEN0000 offline vertical slice
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-001
**Task ID**: 001-T19
**Blocked by**: LEASH-012, LEASH-013
**Blocks**: LEASH-032, LEASH-043, LEASH-128
**Updated**: 2026-09-23

## Description
Explicit transition tables: purchase received → approved/declined/waiting → approved/declined/timed_out; mandate draft → active → revoked/expired.

## Business Value
Prevents illegal transitions such as resolving a final purchase or confirming a revoked mandate.

## Acceptance Criteria
- [x] Allowed transitions succeed; any other raises IllegalTransition.
- [x] Only a customer or the platform can end a waiting purchase.

## Technical Approach
`domain/states.py`.

### Dependencies
- Needs LEASH-012.
- Needs LEASH-013.
- Blocks LEASH-032.
- Blocks LEASH-043.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_cannot_resolve_already_declined`, `test_revoked_mandate_cannot_activate`.

## Related Files
- `solution/engine/src/leash/domain/states.py`
- `solution/engine/tests/domain/test_states.py`

## Out of scope
- Persistence of state (LEASH-043).

## Review log

### 2026-09-23 — independent agent review
- [x] met — criterion 1: all 126 purchase and 60 mandate state×state×actor combinations enumerated; exactly the 8 and 4 listed transitions succeed, all others raise IllegalTransition (incl. unknown states/actors).
- [x] met — criterion 2: only customer (approve/decline) or platform (timed_out) end a wait; engine can't.
Check: 45 passed; mypy strict clean.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
