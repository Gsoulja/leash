# LEASH-082: Laya reader adapter in the engine

**Status**: BACKLOG
**Priority**: P2
**Type**: feature
**Estimated Effort**: M
**Milestone**: M6 — Differentiators (after MVP)
**Rule source**: Engineering
**Decisions**: DEC-009
**Parent**: LEASH-006
**Task ID**: 006-T13
**Blocked by**: LEASH-072, LEASH-081, LEASH-043
**Blocks**: none
**Updated**: 2026-09-23

## Description
FactReader that loads a pinned Laya release at startup, asks the five questions in one batch, caches by text hash, and supports shadow mode.

## Business Value
Model-quality facts in the live engine, behind the same port as regex.

## Acceptance Criteria
- [ ] Model preloaded at startup; first call has no cold start.
- [ ] Five questions answered in one forward pass.
- [ ] Cache hit skips the model.
- [ ] Shadow mode logs disagreements with regex without affecting verdicts.
- [ ] Uses the DEC-009 merge: the verdict with Laya is never less strict than without it.

## Technical Approach
`adapters/laya_reader.py`, wrapped by the fallback reader.

### Dependencies
- Needs LEASH-072.
- Needs LEASH-081.
- Needs LEASH-043.

## Testing Requirements
Write first: `test_cached_text_skips_model` with a fake model.

## Related Files
- `solution/engine/src/leash/adapters/laya_reader.py`
- `solution/engine/tests/adapters/test_laya_reader.py`

## Out of scope
- Training.
