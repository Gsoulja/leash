# LEASH-032: In-memory ledger and replay runner

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M1 — SCEN0000 offline vertical slice
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-002
**Task ID**: 002-T3
**Blocked by**: LEASH-027, LEASH-028, LEASH-030, LEASH-031, LEASH-071
**Blocks**: LEASH-033, LEASH-121, LEASH-128
**Updated**: 2026-09-23

## Description
Replays a scenario through `decide()` with an in-memory ledger, recording decisions and optionally simulated customer answers.

## Business Value
Fast offline check of the whole engine and a demo aid.

## Acceptance Criteria
- [x] Replays each scenario in order and prints ID, shop, CHF, verdict and reasons.
- [x] Customer answers can be scripted: none, approve all, decline all, or per ID.
- [x] `uv run python scripts/replay.py SCEN0004` works.

## Technical Approach
`application/replay.py` + `scripts/replay.py`, in-memory repository implementing the same port as Postgres.

### Dependencies
- Needs LEASH-027.
- Needs LEASH-028.
- Needs LEASH-030.
- Needs LEASH-031.
- Needs LEASH-071.
- Blocks LEASH-033.
- Blocks LEASH-121.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_replay_records_one_decision_per_attempt`.

## Related Files
- `solution/engine/src/leash/application/replay.py`
- `solution/engine/scripts/replay.py`
- `solution/engine/tests/application/test_replay.py`

## Out of scope
- Postgres (LEASH-043).

## Review log

### 2026-09-23 — independent agent review
- [x] met — replays in the pack's replay order and prints ID, shop, CHF, verdict (plus final state) and reasons.
- [x] met — answers none / approve / decline / per ID; only step_up rows change; a decline is never turned into approved. CLI gap: an empty ID (`--answers =approve`) was accepted — fixed after review (`test_script_rejects_malformed_answers`).
- [x] met — `uv run python scripts/replay.py SCEN0004` exits 0 with 11 rows; no args replays all five; an unknown scenario exits 2.
- Ledger: only final approvals count as spend and familiarity; approving AU0006 makes AU0008 break the 7-day limit.
Notes: unknown or wrongly cased per-ID answers are silently ignored. The in-memory ledger is the stand-in; the shared repository port comes with LEASH-043.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
