# LEASH-155: Laya permission verifier: baseline, evaluation and conditional tuning

**Status**: BACKLOG
**Priority**: P1
**Type**: research
**Estimated Effort**: L
**Milestone**: M8 — Permission control journey
**Rule source**: Product agreement 2026-09-24
**Decisions**: DEC-033, DEC-034, DEC-035, DEC-036, DEC-037
**Parent**: LEASH-008
**Task ID**: 008-T6
**Blocked by**: LEASH-156
**Blocks**: none
**Updated**: 2026-09-24

## Description
Evaluate Laya as a second reader of conversation/context versus proposed permission. This is separate from the five shop-text questions in LEASH-070–082. Start with a baseline; fine-tuning and deployment depend on measured failures and a documented release decision.

## Business Value
Measure whether a second reader catches incorrect or omitted permissions without treating model agreement as proof.

## Acceptance Criteria
- [ ] Reuse the reviewed corpus and frozen splits from LEASH-156. Label each proposal supported / contradicted / not stated / ambiguous, and label source restrictions omitted from the proposal.
- [ ] Check source-to-proposal completeness as well as proposal-to-source support; a verifier that only sees proposed rules cannot establish no restriction was omitted.
- [ ] Compare the deterministic/LLM baseline, the available Laya checkpoint without Leash-specific tuning and their combination. Report false support, missed restrictions, useful/needless clarification, abstention, latency and per-family/language results with counts and uncertainty.
- [ ] Profile preferences without customer adoption are not sufficient authorization. Tests include corrections, negation, unresolved references, conflicting background and malicious text.
- [ ] Amounts and IDs remain source-backed and code-validated. Laya returns typed checks, cannot generate authoritative money, confirm permissions or make payment decisions.
- [ ] Use calibrated answer probabilities, document their exact meaning, and keep calibration separate from evaluation. Truncated or missing relevant input is inconclusive, never a confident support result.
- [ ] Baseline evidence determines whether tuning is warranted. If chosen, fine-tune only on the training split, calibrate separately, and compare on the frozen evaluation set; otherwise record why tuning was skipped.
- [ ] Pin model, question wording, dataset and calibration versions. Provide an optional, disabled-by-default permission-service shadow adapter; record its verdict and input version with the baseline outcome unchanged on model disagreement, timeout or failure. The evaluation report can recommend continued shadow use or a separately reviewed promotion.
- [ ] Any active integration is separately reviewed against agreed thresholds and a rollback/fallback plan. Thresholds are unresolved until evidence exists; passing shop-text gates does not certify permission extraction.

## Technical Approach
Use Laya’s typed choice interface and existing evaluation/training utilities where compatible. Add a separate permission question set and report; keep inference out of the authoritative decision core. This ticket delivers reproducible evaluation and a promotion recommendation, not automatic activation.

### Dependencies
- Needs LEASH-156.

## Testing Requirements
From the repository root, run `python -m pytest solution/training/tests/test_permission_verifier.py solution/assistant/tests/test_permission_verifier.py`. Run the evaluator with `cd solution && python -m training.permission_verifier_eval`, documenting the model/data arguments and environment. Tests must detect a missing “no extras” restriction, incorrect support from a profile, input truncation and split leakage; reports must reproduce from pinned inputs.

## Related Files
- `solution/training/permission_verifier_eval.py`
- `solution/training/tests/test_permission_verifier.py`
- `solution/training/permission_questions.py`
- `solution/assistant/permission_verifier.py`
- `solution/assistant/tests/test_permission_verifier.py`
- `solution/training/permission_train.py`
- `solution/evaluation/permission-journey/`
- `solution/docs/laya-training-pipeline.html`

## Out of scope
- Mandatory fine-tuning before baseline measurement; a new general-purpose model; production promotion; interpreting historical approval as consent; reuse of shop-text metrics as permission guarantees.
