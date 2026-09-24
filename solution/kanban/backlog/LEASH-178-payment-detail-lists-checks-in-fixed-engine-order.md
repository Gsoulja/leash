# LEASH-178: Payment detail lists checks in fixed engine order, so the row that stopped the payment sits below the passed ones

**Status**: BACKLOG
**Priority**: P1
**Type**: bug
**Estimated Effort**: S
**Milestone**: M4 — Customer-control journey
**Rule source**: Found in the customer app's payment detail sheet, run `RUN-09dc02f1e6` (SCEN0004) against the local fake platform (2026-09-24)
**Decisions**: none
**Parent**: LEASH-174
**Task ID**: 174-T4
**Blocked by**: none
**Blocks**: none
**Updated**: 2026-09-25

## Description
Open the Cockpit row **PixelHarbor · 20 Aug at 19:05 · Zurich, CH · CHF 399.90**, a `step_up` that timed out in the 120-second customer window (status chip "No answer", `final_state: timed_out`, `resolved_by: platform`). The sheet's table "What you agreed vs this payment" (columns **Rule · You agreed · This payment · Status**) lists the checks in the engine's fixed rule order:

1. Price · ≤ CHF 400.00 · CHF 399.90 · Passed
2. Known shop · Paid there before · 7 earlier payments · Passed
3. Items · Only the requested item, nothing extra · 27-inch computer monitor · Passed
4. Already bought · Buy it once · 1 approved · **Check**
5. Shop text · Data only, never instructions · No instructions found · Passed

The one row that caused the ask, "Already bought", is fourth. The customer has to scan three "Passed" rows before finding what stopped the payment, and on a longer table (up to 13 checks) the decisive row can be near the bottom or off screen.

**Cause, confirmed in code, not assumed.** `PaymentDetail.tsx:79` renders `p.checks.map(...)` in the order received. `GET /api/payments/{id}` (`adapters/http/query_api.py:120-141`) returns `stored["checks"]` exactly as the engine saved them, which is `DEFAULT_RULES` order from `domain/decide.py`. Nothing sorts by status anywhere between the engine and the screen. The ask screen (`StepUp.tsx`) already leads with the reasons and collapses passed checks, so this only affects the detail sheet.

**Expected.** Rows whose status is not "Passed" appear first, then the passed rows; the relative order inside each group stays the engine's. Reason: the sheet exists to answer "what stopped this payment?", so the answer belongs at the top.

## Business Value
The customer and the judges read the failed or doubtful rule first, without scanning the rows that passed. Same information, less effort, at the moment the customer is trying to understand a stopped or timed-out payment.

## Acceptance Criteria
- [ ] In the detail sheet, checks with status `fail`, `integrity` or `warn` render before checks with status `pass`; within each group the engine's order is preserved (stable sort).
- [ ] `info` rows render after the doubt rows and before the passed rows, so the top of the table never contains a "Passed" row while a non-passed row exists.
- [ ] The sort happens in the app's view layer only. `GET /api/payments/{id}` keeps returning the engine's order, and `evidence`, `sent_to_viseca` and the platform payload are unchanged.
- [ ] For the payment above, the first row is "Already bought · Buy it once · 1 approved · Check", followed by the four passed rows in their existing order.
- [ ] A payment whose checks all passed renders exactly as today.
- [ ] Screen-reader order follows the visual order (no CSS-only reordering).

## Technical Approach
`solution/app/src/screens/PaymentDetail.tsx`: before the `p.checks.map(...)` at line 79, derive `ordered` with a stable sort by a status rank (`fail` 0, `integrity` 1, `warn` 2, `info` 3, `pass` 4) and map over that. Keep `STATUS` labels and the untrusted-text container untouched. No engine, API or contract change.

### Dependencies
- None. Relates to LEASH-095 (built the sheet) and LEASH-170 (will restyle shop-supplied slots in the same sheet); blocks neither.

## Testing Requirements
Write first, in `solution/app/src/screens/PaymentDetail.test.tsx`: `test_renders_doubt_and_failed_checks_before_passed_ones` (fixture with the five checks above in engine order, assert row order), `test_keeps_engine_order_inside_each_status_group`, `test_all_passed_checks_keep_their_order`. Run `cd solution/app && npx vitest run src/screens/PaymentDetail.test.tsx`, then the full app suite.

## Related Files
- `solution/app/src/screens/PaymentDetail.tsx`
- `solution/app/src/screens/PaymentDetail.test.tsx`

## Out of scope
- Changing the engine's check order, reason codes or `customer_message` (`domain/decide.py`, `domain/explain.py`).
- Reordering anything in the step-up prompt, which already leads with the reasons.
- Grouping or wording of the rows (LEASH-146 and LEASH-170 own those).
