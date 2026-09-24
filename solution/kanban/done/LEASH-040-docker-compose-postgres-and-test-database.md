# LEASH-040: Docker Compose Postgres and test database

**Status**: DONE
**Priority**: P0
**Type**: infra
**Estimated Effort**: S
**Milestone**: M3 — Durable fake-API integration
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-003
**Task ID**: 003-T1
**Blocked by**: none
**Blocks**: LEASH-041, LEASH-128
**Updated**: 2026-09-23

## Description
Postgres 17 in Docker Compose for development, plus a disposable database for adapter tests.

## Business Value
Everyone runs the same database locally.

## Acceptance Criteria
- [x] `docker compose up -d db` starts Postgres 17 with a healthcheck.
- [x] Tests get an isolated database and clean it up.
- [x] Connection settings come from DATABASE_URL.

## Technical Approach
`solution/docker-compose.yml`, `tests/conftest.py` fixture.

### Dependencies
- None.
- Blocks LEASH-041.
- Blocks LEASH-128.

## Testing Requirements
Write first: a smoke test that connects and runs `select 1`.

## Related Files
- `solution/docker-compose.yml`
- `solution/engine/tests/conftest.py`
- `solution/engine/tests/adapters/test_db_smoke.py`

## Out of scope
- Cloud hosting.

## Review log

### 2026-09-23 — independent agent review
- [x] met — criterion 1: `db` service on postgres:17 with a pg_isready healthcheck; container reported healthy; server major version 17 asserted by test.
- [x] met — criterion 2: each test gets `leash_test_<uuid>` and it is dropped with FORCE in a finally block; no `leash_test_%` databases left after the run.
- [x] met — criterion 3: `database_url` fixture reads DATABASE_URL; tested with monkeypatch; wrong credentials fail instead of skipping.
- Note: default host port is 55432 because 5433 is taken by an unrelated project on this machine.
Check: 6 passed, 0 skipped.
Verdict: moved to review.
