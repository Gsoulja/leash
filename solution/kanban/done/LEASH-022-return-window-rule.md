# LEASH-022: Return-window rule

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: S
**Milestone**: M2 — All five scenarios offline
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-001
**Task ID**: 001-T13
**Blocked by**: LEASH-014, LEASH-020
**Blocks**: LEASH-033, LEASH-128
**Updated**: 2026-09-23

## Description
Check the return window against the minimum days: final sale or non-returnable fails, unstated warns, shorter fails.

## Business Value
Requested-item scenario: final sale, 7-day returns, unstated policy, exactly 14 days.

## Acceptance Criteria
- [x] Exactly the minimum passes.
- [x] Final sale or `order_returnable=false` fails.
- [x] Unstated or `unknown` warns (missing is not permission).
- [x] Structured and text facts disagree → the stricter one wins (e.g. order_returnable=false beats '30 days' in text).

## Technical Approach
`domain/rules/returns.py`.

### Dependencies
- Needs LEASH-014.
- Needs LEASH-020.
- Blocks LEASH-033.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_exactly_14_days_passes`, `test_unknown_return_policy_asks`.

## Related Files
- `solution/engine/src/leash/domain/rules/returns.py`
- `solution/engine/tests/domain/rules/test_returns.py`

## Out of scope
- Cancellation windows.

## Review log

### 2026-09-23 — independent agent review (batch with LEASH-017/021/022/023)
- [x] met — criteria 1–4: all 48 Term × final_sale × days combinations probed; exact minimum passes; final sale / not returnable fail; unknown warns; stricter fact wins.
- Registered in `decide.DEFAULT_RULES` (outside Related Files; needed for the rule to take effect in `decide()`).
- Cosmetic wording notes only (odd text for empty allowed sets / exclusion-only rules); verdicts correct.
Check: rules suite 22 passed; full suite 404; mypy strict clean.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
