# LEASH-074: Public data ingest

**Status**: BACKLOG
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
**Updated**: 2026-09-23

## Description
Download and convert ESCI, deepset and BIPIA into question-bank format, recording each license.

## Business Value
More varied training data.

## Acceptance Criteria
- [ ] Each source converts to the same record format.
- [ ] License recorded per record; unclear licenses are eval-only.

## Technical Approach
`training/ingest.py`.

### Dependencies
- Needs LEASH-070.

## Testing Requirements
Write first: `test_esci_labels_map_to_item_match`.

## Related Files
- `solution/training/ingest.py`
- `solution/training/tests/test_ingest.py`

## Out of scope
- Sources without a clear license in training.
