# LEASH-193: Payment detail in the handoff style

**Status**: REVIEW
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
- [x] The check list and untrusted-text marking are unchanged in content.
- [x] No shop text is rendered as HTML (existing `querySelector("script")` / `<b>` tests stay green).
- [x] Outcome tags follow `status.ts`/`deliveryNote`; approval is not shown as settled or delivered (DEC-037).
- [x] Dialog focus handling and Close are unchanged.
- [x] Existing tests for PaymentDetail and Cockpit still pass.

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

## Review log

### 2026-09-25 — independent agent review
- [x] met — criterion 1: the checks table and untrusted block markup are untouched; only `.untrusted` colours moved to tokens.
- [x] met — criterion 2: no `dangerouslySetInnerHTML`; new text (item names, source line) is React text; the `script` / `<b>` tests stay green.
- [x] met — criterion 3: the outcome chip is `statusOf(p)[0]` with its tone mapped to a hue; `deliveryNote` unchanged in the Why section; the mono source line prints only recorded fields ("no engine verdict" when there is none); a test checks no chip says paid/settled/delivered/shipped (DEC-037). Fixed while writing: the new tests first ran before the payment loaded (so the DEC-037 check was vacuous); they now wait for the content.
- [x] met — criterion 4: focus trap, query and Close untouched; focus tests pass.
- [x] met — criterion 5: 211/211, typecheck clean; `journey.spec.ts` detail steps ("Engine: declined", "Shop's text · untrusted", "Close") still match (e2e run in LEASH-194).
Verdict: moved to review.

### 2026-09-25 — fix after the LEASH-194 acceptance screenshots
- The 28px amount squeezed the merchant, product and time into ellipses ("PixelHar…"). The amount now has its own line in the header grid and the product line wraps.
