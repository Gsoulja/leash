"""The customer's answer to an ask (LEASH-063): POST /api/asks/{authorization_id}/answer, through the full API
process, against a throw-away Postgres and the fake platform. Validated against contracts/policy-api.yaml."""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import asyncpg
import httpx
import jsonschema
import pytest
import yaml
from fastapi.testclient import TestClient

from factories import facts, line, merchant, purchase
from fake_api.app import FakeViseca
from leash.adapters.pack.loader import Pack
from leash.adapters.postgres.migrate import migrate_and_seed
from leash.adapters.postgres.repository import PostgresRepository
from leash.adapters.postgres.unit_of_work import DecisionTransaction, ResolutionTransaction
from leash.adapters.viseca_api.client import VisecaClient
from leash.application.resolve import Sweeper
from leash.domain import mandate as m
from leash.domain.clock import SimTime
from leash.domain.mandate import CompiledMandate, Rule
from leash.policy.hard_rules import rule_to_api
from leash.service import create_api, load_catalogue

ENGINE = Path(__file__).resolve().parents[2]
DATA = ENGINE.parents[1] / "data"
SPEC = yaml.safe_load((ENGINE.parent / "contracts" / "policy-api.yaml").read_text())
NOW = datetime.now(timezone.utc)
SHOP = merchant(merchant_id="ME0001", name="Alpine Basket")
WEEK_100 = Rule(m.F_BILLING_CHF, "<=", Decimal("100"), currency="CHF", scope="period", period_days=7)
SIZE_43 = Rule(m.F_SIZE, "=", "43")
MANDATE = CompiledMandate("Shoes in size 43, CHF 100 a week", (SIZE_43, WEEK_100), "ask")


def valid(body, name):
    jsonschema.validate(body, {"$ref": f"#/components/schemas/{name}", "components": SPEC["components"]})
    return body


def buy(aid, chf, ts, sizes):
    return purchase(chf, authorization_id=aid, source_authorization_id=f"AU-{aid}", card_id="CA0001", merchant=SHOP,
                    sim_time=SimTime.parse(ts), items=(line(f"IT-{aid}", details=f"Size {'/'.join(sizes or ())}"),))


@pytest.fixture
def api(test_database_url):
    """RUN1 with asks: W1 (CHF 60) and W2 (CHF 30) waiting, OLD expired, A1 approved by the engine (CHF 50)."""
    migrate_and_seed(test_database_url, DATA)
    hard_rules = "[" + ",".join(__import__("json").dumps(rule_to_api(r)) for r in MANDATE.rules) + "]"

    async def setup():
        pool = await asyncpg.create_pool(test_database_url, min_size=1, max_size=2)
        try:
            await pool.execute("insert into mandates values ('TM1', $1, 'active', now())", MANDATE.instruction)
            await pool.execute("insert into mandate_versions values ('TM1', 1, $1::jsonb, 'ask', '{}', now())",
                               hard_rules)
            await pool.execute("insert into runs values ('RUN1', 'SCEN0002', 'TM1', 1, 'CA0001', now())")
            repo, tx = PostgresRepository(pool), DecisionTransaction(pool, engine_version="t")
            for aid, chf, ts, sizes, expires in (  # W1 is asked before A1 is approved, so it waits
                    ("W1", "60.00", "2026-08-12T10:00:00Z", None, NOW + timedelta(minutes=5)),
                    ("A1", "50.00", "2026-08-12T09:00:00Z", ("43",), NOW + timedelta(minutes=5)),
                    ("W2", "30.00", "2026-08-12T10:30:00Z", None, NOW + timedelta(minutes=5)),
                    ("OLD", "10.00", "2026-08-12T11:00:00Z", None, NOW - timedelta(seconds=1))):
                p = buy(aid, chf, ts, sizes)
                await repo.receive(p, run_id="RUN1", event={}, received_at=NOW, deadline_at=NOW + timedelta(seconds=8))
                await tx.decide(p, run_id="RUN1", mandate=MANDATE, facts=facts(sizes=sizes),
                                platform_period_spend_chf=None, ask_expires_at=expires)
        finally:
            await pool.close()

    asyncio.run(setup())
    fake = FakeViseca(Pack(DATA), api_key="k")
    viseca = VisecaClient("k", "http://fake", transport=httpx.ASGITransport(app=fake.app))
    with TestClient(create_api(test_database_url, viseca, load_catalogue(DATA), background_seconds=30)) as http:
        yield http, test_database_url


def outbox(url, aid):
    async def go():
        conn = await asyncpg.connect(url)
        try:
            return [tuple(r) for r in await conn.fetch(
                "select endpoint, body->>'decision' from outbox where authorization_id = $1 and endpoint = 'resolve'",
                aid)]
        finally:
            await conn.close()
    return asyncio.run(go())


def test_answer_after_timeout_is_409(api):
    http, url = api
    response = http.post("/api/asks/OLD/answer", json={"decision": "approve"})
    assert response.status_code == 409 and valid(response.json(), "Error")["error"]["code"] == "not_waiting"
    assert outbox(url, "OLD") == []


def test_approve_and_reject_both_reach_the_outbox(api):
    http, url = api
    approved = http.post("/api/asks/W2/answer", json={"decision": "approve"})
    assert approved.status_code == 200, approved.json()
    assert valid(approved.json(), "Payment")["final_state"] == "approved" and approved.json()["resolved_by"] == "customer"
    rejected = http.post("/api/asks/W1/answer", json={"decision": "decline"})
    assert rejected.status_code == 200 and rejected.json()["final_state"] == "declined"
    assert outbox(url, "W2") == [("resolve", "approve")] and outbox(url, "W1") == [("resolve", "decline")]


