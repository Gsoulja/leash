# LEASH-188: Revoke confirmation as the freeze bottom sheet

**Status**: BACKLOG
**Priority**: P2
**Type**: feature
**Estimated Effort**: M
**Milestone**: M8 — Great demo
**Rule source**: Design handoff `designPrototype/README.md` V7 (freeze sheet presentation only); behaviour stays DEC-017 and LEASH-096
**Decisions**: DEC-044 (LEASH-180), DEC-017
**Parent**: LEASH-179
**Task ID**: 179-T9
**Blocked by**: LEASH-187
**Blocks**: LEASH-194
**Updated**: 2026-09-25

## Description
Present the existing two-step revoke as the handoff's V7 bottom sheet: 45% dim, radius-24 top with grab handle, no tap-outside dismiss, red title, a scope sentence, a red block listing consequences, a 54px red confirm and an outlined cancel. The API call, its error handling and "shown as revoked only once Viseca confirmed" stay exactly as today.

Copy follows the app's vocabulary (revoke permission), not the handoff's virtual-card numbers (••4417/••2291), which Leash does not model.

## Business Value
Stopping the agent is the customer's most important control; the sheet makes it deliberate and unmistakable.

## Acceptance Criteria
- [ ] "Revoke permission" opens a modal sheet (`role="dialog"`, labelled) with focus trapped and returned to the opener on close.
- [ ] Tapping the dim does not dismiss; Escape and "Keep it" cancel.
- [ ] "Yes, revoke" calls the same API as today; the result is shown only as the platform reports it.
- [ ] Decision buttons are ≥ 48px.
- [ ] Existing tests for Permission still pass; e2e names "Revoke permission", "Yes, revoke", "Keep it" still resolve.

## Technical Approach
A `Sheet` component (reusing the focus-trap pattern already in `StepUp.tsx`/`PaymentDetail.tsx`) wrapping the existing confirm step in `Permission.tsx`. No change to the revoke mutation.

### Dependencies
- Needs LEASH-187.
- Blocks LEASH-194.

## Testing Requirements
Red first in `src/screens/Permission.test.tsx`: `revoke sheet is not dismissed by clicking the backdrop` and `focus returns to Revoke permission after Keep it`. Run `cd solution/app && npm test && npm run typecheck`.
At risk: `src/screens/Permission.test.tsx` (revoke focus-management cases), `e2e/journey.spec.ts`.

## Related Files
- `solution/app/src/screens/Permission.tsx`
- `solution/app/src/screens/StepUp.tsx` (focus-trap reference, read only)

## Out of scope
- The handoff's 4-step freeze ordering, withdrawing proposals, resolving pending asks on freeze (engine/policy-service behaviour; open question DEC-017).
- A freeze button in the chat header.
