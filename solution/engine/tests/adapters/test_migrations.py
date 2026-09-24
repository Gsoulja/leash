"""LEASH-135: every schema change has to survive a populated database.

`0002` added `purchase jsonb NOT NULL` with no backfill, which Postgres rejects the moment the table
has a single row — so an upgrade from `0001` failed on any real deployment and only passed in tests
because they always started empty. These tests upgrade an empty *and* a populated `0001` database, and
check the rebuilt `Purchase` against the row it came from.
"""

import asyncio
import importlib.util
import json
import threading
import time
from datetime import datetime
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

from leash.adapters.postgres.migrate import alembic_config, head_revision
from leash.adapters.postgres.repository import purchase_from_json
from leash.adapters.viseca_api.translate import translate

DATA = Path(__file__).resolve().parents[4] / "data"
EXAMPLE = json.loads((DATA / "scenario_fixtures" / "example_authorization_request.json").read_text())
FIRST_WITH_PURCHASE = "0002"
#: Well past the 2s lock_timeout the test configures: reaching it means nothing bounded the wait.
GIVE_UP_SECONDS = 15.0


def _revision_module(filename: str):
    """Import a revision file directly, so a helper inside it can be tested without running the chain."""
    path = Path(__file__).resolve().parents[2] / "migrations" / "versions" / filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def upgrade(url: str, revision: str) -> None:
    command.upgrade(alembic_config(url), revision)


def downgrade(url: str, revision: str) -> None:
    command.downgrade(alembic_config(url), revision)


async def _one(url: str, sql: str, *args: object) -> object:
    conn = await asyncpg.connect(url)
    try:
        return await conn.fetchval(sql, *args)
    finally:
        await conn.close()


async def _insert_0001_row(url: str, event: dict, authorization_id: str) -> None:
    """A row exactly as the engine wrote it at revision 0001: no `purchase` column existed yet."""
    a = event["authorization"]
    conn = await asyncpg.connect(url)
    try:
        await conn.execute(
            "insert into authorizations (authorization_id, source_authorization_id, card_id, merchant_id,"
            " sim_ts, billing_chf, item_fingerprint, state, engine_verdict, resolved_by, received_at,"
            " deadline_at, event) values ($1, $2, $3, $4, $5, $6::numeric, $7::jsonb,"
            " 'approved', 'approve', 'engine', now(), now(), $8::jsonb)",
            authorization_id, a["source_authorization_id"], a["card_id"], a["merchant"]["merchant_id"],
            datetime.fromisoformat(a["timestamp"]), str(a["billing_amount_chf"]), json.dumps([]),
            json.dumps(event))
    finally:
        await conn.close()


def test_an_empty_previous_version_database_upgrades_to_head(test_database_url):
    upgrade(test_database_url, "0001")
    upgrade(test_database_url, "head")
    assert asyncio.run(_one(test_database_url, "select version_num from alembic_version")) == head_revision()


def test_a_populated_previous_version_database_upgrades_without_data_loss(test_database_url):
    upgrade(test_database_url, "0001")
    legacy = EXAMPLE["authorization"]["authorization_id"]  # the row is keyed the way `receive` keys it
    asyncio.run(_insert_0001_row(test_database_url, EXAMPLE, legacy))
    upgrade(test_database_url, "head")

    kept = asyncio.run(_one(test_database_url,
                            "select count(*) from authorizations where authorization_id = $1", legacy))
    assert kept == 1, "the row survives the upgrade"
    stored = asyncio.run(_one(test_database_url,
                              "select purchase from authorizations where authorization_id = $1", legacy))
    assert stored is not None, "the backfill filled the column it made required"
    rebuilt = purchase_from_json(json.loads(stored))
    expected = translate(EXAMPLE).purchase
    assert rebuilt == expected, "the reconstructed purchase matches the event it was rebuilt from"


def test_the_purchase_column_is_required_only_after_the_backfill(test_database_url):
    """Expand, then contract. A rolling deploy needs the column to be optional in between."""
    upgrade(test_database_url, FIRST_WITH_PURCHASE)
    nullable = asyncio.run(_one(test_database_url,
                                "select is_nullable from information_schema.columns where table_name = "
                                "'authorizations' and column_name = 'purchase'"))
    assert nullable == "YES", "an app version that does not write `purchase` must still be able to insert"
    upgrade(test_database_url, "head")
    assert asyncio.run(_one(test_database_url,
                            "select is_nullable from information_schema.columns where table_name = "
                            "'authorizations' and column_name = 'purchase'")) == "NO"


def test_a_row_the_backfill_cannot_rebuild_stops_the_migration(test_database_url):
    """Validation, not a silent default: a purchase that cannot be rebuilt is not invented."""
    upgrade(test_database_url, "0001")
    asyncio.run(_insert_0001_row(test_database_url, {"authorization": {
        "source_authorization_id": None, "card_id": "CA0001", "merchant": {"merchant_id": "ME0022"},
        "timestamp": "2026-08-12T09:40:00Z", "billing_amount_chf": 20.0}}, "AZ-unreadable"))
    try:
        upgrade(test_database_url, "head")
    except Exception as exc:  # noqa: BLE001 — a refusal is the point, and it must say which row
        assert "AZ-unreadable" in str(exc), f"the refusal must name the row it could not rebuild: {exc}"
        assert "cannot rebuild" in str(exc), f"a bare constraint violation is not a refusal: {exc}"
    else:
        raise AssertionError("an unrebuildable row must stop the upgrade, not be filled with a guess")
    # and nothing was written: the whole revision is one transaction
    assert asyncio.run(_one(test_database_url, "select version_num from alembic_version")) == "0001"


