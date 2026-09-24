"""LEASH-151: a rehearsal starts from the approved baseline, or it does not start.

The reset is checked twice over — running it twice must leave identical state, and the baseline it
leaves must be provably the pack's own (no duplicate authorization IDs, per-card totals equal to the
CSV). Its guards are checked too: this deletes data, so an accidental invocation has to be refused.
"""

import asyncio
import json
from pathlib import Path

import asyncpg
import pytest

from leash.adapters.pack.loader import Pack
from leash.adapters.postgres.migrate import migrate_and_seed
from leash.adapters.postgres.reset import (
    BUDGET_SECONDS,
    DEMO_TABLES,
    BaselineNotClean,
    RefusedReset,
    check_allowed,
    check_baseline,
    reset,
)

DATA = Path(__file__).resolve().parents[4] / "data"


async def _state(url: str) -> dict:
    conn = await asyncpg.connect(url)
    try:
        counts = {t: await conn.fetchval(f"select count(*) from {t}") for t in (*DEMO_TABLES, "merchants",
                                                                               "auth_history")}
        totals = {r["card_id"]: str(r["total"]) for r in
                  await conn.fetch("select card_id, sum(billing_chf) as total from auth_history group by card_id")}
        return {"counts": counts, "totals": totals}
    finally:
        await conn.close()


async def _write_demo_state(url: str) -> None:
    """Leftovers of the shape a rehearsal actually leaves behind."""
    conn = await asyncpg.connect(url)
    try:
        await conn.execute("insert into mandates (mandate_id, instruction, status) values ('MD-1', 'buy it', 'active')")
        await conn.execute("insert into mandate_versions (mandate_id, version, hard_rules, uncertainty_policy,"
                           " compiled) values ('MD-1', 1, '[]'::jsonb, 'ask', '{}'::jsonb)")
        await conn.execute("insert into runs (run_id, scenario_id, mandate_id, mandate_version, card_id)"
                           " values ('RUN-1', 'SCEN0000', 'MD-1', 1, 'CA0001')")
        await conn.execute("insert into authorizations (authorization_id, run_id, card_id, merchant_id, sim_ts,"
                           " billing_chf, item_fingerprint, state, received_at, deadline_at, event, purchase)"
                           " values ('AZ-1', 'RUN-1', 'CA0001', 'ME0022', now(), 20.00, '[]'::jsonb, 'approved',"
                           " now(), now(), '{}'::jsonb, '{}'::jsonb)")
        await conn.execute("insert into decision_events (authorization_id, kind, payload)"
                           " values ('AZ-1', 'decided', '{}'::jsonb)")
        await conn.execute("insert into outbox (authorization_id, endpoint, body)"
                           " values ('AZ-1', 'decision', '{}'::jsonb)")
        await conn.execute("insert into policy_drafts (draft_id, instruction, draft, revision)"
                           " values ('LD-1', 'buy it', $1::jsonb, 1)", json.dumps({"draft_id": "LD-1"}))
        await conn.execute("insert into draft_revisions (draft_id, revision, draft, answers, context)"
                           " values ('LD-1', 1, '{}'::jsonb, '[]'::jsonb, '{}'::jsonb)")
    finally:
        await conn.close()


def test_the_guards_refuse_an_accidental_reset():
    local = "postgresql://leash:leash@localhost:55432/leash"
    with pytest.raises(RefusedReset, match="--yes"):
        check_allowed(local, yes=False, live=False, env={})
    check_allowed(local, yes=True, live=False, env={})
    check_allowed(local, yes=False, live=False, env={"LEASH_ALLOW_DEMO_RESET": "1"})


def test_a_database_that_is_not_local_needs_live():
    remote = "postgresql://leash:secret@db.example.com:5432/leash"
    with pytest.raises(RefusedReset, match="not a local database"):
        check_allowed(remote, yes=True, live=False, env={})
    check_allowed(remote, yes=True, live=True, env={})


def test_reset_clears_every_table_the_demo_writes(test_database_url):
    migrate_and_seed(test_database_url, DATA)
    asyncio.run(_write_demo_state(test_database_url))
    before = asyncio.run(_state(test_database_url))
    assert before["counts"]["authorizations"] == 1 and before["counts"]["decision_events"] == 1
    asyncio.run(reset(test_database_url, DATA, yes=True))
    after = asyncio.run(_state(test_database_url))
    assert all(after["counts"][t] == 0 for t in DEMO_TABLES), after["counts"]


