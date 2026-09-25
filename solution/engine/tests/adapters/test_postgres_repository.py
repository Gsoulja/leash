"""Postgres repository against a throw-away database (migrated and seeded from the pack)."""

import json
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import asyncpg
import pytest
from alembic import command

from factories import line, merchant, money, purchase
from leash.adapters.pack.loader import Pack
from leash.adapters.pack.seed import seed
from leash.adapters.postgres.repository import PostgresRepository
from leash.domain.checks import Check
from leash.domain.clock import SimTime
from leash.domain.decide import Decision
from leash.domain.states import IllegalTransition
from leash.ports.repository import Repository
from test_schema import alembic, sql

DATA = Path(__file__).resolve().parents[4] / "data"
NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
PIXEL = merchant(merchant_id="ME0022", name="PixelHarbor", category="electronics", mcc="5732")


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
        "insert into runs values ('RUN1', 'SCEN0004', 'TM1', 1, 'CA0039', now())",
        "insert into runs values ('OTHER', 'SCEN0004', 'TM1', 1, 'CA0039', now())")
    return test_database_url


def with_repo(url, body):
    async def go():
        pool = await asyncpg.create_pool(url, min_size=1, max_size=2)
        try:
            return await body(PostgresRepository(pool))
        finally:
            await pool.close()
    return asyncio.run(go())


def buy(aid, ts, chf, *, card="CA0039", shop=PIXEL, items=None, device="DVC-1"):
    return purchase(chf, authorization_id=aid, source_authorization_id=f"SRC-{aid}", card_id=card, merchant=shop,
                    sim_time=SimTime.parse(ts), device_id=device, items=items or (line(),))


def decision(verdict, code=None):
    checks = (Check("price", "Price", "pass" if verdict == "approve" else "fail", "a", "b", "detail", code),)
    return Decision(verdict, checks, (code,) if code else ())


async def received(repo, p, run_id="RUN1", event=None):
    return await repo.receive(p, run_id=run_id, event=event or {"authorization": {"authorization_id":
                              p.authorization_id}}, received_at=NOW, deadline_at=NOW + timedelta(seconds=8))


def test_postgres_repository_implements_the_port():
    assert issubclass(PostgresRepository, Repository)


def test_repeat_delivery_returns_saved_decision(db):
    async def body(repo):
        p = buy("AZ-1", "2026-08-12T09:15:00Z", "289.00")
        first = await received(repo, p)
        await repo.record_decision("AZ-1", decision("decline", "over_order_limit"), response={"decision": "decline"})
        again = await received(repo, p)
        return first, again

    first, again = with_repo(db, body)
    assert first is None  # new
    assert (again.state, again.engine_verdict, again.response) == ("declined", "decline", {"decision": "decline"})


def test_a_redelivery_with_amended_terms_is_not_a_repeat_of_the_saved_verdict(db):
    """LEASH-102: the same live ID carrying a different cart is a different attempt, not a retry.

    Nothing is rewritten (DEC-003): the stored decision stays as it was decided, and the mismatch is
    raised as an integrity alert so the approval cannot be handed back as though it covered these terms.
    """
    async def body(repo):
        p = buy("AZ-1", "2026-08-12T09:15:00Z", "289.00")
        await received(repo, p)
        await repo.record_decision("AZ-1", decision("approve"), response={"decision": "approve"})
        amended = buy("AZ-1", "2026-08-12T09:15:00Z", "368.00",
                      items=(line(), line(line_no=2, item_id="IT0099", name="Warranty", unit_price=money("79.00"))))
        again = await received(repo, amended)
        async with repo._pool.acquire() as conn:
            alerts = await conn.fetch("select payload from decision_events where authorization_id = 'AZ-1' "
                                      "and kind = 'integrity_alert'")
        return again, [json.loads(a["payload"]) for a in alerts]

    again, alerts = with_repo(db, body)
    assert again.engine_verdict == "approve", "the record stays truthful about what was decided"
    assert again.changed_terms, "the amended terms have to be reported, not replayed"
    assert any("billing_chf" in m or "item" in m for m in again.changed_terms), again.changed_terms
    assert alerts and any("mismatches" in a for a in alerts), alerts


