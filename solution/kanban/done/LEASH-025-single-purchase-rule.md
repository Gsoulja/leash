# LEASH-025: Single-purchase rule

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: S
**Milestone**: M2 — All five scenarios offline
**Rule source**: Team
**Decisions**: DEC-013
**Parent**: LEASH-001
**Task ID**: 001-T16
**Blocked by**: LEASH-014, LEASH-015
**Blocks**: LEASH-033, LEASH-128
**Updated**: 2026-09-23

## Description
When the mandate asks for one purchase, warn on any later matching purchase after one was approved.

## Business Value
'Buy the monitor I chose', 'replace my shoes': a second compliant order should not go through silently.

## Acceptance Criteria
- [x] After an approved matching purchase, the next one warns 'you already bought…'.
- [x] Nothing approved yet: no check.

## Technical Approach
`domain/rules/single.py`. Assumption until LEASH-110.

### Dependencies
- Needs LEASH-014.
- Needs LEASH-015.
- Blocks LEASH-033.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_second_monitor_after_approval_asks`.

## Related Files
- `solution/engine/src/leash/domain/rules/single.py`
- `solution/engine/tests/domain/rules/test_single.py`

## Out of scope
- Quantity inside one order (handled by LEASH-019).

## Review log

### 2026-09-23 — independent agent review
- [x] met — criterion 1: after an approved matching purchase the next warns "You already bought…" (with and without item IDs; non-target purchases unaffected; limit 2 allows the second).
- [ ] not met — criterion 2: a zero limit (`max_count < 1` or `<= 0`) with no approvals crashed with IndexError inside decide().
- Outside the criteria: under `approve`/`decline` policies the warning follows the uncertainty policy — recorded as DEC-030 (Open).
Verdict: returned to in-progress. Fix: a zero limit warns "Your rule allows no purchases of this." (`test_a_zero_limit_warns_without_crashing`). 460 tests pass; mypy clean.

### 2026-09-23 — independent agent review (round 2)
- [x] met — criterion 1: after the approved count reaches the limit the next matching purchase warns naming the latest one; limit 2 warns on the third; non-target purchases unaffected; a redelivered authorization doesn't count against itself.
- [x] met — criterion 2: no check with only waiting/declined/timed-out priors; zero, fractional and negative limits warn without crashing.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
