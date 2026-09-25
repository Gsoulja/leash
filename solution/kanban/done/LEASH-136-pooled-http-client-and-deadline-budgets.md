# LEASH-136: Pooled HTTP client and deadline budgets

**Status**: DONE
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
**Updated**: 2026-09-25

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
change is load-bearing, and reported that `asyncio.run(viseca.aclose())` is safe across event loops against
a real socket server with live keep-alive connections.

**That last claim is false, and is retracted (2026-09-24).** A later impartial assessment reproduced the
opposite: with a live keep-alive connection, closing the pool from a second `asyncio.run` after uvicorn
has returned raises `RuntimeError: Event loop is closed`. So `service.main()` ends every clean API
shutdown on a traceback with the socket not cleanly closed, and **AC2 is not met for the API process** —
only for the worker, whose `async with client:` is correct. `origin/feature/LEASH-136` fixes this
properly with a `serve_until_stopped` helper that serves and closes inside one loop, and pins it with a
real-socket test. See the reconciliation note below. All 13 LOCK pins recomputed independently: 0
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

## Reconciliation with feature/LEASH-136 — 2026-09-24

This ticket was implemented twice in parallel. An impartial assessment of both scored
`origin/feature/LEASH-136` better on five of six criteria and on design fit, and found a **production
defect in this branch's version that this log had wrongly certified as checked** (see the retraction
above). The result below is not a merge: the two were reconciled by hand, because a merge-tool
resolution of `worker.py` or `service.py` would have deleted LEASH-130's reconciler loop or LEASH-151's
bundle-revision gate — the other branch predates both.

**Taken from feature/LEASH-136**
- `serve_until_stopped(server, viseca)`: the API serves and closes the pool inside one event loop.
  This is the fix for the defect above.
- Pool settings in the pydantic `Settings` with constraints, plus `config.platform_client(settings)` as
  the single construction site, and `.env.example` documenting every variable. `PoolSettings` is deleted:
  one env reader, validated once, instead of a second one inside the adapter with two call sites.
- `retries=connect_retries` on `httpx.AsyncHTTPTransport`, replacing ~20 lines of hand-rolled retry.
  Verified in httpcore's source: `retries_left` is consumed only inside `_connect()` and only for
  `ConnectError`/`ConnectTimeout`, before a byte of the request is written — so a decision POST the
  platform already received can never be replayed, whatever the method. The previous method-allowlist
  loop was *wider*: it caught `ReadTimeout`, which on the long poll could re-poll after the platform had
  already dequeued an envelope.
- The pool built in `__init__` rather than lazily, which makes "exactly once" structural instead of
  something a check-then-set has to get right.
- `pool_timeout_seconds`, the budget reaching httpx per phase, and the client's own refusal to start when
  `budget_seconds <= 0`.
- `tests/keepalive_server.py` and `tests/adapters/test_api_client_pool.py`: 16 real-socket tests,
  including the **only** genuine pool-exhaustion test either version had, the cross-loop-close hazard, and
  a no-replay proof that reads a whole POST body then hangs up.

**Kept from this branch**
- `_serve`/`_work` split with `async with client:` wrapping bootstrap *and* the database pool — the other
  version leaked the pool on a worker startup failure, the mirror image of the defect it found here.
  Now pinned structurally by `test_the_worker_opens_the_pool_before_anything_that_can_fail`, verified to
  fail when the guard is reordered.
- `min(plan.send_seconds, left)` as the outer send bound (the other used the looser `left`).
- `ClientClosed` as a named exception rather than a bare `RuntimeError`.
- A separate connect-timeout cap: without it a 25-second long poll waits 35 seconds to reach a dead host.
- Everything from LEASH-130, LEASH-135 and LEASH-151, untouched.

**Written fresh, because neither version did it**
- The `Sender` port now takes `budget_seconds`. This branch had moved the budget into
  `ApiSender.__init__`, so the transport only ever saw the *planned* window, not the time actually left —
  which is not what the Description asks for. The other branch threaded the live number but left the
  Protocol declaring two arguments and reached it by sniffing the signature at runtime behind a
  `type: ignore`, so mypy could not catch a sender that silently dropped the budget. The port now states
  the contract and all nine test doubles were updated to match.

**Dropped from this branch as tautological**, on the assessment's evidence: a "pool exhaustion" test that
injected a transport which unconditionally raised `PoolTimeout` and then asserted `PoolTimeout`; a
"startup failure" test that exercised Python's `async with` rather than `_serve`; and two tests that read
back their own constructor arguments.

**Also corrected:** the claim that an unreadable pool setting falls back to its default was false for
`inf`, `nan` and `1e400`, which raised uncaught from `int(float(...))`. Those are now startup errors
naming the variable, along with `0`, `-1` and unparseable values, which used to be silently rewritten.

**Still open, in both versions and not fixed here:** `Worker._answer_invalid` POSTs a real `step_up` with
the default timeout and no `wait_for`. It cannot be bounded as written — `InvalidEvent` carries only
`authorization_id`, so there is no deadline to measure against. Filed rather than smuggled in; AC4 has
that one hole.

Registry LOCK re-pinned from a run, not hand-edited: the `Sender` signature change alone moves all 13
fingerprints, since `application/decide_purchase.py` is in `SHARED_ENFORCEMENT` and `code_hash` reads the
AST. Neither branch's pins or justification would have been truthful for this result.
