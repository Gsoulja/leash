# LEASH-146: Human-readable permission review

**Status**: BACKLOG
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M8 — Great demo
**Rule source**: Product
**Decisions**: DEC-033, DEC-034, DEC-035, DEC-036, DEC-037
**Parent**: LEASH-144
**Task ID**: 144-T2
**Blocked by**: LEASH-145
**Blocks**: LEASH-147, LEASH-153, LEASH-156
**Updated**: 2026-09-24

## Description
Turn the confirmation step into a concise customer contract instead of repeating rules, notes, decision codes and raw platform expressions.

## Business Value
The customer and the audience must understand exactly what will be allowed before activation without learning internal vocabulary.

## Acceptance Criteria
- [ ] The primary review groups boundaries under item, price, merchant, frequency and uncertainty headings.
- [ ] Repeated rule and note text appears only once.
- [ ] `DEC-*`, catalogue IDs, draft IDs and raw rule expressions are hidden from the default view.
- [ ] An “Advanced details” disclosure contains the exact platform payload for technical verification.
- [ ] Open optional questions are summarized as explicit customer choices, not sent silently.
- [ ] “Activate permission” remains visible with a concise statement of effect.
- [ ] Confirmation produces an agent message explaining the next action.
- [ ] The review exposes Must follow / May choose / Must ask, with item selection versus delegated choice, amount/currency/fees, quantity/frequency and uncertainty scope explicitly represented.
- [ ] The primary review is deterministically derived from the exact submitted hard_rules and uncertainty policy. Every enforced restriction is represented; no separate LLM summary supplies consent text.
- [ ] Profile suggestions and team interpretations are identified and adopted explicitly; unresolved material choices block activation and unsupported guarantees are never labelled enforceable.
- [ ] Confirm submits the exact reviewed revision identifier; a changed revision invalidates the action and requires another review. Show the effect of changes without silently changing active mandates.
- [ ] The customer can inspect why a condition exists and its source answer without exposing unrelated history. A purchase-specific uncertainty answer is visually distinct from changing ongoing permission.

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
