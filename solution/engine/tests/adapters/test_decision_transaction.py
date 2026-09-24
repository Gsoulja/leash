"""One transaction per decision: per-card lock, snapshot, decide, save, outbox, NOTIFY (LEASH-044)."""

import asyncio
import inspect
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import asyncpg
import pytest
from alembic import command

from factories import facts, line, mandate, merchant, purchase
from leash.adapters.pack.loader import Pack
from leash.adapters.pack.seed import seed
from leash.adapters.postgres import unit_of_work
from leash.adapters.postgres.repository import PostgresRepository
from leash.adapters.postgres.unit_of_work import DecisionTransaction, LockTimeout
from leash.domain import mandate as m
from leash.domain.clock import SimTime
from leash.domain.mandate import Rule
from test_schema import alembic, sql

DATA = Path(__file__).resolve().parents[4] / "data"
NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
SHOP = merchant(merchant_id="ME0001", name="Alpine Basket")
WEEK_300 = mandate(Rule(m.F_BILLING_CHF, "<=", Decimal("300"), currency="CHF", scope="period", period_days=7))


@pytest.fixture
def db(test_database_url):
    command.upgrade(alembic(test_database_url), "head")

    async def go():
        conn = await asyncpg.connect(test_database_url)
        try:
            await seed(conn, Pack(DATA))
        finally:
            await conn.close()
    asyncio.run(go())
    sql(test_database_url,
        "insert into mandates values ('TM1', 'test', 'active', now())",
        "insert into mandate_versions values ('TM1', 1, '[]', 'ask', '{}', now())",
        "insert into runs values ('RUN1', 'SCEN0001', 'TM1', 1, 'CA0001', now())")
    return test_database_url


def buy(aid, chf, ts="2026-08-12T09:00:00Z", card="CA0001"):
    return purchase(chf, authorization_id=aid, source_authorization_id=f"SRC-{aid}", card_id=card, merchant=SHOP,
                    sim_time=SimTime.parse(ts), items=(line(),))


def with_pool(url, body, size=4):
    async def go():
        pool = await asyncpg.create_pool(url, min_size=1, max_size=size)
        try:
            return await body(pool)
        finally:
            await pool.close()
    return asyncio.run(go())


async def receive(pool, p):
    await PostgresRepository(pool).receive(p, run_id="RUN1", event={}, received_at=NOW,
                                           deadline_at=NOW + timedelta(seconds=8))


def tx(pool, **kw):
    return DecisionTransaction(pool, engine_version="leash-test", **kw)


def test_concurrent_approvals_respect_period_limit(db):
    async def body(pool):
        a, b = buy("A", "200.00"), buy("B", "200.00", ts="2026-08-12T09:01:00Z")
        await receive(pool, a), await receive(pool, b)
        run = tx(pool)
        results = await asyncio.gather(
            run.decide(a, run_id="RUN1", mandate=WEEK_300, facts=facts(), platform_period_spend_chf=None),
            run.decide(b, run_id="RUN1", mandate=WEEK_300, facts=facts(), platform_period_spend_chf=None))
        return sorted(r.decision.verdict for r in results)

    assert with_pool(db, body) == ["approve", "decline"]  # the second sees the first's approval


def test_decision_event_and_outbox_commit_together(db):
    async def body(pool):
        p = buy("A", "20.00")
        await receive(pool, p)
        outcome = await tx(pool).decide(p, run_id="RUN1", mandate=WEEK_300, facts=facts(),
                                        platform_period_spend_chf=None)
        return outcome

    outcome = with_pool(db, body)
    [row] = sql(db, "select state, engine_verdict from authorizations where authorization_id = 'A'")
    [box] = sql(db, "select endpoint, body, sent_at from outbox where authorization_id = 'A'")
    events = sql(db, "select kind from decision_events where authorization_id = 'A' order by seq")
    assert (row["state"], row["engine_verdict"]) == ("approved", "approve")
    assert box["endpoint"] == "decision" and box["sent_at"] is None
    assert json.loads(box["body"]) == outcome.response and outcome.response["decision"] == "approve"
    assert outcome.response["authorization_id"] == "A" and outcome.response["engine_version"] == "leash-test"
    assert [e["kind"] for e in events] == ["received", "decided"]


def test_a_failure_before_commit_leaves_nothing(db, monkeypatch):
    async def broken(conn, authorization_id, body):
        raise RuntimeError("disk full")

    monkeypatch.setattr(unit_of_work, "_write_outbox", broken)

    async def body(pool):
        p = buy("A", "20.00")
        await receive(pool, p)
        with pytest.raises(RuntimeError):
            await tx(pool).decide(p, run_id="RUN1", mandate=WEEK_300, facts=facts(), platform_period_spend_chf=None)

    with_pool(db, body)
    [row] = sql(db, "select state, engine_verdict from authorizations where authorization_id = 'A'")
    assert (row["state"], row["engine_verdict"]) == ("received", None)
    assert sql(db, "select 1 from outbox") == []
    assert [e["kind"] for e in sql(db, "select kind from decision_events where authorization_id = 'A'")] == ["received"]


