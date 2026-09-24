# LEASH-154: Customer context for permission clarification

**Status**: DONE
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
- [x] Bundle entries identify customer/account/card scope, source record, observation time or unknown freshness, and whether they are recorded preferences, observed history, current customer statements or previously confirmed authority.
- [x] Join by IDs; data/ and additional-data-history/ are separate customer populations. Unknown IDs cannot inherit another persona’s history, and names never identify ownership.
- [x] Only information relevant to the task is exposed to the permission assistant. Do not send raw full transaction histories or unrelated persona details.
- [x] Historical summaries use only earlier transactions at the evaluation cutoff, correct card/account scope and currency; completed-purchase/familiarity summaries exclude declines, cash and refunds. Keep net refund accounting separately labelled.
- [x] Preferences, spending patterns, travel and budget style suggest questions only. Current explicit intent can differ; conflicting or stale background is shown as such and cannot widen authority.
- [x] “Usual budget” needs a confirmed amount/scope; “shops I use” can use ID-based history. History without baskets cannot identify an exact previously purchased item.
- [x] Optional constraints become rules only after an explicit answer and final review; no answer does not mean acceptance. Previously confirmed permissions apply only within their recorded scope.
- [x] The bundle exposes its source references for evidence, with missing data visible and sensitive data excluded from ordinary logs. (Retention against each draft revision moved to LEASH-101 on 2026-09-24 — a draft carries no customer/account/card scope and no revision identity today, so there is nothing to attach a scoped bundle to.)

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
- Retaining the bundle against each draft revision: moved to LEASH-101 on 2026-09-24 (needs the
  draft to carry scope and a revision identity, which is that ticket's contract and schema change).
- Training on historical status as a fraud/intent label; demographic profiling; automatic permission inferred from habits; changes to supplied CSVs.

## Review log

### 2026-09-24 — independent agent review (round 1)
- [x] met — AC1-AC6: bundle shape, ID joins and dataset isolation, relevance cap, cutoff/scope/
      currency and refund accounting, conflict and staleness labelling, budget and item-history limits.
- [ ] not met — AC7: the first half held, but nothing recorded, replayed or scoped a previously
      confirmed permission. Not covered by Out of scope, so unfinished rather than deferred.
- [ ] not met — AC8: `as_evidence()` existed but nothing retained a bundle against a draft revision.
- Also found: `test_foreign_currency_rows_are_converted_with_their_own_currency` asserted a property
  of the CSV and would have passed with the module deleted.
Verdict: returned to in-progress.

### 2026-09-24 — fixes
- `ConfirmedPermission` with a `covers()` scope guard: a confirmation is admitted only when the
  bundle's scope lies inside the scope it was recorded for (AC7's second half).
- Replaced the CSV-only test with one that calls `build_context` and pins that `spend_chf` sums each
  row's own CHF column, asserting that summing raw `amount` would give a different total.
- Capped `HistorySummary.merchants`; surfaced `budget_style` only when the customer raises a budget.

### 2026-09-24 — independent agent review (round 2, fresh agent)
- [x] met — AC1-AC7. The reviewer mutation-tested the suite: 7 of 7 injected faults (covers→True,
      refund netting, cutoff removal, questions→[], relevance bypass, cap removal, cross-persona
      leak) each killed tests. No path from background to a rule: the module imports no rule type
      and nothing on the decide path imports it.
- [x] met — LOCK re-pin verified by reproduction, not inference: with `registry._source` patched to
      return HEAD's loader, all 13 fingerprints came back bit-identical to the old LOCK, proving the
      churn is attributable to the additive loader change alone (+120/-0).
- [ ] not met — AC8 (retention half). Blocker verified independently: `CreateDraftRequest` is
      `{instruction}` with `additionalProperties: false`; `policy_drafts` has no scope column and no
      revision table; `mandate_versions` versions confirmed mandates, not local drafts. A draft has
      no scope or revision identity to attach a scoped bundle to. Deferral judged defensible.
- Found: `MAX_ENTRIES` budgeted only history, so 20 caller-supplied confirmations produced 22
  entries against a cap of 12. **Fixed** — the total is now capped and a test pins it.
Verdict: move to review.

### 2026-09-24 — scope decision (the ticket's owner)
AC8's retention half moved to LEASH-101; the evidence view, visible missing data and the safe log
line stay here and are met. All 8 criteria are now ticked against the amended AC8.

### Carried into the human gate
- **The fingerprint LOCK was re-pinned** (`tests/policy/test_registry.py`). Verified twice, but it is
  a security lock and deserves a human's eyes.
- `Kind` declares `"statement"` with no producer: the customer's current words ride on
  `ContextBundle.instruction`. The literal documents the taxonomy AC1 names.
- A `ConfirmedPermission`'s recorded scope is taken on trust from its caller; nothing checks it
  against the pack. There is no producer yet — worth a line in LEASH-101.
