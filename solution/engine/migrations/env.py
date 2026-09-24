"""Alembic environment: plain SQL migrations, run synchronously through psycopg.

Every migration runs with a bounded `lock_timeout` and `statement_timeout` (LEASH-135). One place, so a
new revision cannot forget it: a migration that waits indefinitely for a lock queues every writer
behind it and takes the application down with it. Timing out is the safe outcome — the transaction rolls
back and the deploy fails loudly, leaving the schema as it was.

Both bounds can be raised for a deliberately long backfill window:
    LEASH_MIGRATION_LOCK_TIMEOUT=5s LEASH_MIGRATION_STATEMENT_TIMEOUT=30min leash-migrate

Neither may be zero: in Postgres that means *no* timeout. Note also that `statement_timeout` bounds one
statement, not a whole revision — a migration that loops over many statements is not bounded by it.

The offline (`--sql`) path sets no timeouts: it emits SQL for someone else to run, so the bounds belong
to whoever runs it. `0008` cannot be generated offline at all (it reads rows to rebuild them).
"""

import os
import re

from alembic import context
from sqlalchemy import create_engine

config = context.config

DEFAULT_LOCK_TIMEOUT = "5s"
DEFAULT_STATEMENT_TIMEOUT = "300s"
#: A Postgres interval literal we are willing to interpolate. Anything else is a configuration error,
#: never a string spliced into SQL. Zero is rejected on purpose: in Postgres `0` means *no timeout*, so
#: `LEASH_MIGRATION_LOCK_TIMEOUT=0` would silently remove the bound this file exists to guarantee.
_INTERVAL = re.compile(r"^\d{1,7}(ms|s|min)?$")


def _is_zero(value: str) -> bool:
    return int(re.sub(r"(ms|s|min)$", "", value) or "0") == 0


def timeout(var: str, default: str) -> str:
    value = os.environ.get(var, "").strip() or default
    if not _INTERVAL.fullmatch(value):
        raise RuntimeError(f"{var}={value!r} is not a Postgres interval like '5s', '250ms' or '30min'")
    if _is_zero(value):
        raise RuntimeError(f"{var}={value!r} means no timeout in Postgres; give a positive interval")
    return value


def database_url() -> str:
    url = config.get_main_option("sqlalchemy.url") or os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("set DATABASE_URL to run migrations")
    # Use the psycopg (v3) driver for SQLAlchemy; the engine itself uses asyncpg.
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def run_migrations_online() -> None:
    lock = timeout("LEASH_MIGRATION_LOCK_TIMEOUT", DEFAULT_LOCK_TIMEOUT)
    statement = timeout("LEASH_MIGRATION_STATEMENT_TIMEOUT", DEFAULT_STATEMENT_TIMEOUT)
    engine = create_engine(database_url())
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            # SET LOCAL: the bounds last for this transaction only, so they never leak into the session
            # the application later uses.
            connection.exec_driver_sql(f"SET LOCAL lock_timeout = '{lock}'")
            connection.exec_driver_sql(f"SET LOCAL statement_timeout = '{statement}'")
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    context.configure(url=database_url(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    run_migrations_online()
