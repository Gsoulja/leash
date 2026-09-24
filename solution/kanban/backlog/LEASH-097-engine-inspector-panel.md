# LEASH-097: Engine inspector panel

**Status**: BACKLOG
**Priority**: P2
**Type**: feature
**Estimated Effort**: M
**Milestone**: M6 — Differentiators (after MVP)
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-007
**Task ID**: 007-T8
**Blocked by**: LEASH-091
**Blocks**: LEASH-103
**Updated**: 2026-09-23

## Description
Side panel for judges: every purchase with engine and final verdict, the checks for the selected one, facts read and the JSON sent to the API.

## Business Value
Makes the reasoning visible during the demo.

## Acceptance Criteria
- [ ] Selecting a payment shows its checks and JSON.
- [ ] Hidden on phone width.

## Technical Approach
`src/inspector/Inspector.tsx`.

### Dependencies
- Needs LEASH-091.
- Blocks LEASH-103.

## Testing Requirements
Write first: `selecting a row shows its checks`.

## Related Files
- `solution/app/src/inspector/Inspector.tsx`

## Out of scope
- Editing data.
