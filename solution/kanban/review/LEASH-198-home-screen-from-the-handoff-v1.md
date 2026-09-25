# LEASH-198: Home screen from the handoff's V1 (greeting, card hero, quick actions)

**Status**: REVIEW
**Priority**: P1
**Type**: feature
**Estimated Effort**: M
**Milestone**: M8 — Great demo
**Rule source**: Product owner request after the LEASH-179 build (2026-09-25); design handoff `designPrototype/README.md` § "V1 — Host home" and `Hi-Fi Prototype v4 In-App Chat.dc.html` lines 24–62
**Decisions**: DEC-045 (amends DEC-044 ruling 2), DEC-044, DEC-019, DEC-033
**Parent**: LEASH-179
**Task ID**: 179-T16
**Blocked by**: none
**Blocks**: none
**Updated**: 2026-09-25

## Description
The first tab still reads as the restyled Cockpit. The product owner wants it to look like the handoff's V1 Home: a greeting, a dark card hero and four quick-action tiles above the payments. The first tab becomes **Home**. The run picker, spending card and payment list stay below, so nothing the Cockpit shows today is lost.

- **Greeting:** "Hello" at 700/22, as the screen's heading. No customer name, since there is no login (DEC-019).
- **Card hero:** 300×180, radius 18, dark. It shows only facts Leash has: the agent's permission status (with `LogoMark`), the per-order hard stop, and what is left in the period when a limit exists. No invented card number, balance or expiry, and nothing that imitates an issuer's real card.
- **Quick actions:** four 52px tiles, with "AI agent" the only dark one. Each opens a real destination:
  - **Limits** → the Permission tab.
  - **AI agent** → the Agent tab.
  - **Payments** → scrolls to this screen's payment list.
  - **Revoke** → the Permission tab with the revoke sheet open. Only offered while a permission is active.

Example: an active mandate with `billing_amount_chf <= 400` shows a card reading "ACTIVE" with "Hard stop CHF 400.00 per order". Edge case: no mandate yet shows "No permission yet" with no hard stop, and no Revoke tile.

## Business Value
The first screen the audience sees looks like the designed product, and still shows what happened to the money.

## Acceptance Criteria
- [x] The first tab is named "Home" (tabs: Home · Agent · Permission). Tests and e2e that clicked "Cockpit" are renamed and assert the same facts.
- [x] Home shows the "Hello" greeting as its heading, then the card hero and the four tiles, then the existing run picker, spending card and payment list, unchanged.
- [x] The card hero shows only real data: the permission status in words, the hard stop from `perOrderLimitOf` when one exists, and what is left when spending has a limit. It shows no card number, balance or expiry.
- [x] Every tile is a real button with an accessible name that goes somewhere real. Revoke opens the revoke sheet on the Permission tab and is absent without an active permission.
- [x] Tile targets are ≥ 44px; colour never carries meaning alone.
- [x] No agent banner, and no searching/matches copy (DEC-045, DEC-033).
- [x] Existing tests for all screens still pass; `npm run typecheck`, `npm run build` and `npm run test:e2e` pass.

## Technical Approach
A new `screens/Home.tsx` composes `HomeTop` (greeting, card hero, tiles) with the existing `Cockpit` content. The Cockpit's data flow is not changed. `App.tsx` passes navigation callbacks and does not render its generic `<h1>` on Home, because the greeting is Home's heading. `Permission` gains an optional `startRevoke` prop that opens the existing sheet. It reuses the mandates query key `["mandates"]`, `perOrderLimitOf` and `LogoMark`.

### Dependencies
- Children of LEASH-179; builds on LEASH-185, LEASH-186, LEASH-187 and LEASH-188.

## Testing Requirements
Red first in `src/screens/Home.test.tsx`:
- `home greets and shows the card hero from the active permission`
- `card hero invents no card number or balance`
- `each tile names a real destination`
- `revoke tile opens the revoke sheet and is absent without an active permission`

Then rename "Cockpit" → "Home" in `App.test.tsx`, `TabBar.test.tsx` and `e2e/journey.spec.ts`. Run `cd solution/app && npm test && npm run typecheck && npm run build && npm run test:e2e`.

## Related Files
- `solution/app/src/screens/Home.tsx`, `solution/app/src/screens/Home.test.tsx` (new)
- `solution/app/src/App.tsx`, `solution/app/src/components/TabBar.tsx`, `solution/app/src/screens/Permission.tsx`, `solution/app/src/theme.css`
- `solution/app/src/App.test.tsx`, `solution/app/src/components/TabBar.test.tsx`, `solution/app/e2e/journey.spec.ts`

## Out of scope
- The agent banner (not chosen under DEC-045), Cards/Profile tabs, the avatar, and card lock or card settings (Leash has none).
- Any change to the payments, spending or run-selection logic.

## Review log

### 2026-09-25 — independent agent review
- [x] met — criterion 1: tab label "Home"; `App.test.tsx`, `TabBar.test.tsx` and `journey.spec.ts` assert the same facts under the new name (the e2e tab clicks are `exact: true`, since the "AI agent" tile otherwise matched "Agent" by substring).
- [x] met — criterion 2: App drops its generic `<h1>` on Home; Home renders "Hello", the card hero, the Quick actions nav, then the unmodified `<Cockpit>`. Screenshots confirm the order.
- [x] met — criterion 3: the status overline comes from Permission's `access()` (or "NO PERMISSION YET"), the hard stop from `perOrderLimitOf`, and "Left in N days" only when spending has a period limit; tests cover the active and no-permission cases and a no-invented-data check.
- [x] met — criterion 4: tiles are `<button>`s named by their text; Limits → Permission tab, AI agent → Agent tab, Revoke → Permission with `startRevoke`, only while a permission is active. The reviewer noted two untested paths, both now tested: the Payments tile scrolls the payments wrapper into view (`Home.test.tsx`), and Home's Revoke tile opens the Permission tab with the sheet showing (`App.test.tsx`).
- [x] met — criterion 5: `.tile-btn` min-height 44px with a 52px icon and a visible label; the dark AI agent tile is styling only.
- [x] met — criterion 6: no banner; a test asserts no searching/matches copy.
- [x] met — criterion 7: 222/222 unit tests, typecheck and build clean; `npm run test:e2e` 1 passed (2.4 min).
Verdict: moved to review.
