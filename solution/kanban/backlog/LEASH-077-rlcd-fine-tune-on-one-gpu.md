# LEASH-077: RLCD fine-tune on one GPU

**Status**: BACKLOG
**Priority**: P2
**Type**: feature
**Estimated Effort**: L
**Milestone**: M6 — Differentiators (after MVP)
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-006
**Task ID**: 006-T8
**Blocked by**: LEASH-075
**Blocks**: LEASH-078, LEASH-080
**Updated**: 2026-09-23

## Description
Adapt Laya's Kaggle training script (proper-scoring policy gradient plus soft cross-entropy) to one RTX 5070 Ti on our data.

## Business Value
The model that reads shop text better than regex.

## Acceptance Criteria
- [ ] Training runs end to end and saves a checkpoint.
- [ ] Batch 8 × accumulation 8, bf16, 3–4 epochs, early stop on calibration log score.
- [ ] Wall time recorded.

## Technical Approach
`training/train.py`, reusing laya.common helpers.

### Dependencies
- Needs LEASH-075.
- Blocks LEASH-078.
- Blocks LEASH-080.

## Testing Requirements
Write first: a smoke test that one step on 16 examples lowers the loss.

## Related Files
- `solution/training/train.py`
- `solution/training/tests/test_train_smoke.py`

## Out of scope
- Distributed training.
