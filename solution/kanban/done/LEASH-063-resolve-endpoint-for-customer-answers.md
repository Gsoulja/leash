# LEASH-063: Resolve endpoint for customer answers

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: S
**Milestone**: M4 — Customer-control journey
**Rule source**: Engineering
**Decisions**: DEC-012
**Parent**: LEASH-005
**Task ID**: 005-T4
**Blocked by**: LEASH-045, LEASH-061
**Blocks**: LEASH-094, LEASH-128
**Updated**: 2026-09-23

## Description
Endpoint the app calls when the customer approves or rejects an ask; records it and queues /resolve.

## Business Value
The human approval and rejection path.

## Acceptance Criteria
- [x] Approve and reject both reach the outbox.
- [x] Answering an already final purchase returns 409.
- [x] An answer after expiry, or racing the sweeper, returns 409 and changes nothing.
- [x] Approve is refused when a hard rule now fails (DEC-012).

## Technical Approach
Policy API route calling application/resolve.

### Dependencies
- Needs LEASH-045.
- Needs LEASH-061.
- Blocks LEASH-094.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_answer_after_timeout_is_409`.

## Related Files
- `solution/engine/src/leash/adapters/http/policy_api.py`
- `solution/engine/tests/adapters/test_resolve_api.py`

## Out of scope
- Inventing answers automatically (forbidden).

## Implementation note (2026-09-23)
- `policy_api.asks_router`, wired into the API process (`leash/service.py`), provides `POST /api/asks/{authorization_id}/answer` as in the contract:
  - 200 returns the Payment;
  - 404 for an unknown payment;
  - 409 `not_waiting` when the payment is already final, answered, expired or swept;
  - 422 `cannot_approve` when the DEC-012 re-check fails (the message explains why; only Reject remains);
  - 422 `invalid_request` for a bad body;
  - 503 `busy` when the card lock times out.
- The answer goes through `application.resolve.ResolveAsk`, which uses the per-card lock and a fresh snapshot, re-checks against the run's stored mandate, and writes the `/resolve` outbox row in the same transaction.
- The stored mandates are refreshed first, so a run started a moment ago is never "unknown".
- After the commit, `/resolve` is POSTed at once and marked sent, but only when no earlier outbox row for that purchase (its decision) is still unsent. Otherwise the outbox sends both, in order.
- "Changes nothing" after expiry: the answer is never recorded or sent. An expired ask is marked `timed_out`, exactly as the sweeper would (DEC-016).
- `query_api` exposes `payment_view` / `PAYMENT_COLUMNS` so both endpoints return the same Payment shape.
- Tests: `tests/adapters/test_resolve_api.py` (7, through the full API process, contract-validated).

## Review log

### 2026-09-23 — independent agent review
- [x] met — criterion 1: the state change and the resolve outbox row commit together under the card lock; both answers were checked against the contract.
- [x] met — criterion 2: final purchases give `IllegalTransition` → 409 `not_waiting`.
- [x] met — criterion 3: the sweeper and the answer share the card lock and `FOR UPDATE`; whichever is first wins. An expired answer marks the ask `timed_out` exactly as the sweeper would, and is never recorded or sent.
- [x] met — criterion 4: the re-check runs under the lock with a fresh snapshot; a failing rule returns 422 and writes and sends nothing. Probes:
  - concurrent approve/decline: exactly one wins;
  - an answer racing a new decision on the same card is never approved together with it;
  - a failed immediate send leaves the row for the outbox;
  - /resolve never reaches Viseca before its decision.
- Minor findings, fixed afterwards:
  - **the re-check ignored the platform spend counter (DEC-010)**, so it could be looser than the decision. Both re-check paths (`ResolutionTransaction.resolve` and the ask's `can_approve`) now use `platform_spend_now`: the event's counter plus approvals recorded since the purchase arrived. The snapshot takes the higher of that and the ledger. Test: `test_the_recheck_counts_the_platforms_spend_too`;
  - the contract now documents 404 and 503 for answerAsk, and the app types are regenerated (35 app tests pass);
  - 404 comes from an explicit existence check, not from catching any `KeyError`;
  - the immediate send is bounded at 2 s, below the 3 s outbox grace, so the two can't overlap.
- Residual: a mandate that changes mid-run is not seen (a run keeps its starting snapshot; DEC-003 cross-check not built).
- 1182 tests pass, mypy clean, registry re-pinned.
Moved to done on the product owner's standing instruction for this run.
