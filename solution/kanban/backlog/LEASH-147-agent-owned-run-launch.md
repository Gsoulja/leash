# LEASH-147: Agent-owned run launch

**Status**: BACKLOG
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M8 — Great demo
**Rule source**: Product
**Decisions**: none
**Parent**: LEASH-144
**Task ID**: 144-T3
**Blocked by**: LEASH-145
**Blocks**: LEASH-148, LEASH-149, LEASH-153
**Updated**: 2026-09-24

## Description
Move shopping initiation into the Agent journey and replace raw scenario-ID entry with understandable, curated choices.

## Business Value
After confirming permission, the customer expects the agent to begin work—not to visit Permission and type an engineering fixture ID.

## Acceptance Criteria
- [ ] A confirmed permission leads to a prominent “Start shopping” action in Agent.
- [ ] Demo scenarios are presented by human names and one-line outcomes, never `SCEN*` identifiers.
- [ ] The recommended scenario is selected by default for the rehearsed demo.
- [ ] Starting creates exactly one run and immediately shows its recorded ID/state in the activity experience.
- [ ] Double taps cannot start duplicate runs.
- [ ] A refused start appears as an actionable conversation message.
- [ ] Permission remains focused on viewing, tightening and revoking boundaries.

## Technical Approach
Add a typed scenario catalogue endpoint or build-time catalogue, then call the existing run API from the Agent state machine. Remove the run form from Permission.

### Dependencies
- Needs LEASH-145.
- Blocks LEASH-148.
- Blocks LEASH-149.
- Blocks LEASH-153.

## Testing Requirements
Test curated selection, one-shot start, duplicate-click protection, rejected starts and the absence of raw scenario entry in customer UI.

## Related Files
- `solution/app/src/screens/Agent.tsx`
- `solution/app/src/screens/Permission.tsx`
- `solution/app/src/api/client.ts`
- `solution/contracts/policy-api.yaml`

## Out of scope
- Allowing customers to upload arbitrary scenario fixtures.
