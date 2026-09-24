# LEASH-018: Familiar-shop rule with lookalike evidence

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M1 — SCEN0000 offline vertical slice
**Rule source**: Viseca brief + Team
**Decisions**: DEC-011, DEC-014, DEC-015, DEC-023
**Parent**: LEASH-001
**Task ID**: 001-T9
**Blocked by**: LEASH-014, LEASH-015
**Blocks**: LEASH-121, LEASH-128
**Updated**: 2026-09-23

## Description
Count earlier approved payments at this merchant ID on this card; fail below the mandate threshold. When unfamiliar, compare names with familiar shops and add lookalike evidence.

## Business Value
Manipulated-agent scenario: PixelHarbour vs PixelHarbor; session scenario: unfamiliar shops during a burst.

## Acceptance Criteria
- [x] Matching is by merchant ID only, never by name.
- [x] Below threshold fails; lookalike (edit distance ≤ 2 or containment) is named in the detail with the real shop's payment count.
- [x] Without a familiarity rule, a lookalike becomes a warning, a plain new shop is info only.

## Technical Approach
`domain/rules/familiar.py`. 'Regularly' threshold per DEC-014; same-run approvals count per DEC-015 (assumption).

### Dependencies
- Needs LEASH-014.
- Needs LEASH-015.
- Blocks LEASH-121.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_lookalike_shop_is_declined_with_evidence`, `test_name_similarity_never_grants_familiarity`.

## Related Files
- `solution/engine/src/leash/domain/rules/familiar.py`
- `solution/engine/tests/domain/rules/test_familiar.py`

## Out of scope
- Merchant reputation scores.

## Review log

### 2026-09-23 — independent agent review
- [x] met — matching by merchant ID only: same name with another ID fails, same ID under another name passes.
- [x] met — below threshold fails; lookalikes (case/punctuation, distance ≤ 2, containment) named with the real shop's payment count; distance 3 not flagged; "regularly" (3, DEC-014) fails at 2.
- [x] met — without a familiarity rule a lookalike warns (step_up/approve/decline per policy), a plain new shop is info (approve).
Notes: lookalike evidence is only computed at 0 payments; containment needs names of ≥ 5 characters; `Snapshot.merchant_names` is filled by later repository tickets.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
