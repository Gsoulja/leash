"""Mandate lifecycle endpoints (LEASH-061) against the fake platform and a throw-away Postgres, validated
against contracts/policy-api.yaml."""

import asyncio
import csv
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import asyncpg
import httpx
import jsonschema
import pytest
import yaml
from alembic import command
from fastapi.testclient import TestClient

from adapters.test_schema import alembic
from fake_api.app import FakeViseca
from leash.adapters.http.policy_api import create_policy_app
from leash.adapters.pack.loader import Pack
from leash.adapters.viseca_api.client import VisecaClient
from leash.policy.compiler import CatalogueItem

ENGINE = Path(__file__).resolve().parents[2]
DATA = ENGINE.parents[1] / "data"
SPEC = yaml.safe_load((ENGINE.parent / "contracts" / "policy-api.yaml").read_text())
with (DATA / "items.csv").open() as f:
    CATALOGUE = [CatalogueItem(r["item_id"], r["item_name"], r["item_category"]) for r in csv.DictReader(f)]
CLEAR = "Buy the 27-inch monitor I chose, from a seller I have bought from before, for CHF 400 or less. " \
        "Ask me when uncertain."
UNCLEAR = "Buy something nice for a friend."


def valid(body, name):
    jsonschema.validate(body, {"$ref": f"#/components/schemas/{name}", "components": SPEC["components"]})
    return body


class Counting:
    """The Viseca client, counting mandate calls."""

    def __init__(self, client):
        self.client, self.creates, self.confirms = client, 0, 0

    async def create_mandate(self, draft):
        self.creates += 1
        return await self.client.create_mandate(draft)

    async def confirm_mandate(self, draft_id):
        self.confirms += 1
        await asyncio.sleep(0.05)  # wide enough for a double click to overlap
        return await self.client.confirm_mandate(draft_id)


@pytest.fixture
def api(test_database_url):
    command.upgrade(alembic(test_database_url), "head")
    fake = FakeViseca(Pack(DATA), api_key="k")
    viseca = Counting(VisecaClient("k", "http://fake", transport=httpx.ASGITransport(app=fake.app)))
    with TestClient(create_policy_app(test_database_url, viseca, CATALOGUE)) as http:
        yield http, viseca, fake, test_database_url


def ready_draft(http):
    draft = http.post("/api/policies/drafts", json={"instruction": CLEAR})
    assert draft.status_code == 201, draft.text
    return valid(draft.json(), "PolicyDraft")


def test_confirm_requires_draft(api):
    http, viseca, _, _ = api
    response = http.post("/api/policies/drafts/LD-nope/confirm", json={"confirmed": True})
    assert response.status_code == 404 and response.json()["error"]["code"] == "draft_not_found"
    draft = ready_draft(http)
    response = http.post(f"/api/policies/drafts/{draft['draft_id']}/confirm", json={"confirmed": True})
    assert response.status_code == 409 and response.json()["error"]["code"] == "not_submitted"
    assert viseca.confirms == 0


def test_a_local_draft_is_compiled_and_kept_apart_from_the_platform(api):
    http, viseca, fake, _ = api
    draft = ready_draft(http)
    assert draft["draft_id"].startswith("LD-") and viseca.creates == 0 and not fake.mandates
    assert {"field": "authorization.billing_amount_chf", "operator": "<=", "value": 400, "currency": "CHF",
            "scope": "purchase"} in draft["hard_rules"]
    assert http.get(f"/api/policies/drafts/{draft['draft_id']}").json() == draft
    assert http.get("/api/policies/drafts/LD-nope").status_code == 404


def test_submit_posts_the_draft_to_viseca_and_shows_exactly_what_was_posted(api):
    http, viseca, fake, _ = api
    draft = ready_draft(http)
    posted = valid(http.post(f"/api/policies/drafts/{draft['draft_id']}/submit").json(), "PlatformDraft")
    assert posted["draft_id"] == draft["draft_id"] and posted["platform_draft_id"] != draft["draft_id"]
    stored = fake.mandates[posted["platform_draft_id"]].body
    assert stored["hard_rules"] == posted["hard_rules"] == draft["hard_rules"]
    assert stored["instruction"] == CLEAR and stored["uncertainty_policy"] == "ask"
    again = http.post(f"/api/policies/drafts/{draft['draft_id']}/submit").json()
    assert again == posted and viseca.creates == 1  # submitting again reuses the platform draft


