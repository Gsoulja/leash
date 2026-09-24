# LEASH-031: Compiled mandates for the five scenario instructions

**Status**: DONE
**Priority**: P0
**Type**: test
**Estimated Effort**: S
**Milestone**: M1 — SCEN0000 offline vertical slice
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-002
**Task ID**: 002-T2
**Blocked by**: LEASH-013
**Blocks**: LEASH-032, LEASH-065, LEASH-121, LEASH-128
**Updated**: 2026-09-23

## Description
Hand-compiled mandates for the five public instructions, as the customer would confirm them. A stand-in for the compiler, used only by tests and replay.

## Business Value
Lets replay run before LEASH-065 exists.

## Acceptance Criteria
- [x] One compiled mandate per scenario, matching the rules shown in the prototype.
- [x] Lives under tests/fixtures, never imported by production code.
- [x] Fixtures are expressed as hard_rules through the registry, including fulfilment, quantity and single-purchase rules.
- [x] Tested for full policy meaning, not only limits, days and size.

## Technical Approach
`tests/fixtures/mandates.py`.

### Dependencies
- Needs LEASH-013.
- Blocks LEASH-032.
- Blocks LEASH-065.
- Blocks LEASH-121.
- Blocks LEASH-128.

## Testing Requirements
Write first: a test that every fixture is at least as strict as its instruction's numbers (limits, days, size).

## Related Files
- `solution/engine/tests/fixtures/mandates.py`

## Out of scope
- Automatic compilation (LEASH-065).

## Review log

### 2026-09-23 — independent agent review
- [x] met — criterion 1: five mandates with the exact catalogue instructions; every difference from the prototype is a refinement backed by DEC-013 (quantity 1), DEC-022 (delivery) or DEC-024 (risk points); no rule-level mismatch.
- [x] met — criterion 2: under tests/fixtures; a test enforces no import from src.
- [x] met — criterion 3: all rules are registry fields; check_rules passes; nothing unsupported.
- [x] met — criterion 4: every non-numeric rule asserted per scenario.
- Fixed after review: SCEN0003 note now says "risk points" (DEC-024) instead of "signals".
Check: 13 passed.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
