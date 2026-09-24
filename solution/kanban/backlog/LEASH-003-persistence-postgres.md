# LEASH-003: Persistence (Postgres)

**Status**: BACKLOG
**Priority**: P0
**Type**: epic
**Total Effort**: ~28 h (6 tickets; ~28 h in the MVP)
**Updated**: 2026-09-23

## Description
Postgres 17 storage: schema, seed data, idempotent writes, per-card locking, append-only decision log, outbox.

## Business Value
State over time (rolling limits, duplicates, customer answers) must survive restarts and concurrent customer actions.

## Reference
Design: solution/docs/system-design.html (failure table) and the Postgres schema agreed in chat, recorded in CLAUDE.md.

## Sub-tasks
- [ ] LEASH-040 (003-T1) [M3]: Docker Compose Postgres and test database · S
- [ ] LEASH-041 (003-T2) [M3]: Initial schema migration · L
- [ ] LEASH-042 (003-T3) [M3]: Seed script for reference data · S
- [ ] LEASH-043 (003-T4) [M3]: Repository port and Postgres adapter · L
- [ ] LEASH-044 (003-T5) [M3]: Decision transaction with lock, log, outbox and notify · M
- [ ] LEASH-045 (003-T6) [M3]: Customer resolution and timeout sweeper · M

## Done when
Every sub-task is in `done/`.
