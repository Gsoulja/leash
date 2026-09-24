# LEASH-140: Production security hardening

**Status**: BACKLOG
**Priority**: P0
**Type**: infra
**Estimated Effort**: L
**Milestone**: M7 — Production hardening
**Rule source**: Engineering
**Decisions**: DEC-033, DEC-034, DEC-035, DEC-036, DEC-037
**Parent**: LEASH-129
**Task ID**: 129-T11
**Blocked by**: none
**Blocks**: LEASH-142, LEASH-143
**Gate**: DECISION — security approves the threat model and residual risks.
**Updated**: 2026-09-24

## Description
Harden transport, secrets, networks, input limits, database privileges and audit protection around the service.

## Business Value
Financial authorization data and controls need defense in depth across infrastructure and persistence boundaries.

## Acceptance Criteria
- [ ] TLS is required for public traffic, service-to-service calls and database connections.
- [ ] Secrets come from a managed secret store and have a tested rotation procedure.
- [ ] API, worker and migration processes use separate least-privilege database roles.
- [ ] Network policy restricts database and outbound platform access.
- [ ] Request sizes, connection counts and mutation rates have safe limits.
- [ ] Stored sensitive fields are encrypted according to data classification.
- [ ] Audit events are tamper-evident and identify their originating workload or operator process.
- [ ] A threat model covers replay, tampering, prompt injection, denial of service and insider misuse.
- [ ] Real-customer reads and mutations require authenticated identity and server-side customer/account/card ownership checks; permission-LLM credentials cannot impersonate customer confirmation.
- [ ] Consent evidence binds the authenticated customer to the exact reviewed draft revision, payload and time; replayed, stale or cross-customer confirmations and purchase answers are rejected.
- [ ] Production agent identity, scoped credentials and authoritative checkout ingestion are explicitly designed and tested so the agent cannot bypass Leash with general card authority. Simulator evidence alone does not satisfy this criterion.

## Technical Approach
Apply controls at the edge, workload identity, database and storage layers; keep merchant text untrusted throughout.

### Dependencies
- Blocks LEASH-142.
- Blocks LEASH-143.

## Testing Requirements
Include unauthenticated and cross-customer reads/mutations, forged consent, stale-revision replay and attempted bypass through agent credentials. The authentication mechanism and production credential protocol remain design decisions; no particular vendor or signing scheme is assumed.

Add configuration tests and security integration tests for TLS enforcement, secret rotation, privilege denial, request limits and sensitive-data-safe audit output.

## Related Files
- `solution/engine/src/leash/service.py`
- `solution/engine/src/leash/config.py`
- `solution/docker-compose.yml`
- `solution/RUNBOOK.md`

## Out of scope
- Formal certification or legal approval.
