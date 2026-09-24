"""Read API for the app (LEASH-124), against a throw-away Postgres, validated against the contract."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import asyncpg
import jsonschema
import pytest
import yaml
from alembic import command
from fastapi.testclient import TestClient

from factories import facts, line, mandate, merchant, purchase
from leash.adapters.http.query_api import create_query_app
from leash.adapters.pack.loader import Pack
from leash.adapters.pack.seed import seed
from leash.adapters.postgres.repository import PostgresRepository
from leash.adapters.postgres.unit_of_work import DecisionTransaction, ResolutionTransaction
from leash.application.resolve import ResolveAsk
from leash.domain import mandate as m
from leash.domain.clock import SimTime
from leash.domain.mandate import Rule
from adapters.test_schema import alembic, sql

ENGINE = Path(__file__).resolve().parents[2]
DATA = ENGINE.parents[1] / "data"
SPEC = yaml.safe_load((ENGINE.parent / "contracts" / "policy-api.yaml").read_text())
NOW = datetime.now(timezone.utc).replace(microsecond=0)
SHOP = merchant(merchant_id="ME0001", name="Alpine Basket")
WEEK_300 = Rule(m.F_BILLING_CHF, "<=", Decimal("300"), currency="CHF", scope="period", period_days=7)
MANDATE = mandate(Rule(m.F_SIZE, "=", "43"), WEEK_300)


class Mandates:
    def for_run(self, run_id):
        return MANDATE


def schema(name):
    return {"$ref": f"#/components/schemas/{name}", "components": SPEC["components"]}


@pytest.fixture
def db(test_database_url):
    command.upgrade(alembic(test_database_url), "head")
    sql(test_database_url,
        "insert into mandates values ('TM1', 'Order groceries', 'active', now())",
        """insert into mandate_versions values ('TM1', 1,
           '[{"field": "authorization.billing_amount_chf", "operator": "<=", "value": 300, "currency": "CHF",
              "scope": "period", "period_days": 7}]', 'ask', '{}', now() - interval '1 hour')""",
        """insert into mandate_versions values ('TM1', 2,
           '[{"field": "authorization.billing_amount_chf", "operator": "<=", "value": 300, "currency": "CHF",
              "scope": "period", "period_days": 7}]', 'decline', '{}', now())""",
        "insert into runs values ('RUN1', 'SCEN0001', 'TM1', 1, 'CA0001', now())")

    async def go():
        conn = await asyncpg.connect(test_database_url)
        try:
            await seed(conn, Pack(DATA))
        finally:
            await conn.close()
        pool = await asyncpg.create_pool(test_database_url, min_size=1, max_size=2)
        try:
            repo, tx = PostgresRepository(pool), DecisionTransaction(pool, engine_version="leash-test")
            for aid, chf, sizes, ts in (("A", "120.00", ("43",), "2026-08-12T09:00:00Z"),  # approve
                                        ("B", "90.00", None, "2026-08-12T10:00:00Z"),       # ask (size unknown)
                                        ("C", "60.00", None, "2026-08-12T11:00:00Z"),       # ask, then approved
                                        ("D", "20.00", ("44",), "2026-08-12T12:00:00Z")):   # decline (size)
                p = purchase(chf, authorization_id=aid, source_authorization_id=f"AU-{aid}", card_id="CA0001",
                             merchant=SHOP, sim_time=SimTime.parse(ts),
                             items=(line(f"IT-{aid}", details=f"Size {'/'.join(sizes or ())} shoes"),))
                # the platform's counter: approved spend before this purchase (C is approved only later)
                event = {"context": {"approved_spend_in_period_chf": 0.0 if aid == "A" else 120.0}}
                await repo.receive(p, run_id="RUN1", event=event, received_at=NOW,
                                   deadline_at=NOW + timedelta(seconds=8))
                await tx.decide(p, run_id="RUN1", mandate=MANDATE, facts=facts(sizes=sizes),
                                platform_period_spend_chf=None, ask_expires_at=NOW + timedelta(seconds=120))
            await pool.execute("update outbox set sent_at = now() where authorization_id in ('A', 'D')")
            await ResolveAsk(ResolutionTransaction(pool), Mandates(), engine_version="t").answer(
                "C", "approve", now=NOW + timedelta(seconds=5))
        finally:
            await pool.close()
    asyncio.run(go())
    return test_database_url


