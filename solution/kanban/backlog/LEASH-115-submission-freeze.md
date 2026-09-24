# LEASH-115: Submission freeze

**Status**: BACKLOG
**Priority**: P0
**Type**: infra
**Estimated Effort**: S
**Milestone**: M5 — Hosted API and release
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-009
**Task ID**: 009-T6
**Blocked by**: LEASH-128
**Blocks**: none
**Gate**: FREEZE — a human confirms the tag is created and pushed; no automated run may cross this.
**Updated**: 2026-09-23

## Description
Tag the submitted version and stop changes.

## Business Value
Judges see exactly what we tested.

## Acceptance Criteria
- [ ] Git tag pushed.
- [ ] README states the submitted version.

## Technical Approach
Git tag.

### Dependencies
- Needs LEASH-128.

## Testing Requirements
Human confirmation.

## Related Files
- `solution/README.md`

## Out of scope
- Post-submission changes.
