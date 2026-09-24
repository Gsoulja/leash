# LEASH-100: Catalogue search tool

**Status**: BACKLOG
**Priority**: P2
**Type**: feature
**Estimated Effort**: S
**Milestone**: M6 — Differentiators (after MVP)
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-008
**Task ID**: 008-T1
**Blocked by**: LEASH-030
**Blocks**: LEASH-101
**Updated**: 2026-09-23

## Description
Search items and merchants from the pack by text and category, for the assistant.

## Business Value
The assistant proposes real catalogue items that the engine can judge.

## Acceptance Criteria
- [ ] Search by name and category returns items with price ranges and shops.
- [ ] Results carry IDs.

## Technical Approach
`assistant/catalogue.py`.

### Dependencies
- Needs LEASH-030.
- Blocks LEASH-101.

## Testing Requirements
Write first: `test_search_monitor_returns_it0017`.

## Related Files
- `solution/assistant/catalogue.py`
- `solution/assistant/tests/test_catalogue.py`

## Out of scope
- Web search.
