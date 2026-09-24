# LEASH-078: Calibration

**Status**: BACKLOG
**Priority**: P2
**Type**: feature
**Estimated Effort**: S
**Milestone**: M6 — Differentiators (after MVP)
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-006
**Task ID**: 006-T9
**Blocked by**: LEASH-077
**Blocks**: LEASH-079, LEASH-081
**Updated**: 2026-09-23

## Description
Fit one temperature per question type and option count on the calibration split.

## Business Value
Confidence the engine can trust.

## Acceptance Criteria
- [ ] ECE reported before and after.
- [ ] Temperatures saved with the checkpoint.

## Technical Approach
`training/calibrate.py`.

### Dependencies
- Needs LEASH-077.
- Blocks LEASH-079.
- Blocks LEASH-081.

## Testing Requirements
Write first: `test_temperature_reduces_ece_on_overconfident_logits`.

## Related Files
- `solution/training/calibrate.py`
- `solution/training/tests/test_calibrate.py`

## Out of scope
- Per-language temperatures.
