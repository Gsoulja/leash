# LEASH-137: Outbox leases and dead-letter recovery

**Status**: BACKLOG
**Priority**: P0
**Type**: feature
**Estimated Effort**: L
**Milestone**: M7 — Production hardening
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-129
**Task ID**: 129-T8
**Blocked by**: LEASH-130
**Blocks**: LEASH-138, LEASH-142, LEASH-143
**Updated**: 2026-09-24

## Description
Move outbox network I/O outside database transactions, coordinate multiple senders with durable leases, and expose terminal failures for operator recovery.

## Business Value
Recovery traffic must scale without holding database locks during network calls or silently burying undelivered decisions.

## Acceptance Criteria
- [ ] A sender claims rows in a short transaction and performs HTTP outside it.
- [ ] Claim leases expire so a crashed sender's rows are recoverable.
- [ ] Multiple senders do not concurrently deliver the same active claim.
- [ ] Per-authorization ordering keeps resolve behind decision.
- [ ] Retry attempts use bounded exponential backoff with jitter.
- [ ] Terminal failures enter a visible dead-letter state with reason and operator action.
- [ ] Dead-letter replay is audited and cannot change the stored decision body.

## Technical Approach
Implement claim/send/ack phases with lease owner and expiry columns. Integrate final acknowledgement with LEASH-130.

### Dependencies
- Needs LEASH-130.
- Blocks LEASH-138.
- Blocks LEASH-142.
- Blocks LEASH-143.

## Testing Requirements
Write failing tests for two senders, sender crash after claim, lease expiry, ordering, jitter, terminal failure and audited replay.

## Related Files
- `solution/engine/src/leash/adapters/viseca_api/outbox_sender.py`
- `solution/engine/migrations/versions/`
- `solution/engine/src/leash/adapters/postgres/unit_of_work.py`

## Out of scope
- A general-purpose message broker migration.
