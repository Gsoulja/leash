# LEASH-042: Seed script for reference data

**Status**: DONE
**Priority**: P0
**Type**: infra
**Estimated Effort**: S
**Milestone**: M3 — Durable fake-API integration
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-003
**Task ID**: 003-T3
**Blocked by**: LEASH-041, LEASH-030
**Blocks**: LEASH-127, LEASH-128
**Updated**: 2026-09-23

## Description
Load merchants and authorization history from the pack and refresh the familiarity view.

## Business Value
Familiarity and lookalike checks need the history in the database.

## Acceptance Criteria
- [x] Loads 58 merchants and 4,701 history rows.
- [x] Idempotent: running twice changes nothing.
- [x] Familiarity view shows 6 approved payments for CA0039 at ME0022.
- [~] Runs automatically as part of startup readiness — **moved to LEASH-127** (its AC1: "readiness fails until migrations and seed are done"); hook `leash.adapters.pack.seed.seed()` delivered here.

## Technical Approach
`scripts/seed.py` using the pack loader.

### Dependencies
- Needs LEASH-041.
- Needs LEASH-030.
- Blocks LEASH-127.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_seed_is_idempotent`.

## Related Files
- `solution/engine/scripts/seed.py`
- `solution/engine/tests/adapters/test_seed.py`

## Out of scope
- Scenario attempts (they arrive through the API).

## Review log

### 2026-09-23 — independent agent review
- [x] met — 58 merchants and 4,701 history rows; every CSV row compared (0 mismatches); blank device IDs stored as NULL; exact decimals; timezone-aware timestamps.
- [x] met — idempotent: second run writes (0, 0), md5 and xmin unchanged; altered/deleted rows are repaired and only those touched; a failing row rolls back everything.
- [x] met — familiarity view: CA0039 @ ME0022 = 6; whole view recounted from the CSV matches (declines, refunds, withdrawals excluded — DEC-011).
- [~] handed off — startup readiness: the hook exists and LEASH-127 (blocked by this ticket) covers it in its AC1; criterion moved there.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run (criterion 4 carried by LEASH-127).
