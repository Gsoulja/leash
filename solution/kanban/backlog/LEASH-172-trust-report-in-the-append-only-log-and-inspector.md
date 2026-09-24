# LEASH-172: Trust report in the append-only log and inspector

**Status**: BACKLOG
**Priority**: P2
**Type**: feature
**Estimated Effort**: S
**Milestone**: M7 — Production hardening
**Rule source**: Team (proposal from the 2026-09-24 trust-filter session)
**Decisions**: DEC-038 (to be written in LEASH-161), DEC-009, DEC-025, DEC-029, DEC-030
**Pattern**: Append-only log + projections
**Parent**: LEASH-160
**Task ID**: 160-T12
**Blocked by**: LEASH-167
**Blocks**: none
**Updated**: 2026-09-24

## Description
Store the full `TrustReport` (every finding with field, excerpt and reason, plus canonicalisation flags) with the decision in `decision_events`, so the audit trail shows what the shop tried even when the verdict only needed one finding. Show it in the engine inspector next to `shop_texts`.

## Business Value
Auditable history: a reviewer can see every finding, not only the ones in the message.

## Acceptance Criteria
- [ ] A decision with two findings stores both in `decision_events`.
- [ ] Replaying the log rebuilds the same report (projection).
- [ ] The inspector lists findings per field, with the raw excerpt escaped.
- [ ] Repeat delivery of the same `authorization_id` doesn't store the report twice (edge case: idempotent receiver).

## Technical Approach
Postgres migration adding a JSON column or event payload field; `adapters/postgres/repository.py`; `adapters/http/query_api.py`; `solution/app/src/inspector/Inspector.tsx`.

### Dependencies
- Needs LEASH-167.

## Testing Requirements
Write first: adapter test `test_trust_report_round_trips` against real Postgres. Run `uv run pytest tests/adapters -x -q`.

## Related Files
- `solution/engine/src/leash/adapters/postgres/repository.py`
- `solution/engine/src/leash/adapters/http/query_api.py`
- `solution/app/src/inspector/Inspector.tsx`

## Out of scope
- Customer-facing UI (LEASH-170).
- Retention policy.
