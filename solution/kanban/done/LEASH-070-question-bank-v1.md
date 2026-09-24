# LEASH-070: Question bank v1

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: S
**Milestone**: M1 — SCEN0000 offline vertical slice
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-006
**Task ID**: 006-T1
**Blocked by**: none
**Blocks**: LEASH-071, LEASH-073, LEASH-074, LEASH-128
**Updated**: 2026-09-23

## Description
The five typed questions with exact wording and a version hash: injection, add-on, recurring charges, return terms, item match.

## Business Value
Training and inference must use identical question text.

## Acceptance Criteria
- [x] Questions stored in one module with a stable hash.
- [x] Changing any wording changes the hash.

## Technical Approach
`reading/question_bank.py`.

### Dependencies
- None.
- Blocks LEASH-071.
- Blocks LEASH-073.
- Blocks LEASH-074.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_hash_changes_with_wording`.

## Related Files
- `solution/engine/src/leash/reading/question_bank.py`
- `solution/engine/tests/reading/test_question_bank.py`

## Out of scope
- Training.

## Review log

### 2026-09-23 — independent agent review
- [x] met — criterion 1: five typed questions in one read-only module; SHA-256 over canonical JSON; same hash across PYTHONHASHSEED 1/2/3 and any key order (`qb-v1-08f4d70ec20587a1`).
- [x] met — criterion 2: rewording any of the five questions, a criterion label or a type changes the hash.
- Out-of-list file `reading/__init__.py` judged necessary. "Written first" can't be verified from files alone.
Check: `uv run pytest tests/reading` — 6 passed.
Verdict: moved to review.
