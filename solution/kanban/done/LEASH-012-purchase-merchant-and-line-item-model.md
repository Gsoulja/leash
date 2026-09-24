# LEASH-012: Purchase, merchant and line-item model

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: S
**Milestone**: M1 — SCEN0000 offline vertical slice
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-001
**Task ID**: 001-T3
**Blocked by**: LEASH-010, LEASH-011
**Blocks**: LEASH-014, LEASH-015, LEASH-020, LEASH-028, LEASH-030, LEASH-051, LEASH-128
**Updated**: 2026-09-23

## Description
Immutable domain model of a proposed purchase, independent of the Viseca event format, including fulfilment and quantities.

## Business Value
Every rule reads this model; keeping the API format out of the domain is the anti-corruption rule.

## Acceptance Criteria
- [x] Purchase carries live and source IDs, merchant, sim time, amount, currency, billing CHF, device, velocity, return/cancel tri-states, related order, line items.
- [x] Tri-state terms are typed (`true | false | unknown | not_applicable`); missing values stay missing.
- [x] Purchase includes fulfilment method.
- [x] `item_fingerprint` is the sorted multiset of (item_id, quantity).

## Technical Approach
Frozen dataclasses in `domain/purchase.py`. No parsing from JSON here (that's LEASH-051).

### Dependencies
- Needs LEASH-010.
- Needs LEASH-011.
- Blocks LEASH-014.
- Blocks LEASH-015.
- Blocks LEASH-020.
- Blocks LEASH-028.
- Blocks LEASH-030.
- Blocks LEASH-051.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_fingerprint_includes_quantities`, `test_unknown_return_term_is_not_true`.

## Related Files
- `solution/engine/src/leash/domain/purchase.py`
- `solution/engine/tests/domain/test_purchase.py`

## Out of scope
- JSON parsing and schema validation (LEASH-051).

## Review log

### 2026-09-23 — independent agent review (round 1)
- [x] met — criterion 1: every listed fact present, frozen, typed.
- [x] met — criterion 2: `Term` enum with the schema's four values; `bool()` raises so unknown can't read as yes; missing values stay None.
- [x] met — criterion 3: `fulfillment` field.
- [ ] not met — criterion 4: fingerprint summed quantities per item instead of one (item_id, quantity) pair per line.
Verdict: returned to in-progress. Fix: fingerprint is now the sorted per-line multiset; tests updated (split lines ≠ combined line).

### 2026-09-23 — independent agent review (round 2)
- [x] met — criteria 1–3 re-confirmed.
- [x] met — criterion 4: per-line sorted multiset; quantity, order and split-line cases tested.
Check: 10 passed; mypy strict clean.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
