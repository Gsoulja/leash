# LEASH-135: Safe production database migrations

**Status**: BACKLOG
**Priority**: P0
**Type**: infra
**Estimated Effort**: M
**Milestone**: M7 — Production hardening
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-129
**Task ID**: 129-T6
**Blocked by**: none
**Blocks**: LEASH-139, LEASH-142, LEASH-143
**Updated**: 2026-09-24

## Description
Make every schema change safe on populated databases, beginning with migration `0002`, which adds a non-null column without a backfill.

## Business Value
Deployments must not fail, corrupt data or require dropping the production database.

## Acceptance Criteria
- [ ] A database containing realistic `0001` rows upgrades to head without data loss.
- [ ] Required columns use expand, backfill, validation and contract steps.
- [ ] Long-running migrations have bounded locks and an operational rollback plan.
- [ ] Application versions remain compatible during rolling deployment.
- [ ] Migration checks run against both an empty and populated previous-version database.
- [ ] Downgrade policy is documented; irreversible migrations require backup evidence.

## Technical Approach
Replace unsafe DDL with staged Alembic revisions and add upgrade fixtures representing every supported previous release.

### Dependencies
- Blocks LEASH-139.
- Blocks LEASH-142.
- Blocks LEASH-143.

## Testing Requirements
Write a failing migration test that inserts an authorization at revision `0001`, upgrades to head and verifies the row and reconstructed purchase.

## Related Files
- `solution/engine/migrations/versions/0002_purchase_column.py`
- `solution/engine/migrations/`
- `solution/engine/src/leash/adapters/postgres/migrate.py`

## Out of scope
- Changing the database technology.
