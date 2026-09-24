"""Migrations then the pack seed, the step every start runs before the services (LEASH-127).

Both are idempotent: Alembic skips applied revisions and the seed upserts. Run it as `uv run leash-migrate`.
"""

import asyncio
import os
from pathlib import Path

import asyncpg
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from leash.adapters.pack.loader import Pack
from leash.adapters.pack.seed import seed

ENGINE = Path(__file__).resolve().parents[4]  # solution/engine (src/leash/adapters/postgres/…)


def alembic_config(database_url: str) -> Config:
    cfg = Config(str(ENGINE / "alembic.ini"))
    cfg.set_main_option("script_location", str(ENGINE / "migrations"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def head_revision() -> str:
    head = ScriptDirectory.from_config(alembic_config("postgresql://unused")).get_current_head()
    if head is None:
        raise RuntimeError("no migrations found")
    return head


def migrate_and_seed(database_url: str, data_dir: Path) -> None:
    command.upgrade(alembic_config(database_url), "head")

    async def run_seed() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            await seed(conn, Pack(data_dir))
        finally:
            await conn.close()

    asyncio.run(run_seed())


def main() -> None:  # pragma: no cover - process entry point
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise SystemExit("set DATABASE_URL")
    migrate_and_seed(url, Path(os.environ.get("LEASH_DATA_DIR", str(ENGINE.parents[1] / "data"))))
    print("migrations applied and pack seeded")
