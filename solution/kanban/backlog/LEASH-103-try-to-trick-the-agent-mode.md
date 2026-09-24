# LEASH-103: Adversarial checkout demonstration

**Status**: BACKLOG
**Priority**: P2
**Type**: feature
**Estimated Effort**: M
**Milestone**: M6 — Differentiators (after MVP)
**Rule source**: Engineering
**Decisions**: DEC-033, DEC-034, DEC-035, DEC-036, DEC-037
**Parent**: LEASH-008
**Task ID**: 008-T4
**Blocked by**: LEASH-102, LEASH-097
**Blocks**: none
**Updated**: 2026-09-24

## Description
A demo-only form where judges provide shop text, price and merchant; a synthetic checkout goes through the control engine. This demonstrates external-agent input, not an in-house shopping assistant.

## Business Value
Lets judges attack the system themselves during the demo.

## Acceptance Criteria
- [ ] Any text is accepted and escaped.
- [ ] The result appears in the app and inspector within a second.

## Technical Approach
Presenter-only app form plus fake-platform checkout fixtures through the existing worker path. Keep synthetic events isolated from hosted runs; do not add a permission-assistant payment tool.

### Dependencies
- Needs LEASH-102.
- Needs LEASH-097.

## Testing Requirements
Write first: `malicious text never changes the limit check`.

## Related Files
- `solution/app/src/inspector/TrickTheAgent.tsx`

## Out of scope
- Persisting attack attempts.
