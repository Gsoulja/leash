# Leash runbook

One command starts everything. Nothing on event day should depend on remembering a manual step.

| Service | What it does | Health |
| --- | --- | --- |
| `db` | Postgres 17 | `pg_isready` |
| `migrate` | Alembic migrations, then the pack seed. Idempotent. Runs once and exits. | exit code 0 |
| `api` | Policy, read and event endpoints, the ask sweeper, and the built customer app at `/` | `/healthz` (alive), `/readyz` (migrated, seeded, event stream running) |
| `worker` | Long-polls Viseca, decides, POSTs each answer, resends from the outbox | `:8081/healthz` (alive), `:8081/readyz` (a poll reached the platform in the last 60 s) |
| `fake` | Local fake platform on the real pack, profile `fake` only. Never the live API. | — |

Order: `db` healthy → `migrate` completes → `api` and `worker` start. `api` readiness fails until the migrations and the seed are done.

## 1. Key setup (once)

Create `solution/.env`. Compose reads it; never commit it.

```dotenv
TEAM_API_KEY=<the team's bearer key from Viseca>
LEASH_BASE_URL=<the hosted API base URL from Viseca>
LEASH_DB_PASSWORD=<a long random password>
LEASH_CORS_ORIGINS=http://localhost:5173
```

- Under Compose, without `LEASH_BASE_URL` the worker talks to the local fake (`http://fake:9000`), so a forgotten setting can't reach the live platform. Outside Compose (`uv run leash-worker` or `leash-api`) the default is the live URL: always set `LEASH_BASE_URL` there.
- The database password only takes effect when the volume is first created. With the default password (`leash`), log lines show `[redacted]` wherever the word "leash" appears, because secrets are masked in every log line. Set a real password for event day.
- The worker refuses to start if `/v1/bootstrap` reports an API major version other than `0.x` or a data version other than `saw26`.

## 2. Start

Local, against the fake platform:

```bash
docker compose -f solution/docker-compose.yml --profile fake up -d --build --wait
```

Event day, against Viseca (with `.env` set):

```bash
docker compose -f solution/docker-compose.yml up -d --build --wait
```

`--wait` returns once `api` and `worker` report healthy. Then check:

```bash
curl -s localhost:8080/readyz     # {"status":"ready"}
curl -s localhost:8081/readyz     # ready after the worker's first completed poll (up to 25 s)
open http://localhost:8080/       # the customer app
```

Ports can be changed with `LEASH_DB_PORT`, `LEASH_API_PORT`, `LEASH_WORKER_HEALTH_PORT` and `LEASH_FAKE_PORT`.

## 3. Connection check

This confirms the SCEN0000 mandate, starts its run and waits until the worker has answered every purchase.

```bash
cd solution/engine
LEASH_BASE_URL=http://localhost:9000 TEAM_API_KEY=fake-team-key uv run python scripts/connection_check.py
```

It refuses any non-local base URL unless given `--live`. On event day, run it with `--live` only when the team agrees to start the connection-check run.

## 4. Stop and restart

```bash
docker compose -f solution/docker-compose.yml stop worker     # finishes the event in hand, then exits 0
docker compose -f solution/docker-compose.yml up -d --wait    # everything back; migrate re-runs harmlessly
```

## 5. Reset (development only)

These commands delete data. Never run them on event day.

```bash
docker compose -f solution/docker-compose.yml --profile fake down -v   # drops the local database volume
```

The fake platform keeps its state in memory, so restarting `fake` resets it.

## 6. Recovery

