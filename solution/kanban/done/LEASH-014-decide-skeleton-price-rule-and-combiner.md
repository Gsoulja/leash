# LEASH-014: decide() skeleton, price rule and combiner

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M1 — SCEN0000 offline vertical slice
**Rule source**: Engineering
**Decisions**: DEC-005
**Parent**: LEASH-001
**Task ID**: 001-T5
**Blocked by**: LEASH-012, LEASH-013
**Blocks**: LEASH-016, LEASH-017, LEASH-018, LEASH-019, LEASH-021, LEASH-022, LEASH-023, LEASH-024, LEASH-025, LEASH-026, LEASH-027, LEASH-119, LEASH-120, LEASH-121, LEASH-128
**Updated**: 2026-09-23

## Description
The first slice of the pure core: `decide()` runs a list of rules, collects every check, and combines them most-restrictive-wins, applying the uncertainty policy to warnings. The first rule is the per-order price limit.

## Business Value
Establishes the Notification and combiner patterns every later rule plugs into.

## Acceptance Criteria
- [x] An order at exactly the limit is approved (CHF 20.00 vs CHF 20).
- [x] One cent over the limit is declined with a plain-language reason.
- [x] Checks carry label, agreed value, actual value, status (pass/fail/warn/info), detail and reason code.
- [x] Verdict order is decline > step_up > approve; a warning maps through the uncertainty policy (ask → step_up, decline → decline, approve → approve).
- [x] Integrity checks (unsupported rules) are combined before ordinary warnings and never yield approve.

## Technical Approach
`domain/checks.py`, `domain/decide.py`, `domain/rules/price.py`. Rules share one signature `(purchase, mandate, snapshot, facts) -> list[Check]`.

### Dependencies
- Needs LEASH-012.
- Needs LEASH-013.
- Blocks LEASH-016.
- Blocks LEASH-017.
- Blocks LEASH-018.
- Blocks LEASH-019.
- Blocks LEASH-021.
- Blocks LEASH-022.
- Blocks LEASH-023.
- Blocks LEASH-024.
- Blocks LEASH-025.
- Blocks LEASH-026.
- Blocks LEASH-027.
- Blocks LEASH-119.
- Blocks LEASH-120.
- Blocks LEASH-121.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_order_at_exact_limit_is_approved`, then `test_one_cent_over_limit_is_declined`, then `test_warning_follows_uncertainty_policy`.

## Related Files
- `solution/engine/src/leash/domain/checks.py`
- `solution/engine/src/leash/domain/decide.py`
- `solution/engine/src/leash/domain/rules/price.py`
- `solution/engine/tests/domain/test_decide.py`

## Out of scope
- Customer message wording (LEASH-027).

## Review log

### 2026-09-23 — independent agent review
- [x] met — criterion 1: CHF 20.00 vs ≤ 20 approves (19.99 and 20.00 probed).
- [x] met — criterion 2: 20.01 declines with `over_order_limit` and a plain sentence; strict `<` has its own sentence.
- [x] met — criterion 3: frozen Check with key/label/status/agreed/actual/detail/reason_code; `integrity` status added for criterion 5 (and LEASH-120).
- [x] met — criterion 4: decline > step_up > approve; warnings follow ask/decline/approve.
- [x] met — criterion 5: integrity never approves (step_up, or decline under decline), in any check order.
- Note: no rule yet turns `unsupported_rules()` into integrity checks — that is LEASH-120; DEC-005 holds end to end only after it lands.
- Out-of-list files justified: `domain/rules/__init__.py`, `tests/factories.py` (CLAUDE.md asks for small factory helpers).
Check: 17 passed; mypy strict clean.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
