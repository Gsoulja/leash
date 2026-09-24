# LEASH-111: Sync design pages with decisions

**Status**: DONE
**Priority**: P0
**Type**: docs
**Estimated Effort**: S
**Milestone**: M5 — Hosted API and release
**Rule source**: Engineering
**Decisions**: DEC-001
**Parent**: LEASH-009
**Task ID**: 009-T2
**Blocked by**: none
**Blocks**: LEASH-128
**Updated**: 2026-09-23

## Description
Update the design pages where they diverge from decisions (e.g. lookalike shop is declined, not stepped up) and republish.

## Business Value
Judges and teammates read consistent documents.

## Acceptance Criteria
- [x] System design example JSON matches engine behaviour.
- [x] Both pages republished to their existing links.
- [x] Fixes the SQLite statement (DEC-001), the fixed 6 s watchdog, lookalike step_up vs decline, and tightening wording.
- [x] Adds the decision log link to both pages.

## Technical Approach
Edit solution/docs and republish the artifacts.

### Dependencies
- None.
- Blocks LEASH-128.

## Testing Requirements
Human review of the pages.

## Related Files
- `solution/docs/system-design.html`
- `solution/docs/laya-training-pipeline.html`

## Out of scope
- New design work.

## Review log

### 2026-09-23 — independent agent review (round 1)
- [x] met — criterion 1: example JSON is now the duplicate step_up (`possible_duplicate`) matching the prototype engine for AU0036.
- [?] unverifiable — criterion 2: reviewer could not open the artifact links.
- [x] met — criterion 3: no SQLite, no fixed 6 s watchdog, tightening described as append-only, model-down per DEC-009.
- [x] met — criterion 4: decision-log link on both pages.
- Found three leftovers outside the named items: fixed "120 s" in the purchase-state diagram (aria-label and SVG label) and the unversioned `merchant.prior_approved_count` field name. Fixed in both copies and republished (system design version 4).
Verdict: re-check requested, including the published pages.

### 2026-09-23 — independent agent review (round 2)
- [x] met — criterion 1: published example JSON is the duplicate step_up (`possible_duplicate`).
- [x] met — criterion 2: both existing artifact links serve the updated pages (system design and Laya pipeline), each with decisions.md published alongside (identical sha256).
- [x] met — criterion 3: no SQLite, no fixed 6 s watchdog, no fixed 120 s window, registry field names, append-only tightening; lookalike step_up claim removed.
- [x] met — criterion 4: decision-log link on both published pages and both local copies.
Remaining contradictions: none.
Verdict: moved to review.
