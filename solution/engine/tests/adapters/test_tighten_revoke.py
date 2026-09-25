"""Tighten and revoke (LEASH-062): POST /api/mandates/{id}/tighten and DELETE /api/mandates/{id} through the API
process, against a throw-away Postgres and the fake platform. Validated against contracts/policy-api.yaml."""

import asyncio
from pathlib import Path

import asyncpg
import httpx
import jsonschema
import pytest
import yaml
from fastapi.testclient import TestClient

from fake_api.app import FakeViseca
from leash.adapters.pack.loader import Pack
from leash.adapters.postgres.migrate import migrate_and_seed
from leash.adapters.viseca_api.client import VisecaClient
from leash.service import create_api, load_catalogue

ENGINE = Path(__file__).resolve().parents[2]
DATA = ENGINE.parents[1] / "data"
SPEC = yaml.safe_load((ENGINE.parent / "contracts" / "policy-api.yaml").read_text())
CLEAR = "Buy the 27-inch monitor I chose, from a seller I have bought from before, for CHF 400 or less. " \
        "Ask me when uncertain."


def per_order(chf):
    return {"field": "authorization.billing_amount_chf", "operator": "<=", "value": chf, "currency": "CHF",
            "scope": "purchase"}


def valid(body, name):
    jsonschema.validate(body, {"$ref": f"#/components/schemas/{name}", "components": SPEC["components"]})
    return body


class Counting:
    def __init__(self, client):
        self.client, self.patches, self.revokes = client, 0, 0

    def __getattr__(self, name):
        return getattr(self.client, name)

    async def patch_mandate(self, mandate_id, changes):
        self.patches += 1
        return await self.client.patch_mandate(mandate_id, changes)

    async def revoke_mandate(self, mandate_id):
        self.revokes += 1
        return await self.client.revoke_mandate(mandate_id)


@pytest.fixture
def api(test_database_url):
    migrate_and_seed(test_database_url, DATA)
    fake = FakeViseca(Pack(DATA), api_key="k")
    viseca = Counting(VisecaClient("k", "http://fake", transport=httpx.ASGITransport(app=fake.app)))
    with TestClient(create_api(test_database_url, viseca, load_catalogue(DATA), background_seconds=30)) as http:
        draft = http.post("/api/policies/drafts", json={"instruction": CLEAR}).json()
        http.post(f"/api/policies/drafts/{draft['draft_id']}/submit", json={"revision": draft["revision"]})
        mandate = http.post(f"/api/policies/drafts/{draft['draft_id']}/confirm", json={"confirmed": True, "revision": draft["revision"]}).json()
        yield http, fake, viseca, test_database_url, mandate


def versions(url, mandate_id):
    async def go():
        conn = await asyncpg.connect(url)
        try:
            return [r["version"] for r in await conn.fetch(
                "select version from mandate_versions where mandate_id = $1 order by version", mandate_id)]
        finally:
            await conn.close()
    return asyncio.run(go())


def test_raising_limit_is_refused(api):
    http, fake, viseca, url, mandate = api
    response = http.post(f"/api/mandates/{mandate['mandate_id']}/tighten", json={"add_hard_rules": [per_order(500)]})
    assert response.status_code == 422 and valid(response.json(), "Error")["error"]["code"] == "would_loosen"
    assert "new permission" in response.json()["error"]["message"]
    assert viseca.patches == 0 and versions(url, mandate["mandate_id"]) == [1]
    assert fake.mandates[mandate["mandate_id"]].body["hard_rules"] == mandate["hard_rules"]


def test_a_lower_limit_is_a_new_version_and_patches_every_rule_unchanged_plus_the_new_one(api):
    http, fake, viseca, url, mandate = api
    response = http.post(f"/api/mandates/{mandate['mandate_id']}/tighten", json={"add_hard_rules": [per_order(350)]})
    assert response.status_code == 200, response.json()
    tightened = valid(response.json(), "Mandate")
    assert tightened["version"] == 2 and tightened["hard_rules"] == mandate["hard_rules"] + [per_order(350)]
    assert tightened["rules"][:len(mandate["rules"])] == mandate["rules"]
    assert tightened["rules"][-1]["tightened"] is True and "350" in tightened["rules"][-1]["text"]
    assert fake.mandates[mandate["mandate_id"]].body["hard_rules"] == mandate["hard_rules"] + [per_order(350)]
    assert viseca.patches == 1 and versions(url, mandate["mandate_id"]) == [1, 2]
    assert http.get(f"/api/mandates/{mandate['mandate_id']}").json()["version"] == 2


