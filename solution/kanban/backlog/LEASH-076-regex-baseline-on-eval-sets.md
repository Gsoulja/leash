# LEASH-076: Regex baseline on eval sets

**Status**: BACKLOG
**Priority**: P2
**Type**: test
**Estimated Effort**: S
**Milestone**: M6 — Differentiators (after MVP)
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-006
**Task ID**: 006-T7
**Blocked by**: LEASH-071, LEASH-075
**Blocks**: LEASH-081
**Updated**: 2026-09-23

## Description
Score the regex reader on every eval set to set the bar Laya must beat.

## Business Value
The release gate compares against this.

## Acceptance Criteria
- [ ] Report per question: recall, false-flag rate.
- [ ] Report stored as JSON with dataset version.

## Technical Approach
`training/evaluate.py` shared with LEASH-081.

### Dependencies
- Needs LEASH-071.
- Needs LEASH-075.
- Blocks LEASH-081.

## Testing Requirements
Run `uv run python -m training.evaluate --reader regex`.

## Related Files
- `solution/training/evaluate.py`

## Out of scope
- Laya scores.
