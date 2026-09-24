# LEASH-041: Initial schema migration

**Status**: DONE
**Priority**: P0
**Type**: infra
**Estimated Effort**: L
**Milestone**: M3 — Durable fake-API integration
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-003
**Task ID**: 003-T2
**Blocked by**: LEASH-040
**Blocks**: LEASH-042, LEASH-043, LEASH-128
**Updated**: 2026-09-23

## Description
Alembic migration with the agreed schema: merchants, history, familiarity view, mandates, mandate versions, runs, authorizations, append-only decision_events, outbox, fact_reads, model_releases.

## Business Value
Durable state with constraints that make illegal data impossible.

## Acceptance Criteria
- [x] Migration upgrades and downgrades cleanly.
- [x] Money is NUMERIC(12,2); times are timestamptz; sim_ts and deadline columns are separate.
- [x] UPDATE or DELETE on decision_events raises.
- [x] CHECK constraints enforce state and verdict values.
- [x] Familiarity view counts approved purchases only.

## Technical Approach
`migrations/versions/0001_initial.py` with raw SQL via op.execute.

### Dependencies
- Needs LEASH-040.
- Blocks LEASH-042.
- Blocks LEASH-043.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_decision_events_is_append_only`, `test_state_check_rejects_unknown_value`.

## Related Files
- `solution/engine/alembic.ini`
- `solution/engine/migrations/env.py`
- `solution/engine/migrations/versions/0001_initial.py`
- `solution/engine/tests/adapters/test_schema.py`

## Out of scope
- ORM models.

## Review log

### 2026-09-23 — independent agent review
- [x] met — criterion 1: upgrade → downgrade → upgrade → downgrade on a throw-away database; only alembic_version left.
- [x] met — criterion 2: billing_chf numeric(12,2); all 11 timestamp columns timestamptz; sim_ts separate from received_at/deadline_at/ask_expires_at.
- [x] met — criterion 3: row trigger blocks UPDATE/DELETE (and TRUNCATE) on decision_events.
- [x] met — criterion 4: CHECKs on state, engine_verdict and every other enum column.
- [x] met — criterion 5: familiarity view counts approved purchases only (2 of 5 mixed rows).
Out-of-list file `migrations/script.py.mako` (standard Alembic template) justified. Reviewer dropped its probe database.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
