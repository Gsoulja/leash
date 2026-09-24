# LEASH-092: Agent chat and rule confirmation

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M4 — Customer-control journey
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-007
**Task ID**: 007-T3
**Blocked by**: LEASH-091, LEASH-061, LEASH-065, LEASH-123, LEASH-118
**Blocks**: LEASH-125, LEASH-128
**Updated**: 2026-09-23

## Description
Chat screen: the customer's instruction, the compiled rules with interpretation notes and open questions, and Confirm.

## Business Value
The customer sees and confirms exactly what the agent may do.

## Acceptance Criteria
- [x] Rules and notes render from the draft.
- [x] Confirm calls the policy service; nothing is paid before.
- [x] Open questions must be answered before Confirm is enabled.
- [x] Clarifying questions are answered in the app; the confirm step shows the exact platform draft.

## Technical Approach
`src/screens/Agent.tsx`.

### Dependencies
- Needs LEASH-091.
- Needs LEASH-061.
- Needs LEASH-065.
- Needs LEASH-123.
- Needs LEASH-118.
- Blocks LEASH-125.
- Blocks LEASH-128.

## Testing Requirements
Write first: `confirm is disabled while questions are open`.

## Related Files
- `solution/app/src/screens/Agent.tsx`

## Out of scope
- Free chat with the assistant (LEASH-101).

## Implementation note (2026-09-23)
- `app/src/screens/Agent.tsx` is shown on the Agent tab. The flow:
  1. The customer writes an instruction; "Read my instruction" calls `POST /api/policies/drafts`.
  2. The screen shows the instruction, the rules as read (with the DEC id where the reading comes from the decision log), and the notes.
  3. Each open question is shown with its options as buttons, plus a free-text field. An answer calls `POST …/answers` with that one answer. A refused answer (422) shows the service's reason under its question, and the question stays.
  4. "Review what Viseca will receive" (`POST …/submit`) is enabled only when the draft is `ready`, i.e. no blocking question is left. Questions are marked "Needed" or "Optional". The two optional offers ("any kind of shop", the split check) don't hold it back, following the contract's `blocking` flag.
  5. The review shows the posted body exactly: `platform_draft_id`, each hard rule in one line (field, operator, value, currency, scope), the uncertainty choice and any guidance.
  6. "Confirm this permission" (`POST …/confirm` with `{confirmed: true}`) is the only call that activates anything. It then refreshes the Permission tab.
- The draft id is kept in `sessionStorage` (wrapped in try/catch), so a tab switch or reload returns to the draft. A repeat submit or confirm is idempotent on the service (LEASH-123, LEASH-061).
- `api/client.ts` adds `createDraft`, `draft`, `answerDraft`, `submitDraft` and `confirmDraft`, with types generated from the contract.
- Tests: `src/screens/Agent.test.tsx` has 7 tests, including `confirm is disabled while questions are open`. 75 app tests pass; tsc and the build are clean.
- Not in this ticket: the demo script (LEASH-112, in review) still runs steps 0a–0d in the terminal, because the app had no agent screen when it was written.

## Review log

### 2026-09-23 — independent agent review, round 1
- [x] met — criterion 1: the instruction, rules (with DEC chip) and notes all render from the PolicyDraft.
- [x] met — criterion 2: only the explicit Confirm tap calls `…/confirm` (`{confirmed: true}`). Errors keep it enabled and show the reason; a double tap posts once.
- [x] met — criterion 3: Review, and so Confirm, is enabled only at `status: ready`. The blocking-only reading was judged sound: the LEASH-123 design, its criterion 2, the contract's `blocking` flag and the submit 409 all say "blocking"; the only non-blocking questions are extra-restriction offers.
- [ ] not met — criterion 4:
  - G1: the review didn't show the posted `open_questions`. All five public instructions reach ready with optional questions left open, and those are posted to Viseca.
  - G1b (minor): the posted `instruction` wasn't shown inside the review region.
- [?] unverifiable — layout at phone width and focus behaviour need a real browser (not asked for by the criteria).
Verdict: returned to in-progress. Fix: the review region now shows the posted instruction, and the posted open questions as "Questions left open (sent as they are)", with a line saying they go to Viseca unanswered. The confirm-step test asserts both. 75 app tests pass; tsc clean.

### 2026-09-23 — independent agent review, round 2
- [x] met — criterion 1: the instruction, rules (with DEC chip) and notes render from the PolicyDraft; tested.
- [x] met — criterion 2: only the explicit Confirm tap sends `POST …/confirm` `{confirmed: true}`; a double tap sends once; an error keeps Confirm enabled.
- [x] met — criterion 3: Review, and so Confirm, is enabled only at `status: ready`; "Needed" marks blocking questions; `confirm is disabled while questions are open` passes.
- [x] met — criterion 4: answers go by option or free text, and a refused answer shows its reason under the question. The review shows the full posted body: `platform_draft_id`, instruction, every hard rule, uncertainty choice, guidance and open questions. G1 and G1b are fixed; the round-1 edge tests R1–R9 pass.
- Outside the criteria and unverifiable without a real browser: layout at phone width, and focus after an answer or review (goes to BODY in jsdom).
- Checks: 75 app tests pass; tsc and the build are clean.
Verdict: all criteria met. Moved to done on the product owner's standing instruction for this run.
