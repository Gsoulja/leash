# LEASH-024: Duplicate and split-order detection

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M2 — All five scenarios offline
**Rule source**: Engineering
**Decisions**: DEC-023
**Parent**: LEASH-001
**Task ID**: 001-T15
**Blocked by**: LEASH-014, LEASH-015
**Blocks**: LEASH-033, LEASH-128
**Updated**: 2026-09-23

## Description
Warn on a purchase identical to an approved or waiting one (same merchant, items, amount within 24 h), and on a second order at the same shop within an hour that together exceed the per-order limit.

## Business Value
Manipulated-agent duplicate; household-budget split order.

## Acceptance Criteria
- [x] Identical order within 24 h warns as duplicate, naming the earlier order's time and state.
- [x] Two orders within 60 min at one shop totalling over the limit warn as possible split.
- [x] Split isn't reported when the purchase is already a duplicate.
- [x] Fingerprints compare item IDs with quantities.
- [x] A re-quote of a declined order (related_authorization_status=declined) is not a duplicate of it.

## Technical Approach
`domain/rules/duplicates.py`.

### Dependencies
- Needs LEASH-014.
- Needs LEASH-015.
- Blocks LEASH-033.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_same_monitor_25_minutes_later_asks`, `test_70_plus_65_within_6_minutes_asks`.

## Related Files
- `solution/engine/src/leash/domain/rules/duplicates.py`
- `solution/engine/tests/domain/rules/test_duplicates.py`

## Out of scope
- Cross-card duplicate detection.

## Review log

### 2026-09-23 — independent agent review
- [x] met — identical order within 24 h warns naming the earlier order's Zurich time and state; approved and waiting count, declined/timed_out don't; 23:59:59 warns, exactly 24 h doesn't.
- [x] met — split within 60 min over the per-order limit warns; 59:59 warns, 60:00 doesn't; exactly at a `<=` limit doesn't, at a `<` limit does; needs split check + per-order limit.
- [x] met — split isn't reported when already a duplicate (also when they'd match different earlier orders).
- [x] met — fingerprint compares item IDs with quantities, independent of line order (per line: 2×1 ≠ 1×2).
- [x] met — a re-quote of a declined order (live or source ID) isn't its duplicate.
Note: the outcome under `approve`/`decline` policies follows the uncertainty policy; recorded as DEC-030 (Open).
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
