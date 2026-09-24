# LEASH-136: Pooled HTTP client and deadline budgets

**Status**: BACKLOG
**Priority**: P1
**Type**: infra
**Estimated Effort**: M
**Milestone**: M7 — Production hardening
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-129
**Task ID**: 129-T7
**Blocked by**: none
**Blocks**: LEASH-142, LEASH-143
**Updated**: 2026-09-24

## Description
Reuse a bounded asynchronous HTTP connection pool and propagate the remaining decision budget through connect, read, write and pool timeouts.

## Business Value
Avoiding a fresh client and TLS connection for every request reduces deadline risk and socket exhaustion.

## Acceptance Criteria
- [ ] One managed `httpx.AsyncClient` is reused for the service lifetime.
- [ ] Startup and shutdown create and close the client exactly once.
- [ ] Connection limits and keep-alive expiry are configurable.
- [ ] Decision POST timeouts never extend beyond `deadline_at`.
- [ ] Long-poll timeout remains separate from decision-send timeout.
- [ ] Retry behavior respects idempotency and the remaining wall-clock budget.

## Technical Approach
Make the client an async lifecycle resource and use explicit `httpx.Timeout` values derived from the operation budget.

### Dependencies
- Blocks LEASH-142.
- Blocks LEASH-143.

## Testing Requirements
Write failing transport tests proving connection reuse, shutdown, pool exhaustion behavior and no send after the authoritative deadline.

## Related Files
- `solution/engine/src/leash/adapters/viseca_api/client.py`
- `solution/engine/src/leash/adapters/viseca_api/worker.py`
- `solution/engine/src/leash/service.py`

## Out of scope
- Retrying non-idempotent calls without a platform idempotency guarantee.
