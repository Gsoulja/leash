# LEASH-192: Step-up prompt in the handoff style

**Status**: BACKLOG
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
- [ ] Button names "Confirm payment", "Reject", "Decide later", "OK" are unchanged.
- [ ] `.p-amt` still holds the amount (queried by `StepUp.test.tsx`).
- [ ] When a hard rule now fails, Approve is still replaced by the reason (DEC-012), styled as the stopped tone.
- [ ] Colour never carries meaning alone; decision targets ≥ 48px.
- [ ] Existing tests for StepUp and useAsks still pass.

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
