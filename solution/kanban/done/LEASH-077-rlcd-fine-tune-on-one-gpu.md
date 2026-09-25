# LEASH-077: Shop-text checkpoint baseline and conditional fine-tuning

**Status**: DONE
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
**Updated**: 2026-09-25

## Description
Evaluate the available Laya checkpoint on the development/calibration data against the regex baseline first. If measured failures justify domain tuning, adapt Laya’s training script to one GPU. Keep the frozen evaluation set untouched until release evaluation; otherwise retain the baseline checkpoint and document why tuning was skipped.

## Business Value
The model that reads shop text better than regex.

## Acceptance Criteria
- [x] Record the off-the-shelf checkpoint baseline and a reasoned tune/skip decision. If tuning is chosen, training runs end to end and saves a checkpoint.
- [x] If tuning is chosen, record hardware and selected hyperparameters; batch 8 × accumulation 8, bf16 and 3–4 epochs are starting candidates, not fixed product requirements. Keep training, calibration and evaluation data separate.
- [x] Wall time and checkpoint provenance are recorded for the chosen path. Calibration and the release gate apply even if training is skipped.

## Technical Approach
`training/train.py` for diagnostics and `training/finetune.py` for the single-GPU notebook adaptation, reusing laya.common helpers.

### Dependencies
- Needs LEASH-075.
- Needs LEASH-076.
- Blocks LEASH-078.
- Blocks LEASH-080.

## Testing Requirements
Test the baseline report and explicit tune/skip path. If training is selected, add a reproducible small-data training/checkpoint smoke test; do not require a skipped training job to pass. Run the corresponding training tests in the configured model environment.

## Related Files
- `solution/training/train.py`
- `solution/training/finetune.py`
- `solution/training/tests/test_train_smoke.py`
- `solution/training/README.md`
- `solution/training/reports/laya-baseline-shop-splits-v1.json`
- `solution/training/reports/laya-finetune-shop-splits-v1.json`
- `solution/training/reports/laya-finetune-shop-splits-v1.log`
- `solution/training/reports/laya-development-comparison-shop-splits-v1.json`
- `solution/training/.gitignore`
- `solution/training/reports/laya-finetune-executed.py`
- `solution/docs/laya-training-pipeline.html`

## Execution note
User subsequently confirmed a GPU instance and chose to pursue fine-tuning.
Reopened LEASH-077 for the actual single-GPU runner. The earlier skip-path
review remains historical evidence; GPU execution is now complete; evidence and independent review follow below.

2026-09-24: user requested the next step after LEASH-076's independent review.
Proceeding on the frozen experimental development/calibration inputs; prior
tickets remain in review and dataset release blockers remain in force.

## Out of scope
- Distributed training.

## Implementation and evidence (2026-09-24)
- Evaluated the unchanged multilingual checkpoint `convaiinnovations/laya-multilingual`
  at revision `e4e9ddf21a7b1903b7acffd8814ad4307bf63a67`, using local Laya
  0.3.20 source commit `23a17522aa4942da6cce53a995a275760320b691`.
  Downloaded weights SHA-256:
  `9d628fd971b700382ac6f65920a86f149777b2e748e0c955fb3b19695aa8f204`.
- Baseline reads only verified development/calibration inputs (216/506 cases).
  Tests reject attempts to open train/evaluation/pack/NotInject. Only state and
  canonical questions reach inference. Two long calibration ESCI cases abstain;
  state, question-head and option truncation are checked before prediction.
- Model and regex metrics share LEASH-076's scorer; `regex_on_answered` makes
  coverage differences explicit. Original/loaded checkpoint hashes, input/code
  hashes, runtime versions, predictions and raw API answers are saved in JSON.
- Development injection: 42/108 recall (38.9%), 12/108 false flags (11.1%).
  Add-on recall 88.9% with 87.0% false flags; recurring recall 100% with 91.9%
  false flags. Return-term macro recall 35.2% versus regex 77.8%; item-match
  macro recall 52.8%. These results do not establish superiority over regex.
