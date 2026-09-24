# LEASH-193: Payment detail in the handoff style

**Status**: BACKLOG
**Priority**: P2
**Type**: feature
**Estimated Effort**: S
**Milestone**: M8 — Great demo
**Rule source**: Design handoff `designPrototype/README.md` V5 (merchant, amount 700/28, tags, "Why this went through" with a mono source line); behaviour stays LEASH-095
**Decisions**: DEC-044 (LEASH-180), DEC-037
**Parent**: LEASH-179
**Task ID**: 179-T14
**Blocked by**: LEASH-184
**Blocks**: LEASH-194
**Updated**: 2026-09-25

## Description
Restyle `PaymentDetail.tsx` as V5: merchant row with the store icon, amount at 28/700 tabular, AGENT + outcome tags in the semantic hues, a "Why" section with the plain-language reason and a mono source line (engine verdict → customer answer → platform state), then the existing agreed-vs-paid checks. The shop's text stays quoted and marked untrusted, rendered as text.

## Business Value
Every outcome is explainable after the fact, in the same language as the rest of the app.

## Acceptance Criteria
- [ ] The check list and untrusted-text marking are unchanged in content.
- [ ] No shop text is rendered as HTML (existing `querySelector("script")` / `<b>` tests stay green).
- [ ] Outcome tags follow `status.ts`/`deliveryNote`; approval is not shown as settled or delivered (DEC-037).
- [ ] Dialog focus handling and Close are unchanged.
- [ ] Existing tests for PaymentDetail and Cockpit still pass.

## Technical Approach
Markup/class changes in `screens/PaymentDetail.tsx` plus CSS. The query and focus trap are not modified.

### Dependencies
- Needs LEASH-184.
- Blocks LEASH-194.

## Testing Requirements
Red first in `src/screens/PaymentDetail.test.tsx`: `why section shows the engine verdict and the recorded outcome as text`. Run `cd solution/app && npm test && npm run typecheck`.
At risk: `src/screens/PaymentDetail.test.tsx`, `src/screens/Cockpit.test.tsx` (opens the detail), `e2e/journey.spec.ts` ("Close").

## Related Files
- `solution/app/src/screens/PaymentDetail.tsx`, `solution/app/src/screens/status.ts` (read only)

## Out of scope
- The V6 decision-log timeline (LEASH-148/150).
- Quarantine flag chips (LEASH-170).
