# LEASH-002: Scenario replay and safety properties

**Status**: BACKLOG
**Priority**: P0
**Type**: epic
**Total Effort**: ~20 h (6 tickets; ~20 h in the MVP)
**Updated**: 2026-09-23

## Description
Run all 45 challenge purchases through the pure core with in-memory state, pin the behaviours we agreed on, and prove the safety properties with property tests.

## Business Value
Gives the team a fast, offline regression net and evidence for judges that the engine behaves as designed.

## Reference
Agreed behaviours are listed in CLAUDE.md under 'Development workflow: TDD'.

## Sub-tasks
- [ ] LEASH-030 (002-T1) [M1]: Challenge-pack loader · M
- [ ] LEASH-031 (002-T2) [M1]: Compiled mandates for the five scenario instructions · S
- [ ] LEASH-032 (002-T3) [M1]: In-memory ledger and replay runner · M
- [ ] LEASH-033 (002-T4) [M2]: Replay tests pinning agreed behaviours · M
- [ ] LEASH-034 (002-T5) [M2]: Property tests for safety · M
- [ ] LEASH-121 (002-T6) [M1]: SCEN0000 offline vertical slice · S

## Done when
Every sub-task is in `done/`.
