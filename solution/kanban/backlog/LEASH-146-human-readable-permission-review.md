# LEASH-146: Human-readable permission review

**Status**: BACKLOG
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M8 — Great demo
**Rule source**: Product
**Decisions**: none
**Parent**: LEASH-144
**Task ID**: 144-T2
**Blocked by**: LEASH-145
**Blocks**: LEASH-153
**Updated**: 2026-09-24

## Description
Turn the confirmation step into a concise customer contract instead of repeating rules, notes, decision codes and raw platform expressions.

## Business Value
The customer and the audience must understand exactly what will be allowed before activation without learning internal vocabulary.

## Acceptance Criteria
- [ ] The primary review groups boundaries under item, price, merchant, frequency and uncertainty headings.
- [ ] Repeated rule and note text appears only once.
- [ ] `DEC-*`, catalogue IDs, draft IDs and raw rule expressions are hidden from the default view.
- [ ] An “Advanced details” disclosure contains the exact platform payload for technical verification.
- [ ] Open optional questions are summarized as explicit customer choices, not sent silently.
- [ ] “Activate permission” remains visible with a concise statement of effect.
- [ ] Confirmation produces an agent message explaining the next action.

## Technical Approach
Create a customer-summary view model separate from `HardRule`. Preserve the exact payload in an expandable evidence section.

### Dependencies
- Needs LEASH-145.
- Blocks LEASH-153.

## Testing Requirements
Add tests proving internal identifiers are absent before expanding advanced details and that each customer boundary appears once.

## Related Files
- `solution/app/src/screens/Agent.tsx`
- `solution/app/src/api/client.ts`

## Out of scope
- Removing exact platform evidence from the application entirely.