def test_the_append_only_log_is_cleared_and_protected_again(test_database_url):
    """The trigger is lifted for the truncate only: a demo must not leave the audit log deletable."""
    migrate_and_seed(test_database_url, DATA)
    asyncio.run(_write_demo_state(test_database_url))
    asyncio.run(reset(test_database_url, DATA, yes=True))

    async def try_delete() -> str:
        conn = await asyncpg.connect(test_database_url)
        try:
            await conn.execute("insert into decision_events (authorization_id, kind, payload)"
                               " values ('AZ-2', 'received', '{}'::jsonb)")
            try:
                await conn.execute("delete from decision_events")
            except asyncpg.PostgresError as exc:
                return str(exc)
            return "deleted"
        finally:
            await conn.close()

    assert "append-only" in asyncio.run(try_delete())


def test_running_reset_twice_leaves_identical_state(test_database_url):
    migrate_and_seed(test_database_url, DATA)
    asyncio.run(_write_demo_state(test_database_url))
    asyncio.run(reset(test_database_url, DATA, yes=True))
    once = asyncio.run(_state(test_database_url))
    asyncio.run(reset(test_database_url, DATA, yes=True))
    assert asyncio.run(_state(test_database_url)) == once


def test_the_baseline_check_matches_the_packs_own_totals(test_database_url):
    migrate_and_seed(test_database_url, DATA)
    asyncio.run(reset(test_database_url, DATA, yes=True))

    async def problems() -> list[str]:
        conn = await asyncpg.connect(test_database_url)
        try:
            return await check_baseline(conn, Pack(DATA))
        finally:
            await conn.close()

    assert asyncio.run(problems()) == []


def test_a_history_row_that_does_not_match_the_pack_is_reported(test_database_url):
    """The check is a check, not a formality: change one amount and it must say so."""
    migrate_and_seed(test_database_url, DATA)
    asyncio.run(reset(test_database_url, DATA, yes=True))

    async def tamper_and_check() -> list[str]:
        conn = await asyncpg.connect(test_database_url)
        try:
            await conn.execute("update auth_history set billing_chf = billing_chf + 1 "
                               "where authorization_id = (select min(authorization_id) from auth_history)")
            return await check_baseline(conn, Pack(DATA))
        finally:
            await conn.close()

    found = asyncio.run(tamper_and_check())
    assert found and any("total CHF" in p for p in found), found


def test_leftover_demo_rows_make_the_baseline_check_fail(test_database_url):
    migrate_and_seed(test_database_url, DATA)

    async def check_with_leftovers() -> list[str]:
        await _write_demo_state(test_database_url)
        conn = await asyncpg.connect(test_database_url)
        try:
            return await check_baseline(conn, Pack(DATA))
        finally:
            await conn.close()

    found = asyncio.run(check_with_leftovers())
    assert any("authorizations still holds" in p for p in found), found


def test_reset_raises_when_the_baseline_is_not_clean(test_database_url, monkeypatch):
    migrate_and_seed(test_database_url, DATA)

    async def leaves_rows(conn, tables=DEMO_TABLES):  # a clear that does nothing
        return None

    monkeypatch.setattr("leash.adapters.postgres.reset.clear", leaves_rows)
    asyncio.run(_write_demo_state(test_database_url))
    with pytest.raises(BaselineNotClean, match="not the approved baseline"):
        asyncio.run(reset(test_database_url, DATA, yes=True))


def test_reset_fits_the_rehearsal_budget(test_database_url):
    migrate_and_seed(test_database_url, DATA)
    took = asyncio.run(reset(test_database_url, DATA, yes=True))
    assert took < BUDGET_SECONDS, f"reset took {took:.1f}s, over the {BUDGET_SECONDS:.0f}s rehearsal budget"


# --- round 2: the gaps the independent review found -------------------------------------------

#: Tables a reset must NOT clear, each with the reason. Anything else in the schema has to be in
#: DEMO_TABLES — a new table is then a deliberate decision, not an omission nobody noticed.
KEPT: dict[str, str] = {
    "merchants": "reference data from the pack; upserted by the seed and checked afterwards",
    "auth_history": "reference data from the pack; the familiarity baseline the demo starts from",
    "alembic_version": "the schema version; a reset is not a migration",
    "model_releases": "a registered model release is configuration, not demo state (LEASH-081)",
}


