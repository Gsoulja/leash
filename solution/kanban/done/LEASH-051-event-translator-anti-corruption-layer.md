# LEASH-051: Event translator (anti-corruption layer)

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M1 — SCEN0000 offline vertical slice
**Rule source**: Viseca contract
**Decisions**: DEC-003, DEC-004
**Parent**: LEASH-004
**Task ID**: 004-T2
**Blocked by**: LEASH-012, LEASH-117, LEASH-060
**Blocks**: LEASH-053, LEASH-121, LEASH-128
**Updated**: 2026-09-23

## Description
Validate the envelope's `data` against the event schema and translate it into a Purchase and a mandate snapshot reference.

## Business Value
Keeps the API's format out of the domain.

## Acceptance Criteria
- [x] The example event in data/scenario_fixtures validates and translates.
- [x] Nulls stay None; tri-states map to typed values; amounts become Decimal.
- [x] Invalid events are rejected with a clear error.
- [x] Live and source IDs are kept separate.
- [x] The event's mandate is compiled from its hard_rules through the registry and is authoritative for the run.
- [x] billing_amount_chf is checked against amount × rate; a mismatch is an integrity alert.
- [x] An event that fails validation but has a readable authorization ID gets a safe step_up with reason `invalid_event`.

## Technical Approach
`adapters/viseca_api/translate.py` with jsonschema against data/schemas/authorization_event.schema.json.

### Dependencies
- Needs LEASH-012.
- Needs LEASH-117.
- Needs LEASH-060.
- Blocks LEASH-053.
- Blocks LEASH-121.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_example_event_translates`, `test_null_delivery_by_stays_none`.

## Related Files
- `solution/engine/src/leash/adapters/viseca_api/translate.py`
- `solution/engine/tests/adapters/test_translate.py`

## Notes
- `translate.py` is pure (in the registry's shared core, so it reads no files); the official-schema check is injected from `event_schema.py` (jsonschema, now a runtime dependency). The translator still refuses any value it can't type, even without the schema check.
- Integrity alerts are returned on the translated event (`integrity`); raising them in the decision flow is the worker's job (LEASH-053).

## Out of scope
- Mandate hard_rules interpretation (LEASH-060).

## Review log

### 2026-09-23 — independent agent review
- [x] met — criteria 1, 2, 4, 5, 6, 7 (all 45 pack events translate back to the pack purchases; malformed rules rejected; billing check exact at the cent).
- [ ] not met — criterion 3: schema-valid numbers the Decimal context can't handle (1e30, NaN, Infinity) escaped as decimal.InvalidOperation instead of InvalidEvent, so a caller would never reach the safe step_up. Also: sub-cent amounts were silently rounded; non-RFC 3339 timestamps accepted (the format checker doesn't enforce date-time); the invalid_event evidence carried unescaped event text; a doubled error prefix.
Verdict: returned to in-progress. Fix: every amount must be finite, below 1e12 and whole cents, else InvalidEvent (never rounded silently); RFC 3339 timestamps and YYYY-MM-DD dates enforced in the translator; the evidence error text is HTML-escaped; the prefix fixed. 11 new tests; 780 pass; mypy clean.

### 2026-09-23 — independent agent review, round 2
- [x] met — criteria 1, 2, 4, 5, 6, 7 (round-1 gaps fixed: non-finite, sub-cent and huge amounts; non-RFC 3339 timestamps and dates; doubled error prefix).
- [ ] not met — criterion 3: `OverflowError` escaped `translate()` for timestamps the schema accepts, e.g. `9999-12-31T23:59:59-23:59`.
- Note: `context.approved_spend_in_period_chf` sent as an unrounded float sum by the live platform would be rejected as `invalid_event` (a safe step_up). The data dictionary says totals are rounded half-even to cents; only the live platform can confirm.
Verdict: returned to in-progress. Fix: `clock._parse_utc` turns the overflow into `ValueError`; tests in `tests/domain/test_clock.py` and `tests/adapters/test_translate.py` (three fields, with and without the validator).

### 2026-09-23 — independent agent review, round 3
- [x] met — criteria 1–7. About 200,000 fuzzed `translate()` calls with and without the validator: no exception other than `InvalidEvent` for any input JSON can carry. 943 tests pass, mypy strict clean.
Verdict: all met. Moved to done on the product owner's standing instruction for this run.
