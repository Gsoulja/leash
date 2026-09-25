# LEASH-076: Regex baseline on eval sets

**Status**: DONE
**Priority**: P2
**Type**: test
**Estimated Effort**: S
**Milestone**: M6 — Differentiators (after MVP)
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-006
**Task ID**: 006-T7
**Blocked by**: LEASH-071, LEASH-075
**Blocks**: LEASH-077, LEASH-081
**Updated**: 2026-09-25

## Description
Score the regex reader on every eval set to set the bar Laya must beat.

## Business Value
The release gate compares against this.

## Acceptance Criteria
- [x] Report per question: recall, false-flag rate.
- [x] Report stored as JSON with dataset version.

## Technical Approach
`training/evaluate.py` shared with LEASH-081.

### Dependencies
- Needs LEASH-071.
- Needs LEASH-075.
- Blocks LEASH-077.
- Blocks LEASH-081.

## Testing Requirements
From repository root: `PYTHONPATH=solution uv run --project solution/engine --no-sync python -m training.evaluate --reader regex`.
The direct interpreter equivalent is `solution/engine/.venv/bin/python -m solution.training.evaluate --reader regex`.

## Related Files
- `solution/training/evaluate.py`
- `solution/training/tests/test_evaluate.py`
- `solution/training/reports/regex-shop-splits-v1.json`
- `solution/training/README.md`
- `solution/docs/laya-training-pipeline.html`

## Execution note
2026-09-24: user requested the next pipeline step after LEASH-075's reviewed
implementation. Proceeding with its frozen experimental snapshot; LEASH-075
remains in review and its dataset release blockers remain in force.

## Out of scope
- Laya scores.

## Implementation and evidence (2026-09-24)
- Runs the unchanged production RegexReader over frozen evaluation, held-out
  family/language slices, NotInject and pack; development/calibration are separate
  diagnostics. Source/language breakdowns preserve untagged inputs as unknown.
- Per-question counts, coverage, recall and false-flag rates; choices have
  one-vs-rest confusion counts and unweighted macro rates. Undefined rates are
  null. Unsupported semantic item-match abstains; the pack has no invented gold.
- Report binds dataset version, pinned manifest/file hashes, question bank,
  Python version and reader/evaluator/text-bounding source hashes. Existing
  output paths are refused; no changes to frozen data or reader patterns.
- Evaluation injection recall 83/487 (17.0%), false flags 0/543. Breakdown:
  BIPIA 80/80 (explicit shared wrapper), deepset 3/263, synthetic fake-consent
  0/144. NotInject false flags 0/339. All are experimental, not release evidence.
- Tests written first and observed failing on the missing module. Training
  suite plus production regex adapter tests: 77 passed, including five new
  evaluator checks. Real CLI saved the report successfully using the engine
  interpreter; the installed snap-packaged uv cannot launch in this sandbox
  (`snap-confine` lacks `cap_dac_override`). No dependency change was needed.
- Frozen snapshot still has `release_ready: false`. Pack gold, annotation review
  and independent final evaluation remain missing. No Laya scores or training.

## Review log

### 2026-09-24 — independent agent review
- [x] met — per-question recall/false-flag rates cover every evaluation set and
  held-out slice. Independent confusion-count checks matched all five base sets;
  missing gold and unsupported item-match remain explicitly unscored.
- [x] met — JSON records `shop-splits-v1`, manifest/data hashes and code
  provenance. A fresh CLI run reproduced the saved report byte for byte.
- Reviewer reran all five evaluator tests successfully and found no in-scope
  correctness bugs. Full implementation check: 77 tests passed; compile,
  whitespace, reproducibility and board validation checks passed.
Verdict: moved to review; human review pending. Annotation/release blockers remain.
