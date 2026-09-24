# LEASH-102: Assistant purchases through the engine

**Status**: BACKLOG
**Priority**: P2
**Type**: feature
**Estimated Effort**: M
**Milestone**: M6 — Differentiators (after MVP)
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-008
**Task ID**: 008-T3
**Blocked by**: LEASH-101, LEASH-052
**Blocks**: LEASH-103
**Updated**: 2026-09-23

## Description
The assistant proposes purchases to a local engine endpoint as an untrusted client (vision track); decisions show in the app.

## Business Value
Shows the leash works on any agent, including our own.

## Acceptance Criteria
- [ ] Purchases go through decide-purchase like simulator events.
- [ ] The assistant has no access to mandate writes.

## Technical Approach
Local endpoint in the engine; not sent to the Viseca API.

### Dependencies
- Needs LEASH-101.
- Needs LEASH-052.
- Blocks LEASH-103.

## Testing Requirements
Write first: `test_assistant_purchase_over_limit_is_declined`.

## Related Files
- `solution/engine/src/leash/adapters/http/local_agent_api.py`
- `solution/engine/tests/adapters/test_local_agent_api.py`

## Out of scope
- Sending local purchases to the hosted simulator.
