# LEASH-190: Agent screen as a chat transcript over the existing draft flow

**Status**: BACKLOG
**Priority**: P1
**Type**: feature
**Estimated Effort**: M
**Milestone**: M8 — Great demo
**Rule source**: Design handoff `designPrototype/README.md` V4 (conversation, rule chips posted as rules are created); `solution/docs/customer-journey-for-design.md` screens 1–2; data flow stays LEASH-092/LEASH-123
**Decisions**: DEC-044 (LEASH-180), DEC-033, DEC-003, DEC-035
**Parent**: LEASH-179
**Task ID**: 179-T11
**Blocked by**: LEASH-185, LEASH-189
**Blocks**: LEASH-191
**Updated**: 2026-09-25

## Description
First half of the structural change. Replace the instruction form and question cards in `Agent.tsx` with a transcript built from the **same draft the screen already loads**:
- Empty state: an assistant greeting and the composer (instead of the textarea card).
- The instruction → a customer bubble; `createDraft` unchanged.
- `draft.rules` → one rule chip each; `draft.notes` → assistant bubbles.
- Each open question → an assistant bubble with its options as suggested replies and free text in the composer; `answerDraft` unchanged; a refused answer appears as an assistant message at that point (today's `role="alert"`).
- Answered questions stay visible in the transcript as far as the current draft data allows (no invented history).

The "Review what Viseca will receive" button, the posted-draft card and "Confirm this permission" stay **exactly as they are today**, rendered below the transcript. LEASH-191 converts them.

Example: "Buy a 27-inch monitor, no more than CHF 400" → customer bubble, chips for the item and the limit, then one question with its options. Edge case: a reload with a stored draft id rebuilds the same transcript from the draft, without duplicate messages.

## Business Value
The Agent tab finally reads as a conversation, without touching the review and consent logic that makes activation safe.

## Acceptance Criteria
- [ ] The same API calls happen in the same order as today for create and answer (verified by the existing `api` mocks).
- [ ] Rules, notes and open questions from the draft all appear; nothing is shown that the draft does not contain.
- [ ] Blocking vs optional questions remain distinguishable in text ("Needed" / "Optional").
- [ ] Review, posted-draft and confirm UI and behaviour are unchanged.
- [ ] Accessible names used by tests and e2e — "What may the agent buy?", "Read my instruction", "Your answer", "Send", list "Rules as I read them" — are kept, or changed in the same commit with `Agent.test.tsx` and `e2e/journey.spec.ts` updated to assert the same behaviour.
- [ ] The assistant never claims to search, shop or pay (DEC-033).
- [ ] Existing tests for Agent still pass (updated only for renamed accessible names, never deleted).

## Technical Approach
Derive a `messages` array from `PolicyDraft` in a pure function (`draftToMessages`) and render it with LEASH-189's `Transcript`. State (`draftId`, `posted`, `confirmed`, `busy`, `message`), `act()`, `answer()`, `startOver()` and the query stay as they are. This is presentation over the existing state machine, not a new one; LEASH-145 later adds persistence of the full conversation and revisions.

### Dependencies
- Needs LEASH-185.
- Needs LEASH-189.
- Blocks LEASH-191.

## Testing Requirements
Red first: `src/screens/draftToMessages.test.ts` — `every rule becomes one rule chip`, `open questions follow the rules in order`, `no message is produced for data the draft lacks`. Then adapt the render in `Agent.tsx`. Run `cd solution/app && npm test && npm run typecheck && npm run test:e2e`.
At risk: `src/screens/Agent.test.tsx` (queries by label, list name, button name, "Needed"/"Optional"), `e2e/journey.spec.ts` (instruction label and button).

## Related Files
- `solution/app/src/screens/Agent.tsx`, `solution/app/src/screens/Agent.test.tsx`
- `solution/app/src/components/chat/`
- `solution/app/src/api/client.ts` (read only)

## Out of scope
- Review and confirmation (LEASH-191).
- LLM clarification, draft revisions, context questions, persistent transcript storage (LEASH-101, LEASH-145, LEASH-154).
- Product search results or any shopping activity in the chat (DEC-033).
