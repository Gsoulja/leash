# LEASH-011: SimTime and WallTime value objects

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: S
**Milestone**: M1 — SCEN0000 offline vertical slice
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-001
**Task ID**: 001-T2
**Blocked by**: none
**Blocks**: LEASH-012, LEASH-128
**Updated**: 2026-09-23

## Description
Separate types for simulated purchase time and the real clock, so windows and deadlines can't be mixed.

## Business Value
The brief requires spending windows on simulated time and deadlines on the real clock.

## Acceptance Criteria
- [x] SimTime and WallTime parse ISO-8601 UTC and reject naive timestamps.
- [x] Comparing or subtracting a SimTime with a WallTime is a type error (mypy) and raises at runtime.
- [x] SimTime exposes `within(earlier, window)` for rolling windows and `local()` in Europe/Zurich.

## Technical Approach
Frozen dataclasses in `domain/clock.py`.

### Dependencies
- None.
- Blocks LEASH-012.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_seven_day_window_is_trailing_168_hours`, `test_naive_timestamp_rejected`.

## Related Files
- `solution/engine/src/leash/domain/clock.py`
- `solution/engine/tests/domain/test_clock.py`

## Out of scope
- Timezone handling beyond Europe/Zurich display.

## Review log

### 2026-09-23 — independent agent review (round 1)
- [x] met — criterion 1: naive timestamps rejected by parse and constructor; offsets normalised to UTC.
- [ ] not met — criterion 2: mypy did not report mixed `==` / `!=` (custom `__eq__` disables --strict-equality); runtime raising was complete.
- [x] met — criterion 3: `within` is the half-open trailing window, tested at 167:59:59 / 168 h / same instant / later; `local()` checked for summer and winter offsets.
- Out-of-list files (mypy dev dependency, py.typed) judged necessary.
Verdict: returned to in-progress. Fix: `__eq__` is defined for the runtime only (hidden from type checking), so mypy --strict-equality now reports mixed equality; test extended to `==` and `!=`.

### 2026-09-23 — independent agent review (round 2)
- [x] met — criterion 1: naive and date-only timestamps rejected; offsets normalised; frozen.
- [x] met — criterion 2: mypy --strict-equality reports all 10 mixed operations (==, !=, -, <, <=, >, >=, within); same-type use not flagged; every mixed operation raises TypeError at runtime; same-type equality and hashing consistent.
- [x] met — criterion 3: trailing half-open window tested at the 168 h boundary; Zurich summer and winter offsets tested.
- Noted outside the criteria: `SimTime in [WallTime, …]` raises TypeError (consequence of criterion 2).
Check: 13 passed; `mypy src --strict` clean.
Verdict: moved to review.
