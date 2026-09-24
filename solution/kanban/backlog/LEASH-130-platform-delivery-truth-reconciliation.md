# LEASH-130: Platform delivery truth reconciliation

**Status**: BACKLOG
**Priority**: P0
**Type**: feature
**Estimated Effort**: L
**Milestone**: M7 — Production hardening
**Rule source**: Engineering
**Decisions**: DEC-033, DEC-034, DEC-035, DEC-036, DEC-037
**Parent**: LEASH-129
**Task ID**: 129-T1
**Blocked by**: none
**Blocks**: LEASH-128, LEASH-132, LEASH-137, LEASH-142, LEASH-143, LEASH-148, LEASH-150, LEASH-156
**Updated**: 2026-09-24

## Description
Separate the engine verdict from Viseca's accepted outcome. A decision rejected after the local commit must never remain displayed or counted as paid.

## Business Value
The customer, rolling limits and future decisions must agree with the payment platform's source of truth.

## Acceptance Criteria
- [ ] Authorizations record engine verdict, delivery status and platform outcome separately.
- [ ] A successful decision POST records platform acceptance atomically in the local projection.
- [ ] A terminal refusal such as `deadline_passed` becomes `not_sent` or an equivalent non-approved state.
- [ ] Terminally refused decisions do not count toward spend, familiarity, duplicates or purchase count.
- [ ] The app distinguishes decided, submitted, accepted and not sent.
- [ ] `sent_to_viseca` is never populated for a failed delivery.
- [ ] A reconciliation job repairs or raises an integrity alert for local/platform disagreement.
- [ ] Keep pending local approvals/reservations separate from platform-accepted spending so concurrent attempts cannot overspend while acknowledgements are outstanding; release reservations after terminal refusal.
- [ ] Platform acceptance is not proof of settlement, shipment or delivery; customer wording names the actual state supplied by the contract.

## Technical Approach
Extend the authorization and outbox projections with explicit delivery states. Apply platform acknowledgements through a repository transaction, then derive ledger and UI state only from accepted outcomes.

### Dependencies
- Blocks LEASH-128.
- Blocks LEASH-132.
- Blocks LEASH-137.
- Blocks LEASH-142.
- Blocks LEASH-143.
- Blocks LEASH-148.
- Blocks LEASH-150.
- Blocks LEASH-156.

## Testing Requirements
Write failing adapter tests for accepted responses, retryable failures, terminal 4xx responses and crash-after-POST. Add ledger tests proving terminal refusals never count.

## Related Files
- `solution/engine/src/leash/adapters/viseca_api/outbox_sender.py`
- `solution/engine/src/leash/adapters/postgres/repository.py`
- `solution/engine/src/leash/adapters/postgres/unit_of_work.py`
- `solution/engine/src/leash/adapters/http/query_api.py`
- `solution/app/src/screens/status.ts`

## Out of scope
- Settlement, clearing and chargeback state beyond the challenge authorization API.
