# LEASH-102: External-agent handoff and checkout binding

**Status**: BACKLOG
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M8 — Permission control journey
**Rule source**: Product agreement + Viseca contract
**Decisions**: DEC-003, DEC-033, DEC-035, DEC-037
**Parent**: LEASH-008
**Task ID**: 008-T3
**Blocked by**: LEASH-101, LEASH-066, LEASH-051, LEASH-053
**Blocks**: LEASH-103, LEASH-147, LEASH-156
**Updated**: 2026-09-24

## Description
Connect the customer-confirmed permission to an external shopping-agent run and the actual checkout event. Reuse the Viseca start-run, mandate snapshot and authorization-event contract. The simulator represents the external agent for the challenge; record what a real integration would need without inventing a new payment protocol.

## Business Value
The checked purchase must belong to the authority the customer actually confirmed, and the permission assistant must have no purchase or payment capability.

## Acceptance Criteria
- [ ] A handoff contains the task, confirmed constraints and permission/version reference; authoritative rules stay in the policy service/platform.
- [ ] Unconfirmed, superseded or revoked permissions cannot start a new run; retries return the same recorded start result.
- [ ] The customer-authorized backend starts the simulator run, not an LLM tool. Permission-chat credentials cannot start purchases or call decision endpoints.
- [ ] Every checkout is correlated to its live authorization, run and confirmed mandate snapshot. The event mandate remains authoritative under DEC-003; discrepancies raise an integrity alert without silently rewriting it.
- [ ] Merchant/cart terms are untrusted claims; validation does not imply product quality, fulfillment or delivery has been verified.
- [ ] A changed cart is evaluated as the actual new attempt; a previous approval or customer answer cannot be replayed for different checkout terms.
- [ ] An agent cannot widen permission through its task text, checkout content or a different local policy reference. The tested payment path always passes through the existing worker/engine.
- [ ] Document the demonstrated simulator boundary and open production requirements: agent identity, credential scope, authoritative checkout source and prevention of payment-path bypass.

## Technical Approach
Reuse the existing run and worker paths. Define the minimal handoff record in the policy API contract and persist its linkage to consent evidence; no parallel local payment endpoint. Resolve production protocol and credential choices separately.

### Dependencies
- Needs LEASH-101.
- Needs LEASH-066.
- Needs LEASH-051.
- Needs LEASH-053.
- Blocks LEASH-103.
- Blocks LEASH-147.
- Blocks LEASH-156.

## Testing Requirements
Add fake-API integration cases for unconfirmed/revoked/stale handoff, duplicate start, correct run snapshot, mismatched reference, changed cart and forbidden permission-assistant capabilities. Run `cd solution/engine && uv run pytest tests/adapters/test_runs.py tests/adapters/test_worker.py tests/e2e`.

## Related Files
- `solution/contracts/policy-api.yaml`
- `solution/engine/src/leash/adapters/http/policy_api.py`
- `solution/engine/src/leash/adapters/viseca_api/worker.py`
- `solution/engine/tests/adapters/test_runs.py`
- `solution/engine/tests/adapters/test_worker.py`
- `solution/engine/tests/e2e/`
- `solution/RUNBOOK.md`

## Out of scope
- Building a shopping agent, inventing credentials, signing TaskCards or claiming real-card integration from simulator evidence.
