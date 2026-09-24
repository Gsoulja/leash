# LEASH-021: Size rule

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: S
**Milestone**: M2 — All five scenarios offline
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-001
**Task ID**: 001-T12
**Blocked by**: LEASH-014, LEASH-020
**Blocks**: LEASH-033, LEASH-128
**Updated**: 2026-09-23

## Description
Compare stated sizes with the requested size.

## Business Value
Requested-item scenario: size 42 instead of 43.

## Acceptance Criteria
- [x] Wrong size fails; missing size warns; matching size passes.

## Technical Approach
`domain/rules/size.py`.

### Dependencies
- Needs LEASH-014.
- Needs LEASH-020.
- Blocks LEASH-033.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_size_42_fails_when_43_requested`, `test_missing_size_asks`.

## Related Files
- `solution/engine/src/leash/domain/rules/size.py`
- `solution/engine/tests/domain/rules/test_size.py`

## Out of scope
- Size conversion between systems (EU/US).

## Review log

### 2026-09-23 — independent agent review (batch with LEASH-017/021/022/023)
- [x] met — criterion 1: wrong size fails, missing warns, matching passes; exclusions and several stated sizes probed.
- Registered in `decide.DEFAULT_RULES` (outside Related Files; needed for the rule to take effect in `decide()`).
- Cosmetic wording notes only (odd text for empty allowed sets / exclusion-only rules); verdicts correct.
Check: rules suite 22 passed; full suite 404; mypy strict clean.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