def test_a_draft_with_open_questions_cannot_be_submitted(api):
    http, viseca, _, _ = api
    draft = http.post("/api/policies/drafts", json={"instruction": UNCLEAR}).json()
    assert draft["status"] == "needs_answers" and draft["open_questions"]
    response = http.post(f"/api/policies/drafts/{draft['draft_id']}/submit")
    assert response.status_code == 409 and response.json()["error"]["code"] == "questions_open"
    assert viseca.creates == 0


def test_confirm_stores_the_returned_mandate_as_version_1(api):
    http, viseca, fake, url = api
    draft = ready_draft(http)
    http.post(f"/api/policies/drafts/{draft['draft_id']}/submit")
    mandate = valid(http.post(f"/api/policies/drafts/{draft['draft_id']}/confirm", json={"confirmed": True}).json(),
                    "Mandate")
    assert mandate["mandate_id"].startswith("TM-") and fake.mandates[mandate["mandate_id"]].status == "active"
    assert (mandate["version"], mandate["status"]) == (1, "active")
    assert mandate["hard_rules"] == draft["hard_rules"] and mandate["rules"]

    async def stored():
        conn = await asyncpg.connect(url)
        try:
            return await conn.fetch("select m.status, v.version, v.uncertainty_policy from mandates m "
                                    "join mandate_versions v using (mandate_id) where mandate_id = $1",
                                    mandate["mandate_id"])
        finally:
            await conn.close()
    assert [tuple(r) for r in asyncio.run(stored())] == [("active", 1, "ask")]
    assert valid(http.get(f"/api/mandates/{mandate['mandate_id']}").json(), "Mandate") == mandate
    listing = valid(http.get("/api/mandates").json(), "MandateList")
    assert listing["current_mandate_id"] == mandate["mandate_id"] and listing["mandates"] == [mandate]
    assert http.get("/api/mandates/TM-nope").status_code == 404


def test_confirm_needs_the_customers_explicit_yes(api):
    http, viseca, _, _ = api
    draft = ready_draft(http)
    http.post(f"/api/policies/drafts/{draft['draft_id']}/submit")
    for body in ({}, {"confirmed": False}, {"confirmed": "yes"}, {"confirmed": 1}, {"confirmed": True, "x": 1}):
        response = http.post(f"/api/policies/drafts/{draft['draft_id']}/confirm", json=body)
        assert response.status_code == 422, body
    assert viseca.confirms == 0


def test_confirming_twice_returns_the_same_mandate_and_never_confirms_at_viseca_again(api):
    http, viseca, fake, _ = api
    draft = ready_draft(http)
    http.post(f"/api/policies/drafts/{draft['draft_id']}/submit")
    path = f"/api/policies/drafts/{draft['draft_id']}/confirm"
    first = http.post(path, json={"confirmed": True}).json()
    second = http.post(path, json={"confirmed": True})
    assert second.status_code == 200 and second.json() == first
    assert viseca.confirms == 1 and sum(1 for m in fake.mandates.values() if m.status == "active") == 1


def test_a_double_clicked_confirm_is_idempotent(api):
    http, viseca, fake, _ = api
    draft = ready_draft(http)
    http.post(f"/api/policies/drafts/{draft['draft_id']}/submit")
    path = f"/api/policies/drafts/{draft['draft_id']}/confirm"
    with ThreadPoolExecutor(2) as pool:
        a, b = pool.map(lambda _: http.post(path, json={"confirmed": True}), range(2))
    assert (a.status_code, b.status_code) == (200, 200) and a.json() == b.json()
    assert viseca.confirms == 1 and sum(1 for m in fake.mandates.values() if m.status == "active") == 1


def test_confirming_a_revoked_mandate_fails(api):
    http, viseca, _, url = api
    draft = ready_draft(http)
    http.post(f"/api/policies/drafts/{draft['draft_id']}/submit")
    path = f"/api/policies/drafts/{draft['draft_id']}/confirm"
    mandate = http.post(path, json={"confirmed": True}).json()

    async def revoke():  # LEASH-062 owns the revoke endpoint; the stored status is what confirm must respect
        conn = await asyncpg.connect(url)
        try:
            await conn.execute("update mandates set status = 'revoked' where mandate_id = $1", mandate["mandate_id"])
        finally:
            await conn.close()
    asyncio.run(revoke())
    response = http.post(path, json={"confirmed": True})
    assert response.status_code == 409 and response.json()["error"]["code"] == "mandate_revoked"
    assert viseca.confirms == 1


