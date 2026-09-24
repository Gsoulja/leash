# LEASH-127: Deployment and event-day runbook

**Status**: DONE
**Priority**: P0
**Type**: infra
**Estimated Effort**: M
**Milestone**: M5 — Hosted API and release
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-009
**Task ID**: 009-T8
**Blocked by**: LEASH-042, LEASH-122, LEASH-053, LEASH-054, LEASH-064, LEASH-090
**Blocks**: LEASH-128
**Updated**: 2026-09-23

## Description
One command starts database, migrations, seed, policy API, worker, outbox sender, sweeper and app, with health and readiness checks, CORS for the app, structured logs, and a written event-day runbook.

## Business Value
On event day nothing may depend on remembering manual steps.

## Acceptance Criteria
- [x] `docker compose up` (or one script) starts everything; readiness fails until migrations and seed are done.
- [x] Startup runs the seed automatically (`leash.adapters.pack.seed.seed()`, idempotent) — carried over from LEASH-042.
- [x] Health endpoints for API and worker.
- [x] Runbook covers key setup, start, reset (dev only), and recovery.

## Technical Approach
Compose services + `solution/RUNBOOK.md`.

### Dependencies
- Needs LEASH-042.
- Needs LEASH-122.
- Needs LEASH-053.
- Needs LEASH-054.
- Needs LEASH-064.
- Needs LEASH-090.
- Blocks LEASH-128.

## Testing Requirements
Fresh clone → one command → connection check passes against the fake API.

## Related Files
- `solution/docker-compose.yml`
- `solution/RUNBOOK.md`

## Out of scope
- Cloud deployment.

## Implementation note (2026-09-23)
- `solution/docker-compose.yml`:
  - Services: `db` → `migrate` (one-shot `leash-migrate`: Alembic head, then the idempotent pack seed) → `api` (`leash-api`) and `worker` (`leash-worker`).
  - `fake` (profile `fake`) is the fake platform on the real pack.
  - The worker's base URL defaults to the fake, so the live API is reached only when `LEASH_BASE_URL` is set.
- `solution/engine/Dockerfile`: a Node stage builds the customer app, which the API serves at `/`. Build context is the repo root, for `data/`; `Dockerfile.dockerignore` keeps the ignore rules under `solution/`.
- `leash/service.py` combines the policy, read and event routers with:
  - the ask sweeper and a background refresh of the stored mandate snapshots;
  - `/healthz` and `/readyz` (503 until migrated to head, seeded and the event stream is running; the stream starts on its own once the database is ready);
  - CORS limited to `LEASH_CORS_ORIGINS`;
  - the contract error shape for every failure.
- `adapters/postgres/mandates.StoredMandates`: the production MandateSource. It is compiled from each run's stored hard_rules. An unknown or unreadable run raises; it never becomes an empty (approve-everything) mandate.
- Worker: `/healthz` and `/readyz` (a poll reached the platform in the last 60 s) on port 8081.
- `scripts/connection_check.py`: the SCEN0000 connection check. It refuses non-local URLs without `--live`.
- `solution/RUNBOOK.md`: key setup, start, checks, stop and restart, dev-only reset, recovery table, logs.
- Verified with a fresh image as a separate Compose project (`-p leashcheck`, other ports and volume):
  - `--profile fake up --wait` reached all healthy;
  - `migrate` exited 0;
  - API `/readyz` ready, and `/` served the app;
  - the connection check passed (1/1 answered) and `/api/payments` showed the decision;
  - `docker stop` on the worker exited 0 through the graceful path;
  - then `down -v` for that project only.
- Found while verifying: the default database password `leash` makes redaction mask the word "leash" in every log line. The password is now `LEASH_DB_PASSWORD` (default `leash`, so the existing dev volume still works), and the runbook requires a real one for event day.
- Tests: `tests/test_service.py` (readiness before and after migrate and seed, ready without a restart, CORS, the app served), `tests/adapters/test_stored_mandates.py`, and the worker health test.

## Review log

### 2026-09-23 — independent agent review
- [x] met — criterion 1: built and run as its own Compose project; everything healthy in about 10 s. `api` and `worker` wait for `migrate`; `/readyz` requires head, seed and event stream; the seed is a single transaction.
- [x] met — criterion 2: re-running `migrate` left the row counts unchanged; the test runs it twice.
- [x] met — criterion 3: health and readiness endpoints on both services; graceful worker stop exits 0.
- [x] met in coverage — criterion 4. Accuracy gaps:
  - the logs had no authorization ID or verdict and weren't structured;
  - two recovery rows didn't match Compose behaviour;
  - "can't reach live" held only under Compose.
- Also found:
  - the connection check's localhost prefix accepted `localhost.example.com`;
  - for about 1.7 s after a run first appears, `approval_check` raised `LookupError` (noisy hub retries, and 500s during that window);
  - a fresh clone can't build yet because `solution/` is not committed (commits are the owner's call).
- Probed and fine: SCEN0000–0004 all decided through the stack, 44 asks over SSE, no API key in any log, StoredMandates never hands out a looser mandate.
- Residual: `ensure_run` keeps a run's first-event mandate; a mandate cross-check (DEC-003) doesn't exist yet. Theoretical until tightening mid-run exists.
Verdict: all met.

### Follow-ups (2026-09-23)
- Structured JSON logs for API and worker (`config.JsonFormatter`), with `authorization_id` and a final `handled <id>: <path>, verdict <v>` line.
- Writing the JSON formatter exposed a real leak: exception text bypassed redaction. It is now masked like every other log path, with tests.
- `approval_check` loads a just-started run on a miss instead of failing (test).
- The connection check compares the URL's hostname exactly.
- Runbook: rows for a worker failing at startup and for a failed `migrate` under Compose; the live-default caveat outside Compose; the log format.
- 1168 tests pass, mypy clean.
Moved to done on the product owner's standing instruction for this run.
