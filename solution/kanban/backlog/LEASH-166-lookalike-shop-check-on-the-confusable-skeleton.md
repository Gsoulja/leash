# LEASH-166: Lookalike shop check on the confusable skeleton

**Status**: BACKLOG
**Priority**: P1
**Type**: feature
**Estimated Effort**: S
**Milestone**: M7 — Production hardening
**Rule source**: Team (proposal from the 2026-09-24 trust-filter session)
**Decisions**: DEC-038 (to be written in LEASH-161), DEC-009, DEC-025, DEC-029, DEC-030
**Pattern**: Specification (refactor of an existing rule)
**Parent**: LEASH-160
**Task ID**: 160-T6
**Blocked by**: LEASH-162
**Blocks**: LEASH-168
**Updated**: 2026-09-24

## Description
`familiar.py` compares lower-cased alphanumeric names by edit distance ≤ 2, and `_norm` keeps non-Latin letters. Compare `CanonicalText` skeletons instead, so `Dіgitec` (Cyrillic і) or `Ｄｉｇｉｔｅｃ` (fullwidth) match `Digitec` at distance 0. Names still never grant familiarity: the check joins by `merchant_id` only (DEC-023).

## Business Value
Lookalike shops are a common scam; today a few swapped homoglyphs slip past the distance threshold.

## Acceptance Criteria
- [ ] A name that is all-Cyrillic-lookalike of a known shop is reported as `lookalike_merchant`.
- [ ] A fullwidth version of a known shop's name is reported.
- [ ] The shop's own `merchant_id` is never reported as its own lookalike.
- [ ] Existing lookalike tests and the scenario replay keep their verdicts (edge case: a genuinely different short name, e.g. "Otto" vs "Oto", keeps today's behaviour).

## Technical Approach
Change `_norm` in `domain/rules/familiar.py` to use `CanonicalText(...).skeleton`. No new rule, no new reason code.

### Dependencies
- Needs LEASH-162.
- Blocks LEASH-168.

## Testing Requirements
Write first: `test_cyrillic_lookalike_name_is_reported`, `test_fullwidth_lookalike_name_is_reported`. Run `uv run pytest tests/domain/rules -x -q` and the replay tests.

## Related Files
- `solution/engine/src/leash/domain/rules/familiar.py`
- `solution/engine/tests/domain/rules/test_familiar.py`

## Out of scope
- Matching a domain in text against the shop name (LEASH-164 adds the weight).
- Changing what counts as familiar (DEC-014).
