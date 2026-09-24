# LEASH-159: Run cockpit progress counters are always empty against the live Viseca platform

**Status**: BACKLOG
**Priority**: P1
**Type**: bug
**Estimated Effort**: S
**Milestone**: M5 — Hosted API and release
**Rule source**: Found by manual verification against the hosted Viseca sandbox (2026-09-24)
**Decisions**: none
**Blocked by**: none
**Blocks**: LEASH-128
**Updated**: 2026-09-24

## Description
`solution/engine/src/leash/adapters/http/policy_api.py` reads a nested `counters` object from Viseca's run responses in two places:

- `platform_status()` (used by `GET /api/runs` and `GET /api/runs/{run_id}`): `counters = {k: v for k, v in dict(body.get("counters") or {}).items() if isinstance(v, int)}`.
- The `POST /api/runs` handler after `start_run()`: `counters = {k: v for k, v in dict(started.get("counters") or {}).items() if isinstance(v, int)}`.

Verified live (`solution/postman/apiCalls/07-scenario-runs-create.json`, `08-scenario-runs-get.json`, `13-scenario-runs-get-final.json`), the real `POST /v1/scenario-runs` and `GET /v1/scenario-runs/{id}` responses never include a `counters` key — progress is only available as top-level `generated_event_count`, `delivered_event_count`, `finalized_event_count`, `processed_event_count`, `pending_event_count`, `queued_event_count`, `platform_rejected_count`. So `counters` is always `{}` for a live run. `status` is unaffected (derived correctly from the top-level `status` field, matching `_FINISHED`/`_FAILED`), so the app can tell a run is running/finished, but the numeric progress the README calls out as the "cockpit per run" feature will show nothing for a run against the real platform — it only ever populates against the local fake platform, whose `fake_api/app.py::_counters()` does nest values under `counters`.

## Business Value
The customer app's run cockpit (README: "cockpit per run") is meant to show progress at a glance. Against the real platform it will silently show zero/empty progress for every run, which looks broken during a live demo even though decisions are actually being processed correctly underneath.

## Acceptance Criteria
- [ ] `platform_status()` and the `POST /api/runs` handler read the live API's actual top-level count fields (`generated_event_count`, `delivered_event_count`, `finalized_event_count`, `processed_event_count`, `pending_event_count`, `queued_event_count`, `platform_rejected_count`) and map them into whatever shape `/api/runs` promises its consumers (check `solution/contracts/policy-api.yaml`'s `Run` schema for the exact field names expected by the app).
- [ ] The mapping is written so it degrades gracefully against the local fake platform's differently-shaped (`data.counters`) response too — or the fake platform's response shape is aligned with the live one so only one mapping is needed (see Dependencies).
- [ ] `GET /api/runs/{run_id}` against a live-shaped fixture returns non-empty, correct counts.

## Technical Approach
`solution/engine/src/leash/adapters/http/policy_api.py`, `platform_status()` (~line 394-402) and `start()` (~line 424-461). Extract a single `_run_counters(body: Mapping) -> dict[str, int]` helper that reads the live field names directly (no `data`/`counters` unwrapping needed, per LEASH-158's finding that the live response is already unwrapped), and use it in both places.

### Dependencies
- Shares its root cause with LEASH-158 (same live response shape mismatch) — fix them together if convenient, but they affect different call sites (`connection_check.py` script vs. the app-facing policy API) so are tracked separately.
- Relates to LEASH-066 (built the run-start endpoint) and LEASH-133 (cockpit scoped to one run).
- Blocks LEASH-128 ("Cockpit payments, counts and spending use the same run" criterion needs real counts, not always-empty ones).

## Testing Requirements
Add a test in `solution/engine/tests/adapters/test_policy_api.py` (or the nearest existing coverage for `runs_router`) that feeds `platform_status()` a `get_run` double shaped exactly like the verified live response (top-level count fields, no `counters` key) and asserts the returned counters are non-empty and correct, not `{}`.

## Related Files
- `solution/engine/src/leash/adapters/http/policy_api.py`
- `solution/contracts/policy-api.yaml`
- `solution/engine/tests/fake_api/app.py` (`_counters()` — the differently-shaped local double)
- `solution/postman/apiCalls/07-scenario-runs-create.json`, `08-scenario-runs-get.json`, `13-scenario-runs-get-final.json`

## Out of scope
- Changing the fake platform's response shape (may be worth aligning separately, but not required to fix this bug against the live API).
