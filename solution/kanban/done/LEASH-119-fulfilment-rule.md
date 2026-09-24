# LEASH-119: Fulfilment rule

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: S
**Milestone**: M2 — All five scenarios offline
**Rule source**: Viseca brief
**Decisions**: DEC-022
**Parent**: LEASH-001
**Task ID**: 001-T20
**Blocked by**: LEASH-014, LEASH-117
**Blocks**: LEASH-033, LEASH-128
**Updated**: 2026-09-23

## Description
Check the purchase's fulfilment method against the mandate (e.g. 'for delivery').

## Business Value
Household-budget instruction requires delivery; a pickup or digital order must not pass silently.

## Acceptance Criteria
- [x] A pickup or digital order fails a delivery rule with a plain reason.
- [x] No fulfilment rule: no check.
- [x] The compiled SCEN0001 mandate includes the delivery rule.

## Technical Approach
`domain/rules/fulfilment.py`, field `authorization.fulfillment_method`.

### Dependencies
- Needs LEASH-014.
- Needs LEASH-117.
- Blocks LEASH-033.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_pickup_fails_delivery_rule`.

## Related Files
- `solution/engine/src/leash/domain/rules/fulfilment.py`
- `solution/engine/tests/domain/rules/test_fulfilment.py`

## Notes
- Registered in DEFAULT_RULES and in the field registry's EVALUATORS (the field is no longer pending). An unknown or missing method warns (`fulfilment_unknown`, uncertainty policy) — missing is not permission.

## Out of scope
- Delivery dates.

## Review log

### 2026-09-23 — independent agent review
- [x] met (core) — criterion 1: pickup/digital fail a delivery rule with a plain reason under every policy; !=, not_in and strictest-wins work; the order's method is normalised. Safety gap: the rule's own values weren't normalised — `not_in ("Pickup",)` let a pickup order be approved; `in (" Delivery ",)` wrongly declined delivery. Contradictory mandates gave wrong wording (verdict right).
- [x] met — criterion 2.
- [x] met — criterion 3 (SCEN0001 replay unchanged; all its purchases are delivery).
Verdict: returned to in-progress. Fix: rule values are trimmed and lower-cased like the order's method; contradictory mandates explain themselves ("allow no fulfilment method", "which you excluded"). Two new tests; 635 pass; mypy clean.

### 2026-09-23 — independent agent review (round 2)
- [x] met for single rules — criterion 1 (capitalised/padded values on both sides, every policy); [ ] not met across several rules: values were normalised only after the mandate intersected them, so `in ("Delivery",)` + `in ("delivery",)` declined a delivery order as "allow no fulfilment method"; `in ("",)` gave garbled wording.
- [x] met — criteria 2 and 3.
Verdict: returned to in-progress. Fix: each fulfilment rule is normalised before rules are combined (strictest wins on normalised values); empty values dropped. `test_rules_differing_only_in_case_or_spacing_combine_correctly`, `test_an_empty_allowed_value_reads_sensibly`. 666 pass.

### 2026-09-23 — independent agent review (final round)
- [x] met — criterion 1: under every policy pickup/digital decline with plain reasons; case/spacing across several rules now combine correctly; empty values handled; contradictory mandates worded sensibly.
- [x] met — criteria 2 and 3.
Note: empty *excluded* values garbled the agreed text ("never ") — fixed after review (`test_an_empty_excluded_value_is_ignored`).
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
