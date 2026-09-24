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

## Notes
- The pool is configured through `Settings` (`LEASH_HTTP_MAX_CONNECTIONS`,
  `LEASH_HTTP_MAX_KEEPALIVE_CONNECTIONS`, `LEASH_HTTP_KEEPALIVE_EXPIRY_SECONDS`,
  `LEASH_HTTP_CONNECT_RETRIES`), documented in `solution/.env.example`. Both processes build their
  client through `config.platform_client(settings)`, which is the only `VisecaClient(...)` call site
  left in `src/`.
- `create_api` does **not** close the client: it is given it, so it does not own it. Whoever builds it
  closes it, which lets one process share a client between the API and a worker.
- Field fingerprints in `tests/policy/test_registry.py` were re-pinned. `leash.application.decide_purchase`
  is in `SHARED_ENFORCEMENT`, and its diff is the send's deadline handling only — no rule, compiled
  mandate, fact, check or verdict changed. The reviewer confirmed this by recomputing all 13 fingerprints
  with only `decide_purchase.py` reverted: that reproduces the old pins exactly, so the whole delta is
  attributable to that one file.

## Review log

### 2026-09-24 — independent agent review
- [x] met — criterion 1: proved at socket level, not by object identity. The reviewer ran the new counting
  server against the pre-change client: old = 5 requests / 5 TCP connections, new = 5 / 1.
- [ ] not met — criterion 2: `service.main()` closed the client from a second `asyncio.run` after
  `uvicorn.run` had closed the loop the pool's sockets were opened on. Reproduced: `RuntimeError: Event
  loop is closed` from httpcore while tearing down an idle keep-alive connection, so the process would
  exit on a traceback with the socket uncleanly closed. `worker._serve` was already correct.
- [ ] not met — criterion 3: the new env vars were dead in both deployed processes — `service.py` and
  `worker.py` constructed `VisecaClient(...)` directly, bypassing `from_env`, so the limits were always
  the hard-wired defaults.
- [x] met — criterion 4, incl. the watchdog path; the outbox and `/resolve` carry no `deadline_at` by design (LEASH-054).
- [x] met — criterion 5: asserted on the real `request.extensions["timeout"]` (poll read 35 vs send read 7.5).
- [x] met — criterion 6: verified against the installed httpcore 1.0.9 that the retry loop lives inside
  `_connect()`, before the request is written, so a POST body is never replayed — within the ticket's
  "Out of scope".
Verdict: returned to in-progress.

Fix: `service.serve_until_stopped(server, viseca)` now serves and closes in one loop, and `main()` runs a
`uvicorn.Server` through it. The pool settings moved into `Settings` with `config.platform_client()` as the
single construction site for both processes.

### 2026-09-24 — independent agent review (round 2)
- [x] met — criterion 2: re-checked with a genuine TCP keep-alive socket; the round-1 scenario now closes
  cleanly, `worker._serve` still correct, no double close, and `create_api` still does not close a client
  it was given. The reviewer noted the regression guard was weak (an ASGI transport owns no socket, so it
  could not fail on loop affinity). Fixed after review: that test was replaced by two real-socket tests in
  `tests/adapters/test_api_client_pool.py` — one pinning the hazard itself (closing from a second loop
  raises) and one proving `serve_until_stopped` releases a real connection.
- [x] met — criterion 3: `grep "VisecaClient("` over `src/` returns exactly one hit (`config.py`), so no
  production path hard-wires defaults; the variables are live in both processes.
- [x] met — criteria 1, 4, 5, 6 re-checked with no regression; both new decide tests still fail against the
  pre-change `decide_purchase` and pass on current code.
- Fingerprints re-verified by recomputation, and `config.py`/`service.py` correctly contribute nothing
  (both classified in `NOT_A_FIELD_MEANING`).

Two of the three gaps left open by the review were then closed (2026-09-24), with each new test
checked against the old code so it cannot pass vacuously:

- `main()` is now covered by `test_main_serves_and_closes_the_pooled_client_in_one_loop`. It runs a real
  local keep-alive server, lets `main()` build its own client through `platform_client`, and stubs
  `uvicorn.run` to serve in its own loop the way the real one does. Verified by temporarily reverting
  `main()` to the `uvicorn.run(...)` + second `asyncio.run(aclose())` shape: the test then fails with
  `RuntimeError: Event loop is closed`, and passes again once restored.
- The no-replay property is now proved through the real httpcore path by
  `test_a_real_failure_after_the_body_was_written_is_never_replayed`: the server reads the whole POST
  body and hangs up without answering, with `connect_retries=3`, and the platform must still see the
  decision exactly once (`server.requests == 1`). It no longer rests only on reading httpcore's source.
- The socket helpers moved to `tests/keepalive_server.py` so the service tests can use real sockets too;
  the weaker ASGI-transport version of the shutdown test was deleted rather than left to mislead.

Still unverified, for the human gate:
- The pool has only been exercised against local test servers. Behaviour against the hosted platform
  under real latency, TLS and proxy idle timeouts is untested here: it needs the team API key (gated by
  LEASH-057 until event day) and is LEASH-142's scope.
- `DEFAULT_KEEPALIVE_EXPIRY_SECONDS = 30` was chosen to sit under a typical proxy idle timeout. The
  platform's actual idle timeout is unknown, so the value is a reasoned default, not a measured one.

Verdict: moved to review.
