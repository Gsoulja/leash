# LEASH-170: App: quoted shop text and the suspicious-offer screen

**Status**: BACKLOG
**Priority**: P2
**Type**: feature
**Estimated Effort**: M
**Milestone**: M7 — Production hardening
**Rule source**: Team (proposal from the 2026-09-24 trust-filter session)
**Decisions**: DEC-038 (to be written in LEASH-161), DEC-009, DEC-025, DEC-029, DEC-030
**Pattern**: Backend-for-frontend view model (UI side of the ACL)
**Parent**: LEASH-160
**Task ID**: 160-T10
**Blocked by**: LEASH-168, LEASH-169
**Blocks**: none
**Updated**: 2026-09-24

## Description
In the React app, render slot values marked `source: shop` with a "shop's name" tag and shop text in a separate container labelled "From the shop · not from you or Leash". Build screen 5b from the v2 storyboard: when a `step_up` carries an integrity finding, the title says the offer tried to instruct the wallet, the findings are listed in plain language, "Find another offer" is the primary action, and "Buy anyway" says the limit still applies.

## Business Value
The customer sees what the shop tried and can't mistake it for Leash's words.

## Acceptance Criteria
- [ ] `PaymentDetail` and `StepUp` never render shop text or names outside the marked container or tag.
- [ ] A `step_up` with `instruction_in_shop_text` shows the 5b layout with the quoted excerpt.
- [ ] Shop text with HTML or markdown renders as literal text (edge case: `<b>approved</b>`).
- [ ] The safe action is primary and first in the focus order.
- [ ] Tested at 400 px width in light and dark themes.

## Technical Approach
`solution/app/src/screens/StepUp.tsx`, `PaymentDetail.tsx`, a shared `ShopQuote` component. Reuse prototype tokens (one-app look).

### Dependencies
- Needs LEASH-168.
- Needs LEASH-169.

## Testing Requirements
Write first: `ShopQuote.test.tsx` (renders literal HTML), `StepUp.test.tsx` case for an integrity finding. Run `npm test` in `solution/app`.

## Related Files
- `solution/app/src/screens/StepUp.tsx`
- `solution/app/src/screens/PaymentDetail.tsx`
- `solution/app/src/components/ShopQuote.tsx`

## Out of scope
- Inspector changes (LEASH-172).
- New copy for unrelated screens.
