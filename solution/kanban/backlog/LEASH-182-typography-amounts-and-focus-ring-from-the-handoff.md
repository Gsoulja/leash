# LEASH-182: Typography, amounts and focus ring from the handoff

**Status**: BACKLOG
**Priority**: P1
**Type**: feature
**Estimated Effort**: S
**Milestone**: M8 — Great demo
**Rule source**: Design handoff `designPrototype/README.md` § Design tokens → Type, Buttons (focus); § Accessibility
**Decisions**: DEC-044 (LEASH-180)
**Parent**: LEASH-179
**Task ID**: 179-T3
**Blocked by**: LEASH-181
**Blocks**: LEASH-184, LEASH-185
**Updated**: 2026-09-25

## Description
Switch the phone's type from Figtree / JetBrains Mono to **Inter 400/500/600/700** and **IBM Plex Mono** (identifiers and API sources only). Add the handoff type scale as tokens (28 amount · 22 greeting · 19 screen title · 13–14 body · 12 chips · 11 overline +7% tracking · 9.5–10.5 mono), `font-variant-numeric: tabular-nums` on every amount class, and the focus style: 3px `#8A1FA8` ring at 2px offset inside the phone.

## Business Value
Type is half of the handoff's look; tabular amounts make money columns scannable.

## Acceptance Criteria
- [ ] `--sans` resolves to Inter and `--mono` to IBM Plex Mono, each with a system fallback stack so an offline demo still renders.
- [ ] `index.html` loads Inter and IBM Plex Mono (weights actually used) instead of Figtree / JetBrains Mono.
- [ ] Amount classes (`.v`, `.v2`, `.ramt`, `.p-amt`; not the inspector's `.iamt`) use tabular numerals.
- [ ] Focus-visible inside `.screen` is a 3px `#8A1FA8` ring at 2px offset; the inspector keeps its focus style.
- [ ] Existing tests for all screens still pass.

## Technical Approach
`theme.css` and `index.html` only. Type-scale tokens as custom properties; no component markup change.

### Dependencies
- Needs LEASH-181.
- Blocks LEASH-184.
- Blocks LEASH-185.

## Testing Requirements
Red first: add a `theme.test.ts` case asserting `--sans` starts with `"Inter"` and `--mono` with `"IBM Plex Mono"`. Run `cd solution/app && npm test && npm run typecheck && npm run build`.
At risk: none of the screen tests query fonts; `src/theme.test.ts` gains a case.

## Related Files
- `solution/app/src/theme.css`, `solution/app/src/theme.test.ts`
- `solution/app/index.html`

## Out of scope
- Self-hosting fonts (only if LEASH-151's deterministic delivery requires it — note it there).
- Screen layout changes.
