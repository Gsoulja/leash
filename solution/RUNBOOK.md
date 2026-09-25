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

Local platform simulation with the OpenRouter chat model and Jev checks (set `OPENROUTER_API_KEY` in `solution/.env`):

```bash
LEASH_DB_PORT=55443 LEASH_API_PORT=8090 LEASH_WORKER_HEALTH_PORT=8181 \
LEASH_ASSISTANT_PORT=8100 LEASH_FAKE_PORT=19101 \
docker compose -p leash-local -f solution/docker-compose.yml \
  -f solution/docker-compose.local.yml --profile fake up -d --build --wait
```

Open http://localhost:8090/, choose **Agent**, and select a supplied task. Send the customer instruction,
answer clarifications, review **Must follow / May choose / Must ask**, explicitly confirm, then click
**Start shopping simulation**. Confirmation alone does not start a run. The cockpit shows each actual
checkout, the deterministic decision, customer intervention where needed, and the platform outcome.

The override forces API/worker traffic to `http://fake:9000`, even if `.env` contains the hosted URL.
`leash-local` has its own database volume. Stop any older app services using ports 8090/8181/8100 first;
keep their volumes. The assistant calls Gemini through OpenRouter; Jev checks rules and merchant text.
For a fully offline rehearsal set `LEASH_ASSISTANT_MODEL=offline`, `LEASH_FACT_READER=regex` and
`LEASH_RULE_CLASSIFIER=keyword`.
Scenario selection is enabled only in this local mode and derives the customer card from the supplied
attempts. Background preferences remain context, not permission.

The fake reads the original five scenarios and 45 purchases in `data/`; it does not rewrite them or
supply an answer key. It follows the documented request schema, snapshots, queue, 8-second deadline,
120-second customer window, decisions and outcomes. Unspecified hosted behavior is modeled conservatively
in `tests/fake_api/app.py`, not claimed as observed hosted behavior. With the local override, simulator
state is retained in `output/local-platform-state/platform.json`; permission references, runs and decisions
survive restarts. The JSON file is for this single local simulator process, not a shared production store.
The supplied `data/` remains read-only. For one explicitly declared rolling period, the counter uses that
window and simulated timestamps; with no period or multiple periods it returns null instead of a misleading
lifetime total. The engine still computes its own ledger independently. For app-only updates, restart just
`api assistant worker` with `--no-deps` to avoid interrupting the decision queue.


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

## 5. Reset to the demo baseline (LEASH-151)

One command between rehearsals. It clears everything the demo writes, reloads the challenge pack, and
then **checks** the result rather than assuming it — no leftover rows, no duplicate authorization IDs,
and per-card history totals equal to `data/authorization_history.csv`. It prints how long it took and
fails with a numbered list if the baseline is not clean.

```bash
docker compose -f solution/docker-compose.yml --profile reset run --rm reset
```

Locally, without Compose:

```bash
DATABASE_URL=postgresql://leash:leash@localhost:55432/leash uv run leash-reset --yes
```

Two guards, because it deletes data: it needs `--yes` (or `LEASH_ALLOW_DEMO_RESET=1`), and it refuses a
database host that is not local unless given `--live`. "Local" is resolved the way libpq resolves it —
the URL's host, then a `?host=` parameter, then `PGHOST`, then a unix socket — so
`DATABASE_URL=postgresql:///leash` with `PGHOST` pointing at a real server is refused, not mistaken for
localhost. The Compose service name `db` counts as local; on a machine where `db` resolves to something
real, `--yes` is the guard that remains. It clears drafts and their revisions, mandates
and versions, runs, authorizations, the append-only decision log, the outbox and the reader cache —
lifting the log's append-only trigger only for that truncate, and putting it back in the same
transaction. Reference data is upserted by the seed, never dropped.

It is idempotent: running it twice leaves identical state, and a test asserts exactly that.

Dropping the whole volume still works and is heavier (the migrations run again afterwards):

```bash
docker compose -f solution/docker-compose.yml --profile fake down -v   # drops the local database volume
```

The fake platform keeps its state in memory, so restarting `fake` resets it.

## 5a. Serving the right frontend

The image always rebuilds the app and stamps `dist/build.json` with the revision it was built from;
`dist/` is never copied in from the build context and never mounted. Build with the commit you are
demoing so the stamp is meaningful:

```bash
APP_REVISION=$(git rev-parse --short HEAD) \
  docker compose -f solution/docker-compose.yml --profile fake up -d --build --wait
curl -s localhost:8080/api/build      # what is actually being served
```

`/api/build` returns the bundle's own `revision`, its content `bundle` hash, the build time, and the
revision the image expects. **`/readyz` returns 503** when either check fails:

- the stamp's **revision** differs from the image's `LEASH_APP_REVISION`, or there is no stamp at all;
- the **files actually on disk** do not hash to what `build.json` claims.

The second check is the one that matters when `APP_REVISION` is left at its default: every build then
stamps `dev`, so a stale `dist/` mounted over the image would carry a matching revision string. The
content hash is recomputed from the served files on each readiness call, so a swapped, added or missing
asset is caught whatever the stamp says. Both messages name the action: rebuild the image, or remove the
volume.

