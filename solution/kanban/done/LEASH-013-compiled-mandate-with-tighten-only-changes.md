# LEASH-013: Compiled mandate with tighten-only changes

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M1 — SCEN0000 offline vertical slice
**Rule source**: Viseca contract
**Decisions**: DEC-006, DEC-013
**Parent**: LEASH-001
**Task ID**: 001-T4
**Blocked by**: LEASH-010
**Blocks**: LEASH-014, LEASH-028, LEASH-031, LEASH-034, LEASH-060, LEASH-065, LEASH-117, LEASH-128
**Updated**: 2026-09-23

## Description
The engine's interpretation of the customer's confirmed permission, including rules not expressible as one hard_rule (familiar shop, single purchase, session check). Changes can only tighten.

## Business Value
The brief: adding a rule must not weaken an existing restriction; uncertainty can only move to decline.

## Acceptance Criteria
- [x] Holds limits, period, shop types, familiarity threshold, item mode (purpose or specific items), size, minimum return days, add-on ban, single purchase, session and split checks, uncertainty policy, interpretation notes, version.
- [x] `tighten_uncertainty` accepts only a move to `decline`.
- [x] Any loosening raises `LooseningError`.
- [x] The mandate is an append-only list of rules plus the uncertainty policy; effective limits take the strictest rule per field.
- [x] Tightening appends a stricter rule and never replaces an existing one.
- [x] Carries fulfilment, maximum quantity and single-purchase constraints.

## Technical Approach
Frozen dataclass in `domain/mandate.py` holding rules from the registry (LEASH-117 defines field names).

### Dependencies
- Needs LEASH-010.
- Blocks LEASH-014.
- Blocks LEASH-028.
- Blocks LEASH-031.
- Blocks LEASH-034.
- Blocks LEASH-060.
- Blocks LEASH-065.
- Blocks LEASH-117.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_raising_limit_is_rejected`, `test_ask_to_approve_is_rejected`.

## Related Files
- `solution/engine/src/leash/domain/mandate.py`
- `solution/engine/tests/domain/test_mandate.py`

## Out of scope
- Natural-language compilation (LEASH-065).
- Serialising to API hard_rules (LEASH-060).

## Review log

### 2026-09-23 — independent agent review (round 1)
- [x] met — criteria 1–3, 5, 6 as written.
- [ ] effectively not met — criterion 4 ("effective limits take the strictest rule per field"): reviewer found cases where the effective constraint was looser than a stored rule: add-on ban via `<` lost (A); fractional thresholds truncated (B, e.g. `prior >= 0.5` → 0); `=` treated as half a bound (C); some stricter rules refused (D: not_in / !=); exact duplicate unknown rule accepted (E); ambiguous shapes (period_days without scope, numeric size) misread (F).
Verdict: returned to in-progress. Fixes: per-field operator/value table (`FIELD_SPEC`); rules outside it are `unsupported_rules()` (kept, never half-applied; LEASH-120 makes them never approve); integer bounds round in the strict direction; tightening compares all effective constraints including exclusions and rejects exact duplicates. Six new tests (18 total).

### 2026-09-23 — independent agent review (round 2)
- [x] met — criteria 1, 2, 3, 5, 6; round-1 bugs A–F fixed.
- [ ] not met — criterion 4: still looser than stored rules for (N1) add-on limits other than zero (silently ignored), (N2) non-CHF currency on billing rules read as CHF, (N3) scope/period_days on non-billing fields read as lifetime. Also NaN/Infinity values crash instead of being unsupported, and `=` with a list value is read as membership.
Verdict: returned to in-progress.

### 2026-09-23 — independent agent review (round 3)
- [x] met — criteria 1, 2, 5, 6; N1–N3, NaN/Infinity and list-equals fixed; fuzz of 68,096 rules found 0 safety violations.
- [ ] not met — criterion 4: an unknown `scope` string (e.g. "lifetime") on a billing rule was read as a per-order cap; non-integer period_days accepted.
- Also: crashes (not loosenings) for tighten_max_per_order(NaN) and sNaN rules; `supported()` hangs on a Decimal with a huge exponent.
Verdict: returned to in-progress.

### 2026-09-23 — independent agent review (round 4)
- [x] met — criteria 1–6. Fuzz of 141,680 single-rule mandates (all fields, operators, values incl. NaN/±Inf/huge exponents, scopes, periods, currencies): 0 misreads, 0 crashes, no probe over 0.5 s; 20,000 random tightenings never loosened any effective property.
- Non-blocking observations: rules built against their types (list as field) raise TypeError; `prior >= -1` accepted as a no-op tightening; a 1e999999999999 limit is kept as unsupported.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