def test_uncertainty_can_only_move_to_decline(api):
    http, fake, viseca, _, mandate = api
    path = f"/api/mandates/{mandate['mandate_id']}/tighten"
    assert http.post(path, json={"uncertainty_policy": "approve"}).status_code == 422
    moved = http.post(path, json={"uncertainty_policy": "decline"})
    assert moved.status_code == 200 and moved.json()["uncertainty_policy"] == "decline"
    assert fake.mandates[mandate["mandate_id"]].body["uncertainty_policy"] == "decline"
    again = http.post(path, json={"uncertainty_policy": "decline"})
    assert again.status_code == 422 and again.json()["error"]["code"] == "would_loosen"


def test_a_looser_rule_hidden_next_to_a_stricter_one_is_refused(api):
    http, _, viseca, url, mandate = api
    response = http.post(f"/api/mandates/{mandate['mandate_id']}/tighten",
                         json={"add_hard_rules": [per_order(350), per_order(900)]})
    assert response.status_code == 422 and response.json()["error"]["code"] == "would_loosen"
    assert viseca.patches == 0 and versions(url, mandate["mandate_id"]) == [1]


def test_bad_tighten_requests(api):
    http, _, viseca, _, mandate = api
    path = f"/api/mandates/{mandate['mandate_id']}/tighten"
    for body in ({}, {"add_hard_rules": []}, {"add_hard_rules": [{"field": "x"}]}, {"remove": 1}, []):
        response = http.post(path, json=body)
        assert response.status_code == 422 and valid(response.json(), "Error"), body
    duplicate = http.post(path, json={"add_hard_rules": [mandate["hard_rules"][0]]})
    assert duplicate.status_code == 422 and duplicate.json()["error"]["code"] == "would_loosen"
    assert http.post("/api/mandates/TM-nope/tighten", json={"add_hard_rules": [per_order(1)]}).status_code == 404
    assert viseca.patches == 0


def test_a_platform_refusal_stores_nothing(api):
    http, fake, viseca, url, mandate = api
    fake.mandates[mandate["mandate_id"]].status = "revoked"  # e.g. revoked at the platform already
    response = http.post(f"/api/mandates/{mandate['mandate_id']}/tighten", json={"add_hard_rules": [per_order(300)]})
    assert response.status_code == 409 and response.json()["error"]["code"] == "platform_refused"
    assert versions(url, mandate["mandate_id"]) == [1]


def test_revoke_calls_delete_and_marks_the_mandate_revoked(api):
    http, fake, viseca, _, mandate = api
    revoked = http.delete(f"/api/mandates/{mandate['mandate_id']}")
    assert revoked.status_code == 200
    body = valid(revoked.json(), "Mandate")
    assert body["status"] == "revoked" and body["revocation"] == {"platform_confirmed": True, "note": None}
    assert fake.mandates[mandate["mandate_id"]].status == "revoked" and viseca.revokes == 1
    again = http.delete(f"/api/mandates/{mandate['mandate_id']}")
    assert again.status_code == 200 and again.json()["status"] == "revoked" and viseca.revokes == 1
    tighten = http.post(f"/api/mandates/{mandate['mandate_id']}/tighten", json={"add_hard_rules": [per_order(100)]})
    assert tighten.status_code == 409 and tighten.json()["error"]["code"] == "mandate_not_active"
    listing = http.get("/api/mandates").json()
    assert listing["current_mandate_id"] is None
    assert http.delete("/api/mandates/TM-nope").status_code == 404


def test_an_empty_change_is_refused(api):
    http, _, viseca, url, mandate = api
    path = f"/api/mandates/{mandate['mandate_id']}/tighten"
    for body in ({"uncertainty_policy": None}, {"add_hard_rules": None},
                 {"add_hard_rules": None, "uncertainty_policy": None}):
        assert http.post(path, json=body).status_code == 422, body
    assert viseca.patches == 0 and versions(url, mandate["mandate_id"]) == [1]


