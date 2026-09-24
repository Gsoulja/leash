import asyncio
import os

import asyncpg
import pytest
from conftest import DEFAULT_DATABASE_URL


def test_select_1_on_isolated_database(test_database_url):
    async def probe():
        conn = await asyncpg.connect(test_database_url)
        try:
            return await conn.fetchval("select 1"), await conn.fetchval("select current_database()")
        finally:
            await conn.close()

    one, name = asyncio.run(probe())
    assert one == 1
    assert name.startswith("leash_test_")


def test_isolated_database_is_dropped_afterwards(make_test_database, database_url):
    async def exists(name: str) -> bool:
        conn = await asyncpg.connect(database_url)
        try:
            return await conn.fetchval("select exists(select 1 from pg_database where datname = $1)", name)
        finally:
            await conn.close()

    with make_test_database() as url:
        name = url.rsplit("/", 1)[1]
        assert asyncio.run(exists(name))
    assert not asyncio.run(exists(name))


def test_each_isolated_database_is_distinct(make_test_database):
    with make_test_database() as a, make_test_database() as b:
        assert a != b


def test_connection_settings_come_from_database_url(monkeypatch, request):
    monkeypatch.setenv("DATABASE_URL", "postgresql://someone:secret@db.example:6543/elsewhere")
    assert request.getfixturevalue("database_url") == "postgresql://someone:secret@db.example:6543/elsewhere"


def test_server_is_postgres_17(test_database_url):
    async def version():
        conn = await asyncpg.connect(test_database_url)
        try:
            return conn.get_server_version().major
        finally:
            await conn.close()

    assert asyncio.run(version()) == 17


def test_wrong_credentials_fail_instead_of_skipping(monkeypatch, request):
    right = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    monkeypatch.setenv("DATABASE_URL", right.replace("leash:leash@", "leash:not-the-password@", 1))
    with pytest.raises(asyncpg.InvalidPasswordError):
        request.getfixturevalue("make_test_database")