| Symptom | What happens / what to do |
| --- | --- |
| Worker crashed or restarted mid-run | Decisions committed but not sent are resent by the outbox (every 2 s, oldest first, a resolve never before its decision). A repeat delivery of the same purchase returns the saved verdict and never counts twice. Just restart the worker. |
| Worker `/readyz` 503 for more than a minute | The platform is unreachable or rejecting the key. Logs show `poll failed … retrying in N s` (backoff up to 30 s). Check `TEAM_API_KEY` and `LEASH_BASE_URL`. |
| Worker keeps restarting, no health endpoint answers | It failed at startup: `/v1/bootstrap` was unreachable, rejected the key, or reported an incompatible version (`IncompatibleApi`). See `docker compose -f solution/docker-compose.yml logs worker`. Fix the key, URL or network; Compose restarts it. |
| A purchase got `decision_timeout` | The watchdog answered a safe `step_up` before `deadline_at`. The customer decides. Look at the stage timings in the worker log (`stage … took … ms`). |
| `invalid_event` answers | The platform sent an event we can't read. Its live ID got a safe `step_up`. Save the log line for Viseca. |
| Log line starting `INTEGRITY:` | Something needs a person: a spend counter mismatch, an unsupported mandate rule, or a confirm whose outcome is unknown. Read the message; it names the IDs involved. |
| Confirm returns `confirm_outcome_unknown` | Viseca may have activated the mandate, but we never got the answer. Check the mandate at Viseca before confirming again. |
| Confirm returns `local_write_failed` | Viseca confirmed; our save failed. Confirm again: it finishes the save without asking Viseca twice. |
| `api` and `worker` never start | `migrate` failed, so Compose won't start the services that depend on it. See `docker compose -f solution/docker-compose.yml logs migrate`, fix the cause, then run `docker compose -f solution/docker-compose.yml up -d --wait`, which re-runs `migrate` and then starts `api` and `worker`. |
| API `/readyz` 503 `migrations not at head` | Only when the API runs without Compose against an unmigrated database: run `uv run leash-migrate` first. |

## 6a. Crash recovery for one purchase (LEASH-131)

Each received purchase is claimed by one worker under a short lease (3 s, refreshed every second while the worker decides; `authorizations.claim_owner` and `claim_expires_at`, measured on the database clock). What happens if the worker dies at each point:

| The worker dies… | What is stored | How it recovers |
| --- | --- | --- |
| before `receive` commits | nothing | The platform redelivers the purchase; it is received and decided as new. |
| after `receive`, before or while reading facts | `received`, claimed by the dead worker | A redelivery that finds the claim still live keeps checking (every 0.2 s): once the lease runs out (within 3 s) it takes the claim over (`reclaimed` in `decision_events`, a `reclaimed an expired claim` log line) and decides. If the owner is alive after all, it sends the owner's stored answer. The watchdog still sends a safe step_up before the deadline if neither happens. |
| inside the decision transaction (lock, snapshot, decide, save) | the transaction rolls back: still `received`, claimed | Same as above: the lease runs out and a redelivery reclaims and decides. |
| after the commit, before sending | the decision and its outbox row | The outbox resends the stored body within 2 s (section 6). A redelivery is answered from the stored decision and never counts twice. |
| after sending, before marking it sent | the decision, outbox row unmarked | The outbox resends the same body, which is harmless. |
| stops gracefully (SIGTERM) | the event in hand is finished first; its claim is released | Nothing to do. If handling is cancelled anyway, the claim is released at once, so a redelivery can take over immediately. |

A worker that only stalls (for example a long pause) and wakes after its lease was taken over can't commit: the stored state has already left `received`, so its commit is refused and it sends the stored decision instead. Spend is counted once.

A purchase is only recovered if the platform delivers it again before its deadline. If it doesn't, the platform's own timeout applies; reconciling that with our records is LEASH-130.

## 7. Logs

```bash
docker compose -f solution/docker-compose.yml logs -f worker api
```

Logs are one JSON object per line: `time`, `level`, `logger`, `message`, and `authorization_id` for anything about one purchase. For each purchase, the worker logs every stage (`stage … took … ms`) and a final `handled <id>: <path>, verdict <verdict>` line. Secrets (the API key and the database password) never appear in any log line.