def test_every_table_in_the_schema_is_either_cleared_or_deliberately_kept(test_database_url):
    """Pins the list itself. Without this, removing a table from DEMO_TABLES changes nothing a test
    can see: the clearing test and the baseline check both iterate the same list."""
    migrate_and_seed(test_database_url, DATA)

    async def tables() -> set[str]:
        conn = await asyncpg.connect(test_database_url)
        try:
            return {r["tablename"] for r in
                    await conn.fetch("select tablename from pg_tables where schemaname = 'public'")}
        finally:
            await conn.close()

    found = asyncio.run(tables())
    assert set(DEMO_TABLES) | set(KEPT) == found, (
        f"unclassified: {sorted(found - set(DEMO_TABLES) - set(KEPT))}; "
        f"listed but absent: {sorted((set(DEMO_TABLES) | set(KEPT)) - found)}")


def test_the_demo_tables_are_named_here_too(test_database_url):
    """A second, literal copy of the list: deleting a table from DEMO_TABLES now fails a test."""
    assert set(DEMO_TABLES) == {
        "outbox", "decision_events", "authorizations", "runs",
        "draft_revisions", "policy_drafts", "mandate_versions", "mandates", "fact_reads",
    }


def test_the_event_cursor_keeps_climbing_across_a_reset(test_database_url):
    """A running API keeps a high-water mark on `decision_events.seq`. Restarting the sequence at 1
    made the next rehearsal's first events look already-delivered, and the stream dropped them."""
    migrate_and_seed(test_database_url, DATA)
    asyncio.run(_write_demo_state(test_database_url))

    async def highest() -> int:
        conn = await asyncpg.connect(test_database_url)
        try:
            return int(await conn.fetchval("select coalesce(max(seq), 0) from decision_events"))
        finally:
            await conn.close()

    async def add_event() -> int:
        conn = await asyncpg.connect(test_database_url)
        try:
            return int(await conn.fetchval(
                "insert into decision_events (authorization_id, kind, payload) "
                "values ('AZ-next', 'received', '{}'::jsonb) returning seq"))
        finally:
            await conn.close()

    before = asyncio.run(highest())
    assert before > 0
    asyncio.run(reset(test_database_url, DATA, yes=True))
    assert asyncio.run(add_event()) > before, "a reader's cursor would skip the new rehearsal's events"


@pytest.mark.parametrize("url,env", [
    ("postgresql:///leash?host=prod.viseca.example&port=5432", {}),
    ("postgresql:///leash", {"PGHOST": "prod.viseca.example"}),
    ("postgresql://prod.viseca.example/leash", {}),
])
def test_a_remote_database_reached_without_a_hostname_in_the_url_is_still_refused(url, env):
    """The bypass an earlier review found: libpq resolves `?host=` and `PGHOST` for a DSN whose
    hostname parses as None, which is how operations tooling normally points at an environment."""
    with pytest.raises(RefusedReset, match="not a local database"):
        check_allowed(url, yes=True, live=False, env=env)


@pytest.mark.parametrize("url,env", [
    ("postgresql:///leash", {}),                          # a genuine local unix socket
    ("postgresql:///leash?host=/var/run/postgresql", {}),  # an explicit socket path
    ("postgresql://localhost:55432/leash", {}),
    ("postgresql://leash:leash@db:5432/leash", {}),        # the Compose service
])
def test_a_genuinely_local_database_is_still_allowed(url, env):
    check_allowed(url, yes=True, live=False, env=env)


def test_a_missing_pack_is_reported_by_path(test_database_url):
    """One of the three likeliest rehearsal failures; it used to surface as a traceback."""
    migrate_and_seed(test_database_url, DATA)
    with pytest.raises(FileNotFoundError):
        asyncio.run(reset(test_database_url, Path("/nope"), yes=True))


def test_an_unclean_baseline_says_what_to_do_next(test_database_url, monkeypatch):
    migrate_and_seed(test_database_url, DATA)
    monkeypatch.setattr("leash.adapters.postgres.reset.clear", lambda conn, tables=DEMO_TABLES: _noop())
    asyncio.run(_write_demo_state(test_database_url))
    with pytest.raises(BaselineNotClean, match="Do not start the rehearsal"):
        asyncio.run(reset(test_database_url, DATA, yes=True))


async def _noop() -> None:
    return None
