# LEASH-034: Property tests for safety

**Status**: DONE
**Priority**: P0
**Type**: test
**Estimated Effort**: M
**Milestone**: M2 — All five scenarios offline
**Rule source**: Engineering
**Decisions**: DEC-032
**Parent**: LEASH-002
**Task ID**: 002-T5
**Blocked by**: LEASH-027, LEASH-013, LEASH-072, LEASH-120
**Blocks**: LEASH-128
**Updated**: 2026-09-25

## Description
Randomised tests proving the safety properties.

## Business Value
The brief: adding a rule must not weaken a restriction; models may only add caution.

## Acceptance Criteria
- [x] Tightening any mandate never makes any of the 45 verdicts less strict.
- [x] Adding facts flags never makes a verdict less strict.
- [x] Changing merchant text never changes a limit check's status.
- [x] Model output never makes a verdict less strict than the deterministic one.
- [x] Unknown rules never approve.
- [x] Tightening preserves every earlier rule.
- [x] More quantity never makes a verdict less strict.
- [x] Changing merchant text never changes mandate interpretation.

## Technical Approach
`tests/property/test_safety.py` using `random` with fixed seeds (or hypothesis if added).

### Dependencies
- Needs LEASH-027.
- Needs LEASH-013.
- Needs LEASH-072.
- Needs LEASH-120.
- Blocks LEASH-128.

## Testing Requirements
These are the tests.

## Related Files
- `solution/engine/tests/property/test_safety.py`

## Out of scope
- Formal verification.

## Implementation note (2026-09-23)
- The first property run found a real bug: under "nothing extra", flagging line 2 of a two-line basket declined but flagging lines 1 and 2 approved (`basket._requested` fell back to the whole pool). Fixed: when every candidate line is flagged in a multi-line basket, the first line is the purchase and the rest are add-ons; a lone line is still never "added". Regression test in `tests/domain/rules/test_basket.py`; synthetic multi-line basket properties added for flags and quantity.
- Registry fingerprints re-pinned: `basket.py` is an evaluator and `domain/clock.py` (LEASH-051 overflow fix) is shared enforcement. Both changes only tighten.

## Review log

### 2026-09-23 — independent agent review, round 1
- [ ] not met — criterion 1: a real loosening. Adding an `items.item_category in` or `items.item_id in` rule narrowed what the quantity limit and "nothing extra" counted. Example: AU0018 `[max_quantity <= 1]` declined, but `+ item_category = gift_card` approved; 283 of 80k random baskets were affected. The test missed it because it only tightened the five fixture mandates.
- [x] met — criteria 2–7, each confirmed by a mutation that turns its test red.
- [?] weak — criterion 8: comparing `_snapshot()` could never fail. A text-driven change inside an evaluator (mutation M8b) stayed green.
Verdict: returned to in-progress.

### Fixes (2026-09-23)
- `basket.py`:
  - The basket is judged both as asked and without the item/category narrowing, and the stricter result wins.
  - Quantity counts every line.
  - Under "nothing extra", a line outside the purpose is an add-on.
  - Item-category rules with no category in common fail (the random search found this case).
  - Regression tests are in `tests/domain/rules/test_basket.py`.
- Property tests:
  - Tightening now starts from random base mandates on all 45 pack purchases (`test_tightening_any_mandate_never_loosens_any_pack_verdict`) and on synthetic baskets (`test_tightening_never_loosens_any_basket`).
  - Criterion 8 now holds the facts fixed and requires every check except `shop_text` to keep its status when the shop's text changes, with fixture mandates and one extra random rule.

### 2026-09-23 — independent agent review, round 2
- [x] met — criteria 2–8, each confirmed by a mutation that turns its test red (M8b is now caught). The round-1 counterexamples are closed, and the rework is never looser than the old basket.
- [ ] not met — criterion 1: 196 loosening tightenings, all on pack purchase AU0007:
  - an `item_id in` rule covering every line, added to "nothing extra" plus a category rule, turned `unrequested_addon` into `outside_purpose` (a warning);
  - a second `item_category in` rule leaving no line in the purpose skipped "nothing extra".
