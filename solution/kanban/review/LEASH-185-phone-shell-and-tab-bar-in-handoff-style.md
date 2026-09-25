# LEASH-185: Phone shell and tab bar in the handoff style

**Status**: REVIEW
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
- [x] The phone uses the canvas token, 18px gutters and the handoff status bar.
- [x] Tab labels remain "Cockpit", "Agent", "Permission" with `aria-current="page"` on the active one.
- [x] Long content scrolls without squashing cards (checked at 390×800).
- [x] The inspector layout beside the phone on wide screens is unchanged.
- [x] Existing tests for `App` and every screen still pass; e2e selectors `getByRole("button", { name: "Agent" | "Cockpit" | "Permission" })` still resolve.

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

## Review log

### 2026-09-25 — independent agent review
- [x] met — criterion 1: `.screen` on `--a-bg` → `--hf-canvas`; `.view` padding `4px 18px 20px` as in the handoff; `.sbar` matches handoff line 23 (42px, 0 22px, 600/12, "9:41" + "●●● ⌁"); the island is gone.
- [x] met — criterion 2: `TabBar.tsx` unchanged; new `TabBar.test.tsx` pins the order, names, single `aria-current="page"` and selection by name.
- [x] met — criterion 3: `.view` is a grid with `grid-auto-rows:max-content` (the handoff's pattern). A headless Chromium check at 390×800 loaded the real `theme.css` with 12 cards: each kept its natural 109.8px height while the view scrolled, 18px gutter, no horizontal overflow. It used stand-in cards, not live Cockpit data. The old flex layout didn't squash these cards either, so this guards against the handoff's failure mode rather than fixing an observed one.
- [x] met — criterion 4: `.shell`, the 900px media block and `.phone` are untouched.
- [x] met — criterion 5: 158/158 tests, typecheck clean; tab names still match `journey.spec.ts` (e2e not run here; LEASH-194 runs it).
Inactive tab labels keep the accessible muted text instead of the handoff's `#A9A8A1`, which fails contrast.
Verdict: moved to review.

### 2026-09-25 — fix after the LEASH-194 acceptance screenshots
- The single-column grid on `.view` had an implicit `auto` column, which grew to the widest child's min-content. On the Agent screen under mobile Chromium, the composer's input pushed every child 32px past the phone's edge and clipped the send button. Fixed with `grid-template-columns:minmax(0,1fr)`, verified in the real app (nothing inside `.view` overflows), with a regression assertion in `theme.test.ts`.
