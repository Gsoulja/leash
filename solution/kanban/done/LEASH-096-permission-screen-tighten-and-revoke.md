# LEASH-096: Permission screen: tighten and revoke

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M4 — Customer-control journey
**Rule source**: Engineering
**Decisions**: DEC-006, DEC-017
**Parent**: LEASH-007
**Task ID**: 007-T7
**Blocked by**: LEASH-091, LEASH-062
**Blocks**: LEASH-112, LEASH-125, LEASH-128
**Updated**: 2026-09-23

## Description
Current permission with version, tighten controls (lower limit, decline instead of asking) and revoke with in-page confirmation.

## Business Value
The customer can tighten or revoke at any time.

## Acceptance Criteria
- [x] Raising a limit is impossible in the UI.
- [x] Revoke needs a second tap and shows the platform's confirmation.
- [x] Shows original and appended rules; states that changes apply to later runs.
- [x] Shows only platform-confirmed revocation outcomes.

## Technical Approach
`src/screens/Permission.tsx`.

### Dependencies
- Needs LEASH-091.
- Needs LEASH-062.
- Blocks LEASH-112.
- Blocks LEASH-125.
- Blocks LEASH-128.

## Testing Requirements
Write first: `limit input rejects a higher value`.

## Related Files
- `solution/app/src/screens/Permission.tsx`

## Out of scope
- Creating a new permission from here.

## Implementation note (2026-09-23)
- `app/src/screens/Permission.tsx` sits on the "Permission" tab. It shows:
  - the current permission (`/api/mandates`) with its version and instruction;
  - its rules, with the ones added since marked "Added";
  - the uncertainty choice;
  - "Changes apply to runs started after this change; a run already going keeps its rules."
- **Lower limit:**
  - Input "New limit per order (CHF)". The button is enabled only for a positive amount in whole cents that is *below* the current per-order limit (the strictest `<=`/`<` billing rule with scope purchase), so raising or keeping it is impossible in the UI. The backend refuses it too (422, LEASH-062).
  - It sends `add_hard_rules` with the new per-order rule.
- **Decline instead of asking:** sends `uncertainty_policy: decline`; hidden once the policy is decline.
- **Revoke:**
  - "Revoke permission" → in-page confirmation ("Yes, revoke" / "Keep it") → `DELETE /api/mandates/{id}`.
  - The screen reports "Revoked. Viseca confirmed …" only when the response says `revocation.platform_confirmed`. A 502 shows Viseca's "still active" message; an unconfirmed response says it may still be active. A stored revocation without platform confirmation shows "not confirmed by Viseca yet".
- API client: `tighten`, `revoke` (`send` now also does DELETE).
- Tests: `Permission.test.tsx` (8, including the requested `limit input rejects a higher value`); 58 app tests pass, stable 3/3; `tsc` clean.

## Review log

### 2026-09-23 — independent agent review
- [x] met — criterion 1: raising or keeping the limit is impossible across 11 kinds of input, several per-order rules and `<`; a double tap sends one POST.
- [x] met — criterion 2: the first tap sends nothing, "Keep it" cancels, "Yes, revoke" sends one DELETE and shows Viseca's confirmation.
- [x] met — criterion 3: added rules are marked; the later-runs sentence is shown.
- [x] met — criterion 4: a 502 or an unconfirmed response never shows "can no longer pay".
- Minor findings, fixed afterwards:
  - valid amounts in cents (19.99) were refused, and "0x10"/"3.5e2" were accepted. Input is now plain digits with up to two decimals;
  - a EUR per-order rule was shown as the CHF limit; now only CHF rules count;
  - the confirmation appeared twice; it now appears once, in the live region;
  - focus dropped to the page after "Revoke permission" and "Keep it"; it now moves to the counterpart button;
  - input and light-pill borders were 1.26:1; now #8A8F99, 3.3:1;
  - the confirmation copy no longer states DEC-017 (still Proposed) as settled behaviour.
- Tests: 11 Permission tests; 66 app tests pass, `tsc` clean.
Verdict: all met. Moved to done on the product owner's standing instruction for this run.
