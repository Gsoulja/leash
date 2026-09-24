# LEASH-189: Chat primitives — bubbles, rule chip, system chip, typing, composer

**Status**: BACKLOG
**Priority**: P1
**Type**: feature
**Estimated Effort**: M
**Milestone**: M8 — Great demo
**Rule source**: Design handoff `designPrototype/README.md` V4 message types and composer; § Interactions (typing, 120ms chip animation, reduced motion, `aria-live`)
**Decisions**: DEC-044 (LEASH-180), DEC-033
**Parent**: LEASH-179
**Task ID**: 179-T10
**Blocked by**: LEASH-184
**Blocks**: LEASH-190
**Updated**: 2026-09-25

## Description
Build the chat vocabulary as pure presentational components, not yet mounted in any screen:
- `AssistantBubble` (white, radius 18/18/18/6, max 82%) and `CustomerBubble` (ink, right-aligned, radius 18/18/6/18).
- `RuleChip`: tinted pill, 16px icon, overline `ADDED TO PERMISSION · {LABEL}`, value — "the main trust device".
- `SystemChip`: centred pill in green (e.g. "Permission active") or red ("Permission revoked").
- `TypingIndicator`, and a `Composer` with suggested-reply chips (38px, radius 19; one may be ink-filled), a text field and a send button.
- A `Transcript` container: chronological list, `aria-live="polite"` announcing new assistant messages, auto-scroll to newest, reduced-motion respected.

All text is rendered as React text; shop or agent strings are never interpreted as markup.

## Business Value
The shared basis for this epic's chat screen and for LEASH-145/146, so the conversation is built once.

## Acceptance Criteria
- [ ] Each primitive renders from props only; no queries or API calls.
- [ ] Customer and assistant messages are distinguishable by more than colour (alignment and an accessible "You" / "Permission assistant" label).
- [ ] Rule chips show their label and value in text; overline copy follows DEC-044 (question 6: permission, not shopping).
- [ ] Suggested replies are real buttons ≥ 44px; the composer's send is disabled for empty input.
- [ ] New assistant messages are announced once via a polite live region; reduced motion disables the chip animation.
- [ ] Existing tests for all screens still pass (no screen changes here).

## Technical Approach
`solution/app/src/components/chat/`. Pure components plus CSS; a tiny `useAutoScroll` hook. No timers that fake agent "typing" for content the backend has not produced.

### Dependencies
- Needs LEASH-184.
- Blocks LEASH-190.

## Testing Requirements
Red first in `src/components/chat/*.test.tsx`: `rule chip names its field and value in text`, `suggested reply calls onReply with its label`, `send is disabled when the field is empty`, `transcript announces a new assistant message once`. Run `cd solution/app && npm test && npm run typecheck`.
At risk: none; run the full suite to prove it.

## Related Files
- `solution/app/src/components/chat/` (new)
- `designPrototype/Hi-Fi Prototype v4 In-App Chat.dc.html`, `designPrototype/Sticker Sheet.dc.html`

## Out of scope
- Search card, flag bubble, results carousel, receipt card (DEC-033; shop-text flags belong to LEASH-170).
- Mic / voice input.
