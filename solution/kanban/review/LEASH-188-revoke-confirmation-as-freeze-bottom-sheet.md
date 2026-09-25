# LEASH-188: Revoke confirmation as the freeze bottom sheet

**Status**: REVIEW
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
- [x] "Revoke permission" opens a modal sheet (`role="dialog"`, labelled) with focus trapped and returned to the opener on close.
- [x] Tapping the dim does not dismiss; Escape and "Keep it" cancel.
- [x] "Yes, revoke" calls the same API as today; the result is shown only as the platform reports it.
- [x] Decision buttons are ≥ 48px.
- [x] Existing tests for Permission still pass; e2e names "Revoke permission", "Yes, revoke", "Keep it" still resolve.

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

## Review log

### 2026-09-25 — independent agent review
(The first review run was cut off by a usage limit; this is the re-run.)
- [x] met — criterion 1: `Sheet.tsx` is `role="dialog"`, `aria-modal`, `aria-labelledby` → "Revoke permission?"; focus starts on "Yes, revoke", Tab/Shift+Tab cycle inside (PaymentDetail's pattern), and focus returns to the opener on close. Tests cover the label, the trap and the return after "Keep it" and Escape.
- [x] met — criterion 2: the scrim has no click handler (backdrop test); Escape and "Keep it" cancel (tested).
- [x] met — criterion 3: the revoke body was moved unchanged (`api().revoke`, `platform_confirmed` check, unconfirmed `ApiError(202)`, same success text); DEC-017 kept.
- [x] met — criterion 4: "Yes, revoke" and "Keep it" are `decision` buttons (`min-height:48px`); "Yes, revoke" is 54px in the sheet as V7 asks. Checked from CSS; jsdom can't measure.
- [x] met — criterion 5: all Permission tests pass; "Revoke permission" and "Yes, revoke" each resolve to one button (the dialog's name has role `dialog`, so no clash); e2e read, not run.
DEC-044 ruling 8: the 45% dim covers the tab bar, but the tabs stay visible through it; the reviewer judged a blocking modal consistent with V7's "no tap-outside dismiss".
- [?] unverifiable — the rendered look against V7 (dim, radius-24 top, grab handle, red title and block) needs a human eye.
Verdict: moved to review.
