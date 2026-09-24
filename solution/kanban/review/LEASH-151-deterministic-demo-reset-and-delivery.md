# LEASH-151: Deterministic demo reset and delivery

**Status**: REVIEW
**Priority**: P0
**Type**: infra
**Estimated Effort**: M
**Milestone**: M8 — Great demo
**Rule source**: Engineering
**Decisions**: DEC-041, DEC-042
**Parent**: LEASH-144
**Task ID**: 144-T7
**Blocked by**: none
**Blocks**: LEASH-149, LEASH-153
**Updated**: 2026-09-24

## Description
Guarantee that every rehearsal starts from the same clean data and that localhost serves the frontend bundle built from the current source revision.

## Business Value
A stale bundle or leftover run can invalidate the entire demo before the product story begins.

## Acceptance Criteria
- [x] One documented command resets only demo data and loads the approved baseline.
- [x] Reset clears draft/session state, permissions, runs, asks, outbox records and read models consistently.
- [x] Seed data contains no duplicate authorization IDs and passes run-scoped total checks.
- [x] The served frontend exposes its source revision and asset/build identifier.
- [x] Readiness fails when the served bundle revision differs from the expected revision.
- [x] Container startup rebuilds or consumes a deliberately versioned frontend artifact—never an accidental stale volume.
- [x] Reset and readiness complete within the rehearsal budget and produce clear failure messages.

## Technical Approach
Add a guarded demo reset/seed workflow and build metadata endpoint or manifest. Verify the HTML asset hash against the current build during readiness.

### Dependencies
- Blocks LEASH-149.
- Blocks LEASH-153.

## Testing Requirements
Run reset twice and prove identical API state. Add a deployment test that intentionally serves an old asset and expects readiness to fail.

## Related Files
- `solution/docker-compose.yml`
- `solution/app/dist/`
- `solution/engine/migrations/`
- `solution/RUNBOOK.md`

## Out of scope
- Resetting real production or customer data.

## Implementation notes

### Reset (AC1, AC2, AC3, AC7)
`src/leash/adapters/postgres/reset.py`, exposed as `leash-reset` and as a Compose `reset` profile:

```bash
docker compose -f solution/docker-compose.yml --profile reset run --rm reset
DATABASE_URL=... uv run leash-reset --yes        # without Compose
```

- Clears every table the demo writes — `outbox`, `decision_events`, `authorizations`, `runs`,
  `draft_revisions`, `policy_drafts`, `mandate_versions`, `mandates`, `fact_reads` — in one transaction,
  then reloads the pack through the existing idempotent seed. Reference data is upserted, never dropped.
- `decision_events` carries an append-only trigger, so the reset **disables it explicitly** for the
  truncate and re-enables it in the same transaction. A test proves the log is deletable during the
  reset and protected again afterwards; that protection is not something to lose quietly.
