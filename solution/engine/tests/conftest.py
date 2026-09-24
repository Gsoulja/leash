"""Shared test fixtures.

Database fixtures connect with DATABASE_URL (default: the Docker Compose `db` service) and give
each test its own throw-away database, dropped afterwards. Start the database first:
    docker compose -f ../docker-compose.yml up -d db
"""

import asyncio
import os
import uuid
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager

import asyncpg
import pytest

DEFAULT_DATABASE_URL = "postgresql://leash:leash@localhost:55432/leash"


@pytest.fixture
def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


async def _admin(url: str, sql: str) -> None:
    conn = await asyncpg.connect(url)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


@pytest.fixture
def make_test_database(database_url: str) -> Callable[[], AbstractContextManager[str]]:
    """Factory: `with make_test_database() as url:` creates a fresh database and drops it on exit."""
    # Skip only when nothing is listening. Wrong credentials or the wrong server must fail loudly.
    try:
        asyncio.run(_admin(database_url, "select 1"))
    except (ConnectionRefusedError, asyncpg.CannotConnectNowError) as exc:
        pytest.skip(f"Postgres not reachable at DATABASE_URL ({exc.__class__.__name__}); run `docker compose up -d db`")

    @contextmanager
    def create() -> Iterator[str]:
        name = f"leash_test_{uuid.uuid4().hex[:12]}"
        asyncio.run(_admin(database_url, f'create database "{name}"'))
        try:
            yield f"{database_url.rsplit('/', 1)[0]}/{name}"
        finally:
            asyncio.run(_admin(database_url, f'drop database if exists "{name}" with (force)'))

    return create


@pytest.fixture
def test_database_url(make_test_database: Callable[[], AbstractContextManager[str]]) -> Iterator[str]:
    with make_test_database() as url:
        yield url
