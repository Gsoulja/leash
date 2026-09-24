# LEASH-103: Try-to-trick-the-agent mode

**Status**: BACKLOG
**Priority**: P2
**Type**: feature
**Estimated Effort**: M
**Milestone**: M6 — Differentiators (after MVP)
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-008
**Task ID**: 008-T4
**Blocked by**: LEASH-102, LEASH-097
**Blocks**: none
**Updated**: 2026-09-23

## Description
A form where judges write their own shop text, price and shop; the purchase goes through the engine live.

## Business Value
Lets judges attack the system themselves during the demo.

## Acceptance Criteria
- [ ] Any text is accepted and escaped.
- [ ] The result appears in the app and inspector within a second.

## Technical Approach
App form + local agent endpoint.

### Dependencies
- Needs LEASH-102.
- Needs LEASH-097.

## Testing Requirements
Write first: `malicious text never changes the limit check`.

## Related Files
- `solution/app/src/inspector/TrickTheAgent.tsx`

## Out of scope
- Persisting attack attempts.