def client(url):
    return TestClient(create_query_app(url, Mandates(), clock=lambda: NOW + timedelta(seconds=10)))


def test_open_asks_include_expiry(db):
    with client(db) as c:
        body = c.get("/api/asks").json()
    jsonschema.validate(body, schema("AskList"))
    [ask] = body["asks"]
    assert ask["authorization_id"] == "B"
    assert datetime.fromisoformat(ask["expires_at"].replace("Z", "+00:00")) == NOW + timedelta(seconds=120)
    assert ask["reasons"] and ask["payment"]["final_state"] == "waiting"


def test_ask_that_can_no_longer_be_approved_says_why(db):
    with client(db) as c:
        [ask] = c.get("/api/asks").json()["asks"]
    assert ask["can_approve"] is True and ask["cannot_approve_reason"] is None  # 120 + 60 + 90 = 270 ≤ 300
    # A was really CHF 250: approving B would now make CHF 400 in the week (DEC-012).
    sql(db, """update authorizations set purchase = jsonb_set(purchase, '{billing_amount_chf}', '"250.00"')
               where authorization_id = 'A'""")
    with client(db) as c:
        [ask] = c.get("/api/asks").json()["asks"]
    assert ask["can_approve"] is False and "CHF 400.00" in ask["cannot_approve_reason"]


def test_engine_verdict_and_customer_outcome_are_separate(db):
    with client(db) as c:
        body = c.get("/api/payments", params={"run_id": "RUN1"}).json()
    jsonschema.validate(body, schema("PaymentList"))
    by_id = {p["authorization_id"]: p for p in body["payments"]}
    assert [p["authorization_id"] for p in body["payments"]] == ["A", "B", "C", "D"]
    assert (by_id["C"]["engine_verdict"], by_id["C"]["final_state"], by_id["C"]["resolved_by"]) == (
        "step_up", "approved", "customer")
    assert (by_id["A"]["engine_verdict"], by_id["A"]["final_state"], by_id["A"]["resolved_by"]) == (
        "approve", "approved", "engine")
    assert (by_id["B"]["engine_verdict"], by_id["B"]["final_state"], by_id["B"]["resolved_by"]) == (
        "step_up", "waiting", None)
    assert by_id["D"]["final_state"] == "declined" and by_id["A"]["billing_amount_chf"] == "120.00"


def test_payment_detail_has_checks_evidence_shop_text_and_what_was_sent(db):
    with client(db) as c:
        a = c.get("/api/payments/A").json()
        b = c.get("/api/payments/B").json()
        missing = c.get("/api/payments/ZZZ")
    jsonschema.validate(a, schema("PaymentDetail"))
    assert a["sent_to_viseca"]["decision"] == "approve" and a["engine_version"] == "leash-test"
    assert b["sent_to_viseca"] is None  # decided but not yet marked sent
    assert a["shop_texts"] == [{"item_id": "IT-A", "text": "Size 43 shoes"}]
    assert a["reader"] == {"name": "regex", "model_unavailable": False}
    assert any(ch["key"] == "size" for ch in a["checks"]) and a["evidence"]
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"


def test_spending_totals_match_the_ledger(db):
    with client(db) as c:
        body = c.get("/api/spending", params={"run_id": "RUN1"}).json()
        default = c.get("/api/spending").json()
    jsonschema.validate(body, schema("Spending"))
    assert body == default  # the latest run by default
    assert (body["period_days"], body["limit_chf"], body["approved_chf"], body["remaining_chf"]) == (
        7, "300.00", "180.00", "120.00")  # A 120 + C 60; B waits, D declined
    assert body["platform_counter_chf"] == "120.00" and body["mismatch"] is False  # as of D's arrival
    # LEASH-130: approved is what the limit is enforced against (a reservation the moment it is
    # decided); accepted is the narrower fact. Nothing here has been acknowledged by the platform yet.
    assert (body["accepted_chf"], body["awaiting_platform_chf"]) == ("0.00", "180.00")


