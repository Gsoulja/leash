# LEASH-060: Mandate to API hard_rules serializer

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M1 — SCEN0000 offline vertical slice
**Rule source**: Viseca contract
**Decisions**: DEC-004, DEC-006
**Parent**: LEASH-005
**Task ID**: 005-T1
**Blocked by**: LEASH-013, LEASH-117
**Blocks**: LEASH-051, LEASH-061, LEASH-121, LEASH-128
**Updated**: 2026-09-23

## Description
Parse and serialise mandates to and from the API's hard_rules, uncertainty_policy, guidance and open_questions through the field registry. Every enforceable rule is a hard_rule; guidance is explanation only.

## Business Value
POST /v1/mandates needs it; the rules shown to the customer must match what is stored.

## Acceptance Criteria
- [x] Output validates against the rule format (field, operator, value, currency, scope, period_days).
- [x] Round trip: serialising and parsing returns an equal mandate.
- [x] Existing rules are preserved when serialising a tightened mandate (append-only).

## Technical Approach
`policy/hard_rules.py`.

### Dependencies
- Needs LEASH-013.
- Needs LEASH-117.
- Blocks LEASH-051.
- Blocks LEASH-061.
- Blocks LEASH-121.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_price_rule_serialises_like_the_docs_example`.

## Related Files
- `solution/engine/src/leash/policy/hard_rules.py`
- `solution/engine/tests/policy/test_hard_rules.py`

## Notes
- The rule format is checked by hand (no runtime file read, no runtime jsonschema); a test keeps it in agreement with the official `mandate_rule` schema. Unknown fields are kept so they are enforced as unsupported (DEC-005). Guidance ↔ the mandate's notes; open questions travel alongside. Part of the registry's shared core.

## Out of scope
- Natural-language compilation (LEASH-065).

## Review log

### 2026-09-23 — independent agent review
- [ ] not met — criterion 1: 23,040 fuzzed serialisations validated except: an out-of-enum currency ("chf", "JPY", "") was emitted schema-invalid; ±Infinity crashed with OverflowError. (NaN / values a float can't hold exactly are refused — deliberate.)
- [x] met with caveats — criterion 2: every serialisable rule round-trips exactly through JSON; all fixtures round-trip. Caveats: mandate `version` isn't in the API body; `1e400` → Infinity; empty instruction serialised but not parsed. Hand check vs jsonschema: 196,357 bodies, 240 disagreements (integer-valued float `period_days` refused); unhashable operator/currency/scope raised TypeError.
- [x] met — criterion 3: 68 real tightenings accepted, 348 remove/replace/reorder/insert mutations refused. Edge cases: `True` for `1` accepted; explicit nulls refused.
Verdict: returned to in-progress. Fix: rule_to_api validates its own output (unknown currency, non-finite values → HardRulesError); empty instructions refused on both sides; `period_days: 7.0` accepted as the schema does; non-string operator/currency/scope → HardRulesError; non-finite parsed numbers refused; append-only compares canonical JSON (nulls ignored, True ≠ 1). The version caveat is documented (the service tracks versions, LEASH-061). Three new tests; 666 pass; mypy clean.

### 2026-09-23 — independent agent review (final round)
- [x] met — criterion 1: 23,040 valid outputs, 0 invalid, 0 crashes; 16,920 refusals all HardRulesError.
- [x] met — criterion 2: every serialisable rule round-trips; hand check matches jsonschema on 196,357 bodies (0 mismatches). Documented caveat: the API body has no version, so a tightened mandate parses back as version 1 (LEASH-061 tracks versions).
- [x] met — criterion 3: 68 tightenings accepted, 348 mutations refused; True-for-1 refused, explicit nulls accepted.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