def test_a_lost_patch_reply_is_checked_at_viseca_and_stored_when_it_applied(api):
    http, fake, viseca, url, mandate = api
    real = viseca.client.patch_mandate

    async def lost(mandate_id, changes):
        await real(mandate_id, changes)
        raise httpx.ReadTimeout("no answer")

    viseca.client.patch_mandate = lost
    response = http.post(f"/api/mandates/{mandate['mandate_id']}/tighten", json={"add_hard_rules": [per_order(350)]})
    assert response.status_code == 200, response.json()
    assert response.json()["hard_rules"] == fake.mandates[mandate["mandate_id"]].body["hard_rules"]
    assert versions(url, mandate["mandate_id"]) == [1, 2]
    viseca.client.patch_mandate = real
    later = http.post(f"/api/mandates/{mandate['mandate_id']}/tighten", json={"add_hard_rules": [per_order(300)]})
    assert later.status_code == 200 and later.json()["version"] == 3  # still in step with Viseca


def test_a_lost_patch_that_did_not_apply_stores_nothing(api):
    http, fake, viseca, url, mandate = api

    async def lost(mandate_id, changes):
        raise httpx.ConnectError("down")

    viseca.client.patch_mandate = lost
    response = http.post(f"/api/mandates/{mandate['mandate_id']}/tighten", json={"add_hard_rules": [per_order(350)]})
    assert response.status_code == 502 and versions(url, mandate["mandate_id"]) == [1]


@pytest.mark.parametrize("held", [
    {"data": {"status": "revoked", "hard_rules": None, "uncertainty_policy": "ask"}},
    {"data": {"status": "active", "hard_rules": ["a", "b", "c", "d", "e", "f", "g"], "uncertainty_policy": "ask"}},
])
def test_a_lost_reply_is_stored_only_when_viseca_holds_exactly_the_change_on_an_active_mandate(api, held):
    http, fake, viseca, url, mandate = api

    async def lost(mandate_id, changes):
        raise httpx.ReadTimeout("no answer")

    async def read_back(mandate_id):
        body = dict(held)
        if body["data"]["hard_rules"] is None:
            body = {"data": {**held["data"], "hard_rules": mandate["hard_rules"] + [per_order(350)]}}
        return body

    viseca.client.patch_mandate, viseca.client.get_mandate = lost, read_back
    response = http.post(f"/api/mandates/{mandate['mandate_id']}/tighten", json={"add_hard_rules": [per_order(350)]})
    assert response.status_code == 502 and versions(url, mandate["mandate_id"]) == [1]


def test_review_is_read_only_and_confirmation_rejects_a_stale_version(api):
    http, fake, viseca, url, mandate = api
    path = f"/api/mandates/{mandate['mandate_id']}/tighten"
    change = {"add_hard_rules": [per_order(350)], "expected_version": 1}
    reviewed = http.post(path + "?preview=true", json=change)
    assert reviewed.status_code == 200
    proposal = valid(reviewed.json(), "Mandate")
    assert proposal["version"] == 2
    assert any("350.00" in rule["text"] for rule in proposal["review"]["must_follow"])
    assert viseca.patches == 0 and versions(url, mandate["mandate_id"]) == [1]
    assert fake.mandates[mandate["mandate_id"]].body["hard_rules"] == mandate["hard_rules"]
    applied = http.post(path, json=change)
    assert applied.status_code == 200 and applied.json()["review"] == proposal["review"]
    assert viseca.patches == 1
    stale = http.post(path, json={"uncertainty_policy": "decline", "expected_version": 1})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "stale_version"
    assert viseca.patches == 1 and versions(url, mandate["mandate_id"]) == [1, 2]
    for invalid in (None, True, 0, "2"):
        assert http.post(path, json={"uncertainty_policy": "decline", "expected_version": invalid}).status_code == 422
    snapshot = http.get(f"/api/mandates/{mandate['mandate_id']}/versions").json()["versions"][0]
    assert snapshot["review"] == mandate["review"]
