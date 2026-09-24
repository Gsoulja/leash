# LEASH-073: Data factory

**Status**: BACKLOG
**Priority**: P2
**Type**: feature
**Estimated Effort**: L
**Milestone**: M6 — Differentiators (after MVP)
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-006
**Task ID**: 006-T4
**Blocked by**: LEASH-070
**Blocks**: LEASH-075
**Updated**: 2026-09-23

## Description
Generate labelled product-text lines from items.csv templates: benign lines, planted injections by family, position and language, hard negatives with trigger words.

## Business Value
Labels come from construction, no hand labelling.

## Acceptance Criteria
- [ ] Each line carries labels for all five questions and its attack family.
- [ ] At least 5 attack families, 4 languages, 3 positions.
- [ ] Output is deterministic for a seed.

## Technical Approach
`training/data_factory.py`.

### Dependencies
- Needs LEASH-070.
- Blocks LEASH-075.

## Testing Requirements
Write first: `test_planted_line_is_labelled_injection`, `test_same_seed_same_output`.

## Related Files
- `solution/training/data_factory.py`
- `solution/training/tests/test_data_factory.py`

## Out of scope
- LLM paraphrasing (optional follow-up).
