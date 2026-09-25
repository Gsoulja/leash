# LEASH-146: Human-readable permission review

**Status**: REVIEW
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M8 — Great demo
**Rule source**: Product
**Decisions**: DEC-033, DEC-034, DEC-035, DEC-036, DEC-037, DEC-045
**Parent**: LEASH-144
**Task ID**: 144-T2
**Blocked by**: LEASH-145
**Blocks**: LEASH-147, LEASH-153, LEASH-156
**Updated**: 2026-09-25

## Description
Turn the confirmation step into a concise customer contract instead of repeating rules, notes, decision codes and raw platform expressions.

## Business Value
The customer and the audience must understand exactly what will be allowed before activation without learning internal vocabulary.

## Acceptance Criteria
- [x] The primary review groups boundaries under item, price, merchant, frequency and uncertainty headings.
- [x] Repeated rule and note text appears only once.
- [x] `DEC-*`, catalogue IDs, draft IDs and raw rule expressions are hidden from the default view.
- [x] An “Advanced details” disclosure contains the exact platform payload for technical verification.
- [x] Open optional questions are summarized as explicit customer choices, not sent silently.
- [x] “Activate permission” remains visible with a concise statement of effect.
- [x] Confirmation produces an agent message explaining the next action.
- [x] The review exposes Must follow / May choose / Must ask, with item selection versus delegated choice, amount/currency/fees, quantity/frequency and uncertainty scope explicitly represented.
- [x] The primary review is deterministically derived from the exact submitted hard_rules and uncertainty policy. Every enforced restriction is represented; no separate LLM summary supplies consent text.
- [x] The review names every registry field left **unrestricted**, in plain words, as its own part of
      "May choose". Under DEC-045 this is the only thing standing between a restriction the model
      silently dropped and a frozen mandate, so it is required, not decorative.
- [x] Every sentence shown is generated from the `Rule` object (LEASH-174's renderer); no model prose
      is used as consent text.
- [x] Profile suggestions and team interpretations are identified and adopted explicitly; unresolved material choices block activation and unsupported guarantees are never labelled enforceable.
- [x] Confirm submits the exact reviewed revision identifier; a changed revision invalidates the action and requires another review. Show the effect of changes without silently changing active mandates.
- [x] The customer can inspect why a condition exists and its source answer without exposing unrelated history. A purchase-specific uncertainty answer is visually distinct from changing ongoing permission.

## Technical Approach
Create a deterministic display projection of the exact versioned `HardRule` payload and uncertainty policy, using the registry’s meanings. Preserve the exact payload in an expandable evidence section; test one-to-one coverage so human wording cannot drift from enforcement.

### Dependencies
- Needs LEASH-145.
- Blocks LEASH-147.
- Blocks LEASH-153.
- Blocks LEASH-156.

## Testing Requirements
Add tests proving internal identifiers are absent before expanding advanced details, every enforced boundary appears exactly once, currency/fee/scope semantics match the payload, suggested preferences require adoption, and stale-revision confirmation is rejected.

## Related Files
- `solution/app/src/screens/Agent.tsx`
- `solution/app/src/api/client.ts`

## Out of scope
- Removing exact platform evidence from the application entirely.

## What landed (2026-09-25)

Engine — `policy/render.py`:
- `permission_review` returns `{text, group}` lines instead of bare strings; `GROUPS` is the reading
  order (item, price, merchant, frequency, uncertainty) and `group_of` places every registry field.
- `choice_label` names every registry field in plain words, and `may_choose` is built from `REGISTRY`
  itself, so a field added later cannot drop out of the unrestricted list unseen (DEC-045).
- `_once` dedupes each section: one boundary is read back once.
- An item-id rule reads as "Only the exact product you chose." The catalogue id stays in the payload.
  Caveat: the ids are dropped, not translated — a two-product allowance does not name the products in
  the sentence. Naming them needs the catalogue passed into the renderer.

Engine — `application/clarify.py`: `_rule_views` strips ` (DEC-013)` from the sentence and keeps the
code on `decision`. The app shows provenance from that field, so a decision code can no longer reach
the default view through a note.

Contract: `ReviewLine` with the group enum; `PermissionReview` documents why `may_choose` carries the
unrestricted fields. `app/src/api/schema.d.ts` regenerated.

App:
- `PermissionSummary` renders sub-headings per group and is now used by the Agent review card too,
  which had its own copy of the three lists.
- The review card gained an "Advanced details" disclosure holding the platform draft id, the exact
  `hard_rules` and the raw uncertainty policy — the default view has none of them.
- Optional open questions read as "Choices you left to me" with what leaving them open means.
- Confirmation is a message from Leash saying what happens next.
- `ruleSource` no longer appends the decision code.
- StepUp says an answer covers that payment only, not the standing permission.

Tests: `engine/tests/policy/test_render.py` (grouping, every field grouped and labelled, every field
named in `may_choose`, no catalogue id, no boundary twice), `engine/tests/application/test_clarify.py`
(a rule reads without our decision code), `app/src/screens/Agent.test.tsx` (headings, identifiers not
visible until Advanced details, choices left open, confirmation message), `app/src/screens/StepUp.test.tsx`.

Not covered by this ticket: an independent review against these criteria, and the end-to-end evidence
that LEASH-156 collects.