def test_a_redelivery_of_the_same_terms_stays_a_plain_repeat(db):
    async def body(repo):
        p = buy("AZ-1", "2026-08-12T09:15:00Z", "289.00")
        await received(repo, p)
        await repo.record_decision("AZ-1", decision("approve"), response={"decision": "approve"})
        return await received(repo, buy("AZ-1", "2026-08-12T09:15:00Z", "289.00"))

    again = with_repo(db, body)
    assert again.engine_verdict == "approve" and not again.changed_terms


def test_repeat_delivery_before_a_decision_reports_it_in_flight(db):
    async def body(repo):
        p = buy("AZ-1", "2026-08-12T09:15:00Z", "289.00")
        await received(repo, p)
        return await received(repo, p)

    again = with_repo(db, body)
    assert (again.state, again.engine_verdict, again.response) == ("received", None, None)


def test_snapshot_window_sum(db):
    async def body(repo):
        for aid, ts, chf, verdict in (("A", "2026-08-10T09:00:00Z", "100.00", "approve"),
                                      ("B", "2026-08-12T09:00:00Z", "50.00", "approve"),
                                      ("C", "2026-08-13T09:00:00Z", "70.00", "step_up"),
                                      ("D", "2026-08-13T10:00:00Z", "30.00", "decline")):
            await received(repo, buy(aid, ts, chf))
            await repo.record_decision(aid, decision(verdict), response={})
        return await repo.snapshot("CA0039", run_id="RUN1", platform_period_spend_chf=Decimal("150.00"))

    snap = with_repo(db, body)
    now = SimTime.parse("2026-08-16T09:30:00Z")
    assert snap.approved_spend_in_window(now, timedelta(days=7)) == Decimal("150.00")  # A + B; C waits, D declined
    assert snap.approved_spend_in_window(now, timedelta(days=5)) == Decimal("50.00")
    assert snap.platform_period_spend_chf == Decimal("150.00")
    assert {p.purchase.authorization_id: p.state for p in snap.prior} == {
        "A": "approved", "B": "approved", "C": "waiting", "D": "declined"}


def test_snapshot_includes_history_familiarity_devices_countries_and_names(db):
    async def body(repo):
        return await repo.snapshot("CA0039", run_id="RUN1", platform_period_spend_chf=None)

    snap = with_repo(db, body)
    assert snap.familiarity("ME0022") == 6
    assert snap.baseline.devices and snap.baseline.countries
    assert snap.merchant_names["ME0022"] == "PixelHarbor" and len(snap.merchant_names) == 58


def test_snapshot_recent_orders_at_merchant_and_run_isolation(db):
    async def body(repo):
        await received(repo, buy("A", "2026-08-12T09:15:00Z", "289.00"))
        await repo.record_decision("A", decision("step_up"), response={})
        await received(repo, buy("X", "2026-08-12T09:16:00Z", "10.00"), run_id="OTHER")
        await received(repo, buy("Y", "2026-08-12T09:17:00Z", "10.00", card="CA0001"))
        await received(repo, buy("R", "2026-08-12T09:18:00Z", "10.00"))  # received, no decision yet
        return await repo.snapshot("CA0039", run_id="RUN1", platform_period_spend_chf=None)

    snap = with_repo(db, body)
    recent = snap.recent_at_merchant("ME0022", SimTime.parse("2026-08-12T09:40:00Z"), timedelta(hours=24))
    assert [p.purchase.authorization_id for p in recent] == ["A"]
    assert [p.purchase.authorization_id for p in snap.prior] == ["A"]  # other run, other card, undecided excluded


def test_purchases_round_trip_exactly(db):
    p = buy("A", "2026-08-12T09:15:00Z", "289.00", items=(line("IT0017", quantity=2, name="Monitor", category="electronics",
                                                               details="27 inch"), line("IT0066", line_no=2)))

    async def body(repo):
        await received(repo, p)
        await repo.record_decision("A", decision("approve"), response={})
        return await repo.snapshot("CA0039", run_id="RUN1", platform_period_spend_chf=None)

    [prior] = with_repo(db, body).prior
    assert prior.purchase == p


