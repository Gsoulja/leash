# LEASH-074: Public data ingest

**Status**: DONE
**Priority**: P2
**Type**: feature
**Estimated Effort**: M
**Milestone**: M6 — Differentiators (after MVP)
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-006
**Task ID**: 006-T5
**Blocked by**: LEASH-070
**Blocks**: none
**Updated**: 2026-09-25

## Description
Download and convert ESCI, deepset and BIPIA into question-bank format, recording each license.

## Business Value
More varied training data.

## Acceptance Criteria
- [x] Each source converts to the same record format.
- [x] License recorded per record; unclear licenses are eval-only.

## Technical Approach
`training/ingest.py`.

### Dependencies
- Needs LEASH-070.

## Testing Requirements
Write first: `test_esci_labels_map_to_item_match`.

## Related Files
- `solution/training/ingest.py`
- `solution/training/tests/test_ingest.py`
- `solution/training/README.md`
- `solution/training/data/public-v1/`
- `solution/docs/laya-training-pipeline.html`

## Out of scope
- Sources without a clear license in training.

## Implementation (2026-09-24)

- Added pinned downloads with SHA-256 verification, offline cache reuse, and atomic
  conversion into new output directories. CLI usage is in the training README.
- All sources use `state`, `questions`, `labels` and `gold`, with the engine's
  unchanged question definitions and full bank hash. ESCI labels only item match;
  deepset/BIPIA label only injection. Other answers are left unannotated.
- ESCI joins products by both product ID and locale and maps E/S/C/I to
  exact/substitute/complement/unrelated. Default import is limited to the first
  5,000 records per upstream split, not a representative sample. The real-source
  import produced 5,000 training candidates and 5,000 evaluation records.
- Per-record provenance retains revision, original split, source file hashes,
  license claims and evidence URL. Outputs retain license/card/notice files.
- Deepset's pinned card contains conflicting Apache-2.0 and CC BY 4.0 declarations:
  all 662 records are eval-only pending clarification. This corrects the design page.
- BIPIA imports only MIT-covered text attack payloads, explicitly wrapped as
  instructions to the shopping agent: 75 training candidates and 75 eval records.
  Separately licensed benchmark contexts are excluded. Wrapper-based training is
  not a claim to reproduce BIPIA benchmark results or generalize to natural attacks.
- Upstream tests are never training candidates. Missing/changed license evidence
  forces eval-only; data checksum mismatches and malformed rows fail the import.
- LEASH-075 still owns family grouping, cross-source duplicates and frozen eval
  sets. Imported records explicitly carry `split_status: upstream_only`; no model
  training or calibration ran in this ticket.

## Validation

- Required mapping test written first and observed failing on the missing importer.
- `PYTHONPATH=/tmp/leash-ingest-deps solution/engine/.venv/bin/python -m pytest solution/training/tests -q`
  — 15 passed, including 8 importer checks. PyArrow was installed only in a
  temporary directory for verification; engine dependencies were not changed.
- Source files downloaded from pinned official revisions; all three conversions
  ran against the downloaded data. The complete ESCI examples and product catalog
  match the SHA-256 hashes in the official Git LFS pointers. Total output:
  10,812 records, comprising 5,075 training candidates and 5,737 evaluation records.
- Board validation passes. Two dependency sentences in LEASH-158/159 were clarified
  because parenthetical “depends on”/“needs” wording created false reverse edges;
  their intended dependencies and implementation were unchanged.

## Review log

### 2026-09-24 — independent agent review
- [x] met — each source uses the common question-bank format. Reviewer validated
  all 10,000 ESCI records, all 662 deepset records and all 150 BIPIA records,
  including label mappings, gold distributions, manifest/output hashes and splits.
- [x] met — licenses and pinned provenance are recorded per row. Unclear deepset
  licensing is eval-only, ESCI uses Apache-2.0, BIPIA payloads use MIT, and upstream
  test records remain evaluation-only.
- Full training-data suite: 15 passed, including 8 importer tests. No remaining
  acceptance-criterion gaps. The initial review's missing ESCI evidence was
  resolved after the verified download and real conversion completed.
Verdict: moved to review; human review pending. No model was trained.

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
