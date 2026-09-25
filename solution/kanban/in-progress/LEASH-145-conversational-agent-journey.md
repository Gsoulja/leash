# LEASH-145: Conversational Agent journey

**Status**: ONGOING
**Priority**: P0
**Type**: feature
**Estimated Effort**: L
**Milestone**: M8 — Great demo
**Rule source**: Product
**Decisions**: DEC-033, DEC-034, DEC-035, DEC-036, DEC-037
**Parent**: LEASH-144
**Task ID**: 144-T1
**Blocked by**: LEASH-101
**Blocks**: LEASH-146, LEASH-147, LEASH-148, LEASH-152, LEASH-153
**Updated**: 2026-09-25

## Description
Replace the instruction form and rule dump with a persistent, message-based conversation that guides the customer from intent to confirmed permission.

## Business Value
The product must feel like an agent that understands, clarifies and reports—not a policy administration screen.

## Acceptance Criteria
- [x] The empty state opens with a short agent greeting and a single composer.
- [x] Customer instructions and agent responses render as distinguishable messages in chronological order.
- [x] The agent acknowledges the goal in plain language before showing proposed boundaries.
- [x] Clarifications appear one at a time in the conversation with quick replies and optional free text.
- [x] Answered questions remain visible as part of the transcript.
- [x] Loading, retry and refusal states appear as messages at the point where they occurred.
- [x] Reload and tab changes preserve the conversation without duplicating messages.
- [x] The transcript never claims work that the backend has not recorded.
- [x] Messages distinguish Leash’s permission assistant from the external shopping agent; Leash never claims to search or purchase on its own.
- [x] Context-based questions disclose their source as a preference or observation, permit disagreement, and do not imply prior customer approval.
- [x] Corrections show the superseded and current draft revisions; reload preserves the latest revision and cannot restore a stale confirmation action.

## Technical Approach
Model the UI as explicit conversation states derived from the policy draft, its questions and mutation results. Keep the draft ID durable, but render semantic message components rather than raw API structures.

### Dependencies
- Needs LEASH-101.
- Blocks LEASH-146.
- Blocks LEASH-147.
- Blocks LEASH-148.
- Blocks LEASH-152.
- Blocks LEASH-153.

## Testing Requirements
Include background preference accepted/rejected, an explicit current-request override, a draft correction and stale-tab review recovery.

Write component tests for the empty, compiling, clarification, error, ready and reloaded states. Add a browser test that completes a clarification without leaving the conversation.

## Related Files
- `solution/app/src/screens/Agent.tsx`
- `solution/app/src/theme.css`
- `solution/app/src/api/client.ts`

## Out of scope
- General-purpose open-domain chat.

## Progress log

### 2026-09-24 — the backend a free-text turn needs

Started **out of dependency order**, at the user's direction ("forget Viseca and team, just build and
move"): LEASH-101 is still in `review/`, so the graph does not yet call this ready.

`POST /api/policies/drafts/{draft_id}/turns` is in `policy_api.py`. A chat turn is not an answer to a
question — `clarify()` requires every answer to match a question open at that point, and free text
matches none — so a turn instead adds to the customer's words and the whole instruction is read again.

The rule when a new turn changes the instruction: an earlier answer whose question is no longer open is
**dropped from the replay and re-asked**, never applied to a different question and never assumed
(`_still_answered`). More questions is the safe direction; fewer is not. It reuses the existing revision
machinery unchanged — revision + 1, earlier revisions marked superseded, the context bundle carried
forward — so corrections stay auditable exactly as answers already were.

Five tests in `tests/adapters/test_policy_api.py` against real Postgres: a turn makes a new revision
from the customer's words, turns accumulate in order, a turn that moots an earlier answer does not
break the draft (the later words win), a turn is refused once the draft is at Viseca, and the bad-body
shapes are 422.

**Not done:** none of the acceptance criteria above are ticked. This is the backend a message UI needs,
not the UI — `Agent.tsx` is still the one-shot instruction form. Apertus is not wired into this route
yet either; the route runs the deterministic compiler alone.

### 2026-09-24 — the conversation

`Agent.tsx` is a message conversation. The transcript is **derived, never asserted**: a customer turn
renders only once its words are in the instruction the service stored, and an answered question renders
only once that question has stopped being open. Anything in flight says so. That is what AC8 means in
code rather than in prose — two tests drive it, including one where the service returns a draft that
does not contain the words just sent, and the turn correctly does not appear.

- `POST /turns` reached from the composer; the first message still creates the draft.
- One clarification at a time (the blocking one first), quick replies plus free text; the answered pair
  stays in the transcript above it.
- Rules say where they came from — "you asked for this" against "my default (DEC-013) — say so if you
  disagree". A default is never dressed up as the customer's instruction.
