# LEASH-187: Permission screen as "AI agent access" with the hard-stop tile

**Status**: BACKLOG
**Priority**: P1
**Type**: feature
**Estimated Effort**: M
**Milestone**: M8 — Great demo
**Rule source**: Design handoff `designPrototype/README.md` V3 (dark status card, current mandate, BUDGET / HARD STOP AT tiles, "must show both numbers"); DEC-004/DEC-044 decide what the tiles may show
**Decisions**: DEC-044 (LEASH-180, question 4), DEC-004, DEC-006, DEC-017
**Parent**: LEASH-179
**Task ID**: 179-T8
**Blocked by**: LEASH-180, LEASH-184, LEASH-185
**Blocks**: LEASH-188, LEASH-194
**Updated**: 2026-09-25

## Description
Restyle `Permission.tsx` as the handoff's V3 surface:
- A dark ink status card with the logo status dot and overline `NO ACTIVE PERMISSION` / `ACTIVE` / `REVOKED` derived from the mandate the screen already loads.
- "Current permission" with a `StatusBadge` and a red **HARD STOP AT** `LimitTile` taken from the existing `perOrderLimit()` (the strictest per-purchase CHF limit in `hard_rules`). A BUDGET tile appears only under the rule DEC-044 records (guidance only, never presented as enforced).
- The other rules as label/value rows, then the existing tighten controls ("Lower the limit", "decline instead of asking") and the run start, restyled.

Example: a mandate with `authorization.billing_amount_chf <= 400` per purchase shows "HARD STOP AT CHF 400.00". Edge case: two per-purchase limits (after tightening, DEC-006) show the stricter one.

## Business Value
The handoff's key trust promise: the customer can never believe they authorised less than the mandate allows.

## Acceptance Criteria
- [ ] The hard-stop tile shows exactly `perOrderLimit(m)`; with no per-purchase limit the tile is absent and the rows say so.
- [ ] No tile or copy implies a budget is enforced unless it is a `hard_rule`.
- [ ] Tighten still only accepts a lower value; revoke behaviour and copy are unchanged in this ticket (LEASH-188 restyles it).
- [ ] "Revoked" is shown only once the platform confirmed it (DEC-017), as today.
- [ ] Existing tests for Permission still pass; e2e labels "New limit per order (CHF)", "Lower the limit", "Scenario", "Start a run" still resolve.

## Technical Approach
Markup in `screens/Permission.tsx` using LEASH-183/183 components. `perOrderLimit`, the mandates query, tighten/revoke/run API calls and the focus-management effect are not modified.

### Dependencies
- Needs LEASH-180.
- Needs LEASH-184.
- Needs LEASH-185.
- Blocks LEASH-188.
- Blocks LEASH-194.

## Testing Requirements
Red first in `src/screens/Permission.test.tsx`: `hard stop tile shows the strictest per-purchase limit` (two limits, the lower wins) and `no budget tile without a guidance budget`. Run `cd solution/app && npm test && npm run typecheck`.
At risk: `src/screens/Permission.test.tsx`, `e2e/journey.spec.ts`.

## Related Files
- `solution/app/src/screens/Permission.tsx`
- `solution/app/src/components/ui/`, `solution/app/src/components/LogoMark.tsx`

## Out of scope
- New mandate fields, a "stretch" limit, or any `guidance` → enforcement mapping.
- Monthly report and notifications toggle from V3.
- "+ New in chat" relaunch flow (belongs with LEASH-145).
