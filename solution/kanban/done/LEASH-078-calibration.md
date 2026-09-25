# LEASH-078: Calibration

**Status**: DONE
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
**Updated**: 2026-09-25

## Description
Fit one temperature per question type and option count on the calibration split.

## Business Value
Confidence the engine can trust.

## Acceptance Criteria
- [x] ECE reported before and after.
- [x] Temperatures saved with the checkpoint.

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
- `solution/training/README.md`
- `solution/training/reports/laya-calibration-shop-splits-v1.json`
- `solution/docs/laya-training-pipeline.html`

## Out of scope
- Per-language temperatures.

## Execution note
User explicitly selected calibration after the completed GPU run; LEASH-077
remains in review. Fit only on calibration; development is a separate diagnostic.
Frozen evaluation stays untouched.

## Implementation and evidence (2026-09-24)
- Reuses Laya raw-logit inference, truncation guard, validated diagnostic loader
  and runtime option buckets. Fits NLL with a bounded scalar search in inverse
  temperature, within the runtime's 0.5–5 range. No weight optimizer.
- Only calibration labels fit parameters. Separate development diagnostics are
  computed afterward; train/evaluation/pack/NotInject never reach this runner.
- Actual A100 run: 504 usable calibration cases / 1,368 annotated questions,
  two overlength cases excluded with IDs. Development: 216 cases / 1,080
  questions, no exclusions. Fit plus diagnostics 27.58 seconds.
- Both observed buckets (`noul:2`, `choice:3-5`) fit temperature 5.0. Other
  buckets fall back to 1. ECE uses top-label confidence, 15 equal-width bins.
- Calibration ECE 0.124835 → 0.082736; NLL 1.962604 → 0.453285.
  Development ECE 0.073497 → 0.053902; NLL 1.200212 → 0.263116.
  Argmax accuracy unchanged. Per-question/bin-group counts and raw logits/labels
  are saved, along with Brier scores, parent/data/runtime/source hashes.
- Several already-accurate questions have slightly worse ECE after shared
  temperature fitting. Injection development ECE remains 0.2158, and calibration
  item-match ECE 0.2119. Both temperatures hit the maximum; no release claim.
- Local checkpoint `training/checkpoints/laya-shop-v1-calibrated/`, cloud
  `/home/ubuntu/leash-training/runs/calibrated-001`. New atomic export preserves
  original weights; actual inference reload confirms saved bucket temperatures.
  All local post-load file hashes match cloud provenance.
- Tests written first, observed failing on missing module. Eight model tests
  pass (two calibration tests plus six training tests); full training suite
  in engine environment: 30 passed / 4 model-only skips, covered separately.
  Tests cover synthetic ECE improvement, unchanged accuracy/weights, saved
  temperatures applied by public inference, split isolation and no overwrite.
- Annotation/release limitations remain. No per-language fitting, threshold
  tuning, ask-head training or release evaluation.

## Review log

### 2026-09-24 — independent agent review
- [x] met — ECE before/after independently recomputed from raw logits for both
  calibration and development; labels, order, splits and exclusions verified.
- [x] met — persisted bucket temperatures reproduced using calibration only;
  all seven artifact hashes and unchanged model weights verified. Public
  inference regression confirms saved temperatures are applied.
- Two calibration tests independently passed. No blocking findings.
Verdict: moved to review; human review pending. Temperatures hit their upper
bound and release readiness remains false.

## V2 calibration (2026-09-25)
After user-authorized v2 training, fit the same bounded-NLL temperatures on
calibration only: 624 usable cases, 1,488 labelled questions, two overlength
exclusions. `noul:2 = 3.9719306778`, `choice:3-5 = 5.0` (upper bound).
Calibration ECE: 0.0913532 → 0.0522876. Separate v2 development ECE:
0.0211419 → 0.0084751 across 1,200 questions. Fit/diagnostics: 32.23 seconds.
Report `training/reports/laya-calibration-shop-splits-v2.json` retains raw
logits, provenance and per-question metrics. Calibration item-match ECE
remains 0.1557; aggregate improvement is not a release claim.

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
