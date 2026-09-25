# LEASH-174: The model reads, deterministic code validates and renders

**Status**: ONGOING
**Priority**: P0
**Type**: feature
**Estimated Effort**: L
**Milestone**: M8 — Great demo
**Rule source**: Product (2026-09-25 decision)
**Decisions**: DEC-045, DEC-033, DEC-035, DEC-036, DEC-044
**Pattern**: Anti-corruption layer (model output validated at the edge) + Interpreter (rule → sentence)
**Parent**: LEASH-008
**Task ID**: 008-T8
**Blocked by**: LEASH-101
**Blocks**: none
**Updated**: 2026-09-25

## Description
Today a proposed rule survives only if the deterministic compiler independently reads the customer's
words the same way. Measured on 2026-09-25, that grammar reads almost nothing a customer would
actually type: `höchstens CHF 50 pro Bestellung`, `au plus CHF 50 par commande` and
`al massimo CHF 50 per ordine` produce no rule, `"only electronics"` is refused as an answer, and
`buy me a jacket, at most CHF 120 this week` cannot be read as a whole. Only amount phrasings in
English reliably compile.

Under DEC-045 the model does the reading, in any language, and returns a structured rule. Deterministic
code then does three things and only these three:

1. **Validates** against the policy registry — the field exists, the operator is one that field
   permits, the value's type and magnitude are legal. No natural-language parsing.
2. **Renders** the sentence the customer approves *from the rule object*, so the wording can never
   drift from what will be enforced.
3. **Enumerates what is unrestricted** — the registry fields with no rule — which is the only defence
   against a restriction the model silently dropped.

The customer's agreement to the rendered sentence is what creates the rule. After confirmation the
existing freeze applies unchanged: append-only, tighten-only, snapshot per run.

## Business Value
A customer can state a permission in their own words and their own language and have it enforced.
Today they must speak the compiler's English grammar or answer fixed options.

## Acceptance Criteria
- [x] A structured rule from the model is accepted on registry validation alone; no re-derivation from
      the instruction text is required for it to reach review.
- [x] `höchstens CHF 50 pro Bestellung`, `au plus CHF 50 par commande` and `al massimo CHF 50 per ordine`
      each produce the same rule as `at most CHF 50 per order` (`billing_amount_chf <= 50`, scope purchase).
- [x] A rule whose operator the field does not permit is refused with its reason, never stored
      (edge case: `billing_amount_chf >= 50` — a minimum is not expressible).
- [x] A value that is not a legal `Decimal`, or is absurd in magnitude, is refused (edge case: `NaN`).
- [x] The consent sentence is generated from the `Rule` object. A test asserts that changing the rule
      changes the sentence, and that no model-supplied string reaches it.
- [ ] The rendered sentence is what the confirmation records; the model's prose is stored as provenance
      only, clearly labelled as the model's wording.
- [ ] A rule that would loosen an active mandate is refused before it is ever shown (DEC-006).
- [x] `says` stays a gate, unchanged: a rule must quote the customer's own words verbatim, from the
      turn it names, and the quote must carry the value. Softening it was tried and reverted — it lets a
      background preference become a candidate rule (DEC-034), and it is not what excluded German.
- [x] Corroboration by the compiler is recorded per rule, not required — except where the compiler read a
      *different* rule for the same field, which stays a question (edge case: model reads CHF 500 where the
      compiler reads CHF 50).
- [x] The draft reports every registry field left unrestricted, by field name, for LEASH-146 to render.
- [x] Nothing in the decision path changes: the scenario replay's 45 verdicts are byte-identical.

## Technical Approach
`solution/assistant/agent.py` (validation becomes registry-only; the quote check becomes provenance),
`solution/engine/src/leash/policy/registry.py` (validation entry point),
`solution/engine/src/leash/policy/compiler.py` (keep `Reading`'s sentence generation, retire the text
parsing that feeds it), `solution/assistant/conversation.py` (`_check` no longer requires the compiler
to have derived the same rule). The compiler's question generation for *unset* fields is kept and
becomes the unrestricted-fields list.

### Dependencies
- Needs LEASH-101 (a human still has to accept the current chat before it is rebuilt on top of).
- Feeds LEASH-146: the renderer produces the review's sentences and the unrestricted-fields list.
- Feeds LEASH-155: omission checking is now a required control, not an optional enhancement.

## Testing Requirements
Write first: `test_a_german_instruction_produces_the_same_rule_as_english`,
`test_an_operator_the_field_forbids_is_refused`, `test_the_consent_sentence_comes_from_the_rule_not_the_model`,
`test_an_unquoted_candidate_is_kept_but_marked`, `test_the_draft_lists_unrestricted_fields`.
Run `uv run pytest ../assistant/tests -q` then the full engine suite, including scenario replay.

## Related Files
- `solution/assistant/agent.py`
- `solution/assistant/conversation.py`
- `solution/engine/src/leash/policy/compiler.py`
- `solution/engine/src/leash/policy/registry.py`
- `solution/engine/tests/policy/`

## Out of scope
- Rendering the review screen itself (LEASH-146).
- The omission check (LEASH-155).
- Translating the rendered sentences (presentation, not authority) — a separate ticket when a language
  other than English is actually shown.
- Any change to `decide()`, the rules, or the checkout path.

## Review log

### 2026-09-25 — independent agent review: 8 of 11 met, two not met, one hole found

**The hole I asked the reviewer to hunt for is real, and they reproduced it twice.** `_fully_read`
suppresses the compiler's unreadable-sentence warning when the model's quote covers the whole
sentence — and `says` is not always a fragment: `_customer_excerpt`'s `_restated`/`_value_anchor`
expand it to the customer's whole sentence, and a model may quote the whole sentence anyway. So
`Buy me a jacket, at most CHF 120 per order, and no subscriptions.` returns **no questions at all** and
"no subscriptions" disappears without a trace; the German equivalent loses "keine Abos" the same way.
Neither net catches it: a sentence the grammar rejected yields no compiler rule to be "missing", and
"no subscriptions" maps to no registry field, so the unrestricted list cannot see it either. Before
this change all four cases were asked about. **Not fixed here** — `agent.py` is currently owned by the
LEASH-176 session, whose `_customer_excerpt` expansion is half the cause, and whose `clarify.py`
suppression (DEC-056, still Proposed) has the same hole more permissively on the service side. Handed
to them with both reproductions rather than edited underneath them.

**Not met — criterion 6.** Model prose is neither provenance-only nor labelled: strings in
`reply["questions"]` become `Question(q)` with `field=None` and reach the customer verbatim,
indistinguishable from our own deterministic questions. The new test only asserts the prose stays out
of `consent_text`; it never checks where it does go. Nothing records the rendered sentence at
confirmation either.

**Not met — criterion 7.** The loosening check exists and is unit-tested, but nothing supplies it:
`clarify(..., active=...)` has no caller anywhere in the repo, so through the running service a
loosening rule becomes a candidate and IS shown. The engine still refuses it at `/tighten`, so the
non-negotiable holds; "before it is ever shown" does not. Pre-existing at HEAD, not a regression.

**Criterion 2 is met but its headline test is partly circular** — the stub is handed the finished rule,
so `same rule as English` is true by construction. What it does prove non-circularly is the assertion
above it (`questions == ()`), which fails on the pre-change code. No real-model evidence anywhere.

Criterion 11 verified independently: `evals/baseline.json` untouched, replay and fingerprint tests
pass, full engine suite 1681 passed / exit 0.
