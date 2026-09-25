# LEASH-181: Handoff colour tokens behind the existing token names

**Status**: BACKLOG
**Priority**: P1
**Type**: feature
**Estimated Effort**: M
**Milestone**: M8 — Great demo
**Rule source**: Design handoff `designPrototype/README.md` § Design tokens → Colour; `designPrototype/Visual System.dc.html`
**Decisions**: DEC-044 (LEASH-180), DEC-021 (superseded)
**Parent**: LEASH-179
**Task ID**: 179-T2
**Blocked by**: LEASH-180
**Blocks**: LEASH-182, LEASH-183, LEASH-184
**Updated**: 2026-09-25

## Description
Add the handoff's semantic colour tokens to `theme.css` — `allowed #2E7D45` (tint `#E6F2E8`, ink `#1F5C33`), `stopped #C0203A` (tint `#F9E9EB`, ink `#8E1729`), `your-turn #8A1FA8` (tint `#F3E6F7`, ink `#6A1783`), agent tag `#EDEBF8`/`#3D3478`, ink `#14151A`, muted `#7C7C74`, line `#DCDBD5`/`#EFEEEA`, canvas `#F4F4F2`, on-dark accent `#7BC48F` — and re-point the existing phone tokens (`--a-bg`, `--a-ink`, `--a-blue`, `--a-ok*`, `--a-warn*`, `--a-bad*`, `--a-line`, `--a-muted*`) at them. Because every component already reads the `--a-*` names, the whole phone restyles at once with no markup change, which is the lowest-risk first step.

Mapping: `--a-ok*` → allowed, `--a-bad*` → stopped, `--a-warn*` → your-turn (violet = "needs your attention", replacing amber), `--a-blue` → ink (primary actions become ink-filled; accent violet is reserved for focus and "your turn").

## Business Value
The one change that makes the app visibly the handoff design, with zero behavioural risk.

## Acceptance Criteria
- [ ] `theme.css` defines the handoff tokens as new semantic custom properties on `:root`.
- [ ] The existing `--a-*` names resolve to the handoff values; no component file changes.
- [ ] The inspector/page token set (`--page`, `--panel`, `--accent`, … and the dark-mode blocks) is unchanged.
- [ ] Every text/background pair used by the phone meets WCAG AA 4.5:1; where a handoff hue fails as text, a darker `-text` variant is added (as today).
- [ ] The line-1 comment of `theme.css` cites DEC-044 and the handoff instead of DEC-021.
- [ ] Existing tests for all screens (`Agent`, `Cockpit`, `Permission`, `StepUp`, `PaymentDetail`, `status`, `App`, `Inspector`) still pass.

## Technical Approach
CSS custom properties only. `theme.test.ts` today asserts that tokens equal `solution/prototype/index.html`; that assertion is retargeted (not deleted) to a token table transcribed from the handoff README in the test itself (the `.dc.html` is not parsed), and the "only additions are `-text` variants" rule is kept for the new set.

### Dependencies
- Needs LEASH-180.
- Blocks LEASH-182.
- Blocks LEASH-183.
- Blocks LEASH-184.

## Testing Requirements
Red first: change `theme.test.ts` so "match the prototype exactly" becomes "match the v4 handoff tokens exactly" and fails; then update `theme.css`. Extend the contrast pairs with the new semantic ink/tint pairs. Run `cd solution/app && npm test && npm run typecheck`.
At risk: `src/theme.test.ts` (updated deliberately); `src/screens/Cockpit.test.tsx` (`.full` class on the bar) and `src/screens/StepUp.test.tsx` (`.p-amt`) must stay untouched and green.

## Related Files
- `solution/app/src/theme.css`
- `solution/app/src/theme.test.ts`
- `designPrototype/README.md`, `designPrototype/Visual System.dc.html`

## Out of scope
- Typography (LEASH-182), component shapes (LEASH-184), any `.tsx` change.
- Dark mode for the phone (the handoff is light-only; the phone stays light).
- Deleting `solution/prototype/index.html` or its tokens.
