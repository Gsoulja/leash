# LEASH-158: connection_check.py reads a counters shape the live API never sends, so --live always reports FAILED

**Status**: DONE
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
- [x] `check()` derives completion from fields the live API actually returns: `status == "completed"` (matches `worker.py`'s own `_RUN_OVER` set) is sufficient and matches how the production worker already detects a finished run.
- [ ] Running `connection_check.py --live` against the real sandbox with a genuinely completed SCEN0000 run prints "connection check passed" and exits 0.
- [x] A unit/adapter test feeds `check()` a `get_run` double shaped exactly like the real response (no `data` wrapper, no `counters`, `status: "completed"`) and asserts it reports success, not a timeout.

## Resolution (2026-09-24)
`check()` now calls `worker.run_over(progress)` — the same status test the production worker uses — instead of comparing `data.counters.decided` to `.total`. `worker._run_over` was renamed `run_over` (its only caller moved with it) so the script reuses it rather than copying the status set. The success line prints whichever progress shape the platform sent (live `*_event_count` fields, or the fake platform's nested `counters`). `run_over` also covers `failed`/`stopped`/`expired`, which end the polling but are not a pass: those exit 1 with the platform's status, so a broken run is never reported as a working connection.

Covered by `tests/scripts/test_connection_check.py`: live-shaped completed run passes, a run that never finishes fails, a run that ends `failed` fails, the fake platform's nested shape still passes.

**Not verified:** the `--live` run against the real sandbox (AC 2) — that starts a scored run. Carried to LEASH-114 (live rehearsal, event day) as an explicit criterion; closed here on the customer's call with that criterion open.

### Independent review (2026-09-24)
Both criteria that can be checked offline are met; AC 2 stays open (a `--live` run is scored). Review found the
failed-run test vacuous — it passed with the whole detection branch disabled, because the timeout path also returns 1
and prints "FAILED". It now asserts the platform's status in the message (`ended failed`) and goes red when the branch
is disabled. The module docstring and `RUNBOOK.md` claimed the script "waits until the worker has answered every
purchase"; it waits for the platform to report the run completed and prints the platform's counts without re-checking
them — the docstring now says so. Asserting `finalized_event_count == generated_event_count` was considered and left
out: AC 1 blesses the status test, and the pass/fail meaning of those counts on a scored run is not established.

## Technical Approach
`solution/engine/scripts/connection_check.py`, the polling loop in `check()`. Replace the `counters`-based check with the same status-string test `worker.py::_run_over` already uses (`status.lower() in {"completed", "stopped", "finished", "failed", ...}`), or import `_run_over` directly to avoid a second copy of that set.

### Dependencies
- Relates to LEASH-057 (created `connection_check.py`).
- Relates to LEASH-127 (runbook step that calls this script).
- Blocks LEASH-128 (evidence: a working live connection check).

## Testing Requirements
Add a test in `solution/engine/tests/` (near existing `connection_check` coverage, or a new `tests/scripts/test_connection_check.py`) that stubs `VisecaClient.get_run` to return the real unwrapped shape with `status: "completed"` and asserts `check()` returns `0` and prints "passed", not "FAILED".

## Related Files
- `solution/engine/scripts/connection_check.py`
- `solution/engine/src/leash/adapters/viseca_api/worker.py` (`_run_over`, the correct reference implementation)
- `solution/postman/apiCalls/07-scenario-runs-create.json`, `07b-scenario-runs-create-retry.json`, `08-scenario-runs-get.json`, `13-scenario-runs-get-final.json`

## Out of scope
- The fake platform's own `/v1/scenario-runs/{run_id}` response shape (which does nest `counters` under `data`) — this ticket is about the live/hosted mismatch only.
