# LEASH-100: Catalogue reference resolution for permissions

**Status**: BACKLOG
**Priority**: P2
**Type**: feature
**Estimated Effort**: S
**Milestone**: M6 — Differentiators (after MVP)
**Rule source**: Engineering
**Decisions**: DEC-033, DEC-034, DEC-035, DEC-036, DEC-037
**Parent**: LEASH-008
**Task ID**: 008-T1
**Blocked by**: LEASH-030
**Blocks**: none
**Updated**: 2026-09-24

## Description
Resolve customer-named items and merchants against the supplied catalogue during permission clarification. This is optional evidence lookup, not product recommendations or an in-house shopping agent.

## Business Value
The customer can identify an exact product without the model inventing its ID.

## Acceptance Criteria
- [ ] Search by name and category returns items with price ranges and shops.
- [ ] Results carry IDs.
- [ ] An ambiguous or absent reference returns candidates or a clarification; it never silently selects a product.
- [ ] Catalogue price ranges are context only; the actual checkout supplies the purchase price.

## Technical Approach
`assistant/catalogue.py`.

### Dependencies
- Needs LEASH-030.

## Testing Requirements
Write first: `test_search_monitor_returns_it0017`.

## Related Files
- `solution/assistant/catalogue.py`
- `solution/assistant/tests/test_catalogue.py`

## Out of scope
- Web search.
