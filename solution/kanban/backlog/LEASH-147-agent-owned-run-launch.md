# LEASH-147: Customer handoff to the external shopping agent

**Status**: BACKLOG
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M8 — Great demo
**Rule source**: Product
**Decisions**: DEC-033, DEC-034, DEC-035, DEC-036, DEC-037
**Parent**: LEASH-144
**Task ID**: 144-T3
**Blocked by**: LEASH-145, LEASH-146, LEASH-102
**Blocks**: LEASH-148, LEASH-149, LEASH-153, LEASH-156
**Updated**: 2026-09-24

## Description
Offer the customer a handoff from confirmed permission to the external shopping agent. For the challenge, launch a curated Viseca simulator run and label it as a demonstration; Leash does not perform shopping.

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
- [ ] Start uses the handoff and confirmed revision from LEASH-102; a permission correction requires reconfirmation before launch.
- [ ] The action is a customer/backend action, never a permission-LLM tool. External-agent activity is shown only when recorded; a started simulator run is not proof of real merchant integration.

## Technical Approach
Add a typed scenario catalogue endpoint or build-time catalogue, then call the existing run API from the Agent state machine. Remove the run form from Permission.

### Dependencies
- Needs LEASH-145.
- Needs LEASH-146.
- Needs LEASH-102.
- Blocks LEASH-148.
- Blocks LEASH-149.
- Blocks LEASH-153.
- Blocks LEASH-156.

## Testing Requirements
Test curated selection, one-shot start, duplicate-click protection, rejected starts and the absence of raw scenario entry in customer UI.

## Related Files
- `solution/app/src/screens/Agent.tsx`
- `solution/app/src/screens/Permission.tsx`
- `solution/app/src/api/client.ts`
- `solution/contracts/policy-api.yaml`

## Out of scope
- Allowing customers to upload arbitrary scenario fixtures.
