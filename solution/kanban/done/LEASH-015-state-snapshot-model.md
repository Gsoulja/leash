# LEASH-015: State snapshot model

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: S
**Milestone**: M1 — SCEN0000 offline vertical slice
**Rule source**: Engineering
**Decisions**: DEC-010, DEC-011, DEC-015
**Parent**: LEASH-001
**Task ID**: 001-T6
**Blocked by**: LEASH-012
**Blocks**: LEASH-016, LEASH-018, LEASH-024, LEASH-025, LEASH-026, LEASH-030, LEASH-043, LEASH-128
**Updated**: 2026-09-23

## Description
The immutable input describing history: prior decisions in this run with their final state, card familiarity per merchant, known devices and countries, merchant catalogue.

## Business Value
Keeps `decide()` pure: repositories build the snapshot, the core only reads it.

## Acceptance Criteria
- [x] Snapshot lists prior purchases with final state (approved, waiting, declined, timed_out).
- [x] Familiarity = approved history count + approvals earlier in this run.
- [x] Known devices and countries include this run's approvals.
- [x] Familiarity counts approved purchases only, never refunds, cash withdrawals or declines.
- [x] Snapshot carries the platform's approved_spend_in_period_chf for cross-checking.

## Technical Approach
Frozen dataclass in `domain/snapshot.py` with small query helpers (approved in window, recent at merchant).

### Dependencies
- Needs LEASH-012.
- Blocks LEASH-016.
- Blocks LEASH-018.
- Blocks LEASH-024.
- Blocks LEASH-025.
- Blocks LEASH-026.
- Blocks LEASH-030.
- Blocks LEASH-043.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_waiting_purchase_is_not_spend`, `test_run_approval_counts_as_familiar`.

## Related Files
- `solution/engine/src/leash/domain/snapshot.py`
- `solution/engine/tests/domain/test_snapshot.py`

## Out of scope
- Loading from Postgres (LEASH-043) or CSV (LEASH-030).

## Review log

### 2026-09-23 — independent agent review
- [x] met — criterion 1: prior purchases with validated final state; other-card purchases rejected; only approved counts as spend.
- [x] met — criterion 2: familiarity = history purchases + this run's approvals; waiting doesn't count.
- [x] met — criterion 3: known devices/countries from approved history plus this run's approvals only.
- [x] met — criterion 4: baseline keeps only approved `purchase` rows (refunds, withdrawals, declines excluded).
- [x] met — criterion 5: `platform_period_spend_chf` carries context.approved_spend_in_period_chf.
Check: 8 passed; mypy strict clean.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