- Two guards, because this deletes data: `--yes` (or `LEASH_ALLOW_DEMO_RESET=1`), and a refusal for any
  database host that is not local unless `--live`. Out of scope ("resetting real production or customer
  data") is enforced, not just stated.
- **It checks the baseline instead of assuming one.** `check_baseline` reports leftover rows in any demo
  table, duplicate `authorization_id`s in `auth_history`, a row count that differs from the pack's CSV,
  and any card whose seeded row count or billed total differs from the pack's. A test tampers with one
  amount and asserts the check catches it.
- Idempotent: a test runs it twice and compares full state, which is identical.
- AC7: `reset()` returns its duration, `main()` fails over a 60 s rehearsal budget, and every failure is
  a numbered list rather than a traceback. Measured: **0.2 s** through Compose.

**One reading to flag:** AC3 says "run-scoped total checks". A freshly reset database has no runs yet, so
the scoped total that exists at baseline is per **card** (the scope a run is bound to, `runs.card_id`) —
that is what is checked against `data/authorization_history.csv`. If "run-scoped" was meant as per
scenario, those totals live in `purchase_attempts.csv`, which is not seeded into the database at all.

### Serving the right bundle (AC4, AC5, AC6)
- `solution/app/scripts/stamp.mjs` runs as part of `npm run build` and writes `dist/build.json`:
  `revision` (from `APP_REVISION`), `bundle` (a sha256 over every other file in `dist/`, path included,
  so a renamed asset is a different bundle), `built_at`, file count and total bytes.
- `GET /api/build` returns that stamp, the revision the image expects, and the engine version (AC4).
- `/readyz` returns **503** when the served stamp's revision differs from `LEASH_APP_REVISION`, or when
  the bundle carries no stamp at all — the exact shape an accidentally mounted stale `dist/` takes. The
  message names both revisions and says what to do. With no expected revision configured (plain
  `uv run leash-api`, `npm run dev`) there is nothing to compare and nothing fails.
- The Dockerfile takes an `APP_REVISION` build arg, `rm -rf dist` before building so no stale bundle can
  be inherited, stamps the build with it, and carries it into the runtime as `LEASH_APP_REVISION`.
  Compose passes it through (`APP_REVISION=$(git rev-parse --short HEAD)`).

**Verified against real containers, not only in tests:**

```
image build.json      → {"revision": "6a7bd7a", "bundle": "2fb5c8bf5733e80e", ...}
image env             → LEASH_APP_REVISION=6a7bd7a
matching bundle       → /readyz 200 {"status":"ready"}
/api/build            → {"expected_app_revision":"6a7bd7a","app":{"revision":"6a7bd7a",...},"problem":null}
stale dist mounted    → /readyz 503 {"reasons":["the served bundle is revision '0000old', this image
                          expects '6a7bd7a'; rebuild the app image, or remove the volume shadowing
                          solution/app/dist"]}
compose reset         → reset OK: baseline loaded and checked in 0.2s
reset without --yes   → reset FAILED: this deletes demo data: pass --yes, or set LEASH_ALLOW_DEMO_RESET=1
```

Files outside Related Files: `solution/engine/src/leash/adapters/postgres/reset.py`,
`solution/engine/tests/adapters/test_reset.py`, `solution/engine/src/leash/service.py` (the `/api/build`
endpoint and the readiness gate), `solution/engine/tests/test_service.py`,
`solution/engine/Dockerfile`, `solution/engine/pyproject.toml`, `solution/app/scripts/stamp.mjs`,
`solution/app/package.json`. `solution/app/dist/` stays gitignored — it is built inside the image.

`src/leash/policy/registry.py` also gained a `NOT_A_FIELD_MEANING` entry for the new `reset` module —
the registry refuses to pass until every module is classified, which is what keeps something new off the
live decision path by accident. No field fingerprint moved: `reset.py` is not in `SHARED_ENFORCEMENT` and
not hashed, and no existing module changed.

Verification: `tests/adapters/test_reset.py` 10 passed, `tests/test_service.py` 11 passed,
`tests/policy` + migrations 350 passed together, `mypy src` clean on 66 files, plus the container checks
above. (A full-suite run mid-way showed two registry failures; they were another agent's in-flight
mutations of `env.py` during its review of LEASH-135, and `tests/policy/test_registry.py` is green on a
quiet tree.)

## Review log

### 2026-09-24 — independent agent review
AC1, AC3, AC4, AC5, AC7 `met`; **AC2 and AC6 `not met`**, plus a **guard bypass**. All fixed.

The reviewer verified the good parts by reproduction: the familiarity matview is genuinely refreshed
(it desynced it deliberately — 913 rows vs 937 live — and the reset restored 937/937); `truncate …
cascade` reaches nothing outside the list; there is no `asks` table, so clearing `authorizations` and
`decision_events` really does clear ask state; duplicating a row in a copy of the pack CSV is caught by
the row-count comparison; a card present in the database but absent from the pack is caught; refunds and
`Decimal`/`numeric` comparison are consistent. `stamp.mjs` fails loudly on a missing or empty `dist/`.
The "run-scoped = per-card" reading was accepted.

**The guard bypass (most serious).** `_is_local` read `urlsplit(url).hostname or ""` and treated `""` as
local. libpq — and asyncpg — fall back to a `?host=` parameter and then to `PGHOST` for a DSN whose
hostname parses as `None`, which is how operations tooling normally points at an environment. The
reviewer connected to a remote server through `postgresql:///leash?host=…` and through `PGHOST`, and
**destroyed data with no `--live`**. Locality is now resolved the way libpq resolves it
(`effective_host`: URL host → `?host=` → `PGHOST` → unix socket), with parametrised tests for both
bypasses and for the local forms that must still work. Verified in a container: the same DSN shape now
prints `refusing to reset 'prod.viseca.example', which is not a local database, without --live`.

**AC2 (a): the reset broke the running API's event stream.** `truncate … restart identity` reset
`decision_events.seq` to 1, but `EventHub` keeps an in-process high-water mark — so after a reset done
the documented way (which does not restart `api`), the next rehearsal's first *N* `payment.decided` and
`ask.created` events were silently dropped, *N* being the previous run's event count. Reproduced by the
reviewer. `restart identity` is gone: the sequence is an append-only cursor and keeping it climbing costs
nothing. Pinned by `test_the_event_cursor_keeps_climbing_across_a_reset`.

**AC2 (b): the table list was self-referential.** Both the clearing test and `check_baseline` iterate
`DEMO_TABLES`, so removing `"outbox"` from it left all ten tests green while outbox rows survived every
reset — and AC2 names the outbox. Two tests added: one asserts the list literally by name, the other
reads every table out of `pg_tables` and requires each to be either in `DEMO_TABLES` or in a `KEPT` map
with its reason. A new table now fails the suite until someone classifies it. `model_releases` is in
`KEPT` (a registered release is configuration, not demo state) — the reviewer was right that it would
otherwise have survived silently once LEASH-081 lands.

**AC6: the gate trusted a stamp that travels inside the thing it describes.** Two bypasses, both
reproduced against the real image: Compose defaults `APP_REVISION` to `dev`, so every build stamps and
expects the same string and last week's `dev` bundle passed; and replacing the whole `dist/` while
copying `build.json` verbatim also passed, because the `bundle` hash was written at build time and never
recomputed. `/readyz` now recomputes the content hash from the files actually on disk (the same
path-plus-bytes hash `stamp.mjs` writes) and compares it with the stamp's own. Re-running the reviewer's
swap against the rebuilt image:

```
503 {"reasons":["the served files hash to bce227e4e5ba9380, but build.json says 2fb5c8bf5733e80e;
     the bundle is not the one that was built — rebuild the app image, or remove the volume
     shadowing solution/app/dist"]}
```

That check runs even with no `LEASH_APP_REVISION` configured: a bundle contradicting its own stamp is
wrong under any configuration.

**AC6: the build was not hermetic.** There was no `.dockerignore`, so `COPY solution/app/ ./` shipped the
host's 150 MB `node_modules` over the layer `npm ci` had just produced — the artifact `APP_REVISION`
labels was built from whatever the developer happened to have installed. Added `.dockerignore` at the
repository root; the rebuilt image now contains only `dist` under `solution/app`.

**AC7 and AC1, smaller:** the three likeliest rehearsal failures (database down, wrong password, missing
pack) printed tracebacks, contradicting this ticket's own claim — `main()` now reports each on one line
with the action. `BaselineNotClean` now says what to do next. The Compose `reset` service depended only
on `db`, so on a fresh volume it died with a raw `UndefinedTableError`; it now waits for `migrate`.

Left as noted: a history row whose merchant or timestamp changed while count and total stay equal is not
caught, and the budget is a retrospective assertion (a *hung* reset would not trip it — no timeout
anywhere). Both are true and neither is worth the machinery at this size.

Verification after round 2: 22 reset tests, 14 service tests, `mypy src` clean, plus container checks —
compose reset OK in 0.2 s, the whole-dist swap refused, the remote-DSN bypass refused, the image
hermetic.
