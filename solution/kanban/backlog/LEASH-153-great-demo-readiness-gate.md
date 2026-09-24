# LEASH-153: Great-demo readiness gate

**Status**: BACKLOG
**Priority**: P0
**Type**: test
**Estimated Effort**: S
**Milestone**: M8 — Great demo
**Rule source**: Product
**Decisions**: none
**Parent**: LEASH-144
**Task ID**: 144-T9
**Blocked by**: LEASH-101, LEASH-133, LEASH-145, LEASH-146, LEASH-147, LEASH-148, LEASH-149, LEASH-150, LEASH-151, LEASH-152
**Blocks**: LEASH-128
**Gate**: DECISION — a person unfamiliar with the implementation can explain the agent, the protection and the outcome after one rehearsal.
**Updated**: 2026-09-24

## Description
Run the complete presentation from a clean reset and approve it only when the agent story is understandable, reliable and timed.

## Business Value
Feature completeness is not demo readiness; the audience must see the agent act and understand Leash's value without engineering narration.

## Acceptance Criteria
- [ ] The served build revision matches the source selected for the demo.
- [ ] Reset produces the documented clean baseline on the first attempt.
- [ ] The presenter completes instruction, clarification, activation, live run, customer intervention and final summary within the time budget.
- [ ] The agent visibly works; no silent wait exceeds the approved threshold.
- [ ] Cockpit, Agent summary and payment details agree on counts, outcomes and spending.
- [ ] No internal scenario IDs, decision codes or raw rule syntax appear in the primary customer journey.
- [ ] The LLM is demonstrably limited to shopping chat and draft generation; the deterministic control layer remains authoritative.
- [ ] A network interruption or accidental refresh has a rehearsed recovery path.
- [ ] Projector text is readable and all primary controls remain keyboard accessible.
- [ ] Two observers unfamiliar with the code correctly explain what was allowed, what was blocked and why.
- [ ] The final evidence bundle contains the script, recording, screenshots, timings and known fallback plan.

## Technical Approach
Use a fixed rehearsal script and scoring sheet. Record defects as new tickets; do not waive a failed P0 criterion verbally.

### Dependencies
- Needs LEASH-101.
- Needs LEASH-133.
- Needs LEASH-145.
- Needs LEASH-146.
- Needs LEASH-147.
- Needs LEASH-148.
- Needs LEASH-149.
- Needs LEASH-150.
- Needs LEASH-151.
- Needs LEASH-152.
- Blocks LEASH-128.

## Testing Requirements
Perform three consecutive clean rehearsals, including one refresh recovery and one presenter fallback. A human signs the scoring sheet.

## Related Files
- `solution/RUNBOOK.md`
- `solution/app/e2e/`
- `solution/kanban/`

## Out of scope
- Approving a demo that requires undocumented manual database repair.