- `revision N` with "replaces revision N-1" after a correction.
- **Submit and confirm now carry the revision that was reviewed** (`client.ts`), so a stale tab is
  refused by the service instead of confirming something nobody read. This needed the contract and the
  client, which is why both are touched beyond the ticket's Related Files: `client.ts` types are
  generated from `contracts/policy-api.yaml`, so `/turns` and `TurnRequest` had to be added there first.

13 component tests (empty, acknowledged, clarification one-at-a-time, correction, refusal, reload,
unrecorded turn, review held back, stale confirm, submit refused). App suite 119 passing, `tsc` clean;
engine contract tests 41 passing against the updated spec.

**Not done, and not ticked:**
- **AC10 is unmet.** Context-based questions cannot disclose their source: the contract's `Question`
  has `question_id`, `text`, `blocking`, `options` and no provenance field, so the screen has nothing
  to render. Rules do disclose theirs. Closing this needs a contract change (a `source` on `Question`),
  which belongs with LEASH-154's context work rather than here.
- The **Playwright browser test** the Testing Requirements ask for is not written; coverage is component
  level only.
- **Background preference accepted/rejected** is untested for the same reason as AC10 — the screen
  cannot yet tell a context-derived question from any other.
- Apertus is **not** behind this conversation yet; `/turns` runs the deterministic compiler alone.

### 2026-09-24 — independent agent review (round 1), and the fixes

The reviewer returned **AC2, AC6 and AC8 `not met`** and recommended staying in `in-progress`. It was
right on every count; all are now fixed and pinned.

- **AC8, break 1 — a dropped answer kept rendering as answered.** `question_id` is a hash of the
  question *text* (`clarify.py:50`), so a correction re-asks the same question under a *new* id and
  `_still_answered` drops the old answer entirely. The screen's test was `!open.has(question_id)` — the
  old id is not open, so the settled pair kept showing beside the fresh question, while the backend held
  no answer at all. Inferring "answered" from "not open" was the mistake. **Fixed at the source:**
  `clarify()` now returns `answers` — the answers the view was actually built from — and the contract
  carries it on `PolicyDraft`. The transcript renders answered pairs from that and nothing else.
- **AC8, break 2 — one recorded turn, two bubbles.** A turn whose words the service did not record
  stayed in local storage forever; when the customer retyped the same sentence and it *was* recorded,
  `instruction.includes(text)` was true for both entries. Fixed: each entry consumes its match in the
  instruction (`indexOf(text, from)`), so a record can be claimed once and only once.
- **AC8, break 3 — the second mechanism had no test.** The reviewer deleted the answered-filter and all
  13 tests still passed. Both halves now fail a test when removed (verified by mutation, reverted).
- **AC2 — order.** Answered pairs were rendered after every customer turn regardless of when they
  happened. The two local arrays are now one ordered log: local order, service truth.
- **AC6 — a draft that could not be loaded produced no message at all.** The old error branch had been
  dropped in the rewrite. Restored as a message with the way out beside it, and the retry line no longer
  points at a composer that is hidden after submission.
- **A Viseca rule was presented as Leash's own default.** `ruleSource` mapped only `customer`, so the
  contract's `viseca` and `assumption` sources both fell through to "my default — say so if you
  disagree", inviting the customer to disagree with something that is not ours to change. Fixed and
  tested.

The reviewer also **confirmed the AC10 claim is honest** — `Question` in the contract has no provenance
field, and the UI never sends the `context` object `create_draft` accepts, so no context-derived question
can exist yet. It found the stale-revision guard sound and could not defeat it.

19 component tests (6 new), 125 app tests, `tsc` clean. Engine: `clarify()` gained `answers`, with a test
that a turn dropping an answer is reported.

**Still open:** AC10 (needs a contract change belonging to LEASH-154), the Playwright browser test, the
background-preference and current-request-override cases, and Apertus behind the route.

### 2026-09-24 — independent agent review (round 2), and the fixes

AC2, AC6 and AC11 now `met`; the reviewer found **AC8 still broken**, in two new ways it reproduced.
Both fixed and pinned by mutation.

- **A refused answer was reported as one the draft was built from.** I had moved the record to
  `clarify()` believing a rejected answer always raises. It does not: two branches reject with
  `continue` — an option clash and a free-text conflict — so the answer stayed in `replayed`, shipped in
  `PolicyDraft.answers`, and the transcript showed the question as settled while it was still open and
  the answer had been discarded. Reproduced against the real compiler: answering *"At most CHF 50, pick
  up only."* to the spend question on a delivery-only instruction keeps the question open, never applies
  the pick-up, and still reported the answer. Fixed: the record is appended where an answer is actually
  **applied**, not where it is read. A new API test pins it, verified to fail against the old placement.
