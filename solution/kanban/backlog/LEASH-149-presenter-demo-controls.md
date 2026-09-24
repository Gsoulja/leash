# LEASH-149: Presenter demo controls

**Status**: BACKLOG
**Priority**: P0
**Type**: feature
**Estimated Effort**: L
**Milestone**: M8 — Great demo
**Rule source**: Product
**Decisions**: none
**Parent**: LEASH-144
**Task ID**: 144-T5
**Blocked by**: LEASH-147, LEASH-148, LEASH-151
**Blocks**: LEASH-153
**Gate**: DECISION — the team approves which controls are demo-only and how they are disabled outside demo mode.
**Updated**: 2026-09-24

## Description
Add a presenter-only control panel outside the customer phone for scenario selection, play/pause, next event, speed and reset.

## Business Value
The presenter needs reliable pacing and recovery without exposing fixture controls as customer product features.

## Acceptance Criteria
- [ ] Demo mode is explicitly enabled and visually separated from the customer interface.
- [ ] Controls include scenario, play/pause, next event, speed and reset.
- [ ] The panel shows current run, event position and backend connection health.
- [ ] Every control reflects confirmed backend state; repeated clicks remain idempotent.
- [ ] Reset asks for confirmation and returns to the documented clean baseline.
- [ ] Demo controls are absent or inaccessible when demo mode is disabled.
- [ ] Keyboard shortcuts exist for play/pause and next event without stealing focus from customer inputs.

## Technical Approach
Restore the useful orchestration concepts from the prototype as a desktop companion panel backed by explicit demo endpoints or the fake-platform controller.

### Dependencies
- Needs LEASH-147.
- Needs LEASH-148.
- Needs LEASH-151.
- Blocks LEASH-153.

## Testing Requirements
Add browser tests for every control, idempotency, keyboard use, disabled production mode and recovery after refresh.

## Related Files
- `solution/prototype/index.html`
- `solution/app/src/App.tsx`
- `solution/docker-compose.yml`
- `solution/RUNBOOK.md`

## Out of scope
- Shipping fixture manipulation as a customer-facing production capability.
