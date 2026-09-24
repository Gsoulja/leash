# LEASH-019: Basket rule: item match, purpose, add-ons, quantity

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M1 — SCEN0000 offline vertical slice
**Rule source**: Viseca brief + Team
**Decisions**: DEC-013, DEC-023
**Parent**: LEASH-001
**Task ID**: 001-T10
**Blocked by**: LEASH-014
**Blocks**: LEASH-121, LEASH-128
**Updated**: 2026-09-23

## Description
Check every basket line: in item mode each line must be a requested item (else add-on or wrong item); in purpose mode lines outside the purpose are uncertain; optional maximum line count.

## Business Value
Covers add-ons (protection plans), wrong items (trail shoes, helmet, voucher) and out-of-purpose items (cosmetics in groceries).

## Acceptance Criteria
- [x] Item mode: an extra add-on next to the requested item fails as 'added X you didn't ask for'.
- [x] Item mode: a different item fails as 'not the item you asked for'.
- [x] Purpose mode: an out-of-purpose line is a warning (step_up under 'ask').
- [x] Add-on detection uses item category (subscriptions, membership, gift_card) and facts, not merchant category.
- [x] Maximum total quantity of requested items is enforced across lines and quantities (one line with quantity 3 fails 'one item').
- [x] Every rule message is part of the check (explanations don't wait for LEASH-027 extensions).

## Technical Approach
`domain/rules/basket.py`.

### Dependencies
- Needs LEASH-014.
- Blocks LEASH-121.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_protection_plan_added_to_monitor_fails`, `test_cosmetics_in_grocery_basket_asks`.

## Related Files
- `solution/engine/src/leash/domain/rules/basket.py`
- `solution/engine/tests/domain/rules/test_basket.py`

## Out of scope
- Semantic item matching with a model (LEASH-082 may add evidence).

## Review log

### 2026-09-23 — independent agent review
- [x] met — item mode: add-on next to the requested item fails as "added X you didn't ask for".
- [x] met — item mode: a different item fails as "not the item you asked for".
- [x] met — purpose mode: out-of-purpose line warns (step_up under ask); category "unknown" also warns.
- [ ] not met — add-on detection also ran on the requested line itself: a requested gift_card item (IT0005) or a requested monitor flagged by `facts.addon_lines` was declined as `item_mismatch`.
- [x] met — quantity enforced across lines and quantities.
- [x] met — every outcome carries its customer sentence in `Check.detail`.
Cosmetic: add-on price showed the unit price, and empty brackets for a currency outside FX_TO_CHF.
Verdict: returned to in-progress. Fix: a requested item ID is never an add-on by category; shop text can mark a line of it as an add-on only while another unmarked requested line remains. Message shows the line total, in its own currency when not convertible. Tests `test_requested_item_is_never_treated_as_an_addon`, `test_addon_message_shows_the_line_total_and_its_own_currency`; 444 pass; mypy clean.

### 2026-09-23 — independent agent review (round 2)
- [x] met — criteria 1, 2, 3, 5, 6 (item-mode fix verified: requested gift_card passes; a lone flagged requested line passes; a second flagged line of the same item is an add-on; price shows the line total, converted or in its own currency).
- [ ] not met — criterion 4 in purpose mode: the wanted category itself (gift_card purpose + nothing extra) and a lone in-purpose line flagged by shop text were declined as `unrequested_addon`; purpose-mode add-on message had no price.
- Outside the criteria: `items.item_id not_in` was accepted but never enforced.
Verdict: returned to in-progress. Fix: one `_requested()` for all modes (matching lines are never add-ons by category; shop text marks one only while another unmarked matching line remains); add-on message with price in every mode; excluded item IDs fail `excluded_item`. 460 tests pass; mypy clean.

### 2026-09-23 — independent agent review (round 3)
- [x] met — criteria 1, 2, 3, 6; item and purpose modes fixed; `item_id not_in` enforced.
- [ ] not met — criterion 4 (mode with neither item IDs nor purpose): a lone gift_card/subscriptions line declined as an add-on.
- [ ] not met — criterion 5 (same mode): add-on-category lines skipped the quantity cap (gift_card ×3 approved under "at most 1").
- Outside the criteria: an `unknown` category passed a `not_in` exclusion; pass message wording.
Verdict: returned to in-progress. Fix: in that mode an add-on-category line is an add-on only next to an ordinary line; quantity counts every line; an unknown category under an exclusion warns `unknown_item_category`; pass message "only allowed items". 480 tests pass; mypy clean.

### 2026-09-23 — independent agent review (round 4)
- [x] met — criteria 1, 2, 5, 6; the mode with neither item IDs nor purpose is fixed (lone lines never "added", quantity counts every line, unknown category warns under an exclusion).
- [ ] not met — criterion 3 (and 4 via the same path): purpose mode + "nothing extra", a lone out-of-purpose line was declined as "added" instead of warning `outside_purpose`; on a lone line the shop text alone turned step_up into decline.
- Remark: with neither mode set, gift_card + subscriptions and no ordinary line is approved (nothing identifies the requested line).
Verdict: returned to in-progress. Fix: "added" needs a line it was added to — in purpose mode the add-on check runs only when an in-purpose line exists (`test_purpose_mode_lone_out_of_purpose_line_warns_even_under_nothing_extra`). 497 pass; mypy clean.

### 2026-09-23 — independent agent review (round 5)
- [x] met — all six criteria. 2,401,504 enumerated cases (item / purpose / neither modes × exclusions × nothing-extra × max quantity × 1–3 lines of every kind × quantities × every addon_lines subset) through basket_rule and decide(ask): 0 violations; verdicts always match check status. Merchant category never changes an outcome.
- Remark (from round 4, not a criterion): with neither mode set plus "nothing extra", gift_card + subscriptions and no ordinary line is approved.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
