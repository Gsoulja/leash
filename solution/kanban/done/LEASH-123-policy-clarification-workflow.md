# LEASH-123: Policy clarification workflow

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M4 — Customer-control journey
**Rule source**: Viseca contract + Team
**Decisions**: DEC-003
**Parent**: LEASH-005
**Task ID**: 005-T10
**Blocked by**: LEASH-065, LEASH-118
**Blocks**: LEASH-092, LEASH-125, LEASH-128
**Updated**: 2026-09-23

## Description
Local draft → open questions → customer answers → recompile until nothing blocking remains → post the finalised policy as a Viseca draft → show that exact draft → separate explicit confirm.

## Business Value
The customer confirms a complete, understood policy; the API has no draft-update endpoint.

## Acceptance Criteria
- [x] Answers are stored locally and trigger recompilation.
- [x] Nothing is posted to Viseca while blocking questions remain.
- [x] The confirm step shows the exact platform draft that will be activated.
- [x] Confirming twice is idempotent.

## Technical Approach
Policy service endpoints + compiler.

### Dependencies
- Needs LEASH-065.
- Needs LEASH-118.
- Blocks LEASH-092.
- Blocks LEASH-125.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_no_platform_draft_while_questions_open`.

## Related Files
- `solution/engine/src/leash/application/clarify.py`
- `solution/engine/tests/application/test_clarify.py`

## Out of scope
- Free chat (LEASH-101).

## Implementation note (2026-09-23)
- `application/clarify.py` turns an instruction plus the customer's answers so far into the contract's PolicyDraft.
  - Question IDs are derived from the question itself, so answers keep pointing at their questions across recompiles.
  - The uncertainty choice, the split check and the shop kind have fixed options with a deterministic effect: set the policy; add `split_check = on`; add `merchant_category in [kind]`, or explicitly any shop.
  - Any other answer is the customer's words. It is appended as a clarifying sentence and the whole text is recompiled through the compiler's grammar, so it can raise new questions. The question closes only if the compiler stops asking it.
  - Answers never remove a rule the instruction stated. The stored instruction stays verbatim. Unknown questions or options → `AnswerError`.
- `POST /api/policies/drafts/{id}/answers` (contract AnswersRequest):
  - answers are stored in order (migration 0005, `policy_drafts.answers`) and the draft is recompiled and stored;
  - 404 for an unknown draft, 422 for a bad body, an unknown question or an invalid option;
  - 409 `already_submitted` once the draft is at Viseca, which has no draft-update endpoint.
- Criteria 2–4:
  - submit refuses while any blocking question remains (409, nothing posted);
  - submit returns the exact posted body, again on every repeat, and that is what gets confirmed;
  - confirm is idempotent (LEASH-061).
- Tests: `tests/application/test_clarify.py` (8, including `test_no_platform_draft_while_questions_open`) and 3 API tests in `test_policy_api.py`. 1266 tests pass, mypy clean, registry re-pinned (migration).

## Review log

### 2026-09-23 — independent agent review, round 1
- [x] met as worded — criteria 2, 3 and 4.
- [ ] blocking — criterion 1:
  - a free-text answer was recompiled with the instruction, and cross-sentence readers then dropped a stated rule. Example: "Buy from a sports shop … Decline when unsure." plus the answer "Buy clothing from a clothing shop. Approve when unsure." lost `merchant_category in [sporting_goods]`, and after an "Approve" option answer the draft reached ready with policy approve;
  - answers to already-closed questions were applied;
  - some questions raised by the unchanged instruction could never close.
- Also: `answerDraftQuestions` didn't document its 409/422 responses.
Verdict: returned to in-progress. Fixes:
- The result keeps every rule the instruction stated (the union with what answers add), so answers only add restrictions.
- A stated uncertainty choice is never asked again or changed by later words.
- Answers are replayed in order and each must answer a question open at that moment (otherwise 422).
- A free-text answer closes its question when it is itself fully readable and gives a rule for that field (or answers an "I'm not sure how to read" question), so no dead ends.
- The contract documents 409 and 422 for answers.
- 3 regression tests, including the reviewer's exact case.

### 2026-09-23 — independent agent review, round 2
- [x] met — criteria 2–4; every round-1 finding fixed. No sequence of answers gave a draft looser than the instruction's reading.
- [ ] not met — criterion 1:
  - an answer that conflicts with the instruction closed its question and was silently dropped (clothing vs groceries, pickup vs delivery, CHF 5000 vs 50);
  - a shop restriction from the customer's own unread sentence was only an optional question.
- Minor: "Yes" didn't answer "Is CHF 50.00 the most…?"; blank answers were stored.
Verdict: returned to in-progress. Fixes:
- Every readable rule of a free-text answer is checked against the instruction's own reading. One that adds nothing for a field the instruction limits, or leaves no allowed value, raises a blocking question: "Your answer … conflicts with your instruction for <field>: a draft can only add to what you wrote …". The original question stays open until a fitting answer arrives.
- Only the two offers of an extra restriction are optional (the "any kind of shop" offer and the split check).
- "Yes" confirms the amount as read, with free text still possible.
- Blank answers are refused (422).
- 5 regression tests, including the reviewer's three conflict cases; 1277 tests pass.

### 2026-09-23 — independent agent review, round 3
- [x] met — criteria 2–4; every round-1 and round-2 finding still fixed; no dead end found.
- [ ] not met — criterion 1: an answer could close its question without taking effect. Its rule came only from recompiling the whole text, and an ambiguous instruction made it vanish:
  - "Buy groceries… Buy clothing." answered "Buy clothing." reached ready with no item rule;
  - the same happened with delivery vs pickup;
  - answers contradicting earlier answers weren't checked;
  - a later "Decline when unsure." after choosing Approve was silently dropped;
  - an off-topic answer could close a conflict question.
Verdict: returned to in-progress. Fixes:
- Every accepted free-text answer also counts on its own: its readable rules join the union (instruction ∪ recompile ∪ answers), so a closed question's answer always takes effect.
- Conflicts are checked against everything so far (instruction, earlier answers, and a settled uncertainty choice). A conflicting answer is never used (not added to the recompiled text either) and raises a blocking question.
- A conflict question is closed only by an answer about its own field (an uncertainty conflict offers the three choices).
- 4 regression tests with the reviewer's cases.

### 2026-09-23 — independent agent review, round 4
- [x] met — criteria 2–4; every round-1 to round-3 finding still fixed; no stated restriction optional; no dead end.
- [ ] not met — criterion 1:
  - an option chosen on an uncertainty conflict question was dropped: the question left the lookup before its answer applied, so Decline stayed Approve;
  - a chosen catalogue item plus an item category it isn't in reached ready with rules no purchase can meet.
Verdict: returned to in-progress. Fixes:
- Answered conflict questions stay known (`resolved`), so their chosen option applies.
- A catalogue-aware check `_unsatisfiable` (an empty allowed set, or chosen items all excluded by the other item rules) runs inside the conflict check and again on the final draft. There it adds a blocking "Your rules can't all be met together…" question, so such a draft is never ready.
- The five public instructions are still ready. 2 regression tests; 1283 tests pass.

### 2026-09-23 — independent agent review, round 5
- [x] met — criteria 2–4; earlier findings still fixed.
- [ ] not met — criterion 1:
  - a chosen "Only X shops" option was lost after later answers, because its effect came from a recompile that no longer read the kind;
  - an answer that made the rules impossible on a field not yet limited was accepted, leading to a permanent "can't all be met" dead end;
  - "Should I buy only the item you chose…?" couldn't close for some items, and restating the chosen item changed the reading;
  - a restatement that settled nothing still changed the recompile.
Verdict: returned to in-progress. Root cause: recompiling instruction + answers as one text. Redesign:
- No recompile. The draft is the instruction's own reading ∪ each accepted answer read on its own ∪ option effects fixed when chosen.
- A free-text answer must answer its question: it must be fully readable (no unclear part, including "only the item you chose?") and give that question's field. Otherwise it is refused (422) with the reason, never half applied.
- Every answer is checked before it counts:
  - "adds nothing" applies only to fields already limited;
  - an answer that leaves no purchase possible is a conflict on any field;
  - so is a different uncertainty choice.
- Conflict questions offer "Keep what I had", which withdraws the unused answer so the original question can be answered again. An uncertainty conflict offers only choices at least as strict as the settled one.
- "Should I buy only the item you chose…?" offers "Only the item I chose".
- A base question closes once an accepted answer gives its field.
- 9 new or updated regression tests. The five public instructions are still ready. 1291 tests pass, mypy clean.

### 2026-09-23 — independent agent review, round 6
- [x] met — criteria 2–4. All round 1–5 findings are still fixed. A fuzzer (750 answer walks) and a dead-end probe (20 instructions) found no looser draft, no dropped answer, no impossible draft reaching ready and no dead end.
- [ ] not met — criterion 1: two gaps, both erring toward caution:
  - answering "which one applies?" (CHF 50 vs CHF 40) with the already-read but overridden "At most CHF 50" closed the question with no effect;
  - an answer whose own uncertainty wording is contradictory ("Approve when unsure. Ask me when unsure.") was accepted and that part dropped.
Verdict: returned to in-progress. Fixes:
- An answer rule that is already present but overridden by a stricter one (removing it changes nothing) is a conflict: it can't apply.
- An answer that states an uncertainty choice but raises an uncertainty question of its own is refused as unclear.
- Kept as intended: a restatement of a binding rule answers "not sure how to read …". The customer says what the sentence meant, and that rule already holds.
- 2 regression tests. The reviewer's fuzzer and dead-end probe are clean again. 1293 tests pass, mypy clean.

### 2026-09-23 — independent agent review, round 7
- [x] met — criteria 2–4. Every round 1–6 finding is still fixed. No looser draft and no loosened uncertainty choice in 750 new fuzz walks.
- [ ] not met — criterion 1:
  - G1: an option ("Only groceries shops") could make the rules impossible without the conflict check, so the customer hit a "can't all be met" dead end;
  - G2: a spending limit at or below CHF 0 reached ready;
  - G3: a blocking question about another amount the customer wrote (CHF 100) closed on its own when an answer gave the same field, and that limit vanished;
  - G4: an answer's own unclear shop or item wording was treated as filler and dropped (half applied).
Verdict: returned to in-progress. Fixes:
- G1: an option's rule goes through the same conflict check as free text. A clash is a conflict question with "Keep what I had".
- G2: `_unsatisfiable` also catches a billing limit that no positive amount can meet (`< 0`, or `<`/`<=` 0).
- G3: only questions asking for missing items or shops (no quoted customer words) close when another answer gives their field.
- G4: an answer's own question counts as filler only if it is optional or is one of the questions any short answer raises (for example "What kind of items may I buy?"). Anything else, including the answer's own shop or item doubts, makes it unclear, so it is refused.
- 7 regression tests with the reviewer's inputs. Both reviewers' fuzzers (rounds 6 and 7) find 0 issues. Both dead-end probes only flag the self-contradicting instruction, whose exit is a new draft. The five scenarios are ready. 1300 tests pass, mypy clean.

### 2026-09-23 — independent agent review, round 8
- [x] met — criteria 2–4. Earlier findings are still fixed, except that G4 was only partly fixed. No looser draft, no loosened settled uncertainty choice.
- [ ] not met — criterion 1:
  - H1: an answer whose sentences cancel each other out ("For delivery. Buy clothing. Buy books.") was accepted with only the delivery rule, because the compiler's "What kind of items may I buy?" looked like a default question.
  - H2: `< CHF 0.01` (per order or per period) reached ready.
  - H3: a dead end. After "Buy books." for an unknown item, a book item couldn't be named: the category word inside the item's own name ("paperback book order") raised "only the item you chose, or also other kinds?".
- Minor: the contract example answered `'yes'` (a 422), and the 422 description left out refused free-text answers.
Verdict: returned to in-progress. Fixes:
- H1: every sentence of an answer is also read alone. If one gives a rule that the whole answer loses, the answer is refused as unclear, naming those parts.
- H2: a billing limit that CHF 0.01 can't meet is impossible (`<= x` with x < 0.01, `< x` with x ≤ 0.01).
- H3 (compiler): the chosen item's own name is ignored when looking for other item kinds. "Buy the monitor I chose and some books" still asks.
- The contract example now answers `Yes`, and the 422 description lists every refusal. App types regenerated.
- 7 regression tests (6 in clarify, 1 in the compiler).
- Fuzzing with the reviewer's seeds shows no DEAD_END and no READY_NO_POSITIVE_CENT. The remaining fuzz flags are the kinds the reviewer called intended: restating the binding value, and a policy stated for an unread sentence.
- 1307 engine tests and 68 app tests pass; mypy clean; the five scenarios are ready.

### 2026-09-23 — independent agent review, round 9
- [x] met — criteria 2–4. Findings from rounds 1–8 are fixed for their reported inputs. The fuzzers show no looser draft, no dropped answer, no impossible ready draft, and no real dead end (fuzz3's "Replace my shoes…" flags close with items outside its pool).
- [ ] not met — criterion 1, gap I1: an answer naming two item kinds in one sentence ("For delivery, clothing and books.", "At most CHF 40 per order, groceries and cosmetics.") was accepted with only its other rules. The compiler asked the generic "What kind of items may I buy?", which is also what any short answer raises, so it counted as filler. The round-8 sentence check didn't split on commas or "and".
Verdict: returned to in-progress. Root fix in the compiler:
- When it reads item kinds it can't settle (several, or negated), the question now names what it read ("What kind of items may I buy? I read books, clothing, which isn't one kind I can limit to.").
- The generic question is added only when no item question was asked.
- So an answer raising it is never mistaken for "no items given": it is refused as unclear.
- 5 regression tests (4 with the reviewer's inputs, 1 in the compiler).
- fuzz4 (seed 1, 400) and earlier fuzzers: 0 issues. 1312 tests pass, mypy clean, the five scenarios are ready.

### 2026-09-23 — independent agent review, round 10
- [x] met — criteria 2–4. Every round 1–9 finding is still fixed. New fuzz runs show no looser draft, dropped answer, impossible ready draft, dead end or crash.
- [ ] not met — criterion 1, gap J1: "shoes" and "running shoes" count as understood by the grammar, but no reader turns them into a rule. So "Buy groceries and shoes." was accepted as groceries only, and "At most CHF 100 per order. Buy running shoes." on a clothing instruction reached ready with no conflict.
Verdict: returned to in-progress. Fix (compiler): shoes span two catalogue categories (running shoes are sporting goods, work shoes are clothing), so a shoe mention outside a chosen item is never a single kind. It raises the named question "What kind of items may I buy? I read …: shoes…", and the answer is refused as unclear. A chosen shoe item (SCEN0002, "the road-running shoes I chose") is unaffected. 7 regression tests (4 clarify with the reviewer's inputs, 3 compiler). Fuzzers: 0 issues outside the accepted design. 1319 tests pass, mypy clean, the five scenarios are ready.

### 2026-09-23 — independent agent review, round 11
- [x] met — criteria 2–4. Every round 1–10 finding is still fixed. Fuzz runs: nothing outside the accepted design.
- [ ] not met — criterion 1, gap K1. A sweep of every item phrase the grammar accepts found one word no reader turned into a rule: "household" (a catalogue category with 3 items, allowed by the grammar only as a modifier). So "At most CHF 100 per order. Buy household items." was accepted with no conflict on a clothing instruction, and "Buy groceries and household items." was half applied. The same cause silently dropped household from an instruction.
Verdict: returned to in-progress. Fix (compiler): "household" is its own kind ("household items"), except directly before another kind, where it only describes it ("our household groceries", SCEN0001). "household" is also a merchant category, so the "Only household shops" offer is valid.
- 6 regression tests: 5 in clarify with the reviewer's inputs, 1 in the compiler, including SCEN0001's modifier.
- The reviewer's sweeps flag nothing about household. The remaining NO_EFFECT flags restate the binding kind or use generic "items".
- Fuzzers show nothing outside the accepted design. 1325 tests pass, mypy clean, the five scenarios are ready.

### 2026-09-23 — independent agent review, round 12
- [x] met — criteria 2–4. Every round 1–11 finding is still fixed, including the round-11 sweeps. The fuzzers show nothing outside the accepted design.
- [ ] not met — criterion 1, gap L1: the round-10 shoe check ran only when no item was chosen. So "Buy the 27-inch monitor I chose and running shoes." was accepted with the monitor only, and "Buy the paperback I chose. Buy running shoes." reached ready without asking. A sweep of every accepted item phrase next to a chosen item flagged 72 inputs, all of them shoe phrases.
Verdict: returned to in-progress. Fixes:
- (compiler) a shoe mention outside the chosen item's own name raises the blocking "Should I buy only the item you chose, or also other kinds of items?", like the other kinds do. SCEN0002's "my worn road-running shoes" is the item's own name and is unaffected.
- The named item question now reads "What kind of items may I buy? I read …, which isn't one kind I can limit to." (it also covers a single word like shoes).
- 3 regression tests with the reviewer's inputs.
- Checks: `sweep_itemmode.py` flags 0 inputs, and fuzz2/fuzz4 find 0 issues. fuzz3's one dead-end flag ("Replace my shoes…") closes with a grocery item outside its pool ("Buy the pantry staples I chose." → ready). 1328 tests pass, mypy clean, the five scenarios are ready.

### 2026-09-23 — independent agent review, round 13
- [x] met — criteria 2–4. Every round 1–12 finding is still fixed.
- Exhaustive sweeps found no looser reading, no dropped or half-applied answer, no impossible ready draft, no dead end and no loosened settled choice:
  - 996k instructions: every accepted item phrase, pair, and phrase next to a chosen item;
  - 2.24M answers to 7 base questions.
- [ ] not met — criterion 1, gap M1: a kind matching the chosen item's category, given as the answer to "Should I buy only the item you chose, or also other kinds?" ("Buy books." for a chosen paperback), was accepted. The question closed although the kind rule changes nothing next to `item_id`, so the customer's "also books" was silently not honoured. The sweep counted 9,480 such answers.
Verdict: returned to in-progress. Fix:
- In `_clashing_rule`, an `item_category` rule next to a chosen item is always a conflict: it either excludes the item (already a conflict) or adds nothing; it can never widen.
- The customer gets the conflict question with "Keep what I had", then can answer "Only the item I chose", or start a new draft for other kinds.
- 5 regression tests with the reviewer's inputs.
- Checks:
  - `sweep_ans.py` C1 NO_EFFECT dropped from 9,747 to 267, all restating the chosen item (optionally with generic "items"), the same as C2;
  - fuzz2 and fuzz4: 0 issues;
  - fuzz3's "Replace my shoes…" dead-end flag closes with a clothing item ("Buy the work shoes I chose." → ready);
  - 1333 tests pass, mypy clean, the five scenarios are ready.

### 2026-09-23 — independent agent review, round 14
- [x] met — criterion 1: no gap found.
  - The round-13 change creates no dead end. Every chosen item × 7 kinds in both orders reaches ready. All 246,268 conflicts on the sweep bases offer "Keep what I had", which reopens the question and leaves the rules unchanged.
  - A 2-answer reachability search over 70 item+kind instructions flagged 492 states; all 492 close once an item of the matching kind is in the answer pool.
  - The round-13 sweeps give the same counts, all accepted design. The fuzzers show 0 issues outside the accepted design.
  - R1–R6 and G–M findings are still fixed on their reported inputs.
- [x] met — criterion 2: submit returns 409 `questions_open` unless ready; nothing is posted.
- [x] met — criterion 3: submit returns the stored posted body on every repeat; confirm activates that draft.
- [x] met — criterion 4: confirm is idempotent (claim window, `confirmed_mandate_id`).
- Checks: 1333 tests pass, mypy clean, the five scenarios are ready.
Verdict: all criteria met. Moved to done on the product owner's standing instruction for this run.