def test_a_platform_refusal_to_confirm_stores_nothing(api):
    http, viseca, fake, url = api
    draft = ready_draft(http)
    posted = http.post(f"/api/policies/drafts/{draft['draft_id']}/submit").json()
    fake.mandates[posted["platform_draft_id"]].status = "confirmed"  # e.g. confirmed elsewhere already
    response = http.post(f"/api/policies/drafts/{draft['draft_id']}/confirm", json={"confirmed": True})
    assert response.status_code == 409 and response.json()["error"]["code"] == "platform_refused"
    assert valid(http.get("/api/mandates").json(), "MandateList") == {"mandates": [], "current_mandate_id": None}


def test_parallel_submits_create_one_platform_draft(api):
    http, viseca, fake, _ = api
    draft = ready_draft(http)
    with ThreadPoolExecutor(5) as pool:
        bodies = list(pool.map(lambda _: http.post(f"/api/policies/drafts/{draft['draft_id']}/submit").json(),
                               range(5)))
    assert all(b == bodies[0] for b in bodies) and viseca.creates == 1 and len(fake.mandates) == 1


def test_a_failed_local_write_after_viseca_confirmed_is_recovered_on_retry(api):
    http, viseca, fake, url = api
    draft = ready_draft(http)
    http.post(f"/api/policies/drafts/{draft['draft_id']}/submit")

    async def break_local_write(on: bool):
        conn = await asyncpg.connect(url)
        try:
            if on:
                await conn.execute("create function no_mandates() returns trigger language plpgsql as "
                                   "$$ begin raise exception 'disk full'; end $$")
                await conn.execute("create trigger no_mandates before insert on mandates "
                                   "for each row execute function no_mandates()")
            else:
                await conn.execute("drop trigger no_mandates on mandates")
        finally:
            await conn.close()

    asyncio.run(break_local_write(True))
    path = f"/api/policies/drafts/{draft['draft_id']}/confirm"
    first = http.post(path, json={"confirmed": True})
    [active] = [mid for mid, m in fake.mandates.items() if m.status == "active"]  # Viseca did confirm
    assert first.status_code == 500 and first.json()["error"]["code"] == "local_write_failed"
    assert active in first.json()["error"]["message"]
    asyncio.run(break_local_write(False))
    again = http.post(path, json={"confirmed": True})
    assert again.status_code == 200 and again.json()["mandate_id"] == active and viseca.confirms == 1


def test_a_confirm_whose_answer_was_lost_is_reported_not_silently_refused(api):
    http, viseca, fake, _ = api
    draft = ready_draft(http)
    http.post(f"/api/policies/drafts/{draft['draft_id']}/submit")
    real = viseca.confirm_mandate

    async def lost(draft_id):
        await real(draft_id)
        raise httpx.ReadTimeout("no answer")

    viseca.confirm_mandate = lost
    path = f"/api/policies/drafts/{draft['draft_id']}/confirm"
    assert http.post(path, json={"confirmed": True}).status_code == 502
    viseca.confirm_mandate = real
    again = http.post(path, json={"confirmed": True})
    assert again.status_code == 409 and again.json()["error"]["code"] == "confirm_outcome_unknown"
    assert "may already be active" in again.json()["error"]["message"]


def test_a_body_that_is_not_an_object_gets_the_contract_error_shape(api):
    http, _, _, _ = api
    for path in ("/api/policies/drafts", "/api/policies/drafts/LD-x/confirm"):
        response = http.post(path, json=[])
        assert response.status_code == 422
        valid(response.json(), "Error")


def test_many_parallel_confirms_on_many_drafts_never_deadlock(api):
    http, viseca, fake, _ = api
    drafts = [ready_draft(http) for _ in range(4)]
    for d in drafts:
        http.post(f"/api/policies/drafts/{d['draft_id']}/submit")
    paths = [f"/api/policies/drafts/{d['draft_id']}/confirm" for d in drafts for _ in range(3)]
    with ThreadPoolExecutor(12) as pool:
        responses = list(pool.map(lambda p: http.post(p, json={"confirmed": True}), paths))
    assert [r.status_code for r in responses] == [200] * 12
    assert viseca.confirms == 4 and sum(1 for m in fake.mandates.values() if m.status == "active") == 4
    for i in range(4):
        assert len({r.json()["mandate_id"] for r in responses[3 * i:3 * i + 3]}) == 1


def test_a_refused_confirm_is_not_later_reported_as_unknown(api):
    http, viseca, fake, _ = api
    draft = ready_draft(http)
    posted = http.post(f"/api/policies/drafts/{draft['draft_id']}/submit").json()
    fake.mandates[posted["platform_draft_id"]].status = "confirmed"
    path = f"/api/policies/drafts/{draft['draft_id']}/confirm"
    for _ in range(2):
        response = http.post(path, json={"confirmed": True})
        assert response.status_code == 409 and response.json()["error"]["code"] == "platform_refused"