def test_every_revision_downgrades_back_to_the_previous_one(test_database_url):
    """The documented policy: every revision in the chain is reversible (migrations/README.md)."""
    upgrade(test_database_url, "head")
    revisions = [r.revision for r in ScriptDirectory.from_config(alembic_config(test_database_url)).walk_revisions()]
    for revision in revisions:  # newest first
        downgrade(test_database_url, f"{revision}-1" if revision != revisions[-1] else "base")
    assert asyncio.run(_one(test_database_url, "select to_regclass('authorizations')::text")) is None
    upgrade(test_database_url, "head")  # and back up again, on the same database


def test_a_blocked_migration_fails_fast_instead_of_waiting(test_database_url, monkeypatch):
    """AC3, measured rather than grepped: hold the table and the migration must give up, not queue.

    A migration that waits indefinitely for a lock puts every writer behind it. Timing out is the safe
    outcome: the transaction rolls back and the deploy fails loudly with the schema untouched.
    """
    upgrade(test_database_url, "0001")
    monkeypatch.setenv("LEASH_MIGRATION_LOCK_TIMEOUT", "2s")

    async def hold_then_migrate() -> tuple[float, str, str]:
        holder = await asyncpg.connect(test_database_url)
        try:
            transaction = holder.transaction()
            await transaction.start()
            await holder.execute("lock table authorizations in access exclusive mode")
            # In a thread with a wall-clock join: without the bound the migration waits for the lock
            # forever, and a test that hangs proves nothing to anyone reading a CI log.
            outcome: dict[str, str] = {}

            def migrate() -> None:
                try:
                    upgrade(test_database_url, "0002")
                    outcome["failure"] = ""
                except Exception as exc:  # noqa: BLE001 — the timeout is what we are measuring
                    outcome["failure"] = str(exc)

            started = time.monotonic()
            worker = threading.Thread(target=migrate, daemon=True)
            worker.start()
            worker.join(GIVE_UP_SECONDS)
            took = time.monotonic() - started
            if worker.is_alive():  # still waiting: the bound is gone
                await transaction.rollback()
                worker.join(GIVE_UP_SECONDS)
                raise AssertionError(f"the migration was still waiting for the lock after {took:.0f}s; "
                                     "env.py is not bounding it")
            failure = outcome["failure"]
            await transaction.rollback()
        finally:
            await holder.close()
        applied = await _one(test_database_url, "select version_num from alembic_version")
        return took, failure, str(applied)

    took, failure, applied = asyncio.run(hold_then_migrate())
    assert failure, "the migration was not blocked at all; the lock was not held"
    assert "lock timeout" in failure.lower(), failure
    assert took < 10, f"it waited {took:.1f}s for a 2s lock_timeout"
    assert applied == "0001", "a timed-out migration must leave the schema exactly as it was"


def test_a_zero_timeout_is_refused_because_postgres_reads_it_as_no_timeout(test_database_url, monkeypatch):
    monkeypatch.setenv("LEASH_MIGRATION_LOCK_TIMEOUT", "0")
    with pytest.raises(Exception, match="no timeout"):
        upgrade(test_database_url, "0001")


def test_a_reclaimed_event_blocks_the_downgrade_past_0006(test_database_url):
    """The documented exception (migrations/README.md): `0006` is not reversible once a claim was reclaimed.

    Pinned as a property rather than left as a surprise during an incident: the narrower constraint is
    violated by a row that cannot be deleted, because `decision_events` is append-only.
    """
    upgrade(test_database_url, "head")

    async def add_reclaimed() -> None:
        conn = await asyncpg.connect(test_database_url)
        try:
            await conn.execute("insert into decision_events (authorization_id, kind, payload) "
                               "values ('AZ-1', 'reclaimed', '{}'::jsonb)")
        finally:
            await conn.close()

    asyncio.run(add_reclaimed())
    with pytest.raises(Exception, match="decision_events_kind_check"):
        downgrade(test_database_url, "0005")
    # still at head, and the blocking row is still undeletable
    assert asyncio.run(_one(test_database_url, "select version_num from alembic_version")) == head_revision()


def test_the_backfill_validation_counts_what_it_says_it_counts(test_database_url):
    """The count that guards `SET NOT NULL`, tested directly — the loop above it normally leaves it zero."""
    module = _revision_module("0008_purchase_backfill.py")
    upgrade(test_database_url, "0007")
    asyncio.run(_insert_0001_row(test_database_url, EXAMPLE, "AZ-nopurchase"))

    engine = create_engine(alembic_config(test_database_url).get_main_option("sqlalchemy.url")
                           .replace("postgresql://", "postgresql+psycopg://"))
    try:
        with engine.connect() as conn:
            assert module.remaining_without_purchase(conn) == 1
            conn.exec_driver_sql("update authorizations set purchase = '{}'::jsonb")
            assert module.remaining_without_purchase(conn) == 0
    finally:
        engine.dispose()