- The generators only drew single-value ID and category rules, so they missed these.
Verdict: returned to in-progress.

### Fixes (2026-09-23), round 2
- `basket_rule` is now monotone by construction:
  - It judges the basket under the mandate and under every proper subset of its narrowing rules (`items.item_id` and `items.item_category` in/=), and returns the most severe result.
  - Adding any rule only adds subsets, so it can't lower the maximum.
  - With the narrowing fixed, the other basket rules (excluded, nothing extra, quantity) only add failures.
- Explanations still use the full mandate's wording.
- AU0007-style regression tests were added to `test_basket.py`.
- The generators now draw multi-value ID sets (from the basket's own lines and from pack item IDs) and one or two multi-category rules.
- 1117 tests pass, mypy clean, registry re-pinned.

### 2026-09-23 — independent agent review, round 3
- [x] met — criteria 2–8. The basket is now monotone: exhaustive synthetic check with 0 loosenings, all round-1 and round-2 probes green, and every mutation red. Criterion 8's `shop_text` key filter never matches (the keys are `text` and `text_size`); with the facts held fixed that doesn't weaken the test.
- [ ] not met — criterion 1, now in `single_rule`: `max_count` counts only approved purchases matching `mandate.target_item_ids`, so adding an `items.item_id` rule narrows what counts. AU0017 with `[max_count <= 1]` plus `item_id in (IT0063)` goes from step_up to approve; 54 pack cases in all. The random generators rarely reach it.
Verdict: returned to in-progress. **Blocked on DEC-032 (Open):** a monotone fix changes the registered meaning of `leash.purchase.max_count.v1` ("purchases of the requested item"), which needs a new field version and a team decision. Recommendation in DEC-032: a v2 counting every approved purchase in the run.

### Fixes (2026-09-24), round 3 — DEC-032 accepted (option a)
- New field `leash.purchase.max_count.v2`: counts **every approved purchase in the run**, whatever the item, and applies to every purchase. An item rule now narrows only what is allowed, never what is counted.
- `max_count.v1` is retired: it is no longer in `FIELD_SPEC`, so a mandate still carrying it is unsupported and never approves (DEC-005).
- The compiler, fixtures and contract examples (`contracts/policy-api.yaml`) use v2 through `m.F_MAX_PURCHASES`.
- Registry: v1's pin replaced by v2. The other fields' fingerprints moved only because the shared `domain/mandate.py` changed (the field constant); their meaning is unchanged.
- Tests:
  - `tests/domain/rules/test_single.py`: every approved purchase counts even with an item rule; an item rule never lifts the count (AU0017 shape); the field is v2; v1 never approves.
  - `tests/property/test_safety.py::test_an_item_rule_never_lifts_the_purchase_count_on_any_pack_verdict`: exhaustive over all 45 pack purchases, counts 0–2, every item ID, item set and category of the purchase, all three uncertainty policies. It turns red when v1's counting is restored (AU0004).
- 1339 tests pass, mypy clean.
- Local dev data: mandates stored before this change carry v1 and now step_up; reset the dev database (`down -v`) to clear them.

### 2026-09-24 — independent agent review, round 4
- [ ] not met — criterion 1: the max_count fix holds (0 loosenings in ~54k tightenings; v1 never approves), but `period.py` used the platform's spend counter only when the mandate had exactly one period rule. Appending a period rule with another window switched the counter off: SCEN0001 AU0003, AU0005, AU0008, AU0011 went decline → approve with the platform counter at our total + CHF 200. The replay and the `cases` fixture leave `platform_period_spend_chf` empty, so the tests missed it.
- [x] met — criteria 2, 3, 5, 6, 7, 8, each confirmed by a mutation that turns its test red.
- [x] met with a caveat — criterion 4: guaranteed by `decide()` and caught by `tests/domain/test_decide.py::test_verdict_is_never_less_strict_than_the_deterministic_facts`; the property test in `test_safety.py` alone stays green under guard-off mutations.
Verdict: returned to in-progress.

### Fixes (2026-09-24), round 4
- Checked first: the reviewer's repro reproduces all six cases exactly, and the tree was left clean.
- `period.py`: the platform doesn't say which window its counter covers, so the higher total now applies to **every** period rule; adding a rule can no longer drop it. The mismatch alert is raised once.
- Tests (red first): `tests/domain/rules/test_period.py::test_adding_a_second_period_rule_never_drops_the_platform_counter` and `::test_the_mismatch_alert_is_raised_once_with_several_period_rules`.
- Property: `test_tightening_never_loosens_when_the_platform_reports_its_own_spend_counter` sets the platform counter on all 45 pack purchases and always also tries a second period window. With the old single-period code restored it fails on 10 of 12 seeds.
- Merged in the same tree (decided 2026-09-24, pack verdicts under our `ask` fixtures unchanged): DEC-029 (a definite injection never approves) and DEC-030 (repeat, split, off-purpose and already-bought orders always ask) in `decide.combine()`, tests in `tests/domain/test_decide.py`.
- Registry re-pinned (both changes only tighten; see the note in `test_registry.py`). 1370 tests pass, mypy clean.

### 2026-09-24 — independent agent review, round 5
- [ ] not met — criterion 1: the round-4 fixes hold (0 loosenings in 1.2M pack tightenings, platform counter varied), but DEC-030 as first recorded ("step_up whatever the policy") broke monotonicity. `basket._judge` reports `outside_purpose` before `unknown_item_category`; under a `decline` policy, appending `items.item_category in (groceries)` to `[item_category not_in (gift_card)]` turned decline (`unknown_item_category`) into step_up (`outside_purpose`) for a line of category `unknown`. 138 of 300k synthetic baskets; the pack is unaffected. `synthetic_basket` never drew `not_in`/`!=` category rules.
- [x] met — criteria 2, 3, 5, 6, 7, 8 (each mutation turns its test red).
- [x] met with the round-4 caveat — criterion 4.
Verdict: returned to in-progress.

### Fixes (2026-09-24), round 5 — DEC-030 option A
- Reproduced the counterexample first. The product owner chose option A: DEC-030 in `docs/decisions.md` now reads "never approved automatically" (step_up under ask/approve, decline under decline).
- `decide.py`: duplicate, split, outside-purpose, already-bought and injection warnings share one set, `NEVER_APPROVE`, treated like an integrity problem. Each is at least as strict as an ordinary warning, so a rule swapping one warning for another can't loosen the verdict.
- Tests (red first): the combiner table in `tests/domain/test_decide.py` for option A, and the reviewer's counterexample as `test_an_item_category_rule_never_turns_an_unknown_category_decline_into_an_ask`.
- Property: `synthetic_basket` also draws `not_in`/`!=` category rules; with the round-5 combiner restored, `test_tightening_never_loosens_any_basket` turns red.
- Compared with before today, pack verdicts under `ask` and `decline` are unchanged; 11 change under `approve`. The prototype (`prototype/index.html`) was updated to match and agrees with the engine on all 135 (45 × 3 policies).
- Registry re-pinned. 1371 tests pass, mypy clean.

### 2026-09-24 — independent agent review, round 6
- [x] met — criterion 1: no loosening in 600k pack tightenings (platform counter, prior states, model facts and policy varied), 400k synthetic baskets, 1.59M exhaustive small-basket tightenings, and the round-5 repro (now decline → decline). Masking was checked by reading the code and by the exhaustive search: no single-check rule can hide a never-approve warning behind an ordinary one. Mutations restoring each earlier bug (round-5 combiner, single-period counter, v1 counting, no subset loop) turn tests red.
- [x] met — criteria 2, 3, 5, 6, 7, 8 (each mutation turns its test red).
- [x] met with the round-4 caveat — criterion 4: caught by `tests/domain/test_decide.py`, not by the property test alone.
- Caveat (test quality): `synthetic_basket` drew `!=` with a tuple, which is always unsupported. Fixed after the review: `!=` now takes a single category (supported); 159 property tests pass.
Verdict: all met; moved to review.