def test_accepted_spend_is_measured_over_the_same_window_as_approved_spend(db):
    """Otherwise `accepted_chf` can exceed the total it is documented as being part of, and
    `awaiting_platform_chf` clamps to zero while spend is genuinely outstanding."""
    import asyncio

    import asyncpg

    async def acknowledge_everything() -> None:
        conn = await asyncpg.connect(db)
        try:
            await conn.execute("update authorizations set delivery = 'accepted', platform_outcome = 'accepted' "
                               "where state = 'approved'")
        finally:
            await conn.close()

    asyncio.run(acknowledge_everything())
    with client(db) as c:
        body = c.get("/api/spending", params={"run_id": "RUN1"}).json()
    assert body["approved_chf"] == "180.00"
    assert body["accepted_chf"] == "180.00", "everything in the window is acknowledged"
    assert body["awaiting_platform_chf"] == "0.00"
    assert Decimal(body["accepted_chf"]) <= Decimal(body["approved_chf"]), \
        "accepted is a part of approved, never more than it"


def test_mandate_versions(db):
    with client(db) as c:
        body = c.get("/api/mandates/TM1/versions").json()
        missing = c.get("/api/mandates/NOPE/versions")
    jsonschema.validate(body, schema("MandateVersionList"))
    assert [(v["version"], v["change"], v["uncertainty_policy"]) for v in body["versions"]] == [
        (1, "confirmed", "ask"), (2, "tightened", "decline")]
    assert missing.status_code == 404


def test_a_reconnecting_app_gets_the_same_complete_state(db):
    with client(db) as first:
        before = {path: first.get(path).json() for path in ("/api/payments", "/api/asks", "/api/spending")}
    with client(db) as second:  # a new connection, no event history
        after = {path: second.get(path).json() for path in ("/api/payments", "/api/asks", "/api/spending")}
    assert before == after and len(after["/api/payments"]["payments"]) == 4


def _add(url, aid, chf, ts, counter, sizes=("43",)):
    async def go():
        pool = await asyncpg.create_pool(url, min_size=1, max_size=2)
        try:
            p = purchase(chf, authorization_id=aid, source_authorization_id=f"AU-{aid}", card_id="CA0001",
                         merchant=SHOP, sim_time=SimTime.parse(ts), items=(line(f"IT-{aid}"),))
            await PostgresRepository(pool).receive(p, run_id="RUN1", event={"context": {
                "approved_spend_in_period_chf": counter}}, received_at=NOW, deadline_at=NOW + timedelta(seconds=8))
            await DecisionTransaction(pool, engine_version="t").decide(
                p, run_id="RUN1", mandate=MANDATE, facts=facts(sizes=sizes), platform_period_spend_chf=None)
        finally:
            await pool.close()
    asyncio.run(go())


def test_the_platform_counter_is_compared_with_spend_before_that_purchase(db):
    # Review finding: the counter is the spend *before* the purchase; comparing it with the total raised false alarms.
    _add(db, "E", "20.00", "2026-08-12T13:00:00Z", counter=180.0)  # approved; correct counter = A 120 + C 60
    with client(db) as c:
        body = c.get("/api/spending").json()
    assert (body["approved_chf"], body["platform_counter_chf"], body["mismatch"]) == ("200.00", "180.00", False)
    _add(db, "F", "10.00", "2026-08-12T14:00:00Z", counter=150.0)  # the platform really disagrees
    with client(db) as c:
        body = c.get("/api/spending").json()
    assert (body["platform_counter_chf"], body["mismatch"]) == ("150.00", True)


def test_an_ask_approved_after_the_next_purchase_arrived_is_not_a_mismatch(db):
    # Review finding: B (waiting) approved after E arrived; E's counter rightly excluded B.
    _add(db, "E", "20.00", "2026-08-12T13:00:00Z", counter=180.0)  # A 120 + C 60 approved when E arrived

    async def approve_b():
        pool = await asyncpg.create_pool(db, min_size=1, max_size=2)
        try:
            await ResolveAsk(ResolutionTransaction(pool), Mandates(), engine_version="t").answer(
                "B", "approve", now=NOW + timedelta(seconds=20))
        finally:
            await pool.close()
    asyncio.run(approve_b())
    with client(db) as c:
        body = c.get("/api/spending").json()
    assert (body["approved_chf"], body["platform_counter_chf"], body["mismatch"]) == ("290.00", "180.00", False)
