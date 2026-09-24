# LEASH-151: Deterministic demo reset and delivery

**Status**: BACKLOG
**Priority**: P0
**Type**: infra
**Estimated Effort**: M
**Milestone**: M8 — Great demo
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-144
**Task ID**: 144-T7
**Blocked by**: none
**Blocks**: LEASH-149, LEASH-153
**Updated**: 2026-09-24

## Description
Guarantee that every rehearsal starts from the same clean data and that localhost serves the frontend bundle built from the current source revision.

## Business Value
A stale bundle or leftover run can invalidate the entire demo before the product story begins.

## Acceptance Criteria
- [ ] One documented command resets only demo data and loads the approved baseline.
- [ ] Reset clears draft/session state, permissions, runs, asks, outbox records and read models consistently.
- [ ] Seed data contains no duplicate authorization IDs and passes run-scoped total checks.
- [ ] The served frontend exposes its source revision and asset/build identifier.
- [ ] Readiness fails when the served bundle revision differs from the expected revision.
- [ ] Container startup rebuilds or consumes a deliberately versioned frontend artifact—never an accidental stale volume.
- [ ] Reset and readiness complete within the rehearsal budget and produce clear failure messages.

## Technical Approach
Add a guarded demo reset/seed workflow and build metadata endpoint or manifest. Verify the HTML asset hash against the current build during readiness.

### Dependencies
- Blocks LEASH-149.
- Blocks LEASH-153.

## Testing Requirements
Run reset twice and prove identical API state. Add a deployment test that intentionally serves an old asset and expects readiness to fail.

## Related Files
- `solution/docker-compose.yml`
- `solution/app/dist/`
- `solution/engine/migrations/`
- `solution/RUNBOOK.md`

## Out of scope
- Resetting real production or customer data.
