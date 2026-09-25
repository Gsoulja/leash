# LEASH-184: Presentational primitives — buttons, tiles, badges and chips

**Status**: REVIEW
**Priority**: P1
**Type**: feature
**Estimated Effort**: M
**Milestone**: M8 — Great demo
**Rule source**: Design handoff `designPrototype/README.md` § Buttons, § Radius, V3 tiles; `designPrototype/Sticker Sheet.dc.html` (component states, 5×6 button matrix)
**Decisions**: DEC-044 (LEASH-180)
**Parent**: LEASH-179
**Task ID**: 179-T5
**Blocked by**: LEASH-181, LEASH-182
**Blocks**: LEASH-186, LEASH-187, LEASH-189, LEASH-192, LEASH-193
**Updated**: 2026-09-25

## Description
Build the small shared building blocks the screen tickets will use, as CSS classes plus thin React components, **without adopting them in any screen yet**:
- `Button` variants: primary (ink fill), secondary (1.5px ink outline), destructive (red outline / red fill), approve (green) and attention (violet); heights 44–52px, decision buttons ≥ 48px; radius 11–14.
- `LimitTile`: overline + tabular amount, tones `allowed` (BUDGET), `attention` (STRETCH UP TO) and `stopped` (HARD STOP AT).
- `StatusBadge`: DRAFT / ACTIVE / REVOKED.
- Chip tones re-expressed in the three semantic hues (green = within rules, violet = needs attention, red = stopped), plus the AGENT tag style.

## Business Value
One consistent vocabulary for every later screen ticket, reviewed once instead of per screen.

## Acceptance Criteria
- [x] Each primitive renders the handoff shape and tone from tokens only (no hard-coded hex in components).
- [x] Decision-sized buttons are ≥ 48px tall; other targets ≥ 44px.
- [x] Every tone also carries text (e.g. "Hard stop at", "over budget"); colour never carries meaning alone.
- [x] `LimitTile` formats amounts from a string/`Decimal`-safe input, never recomputing money in floats.
- [x] No existing screen imports the new primitives in this ticket; the existing `.pill`, `.chip`, `.card` classes keep working.
- [x] Existing tests for all screens still pass.

## Technical Approach
`solution/app/src/components/ui/` (Button, LimitTile, StatusBadge, Chip) and their CSS in `theme.css`. Pure presentational components: props in, markup out; no queries, no API.

### Dependencies
- Needs LEASH-181.
- Needs LEASH-182.
- Blocks LEASH-186.
- Blocks LEASH-187.
- Blocks LEASH-189.
- Blocks LEASH-192.
- Blocks LEASH-193.

## Testing Requirements
Red first, one behaviour per test in `src/components/ui/*.test.tsx`: `test_hard_stop_tile_names_its_limit_in_text`, button variant renders an accessible name and `disabled` state, badge text per status. Run `cd solution/app && npm test && npm run typecheck`.
At risk: none (no screen changes); run the full suite to prove it.

## Related Files
- `solution/app/src/components/`
- `solution/app/src/theme.css`
- `designPrototype/Sticker Sheet.dc.html`

## Out of scope
- Chat-specific primitives (LEASH-189).
- Adopting the primitives in screens.
- Approve buttons on product proposals (superseded by DEC-033).

## Review log

### 2026-09-25 — independent agent review
- [?] unverifiable — criterion 1: tokens-only part met (no hex in the `.tsx` components; every tone is a `var(--hf-*)` token; `#fff` labels on filled buttons are the handoff's neutral, contrast-tested ≥ 4.5). Tile, badge and button geometry match the handoff. Fixed after review: the destructive outline label now uses stopped red `#C0203A` as the Sticker Sheet does (5.98:1 on white). Remaining deliberate drifts for a human to accept: DRAFT badge uses `--hf-divider`/`--hf-muted-text` (prototype's `#F1F0EC`/`#55554F` are not tokens); badge text is `--fs-overline` (11px) rather than 9.5px. The visual match needs a human look.
- [x] met — criterion 2: `.btn` min-height 44px, `.btn-decision` 48px (class tested; jsdom can't measure pixels).
- [x] met — criterion 3: tiles say "Hard stop at" / "Stretch up to" / "Budget · guidance" (DEC-044 ruling 4) in text and `aria-label`; badges show DRAFT/ACTIVE/REVOKED; buttons and chips require text children.
- [x] met — criterion 4: `formatChf` is regex + string operations only; tests cover an amount beyond float precision and reject `1e3`, `-5`, `12.345`, `NaN`, empty.
- [x] met — criterion 5: nothing in `src/screens` or `App.tsx` imports `components/ui`; new selectors collide with no existing rule; `.pill`, `.chip`, `.card` untouched.
- [x] met — criterion 6: 152/152 at review time; typecheck clean.
Verdict: moved to review; the visual match is left for the human gate.