- **An unrecorded turn could hide a recorded one.** `indexOf(text, from)` searched anywhere, so a turn
  the service never recorded matched *inside* a later turn and advanced the cursor past it — the phantom
  showed and the real turn vanished. Reproduced: say "delivery" (not recorded), then "Only for
  delivery" (recorded) → the transcript showed "delivery" and dropped the real one. Fixed: turns are
  appended in order, so an entry must match at the **head** of what is left or it is no record at all.
- **Two identical answers collapsed into one.** The claim map was keyed `question_id|answer`. Answers
  are now claimed one for one from what the draft reports.

Mutations verified after the fix: searching anywhere instead of at the head fails a test; not claiming
answers one for one fails two; the round-1 mutations still fail theirs.

21 component tests (2 new), 127 app tests, `tsc` clean.

**Still open and unticked:** AC10 (needs a `source` on `Question` in the contract — LEASH-154's work; the
reviewer independently confirmed no context-derived question can exist yet, since the UI never sends the
`context` object `create_draft` accepts). Also outstanding: the Playwright test, the background-preference
and current-request-override cases, tests for the loading/sending states, and Apertus behind the route.
Known minor, left as is: an answer given in another tab always renders at the end of the transcript,
which cannot happen in the single-tab flow; and a draft row written before `answers` existed loses its
answered pairs on reload.

### 2026-09-25 — independent agent review (round 3), and the fixes

Nine criteria `met`. AC8 **`not met` for the sixth time**, and the reviewer named the pattern correctly:
every break has been the screen *inferring* backend state instead of reading it. So this round changed
the mechanism rather than patching the symptom.

- **The head-match still matched typed words.** A turn that was never recorded but is a *prefix* of the
  next recorded one matched at the head, consumed the cursor, and the real turn then vanished —
  "Only" swallowing "Only for delivery". Round 2 had narrowed the character class, not closed the hole.
  **Fixed by removing the matching entirely:** a `said` entry now stores *the instruction the service
  returned for that turn*, and the message rendered is the text the service **added** —
  `entry.instruction` minus what is already accounted for. Nothing is matched against the customer's
  typed words, so a turn that added nothing contributes nothing, and a recorded turn cannot be hidden
  by one that was not.
- **"Nothing changed." was asserted, never read.** `/turns` commits in a transaction, so a lost reply
  can follow a write that landed — and the screen said flatly that nothing had. Worse, those words then
  reached no transcript ever, on any reload. Fixed two ways: a failed turn refetches the draft instead
  of speaking for the service, and any words the draft holds that this tab never saw a response for are
  read off the end of the instruction. Tested with a 500 whose write did land.
- **The free-text `replayed.append` was unpinned** — deleting it left 204 tests passing, so an applied
  answer could silently stop being reported and the transcript would lose a settled pair. Both sites
  are now pinned by a test that fails when either is removed.
- **A claim about Viseca the screen could not support.** The load-failure message said "nothing was
  lost at Viseca — nothing had been sent there yet" on any load error, including one for a draft that
  may already carry a `platform_draft_id`. Reworded to what it actually knows.

Mutations after the fixes: dropping the added-nothing guard fails 4 tests, dropping the read-off-the-end
fails 1, dropping the stale-log guard fails 1 (it survived until a test was written for it), and both
engine sites fail their own. 24 component tests, 129 app tests.

**Still unticked: AC10**, confirmed honest a third time — `Question` carries no provenance and the UI
never sends `create_draft`'s `context`. The reviewer also noted a contract/implementation drift for
LEASH-154: `CreateDraftRequest` is `additionalProperties: false` with no `context`, while
`create_draft` accepts one.

Outstanding: the Playwright test, background-preference and current-request-override cases, and Apertus
behind the route.

### 2026-09-25 — independent agent review (round 4), and the fixes

**AC8 held.** The reviewer attacked the round-3 mechanism and could not break it, and showed why:
every surviving entry is checked against the same `d.instruction`, so all survivors are prefixes of one
string and a splice can only yield a contiguous tail of text the service actually stored. It also
confirmed that `/answers` never writes the instruction column — only `/turns` does, append-only — so
every "me" message is literally stored customer text. Both engine `replayed.append` sites were
re-derived rather than taken on trust, and `_still_answered` cannot desynchronise `answers` from
`open_questions`.

**AC2 `not met`, and it was the same divergence mirrored.** The refetch a failed turn starts was not
cancelled, so it could land *after* the retry succeeded, overwrite newer data, and the recorded turn
then failed its check and vanished — with no error, because the successful retry had cleared the
message. It did not self-heal (`staleTime: Infinity`), and the customer was invited to say it a third
time, appending the same words again. Fixed: in-flight reads are cancelled before a mutation result is
applied, on both the turn and the answer paths, and the failure path refetches rather than invalidating.
Pinned by a test that holds the stale read open and releases it after the retry — it lives in its own
file (`Agent.race.test.tsx`), because a held reply leaves a pending fetch that breaks whatever test
renders next.

