# LEASH-190: Agent screen as a chat transcript over the existing draft flow

**Status**: REVIEW
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
- [x] The same API calls happen in the same order as today for create and answer (verified by the existing `api` mocks).
- [x] Rules, notes and open questions from the draft all appear; nothing is shown that the draft does not contain.
- [x] Blocking vs optional questions remain distinguishable in text ("Needed" / "Optional").
- [x] Review, posted-draft and confirm UI and behaviour are unchanged.
- [x] Accessible names used by tests and e2e — "What may the agent buy?", "Read my instruction", "Your answer", "Send", list "Rules as I read them" — are kept, or changed in the same commit with `Agent.test.tsx` and `e2e/journey.spec.ts` updated to assert the same behaviour.
- [x] The assistant never claims to search, shop or pay (DEC-033).
- [x] Existing tests for Agent still pass (updated only for renamed accessible names, never deleted).

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

## Review log

### 2026-09-25 — independent agent review
- [x] met — criterion 1: `createDraft` still gets the trimmed instruction; `answerDraft(d.draft_id, questionId, text)` is unchanged apart from taking the id; the api-mock tests pass.
- [x] met — criterion 2: `draftToMessages` maps only instruction, rules, notes and open questions ("no message is produced for data the draft lacks" pins it); after posting, questions are filtered out as before. The draft has no answered-question history, so none is shown.
- [x] met — criterion 3: "Needed" / "Optional" chips; the existing test passes.
- [x] met — criterion 4: everything after the transcript (review, "What Viseca received", confirm, status, start over) was identical to HEAD in this ticket's diff.
- [x] met — criterion 5: "What may the agent buy?" and "Read my instruction" are the Composer's accessible names; each question group has its own "Your answer" and "Send"; the rule list is still "Rules as I read them". Nothing renamed.
- [x] met — criterion 6: the greeting only reads, asks and says nothing is active until the customer confirms; tests check no search/shop/pay claim.
- [x] met — criterion 7: `Agent.test.tsx` only gained a describe block; all Agent tests pass.
e2e: `npm run test:e2e` on a fresh isolated `leash-e2e` stack passed the whole Agent part (instruction, rules list, answering a question group, review, confirm) and failed later at `journey.spec.ts:126` on the Cockpit wording "Paid · you approved", which `status.ts` had changed before this epic (fixed in LEASH-194).
Verdict: moved to review.