def test_saving_an_illegal_transition_fails(db):
    async def body(repo):
        await received(repo, buy("A", "2026-08-12T09:15:00Z", "20.00"))
        await repo.record_decision("A", decision("approve"), response={})
        errors = []
        for call in (repo.record_decision("A", decision("decline"), response={}),  # decided twice
                     repo.transition("A", "approved", by="customer"),              # not waiting
                     repo.transition("A", "timed_out", by="engine")):
            try:
                await call
            except IllegalTransition as exc:
                errors.append(str(exc))
        await received(repo, buy("B", "2026-08-12T09:16:00Z", "20.00"))
        await repo.record_decision("B", decision("step_up"), response={}, ask_expires_at=NOW + timedelta(minutes=2))
        try:
            await repo.transition("B", "approved", by="engine")  # only the customer ends a wait
        except IllegalTransition as exc:
            errors.append(str(exc))
        await repo.transition("B", "approved", by="customer")
        return errors

    errors = with_repo(db, body)
    assert len(errors) == 4
    [row] = sql(db, "select state, resolved_by from authorizations where authorization_id = 'B'")
    assert (row["state"], row["resolved_by"]) == ("approved", "customer")
    [a] = sql(db, "select state from authorizations where authorization_id = 'A'")
    assert a["state"] == "approved"  # unchanged by the failed attempts


def test_every_change_is_an_append_only_event(db):
    async def body(repo):
        await received(repo, buy("B", "2026-08-12T09:16:00Z", "20.00"))
        await repo.record_decision("B", decision("step_up"), response={"decision": "step_up"})
        await repo.transition("B", "declined", by="customer")

    with_repo(db, body)
    rows = sql(db, "select kind from decision_events where authorization_id = 'B' order by seq")
    assert [r["kind"] for r in rows] == ["received", "decided", "customer_resolved"]


def test_snapshot_reconciles_with_the_event_context(db):
    async def body(repo):
        await received(repo, buy("A", "2026-08-12T09:00:00Z", "100.00"))
        await repo.record_decision("A", decision("approve"), response={})
        await received(repo, buy("B", "2026-08-12T09:05:00Z", "40.00"))
        await repo.record_decision("B", decision("step_up"), response={})
        now = buy("N", "2026-08-12T09:08:00Z", "10.00")
        snap = await repo.snapshot("CA0039", run_id="RUN1", platform_period_spend_chf=Decimal("140.00"))
        context = {"approved_spend_in_period_chf": 140.0, "recent_authorizations": [
            {"authorization_id": "A", "timestamp": "2026-08-12T09:00:00Z", "merchant_id": "ME0022",
             "billing_amount_chf": 100.0, "status": "approved"},
            {"authorization_id": "B", "timestamp": "2026-08-12T09:05:00Z", "merchant_id": "ME0022",
             "billing_amount_chf": 40.0, "status": "approved"},    # we still have it waiting
            {"authorization_id": "Z", "timestamp": "2026-08-12T09:06:00Z", "merchant_id": "ME0022",
             "billing_amount_chf": 5.0, "status": "pending"}]}     # we never saw it
        clean = {"approved_spend_in_period_chf": 100.0, "recent_authorizations": context["recent_authorizations"][:1]}
        return (await repo.reconcile(now, snap, context, period=timedelta(days=7)),
                await repo.reconcile(now, snap, clean, period=timedelta(days=7)))

    mismatches, clean = with_repo(db, body)
    assert clean == []
    assert any("B" in m and "waiting" in m and "approved" in m for m in mismatches)
    assert any("Z" in m for m in mismatches)
    assert any("140.00" in m and "100.00" in m for m in mismatches)
    rows = sql(db, "select payload from decision_events where kind = 'integrity_alert' and authorization_id = 'N'")
    assert len(rows) == 1


def test_a_repeat_says_whether_the_platform_already_accepted_the_answer(db):
    """So the caller can tell a resend (our POST never landed) from the 409 loop (it did).

    The platform re-delivers a step_up'd purchase on every poll until the customer resolves it; sending
    the decision again is refused, and that refusal is not a reason to keep trying.
    """
    async def body(repo):
        p = buy("AZ-1", "2026-08-12T09:15:00Z", "18.00")
        await received(repo, p)
        await repo.record_decision("AZ-1", decision("step_up", "ask_customer"), response={"decision": "step_up"},
                                   ask_expires_at=NOW + timedelta(seconds=120))
        before = await received(repo, p)
        async with repo._pool.acquire() as conn, conn.transaction():  # what a successful POST records
            await PostgresRepository.record_delivery(conn, "AZ-1", accepted=True, outcome="accepted", at=NOW)
        return before, await received(repo, p)

    before, after = with_repo(db, body)
    assert before.sent is False, "not acknowledged yet: a redelivery must resend it"
    assert after.sent is True, "the platform has it; only /resolve moves this on"
