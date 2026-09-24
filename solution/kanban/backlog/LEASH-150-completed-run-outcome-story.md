# LEASH-150: Completed-run outcome story

**Status**: BACKLOG
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M8 — Great demo
**Rule source**: Product
**Decisions**: DEC-033, DEC-034, DEC-035, DEC-036, DEC-037
**Parent**: LEASH-144
**Task ID**: 144-T6
**Blocked by**: LEASH-133, LEASH-148, LEASH-130
**Blocks**: LEASH-153
**Updated**: 2026-09-24

## Description
Close each run with a concise narrative summary and make every significant outcome traceable from the timeline to its payment evidence.

## Business Value
The demo needs a payoff: what the agent achieved, what Leash prevented and where the customer stayed in control.

## Acceptance Criteria
- [ ] Completion is announced in the Agent conversation without requiring a tab change.
- [ ] The summary shows paid, blocked, customer-approved and customer-rejected counts for the same run.
- [ ] It highlights at least one successful purchase, one protected outcome and one intervention when present.
- [ ] Selecting an outcome opens the relevant payment comparison and returns to the same timeline position.
- [ ] Cockpit and Agent totals agree for the selected run.
- [ ] Failed and partially completed runs state what happened and what can be retried.
- [ ] A clear action opens the full Cockpit evidence.

## Technical Approach
Build the summary from the run-scoped read model fixed by LEASH-133. Reuse `PaymentDetail` instead of duplicating rule comparison logic.

### Dependencies
- Needs LEASH-133.
- Needs LEASH-148.
- Needs LEASH-130.
- Blocks LEASH-153.

## Testing Requirements
Test successful, mixed, failed and empty runs. Add an end-to-end assertion that Agent and Cockpit show identical counts and spending.

## Related Files
- `solution/app/src/screens/Cockpit.tsx`
- `solution/app/src/screens/PaymentDetail.tsx`
- `solution/app/src/screens/Agent.tsx`

## Out of scope
- Cross-run financial analytics.