- AMD Ryzen 5 5600H, four CPU threads, float32, CPU autocast unset. CUDA driver
  unavailable. Baseline wall time 544.6 seconds, including 5.8 seconds load;
  downloads/environment setup excluded. No payment-engine dependency changes.
- Tests written first and observed failing on missing module. Model environment:
  five tests passed. Full training suite in engine environment: 30 passed,
  one torch-only test skipped (it passes in the model environment). Compile,
  whitespace and dependency checks pass.

## Historical CPU-only decision and limits
Skip fine-tuning in this run and retain the pinned off-the-shelf checkpoint for
research only. Diagnostic failures indicate domain tuning would be useful;
skipping reflects the missing CUDA runtime and unresolved annotation review,
not an adequate model. This is a recorded implementation choice, not a new
approval requirement. No trained checkpoint or chosen training hyperparameters
are claimed; those conditional acceptance requirements do not apply to this
skip path. The command reports `training_performed: false` and cannot claim a
completed tuning run: if its diagnostic policy chooses `tune`, it exits nonzero
and says the separate one-GPU run remains required. Calibration and a reviewed
release gate remain outstanding. No model was promoted.

## Review log

### 2026-09-24 — independent agent review
- [x] met — actual 216-development/506-calibration checkpoint baseline; poor
  performance and explicit skip rationale are recorded without claiming adequacy.
- [x] met — no fitting; only diagnostic files reach this runner and labels stay
  outside inference. Training-specific requirements are conditional and do not
  apply to the chosen skip path.
- [x] met — 544.63-second wall time, pinned checkpoint/loaded-file hashes,
  runtime versions and source/input hashes verified. Calibration/release remain
  outstanding.
- Reviewer independently reconciled every prediction with stored API answers,
  every confusion count/rate with diagnostic labels, partition counts,
  abstentions, report-copy identity, hashes and timing consistency. Five model
  environment tests passed. No blocking findings.
Verdict: moved to review for the diagnostic skip path only; human review pending.
No fine-tuned checkpoint, temperature fitting or release validation is claimed.

## Actual GPU fine-tuning (2026-09-24)

The user supplied a Lambda A100 and explicitly selected experimental fine-tuning,
superseding the historical CPU-only skip. The runner adapts the existing
`laya/notebooks/laya_finetune_typed_decisions_2xT4_kaggle.ipynb`; it uses the
same G=4 projected Gaussian RLCD reward plus cross-entropy objective.

- NVIDIA A100-SXM4-40GB, Python 3.12.14, torch 2.7.1+cu126, CUDA 12.6.
- 3 epochs, batch 8 × accumulation 8, bf16, seed 42; encoder LR 2.5e-5,
  decision-layer LR 1e-4, weight decay 0.01, cosine schedule, sigma 0.4 → 0.1.
- 2,528 usable cases / 5,120 question examples; 37 overlength cases excluded
  with an ID/reason ledger. Optimizer input opens only verified train.jsonl.
- 80 updates per epoch, 240 total; 287.96 seconds including preparation and
  checkpoint saves, excluding environment setup/downloads. Epoch compute
  times: 86.74, 87.15 and 87.01 seconds. Peak allocated GPU memory: 6.03 GiB.
- Separate atomic checkpoints saved after all three epochs. Final cloud path:
  `/home/ubuntu/leash-training/runs/full-001/epoch-003`. Full run report:
  `training/reports/laya-finetune-shop-splits-v1.json`.
- Ask/act weights remain frozen. Temperatures reset to 1; calibration fitting
  and release evaluation remain separate. No held-out evaluation files uploaded.
- Small real GPU smoke: 128 question examples, 2 updates, saved/reloaded on CUDA.
  Six model-environment tests pass locally and remotely; complete training suite:
  30 passed, 2 torch checks skipped in engine environment and passed separately.
  Tests cover train-only access, actual weight updates, unchanged ask/act weights,
  checkpoint round-trip and refusal to overwrite.

