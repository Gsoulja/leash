# LEASH-080: Adversarial loop

**Status**: BACKLOG
**Priority**: P2
**Type**: feature
**Estimated Effort**: M
**Milestone**: M6 — Differentiators (after MVP)
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-006
**Task ID**: 006-T11
**Blocked by**: LEASH-077
**Blocks**: none
**Updated**: 2026-09-23

## Description
Rounds of attacker-LLM variants of missed attacks, with benign twins, added to training; stop after 3–4 rounds or when misses stop falling.

## Business Value
Hardens the reader where it is weakest.

## Acceptance Criteria
- [ ] Each round logs miss rate on fresh variants.
- [ ] Adversarial data capped at 20% of the mix.
- [ ] Held-out family never used.

## Technical Approach
`training/adversarial.py`.

### Dependencies
- Needs LEASH-077.

## Testing Requirements
Write first: `test_round_excludes_held_out_family`.

## Related Files
- `solution/training/adversarial.py`
- `solution/training/tests/test_adversarial.py`

## Out of scope
- Training the attacker model.
