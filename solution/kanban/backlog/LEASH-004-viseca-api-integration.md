# LEASH-004: Viseca API integration

**Status**: BACKLOG
**Priority**: P0
**Type**: epic
**Total Effort**: ~36 h (10 tickets; ~36 h in the MVP)
**Updated**: 2026-09-23

## Description
Anti-corruption layer, long-poll worker, deadline budget and watchdog, outbox sender, and an end-to-end test against a fake Viseca API.

## Business Value
Without it nothing is scored: the hosted simulator only talks to a worker.

## Reference
API contract: technical_details.md sections 4–8.

## Sub-tasks
- [ ] LEASH-050 (004-T1) [M3]: Viseca API client · M
- [ ] LEASH-051 (004-T2) [M1]: Event translator (anti-corruption layer) · M
- [ ] LEASH-052 (004-T3) [M3]: Decide-purchase use case with deadline budget · M
- [ ] LEASH-053 (004-T4) [M3]: Long-poll worker · M
- [ ] LEASH-054 (004-T5) [M3]: Outbox sender · S
- [ ] LEASH-055 (004-T6) [M3]: Fake Viseca API for tests · M
- [ ] LEASH-056 (004-T7) [M3]: End-to-end test against the fake API · M
- [ ] LEASH-057 (004-T8) [M5]: Live connection check (SCEN0000) · S
- [ ] LEASH-122 (004-T9) [M3]: Runtime configuration and bootstrap settings · M
- [ ] LEASH-126 (004-T10) [M5]: Resilience and performance suite · M

## Done when
Every sub-task is in `done/`.
