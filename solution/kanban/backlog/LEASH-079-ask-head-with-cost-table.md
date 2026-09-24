# LEASH-079: Ask head with cost table

**Status**: BACKLOG
**Priority**: P2
**Type**: feature
**Estimated Effort**: M
**Milestone**: M6 — Differentiators (after MVP)
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-006
**Task ID**: 006-T10
**Blocked by**: LEASH-078
**Blocks**: none
**Gate**: DECISION — the cost table is a product decision. A human (ideally with Viseca) confirms the costs before training.
**Updated**: 2026-09-23

## Description
Train Laya's unused action head to choose trust vs defer using the cost table (missed injection −10, other miss −3, false flag −2, defer −0.5).

## Business Value
A learned, explainable 'I'm not sure' that only ever adds caution.

## Acceptance Criteria
- [ ] Expected cost on eval is lower than a fixed confidence threshold.
- [ ] Costs are read from config and stored in the release.

## Technical Approach
`training/ask_head.py`.

### Dependencies
- Needs LEASH-078.

## Testing Requirements
Write first: `test_defer_when_expected_miss_cost_exceeds_ask_cost`.

## Related Files
- `solution/training/ask_head.py`
- `solution/training/tests/test_ask_head.py`

## Out of scope
- Online learning from customers.
