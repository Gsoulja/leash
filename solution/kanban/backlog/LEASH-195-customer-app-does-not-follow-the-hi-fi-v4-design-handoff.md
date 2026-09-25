# LEASH-195: Customer app doesn't follow the Hi-Fi v4 design handoff

**Status**: BACKLOG
**Priority**: P1
**Type**: bug
**Estimated Effort**: S (this ticket) — see LEASH-179 for the fix's real size
**Milestone**: M8 — Great demo
**Rule source**: Team (observed against `designPrototype/Hi-Fi Prototype v4 In-App Chat.dc.html`, 2026-09-25)
**Decisions**: DEC-021 (Proposed, disputed by this finding)
**Parent**: LEASH-174
**Task ID**: 174-T5
**Blocked by**: none
**Blocks**: none
**Updated**: 2026-09-25

## Description
`solution/app` does not follow the design specified in `designPrototype/`, most visibly against `Hi-Fi Prototype v4 In-App Chat.dc.html`. The app currently looks like the team's first-hour placeholder prototype (`solution/prototype/index.html`, ported via `theme.css`, cited as `DEC-021` — which was never accepted, only Proposed): blue accent, Figtree font, generic form-based screens. The actual design handoff, added a few hours after that placeholder and marked by its own README as "the single source of truth for behaviour and copy," specifies a different visual system entirely and a conversational chat flow that today's form-based `Agent.tsx` doesn't resemble.

This is not a small styling tweak — see **LEASH-179** for the full investigation and breakdown.

## Business Value
The demo is judged on whether the audience instantly sees the customer's control. A UI that doesn't match the agreed design handoff undermines that, and leaves `DEC-021` standing uncontested even though it was never formally accepted and predates the real handoff.

## Acceptance Criteria
- [ ] Fixed by completing epic **LEASH-179** (Align the customer app with the Hi-Fi v4 design handoff) and all of its sub-tasks (LEASH-180 through LEASH-194).
- [ ] This ticket closes when LEASH-179 closes; it adds no work of its own beyond the cross-reference.

## Technical Approach
None here — see LEASH-179's Technical Approach and its 15 leaf tickets for the actual sequencing (decision record first, then tokens/typography/primitives, then per-screen restyles, then the chat conversion, then a final acceptance check).

### Dependencies
- Resolved by LEASH-179 (and transitively LEASH-180 through LEASH-194).

## Testing Requirements
None here; each LEASH-179 leaf ticket names its own tests and existing-test regression risk.

## Related Files
- `solution/kanban/backlog/LEASH-179-align-customer-app-with-hi-fi-v4-design-handoff.md`
- `designPrototype/Hi-Fi Prototype v4 In-App Chat.dc.html`
- `solution/app/src/theme.css`
- `solution/app/src/screens/Agent.tsx`

## Out of scope
- Everything LEASH-179 itself marks out of scope (the superseded product-carousel/agent-shopping surfaces under DEC-033, the generic host shell, porting the `.dc.html`/`support.js` format literally).
