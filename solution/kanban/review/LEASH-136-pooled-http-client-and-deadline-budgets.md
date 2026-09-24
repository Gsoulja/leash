# LEASH-136: Pooled HTTP client and deadline budgets

**Status**: REVIEW
**Priority**: P1
**Type**: infra
**Estimated Effort**: M
**Milestone**: M7 — Production hardening
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-129
**Task ID**: 129-T7
**Blocked by**: none
**Blocks**: LEASH-142, LEASH-143
**Updated**: 2026-09-24

## Description
Reuse a bounded asynchronous HTTP connection pool and propagate the remaining decision budget through connect, read, write and pool timeouts.

## Business Value
Avoiding a fresh client and TLS connection for every request reduces deadline risk and socket exhaustion.

## Acceptance Criteria
- [x] One managed `httpx.AsyncClient` is reused for the service lifetime.
- [x] Startup and shutdown create and close the client exactly once.
- [x] Connection limits and keep-alive expiry are configurable.
- [x] Decision POST timeouts never extend beyond `deadline_at`.
- [x] Long-poll timeout remains separate from decision-send timeout.
- [x] Retry behavior respects idempotency and the remaining wall-clock budget.

## Technical Approach
Make the client an async lifecycle resource and use explicit `httpx.Timeout` values derived from the operation budget.

### Dependencies
- Blocks LEASH-142.
- Blocks LEASH-143.

## Testing Requirements
Write failing transport tests proving connection reuse, shutdown, pool exhaustion behavior and no send after the authoritative deadline.

## Related Files
- `solution/engine/src/leash/adapters/viseca_api/client.py`
- `solution/engine/src/leash/adapters/viseca_api/worker.py`
- `solution/engine/src/leash/service.py`

## Out of scope
- Retrying non-idempotent calls without a platform idempotency guarantee.

## Implementation notes

- `VisecaClient` now owns one pooled `httpx.AsyncClient`, created on first use and closed once by
  `aclose()` (also an async context manager). A closed client raises `ClientClosed` rather than
  quietly opening a second pool.
- Ownership: whoever creates the pool closes it. `service.main()` closes it in a `finally` around
  `uvicorn.run`; `worker._serve` wraps everything in `async with client`. The API app never closes a
  client it was handed — a worker in the same process can share it, and the first version of this
  change broke the end-to-end run exactly that way.
- `PoolSettings` (`LEASH_HTTP_MAX_CONNECTIONS`, `LEASH_HTTP_MAX_KEEPALIVE_CONNECTIONS`,
  `LEASH_HTTP_KEEPALIVE_EXPIRY_SECONDS`, `LEASH_HTTP_CONNECT_TIMEOUT_SECONDS`, `LEASH_HTTP_RETRIES`)
  carries the limits; an unreadable value falls back to the documented default.
- Every request builds an explicit `httpx.Timeout` from that call's budget, connect included, so no
  phase can outlive the whole call. The long-poll keeps `wait + LONG_POLL_MARGIN_SECONDS`.
- `DecidePurchase._send` capped the POST at `max(send_seconds, left)`, which let a slow platform hold
  the call past `deadline_at` whenever the plan's send budget was the larger number. It is now
  `max(0.0, min(send_seconds, left))`, and `ApiSender` passes the same budget down as the HTTP
  timeout. (`application/decide_purchase.py` is outside this ticket's Related Files, but AC4 cannot
  be true without that one line.)
- Retries: safe methods only (`GET`/`HEAD`/`OPTIONS`), never a decision POST — the outbox resends
  that — and never once the call's budget is spent.

## Review log

### 2026-09-24 — independent agent review
AC1, AC3, AC4, AC5, AC6 `met`; **AC2 `not met`** — all gaps now fixed.

Verified by reproduction, not reading: the `max(send_seconds, left)` → `min(...)` change was mutated
back and `test_a_hanging_send_is_abandoned_before_the_deadline` failed at the 5 s plan budget instead
of the 0.6 s deadline; adding `"POST"` to `SAFE_METHODS` killed the never-retried test; removing the
long-poll timeout killed two. The reviewer also re-added the lifespan close I had removed and
reproduced the e2e failure it caused (61 s, 0 of 11 authorizations decided), confirming the ownership
change is load-bearing, and checked `asyncio.run(viseca.aclose())` is safe across event loops against a
real socket server with live keep-alive connections. All 13 LOCK pins recomputed independently: 0
mismatches, and the re-pin justification holds (`decide_purchase.py` is in `SHARED_ENFORCEMENT`; the
only change is the timeout expression and two comments, which read no rule, fact or amount).

AC2 gaps, fixed:
- **The worker leaked the pool on a startup failure.** `load_runtime` opens the HTTP pool (it calls
  `bootstrap()`), and both it and `asyncpg.create_pool` ran *before* the `try` whose `finally` closed
  the client — so a version mismatch or a down database leaked it. `_serve` now opens `async with
  client:` before any of that and delegates to `_work`; the HTTP close also runs *after* the database
  close, so a database close that raises can no longer skip it.
- **Nothing tested the exactly-once wiring** (both entry points are `# pragma: no cover`).
  `test_a_startup_failure_still_closes_the_pool` pins the mechanism `_serve` relies on, and
  `test_only_one_async_client_is_ever_constructed` counts constructions rather than comparing two
  handles (the old test passed even with a client per request).
- **AC1's evidence was object identity, not socket reuse** — what the Testing Requirements asked for.
  `test_the_pool_reuses_one_tcp_connection_across_requests` runs a real `asyncio.start_server` that
  counts accepted connections: 4 requests, 1 connection. Mutating the pool cache to build a client per
  request fails it (4 connections) along with two others.
  `test_the_configured_limits_reach_the_real_connection_pool` checks the limits land on the real
  httpcore pool, not just on `PoolSettings.limits()`.

Defect found inside the diff, fixed: `LEASH_HTTP_RETRIES=-1` is readable but out of range, so it
escaped the fallback and gave `attempts = 0` — every safe GET raised `UnboundLocalError` and sent
nothing. `PoolSettings.from_env` now clamps, and `_request` takes one attempt as its floor.

Two findings deliberately left alone, both outside this ticket:
- `Worker._answer_invalid` POSTs a real `step_up` with the default 10 s timeout and no `wait_for`.
  It cannot be capped as written: `InvalidEvent` carries only `authorization_id`, so that path has no
  `deadline_at` to measure against.
- `OutboxSender` also uses the default timeout. That is correct — it is the post-deadline recovery
  channel (DEC-007/LEASH-054), and capping it to "time left before `deadline_at`" would mean never
  sending.

Also noted, not acted on: a `TransportError` retry of `GET /v1/decision-requests/next` could in
principle lose a dequeued item if the platform dequeues before delivery completes and does not
redeliver. `technical_details.md` does not say either way — one for the Viseca experts.
