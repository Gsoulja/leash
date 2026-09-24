# LEASH-043: Repository port and Postgres adapter

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: L
**Milestone**: M3 — Durable fake-API integration
**Rule source**: Engineering
**Decisions**: DEC-003, DEC-010
**Parent**: LEASH-003
**Task ID**: 003-T4
**Blocked by**: LEASH-041, LEASH-015, LEASH-028
**Blocks**: LEASH-044, LEASH-052, LEASH-061, LEASH-082, LEASH-124, LEASH-128
**Updated**: 2026-09-23

## Description
Repository port and its Postgres implementation: idempotent insert of a received purchase, snapshot query for a card, saving decisions through the state machine.

## Business Value
Durable state behind the same interface the in-memory replay uses.

## Acceptance Criteria
- [x] Inserting the same live authorization_id twice returns the saved decision.
- [x] Snapshot includes approved spend in window, recent orders at the merchant, familiarity, known devices and countries.
- [x] Saving an illegal transition fails.
- [x] Snapshot reconciles with the event context; mismatches are reported.

## Technical Approach
`ports/repository.py`, `adapters/postgres/repository.py` (asyncpg).

### Dependencies
- Needs LEASH-041.
- Needs LEASH-015.
- Needs LEASH-028.
- Blocks LEASH-044.
- Blocks LEASH-052.
- Blocks LEASH-061.
- Blocks LEASH-082.
- Blocks LEASH-124.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_repeat_delivery_returns_saved_decision`, `test_snapshot_window_sum`.

## Related Files
- `solution/engine/src/leash/ports/repository.py`
- `solution/engine/src/leash/adapters/postgres/repository.py`
- `solution/engine/tests/adapters/test_postgres_repository.py`

## Out of scope
- Outbox sending (LEASH-054).

## Review log

### 2026-09-23 — independent agent review
- [x] met — idempotent receive: 30 concurrent receives of one live ID → 1 insert, 29 saved records, 1 event; repeat before a decision reports it in flight.
- [x] met — snapshot: 7-day spend by simulated time (exact boundary excluded), recent orders incl. waiting, familiarity = history 6 + run approvals (DEC-011/015), devices and countries from approved purchases only, 58 merchant names, run/card isolation, delivery order, exact Purchase round-trip (Decimal precision, Terms, dates, None, non-ASCII).
- [x] met — illegal transitions raise and leave row and events unchanged; 15 concurrent decisions → 1 wins; racing customer/platform resolutions → 1 wins.
- [x] met — reconcile reports status mismatches, unknown IDs and spend differences (down to 0.01) with one integrity_alert; nothing on a clean context.
Notes: our spend total is now rounded to cents before comparing (a 3-decimal amount gave a false alert; fixed after review). Migration 0002 adds `purchase` NOT NULL without a backfill — fine today (no database holds authorizations at 0001), not safe for a populated table.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
