# LEASH-163: Trust detectors as specifications, with an injection scan over every text field

**Status**: BACKLOG
**Priority**: P1
**Type**: feature
**Estimated Effort**: M
**Milestone**: M7 — Production hardening
**Rule source**: Team (proposal from the 2026-09-24 trust-filter session)
**Decisions**: DEC-038 (to be written in LEASH-161), DEC-009, DEC-025, DEC-029, DEC-030
**Pattern**: Specification + Notification (collect all findings)
**Parent**: LEASH-160
**Task ID**: 160-T3
**Blocked by**: LEASH-162
**Blocks**: LEASH-164, LEASH-165, LEASH-167
**Updated**: 2026-09-24

## Description
Define the detector interface: `TrustDetector(purchase, texts) -> list[TrustFinding]`, where each finding carries a reason code, the source field (`merchant_name`, `item_name[line 2]`, …), a short excerpt and a severity class (integrity or doubt). `assess()` runs every registered detector and returns a `TrustReport` with all findings, not the first one. The first detector moves the existing injection patterns from `regex_reader.py` into `domain/trust/` and runs them on the canonical text of all five free-text fields.

## Business Value
Closes the biggest gap: today only `item_details` is scanned, and only the first match is kept for the audit trail.

## Acceptance Criteria
- [ ] Both pack injections (AU0037, AU0040) are still found, now with field `item_details` and the line number.
- [ ] An injection placed in `item_name` or `merchant_name` is found (reason `instruction_in_name` or as set by DEC-038).
- [ ] A homoglyph or zero-width variant of a pack injection is found.
- [ ] Two injections in one purchase give two findings, not one.
- [ ] None of the other pack lines raises a finding (edge case: "System: 2.1 soundbar" stays clean, as in LEASH-071's review).
- [ ] `RegexReader` still fills `Facts.injection_excerpt` from the same patterns, so current verdicts don't change.

## Technical Approach
`domain/trust/detectors.py` (interface, `assess`) and `domain/trust/injection.py`. Patterns live in one module shared with `adapters/regex_reader.py`, so field strings and patterns aren't duplicated. Pure; takes `CanonicalText` per field.

### Dependencies
- Needs LEASH-162.
- Blocks LEASH-164.
- Blocks LEASH-165.
- Blocks LEASH-167.

## Testing Requirements
Write first: `test_injection_in_item_name_is_found`, `test_homoglyph_injection_is_found`, `test_every_injection_is_recorded`, `test_clean_pack_lines_raise_no_finding`. Run `uv run pytest tests/domain/trust -x -q`, then the full suite to show no verdict changed.

## Related Files
- `solution/engine/src/leash/domain/trust/detectors.py`
- `solution/engine/src/leash/domain/trust/injection.py`
- `solution/engine/src/leash/adapters/regex_reader.py`
- `solution/engine/tests/domain/trust/test_injection.py`

## Out of scope
- Wiring the report into the pipeline or verdict (LEASH-167, LEASH-168).
- New injection phrasing beyond what LEASH-071 covers.
- Laya.
