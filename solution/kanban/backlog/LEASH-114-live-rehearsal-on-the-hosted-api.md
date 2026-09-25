# LEASH-114: Live rehearsal on the hosted API

**Status**: BACKLOG
**Priority**: P0
**Type**: test
**Estimated Effort**: M
**Milestone**: M5 — Hosted API and release
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-009
**Task ID**: 009-T5
**Blocked by**: LEASH-057, LEASH-112
**Blocks**: LEASH-128
**Gate**: DECISION — a human runs the rehearsal on event day and decides if we're ready.
**Updated**: 2026-09-23

## Description
Run all five scenarios on the hosted API with the demo script, fix anything that breaks.

## Business Value
No surprises during judging (team reset is disabled then).

## Acceptance Criteria
- [ ] All scenarios run with decisions before deadlines.
- [ ] Demo script works end to end on the live system.
- [ ] `connection_check.py --live` against the hosted sandbox prints "connection check passed" and exits 0 (carried over from LEASH-158, which could not verify it offline: a `--live` run is scored).
- [ ] Defects found become tickets; the rehearsal passes when every scenario completes and the demo script runs end to end.

## Technical Approach
Event day, before judging.

### Dependencies
- Needs LEASH-057.
- Needs LEASH-112.
- Blocks LEASH-128.

## Testing Requirements
Human-run rehearsal; log run IDs.

## Related Files
- `solution/demo/rehearsal-log.md`

## Out of scope
- New features.
