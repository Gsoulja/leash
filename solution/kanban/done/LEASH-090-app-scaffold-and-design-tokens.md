# LEASH-090: App scaffold and design tokens

**Status**: DONE
**Priority**: P0
**Type**: infra
**Estimated Effort**: S
**Milestone**: M4 — Customer-control journey
**Rule source**: Engineering
**Decisions**: DEC-021
**Parent**: LEASH-007
**Task ID**: 007-T1
**Blocked by**: LEASH-118
**Blocks**: LEASH-091, LEASH-127, LEASH-128
**Updated**: 2026-09-23

## Description
Vite + React + TypeScript app porting the prototype's design tokens, phone-frame layout and screens.

## Business Value
Foundation for every screen.

## Acceptance Criteria
- [x] `npm run dev` shows an empty phone frame with tab bar.
- [x] Tokens match the prototype. *Every prototype token is byte-identical; four `--a-*-text` tokens were added because the prototype's muted, green, amber and red colours fail WCAG AA as text on their backgrounds (3.66–4.41:1) and its inactive tab colour is 2.68:1.*
- [x] Vitest set up with one passing test.
- [x] Uses the contract mocks (LEASH-118).
- [x] Baseline accessibility: focus states, labels, contrast.

## Technical Approach
`solution/app/`.

### Dependencies
- Needs LEASH-118.
- Blocks LEASH-091.
- Blocks LEASH-127.
- Blocks LEASH-128.

## Testing Requirements
Write first: a render test for the tab bar.

## Related Files
- `solution/app/package.json`
- `solution/app/src/App.tsx`
- `solution/app/src/theme.css`

## Out of scope
- Native mobile.

## Review log

### 2026-09-23 — independent agent review
- [x] met — dev server serves the page and modules; headless Chromium screenshot shows the phone frame, status bar, "Cockpit" heading, empty state and the three-tab bar.
- [x] met — every prototype `:root` token and both dark blocks identical; four darker `--a-*-text` tokens added (each lifts a failing colour to AA: 3.80→4.64, 3.66→4.66, 3.83→4.68, 4.41→4.64).
- [x] met — Vitest: 3 files, 8 tests pass; typecheck and build clean.
- [x] met — `/api` proxied to the contract mock; all five client paths exist in policy-api.yaml and return 200 through the proxy.
- [x] met — focus-visible outlines, labelled nav/region, aria-current, hidden icons, native buttons; every text colour used passes AA.
Notes: ticket-note wording corrected after review (red added; exact ratio range). Dark mode not screenshot.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
