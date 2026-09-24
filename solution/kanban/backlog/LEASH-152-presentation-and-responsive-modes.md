# LEASH-152: Presentation and responsive modes

**Status**: BACKLOG
**Priority**: P1
**Type**: feature
**Estimated Effort**: M
**Milestone**: M8 — Great demo
**Rule source**: Product
**Decisions**: none
**Parent**: LEASH-144
**Task ID**: 144-T8
**Blocked by**: LEASH-145, LEASH-148
**Blocks**: LEASH-153
**Updated**: 2026-09-24

## Description
Make the experience readable both on a real narrow phone and on a projected desktop demo with the customer phone and presenter context visible together.

## Business Value
Judges should read the important state from across a room, while mobile users retain stable navigation and controls.

## Acceptance Criteria
- [ ] At 320 px width, the app has no horizontal overflow and bottom navigation remains reachable without scrolling the outer page.
- [ ] At 390 px width, conversation, timeline and decision actions fit without clipped controls.
- [ ] Desktop demo mode pairs the phone with the presenter panel and enlarges essential progress text.
- [ ] Long merchant, rule and translated currency text wraps without hiding actions.
- [ ] Reduced-motion preference disables non-essential timeline animation.
- [ ] Focus order follows conversation chronology and remains visible.
- [ ] A projector screenshot at the approved presentation resolution passes human review.

## Technical Approach
Replace fixed device heights on narrow screens with dynamic viewport sizing. Add a desktop stage layout without changing customer semantics.

### Dependencies
- Needs LEASH-145.
- Needs LEASH-148.
- Blocks LEASH-153.

## Testing Requirements
Add browser checks at 320×700, 390×844 and the approved projector resolution, including keyboard navigation and reduced motion.

## Related Files
- `solution/app/src/theme.css`
- `solution/app/src/App.tsx`

## Out of scope
- Native iOS or Android packaging.
