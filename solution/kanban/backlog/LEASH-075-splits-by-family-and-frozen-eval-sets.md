# LEASH-075: Splits by family and frozen eval sets

**Status**: BACKLOG
**Priority**: P2
**Type**: feature
**Estimated Effort**: M
**Milestone**: M6 — Differentiators (after MVP)
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-006
**Task ID**: 006-T6
**Blocked by**: LEASH-073
**Blocks**: LEASH-076, LEASH-077
**Updated**: 2026-09-23

## Description
Split by attack family into train, calibration and eval; freeze held-out family, language, NotInject and the 56 pack lines.

## Business Value
Honest scores on attacks the model never saw.

## Acceptance Criteria
- [ ] No family appears in more than one split.
- [ ] Pack lines never appear in train.
- [ ] Eval sets are hashed and read-only.
- [ ] Optional public datasets (LEASH-074) are included when available, never required.

## Technical Approach
`training/splits.py`.

### Dependencies
- Needs LEASH-073.
- Blocks LEASH-076.
- Blocks LEASH-077.

## Testing Requirements
Write first: `test_no_family_leaks_across_splits`.

## Related Files
- `solution/training/splits.py`
- `solution/training/tests/test_splits.py`

## Out of scope
- Training.
