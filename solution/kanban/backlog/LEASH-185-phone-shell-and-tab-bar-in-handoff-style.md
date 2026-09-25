# LEASH-185: Phone shell and tab bar in the handoff style

**Status**: BACKLOG
**Priority**: P1
**Type**: feature
**Estimated Effort**: S
**Milestone**: M8 — Great demo
**Rule source**: Design handoff `designPrototype/README.md` § Screens (phone frame 390×800, canvas `#F4F4F2`, 18px gutters, status bar, tab bar, non-shrinking scroll children)
**Decisions**: DEC-044 (LEASH-180, question 8: tabs stay visible)
**Parent**: LEASH-179
**Task ID**: 179-T6
**Blocked by**: LEASH-182, LEASH-183
**Blocks**: LEASH-186, LEASH-187, LEASH-190, LEASH-192
**Updated**: 2026-09-25

## Description
Restyle `PhoneFrame` and `TabBar`: canvas background, 18px gutters, status-bar colour, screen-title type (19/700 instead of 28/800), and the handoff tab-bar look with the new icons. Make scroll containers keep their children at natural height (the handoff's `grid-auto-rows:max-content` note). Keep the app's three tabs, their labels and their order; the handoff's Home/Cards/AI agent/Profile bar is generic host chrome.

## Business Value
The frame every screen sits in; after this ticket the whole app reads as the handoff design even before the screens are touched.

## Acceptance Criteria
- [ ] The phone uses the canvas token, 18px gutters and the handoff status bar.
- [ ] Tab labels remain "Cockpit", "Agent", "Permission" with `aria-current="page"` on the active one.
- [ ] Long content scrolls without squashing cards (checked at 390×800).
- [ ] The inspector layout beside the phone on wide screens is unchanged.
- [ ] Existing tests for `App` and every screen still pass; e2e selectors `getByRole("button", { name: "Agent" | "Cockpit" | "Permission" })` still resolve.

## Technical Approach
`components/PhoneFrame.tsx`, `components/TabBar.tsx`, shell rules in `theme.css`. No state or routing change in `App.tsx`.

### Dependencies
- Needs LEASH-182.
- Needs LEASH-183.
- Blocks LEASH-186.
- Blocks LEASH-187.
- Blocks LEASH-190.
- Blocks LEASH-192.

## Testing Requirements
Red first: `src/components/TabBar.test.tsx` — three tabs in order with their names, the current one marked. Run `cd solution/app && npm test && npm run typecheck`.
At risk: `src/App.test.tsx`, `e2e/journey.spec.ts` (tab navigation by name).

## Related Files
- `solution/app/src/components/PhoneFrame.tsx`, `solution/app/src/components/TabBar.tsx`
- `solution/app/src/App.tsx` (read only)
- `solution/app/src/theme.css`

## Out of scope
- Renaming or adding tabs; hiding the tab bar in chat.
- Narrow-screen and projector modes (LEASH-152).
