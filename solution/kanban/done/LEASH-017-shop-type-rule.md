# LEASH-017: Shop-type rule

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: S
**Milestone**: M2 — All five scenarios offline
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-001
**Task ID**: 001-T8
**Blocked by**: LEASH-014
**Blocks**: LEASH-033, LEASH-128
**Updated**: 2026-09-23

## Description
Check the merchant's category against the allowed shop types (e.g. 'specialist sports retailer' = sporting_goods).

## Business Value
Requested-item scenario: GreenLoop (sustainable goods) must fail.

## Acceptance Criteria
- [x] Allowed category passes; others fail with the shop's actual type named.
- [x] No shop-type restriction produces no check.

## Technical Approach
`domain/rules/shop_type.py`.

### Dependencies
- Needs LEASH-014.
- Blocks LEASH-033.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_sustainable_goods_shop_fails_specialist_rule`.

## Related Files
- `solution/engine/src/leash/domain/rules/shop_type.py`
- `solution/engine/tests/domain/rules/test_shop_type.py`

## Out of scope
- Deriving basket item categories from the shop category (forbidden by the data contract).

## Review log

### 2026-09-23 — independent agent review (batch with LEASH-017/021/022/023)
- [x] met — criterion 1: allowed passes, others fail naming the real type (incl. exclusions); criterion 2: no restriction → no check.
- Registered in `decide.DEFAULT_RULES` (outside Related Files; needed for the rule to take effect in `decide()`).
- Cosmetic wording notes only (odd text for empty allowed sets / exclusion-only rules); verdicts correct.
Check: rules suite 22 passed; full suite 404; mypy strict clean.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
