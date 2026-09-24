# LEASH-162: CanonicalText value object

**Status**: BACKLOG
**Priority**: P1
**Type**: feature
**Estimated Effort**: M
**Milestone**: M7 — Production hardening
**Rule source**: Team (proposal from the 2026-09-24 trust-filter session)
**Decisions**: DEC-038 (to be written in LEASH-161), DEC-009, DEC-025, DEC-029, DEC-030
**Pattern**: Value object
**Parent**: LEASH-160
**Task ID**: 160-T2
**Blocked by**: LEASH-161
**Blocks**: LEASH-163, LEASH-166, LEASH-171
**Updated**: 2026-09-24

## Description
A pure, immutable `CanonicalText` built from one raw untrusted string. It keeps `raw` unchanged and adds `canonical` (NFKC, HTML entities decoded, zero-width and bidi-control characters removed, whitespace collapsed) and `skeleton` (confusables mapped to Latin per UTS #39, lower-cased). It also reports what changed: invisible characters removed, mixed scripts inside one word.

## Business Value
Regexes and lookalike checks stop being bypassed by `ig\u200bnore`, Cyrillic `іgnore` or fullwidth letters, and the raw text survives as evidence.

## Acceptance Criteria
- [ ] `CanonicalText("ig\u200bnore").canonical == "ignore"` and it flags `invisible_chars`.
- [ ] Cyrillic `іgnore` has skeleton `ignore` and flags `mixed_script`.
- [ ] Plain ASCII text is unchanged and raises no flags.
- [ ] `raw` is always the exact input (edge case: empty string and `None`-as-missing stay missing, never `""` meaning a pass).
- [ ] Construction is pure: no I/O, no clock, no model.

## Technical Approach
`domain/trust/canonical.py`. Stdlib `unicodedata` for NFKC; a small vendored confusables table (only Latin lookalikes from Cyrillic, Greek and fullwidth), not a new dependency unless DEC-038 allows it. Frozen dataclass like `money.py` and `clock.py`.

### Dependencies
- Needs LEASH-161.
- Blocks LEASH-163.
- Blocks LEASH-166.
- Blocks LEASH-171.

## Testing Requirements
Write first: `test_zero_width_space_is_removed_and_flagged`, `test_cyrillic_i_maps_to_latin_skeleton`, `test_ascii_text_is_unchanged`. Run `uv run pytest tests/domain/trust -x -q`.

## Related Files
- `solution/engine/src/leash/domain/trust/__init__.py`
- `solution/engine/src/leash/domain/trust/canonical.py`
- `solution/engine/tests/domain/trust/test_canonical.py`

## Out of scope
- Using the canonical text anywhere (LEASH-163, LEASH-166, LEASH-167).
- Full UTS #39 coverage beyond Latin lookalikes.
- Translating or spell-correcting text.
