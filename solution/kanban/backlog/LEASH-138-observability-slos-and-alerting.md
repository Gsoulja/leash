# LEASH-138: Observability, SLOs and alerting

**Status**: BACKLOG
**Priority**: P0
**Type**: infra
**Estimated Effort**: L
**Milestone**: M7 — Production hardening
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-129
**Task ID**: 129-T9
**Blocked by**: LEASH-137
**Blocks**: LEASH-142, LEASH-143
**Gate**: DECISION — operations signs off the SLOs, paging thresholds and data-safe telemetry fields.
**Updated**: 2026-09-24

## Description
Add metrics, distributed traces, dashboards and actionable alerts for the complete authorization path.

## Business Value
Operators must detect deadline risk, stuck work and platform disagreement before customers report them.

## Acceptance Criteria
- [ ] Metrics cover decision latency, remaining deadline margin, lock wait, verdicts and reader fallback.
- [ ] Metrics cover claim age, outbox age, retry count, dead letters and reconciliation mismatches.
- [ ] Traces correlate poll, authorization ID, decision transaction, platform POST and customer resolution.
- [ ] Logs, metrics and traces exclude secrets and unsafe merchant text.
- [ ] Dashboards show SLO attainment and the oldest unresolved work.
- [ ] Alerts have thresholds, owners, severity and linked runbook actions.
- [ ] Synthetic probes verify the decision and human-resolution paths.

## Technical Approach
Instrument ports and application stages with OpenTelemetry-compatible telemetry and expose a scrape/export endpoint outside the customer API.

### Dependencies
- Needs LEASH-137.
- Blocks LEASH-142.
- Blocks LEASH-143.

## Testing Requirements
Write telemetry contract tests for required labels, trace propagation, redaction and alert-condition calculations.

## Related Files
- `solution/engine/src/leash/config.py`
- `solution/engine/src/leash/application/decide_purchase.py`
- `solution/engine/src/leash/adapters/viseca_api/worker.py`
- `solution/RUNBOOK.md`

## Out of scope
- Selecting a commercial observability vendor.