def test_answering_an_already_final_purchase_is_409(api):
    http, url = api
    assert http.post("/api/asks/A1/answer", json={"decision": "decline"}).status_code == 409
    http.post("/api/asks/W2/answer", json={"decision": "decline"})
    again = http.post("/api/asks/W2/answer", json={"decision": "approve"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "not_waiting"
    assert outbox(url, "W2") == [("resolve", "decline")] and outbox(url, "A1") == []


def test_an_answer_racing_the_sweeper_is_409_and_changes_nothing(api):
    http, url = api

    async def sweep_later():
        pool = await asyncpg.create_pool(url, min_size=1, max_size=1)
        try:
            return await Sweeper(ResolutionTransaction(pool)).run_once(now=NOW + timedelta(minutes=10))
        finally:
            await pool.close()

    assert set(asyncio.run(sweep_later())) >= {"W1", "W2"}
    response = http.post("/api/asks/W1/answer", json={"decision": "approve"})
    assert response.status_code == 409 and outbox(url, "W1") == []


def test_approve_is_refused_when_a_hard_rule_now_fails(api):
    http, url = api
    # A1 (50) is approved; W1 (60) would take the week to 110 > 100: only Reject remains (DEC-012)
    refused = http.post("/api/asks/W1/answer", json={"decision": "approve"})
    assert refused.status_code == 422 and valid(refused.json(), "Error")["error"]["code"] == "cannot_approve"
    assert "100" in refused.json()["error"]["message"]
    assert outbox(url, "W1") == []
    assert http.post("/api/asks/W1/answer", json={"decision": "decline"}).status_code == 200


def test_unknown_asks_and_bad_answers(api):
    http, _ = api
    assert http.post("/api/asks/NOPE/answer", json={"decision": "approve"}).status_code == 404
    for body in ({}, {"decision": "maybe"}, {"decision": "approve", "x": 1}, []):
        response = http.post("/api/asks/W1/answer", json=body)
        assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_request", body


def test_resolve_is_posted_at_once_but_never_before_its_decision(test_database_url, api):
    http, url = api
    sent = []

    class Recording:
        async def create_mandate(self, draft):
            raise AssertionError("not used")

        async def confirm_mandate(self, draft_id):
            raise AssertionError("not used")

        async def resolve(self, authorization_id, answer):
            sent.append((authorization_id, answer["decision"]))

    async def mark_decision_sent(aid):
        conn = await asyncpg.connect(url)
        try:
            await conn.execute("update outbox set sent_at = now() where authorization_id = $1 and endpoint = 'decision'",
                               aid)
            return [tuple(r) for r in await conn.fetch(
                "select authorization_id, sent_at is not null from outbox where endpoint = 'resolve' order by id")]
        finally:
            await conn.close()

    asyncio.run(mark_decision_sent("W2"))  # W2's decision reached Viseca; W1's did not
    with TestClient(create_api(url, Recording(), load_catalogue(DATA), background_seconds=30)) as app:
        assert app.post("/api/asks/W2/answer", json={"decision": "approve"}).status_code == 200
        assert app.post("/api/asks/W1/answer", json={"decision": "decline"}).status_code == 200
    assert sent == [("W2", "approve")]  # W1 waits for the outbox, which sends its decision first
    assert asyncio.run(mark_decision_sent("none")) == [("W2", True), ("W1", False)]


def test_the_recheck_counts_the_platforms_spend_too(test_database_url, api):
    """DEC-010: at W3's decision the platform had CHF 60 approved (we knew of 50). Approving A2 (CHF 35)
    afterwards makes it about 95; W3 (CHF 10) would exceed 100, although our own ledger says 85 + 10 = 95."""
    http, url = api

    async def setup():
        pool = await asyncpg.create_pool(url, min_size=1, max_size=2)
        try:
            repo, tx = PostgresRepository(pool), DecisionTransaction(pool, engine_version="t")
            await pool.execute("update authorizations set state = 'declined' where authorization_id in ('W1', 'W2')")
            for aid, chf, ts, sizes, counter in (("W3", "10.00", "2026-08-12T12:00:00Z", None, 60.0),
                                                 ("A2", "35.00", "2026-08-12T12:30:00Z", ("43",), None)):
                p = buy(aid, chf, ts, sizes)
                event = {"context": {"approved_spend_in_period_chf": counter}} if counter is not None else {}
                await repo.receive(p, run_id="RUN1", event=event, received_at=NOW,
                                   deadline_at=NOW + timedelta(seconds=8))
                await tx.decide(p, run_id="RUN1", mandate=MANDATE, facts=facts(sizes=sizes),
                                platform_period_spend_chf=None if counter is None else Decimal(str(counter)),
                                ask_expires_at=NOW + timedelta(minutes=5))
            return await pool.fetchval("select state from authorizations where authorization_id = 'W3'")
        finally:
            await pool.close()

    assert asyncio.run(setup()) == "waiting"
    refused = http.post("/api/asks/W3/answer", json={"decision": "approve"})
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "cannot_approve", refused.json()
    asks = {a["authorization_id"]: a for a in http.get("/api/asks").json()["asks"]}
    assert asks["W3"]["can_approve"] is False
