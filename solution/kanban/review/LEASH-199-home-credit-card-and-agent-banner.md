# LEASH-199: Home shows the credit card and the "Try your new AI shopping agent" banner

**Status**: REVIEW
**Priority**: P1
**Type**: feature
**Estimated Effort**: S
**Milestone**: M8 — Great demo
**Rule source**: Product owner request after LEASH-198 (2026-09-25); handoff `designPrototype/Hi-Fi Prototype v4 In-App Chat.dc.html` lines 27–33 (card) and 44–49 (banner), README § "V1 — Host home" banner table ("never started")
**Decisions**: DEC-046 (amends DEC-045), DEC-033
**Parent**: LEASH-179
**Task ID**: 179-T17
**Blocked by**: none
**Blocks**: none
**Updated**: 2026-09-25

## Description
Two changes to Home (LEASH-198), both from DEC-046:

- **Credit card:** the dark card becomes the handoff's credit card: "Credit card" with a chip, a masked number, "Available" with an amount, and an expiry, on the handoff's card colour. The values are static demo values held in one constant. No API supplies them, and they feed no decision.
- **Agent banner:** the spending card ("Agent spent" and its counts) no longer appears on Home. In its place, while no permission is active, is the handoff's banner "Try your new AI shopping agent · Set rules together in a chat". Tapping it opens the chat. Once a permission is active the banner is hidden.

Example: first visit with no permission shows the card, the tiles and the banner; tapping the banner opens the Agent tab. Edge case: with an active permission, Home shows the card, the tiles, the run picker and the payments, with no banner and no spending card.

## Business Value
Home matches the handoff's V1 look the product owner asked for, and the first thing a new customer is invited to do is set up the agent.

## Acceptance Criteria
- [x] The card shows "Credit card", a masked number, "Available" with an amount and an expiry, from one demo constant; nothing else reads that constant.
- [x] The banner reads "Try your new AI shopping agent" / "Set rules together in a chat", is a real button, and opens the Agent tab.
- [x] The banner shows only while no permission is active, and is hidden once one is.
- [x] Home no longer shows the spending card. The Cockpit component still shows it wherever else it is used (its own tests unchanged).
- [x] No copy claims Leash itself searches or shops (DEC-033).
- [x] Existing tests for all screens still pass; `npm run typecheck`, `npm run build` and `npm run test:e2e` pass.

## Technical Approach
In `screens/Home.tsx`: `CardHero` renders the demo constant, and a new `AgentBanner` appears when the mandates query shows no active permission. `Cockpit` gains a `showSpending` prop (default `true`); Home passes `false`. CSS goes in `theme.css`, with the handoff's card colour as a named value.

## Testing Requirements
Red first in `src/screens/Home.test.tsx`:
- `home shows the credit card from the demo constant`
- `the agent banner opens the chat`
- `the banner is hidden once a permission is active`
- `home shows no spending card`

Run `cd solution/app && npm test && npm run typecheck && npm run build && npm run test:e2e`.

## Related Files
- `solution/app/src/screens/Home.tsx`, `solution/app/src/screens/Home.test.tsx`, `solution/app/src/screens/Cockpit.tsx`, `solution/app/src/theme.css`

## Out of scope
- The banner's other handoff states (setup, searching, proposals, frozen). The searching and proposals states are superseded by DEC-033.
- Real card data from the pack (not chosen under DEC-046).

## Review log

### 2026-09-25 — independent agent review
- [x] met — criterion 1: `DEMO_CARD` (`Home.tsx`) holds `last4`, `available` and `expiry`, and only the card markup and its test read it. The card shows "Credit card", a chip, "•••• •••• •••• 2291", "Available CHF 4'312.60" and "09/29" on the handoff's #1E2A38.
- [x] met — criterion 2: the banner is a `<button>` with both lines and calls `onNavigate("agent")` (tested).
- [x] met — criterion 3: shown only when `mandates.isSuccess && !active`, so it can't flash before the answer; hidden with an active permission (tested, and in the screenshot).
- [x] met — criterion 4: `showSpending` defaults to `true`; Home, the only production user of `Cockpit`, passes `false`. Cockpit's own tests are unchanged and pass.
- [x] met — criterion 5: the banner names the shopping agent and setting rules in chat; a test asserts no searching/matches copy.
- [x] met — criterion 6: 224/224 unit tests, typecheck and build clean; e2e 1 passed (2.5 min).
The reviewer judged replacing LEASH-198's permission-card and "no invented card data" tests consistent with DEC-046, which reverses them. The no-Revoke-tile check is kept.
Verdict: moved to review.

