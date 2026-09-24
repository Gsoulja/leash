# LEASH-158: connection_check.py reads a counters shape the live API never sends, so --live always reports FAILED

**Status**: BACKLOG
**Priority**: P0
**Type**: bug
**Estimated Effort**: S
**Milestone**: M5 — Hosted API and release
**Rule source**: Found by manual verification against the hosted Viseca sandbox (2026-09-24)
**Decisions**: none
**Blocked by**: none
**Blocks**: LEASH-128
**Updated**: 2026-09-24

## Description
`solution/engine/scripts/connection_check.py` polls run progress with:

```python
counters = ((await client.get_run(str(run_id))) or {}).get("data", {}).get("counters", {})
if counters and counters.get("decided") == counters.get("total"):
```

This assumes `GET /v1/scenario-runs/{run_id}` wraps its body in `{"data": {...}}` with a nested `counters` object holding `decided`/`total`. Verified live (four independent calls: `solution/postman/apiCalls/07-scenario-runs-create.json`, `07b-...-retry.json`, `08-scenario-runs-get.json`, `13-scenario-runs-get-final.json`), the real response is **unwrapped** and has **no `counters` key at all** — it returns top-level `status`, `generated_event_count`, `delivered_event_count`, `finalized_event_count`, `processed_event_count`, `pending_event_count`, `queued_event_count`, `platform_rejected_count`.

Because of this, `counters` is always `{}` on the live platform, the success condition is never true, and `check()` loops until `--timeout` and prints `connection check FAILED: the worker did not answer every purchase in time` — even when the run genuinely completed and every purchase was answered. This is precisely the script `technical_details.md` §6 and `RUNBOOK.md` §3 name as the pre-event-day sanity check ("run it with `--live` only when the team agrees to start the connection-check run"), so as written it can never pass against the real platform.

## Business Value
The connection check is the one live/hosted smoke test the team is meant to run before trusting the event-day setup (`RUNBOOK.md` §3). A script that always reports FAILED against the real platform — even on success — either causes false alarm on event day or gets its output distrusted and ignored, defeating its purpose.

## Acceptance Criteria
- [ ] `check()` derives completion from fields the live API actually returns: `status == "completed"` (matches `worker.py`'s own `_RUN_OVER` set) is sufficient and matches how the production worker already detects a finished run.
- [ ] Running `connection_check.py --live` against the real sandbox with a genuinely completed SCEN0000 run prints "connection check passed" and exits 0.
- [ ] A unit/adapter test feeds `check()` a `get_run` double shaped exactly like the real response (no `data` wrapper, no `counters`, `status: "completed"`) and asserts it reports success, not a timeout.

## Technical Approach
`solution/engine/scripts/connection_check.py`, the polling loop in `check()`. Replace the `counters`-based check with the same status-string test `worker.py::_run_over` already uses (`status.lower() in {"completed", "stopped", "finished", "failed", ...}`), or import `_run_over` directly to avoid a second copy of that set.

### Dependencies
- Relates to LEASH-057 (created `connection_check.py`).
- Relates to LEASH-127 (runbook step that calls this script).
- Blocks LEASH-128 (release-readiness gate depends on the live connection check actually working).

## Testing Requirements
Add a test in `solution/engine/tests/` (near existing `connection_check` coverage, or a new `tests/scripts/test_connection_check.py`) that stubs `VisecaClient.get_run` to return the real unwrapped shape with `status: "completed"` and asserts `check()` returns `0` and prints "passed", not "FAILED".

## Related Files
- `solution/engine/scripts/connection_check.py`
- `solution/engine/src/leash/adapters/viseca_api/worker.py` (`_run_over`, the correct reference implementation)
- `solution/postman/apiCalls/07-scenario-runs-create.json`, `07b-scenario-runs-create-retry.json`, `08-scenario-runs-get.json`, `13-scenario-runs-get-final.json`

## Out of scope
- The fake platform's own `/v1/scenario-runs/{run_id}` response shape (which does nest `counters` under `data`) — this ticket is about the live/hosted mismatch only.