Also fixed: **`create_draft` stored the instruction untrimmed** while `add_turn` stores
`f"{old} {text}".strip()`. The transcript relies on each stored instruction being a prefix of its
successors; that property was true only by the client's good manners. Now enforced at both writers and
tested.

Left as known and minor, both declared rather than fixed: two lost replies in a row render as one
customer message (all words recorded, nothing false claimed), and a draft row written before `answers`
existed loses its answered pairs on reload.

131 app tests across 13 files, `tsc` clean.

**Still unticked: AC10** — a fourth independent confirmation that `Question` carries no provenance.
Outstanding: the Playwright test, background-preference and current-request-override cases, Apertus
behind the route.

### 2026-09-25 — the browser journey, and what it had been hiding

The Testing Requirements' browser test is done: `e2e/journey.spec.ts` drives the conversation and
completes a clarification without leaving it (the composer stays, and the answer lands in the
transcript). **1 passed (32.8s)** against the real Compose stack.

Getting there took fixing five things, only two of which were this ticket's:

| What | Whose |
| --- | --- |
| Port 19000 taken by an unrelated MinIO container | environment — `e2e/stack.ts` default moved to 19100 |
| Playwright's chromium was never installed | environment |
| `"Read my instruction"` selectors | **LEASH-145** — the rewrite broke them and nothing caught it |
| Clarifications now come one at a time, so the split-check question is not on screen until the shop question is answered | **LEASH-145** — intended (AC4); the journey now asserts it |
| `"Paid · you approved"` asserted three times | **LEASH-130** — see below |

**LEASH-130 (in `review/`) left a stale assertion with real meaning.** Commit `55df06c` removed the
"Paid" label deliberately — the generated contract says approved+accepted is shown as "Approved",
*"never Paid, because the platform accepting a decision says nothing about settlement"*. The journey
kept asserting the overclaiming label in three places. It went unnoticed because `npm run test:e2e`
could not start on this machine at all. Worth telling whoever reviews LEASH-130: its acceptance
evidence would have been checked against a suite that never ran.

Verified together: engine 1600, app 131 across 13 files, e2e 1 passed, `tsc` clean.

### 2026-09-25 — AC10 closed

The ticket said this needed "a contract change (a `source` on `Question`)". It needed that and four
things underneath it, because the provenance was being dropped in three places and the obvious one was
not the one that mattered.

What was actually wrong: `conversation._blocking` rewrites a blocking question's wording with the
background's phrasing whenever the field matches, and discards the `SourceRef` one line earlier — but
that rewrite never reaches the customer at all, because the chat renders the **draft's**
`open_questions` and `client.ts` throws the assistant's reply array away (`.then(r => r.draft)`). So
background was not silently mislabelled in the UI; it was invisible. The question the customer answers
comes from the draft, which is where provenance had to land.

The path now: `permission_context.SuggestedQuestion` carries `kind` and `evidence` (the recorded words
themselves) alongside its existing `SourceRef` → `agent.Question` gains a `QuestionSource` →
`Proposal.as_draft()` sends questions as objects instead of bare strings → `policy_api._assessed`
attaches the source to the `open_question` it creates, still accepting bare strings so the existing
contract holds → both contracts document it → the chat renders "From your saved preferences" with the
recorded words quoted, and says it is not a rule yet and not something the customer told us.

`_context_gaps`' two questions (conflicting background, truncated background) now carry a source too —
they are about the bundle rather than one entry, so the source quotes the entries at issue. A customer
asked to overrule something on file cannot do that fairly without seeing what it says.

Tests, all written first and each red for the right reason:
`test_a_background_question_carries_the_kind_and_words_it_came_from` (permission_context),
`test_a_background_question_tells_the_customer_where_it_came_from` and
`test_a_question_the_customer_prompted_claims_no_background_source` (assistant surface),
`test_an_assistant_question_keeps_its_background_source_on_the_draft` and
`test_a_question_with_no_background_behind_it_carries_no_source` (policy API, incl. reload),
plus two in `Agent.test.tsx`. Every one has a mirror asserting an ordinary question wears no source —
a provenance label that appears everywhere says nothing.

Checks: permission_context 31 · assistant 154 · policy API 49 · app 144 with `tsc` clean.

Still open on this ticket, unchanged: the Playwright browser test the Testing Requirements ask for is
not written, and the "background preference accepted/rejected" case is component-level only. The note
above saying Apertus is not behind this conversation is now stale — LEASH-175 wired it.
