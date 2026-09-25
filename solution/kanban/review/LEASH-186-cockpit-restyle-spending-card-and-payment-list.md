# LEASH-186: Cockpit restyle — spending card and payment list

**Status**: REVIEW
**Priority**: P1
**Type**: feature
**Estimated Effort**: M
**Milestone**: M8 — Great demo
**Rule source**: Design handoff `designPrototype/README.md` V1 (transactions list, AGENT tag, status line) — styling only, the host shell itself is generic; outcome labels stay per LEASH-130
**Decisions**: DEC-044 (LEASH-180), DEC-037 (approval is not platform acceptance), DEC-010
**Parent**: LEASH-179
**Task ID**: 179-T7
**Blocked by**: LEASH-184, LEASH-185
**Blocks**: LEASH-194
**Updated**: 2026-09-25

## Description
Restyle `Cockpit.tsx` with the new primitives: the spending card (amount at 28/700 tabular, progress bar in the semantic hues), and the payment list as a white radius-16 list whose rows carry the AGENT tag and a status chip in green (approved within permission), violet (waiting for you) or red (blocked/declined). Only presentation changes: the same queries, run selection, SSE invalidation and the existing `statusOf` / `stageOf` labels.

## Business Value
The first screen the audience sees; it must show what happened to the money in the handoff's visual language.

## Acceptance Criteria
- [x] Spending card and payment rows use the LEASH-184 primitives and handoff tokens.
- [x] Row accessible names keep the pattern "merchant · amount · outcome label" that tests and e2e match (e.g. `/HarborByte.*CHF 391.50.*Blocked/`).
- [x] Status wording still comes from `screens/status.ts`; approval, submitted, accepted and not sent never collapse into "Paid".
- [x] `data-status` on each row's chip and the `.full` class on an exhausted bar are preserved.
- [x] No amount is ever invented when spending is loading or unavailable (existing behaviour).
- [x] Existing tests for Cockpit, status and PaymentDetail still pass.

## Technical Approach
Markup/class changes in `screens/Cockpit.tsx` and CSS in `theme.css`. `useCockpitData`, `SpendingCard` counting logic and `status.ts` are not modified.

### Dependencies
- Needs LEASH-184.
- Needs LEASH-185.
- Blocks LEASH-194.

## Testing Requirements
Red first: one new assertion in `src/screens/Cockpit.test.tsx` that an agent row shows the AGENT tag text. Run `cd solution/app && npm test && npm run typecheck`.
At risk: `src/screens/Cockpit.test.tsx` (queries `[data-status]` and `.full`), `src/screens/status.test.ts`, `e2e/journey.spec.ts` (row names).

## Related Files
- `solution/app/src/screens/Cockpit.tsx`, `solution/app/src/screens/status.ts` (read only)
- `solution/app/src/theme.css`

## Out of scope
- The handoff's card hero, quick-action tiles, greeting and agent banner states ("searching", "8 matches") — generic host shell or superseded by DEC-033.
- Run activity timeline (LEASH-148).

## Review log

### 2026-09-25 — independent agent review
- [x] met — criterion 1: counts, row and run-picker chips are `<Chip>`; amount `var(--fs-amount)` 700 tabular; bar on `--hf-divider` with a `--hf-allowed` fill, `.full` in stopped red; list radius 16; row icon is the handoff `store` icon. Fixed after review: the AGENT tag's weight is now 600 as in the handoff; its size stays 9.5px (handoff 8.5px) for legibility, noted in the CSS.
- [?] unverifiable — the rendered look needs a human eye.
- [x] met — criterion 2: row names read "HarborByte AGENT CHF 391.50 … Blocked"; the e2e `.*` patterns still match; a unit test pins `/Shop A.*CHF .*Approved/`.
- [x] met — criterion 3: `status.ts` unchanged; labels and tones come from `statusOf`; `HUE` only maps tone → chip colour; counts still say "approved", never "paid".
- [x] met — criterion 4: `data-status={tone}` reaches the chip through `Chip`'s new attribute pass-through (tested); `.full` logic unchanged.
- [x] met — criterion 5: the `!spending` early return is untouched.
- [x] met — criterion 6: 161/161, typecheck clean.
Also changed: `components/ui/Chip.tsx` gained a `neutral` tone (for "no answer" / "not sent") and attribute pass-through; tested.
Pre-existing, not caused here: `e2e/journey.spec.ts` lines 126/158/160/161 expect "Paid · you approved", but `status.ts` says "Approved · you approved". Left for LEASH-194, which runs the e2e.
Verdict: moved to review.

### 2026-09-25 — fix after the LEASH-194 acceptance screenshots
- The row's merchant-name ellipsis hid the AGENT tag ("PixelHarbor ..."). The name now truncates in its own span (`.rname-text`) and the chip never shrinks, so the tag is always visible.
