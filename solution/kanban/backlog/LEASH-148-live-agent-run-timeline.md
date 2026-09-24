# LEASH-148: Live Agent run timeline

**Status**: BACKLOG
**Priority**: P0
**Type**: feature
**Estimated Effort**: L
**Milestone**: M8 — Great demo
**Rule source**: Product
**Decisions**: none
**Parent**: LEASH-144
**Task ID**: 144-T4
**Blocked by**: LEASH-145, LEASH-147
**Blocks**: LEASH-149, LEASH-150, LEASH-152, LEASH-153
**Updated**: 2026-09-24

## Description
Show the agent working through a run as an authoritative live timeline with progress, merchant activity, rule checks, interventions and recovery states.

## Business Value
Visible execution is the core of the demo: the audience needs to see Leash mediate the agent rather than infer it from a final payment list.

## Acceptance Criteria
- [ ] The active run shows running, paused/waiting, finished and failed states.
- [ ] Progress shows attempted and total payments when the total is known.
- [ ] Each recorded authorization appears once with merchant, amount and current outcome.
- [ ] Timeline entries distinguish searching, evaluating, approved, blocked and customer-needed states without fabricating backend events.
- [ ] New event-stream records update the timeline without reordering completed entries.
- [ ] Reconnect and reload reconstruct the same timeline from durable state.
- [ ] A waiting payment opens the existing customer decision prompt with context.
- [ ] No-event periods show a meaningful active state rather than a frozen screen.

## Technical Approach
Build a run projection from `GET /api/runs/{id}`, run-scoped payments and SSE invalidation. Add event types only where a real durable fact is missing.

### Dependencies
- Needs LEASH-145.
- Needs LEASH-147.
- Blocks LEASH-149.
- Blocks LEASH-150.
- Blocks LEASH-152.
- Blocks LEASH-153.

## Testing Requirements
Use a deterministic event fixture to test ordering, deduplication, reconnect, waiting decisions, failure and completion. Add a browser test that observes progress change without reloading.

## Related Files
- `solution/app/src/App.tsx`
- `solution/app/src/api/useAsks.ts`
- `solution/app/src/api/client.ts`
- `solution/contracts/policy-api.yaml`

## Out of scope
- Invented chain-of-thought or simulated reasoning text.
