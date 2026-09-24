# LEASH-177: Instruction compiler reads zero rules from "buy me nike running shoes size 44 up to 40 CHF"

**Status**: BACKLOG
**Priority**: P1
**Type**: bug
**Estimated Effort**: M
**Milestone**: M8 — Permission conversation, context, external-agent handoff
**Rule source**: Found via `POST /api/policies/drafts` with `{"instruction":"buy me nike running shoes size 44 up to 40 CHF"}` (2026-09-24)
**Decisions**: none
**Parent**: LEASH-174
**Task ID**: 174-T3
**Blocked by**: none
**Blocks**: none
**Updated**: 2026-09-24

## Description
`POST /api/policies/drafts` with `{"instruction":"buy me nike running shoes size 44 up to 40 CHF"}` returns `rules: []`, `hard_rules: []` and six generic clarification questions, including two different `question_id`s carrying the exact same text (`Please confirm what "buy me nike running shoes size 44 up to 40 CHF" means for this rule.`) — no size, no amount, no item category is read, even though all three are stated plainly.

**No model is involved, and none should be at this endpoint yet.** `create_draft` (`adapters/http/policy_api.py:108-115`) calls `clarify(...)` directly, which runs `policy/compiler.py`'s deterministic `compile_instruction` (LEASH-065, regex only) — confirmed by reading the code path, not assumed. LEASH-101 does add an LLM-powered permission assistant, but it is a separate component (`solution/assistant/`) that is **not wired to this route**: its own review log states "nothing imports `assistant.agent` except its own tests" and "no LLM is configured in this environment," and CLAUDE.md still lists model choice as an open decision. So the absence of a model here is expected, current behaviour, not the bug — the bug is that the deterministic compiler itself mis-reads a plain instruction.

**Reproduced directly against `policy/compiler.py`** (no HTTP/DB needed):

```python
compile_instruction("buy me nike running shoes size 44 up to 40 CHF")
# -> rules=(), only the generic fallback questions
```

Root cause: `_understood()` requires the **entire** sentence to fully match the fixed phrase grammar built by `_grammar()` — if any single word breaks the match, the whole sentence is discarded and none of its readers (`_amounts`, `_sizes_and_days`, `KeywordClassifier`) ever run on it, even for the parts that are individually well-formed. Three independent, narrow gaps in that phrase grammar, any one of which alone already zeroes the whole sentence:

1. **"buy me" is not a recognized opener.** `_PHRASES[0]` is `(?:the agent may |please )?(?:buy|order|purchase)(?: only)?` — "buy" matches, but "buy me" does not (confirmed: `"buy running shoes"` → matches; `"buy me running shoes"` → does not).
2. **A brand or other qualifier before a category noun is not recognized.** The item-phrase entries only allow a small fixed prefix list (`ordinary|household|our|some`) before `shoes`/`clothes`/etc. — `"nike"` is not in it (confirmed: `"buy running shoes"` → matches; `"buy nike running shoes"` → does not), even though the classifier's own `_SHOES` regex would happily read "shoes" out of that same text once past the grammar gate.
3. **"size 44" without a leading "in" is not recognized**, even though the actual size reader (`_SIZE` regex in `_sizes_and_days`) matches bare `"size 44"` just fine once it gets to run (confirmed: `"buy running shoes in size 44"` → matches; `"buy running shoes size 44"` → does not).

The reported instruction trips all three at once, so it reads as fully unparseable text instead of partially-understood-plus-one-question (e.g. a size and an amount read cleanly, with only "nike" and "buy me" prompting a clarification).

The duplicate-text-different-`question_id` pair is a direct symptom of the same failure: once a sentence is rejected outright, `compile_instruction` appends one generic "I'm not sure how to read ..." question, then loops `_CUES` and appends a second, identically-worded "Please confirm what ... means for this rule" for every cue keyword it still finds in the same rejected sentence (here: an amount cue and a size cue) — so the customer sees the same quoted sentence "confirmed" twice for no additional information.

