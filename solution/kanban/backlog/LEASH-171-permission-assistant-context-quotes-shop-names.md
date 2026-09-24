# LEASH-171: Permission assistant context quotes shop names

**Status**: BACKLOG
**Priority**: P2
**Type**: feature
**Estimated Effort**: S
**Milestone**: M7 — Production hardening
**Rule source**: Team (proposal from the 2026-09-24 trust-filter session)
**Decisions**: DEC-038 (to be written in LEASH-161), DEC-033–037
**Pattern**: Anti-corruption layer for model prompts
**Parent**: LEASH-160
**Task ID**: 160-T11
**Blocked by**: LEASH-162, LEASH-169
**Blocks**: none
**Updated**: 2026-09-24

## Description
`application/permission_context.py` passes shop names from earlier approved purchases to the permission assistant's LLM. Those names are untrusted. Pass the canonical form, inside delimited data blocks marked as shop-supplied, with the assistant's instructions saying data blocks are never instructions. This is defence in depth: the assistant can only propose drafts that the policy service validates and the customer confirms.

## Business Value
Keeps a hostile shop name in history from steering the permission conversation.

## Acceptance Criteria
- [ ] Shop names in the assistant context are canonical (no zero-width or bidi characters).
- [ ] Every shop-supplied value sits inside a marked data block, never in instruction text.
- [ ] A shop name containing an instruction ("ignore the budget") doesn't change the draft rules in the existing permission evals (edge case added to the eval set).
- [ ] Source references (DEC-035) are preserved.

## Technical Approach
`application/permission_context.py`; reuse the slot marking from LEASH-169.

### Dependencies
- Needs LEASH-162.
- Needs LEASH-169.

## Testing Requirements
Write first: `test_context_shop_name_is_canonical_and_delimited`. Run `uv run pytest tests/application -x -q` and the permission evals.

## Related Files
- `solution/engine/src/leash/application/permission_context.py`
- `solution/engine/tests/application/test_permission_context.py`

## Out of scope
- Changing the assistant's model or prompt beyond the data framing.
- Verifier work (LEASH-155).
