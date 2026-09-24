# LEASH-128: Release-readiness gate

**Status**: BACKLOG
**Priority**: P0
**Type**: test
**Estimated Effort**: S
**Milestone**: M5 — Hosted API and release
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-009
**Task ID**: 009-T9
**Blocked by**: LEASH-010, LEASH-011, LEASH-012, LEASH-013, LEASH-014, LEASH-015, LEASH-016, LEASH-017, LEASH-018, LEASH-019, LEASH-020, LEASH-021, LEASH-022, LEASH-023, LEASH-024, LEASH-025, LEASH-026, LEASH-027, LEASH-028, LEASH-030, LEASH-031, LEASH-032, LEASH-033, LEASH-034, LEASH-040, LEASH-041, LEASH-042, LEASH-043, LEASH-044, LEASH-045, LEASH-050, LEASH-051, LEASH-052, LEASH-053, LEASH-054, LEASH-055, LEASH-056, LEASH-057, LEASH-060, LEASH-061, LEASH-062, LEASH-063, LEASH-064, LEASH-065, LEASH-066, LEASH-070, LEASH-071, LEASH-072, LEASH-090, LEASH-091, LEASH-092, LEASH-093, LEASH-094, LEASH-095, LEASH-096, LEASH-110, LEASH-111, LEASH-112, LEASH-114, LEASH-116, LEASH-117, LEASH-118, LEASH-119, LEASH-120, LEASH-121, LEASH-122, LEASH-123, LEASH-124, LEASH-125, LEASH-126, LEASH-127, LEASH-130, LEASH-131, LEASH-132, LEASH-133, LEASH-153
**Blocks**: LEASH-115
**Gate**: DECISION — a human confirms every release criterion has evidence.
**Updated**: 2026-09-24

## Description
Evidence-based gate before the freeze: every required ticket done, and the release criteria proven.

## Business Value
Submission only after all project requirements are proven, not just when a demo runs.

## Acceptance Criteria
- [ ] Every compiler-produced hard-rule field is supported.
- [ ] All 45 attempts replay without errors; agreed behaviours pass.
- [ ] Tightening never loosens; model output never weakens the deterministic verdict.
- [ ] Duplicate delivery never double-counts; concurrent decisions can't breach limits; late approval can't bypass a hard rule.
- [ ] All fake-API decisions accepted before deadline_at; restart resends the outbox safely.
- [ ] Open asks survive reconnects; customer can confirm, resolve, tighten and revoke.
- [ ] Platform/local mismatches are visible; secrets and merchant text never leak into logs or unsafe rendering.
- [ ] Documentation matches the implementation; every Open decision is answered or accepted.
- [ ] Platform-refused decisions never appear or count as paid; abandoned receives and malformed-event fallbacks recover after restart.
- [ ] Cockpit payments, counts and spending use the same run.
- [ ] An unfamiliar observer can follow the agent conversation, visible work, customer intervention and final outcome without implementation narration.

## Technical Approach
Checklist ticket; each criterion links to its evidence (test run, log, screenshot).

### Dependencies
- Needs LEASH-010.
- Needs LEASH-011.
- Needs LEASH-012.
- Needs LEASH-013.
- Needs LEASH-014.
- Needs LEASH-015.
- Needs LEASH-016.
- Needs LEASH-017.
- Needs LEASH-018.
- Needs LEASH-019.
- Needs LEASH-020.
- Needs LEASH-021.
- Needs LEASH-022.
- Needs LEASH-023.
- Needs LEASH-024.
- Needs LEASH-025.
- Needs LEASH-026.
- Needs LEASH-027.
- Needs LEASH-028.
- Needs LEASH-030.
- Needs LEASH-031.
- Needs LEASH-032.
- Needs LEASH-033.
- Needs LEASH-034.
- Needs LEASH-040.
- Needs LEASH-041.
- Needs LEASH-042.
- Needs LEASH-043.
- Needs LEASH-044.
- Needs LEASH-045.
- Needs LEASH-050.
- Needs LEASH-051.
- Needs LEASH-052.
- Needs LEASH-053.
- Needs LEASH-054.
- Needs LEASH-055.
- Needs LEASH-056.
- Needs LEASH-057.
- Needs LEASH-060.
- Needs LEASH-061.
- Needs LEASH-062.
- Needs LEASH-063.
- Needs LEASH-064.
- Needs LEASH-065.
- Needs LEASH-066.
- Needs LEASH-070.
- Needs LEASH-071.
- Needs LEASH-072.
- Needs LEASH-090.
- Needs LEASH-091.
- Needs LEASH-092.
- Needs LEASH-093.
- Needs LEASH-094.
- Needs LEASH-095.
- Needs LEASH-096.
- Needs LEASH-110.
- Needs LEASH-111.
- Needs LEASH-112.
- Needs LEASH-114.
- Needs LEASH-116.
- Needs LEASH-117.
- Needs LEASH-118.
- Needs LEASH-119.
- Needs LEASH-120.
- Needs LEASH-121.
- Needs LEASH-122.
- Needs LEASH-123.
- Needs LEASH-124.
- Needs LEASH-125.
- Needs LEASH-126.
- Needs LEASH-127.
- Needs LEASH-130.
- Needs LEASH-131.
- Needs LEASH-132.
- Needs LEASH-133.
- Needs LEASH-153.
- Blocks LEASH-115.

## Testing Requirements
A human walks the checklist with the evidence.

## Related Files
- `solution/docs/decisions.md`

## Out of scope
- New features.