def test_an_unexpected_failure_gets_the_contract_error_shape(test_database_url):
    command.upgrade(alembic(test_database_url), "head")

    class Broken:
        async def create_mandate(self, draft):
            return {"draft_id": "TD-1"}

        async def confirm_mandate(self, draft_id):
            raise KeyError("something nobody expected")

    with TestClient(create_policy_app(test_database_url, Broken(), CATALOGUE), raise_server_exceptions=False) as http:
        draft = ready_draft(http)
        http.post(f"/api/policies/drafts/{draft['draft_id']}/submit")
        response = http.post(f"/api/policies/drafts/{draft['draft_id']}/confirm", json={"confirmed": True})
    assert response.status_code == 500
    valid(response.json(), "Error")


def test_a_viseca_call_slower_than_the_claim_window_is_cut_and_never_answered_twice(api, monkeypatch):
    from leash.adapters.http import policy_api

    monkeypatch.setattr(policy_api, "CONFIRM_WAIT_SECONDS", 1.0)
    http, viseca, fake, _ = api
    draft = ready_draft(http)
    http.post(f"/api/policies/drafts/{draft['draft_id']}/submit")
    real, calls = viseca.confirm_mandate, []

    async def slow(draft_id):
        calls.append(draft_id)
        await asyncio.sleep(1.5)  # longer than the claim window: the call is abandoned, the outcome unknown
        return await real(draft_id)

    viseca.confirm_mandate = slow
    path = f"/api/policies/drafts/{draft['draft_id']}/confirm"
    with ThreadPoolExecutor(2) as pool:
        first, second = pool.map(lambda _: http.post(path, json={"confirmed": True}), range(2))
    codes = sorted([first.status_code, second.status_code])
    assert len(calls) == 1, codes  # the second click waited; it never called Viseca a second time
    assert 502 in codes and all(c in (409, 502) for c in codes), (first.json(), second.json())


GROCERIES = "Buy groceries for CHF 50 or less."


def test_no_platform_draft_while_questions_open(api):
    http, viseca, _, _ = api
    draft = valid(http.post("/api/policies/drafts", json={"instruction": GROCERIES}).json(), "PolicyDraft")
    assert draft["status"] == "needs_answers"
    assert http.post(f"/api/policies/drafts/{draft['draft_id']}/submit").status_code == 409
    assert viseca.creates == 0


def test_answers_are_stored_and_recompile_until_the_draft_can_go_to_viseca(api):
    http, viseca, fake, url = api
    draft = http.post("/api/policies/drafts", json={"instruction": GROCERIES}).json()
    unsure = next(q for q in draft["open_questions"] if "unsure" in q["text"])
    answered = http.post(f"/api/policies/drafts/{draft['draft_id']}/answers",
                         json={"answers": [{"question_id": unsure["question_id"], "answer": "Decline"}]})
    assert answered.status_code == 200, answered.json()
    ready = valid(answered.json(), "PolicyDraft")
    assert ready["status"] == "ready" and ready["uncertainty_policy"] == "decline"
    assert http.get(f"/api/policies/drafts/{draft['draft_id']}").json() == ready  # stored
    posted = valid(http.post(f"/api/policies/drafts/{draft['draft_id']}/submit").json(), "PlatformDraft")
    assert posted["uncertainty_policy"] == "decline" and posted["hard_rules"] == ready["hard_rules"]
    assert fake.mandates[posted["platform_draft_id"]].body["uncertainty_policy"] == "decline"
    # what the customer confirms is exactly what was posted
    assert http.post(f"/api/policies/drafts/{draft['draft_id']}/submit").json() == posted
    later = http.post(f"/api/policies/drafts/{draft['draft_id']}/answers",
                      json={"answers": [{"question_id": unsure["question_id"], "answer": "Ask me"}]})
    assert later.status_code == 409 and later.json()["error"]["code"] == "already_submitted"


def test_bad_answers(api):
    http, _, _, _ = api
    draft = http.post("/api/policies/drafts", json={"instruction": GROCERIES}).json()
    path = f"/api/policies/drafts/{draft['draft_id']}/answers"
    assert http.post("/api/policies/drafts/LD-nope/answers",
                     json={"answers": [{"question_id": "Q", "answer": "x"}]}).status_code == 404
    for body in ({}, {"answers": []}, {"answers": [{"question_id": "Q-nope", "answer": "x"}]},
                 {"answers": [{"question_id": draft["open_questions"][0]["question_id"]}]}, []):
        response = http.post(path, json=body)
        assert response.status_code == 422 and valid(response.json(), "Error"), body
