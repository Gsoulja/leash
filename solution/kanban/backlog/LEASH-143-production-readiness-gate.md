# LEASH-143: Production-readiness gate

**Status**: BACKLOG
**Priority**: P0
**Type**: test
**Estimated Effort**: S
**Milestone**: M7 — Production hardening
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-129
**Task ID**: 129-T14
**Blocked by**: LEASH-130, LEASH-131, LEASH-132, LEASH-133, LEASH-135, LEASH-136, LEASH-137, LEASH-138, LEASH-139, LEASH-140, LEASH-141, LEASH-142
**Blocks**: none
**Gate**: DECISION — product, engineering, security and operations jointly accept the evidence and residual risks.
**Updated**: 2026-09-24

## Description
Evidence-based approval before Leash handles non-synthetic authorization data or real customer actions.

## Business Value
No production launch occurs because a demo works; every safety, security and operational claim must have reviewable evidence.

## Acceptance Criteria
- [ ] Platform and local state reconcile across success, retry, terminal refusal and crash cases.
- [ ] Migration, backup, restore, failover and rollback drills meet approved objectives.
- [ ] SLO dashboards and paging alerts are live and exercised.
- [ ] Load, soak and chaos evidence meets the capacity plan.
- [ ] Data retention, encryption, audit and incident-response controls are approved.
- [ ] The deployed artifact is signed, reproducible and linked to its source and schema revision.
- [ ] Every accepted residual risk has an owner and expiry date.

## Technical Approach
Maintain a release evidence index linking automated reports, drill records, dashboards, security review and signed artifacts.

### Dependencies
- Needs LEASH-130 through LEASH-133 and LEASH-135 through LEASH-142.

## Testing Requirements
A human review panel walks every criterion and records approve/reject with evidence links.

## Related Files
- `solution/RUNBOOK.md`
- `solution/docs/decisions.md`
- `solution/kanban/`

## Out of scope
- Waiving a failed critical control to meet a launch date.
