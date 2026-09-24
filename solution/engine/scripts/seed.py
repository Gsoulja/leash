"""Seed Postgres with the challenge pack's reference data (merchants, authorization history).

    uv run python scripts/seed.py                     # uses DATABASE_URL
    uv run python scripts/seed.py --database-url postgresql://leash:leash@localhost:55432/leash

Safe to run again: nothing changes when the data is already there.
"""

import argparse
import asyncio
import os
from pathlib import Path

import asyncpg

from leash.adapters.pack.loader import Pack
from leash.adapters.pack.seed import seed

DATA = Path(__file__).resolve().parents[3] / "data"


async def main(url: str) -> None:
    conn = await asyncpg.connect(url)
    try:
        result = await seed(conn, Pack(DATA))
    finally:
        await conn.close()
    print(f"seeded: {result.merchants} merchants and {result.history} history rows written; familiarity refreshed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    args = parser.parse_args()
    if not args.database_url:
        parser.error("set DATABASE_URL or pass --database-url")
    asyncio.run(main(args.database_url))