def test_step_up_notifies_asks(db):
    async def body(pool):
        heard: list[str] = []
        listener = await asyncpg.connect(db)
        await listener.add_listener("asks", lambda *args: heard.append(args[3]))
        try:
            p = buy("A", "20.00")
            await receive(pool, p)
            unsure = mandate(Rule(m.F_SIZE, "=", "43"))  # no size stated → ask
            outcome = await tx(pool).decide(p, run_id="RUN1", mandate=unsure, facts=facts(),
                                            platform_period_spend_chf=None, ask_expires_at=NOW + timedelta(minutes=2))
            q = buy("B", "35.00")  # not a duplicate of the waiting A
            await receive(pool, q)
            await tx(pool).decide(q, run_id="RUN1", mandate=WEEK_300, facts=facts(), platform_period_spend_chf=None)
            for _ in range(50):
                if heard:
                    break
                await asyncio.sleep(0.02)
            return outcome.decision.verdict, heard
        finally:
            await listener.close()

    verdict, heard = with_pool(db, body)
    assert verdict == "step_up" and heard == ["A"]  # the approval sent no notification


def test_stages_run_in_order_and_take_facts_not_a_reader(db):
    params = inspect.signature(DecisionTransaction.decide).parameters
    assert "facts" in params and not any("reader" in name for name in params)

    async def body(pool):
        p = buy("A", "20.00")
        await receive(pool, p)
        return await tx(pool).decide(p, run_id="RUN1", mandate=WEEK_300, facts=facts(), platform_period_spend_chf=None)

    outcome = with_pool(db, body)
    assert [name for name, _ in outcome.stages] == ["lock", "snapshot", "decide", "save", "commit"]
    assert all(ms >= 0 for _, ms in outcome.stages)


def test_lock_wait_is_bounded(db):
    async def body(pool):
        p = buy("A", "20.00")
        await receive(pool, p)
        holder = await asyncpg.connect(db)
        try:
            await holder.execute("begin")
            await holder.execute("select pg_advisory_xact_lock(hashtext('card:CA0001'))")
            start = asyncio.get_running_loop().time()
            with pytest.raises(LockTimeout):
                await tx(pool, lock_timeout_ms=200).decide(p, run_id="RUN1", mandate=WEEK_300, facts=facts(),
                                                           platform_period_spend_chf=None)
            waited = asyncio.get_running_loop().time() - start
            await holder.execute("rollback")
            return waited
        finally:
            await holder.close()

    waited = with_pool(db, body)
    assert 0.15 <= waited < 1.0
    [row] = sql(db, "select state from authorizations where authorization_id = 'A'")
    assert row["state"] == "received"


def test_other_cards_are_not_blocked(db):
    async def body(pool):
        p = buy("C", "20.00", card="CA0002")
        await receive(pool, p)
        holder = await asyncpg.connect(db)
        try:
            await holder.execute("begin")
            await holder.execute("select pg_advisory_xact_lock(hashtext('card:CA0001'))")
            outcome = await tx(pool, lock_timeout_ms=200).decide(p, run_id="RUN1", mandate=WEEK_300, facts=facts(),
                                                                 platform_period_spend_chf=None)
            await holder.execute("rollback")
            return outcome.decision.verdict
        finally:
            await holder.close()

    assert with_pool(db, body) == "approve"


def test_serialisation_does_not_depend_on_the_database_default_isolation(db):
    # Review finding: under a 'repeatable read' default, every concurrent approval saw the same old snapshot.
    name = db.rsplit("/", 1)[1]
    sql(db, f"alter database \"{name}\" set default_transaction_isolation = 'repeatable read'")

    async def body(pool):
        purchases = [purchase("50.00", authorization_id=f"P{i}", source_authorization_id=f"SRC-P{i}", card_id="CA0001",
                              merchant=SHOP, sim_time=SimTime.parse("2026-08-12T09:00:00Z"),
                              items=(line(f"IT{i:04d}"),)) for i in range(8)]  # distinct baskets: no duplicates
        for p in purchases:
            await receive(pool, p)
        run = tx(pool)
        results = await asyncio.gather(*(run.decide(p, run_id="RUN1", mandate=WEEK_300, facts=facts(),
                                                    platform_period_spend_chf=None) for p in purchases))
        return [r.decision.verdict for r in results]

    verdicts = with_pool(db, body, size=8)
    assert verdicts.count("approve") == 6  # CHF 300 in 50s, never more


def test_a_row_lock_timeout_is_also_a_lock_timeout(db):
    async def body(pool):
        p = buy("A", "20.00")
        await receive(pool, p)
        holder = await asyncpg.connect(db)
        try:
            await holder.execute("begin")
            await holder.execute("select 1 from authorizations where authorization_id = 'A' for update")
            with pytest.raises(LockTimeout):
                await tx(pool, lock_timeout_ms=200).decide(p, run_id="RUN1", mandate=WEEK_300, facts=facts(),
                                                           platform_period_spend_chf=None)
            await holder.execute("rollback")
        finally:
            await holder.close()

    with_pool(db, body)


def test_an_unsupported_rule_emits_an_operational_alert(db):
    unknown = mandate(Rule("leash.merchant.carbon_score.v1", "<=", Decimal("3")), uncertainty="approve")

    async def body(pool):
        p = buy("A", "20.00")
        await receive(pool, p)
        return await tx(pool).decide(p, run_id="RUN1", mandate=unknown, facts=facts(), platform_period_spend_chf=None,
                                     mandate_id="TM1")

    outcome = with_pool(db, body)
    assert outcome.decision.verdict == "step_up"
    [alert] = sql(db, "select payload from decision_events where authorization_id = 'A' and kind = 'integrity_alert'")
    payload = json.loads(alert["payload"])
    assert payload == {"kind": "unsupported_mandate_rule", "mandate_id": "TM1",
                       "fields": ["leash.merchant.carbon_score.v1"], "engine_version": "leash-test"}
