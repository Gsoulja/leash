# LEASH-182: Typography, amounts and focus ring from the handoff

**Status**: REVIEW
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
- [x] `--sans` resolves to Inter and `--mono` to IBM Plex Mono, each with a system fallback stack so an offline demo still renders.
- [x] `index.html` loads Inter and IBM Plex Mono (weights actually used) instead of Figtree / JetBrains Mono.
- [x] Amount classes (`.v`, `.v2`, `.ramt`, `.p-amt`; not the inspector's `.iamt`) use tabular numerals.
- [x] Focus-visible inside `.screen` is a 3px `#8A1FA8` ring at 2px offset; the inspector keeps its focus style.
- [x] Existing tests for all screens still pass.

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

## Review log

### 2026-09-25 — independent agent review
- [x] met — criterion 1: `--sans` is `"Inter",…,sans-serif` and `--mono` is `"IBM Plex Mono",…,monospace`, both with system fallbacks; tests assert both.
- [x] met — criterion 2: `index.html` loads Inter 400–800 (800 is still used by `.view h1`, `.sum-row .v`, `.p-amt`) and IBM Plex Mono 400/500; a test guards against Figtree/JetBrains returning.
- [x] met — criterion 3: tabular numerals on `.sum-row .v`, `.v2`, `.ramt` (added) and `.p-amt` (already); `.iamt` untouched.
- [x] met — criterion 4: `.screen :focus-visible{outline:3px solid var(--hf-your-turn);outline-offset:2px}`; every per-element `--a-blue` ring removed; the inspector's rings unchanged. Deliberate deviation accepted by the reviewer: `.sheet` and `.prompt` ring inward (−5px) because `.screen` has `overflow:hidden` and they are full-bleed, so an outward ring would be clipped.
- [?] unverifiable — how the ring looks rendered, especially on the bottom sheet, needs a human eye.
- [x] met — criterion 5: `npm test` 123/123, typecheck clean, build succeeds.
Verdict: moved to review.
