# LEASH-183: Handoff icon set and the bracket-dot logo mark

**Status**: REVIEW
**Priority**: P2
**Type**: feature
**Estimated Effort**: S
**Milestone**: M8 — Great demo
**Rule source**: Design handoff `designPrototype/README.md` § Icons, § Logo; `designPrototype/Visual System.dc.html` (icon SVG paths, logo construction)
**Decisions**: DEC-044 (LEASH-180)
**Parent**: LEASH-179
**Task ID**: 179-T4
**Blocked by**: LEASH-181
**Blocks**: LEASH-185, LEASH-191
**Updated**: 2026-09-25

## Description
Replace the three prototype paths in `components/icons.tsx` with the handoff's 24px / 2px-stroke / square-cap icon set, lifting the SVG path data from `Visual System.dc.html` (and the `icon()` method of the v4 logic class) rather than redrawing it. Add a `LogoMark` component: the bracket around a dot, where the dot is a status light — grey (no permission), green `#7BC48F` (active), red (revoked/frozen).

## Business Value
The status-light logo is how the chat header and agent-access card show at a glance whether the agent may spend.

## Acceptance Criteria
- [x] `IconName` covers the icons the later tickets use (at least home, chat, shield, fingerprint, flag, chevron, back, send, store, check, close) with handoff path data.
- [x] The existing `home`, `chat`, `shield` names keep working, so `TabBar` needs no change.
- [x] `LogoMark` takes a `status: "none" | "active" | "revoked"` and exposes it as an accessible label (colour never carries meaning alone).
- [x] Icons are decorative (`aria-hidden`) unless given a label.
- [x] Existing tests for `App` and `TabBar` usage (`src/App.test.tsx`) still pass.

## Technical Approach
`solution/app/src/components/icons.tsx` plus a new `LogoMark.tsx`. Static path data, no runtime fetching; no `image-slot.js`.

### Dependencies
- Needs LEASH-181.
- Blocks LEASH-185.
- Blocks LEASH-191.

## Testing Requirements
Red first: `src/components/LogoMark.test.tsx` — renders an accessible name per status ("Agent permission: active" etc.) and never relies on colour alone. Run `cd solution/app && npm test && npm run typecheck`.
At risk: `src/App.test.tsx` (tab buttons render icons).

## Related Files
- `solution/app/src/components/icons.tsx`
- `designPrototype/Visual System.dc.html`, `designPrototype/Sticker Sheet.dc.html`

## Out of scope
- Using the logo in screens (LEASH-185, LEASH-187, LEASH-191).
- Any branding that imitates the card issuer's real logo.

## Review log

### 2026-09-25 — independent agent review
- [?] needs a human decision — criterion 1: 8 of the 11 named icons are lifted verbatim (home, chat, shield, flag, send, check; `store` = handoff `merchant`; `fingerprint` = Visual System `biometric`). The extra icons match the handoff too. **The handoff has no SVG for `back` or `chevron`** (it uses the text glyphs ‹ ⌃ ⌄), so those two are new strokes on the handoff grid (24px, 2px, square caps). `close` is the decline icon's cross, lifted exactly; the reviewer flagged that an earlier scaled version didn't match the comment, and it was fixed. The owner should accept the two new drawings or reword the criterion.
- [x] met — criterion 2: `TabBar.tsx` unchanged; `home`, `chat`, `shield` still resolve.
- [x] met — criterion 3: `LogoMark` is `role="img"` with `aria-label="Agent permission: <status>"`; tests check all three names differ. Construction matches Visual System (radius 14, two 14×24 cut-outs, 14px dot); active is `#2E7D45` on light and `#7BC48F` with `onDark`.
- [x] met — criterion 4: `aria-hidden="true"` by default, `role="img"` + `aria-label` with `label`; tested.
- [x] met — criterion 5: `npm test` 14 files / 132 tests; typecheck clean.
Search and cart icons were left out under DEC-033 (not on the criterion's list).
Verdict: moved to review, with criterion 1 left for the human gate.
