# LEASH-053: Long-poll worker

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M3 — Durable fake-API integration
**Rule source**: Engineering
**Decisions**: DEC-007
**Parent**: LEASH-004
**Task ID**: 004-T4
**Blocked by**: LEASH-050, LEASH-051, LEASH-052, LEASH-044
**Blocks**: LEASH-056, LEASH-127, LEASH-128
**Updated**: 2026-09-23

## Description
Loop: poll /decision-requests/next, handle 204 by checking run progress, decide each event, keep polling while asks are open.

## Business Value
The component the hosted simulator actually talks to.

## Acceptance Criteria
- [x] 204 → check run progress, poll again.
- [x] Errors are logged and retried with backoff.
- [x] Asks never block the loop.
- [x] Graceful shutdown finishes the current event.
- [x] The decision is POSTed immediately after commit; the outbox is only for recovery.

## Technical Approach
`adapters/viseca_api/worker.py`, run with `uv run leash-worker`.

### Dependencies
- Needs LEASH-050.
- Needs LEASH-051.
- Needs LEASH-052.
- Needs LEASH-044.
- Blocks LEASH-056.
- Blocks LEASH-127.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_worker_keeps_polling_while_ask_open` against the fake API.

## Related Files
- `solution/engine/src/leash/adapters/viseca_api/worker.py`
- `solution/engine/tests/adapters/test_worker.py`

## Out of scope
- Scheduling multiple runs in parallel.

## Notes (2026-09-23, from LEASH-121)
- Turn each polled envelope into a request with `adapters/viseca_api/translate.request_from_envelope(envelope, validate=...)` — the same path the SCEN0000 offline slice proves. On `InvalidEvent` with a readable ID, answer with `invalid_event_response`.

## Implementation note (2026-09-23)
- `adapters/viseca_api/worker.py` holds the `Worker` loop, `ApiSender` (DecidePurchase's Sender, POSTing `/decision`), and `main` (`uv run leash-worker`). `main` wires Settings, bootstrap, Postgres, `PostgresDecisionStore`, `RegexReader`, `DecidePurchase`, the event schema, SIGINT/SIGTERM → `stop()`, and an outbox recovery pass every 2 s.
- The loop:
  - Envelopes go through `request_from_envelope`.
  - A 204 checks run progress when a run ID was given (stops when the run is over), otherwise it polls again.
  - An unreadable event with a live ID gets `invalid_event_response`.
  - A handler crash is logged and the loop continues.
- Poll and progress errors back off exponentially (1 s doubling to 30 s), and the backoff resets after a success.
- Shutdown: `stop()` abandons a poll in progress and finishes the event being handled. That event also finishes if the task is cancelled (shielded).
- `adapters/postgres/unit_of_work.PostgresDecisionStore` is the DecisionStore port on Postgres:
  - `receive` (which first records an unknown run from the event), `decide`, `mark_sent`;
  - `record_fallback`: a waiting step_up with its outbox row, only if nothing committed, otherwise it returns what did commit.
- `repository.ensure_run` was added because the real-Postgres worker test showed every purchase of an unregistered run failing the `runs` foreign key and falling back to step_up. The run and the event's mandate snapshot are recorded on first sight; runs we start are LEASH-066.
- `Outcome` (decide_purchase) became a read-only protocol so the frozen `DecisionOutcome` satisfies it.
- Registry lock re-pinned (shared modules changed; no field meaning changed).

## Review log

### 2026-09-23 — independent agent review
- [x] met — criterion 1: a 204 checks progress only when a run ID is given and stops on a finished status or `remaining == 0`. Whether the live API reports those fields that way can't be checked offline.
- [x] met — criterion 2: probe backoff `[1, 2, 4, 8, 16, 30, 30, 30]`, reset after a success. Failed progress checks also back off, and handler crashes don't end the loop.
- [x] met — criterion 3: step_ups are never awaited. Later purchases were decided while an ask stayed open, on both the fake and Postgres.
- [x] met — criterion 4: stop during a poll, stop during an event and task cancellation all tested.
- [x] met — criterion 5: commit → send → mark_sent, and every Postgres outbox row is sent with `attempts == 1`. With a lost first POST and repeat delivery, each event was decided once. The watchdog path answered in time with a slow reader, a held lock and a lock timeout. Concurrent `ensure_run` calls wrote one row per run and never override the event's mandate.
- Minor, fixed afterwards: `stop()` now interrupts a backoff wait, and any error while answering an unreadable event is logged instead of ending the loop. Tests: `test_stop_interrupts_a_backoff_wait` and `test_a_failing_invalid_event_answer_never_ends_the_loop`. 1089 tests pass, mypy clean.
- [?] unverifiable offline: `main` wiring against the live API. The default schema path assumes the worker runs from `solution/engine` (overridable with `LEASH_EVENT_SCHEMA`).
Verdict: all met. Moved to done on the product owner's standing instruction for this run.
