# LEASH-077: Shop-text checkpoint baseline and conditional fine-tuning

**Status**: BACKLOG
**Priority**: P2
**Type**: feature
**Estimated Effort**: L
**Milestone**: M6 — Differentiators (after MVP)
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-006
**Task ID**: 006-T8
**Blocked by**: LEASH-075, LEASH-076
**Blocks**: LEASH-078, LEASH-080
**Updated**: 2026-09-24

## Description
Evaluate the available Laya checkpoint on the development/calibration data against the regex baseline first. If measured failures justify domain tuning, adapt Laya’s training script to one GPU. Keep the frozen evaluation set untouched until release evaluation; otherwise retain the baseline checkpoint and document why tuning was skipped.

## Business Value
The model that reads shop text better than regex.

## Acceptance Criteria
- [ ] Record the off-the-shelf checkpoint baseline and a reasoned tune/skip decision. If tuning is chosen, training runs end to end and saves a checkpoint.
- [ ] If tuning is chosen, record hardware and selected hyperparameters; batch 8 × accumulation 8, bf16 and 3–4 epochs are starting candidates, not fixed product requirements. Keep training, calibration and evaluation data separate.
- [ ] Wall time and checkpoint provenance are recorded for the chosen path. Calibration and the release gate apply even if training is skipped.

## Technical Approach
`training/train.py`, reusing laya.common helpers.

### Dependencies
- Needs LEASH-075.
- Needs LEASH-076.
- Blocks LEASH-078.
- Blocks LEASH-080.

## Testing Requirements
Test the baseline report and explicit tune/skip path. If training is selected, add a reproducible small-data training/checkpoint smoke test; do not require a skipped training job to pass. Run the corresponding training tests in the configured model environment.

## Related Files
- `solution/training/train.py`
- `solution/training/tests/test_train_smoke.py`

## Out of scope
- Distributed training.
