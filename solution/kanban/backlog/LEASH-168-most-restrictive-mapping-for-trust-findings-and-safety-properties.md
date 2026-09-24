# LEASH-168: Most-restrictive mapping for trust findings, with safety properties

**Status**: BACKLOG
**Priority**: P1
**Type**: feature
**Estimated Effort**: M
**Milestone**: M7 — Production hardening
**Rule source**: Team (proposal from the 2026-09-24 trust-filter session)
**Decisions**: DEC-038 (to be written in LEASH-161), DEC-009, DEC-025, DEC-029, DEC-030
**Pattern**: Most-restrictive combiner + Notification
**Parent**: LEASH-160
**Task ID**: 160-T8
**Blocked by**: LEASH-164, LEASH-165, LEASH-166, LEASH-167
**Blocks**: LEASH-170
**Updated**: 2026-09-24

## Description
Turn each `TrustFinding` into a `Check` and let the existing combiner decide. Integrity codes (injection anywhere, `off_platform_payment`, and whatever else DEC-038 lists) join `NEVER_APPROVE`: `step_up`, or `decline` under a decline policy. Doubt codes (`external_link_in_shop_text`, `obfuscated_text`, `category_mismatch`, `price_anomaly` if doubt) follow the uncertainty policy. A hard-rule failure still declines first. Every finding is listed in the evidence, not just the first one.

## Business Value
This is where the filter changes verdicts, so it must be provably unable to loosen one.

## Acceptance Criteria
- [ ] Pack injection over the limit stays `decline`; within limits it's `step_up` under `ask` and `approve`, `decline` under `decline`.
- [ ] Injection in `item_name` behaves exactly like injection in `item_details`.
- [ ] A payment link under the `approve` policy is never approved.
- [ ] A doubt finding under `approve` gives an approval with a warning, under `ask` a `step_up`.
- [ ] Property test: adding any trust finding to any purchase never makes the verdict less strict.
- [ ] Property test: the verdict with the trust stage is never less strict than without it (edge case: model unavailable).
- [ ] All 45 scenario-replay verdicts are unchanged or stricter, and each stricter one is listed in the ticket with its reason.

## Technical Approach
`domain/rules/shop_text.py` (or a new `domain/rules/trust.py`) emits the checks; `domain/decide.py` extends `NEVER_APPROVE`. Reason codes are defined once in the trust module, not scattered strings.

### Dependencies
- Needs LEASH-164.
- Needs LEASH-165.
- Needs LEASH-166.
- Needs LEASH-167.
- Blocks LEASH-170.

## Testing Requirements
Write first: `test_injection_in_item_name_is_never_approved`, `test_payment_link_under_approve_policy_is_step_up`, the two Hypothesis properties. Run `uv run pytest -x -q` (all layers, including replay).

## Related Files
- `solution/engine/src/leash/domain/decide.py`
- `solution/engine/src/leash/domain/rules/shop_text.py`
- `solution/engine/tests/domain/test_decide.py`
- `solution/engine/tests/properties/test_trust_monotone.py`

## Out of scope
- Changing hard rules or mandate compilation.
- UI (LEASH-170).
