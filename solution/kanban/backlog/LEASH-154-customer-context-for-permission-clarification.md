# LEASH-154: Customer context for permission clarification

**Status**: BACKLOG
**Priority**: P0
**Type**: feature
**Estimated Effort**: L
**Milestone**: M8 — Permission control journey
**Rule source**: Product agreement 2026-09-24
**Decisions**: DEC-033, DEC-034, DEC-035, DEC-036, DEC-037
**Parent**: LEASH-008
**Task ID**: 008-T5
**Blocked by**: LEASH-030, LEASH-042
**Blocks**: LEASH-101
**Updated**: 2026-09-24

## Description
Build a small, relevant context bundle for a permission conversation from the selected customer, account/card, profile preferences and earlier transactions. Example: a recorded 30-day clothing-return preference prompts a question when buying a jacket; it never silently becomes a hard rule.

## Business Value
Clarify missing intent with fewer irrelevant questions while keeping background information separate from customer authorization.

## Acceptance Criteria
- [ ] Bundle entries identify customer/account/card scope, source record, observation time or unknown freshness, and whether they are recorded preferences, observed history, current customer statements or previously confirmed authority.
- [ ] Join by IDs; data/ and additional-data-history/ are separate customer populations. Unknown IDs cannot inherit another persona’s history, and names never identify ownership.
- [ ] Only information relevant to the task is exposed to the permission assistant. Do not send raw full transaction histories or unrelated persona details.
- [ ] Historical summaries use only earlier transactions at the evaluation cutoff, correct card/account scope and currency; completed-purchase/familiarity summaries exclude declines, cash and refunds. Keep net refund accounting separately labelled.
- [ ] Preferences, spending patterns, travel and budget style suggest questions only. Current explicit intent can differ; conflicting or stale background is shown as such and cannot widen authority.
- [ ] “Usual budget” needs a confirmed amount/scope; “shops I use” can use ID-based history. History without baskets cannot identify an exact previously purchased item.
- [ ] Optional constraints become rules only after an explicit answer and final review; no answer does not mean acceptance. Previously confirmed permissions apply only within their recorded scope.
- [ ] The bundle and source references used by each draft revision are retained for evidence, with missing data visible and sensitive data excluded from ordinary logs.

## Technical Approach
Reuse Pack/reference loading, existing history calculations and policy persistence. Compute a bounded context bundle in the policy application layer; no vector database or predictive risk model is required. Profile text is data and cannot issue model instructions.

### Dependencies
- Needs LEASH-030.
- Needs LEASH-042.
- Blocks LEASH-101.

## Testing Requirements
Write tests for the jacket preference question, an explicit exception, absent/stale preferences, cross-customer isolation, separate dataset IDs, future-row exclusion and refund/decline accounting. Run `cd solution/engine && uv run pytest tests/application/test_permission_context.py`.

## Related Files
- `solution/engine/src/leash/application/permission_context.py`
- `solution/engine/tests/application/test_permission_context.py`
- `solution/engine/src/leash/adapters/pack/loader.py`
- `solution/engine/src/leash/adapters/postgres/`
- `solution/contracts/policy-api.yaml`

## Out of scope
- Training on historical status as a fraud/intent label; demographic profiling; automatic permission inferred from habits; changes to supplied CSVs.