## Business Value
"Buy me X" is among the most natural ways to phrase a purchase instruction, and named brands are how real customers describe what they want (a demo scenario asking for "Nike running shoes" is exactly this shape). Losing 100% of a plainly-stated size and price limit to a single unrecognized word means the permission-drafting flow devolves into unhelpful, repetitive clarification for common phrasing — directly undermining the "clarifies customer intent" goal in LEASH-101/CLAUDE.md.

## Acceptance Criteria
- [ ] `compile_instruction("buy me nike running shoes size 44 up to 40 CHF")` reads a `leash.items.size.v1 = 44` rule and a `authorization.billing_amount_chf <= 40.00` (scope `purchase`) rule; only the item-category/brand part may still raise a clarifying question (since "nike running shoes" isn't a catalogue-backed item and isn't one of the fixed `_ITEM_TYPES` categories).
- [ ] "Buy me X" is read the same as "Buy X" for every existing phrase the grammar already accepts (no regression to any of the sentences `_PHRASES` currently matches).
- [ ] A bare `"size 44"` (no leading "in") is read the same as `"in size 44"`.
- [ ] The compiler never emits two questions with identical text for two different `question_id`s from the same unrecognized sentence; each distinct cue gets one question, or the sentence gets exactly one fallback question, not both worded identically.
- [ ] No existing replay test, property test, or `test_compiler.py`/`test_clarify.py` case changes its read rules or questions (this only adds recognition, per LEASH-065's own conservative rule: never read a looser or different rule than before, only fewer needless questions).

## Technical Approach
`solution/engine/src/leash/policy/compiler.py`:
- `_PHRASES[0]`: add "me" as an optional token after "buy" (`(?:buy|order|purchase)(?:\s+me)?(?: only)?`), mirroring the existing `(?:the agent may |please )?` optional-prefix pattern.
- Item-phrase prefixes (the `(?:ordinary |household |our |some )*` groups feeding `_ITEM_TYPES`/`_SHOES` words): allow one bare adjective/brand token before the recognized category noun, without letting it absorb words that change meaning (a brand token must not itself contain a negation, amount, or period word — reuse `_SPAN_STOP`-style exclusion, not an open wildcard).
- The `in size N` phrase entry: make `in ` optional, matching the actual `_SIZE` regex's own leniency.
- The duplicate-question fix belongs in `compile_instruction`'s fallback-question loop (around line 589-593): suppress a `_CUES` "Please confirm ..." question whose text is byte-identical to another question already queued for the same sentence.

Keep the "understood" gate a grammar, not a word list, per LEASH-065's review notes — the fix is to widen specific phrase entries, not to relax `_understood()`'s all-or-nothing matching, so the conservative safety property (a rule is never invented from ambiguous wording) is unaffected.

### Dependencies
- None; self-contained in `policy/compiler.py`. Relates to LEASH-065 (built this compiler) and LEASH-101 (the consumer that made this visible), but blocks neither.

## Testing Requirements
Write first: `test_buy_me_is_read_the_same_as_buy`, `test_brand_qualified_item_still_reads_its_category`, `test_bare_size_number_is_read_without_leading_in`, `test_unresolved_sentence_never_produces_duplicate_question_text`. Run `uv run pytest solution/engine/tests/policy -x -q` and the full replay suite to confirm no existing read changes.

## Related Files
- `solution/engine/src/leash/policy/compiler.py`
- `solution/engine/tests/policy/test_compiler.py`

## Out of scope
- Adding a general brand/product catalogue lookup for arbitrary item names — "nike running shoes" without a catalogue match still becomes a clarifying question about item category, exactly as today.
- Wiring the LLM-powered assistant (LEASH-101) into `/api/policies/drafts` — that endpoint stays deterministic-only; this ticket only fixes what the deterministic compiler itself should already be able to read.
