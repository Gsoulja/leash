# LEASH-129: Production readiness hardening

**Status**: BACKLOG
**Priority**: P0
**Type**: infra
**Estimated Effort**: L
**Milestone**: M7 — Production hardening
**Rule source**: Engineering
**Decisions**: none
**Blocked by**: none
**Blocks**: none
**Updated**: 2026-09-24

## Description
Move Leash from a hackathon prototype to a production-grade financial control service. The work establishes platform-truth reconciliation, crash recovery, safe operations, and evidence-based release controls.

## Business Value
Real purchases must remain correct and explainable through crashes, retries, deployments, dependency failures and operator intervention.

## Acceptance Criteria
- [ ] Platform acceptance, not only the engine verdict, determines final payment state.
- [ ] Every received authorization is recoverable after a crash.
- [ ] Production deployment, recovery, observability and release controls have evidence.
- [ ] A human completes the production-readiness gate.

## Sub-tasks
- LEASH-130 — Reconcile decision delivery with platform truth.
- LEASH-131 — Recover abandoned received authorizations.
- LEASH-132 — Persist invalid-event fallback decisions.
- LEASH-133 — Scope the cockpit to one selected run.
- LEASH-135 — Make database migrations safe on populated systems.
- LEASH-136 — Reuse HTTP connections and enforce deadline budgets.
- LEASH-137 — Add outbox leases, dead letters and operator recovery.
- LEASH-138 — Add production metrics, tracing, SLOs and alerts.
- LEASH-139 — Define backup, restore, retention and disaster recovery.
- LEASH-140 — Harden TLS, secrets, networks and database privileges.
- LEASH-141 — Add CI and software-supply-chain release controls.
- LEASH-142 — Prove load, failover and chaos resilience.
- LEASH-143 — Production-readiness gate.

## Technical Approach
Keep the deterministic domain core. Harden the adapters, persistence projections, deployment boundary and operational evidence around it.

### Dependencies
- The epic closes when LEASH-130 through LEASH-133 and LEASH-135 through LEASH-143 are done.

## Testing Requirements
Each leaf ticket defines its own failing tests and operational evidence.

## Related Files
- `solution/engine/`
- `solution/app/`
- `solution/docker-compose.yml`
- `solution/RUNBOOK.md`

## Out of scope
- Replacing the deterministic decision core with a model.
