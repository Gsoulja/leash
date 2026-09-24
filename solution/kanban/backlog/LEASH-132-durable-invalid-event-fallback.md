# LEASH-132: Durable invalid-event fallback

**Status**: BACKLOG
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M7 — Production hardening
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-129
**Task ID**: 129-T3
**Blocked by**: LEASH-130
**Blocks**: LEASH-128, LEASH-142, LEASH-143
**Updated**: 2026-09-24

## Description
Persist the safe `invalid_event` response whenever a live authorization ID can be recovered, and retry delivery through the same durable mechanism as ordinary decisions.

## Business Value
A malformed upstream event must fail safely even when the first response attempt encounters a network failure.

## Acceptance Criteria
- [ ] Invalid events with a live ID create an auditable authorization/error record.
- [ ] The safe `step_up` body is stored before it is sent.
- [ ] Retryable send failures remain in the outbox.
- [ ] Terminal platform refusals use the delivery-truth state from LEASH-130.
- [ ] Duplicate malformed deliveries reuse the same stored response.
- [ ] Events without a recoverable live ID create an operator alert without leaking their body.

## Technical Approach
Add a minimal invalid-event receive path and reuse the transactional outbox and platform-acknowledgement projection.

### Dependencies
- Needs LEASH-130.
- Blocks LEASH-128.
- Blocks LEASH-142.
- Blocks LEASH-143.

## Testing Requirements
Write failing worker and repository tests for malformed-event delivery, network failure, restart, duplicate delivery and terminal refusal.

## Related Files
- `solution/engine/src/leash/adapters/viseca_api/worker.py`
- `solution/engine/src/leash/adapters/viseca_api/translate.py`
- `solution/engine/src/leash/adapters/postgres/repository.py`

## Out of scope
- Guessing an authorization ID when the upstream message does not contain one.
