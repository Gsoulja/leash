# LEASH-030: Challenge-pack loader

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M1 — SCEN0000 offline vertical slice
**Rule source**: Engineering
**Decisions**: DEC-011
**Parent**: LEASH-002
**Task ID**: 002-T1
**Blocked by**: LEASH-012, LEASH-015
**Blocks**: LEASH-032, LEASH-042, LEASH-055, LEASH-100, LEASH-121, LEASH-128
**Updated**: 2026-09-23

## Description
Load merchants, history, purchase attempts and cart lines from data/ into domain objects, and build familiarity from approved history.

## Business Value
Offline replay and seeding both need the pack as domain objects.

## Acceptance Criteria
- [x] All 45 attempts load with their cart lines, sorted by replay_order.
- [x] Empty CSV fields become None, amounts Decimal, times SimTime.
- [x] Joins are by ID only.
- [x] Card CA0039 shows 6 approved payments at ME0022.
- [x] Distinguishes purchases, refunds, cash withdrawals and declines; familiarity uses approved purchases only.

## Technical Approach
`adapters/pack/loader.py`. Reads CSVs only.

### Dependencies
- Needs LEASH-012.
- Needs LEASH-015.
- Blocks LEASH-032.
- Blocks LEASH-042.
- Blocks LEASH-055.
- Blocks LEASH-100.
- Blocks LEASH-121.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_loads_45_attempts_with_items`, `test_familiarity_counts_approved_only`.

## Related Files
- `solution/engine/src/leash/adapters/pack/loader.py`
- `solution/engine/tests/adapters/test_pack_loader.py`

## Out of scope
- Writing to the database (LEASH-042).

## Review log

### 2026-09-23 — independent agent review
- [x] met — criterion 1: 45 attempts, 56 lines, sorted by replay_order; lines by line_no.
- [x] met — criterion 2: empty fields → None; Decimal amounts; SimTime; Term tri-states; dates.
- [x] met — criterion 3: joins by merchant_id / authorization_id / card_id only; lookalike resolves by ID.
- [x] met — criterion 4: CA0039 × ME0022 = 6.
- [x] met — criterion 5: transaction types and statuses kept; CA0011 × ME0028 = 22 (refund excluded).
Independent cross-check: all 45 attempts × 14 fields vs raw CSV, 0 mismatches. Check: 7 passed; mypy clean.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
