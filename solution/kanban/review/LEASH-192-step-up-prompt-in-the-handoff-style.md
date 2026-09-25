# LEASH-192: Step-up prompt in the handoff style

**Status**: REVIEW
**Priority**: P1
**Type**: feature
**Estimated Effort**: S
**Milestone**: M8 — Great demo
**Rule source**: Design handoff `designPrototype/README.md` § Design tokens (violet = "your turn", decision buttons, focus), V7 sheet shape; behaviour stays LEASH-094, DEC-008, DEC-012; brief screen 5C
**Decisions**: DEC-044 (LEASH-180), DEC-008, DEC-012, DEC-016
**Parent**: LEASH-179
**Task ID**: 179-T13
**Blocked by**: LEASH-184, LEASH-185
**Blocks**: LEASH-194
**Updated**: 2026-09-25

## Description
Restyle `StepUp.tsx` with the handoff system: violet "your turn" header tint, amount at 28/700 tabular, shop and reason, the passed checks as green chips, the countdown, and decision buttons from LEASH-184 (Confirm payment as the approve variant, Reject as secondary, Decide later as tertiary), all ≥ 48px. Everything behavioural stays: pinned ask, arm delay, countdown from `expires_at`, DEC-012 replacement of Approve by the reason, answer timeout, outcome notices.

## Business Value
The one moment the customer is interrupted must be the clearest screen in the app.

## Acceptance Criteria
- [x] Button names "Confirm payment", "Reject", "Decide later", "OK" are unchanged.
- [x] `.p-amt` still holds the amount (queried by `StepUp.test.tsx`).
- [x] When a hard rule now fails, Approve is still replaced by the reason (DEC-012), styled as the stopped tone.
- [x] Colour never carries meaning alone; decision targets ≥ 48px.
- [x] Existing tests for StepUp and useAsks still pass.

## Technical Approach
Markup/class changes in `screens/StepUp.tsx` plus CSS. `useDialogFocus`, `useNow`, `ARM_MS`, `ANSWER_TIMEOUT_MS` and the answer flow are not modified.

### Dependencies
- Needs LEASH-184.
- Needs LEASH-185.
- Blocks LEASH-194.

## Testing Requirements
Red first in `src/screens/StepUp.test.tsx`: `approve button is at least decision size` via a class assertion on the approve variant. Run `cd solution/app && npm test && npm run typecheck`.
At risk: `src/screens/StepUp.test.tsx` (enabled-button list, `.p-amt`), `src/api/useAsks.test.tsx`, `e2e/journey.spec.ts`.

## Related Files
- `solution/app/src/screens/StepUp.tsx`, `solution/app/src/screens/StepUp.test.tsx`

## Out of scope
- Moving the ask into the chat as a proposal card with "Approve · CHF" (superseded by DEC-033).
- Biometric confirmation.

## Review log

### 2026-09-25 — independent agent review
- [x] met — criterion 1: "Confirm payment", "Reject", "Decide later", "OK" unchanged (and match `journey.spec.ts`).
- [x] met — criterion 2: `.p-amt` still holds the amount; only its CSS changed (28/700).
- [x] met — criterion 3: `{!reason && <Button variant="approve">}` kept; `.p-blocked` now in the stopped tint/ink; tested.
- [ ] not met → fixed → [x] met — criterion 4: the first review found "Decide later" (`.link.later`) at ~35px, while the ticket counts it among the ≥ 48px decision buttons. Fixed: `.link.later` now has `min-height:48px`, with a test asserting it and `.btn-decision`'s 48px. Re-review: met. Colour never carries meaning alone ("YOUR ANSWER NEEDED", "X OK" chips, reason text, labels).
- [x] met — criterion 5: all StepUp and useAsks tests pass. One assertion changed with the ticket's copy: "Price, Known shop: OK" became one chip per passed check ("Price OK", "Known shop OK"); the reviewer judged the same behaviour asserted, more strictly.
Verdict: moved to review.
