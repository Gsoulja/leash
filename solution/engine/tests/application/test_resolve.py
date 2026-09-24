"""Customer answers and the ask timeout sweeper, against a throw-away Postgres (LEASH-045)."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import asyncpg
import pytest
from alembic import command

from factories import facts, line, mandate, merchant, purchase, snapshot
from leash.adapters.pack.loader import Pack
from leash.adapters.pack.seed import seed
from leash.adapters.postgres.repository import PostgresRepository
from leash.adapters.postgres.unit_of_work import DecisionTransaction, ResolutionTransaction
from leash.application.resolve import ResolveAsk, Sweeper
from leash.domain import mandate as m
from leash.domain.clock import SimTime
from leash.domain.mandate import Rule
from leash.domain.states import IllegalTransition
from adapters.test_schema import alembic, sql

DATA = Path(__file__).resolve().parents[4] / "data"
NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
SHOP = merchant(merchant_id="ME0001", name="Alpine Basket")
# Asks when the size isn't stated; hard limit: CHF 300 in any 7 days.
MANDATE = mandate(Rule(m.F_SIZE, "=", "43"),
                  Rule(m.F_BILLING_CHF, "<=", Decimal("300"), currency="CHF", scope="period", period_days=7))


class Mandates:
    def for_run(self, run_id):
        return MANDATE


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
        "insert into runs values ('RUN1', 'SCEN0002', 'TM1', 1, 'CA0001', now())")
    return test_database_url


def buy(aid, chf, ts="2026-08-12T09:00:00Z"):
    return purchase(chf, authorization_id=aid, source_authorization_id=f"SRC-{aid}", card_id="CA0001", merchant=SHOP,
                    sim_time=SimTime.parse(ts), items=(line(f"IT-{aid}"),))


def with_pool(url, body):
    async def go():
        pool = await asyncpg.create_pool(url, min_size=1, max_size=4)
        try:
            return await body(pool)
        finally:
            await pool.close()
    return asyncio.run(go())


async def ask(pool, p, expires=NOW + timedelta(seconds=120), m_=MANDATE, f=None):
    await PostgresRepository(pool).receive(p, run_id="RUN1", event={}, received_at=NOW,
                                           deadline_at=NOW + timedelta(seconds=8))
    out = await DecisionTransaction(pool, engine_version="t").decide(
        p, run_id="RUN1", mandate=m_, facts=f or facts(), platform_period_spend_chf=None, ask_expires_at=expires)
    return out.decision.verdict


def resolver(pool):
    return ResolveAsk(ResolutionTransaction(pool), Mandates(), engine_version="t")


def state(url, aid):
    [row] = sql(url, f"select state, resolved_by, ask_expires_at from authorizations where authorization_id = '{aid}'")
    return row


def test_customer_approval_adds_spend(db):
    async def body(pool):
        assert await ask(pool, buy("A", "200.00")) == "step_up"
        result = await resolver(pool).answer("A", "approve", now=NOW + timedelta(seconds=30))
        snap = await PostgresRepository(pool).snapshot("CA0001", run_id="RUN1", platform_period_spend_chf=None)
        return result, snap

    result, snap = with_pool(db, body)
    assert result.state == "approved" and result.blocked == ()
    assert snap.approved_spend_in_window(SimTime.parse("2026-08-12T10:00:00Z"), timedelta(days=7)) == Decimal("200.00")
    assert (state(db, "A")["state"], state(db, "A")["resolved_by"]) == ("approved", "customer")


def test_customer_decline(db):
    async def body(pool):
        await ask(pool, buy("A", "200.00"))
        return await resolver(pool).answer("A", "decline", now=NOW + timedelta(seconds=30))

    assert with_pool(db, body).state == "declined"
    assert state(db, "A")["state"] == "declined"


def test_each_resolution_writes_a_resolve_outbox_row(db):
    async def body(pool):
        await ask(pool, buy("A", "20.00")), await ask(pool, buy("B", "30.00", ts="2026-08-12T09:05:00Z"))
        await resolver(pool).answer("A", "approve", now=NOW)
        await resolver(pool).answer("B", "decline", now=NOW)

    with_pool(db, body)
    rows = sql(db, "select authorization_id, body from outbox where endpoint = 'resolve' order by id")
    bodies = {r["authorization_id"]: json.loads(r["body"]) for r in rows}
    assert bodies["A"]["decision"] == "approve" and bodies["B"]["decision"] == "decline"
    assert all(b["customer_message"] and isinstance(b["evidence"], list) for b in bodies.values())


def test_resolving_a_non_waiting_purchase_fails(db):
    async def body(pool):
        assert await ask(pool, buy("A", "20.00"), m_=mandate()) == "approve"
        with pytest.raises(IllegalTransition):
            await resolver(pool).answer("A", "approve", now=NOW)
        await ask(pool, buy("B", "20.00", ts="2026-08-12T09:05:00Z"))
        await resolver(pool).answer("B", "decline", now=NOW)
        with pytest.raises(IllegalTransition):
            await resolver(pool).answer("B", "approve", now=NOW)  # already answered

    with_pool(db, body)
    assert sql(db, "select count(*) n from outbox where endpoint = 'resolve'")[0]["n"] == 1


def test_a_now_failing_limit_cannot_be_approved_and_the_record_stays_truthful(db):
    async def body(pool):
        await ask(pool, buy("A", "200.00"))                                   # waits for the customer
        await ask(pool, buy("B", "150.00", ts="2026-08-12T09:30:00Z"), m_=mandate(
            Rule(m.F_BILLING_CHF, "<=", Decimal("300"), currency="CHF", scope="period", period_days=7)))
        # B was approved automatically meanwhile; approving A now would make CHF 350 in 7 days.
        result = await resolver(pool).answer("A", "approve", now=NOW + timedelta(seconds=30))
        return result

    result = with_pool(db, body)
    assert result.state == "waiting" and "over_period_limit" in result.blocked
    assert "CHF 350.00" in result.explanation
    assert state(db, "A")["state"] == "waiting"  # nothing recorded as approved
    assert sql(db, "select count(*) n from outbox where endpoint = 'resolve'")[0]["n"] == 0

    async def reject(pool):
        return await resolver(pool).answer("A", "decline", now=NOW + timedelta(seconds=40))

    assert with_pool(db, reject).state == "declined"  # only Reject remains


def test_the_answer_window_is_an_explicit_expiry_per_ask(db):
    async def body(pool):
        await ask(pool, buy("A", "20.00"), expires=NOW + timedelta(seconds=120))
        await ask(pool, buy("B", "30.00", ts="2026-08-12T09:05:00Z"), expires=NOW + timedelta(seconds=300))
        late = await resolver(pool).answer("A", "approve", now=NOW + timedelta(seconds=150))
        fine = await resolver(pool).answer("B", "approve", now=NOW + timedelta(seconds=150))
        return late, fine

    late, fine = with_pool(db, body)
    assert state(db, "A")["ask_expires_at"] == NOW + timedelta(seconds=120)
    assert late.state == "timed_out" and "expired" in late.explanation
    assert fine.state == "approved"


def test_ask_times_out_after_120s(db):
    async def body(pool):
        await ask(pool, buy("A", "200.00"), expires=NOW + timedelta(seconds=120))
        sweeper = Sweeper(ResolutionTransaction(pool))
        early = await sweeper.run_once(now=NOW + timedelta(seconds=119))
        late = await sweeper.run_once(now=NOW + timedelta(seconds=120))
        again = await sweeper.run_once(now=NOW + timedelta(seconds=500))
        snap = await PostgresRepository(pool).snapshot("CA0001", run_id="RUN1", platform_period_spend_chf=None)
        return early, late, again, snap

    early, late, again, snap = with_pool(db, body)
    assert (early, late, again) == ([], ["A"], [])
    assert state(db, "A")["state"] == "timed_out" and state(db, "A")["resolved_by"] == "platform"
    assert snap.approved_spend_in_window(SimTime.parse("2026-08-12T10:00:00Z"), timedelta(days=7)) == Decimal("0.00")
    kinds = [r["kind"] for r in sql(db, "select kind from decision_events where authorization_id = 'A' order by seq")]
    assert kinds[-1] == "timed_out"


def test_answer_and_sweeper_race_only_one_wins(db):
    async def body(pool):
        await ask(pool, buy("A", "20.00"), expires=NOW + timedelta(seconds=120))
        at = NOW + timedelta(seconds=120)
        results = await asyncio.gather(resolver(pool).answer("A", "approve", now=at),
                                       Sweeper(ResolutionTransaction(pool)).run_once(now=at),
                                       return_exceptions=True)
        return results

    with_pool(db, body)
    assert state(db, "A")["state"] == "timed_out"  # at the expiry instant the ask is over, either way
    assert sql(db, "select count(*) n from outbox where endpoint = 'resolve'")[0]["n"] == 0


def test_a_locked_card_does_not_stop_the_sweep_for_others(db):
    sql(db, "insert into runs values ('RUN2', 'SCEN0002', 'TM1', 1, 'CA0002', now())")

    async def body(pool):
        await ask(pool, buy("A", "20.00"), expires=NOW + timedelta(seconds=120))
        other = purchase("20.00", authorization_id="B", source_authorization_id="SRC-B", card_id="CA0002",
                         merchant=SHOP, sim_time=SimTime.parse("2026-08-12T09:00:00Z"), items=(line("IT-B"),))
        await PostgresRepository(pool).receive(other, run_id="RUN2", event={}, received_at=NOW,
                                               deadline_at=NOW + timedelta(seconds=8))
        await DecisionTransaction(pool, engine_version="t").decide(
            other, run_id="RUN2", mandate=MANDATE, facts=facts(), platform_period_spend_chf=None,
            ask_expires_at=NOW + timedelta(seconds=120))
        holder = await asyncpg.connect(db)
        try:
            await holder.execute("begin")
            await holder.execute("select pg_advisory_xact_lock(hashtext('card:CA0001'))")
            swept = await Sweeper(ResolutionTransaction(pool, lock_timeout_ms=200)).run_once(
                now=NOW + timedelta(seconds=200))
            await holder.execute("rollback")
        finally:
            await holder.close()
        return swept

    assert with_pool(db, body) == ["B"]
    assert state(db, "A")["state"] == "waiting"  # left for the next run
