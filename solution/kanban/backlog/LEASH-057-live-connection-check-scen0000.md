# LEASH-057: Live connection check (SCEN0000)

**Status**: BACKLOG
**Priority**: P0
**Type**: test
**Estimated Effort**: S
**Milestone**: M5 — Hosted API and release
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-004
**Task ID**: 004-T8
**Blocked by**: LEASH-056
**Blocks**: LEASH-114, LEASH-128
**Gate**: DECISION — needs the team API key, only handed out on event day. A human runs it and confirms the result.
**Updated**: 2026-09-23

## Description
Run the one-purchase connection check against the hosted API with the team key.

## Business Value
First proof the real integration works.

## Acceptance Criteria
- [ ] Health, bootstrap and reference data calls succeed.
- [ ] Mandate created and confirmed.
- [ ] SCEN0000 decision accepted before its deadline.

## Technical Approach
Script `scripts/connection_check.py`.

### Dependencies
- Needs LEASH-056.
- Blocks LEASH-114.
- Blocks LEASH-128.

## Testing Requirements
Run the script with TEAM_API_KEY set; record the run_id.

## Related Files
- `solution/engine/scripts/connection_check.py`

## Out of scope
- Other scenarios.
