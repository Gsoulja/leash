# LEASH-095: Payment detail: agreed vs paid

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: S
**Milestone**: M4 — Customer-control journey
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-007
**Task ID**: 007-T6
**Blocked by**: LEASH-093
**Blocks**: LEASH-125, LEASH-128
**Updated**: 2026-09-23

## Description
Sheet comparing what the customer agreed with what this payment tried to do, check by check, plus the shop's text marked untrusted.

## Business Value
Shows what evidence the engine considered.

## Acceptance Criteria
- [x] Every check row shows agreed, actual and status.
- [x] Shop text is rendered as text, never as HTML.
- [x] Engine verdict and customer outcome are shown separately.

## Technical Approach
`src/screens/PaymentDetail.tsx`.

### Dependencies
- Needs LEASH-093.
- Blocks LEASH-125.
- Blocks LEASH-128.

## Testing Requirements
Write first: `shop text with <script> is shown literally`.

## Related Files
- `solution/app/src/screens/PaymentDetail.tsx`

## Notes
- Opens from a Cockpit row as a dialog (Escape or Close). Status labels shared with the Cockpit via src/screens/status.ts.
- Contract nit: `PaymentDetail.sent_to_viseca` is typed as an object with no properties, so the generated TS type is `Record<string, never>`; not shown in the sheet yet.

## Out of scope
- Editing rules from the sheet.

## Review log

### 2026-09-23 — independent agent review
- [ ] not met — criterion 1: normal data fine (every status, empty checks), but a long unbroken value (e.g. a 55-character URL in `actual`) pushed the Status column off the sheet (right edge 572 px vs 368 px).
- [x] met — criterion 2: hostile strings in every field (script, onerror/onload, javascript:, style, entities, RTL/zero-width, 3000 chars) rendered literally in headless Chromium; nothing executed; no HTML injection paths in src.
- [x] met — criterion 3: every verdict × outcome × resolver combination shows two separate chips; a null verdict shows only "Not sent".
- Accessibility gaps (not criteria): focus not returned on close; no focus trap; Escape stopped working once focus left the dialog.
Verdict: returned to in-progress. Fix: fixed table layout with a set Status width and `overflow-wrap:anywhere` on check cells; the dialog traps Tab, handles Escape wherever focus is, and returns focus to the opener. Two new tests; 34 app tests pass; typecheck clean.

### 2026-09-23 — independent agent review (round 2)
- [x] met — criterion 1: at 390 px and 320 px, every Status cell stays inside the sheet with long URLs, 3000-char values in label/agreed/actual and 60 mixed rows; the other columns wrap.
- [x] met — criteria 2 and 3 (hostile probes and all combinations re-run).
- Dialog: focus in on open, Tab stays inside, Escape from anywhere, focus returns to the exact row, scrim closes. Gap: the first Shift+Tab after opening escaped (focus starts on the container). Also a 200-char unbroken merchant name scrolled the sheet sideways.
Fixed after review: container focus counts as outside the list so Shift+Tab wraps (`Shift+Tab right after opening stays inside the dialog`); the sheet header wraps long names. 35 app tests pass; typecheck clean.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
