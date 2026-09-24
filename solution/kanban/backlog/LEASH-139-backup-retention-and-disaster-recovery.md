# LEASH-139: Backup, retention and disaster recovery

**Status**: BACKLOG
**Priority**: P0
**Type**: infra
**Estimated Effort**: L
**Milestone**: M7 — Production hardening
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-129
**Task ID**: 129-T10
**Blocked by**: LEASH-135
**Blocks**: LEASH-142, LEASH-143
**Gate**: DECISION — product, security and operations approve retention periods and recovery objectives.
**Updated**: 2026-09-24

## Description
Define and prove backup, restore, retention, archival and disaster-recovery procedures for decision and audit data.

## Business Value
The service must recover auditable customer-control state without retaining sensitive data indefinitely.

## Acceptance Criteria
- [ ] Data classes and retention periods are documented for raw events, decisions, merchant text and audit events.
- [ ] Encrypted automated backups and point-in-time recovery are configured.
- [ ] RPO and RTO are stated and approved.
- [ ] A restore into an isolated environment is exercised and verified.
- [ ] Restored projections reconcile with the append-only decision log and platform state.
- [ ] Expiry and deletion preserve legally required audit evidence while removing unnecessary payloads.
- [ ] Disaster failover and return-to-primary procedures are documented.

## Technical Approach
Use managed database backup/PITR capabilities, scheduled restore drills and explicit retention jobs with immutable audit summaries.

### Dependencies
- Needs LEASH-135.
- Blocks LEASH-142.
- Blocks LEASH-143.

## Testing Requirements
Automate a backup/restore drill with checksum, row-count, projection-rebuild and reconciliation assertions.

## Related Files
- `solution/engine/migrations/`
- `solution/engine/src/leash/adapters/postgres/`
- `solution/RUNBOOK.md`

## Out of scope
- Choosing jurisdiction-specific legal retention periods without legal review.