With no `LEASH_APP_REVISION` set (plain `uv run leash-api`, or `npm run dev`) there is no revision to
compare — but a bundle that contradicts its own stamp is still reported, because that is wrong under any
configuration.

Set `APP_REVISION` anyway when you build for a rehearsal: `dev` tells nobody which commit is on screen.

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

## 8. The external-agent boundary, and what it does not prove (LEASH-102)

Leash owns permission and the verdict. An external shopping agent owns product search and order
preparation; in the challenge, Viseca's simulator plays it. What is demonstrated here is the
**handoff and the payment path**, not an integration with a real shopping agent.

**What the handoff carries.** `POST /api/runs` takes a `scenario_id` and a `mandate_id` and nothing
else. The run stores the mandate snapshot the platform returns, and the version it used
(`runs.mandate_version`), so a run keeps the permission it started with (DEC-003). Retrying the same
start returns the run that already exists rather than minting a second one, so a dropped response does
not produce two sets of counters. The key includes the mandate version, so tightening and starting
again is a *new* run under the new version — that is the intended journey, not a retry. This is an
application-level check with no unique index behind it, so two simultaneous starts can still both miss
it; one customer pressing one button is not that case, and it fails towards an extra run, never a lost
one.

**Where authority is not.** Two real controls, and one thing that is *not* a control yet. The assistant
runs as its own process with no database credential and no import of the decision path, and the
browser-facing proxy forwards only `POST /api/permission/*`, so the chat screen's own calls cannot
carry a start or an answer. What does **not** hold today is credential scope: the engine API has no
authentication at all, and the assistant container already reaches it at `LEASH_POLICY_URL` to create
drafts — nothing but the absence of a method on its client class stops that process from calling
`/api/runs` on the same connection. That is a code-shape guarantee, not a reachability one; read the
"credential scope" item below as the open hole it is. Nothing the agent writes changes the rules: the mandate inside the live event
decides that purchase, the agent's task text is never re-interpreted, and merchant or item text is
data. An event carrying a mandate that differs from the run's snapshot is logged as an INTEGRITY line
and changes nothing.

**A cart that changed behind an answer.** A redelivery of the same live `authorization_id` is treated
as a retry only while the terms match — the shop, the amount and the basket the verdict was given on.
If any of them differ, the stored decision is left exactly as it was (DEC-003), an `integrity_alert` is
written to `decision_events` naming each difference, an `INTEGRITY:` line is logged, and this delivery
is answered with a `step_up` instead of the saved verdict. An approval covers the terms it was checked
against and nothing else. If the platform had already recorded an answer it refuses ours with `409
already_decided`, which is the expected outcome and appears in the logs as a failed send; the point of
the step_up is the case where our first answer never arrived.

**What acceptance does not mean.** A verdict is a decision about permission, not a statement about the
product, the merchant's honesty, or whether anything was delivered. A local `approve` is not platform
acceptance, and platform acceptance is not settlement or fulfilment.

**Open before production.** None of these are answered by simulator evidence:

- **Agent identity.** The simulator is trusted because it is the platform. A real agent needs an
  identity bound to the authority — a key, a registered agent, or an attested workload.
- **Credential scope.** Today a run is started by a backend holding the team API key. A production
  handoff needs a credential scoped to one task, one amount and one expiry, that the agent cannot
  widen by presenting it elsewhere.
- **Authoritative checkout source.** We are given the checkout by the platform. Outside the challenge,
  something must establish that the cart presented for payment is the cart the merchant will fulfil.
- **Payment-path bypass.** Here, every purchase arrives through the platform's queue, so there is no
  other path. In production the control is only as good as the guarantee that no charge can reach the
  card without passing through it.
- **Authenticated consent.** The prototype has no login (DEC-019). Confirmation must be authenticated
  before any of this is a real permission (LEASH-140, LEASH-143).

## Model selection and benchmark

Permission drafting uses Gemini 3.8 Flash on OpenRouter with low reasoning and latency routing.
Jev replaces the local Laya reader and supplies all shop-text facts, including sizes and return windows.
It makes one typed request per purchase, with a one-second HTTP timeout and the engine's overall deadline.
There is no regex merge or fallback in the Jev path. Provider errors, invalid or ambiguous extractions,
and input beyond the reader's bounds reach the existing safe customer-confirmation path.
Regex remains an explicitly selected offline/benchmark baseline; a missing OpenRouter key fails startup.
Jev also checks
rule proposals in shadow mode (`LEASH_JEV_RULE_MODE=shadow`): the benchmark found false rejections,
so these checks do not block drafts until calibrated. `enforce` enables the experimental blocking check.
See [the measured comparison and reproduction command](docs/openrouter-benchmark.md).

For the full-reader diagnostic, set `OPENROUTER_API_KEY` in the process environment and run from `solution/engine`:
`PYTHONPATH=src:tests .venv/bin/python -m evals.jev --output ../../output/jev-full-reader.json`.
Size choices come from source tokens and standard clothing labels. Return choices cover literal numeric
day/week counts and common spelled-out windows. Unsupported values (such as an ambiguous calendar month),
conflicting selected sizes and low-confidence extractions request confirmation rather than guessing.
The reader caps input at 16,000 characters, 64 lines and 128 distinct candidate tokens per line.
