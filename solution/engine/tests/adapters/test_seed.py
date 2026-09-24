"""Seeding reference data from the challenge pack into a throw-away Postgres database."""

import asyncio
import subprocess
import sys
from pathlib import Path

import asyncpg
import pytest
from alembic import command

from leash.adapters.pack.loader import Pack
from leash.adapters.pack.seed import seed
from test_schema import alembic, sql

ENGINE = Path(__file__).resolve().parents[2]
DATA = ENGINE.parents[1] / "data"


@pytest.fixture
def db(test_database_url):
    command.upgrade(alembic(test_database_url), "head")
    return test_database_url


def run_seed(url: str):
    async def go():
        conn = await asyncpg.connect(url)
        try:
            return await seed(conn, Pack(DATA))
        finally:
            await conn.close()
    return asyncio.run(go())


def counts(url: str) -> tuple[int, int]:
    [row] = sql(url, "select (select count(*) from merchants) m, (select count(*) from auth_history) h")
    return row["m"], row["h"]


def test_loads_58_merchants_and_4701_history_rows(db):
    result = run_seed(db)
    assert counts(db) == (58, 4701)
    assert (result.merchants, result.history) == (58, 4701)


def test_seed_is_idempotent(db):
    run_seed(db)
    snapshot = sql(db, "select md5(string_agg(t::text, '|' order by authorization_id)) h from auth_history t")
    second = run_seed(db)
    assert (second.merchants, second.history) == (0, 0)  # nothing written the second time
    assert counts(db) == (58, 4701)
    assert sql(db, "select md5(string_agg(t::text, '|' order by authorization_id)) h from auth_history t") == snapshot


def test_familiarity_view_counts_approved_purchases(db):
    run_seed(db)
    [row] = sql(db, "select approved_purchases from card_merchant_familiarity "
                    "where card_id = 'CA0039' and merchant_id = 'ME0022'")
    assert row["approved_purchases"] == 6


def test_history_columns_are_mapped(db):
    run_seed(db)
    [row] = sql(db, "select * from auth_history where authorization_id = 'TR00001'")
    assert (row["card_id"], row["merchant_id"], row["transaction_type"], row["status"], str(row["billing_chf"]),
            row["device_id"], row["country"], row["initiator"]) == (
        "CA0018", "ME0052", "purchase", "declined", "10.00", "DVC-608523", "CH", "human")


def test_script_seeds_the_database(db):
    out = subprocess.run([sys.executable, "scripts/seed.py", "--database-url", db], cwd=ENGINE,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert "58 merchants" in out.stdout and counts(db) == (58, 4701)
