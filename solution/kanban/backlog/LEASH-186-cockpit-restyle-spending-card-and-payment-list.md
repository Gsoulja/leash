# LEASH-186: Cockpit restyle — spending card and payment list

**Status**: BACKLOG
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
- [ ] Spending card and payment rows use the LEASH-184 primitives and handoff tokens.
- [ ] Row accessible names keep the pattern "merchant · amount · outcome label" that tests and e2e match (e.g. `/HarborByte.*CHF 391.50.*Blocked/`).
- [ ] Status wording still comes from `screens/status.ts`; approval, submitted, accepted and not sent never collapse into "Paid".
- [ ] `data-status` on each row's chip and the `.full` class on an exhausted bar are preserved.
- [ ] No amount is ever invented when spending is loading or unavailable (existing behaviour).
- [ ] Existing tests for Cockpit, status and PaymentDetail still pass.

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
