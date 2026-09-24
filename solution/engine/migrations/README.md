# Migrations

Plain SQL through Alembic, one revision per file in `versions/`, applied by `leash-migrate`
(`leash.adapters.postgres.migrate`), which then runs the idempotent pack seed. Compose runs it before
the API and the worker, and `/readyz` fails until it has finished.

```bash
uv run leash-migrate                  # migrations + pack seed, idempotent
uv run alembic upgrade 0007           # stop at a revision (a staged deploy)
uv run alembic downgrade -1           # back one revision
```

## Every change is safe on a populated database

A migration is written for a database that already holds rows, because that is the only kind that
matters in production. The rules, in the order they bite:

1. **Expand before you require.** Add a column nullable, in its own revision. A `NOT NULL` column with
   no default is rejected outright the moment the table holds one row — that was `0002`'s bug
   (LEASH-135).
2. **Backfill from something that already exists**, never from a guess. `0008` rebuilds each missing
   `purchase` from the raw event the decision was made on, using the same translator the worker uses.
3. **Validate, then contract.** Count the rows that are still wrong and refuse with that number before
   adding the constraint. A guessed amount or basket would feed straight into spend, familiarity and
   duplicate checks, so a row that cannot be rebuilt stops the migration instead.
4. **Never rewrite a table under a lock you cannot bound.** `env.py` sets `lock_timeout` and
   `statement_timeout` for every revision, so a blocked migration fails and rolls back rather than
   queueing every writer behind it.

### Rolling deploys

Because expand and contract are separate revisions, a populated database is upgraded in three steps:

1. `alembic upgrade 0007` — the column exists and is optional.
2. Roll out the application version that writes it. Old and new instances can both run here: the old
   one omits the column, the new one fills it.
3. `alembic upgrade head` — the backfill runs and the column becomes required.

Doing 1 and 3 together is fine on an empty database and is what local development and CI do.

## Downgrade policy

**Every revision downgrades cleanly on an empty database. Most of them do not on a populated one.** That
distinction is the policy, because an empty database is not the case that matters. Each revision states
its own downgrade cost in its docstring; this table is the summary.

| Revision | Downgrade on a populated database |
| --- | --- |
| `0008` purchase backfill | **Safe.** Drops only the `NOT NULL`; every backfilled value stays, and the previous application version can insert again. |
| `0007` draft revisions | **Loses data.** Drops `draft_revisions`: superseded proposals, transcripts and the retained context bundles — the evidence behind a confirmed mandate. |
| `0006` authorization claims | **Can be impossible.** Narrows `decision_events_kind_check` back to the kinds before `'reclaimed'`. On a database where any worker ever reclaimed an expired claim, an existing row violates it and the downgrade fails — and that row cannot be deleted, because the table is append-only by trigger. The only ways back are a restore from backup or a new forward revision. |
| `0005` draft answers | **Loses data.** Drops `policy_drafts.answers`; the customer's answers exist nowhere else, and re-upgrading leaves them `[]`. |
| `0004` policy drafts | **Loses data.** Drops `policy_drafts` whole, including every submitted `platform_body` — the evidence of what was posted to Viseca. |
| `0003` outbox retry | Safe: drops columns the outbox adds. |
| `0002` purchase column | **Loses data.** Drops the `purchase` column; `0008` can rebuild it from the stored events, so this is recoverable rather than lost outright. |
| `0001` initial | **Destroys everything**, `decision_events` included. Nothing can rebuild the audit log. |

Two tests hold this table honest, rather than the table being an assertion on its own:
`test_every_revision_downgrades_back_to_the_previous_one` walks the whole chain down to `base` and back
up on an **empty** database, and `test_a_reclaimed_event_blocks_the_downgrade_past_0006` pins `0006`'s
documented failure on a populated one.

**Backup evidence.** Running a downgrade marked "loses data", "can be impossible" or "destroys
everything" in an environment that holds real data requires a verified backup first: take the dump,
restore it somewhere else, check the row counts of every table the revision touches, and record where the
dump lives and who checked it. Without that evidence the correct action is to roll the *application* back
and leave the schema alone — a newer schema serving an older application is exactly what the
expand/contract split is designed for.

Reversing a revision is a repair path, not a deploy step. A mistake in production is normally fixed by a
new forward revision.

## Bounds and settings

| Variable | Default | What it bounds |
| --- | --- | --- |
| `LEASH_MIGRATION_LOCK_TIMEOUT` | `5s` | How long a migration waits for a lock before failing |
| `LEASH_MIGRATION_STATEMENT_TIMEOUT` | `300s` | How long any single statement in it may run |

Both take a Postgres interval (`250ms`, `5s`, `30min`); anything else is a configuration error rather
than a string spliced into SQL. Raise them deliberately for a long backfill window.

## Checks

`tests/adapters/test_migrations.py` upgrades an **empty** and a **populated** `0001` database to head,
checks the rebuilt `Purchase` equals what the translator makes of the same event, proves the column is
optional between `0002` and `0008`, proves an unrebuildable row stops the upgrade naming that row, proves
the lock bound really applies by holding a conflicting lock, and walks the downgrade chain.

The registry pins `migrations/versions/*` and `migrations/env.py` into every field's fingerprint
(`leash.policy.registry.SHARED_FILES`), so a behaviour change in a migration is a versioned decision:
`tests/policy/test_registry.py` fails until it is justified and the LOCK is re-pinned. Python files are
hashed by `code_hash`, which is an AST dump with docstrings stripped — so a comment or docstring edit
here deliberately does *not* move a fingerprint, and any change to SQL, control flow or a literal does.
