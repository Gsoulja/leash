# LEASH-120: Unsupported mandate rule outcome

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: S
**Milestone**: M2 — All five scenarios offline
**Rule source**: Team
**Decisions**: DEC-005
**Parent**: LEASH-001
**Task ID**: 001-T21
**Blocked by**: LEASH-014, LEASH-117
**Blocks**: LEASH-033, LEASH-034, LEASH-128
**Updated**: 2026-09-23

## Description
A mandate rule the engine can't evaluate produces an integrity check that bypasses ordinary uncertainty handling.

## Business Value
A confirmed restriction must never be silently unenforced.

## Acceptance Criteria
- [x] Unknown field → verdict is step_up (decline when the policy is decline), never approve, even with uncertainty_policy=approve.
- [x] Reason code `unsupported_mandate_rule`; the detail names the field.
- [x] An operational alert is emitted with mandate ID, field and engine version.

## Technical Approach
Integrity status in `domain/checks.py`, handled first by the combiner.

### Dependencies
- Needs LEASH-014.
- Needs LEASH-117.
- Blocks LEASH-033.
- Blocks LEASH-034.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_unknown_rule_never_approves_under_approve_policy`.

## Related Files
- `solution/engine/src/leash/domain/rules/unsupported.py`
- `solution/engine/tests/domain/rules/test_unsupported.py`

## Notes
- `rules/unsupported.py` emits one integrity check per rule `supported()` rejects (unknown field, operator or value); it runs first in DEFAULT_RULES and is part of the registry's shared core.
- The operational alert is recorded by the decision transaction as an `integrity_alert` event {kind, mandate_id, fields, engine_version} (the mandate ID comes from the live event via DecidePurchase) and streamed as `integrity.alert` kind `unsupported_mandate_rule`.

## Out of scope
- Schema-invalid operators (rejected earlier by LEASH-051).

## Review log

### 2026-09-23 — independent agent review
- [x] met — criterion 1: never approve across unknown fields, unsupported operators, wrong value kinds, EUR/lower-case currency, NaN/Infinity/huge values, bad period shapes, `=` with a list, unrequested > 0, split_check "off" — step_up (decline under decline); a hard fail alongside still declines.
- [x] met — criterion 2: one check per unsupported rule, field in detail and actual.
- [x] met — criterion 3: alert {kind, mandate_id, fields, engine_version} in the transaction, streamed per contract; repeats don't duplicate.
- Noted: customer message showed Python repr and dropped the currency; the watchdog/exception fallback paths recorded no alert; a customer can approve an ask caused only by an unsupported rule, which made the streamed text "never approved" inaccurate.
Fixed after review: plain wording with currency and period; the fallback path logs the operational alert; the stream text says the engine never approves such purchases on its own. The customer-approval question is recorded as DEC-031 (Open) for the product owner. 666 pass; mypy clean.

### 2026-09-23 — independent agent review (final round)
- [x] met — criterion 1: 11 unsupported shapes × 3 policies never approve; a hard fail alongside still declines.
- [x] met — criterion 2: plain wording with currency and period, field named.
- [x] met — criterion 3: transaction alert event {kind, mandate_id, fields, engine_version}, streamed per contract; the fallback path logs the alert (log only). DEC-031 recorded Open.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
