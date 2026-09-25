# LEASH-159: Run cockpit progress counters are always empty against the live Viseca platform

**Status**: DONE
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
- [x] `platform_status()` and the `POST /api/runs` handler read the live API's actual top-level count fields (`generated_event_count`, `delivered_event_count`, `finalized_event_count`, `processed_event_count`, `pending_event_count`, `queued_event_count`, `platform_rejected_count`) and map them into whatever shape `/api/runs` promises its consumers (check `solution/contracts/policy-api.yaml`'s `Run` schema for the exact field names expected by the app).
- [x] The mapping is written so it degrades gracefully against the local fake platform's differently-shaped (`data.counters`) response too — or the fake platform's response shape is aligned with the live one so only one mapping is needed (see Dependencies).
- [x] `GET /api/runs/{run_id}` against a live-shaped fixture returns non-empty, correct counts.

## Resolution (2026-09-24)
`_run_counters(body)` in `policy_api.py` reads the nested `counters` object when the platform sent one and otherwise collects the live API's top-level `*_count` fields; `platform_status()` and the `POST /api/runs` handler both use it. Names are passed through as the platform spells them, which `policy-api.yaml`'s free-form `counters` map (`additionalProperties: integer`) already allows, so no contract or app change was needed and the fake platform keeps working unchanged.

Covered by `tests/adapters/test_runs.py::test_live_shaped_run_reports_its_counts` and `::test_fake_platform_counters_still_reported`.

### Independent review (2026-09-24)
All three criteria met. Review found two gaps, both closed: the `POST /api/runs` call site had no live-shaped test
(`test_live_shaped_start_reports_its_counts`), and `_run_counters` trusted the platform's `counters` field — a non-dict
raised outside `platform_status()`'s try/except (500 on `GET /api/runs`) and a bool passed the `isinstance(v, int)`
filter, breaking the contract's `additionalProperties: integer`. It now drops both
(`test_unusable_platform_counts_are_dropped_not_served`).

Noted, not fixed here (outside this ticket):
- The app never rendered these counts: `Cockpit.tsx` shows `run.status` only, so this ticket makes the API correct but
  does not by itself deliver "progress at a glance" — that belongs with the cockpit work (LEASH-133).
- `solution/app/e2e/journey.spec.ts:30` still polls `c.decided === c.total`. It runs against the fake platform only, so
  it works today, but it would hang against a live-shaped API.

## Technical Approach
`solution/engine/src/leash/adapters/http/policy_api.py`, `platform_status()` (~line 394-402) and `start()` (~line 424-461). Extract a single `_run_counters(body: Mapping) -> dict[str, int]` helper that reads the live field names directly (no `data`/`counters` unwrapping needed, per LEASH-158's finding that the live response is already unwrapped), and use it in both places.

### Dependencies
- Shares its root cause with LEASH-158 (same live response shape mismatch) — fix them together if convenient, but they affect different call sites (`connection_check.py` script vs. the app-facing policy API) so are tracked separately.
- Relates to LEASH-066 (built the run-start endpoint) and LEASH-133 (cockpit scoped to one run).
- Blocks LEASH-128 (evidence: real counts for the "Cockpit payments, counts and spending use the same run" criterion).

## Testing Requirements
Add a test in `solution/engine/tests/adapters/test_policy_api.py` (or the nearest existing coverage for `runs_router`) that feeds `platform_status()` a `get_run` double shaped exactly like the verified live response (top-level count fields, no `counters` key) and asserts the returned counters are non-empty and correct, not `{}`.

## Related Files
- `solution/engine/src/leash/adapters/http/policy_api.py`
- `solution/contracts/policy-api.yaml`
- `solution/engine/tests/fake_api/app.py` (`_counters()` — the differently-shaped local double)
- `solution/postman/apiCalls/07-scenario-runs-create.json`, `08-scenario-runs-get.json`, `13-scenario-runs-get-final.json`

## Out of scope
- Changing the fake platform's response shape (may be worth aligning separately, but not required to fix this bug against the live API).