The same-GPU comparison on 216 development cases is saved in
`training/reports/laya-development-comparison-shop-splits-v1.json`.
Injection recall improved from 38.9% to 50.9%, with false flags falling from
11.1% to zero observed. Add-on recall reached 100% with zero observed false
flags; recurring recall remained 100% with false flags falling to 0.58%.
Return-term macro recall improved from 35.6% to 88.0%; item-match macro recall
from 52.3% to 100%. These are small, partly synthetic development diagnostics,
not release estimates; injection recall remains inadequate. The earlier CPU
baseline differs slightly for some choices due to GPU bf16 inference.
The checkpoint passed CUDA reload and file-hash verification; decision weights
changed and ask/act weights remained identical to the base model.

Review found inherited base-model training metadata in the exported agent config.
Removed that stale summary from all three GPU checkpoint configs and refreshed
their provenance hashes without changing weights; training_report.json remains
authoritative. The exporter now omits that field, covered by the round-trip test.
The exact runner used for the completed optimization is archived as
`training/reports/laya-finetune-executed.py` and matches the run's source hash;
the subsequent exporter fix does not change the objective or trained weights.

### 2026-09-24 — independent review of actual GPU fine-tuning
- [x] met — baseline/tune rationale recorded; actual 3 × 80-update GPU run
  completed and saved reloadable checkpoints.
- [x] met — hardware/hyperparameters and 2,528 usable cases / 5,120 questions
  verified; optimizer input remains separate from calibration/evaluation.
- [x] met — 287.96-second wall time, parent checkpoint, data and executed-source
  hashes verified; calibration and release remain outstanding.
- Reviewer independently reconciled every development prediction and confusion
  count with raw answers/labels, checked the exporter metadata fix and ran all
  six model-environment tests. No outstanding blocking findings.
Verdict: moved to review for the completed GPU run; human review pending.

Final local backup complete: `training/checkpoints/laya-shop-v1/`. Every file
(including corrected metadata and 1,287,653,720-byte weights) matches the cloud
provenance manifest. Weights SHA-256:
`da6ddb576bb5a34afdfbbda8674c5d2c5088246949f88c643c7bdf7cf451441e`.

## V2 run requested (2026-09-25)
User explicitly authorized training on the reviewed v2 implementation, with
experimental labels/release blockers still recorded. Start again from the same
pinned multilingual base and retain the 3-epoch/bf16/batch8×accumulation8 recipe.
The data pin is `e4a36fee7874eaa17f277d9cb82a17b0dd4d99df311d1a1d7f9d7d9d638d6ccb`;
5,788 usable question examples, 39 overlength cases excluded. Compare v1/v2 on
unchanged original development cases and separately on the new real carriers.
The completed run and comparison evidence follow below.

### V2 completed run evidence
- Training: 322.46665 seconds, A100-SXM4-40GB, 273 updates, 5,788 questions
  per epoch, same base and recipe as v1. Three per-epoch checkpoints saved.
- Original development injection: v1 55/108 TP, v2 102/108 TP, both 0/108 FP.
  New real-carrier development: v1 17/60 TP and 1/60 FP; v2 58/60 TP and 0/60 FP.
- Reports: `training/reports/laya-finetune-shop-splits-v2.json`,
  `laya-development-comparison-shop-splits-v2.json`, training log and executed
  source archives. All decoded answers/raw logits are retained for audit.
- Final v2 weights SHA-256:
  `4c1becf77f239c9a2a13c2dbd87a18c6735c221c6fed328b0472c04eabad9efc`.
- New calibrated export: `training/checkpoints/laya-shop-v2-calibrated/`;
  cloud `/home/ubuntu/leash-training/runs/calibrated-v2-001`.
  Frozen evaluation remains untouched; experimental labels still need review.

### 2026-09-25 — independent v2 run review and verified backup
Independent review: PASS for experimental-run evidence, with no blocking findings.
Verified pinned data/base/source hashes, counts and all comparison predictions;
independently recomputed calibration metrics and fitted temperatures. Eight
targeted model-environment tests passed. All seven final local checkpoint artifact
hashes match provenance, including the 1,287,653,720-byte weights at
`training/checkpoints/laya-shop-v2-calibrated/`. Local CPU loader applies the saved
temperatures, and all post-load hashes still match. Release readiness remains false;
annotation review and frozen release evaluation remain outstanding. Ticket stays
in review pending human review.
