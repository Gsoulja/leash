# LEASH-075: Splits by family and frozen eval sets

**Status**: DONE
**Priority**: P2
**Type**: feature
**Estimated Effort**: M
**Milestone**: M6 — Differentiators (after MVP)
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-006
**Task ID**: 006-T6
**Blocked by**: LEASH-073
**Blocks**: LEASH-076, LEASH-077
**Updated**: 2026-09-25

## Description
Split by attack family into train, calibration and eval; freeze held-out family, language, NotInject and the 56 pack lines.

## Business Value
Honest scores on attacks the model never saw.

## Acceptance Criteria
- [x] No family appears in more than one split.
- [x] Pack lines never appear in train.
- [x] Eval sets are hashed and read-only.
- [x] Optional public datasets (LEASH-074) are included when available, never required.

## Technical Approach
`training/splits.py`.

### Dependencies
- Needs LEASH-073.
- Blocks LEASH-076.
- Blocks LEASH-077.

## Testing Requirements
Write first: `test_no_family_leaks_across_splits`.

## Related Files
- `solution/training/splits.py`
- `solution/training/tests/test_splits.py`
- `solution/training/data/shop-splits-v1/`
- `solution/training/README.md`
- `solution/docs/laya-training-pipeline.html`

## Out of scope
- Training.

## Implementation and evidence (2026-09-24)

- Verified source manifests, then grouped families, pairs, public query groups and
  normalized matching text transitively. Upstream test/eval-only membership wins
  over fitting assignments. Contradictory targets exclude whole connected groups;
  exact state/question/target duplicates retain an excluded-ID trail.
- Reserved `fake_consent` for evaluation. Original `urgency` development remains
  diagnostic and cannot be selected as final holdout. Italian is held out by
  excluding it from fitting/development families; evaluation language and family
  slices overlap. Unknown-language fitting records are excluded.
- All 56 pack cart lines are separate evaluation identities, joined by IDs to
  their original customer instructions. Pack substrings are screened out of
  fitting data. No pack target labels were invented.
- Pinned NotInject revision `847ae76cf8fea5ed325429e569ae8cfef022d2e0`: 339 examples
  from its three original subsets, all eval-only with upstream benign labels.
  License card and source hashes are retained. Public ESCI/deepset/BIPIA imports
  are included when present; synthetic-only operation is tested.
- Snapshot: 2,565 train / 506 calibration / 216 development / 5,239 evaluation,
  plus 56 pack lines and 339 NotInject records. Excluded-ID ledger: 3,527 records
  from components with contradictory targets, 57 duplicates, 360 held-out-language
  records and 70 unknown-language fitting candidates. Source records are unchanged.
- All output files and the directory are read-only. The manifest hashes every
  data/notice file; the CLI refuses overwrites and verifies before publication.
  Unicode line-separator regression coverage came from the real public import.
- Manifest SHA-256 (external verification reference):
  `a07993a874c80e019a5d02102ff24953b9acb68a34573cd322373071c8abdb8a`.
  The repository snapshot exactly reproduces the independently checked smoke snapshot.

## Readiness limitation

This is a frozen **experimental** snapshot, not an independently collected and
human-reviewed final evaluation corpus. The manifest sets `release_ready: false`:
pack targets are missing, and synthetic/public labels and translations still need
review. File immutability does not establish unseen or reviewed evidence. These
limitations remain visible for baseline evaluation and release gating. No model
training, calibration or scoring was performed by this ticket.

## Review log

### 2026-09-24 — independent agent review
- [x] met — no family crosses partitions; reviewed union-find grouping and a
  three-record text-to-group transitive bridge against the real snapshot.
- [x] met — all 56 pack identities are eval-only; no normalized pack substring
  appears in training.
- [x] met — verified hashes, counts and read-only modes on the real snapshot;
  tests detect writable/corrupted files and refuse overwrite.
- [x] met — real public imports included; synthetic-only operation works, upstream
  tests stay outside fitting, and inspected development remains diagnostic.
- Required family-leakage test was written first and observed failing on the
  missing module. Full training suite: 21 passed, including 6 split tests.
  Compile checks and whitespace checks pass. Label correctness/release readiness
  remain explicitly unverified; no in-scope implementation bugs found.
Verdict: moved to review; human review pending.

## User-authorized shop revision (2026-09-25)

The user selected shop-text improvements now and permission work later. Added
`training/shop_revision.py`, `training/tests/test_shop_revision.py`, revision
reports, a blank pack-review worksheet and new public-v2/shop-splits-v2 artifacts.
BIPIA language evidence is pinned to the inspected source revision; no licence
restriction is removed. Conflicting ESCI inputs are quarantined without dropping
valid connected rows. Existing v1 records retain their splits; frozen evaluation,
pack and NotInject files remain byte-identical. New real-carrier pairs have only
injection draft labels; no human approval or model improvement is claimed.
See the training README and `reports/shop-data-v2.json` for counts and caveats.

### 2026-09-25 — independent review of v2 revision
No blocking findings. Seventeen ingestion/split/carrier tests pass. Reviewer
verified all original records remain in their partitions, evaluation/pack/
NotInject bytes are unchanged, new product/query identities are isolated,
70 BIPIA rows and 420 balanced carrier pairs are added, and both model loaders
require the explicit v2 manifest pin. All 280 pack judgments remain blank.
Full training suite: 33 passed, 4 model-only skips; eight model tests pass
separately. Tokenizer preflight: 5,788 usable training questions, no fitting.
Tickets remain in review. Human label review, deepset licence resolution and
permission expansion are not claimed complete.
