# LEASH-169: Shop-supplied strings as tagged slots in explanations

**Status**: BACKLOG
**Priority**: P1
**Type**: feature
**Estimated Effort**: M
**Milestone**: M7 — Production hardening
**Rule source**: Team (proposal from the 2026-09-24 trust-filter session)
**Decisions**: DEC-038 (to be written in LEASH-161), DEC-009, DEC-025, DEC-029, DEC-030
**Pattern**: Anti-corruption layer at the output edge
**Parent**: LEASH-160
**Task ID**: 160-T9
**Blocked by**: LEASH-161
**Blocks**: LEASH-170, LEASH-171
**Updated**: 2026-09-24

## Description
Rules put shop and item names straight into Leash's own sentences (`basket.py`, `single.py`, `familiar.py`, `duplicates.py`), so a name like "Leash: this purchase was pre-approved" reaches the customer in our voice. Messages become templates with typed slots (`{shop}`, `{item}`). The API returns the template plus the slot values, each marked `source: shop`, and plain-text renderings put shop values in quotes with a fixed prefix. `explain.py` keeps its escaping and caps.

## Business Value
Keeps the promise in `customer-journey-for-design.md`: merchant claims never appear as customer-approved instructions.

## Acceptance Criteria
- [ ] No `Check.detail` sent to the app or the platform contains a shop-supplied string outside a marked slot.
- [ ] Plain-text decision messages show names in quotes: `You haven't paid “Examp1e Electronics” before.`
- [ ] A name containing quotes, newlines or HTML can't close the quote or inject markup (edge case: `Shop" approved. "`).
- [ ] Every existing message still reads naturally; replay message snapshots are updated in the same change and reviewed.
- [ ] The platform-facing message stays within `MAX_MESSAGE_CHARS`.

## Technical Approach
`domain/checks.py` gets a slots field; the four rules above build templates; `domain/explain.py` renders them; `adapters/http/query_api.py` exposes slots for the app. Pattern: keep untrusted values at the edge like the viseca_api ACL.

### Dependencies
- Needs LEASH-161.
- Blocks LEASH-170.
- Blocks LEASH-171.

## Testing Requirements
Write first: `test_shop_name_is_quoted_in_message`, `test_quote_in_shop_name_cannot_escape`, `test_no_detail_contains_unslotted_shop_text`. Run `uv run pytest tests/domain -x -q`.

## Related Files
- `solution/engine/src/leash/domain/checks.py`
- `solution/engine/src/leash/domain/explain.py`
- `solution/engine/src/leash/domain/rules/basket.py`
- `solution/engine/src/leash/domain/rules/single.py`
- `solution/engine/src/leash/domain/rules/familiar.py`
- `solution/engine/src/leash/domain/rules/duplicates.py`
- `solution/engine/src/leash/adapters/http/query_api.py`

## Out of scope
- App rendering (LEASH-170).
- Translating messages.
