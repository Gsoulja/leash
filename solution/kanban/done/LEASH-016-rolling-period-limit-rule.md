# LEASH-016: Rolling period limit rule

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M2 — All five scenarios offline
**Rule source**: Viseca brief + Team
**Decisions**: DEC-010
**Parent**: LEASH-001
**Task ID**: 001-T7
**Blocked by**: LEASH-014, LEASH-015
**Blocks**: LEASH-033, LEASH-128
**Updated**: 2026-09-23

## Description
Sum final approvals on the card in the trailing N × 24 h of simulated time and check the new purchase fits.

## Business Value
Household-budget scenario: 'total across any seven days at or below CHF 300'.

## Acceptance Criteria
- [x] Only approved purchases count; waiting ones don't.
- [x] Reaching exactly the limit passes; one cent over fails.
- [x] A purchase exactly 7 × 24 h older is outside the window.
- [x] The check shows paid-so-far + this purchase = total.
- [x] Period spend = final agent approvals in this run by simulated time.
- [x] Compares with the platform counter; on mismatch uses the higher value and emits an integrity alert.

## Technical Approach
`domain/rules/period.py`, using SimTime.within.

### Dependencies
- Needs LEASH-014.
- Needs LEASH-015.
- Blocks LEASH-033.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_total_reaching_exactly_300_is_approved`, `test_waiting_order_not_counted`.

## Related Files
- `solution/engine/src/leash/domain/rules/period.py`
- `solution/engine/tests/domain/rules/test_period.py`

## Out of scope
- Calendar-month limits.

## Review log

### 2026-09-23 — independent agent review
- [x] met — only approved purchases count (waiting/declined/timed_out give CHF 0.00 paid; test + probe).
- [x] met — exactly at the limit passes, one cent over fails; strict `<` at the limit fails; the stricter of two 7-day rules wins.
- [x] met — exactly 7 × 24 h older is outside; 1 s inside is counted.
- [x] met — actual reads "CHF 234.50 paid + CHF 65.50 = CHF 300.00".
- [x] met — spend = this run's final approvals by simulated time; history never adds to spend.
- [x] met — higher counter used both ways; `spend_counter_mismatch` info check surfaced in `Decision.alerts` (operational alert per DEC-010, does not force step_up).
Notes: with more than one period rule the platform counter isn't compared (its window is ambiguous); `platform_period_spend_chf` is filled by later adapter tickets.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.

### 2026-09-23 — reopened
Found while reviewing LEASH-044: the rule only checks the 7-day window *ending at* the new purchase. When purchases are decided out of simulated-time order (pack scenarios SCEN0002/0004 have non-monotonic times; concurrent decisions too), an earlier-dated purchase can push a later window over the limit unnoticed. "Any seven days" means every window that contains the purchase must stay within the limit.
Fix: the rule now takes the worst window that contains the purchase — the one ending at it (with the platform counter) and every window ending at a later-dated approval less than N days after it; the check shows that worst window. Tests `test_every_window_containing_the_purchase_counts_not_only_the_one_ending_at_it`, `test_a_later_approval_outside_the_window_does_not_count`, `test_the_worst_window_is_reported`. Registry lock re-pinned (period.py is an evaluator of `authorization.billing_amount_chf`). 563 pass; mypy clean.

### 2026-09-23 — independent agent review (after reopening)
- [x] met — all original criteria and the worst-window behaviour: 40,000 fuzz cases (0–8 priors in every final state, at random offsets and exactly ±N days ±1 s; 1/3/7/30-day rules, inclusive and strict, up to three period rules) against an independent oracle: 0 failures in verdict, "paid + this = total" text and the counter alert; 17,091 cases where a later window was the worst.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
