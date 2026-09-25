# LEASH-174: Bug reports

**Status**: BACKLOG
**Priority**: P1
**Type**: epic
**Estimated Effort**: open-ended (grows as bugs are filed)
**Milestone**: none — cross-cutting, ongoing
**Rule source**: Team (bug-reporting workflow, started 2026-09-24)
**Decisions**: none
**Blocked by**: none
**Blocks**: none
**Updated**: 2026-09-24

## Description
Container for bugs found in the engine, prototype or app after the fact — not planned feature work. Each bug is filed as its own leaf ticket under this epic, with `**Parent**: LEASH-174` and a `**Task ID**` of the form `174-T<n>`, numbered in the order they are reported. This epic never closes in the normal sense: it stays open and accumulates children as long as bugs are being reported.

## Business Value
Keeps defect tracking on the same board as planned work, joined by ID like everything else, instead of living in chat history or ad-hoc notes.

## Acceptance Criteria
- [ ] Every reported bug has its own ticket file under `solution/kanban/`, parented to LEASH-174.
- [ ] Each bug ticket names the observed behaviour, the expected behaviour, and steps to reproduce.
- [ ] Bug tickets follow the same stage folders and status values as the rest of the board.

## Sub-tasks
- [ ] LEASH-175 (174-T1): CI image-scan job fails to resolve a nested action tag (`aquasecurity/setup-trivy@v0.2.1` deleted upstream) · S · P0
- [ ] LEASH-176 (174-T2): Worker refuses to start against the live platform — data version `saw26-hackaton-api` != `saw26` · S · P0 · **DECISION gate**
- [ ] LEASH-177 (174-T3): Instruction compiler reads zero rules from "buy me nike running shoes size 44 up to 40 CHF" · M · P1
- [ ] LEASH-178 (174-T4): Payment detail lists checks in fixed engine order, so the row that stopped the payment sits below the passed ones · S · P1
- [ ] LEASH-195 (174-T5): Customer app doesn't follow the Hi-Fi v4 design handoff — fixed by completing LEASH-179 · S · P1
- [ ] LEASH-196 (174-T6): Release job fails to store build provenance — GitHub attestations are refused for user-owned private repos · S · P0
- [ ] LEASH-197 (174-T7): Secret scan fails with 403 on pull requests — token lacks `pull-requests: read` · S · P0

## Technical Approach
No production code changes from this ticket itself. Each child ticket follows the normal TDD workflow in `CLAUDE.md`: a failing test that reproduces the bug, then the fix.

### Dependencies
- Children point back here with `**Parent**: LEASH-174`.

## Testing Requirements
Not applicable to the epic; each child ticket specifies its own reproducing test.

## Related Files
- `solution/kanban/`

## Out of scope
- Feature requests and planned work — those get their own epics, not this one.
