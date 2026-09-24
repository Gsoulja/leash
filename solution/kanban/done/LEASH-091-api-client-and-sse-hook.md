# LEASH-091: API client and SSE hook

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: S
**Milestone**: M4 — Customer-control journey
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-007
**Task ID**: 007-T2
**Blocked by**: LEASH-090, LEASH-118
**Blocks**: LEASH-092, LEASH-093, LEASH-094, LEASH-096, LEASH-097, LEASH-128
**Updated**: 2026-09-23

## Description
Typed client for the policy service and a hook that subscribes to the SSE stream.

## Business Value
Screens get data and live asks.

## Acceptance Criteria
- [x] Types match the policy API.
- [x] The SSE hook reconnects and replays open asks.

## Technical Approach
`src/api/`, TanStack Query.

### Dependencies
- Needs LEASH-090.
- Needs LEASH-118.
- Blocks LEASH-092.
- Blocks LEASH-093.
- Blocks LEASH-094.
- Blocks LEASH-096.
- Blocks LEASH-097.
- Blocks LEASH-128.

## Testing Requirements
Write first: `useAsks` test with a mocked EventSource.

## Related Files
- `solution/app/src/api/client.ts`
- `solution/app/src/api/useAsks.ts`

## Notes
- Types are generated from policy-api.yaml with openapi-typescript (`npm run gen:api` → src/api/schema.d.ts); src/api/schema.test.ts fails when they drift from the contract.

## Out of scope
- Offline mode.

## Review log

### 2026-09-23 — independent agent review
- [x] met — criterion 1: schema.d.ts byte-identical to a fresh generation; the drift test fails on a contract change; contract renames break `tsc`. Minor: no `/api/runs` / `/api/mandates/{id}` reads.
- [ ] not met — criterion 2: a late `/api/asks` response overwrote newer stream events (new asks lost, resolved asks kept — reproduced against the contract mock); a CLOSED stream (e.g. 502 from the dev proxy) was never reopened; events with missing fields threw.
Verdict: returned to in-progress. Fix: stream events are journalled and replayed onto every /api/asks response that started before them; a closed stream reopens with backoff (1 s → 30 s); events are shape-checked; runs and mandate reads added. Four new tests; 17 app tests pass; typecheck clean.

### 2026-09-23 — independent agent review (round 2)
- [x] met — criterion 1 (incl. the new runs/mandate reads).
- [ ] not met — criterion 2: all round-1 findings fixed (stale responses, reopen after CLOSED with backoff 1→30 s, malformed events), but an ask resolved between the hook's reload and the server stream's start point (set ~150 ms after the connection opens) was never removed.
- Minor: journal of 500 could overflow during one pending fetch.
Verdict: returned to in-progress. Fix: after every (re)open the hook reloads once more when the stream has settled (2 s); journal raised to 5000. A fully rigorous alternative needs a contract change (a snapshot-complete event, or a cursor on /api/asks) — noted for LEASH-118's owner. 18 app tests pass.

### 2026-09-23 — independent agent review (round 3)
- [x] met — criterion 1.
- [x] met — criterion 2: both round-2 reproductions converge after the settle reload at server setup delays of 150–1900 ms (real EventSource against a server mimicking events.py); stale settle responses are corrected by the journal; timers cleared on unmount and repeated opens; all round-1/2 probes pass.
- Remaining window found: a first /api/asks slower than 2 s made the settle reload join it instead of fetching fresh, so an ask resolved before the stream's start point could stay. Fixed after review: the settle reload cancels any in-flight load and fetches fresh (`the settle reload is a fresh request even while the first load is still running`). 19 app tests pass; typecheck clean.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
