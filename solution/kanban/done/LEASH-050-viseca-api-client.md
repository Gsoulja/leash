# LEASH-050: Viseca API client

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M3 — Durable fake-API integration
**Rule source**: Engineering
**Decisions**: DEC-008
**Parent**: LEASH-004
**Task ID**: 004-T1
**Blocked by**: none
**Blocks**: LEASH-053, LEASH-054, LEASH-061, LEASH-122, LEASH-128
**Updated**: 2026-09-23

## Description
httpx client for the hosted API: bearer key, JSON errors under `error`, 200 vs 204 on long-poll, bootstrap and reference data.

## Business Value
All live traffic goes through it.

## Acceptance Criteria
- [x] 204 returns 'no work' without parsing a body.
- [x] Non-2xx raises an error carrying the API's `error` object.
- [x] Timeouts are configurable; the key comes from TEAM_API_KEY and is never logged.
- [x] Covers every endpoint we use: healthz, bootstrap, reference data, history CSV, mandates (create, confirm, get, patch, delete), runs (start, get), decision-requests, decision, resolve, authorizations, events.
- [x] Bootstrap response is parsed into typed settings.

## Technical Approach
`adapters/viseca_api/client.py`.

### Dependencies
- None.
- Blocks LEASH-053.
- Blocks LEASH-054.
- Blocks LEASH-061.
- Blocks LEASH-122.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_204_means_no_work` using a mocked transport.

## Related Files
- `solution/engine/src/leash/adapters/viseca_api/client.py`
- `solution/engine/tests/adapters/test_api_client.py`

## Out of scope
- Retry policy for decisions (LEASH-054).

## Review log

### 2026-09-23 — independent agent review
- [x] met — criterion 1: 204 returns None without calling `.json()`; tested with a non-JSON 204 body.
- [x] met — criterion 2: every non-2xx raises `VisecaApiError` carrying the `error` object (401 tested) or None for non-JSON bodies (502 tested).
- [x] met — criterion 3: timeout via constructor or LEASH_API_TIMEOUT_SECONDS, long-poll timeout = wait + 10 s; key from TEAM_API_KEY; no logging, redacted repr, key absent from error text (caplog at DEBUG).
- [x] met — criterion 4: all 18 calls match technical_details.md methods and paths; healthz sends no key.
- [x] met — criterion 5: typed `BootstrapSettings`; defaults used are recorded in `defaults_used`. The live bootstrap shape remains unconfirmed until the team key is available (event day).
Check: 26 passed; `mypy src --strict` clean. No live API calls.
Verdict: moved to review.
