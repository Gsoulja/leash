"""LEASH-121: the SCEN0000 event, built from the pack as the platform would deliver it, goes through the
worker's own path offline: envelope → request (translate + mandate from hard_rules) → DecidePurchase →
the /decision body. Only the store is in memory instead of Postgres."""

import asyncio
from pathlib import Path

import httpx

from fixtures.mandates import MANDATES
from leash.adapters.pack.loader import Pack
from leash.adapters.regex_reader import RegexReader
from leash.adapters.viseca_api.client import VisecaClient
from leash.adapters.viseca_api.event_schema import load_event_validator
from leash.adapters.viseca_api.translate import request_from_envelope
from leash.application.decide_purchase import DeadlinePlan, DecidePurchase
from leash.application.replay import InMemoryDecisionStore
from leash.policy.hard_rules import mandate_to_api
from fake_api.app import FakeViseca

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "data"
VALIDATE = load_event_validator(DATA / "schemas" / "authorization_event.schema.json")
PLAN = DeadlinePlan(send_seconds=0.5, lock_seconds=0.5, decide_seconds=0.5, fallback_seconds=0.5)


class Sent:
    def __init__(self) -> None:
        self.bodies: dict[str, dict] = {}

    async def send(self, authorization_id, body, budget_seconds=None):
        self.bodies[authorization_id] = dict(body)


def run_scen0000():
    pack = Pack(DATA)
    fake = FakeViseca(pack, api_key="k")
    client = VisecaClient("k", "http://fake", transport=httpx.ASGITransport(app=fake.app))
    store, sender = InMemoryDecisionStore(pack), Sent()
    use_case = DecidePurchase(store=store, reader=RegexReader(), sender=sender, plan=PLAN, engine_version="slice",
                              human_window_seconds=120)

    async def go():
        body = {**mandate_to_api(MANDATES["SCEN0000"]), "guidance": [], "open_questions": []}
        draft = await client.create_mandate(body)
        mandate_id = (await client.confirm_mandate(draft["draft_id"]))["mandate_id"]
        await client.start_run("SCEN0000", mandate_id)
        results = []
        while (envelope := await client.next_decision_request(wait=0)) is not None:
            request, translated = request_from_envelope(envelope, validate=VALIDATE)
            result = await use_case.handle(request)
            results.append((request, translated, result))
            await client.post_decision(request.purchase.authorization_id, sender.bodies[request.purchase.authorization_id])
        return results

    return pack, asyncio.run(go()), sender


def test_every_scen0000_event_is_decided_through_the_worker_path():
    pack, results, sender = run_scen0000()
    assert results and len(results) == len(pack.attempts("SCEN0000"))
    for request, translated, result in results:
        assert result.path == "decided", result.path
        assert request.run_id and request.mandate == translated.mandate  # the event's mandate, not a local copy
        assert request.mandate.rules == MANDATES["SCEN0000"].rules
        assert sender.bodies[request.purchase.authorization_id]["decision"] == result.verdict


def test_the_decision_carries_a_plain_message_and_evidence():
    _, results, sender = run_scen0000()
    for request, _, _ in results:
        body = sender.bodies[request.purchase.authorization_id]
        assert body["authorization_id"] == request.purchase.authorization_id
        assert body["customer_message"].strip()
        assert body["evidence"], body


def test_chf_20_exactly_is_approved_on_the_live_path():
    _, results, sender = run_scen0000()
    by_source = {t.purchase.source_authorization_id: r for _, t, r in results}
    assert by_source["AU0001"].verdict == "approve"


def test_a_repeat_delivery_returns_the_saved_verdict_and_counts_once():
    pack = Pack(DATA)
    fake = FakeViseca(pack, api_key="k")
    client = VisecaClient("k", "http://fake", transport=httpx.ASGITransport(app=fake.app))
    store, sender = InMemoryDecisionStore(pack), Sent()
    use_case = DecidePurchase(store=store, reader=RegexReader(), sender=sender, plan=PLAN, engine_version="slice",
                              human_window_seconds=120)

    async def go():
        body = {**mandate_to_api(MANDATES["SCEN0000"]), "guidance": [], "open_questions": []}
        draft = await client.create_mandate(body)
        await client.start_run("SCEN0000", (await client.confirm_mandate(draft["draft_id"]))["mandate_id"])
        request, _ = request_from_envelope(await client.next_decision_request(wait=0), validate=VALIDATE)
        return await use_case.handle(request), await use_case.handle(request)

    first, again = asyncio.run(go())
    assert (first.path, again.path) == ("decided", "repeat") and again.verdict == first.verdict
    assert len(store.ledger.decisions) == 1
