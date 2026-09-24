# LEASH-142: Load, failover and chaos evidence

**Status**: BACKLOG
**Priority**: P1
**Type**: test
**Estimated Effort**: L
**Milestone**: M7 — Production hardening
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-129
**Task ID**: 129-T13
**Blocked by**: LEASH-130, LEASH-131, LEASH-132, LEASH-135, LEASH-136, LEASH-137, LEASH-138, LEASH-139, LEASH-140, LEASH-141
**Blocks**: LEASH-143
**Updated**: 2026-09-24

## Description
Prove the production design under sustained load and controlled failures rather than relying only on unit and happy-path integration tests.

## Business Value
The safety invariants and response deadlines must survive the exact failures production introduces.

## Acceptance Criteria
- [ ] Load tests establish throughput, p50/p95/p99 latency and deadline-margin capacity.
- [ ] Soak tests detect connection, thread, memory and outbox growth leaks.
- [ ] Worker termination at every processing boundary loses no authorization.
- [ ] Database failover and platform outages recover within approved objectives.
- [ ] Multiple workers preserve per-card limits and idempotency.
- [ ] Retry storms and dead-letter growth trigger alerts without exhausting the database.
- [ ] The evidence bundle records environment, version, workload and results.

## Technical Approach
Create deterministic workload drivers and fault injection around network, process and database boundaries. Assert domain invariants after every run.

### Dependencies
- Needs LEASH-130, LEASH-131, LEASH-132 and LEASH-135 through LEASH-141.
- Blocks LEASH-143.

## Testing Requirements
Run load, soak and failure scenarios in a production-like staging environment and archive the reports.

## Related Files
- `solution/engine/tests/resilience/`
- `solution/app/e2e/`
- `solution/RUNBOOK.md`

## Out of scope
- Testing against real customer cards or production customer data.
