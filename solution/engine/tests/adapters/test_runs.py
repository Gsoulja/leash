"""Starting a scenario run with the mandate snapshot (LEASH-066): POST/GET /api/runs through the API process,
against a throw-away Postgres and the fake platform. Validated against contracts/policy-api.yaml."""

import asyncio
import json
import logging
from pathlib import Path

import asyncpg
import httpx
import jsonschema
import pytest
import yaml
from fastapi.testclient import TestClient

from fake_api.app import FakeViseca
from leash.adapters.pack.loader import Pack
from leash.adapters.postgres.mandates import StoredMandates
from leash.adapters.postgres.migrate import migrate_and_seed
from leash.adapters.viseca_api.client import VisecaClient
from leash.service import create_api, load_catalogue

ENGINE = Path(__file__).resolve().parents[2]
DATA = ENGINE.parents[1] / "data"
SPEC = yaml.safe_load((ENGINE.parent / "contracts" / "policy-api.yaml").read_text())
CLEAR = "Buy the 27-inch monitor I chose, from a seller I have bought from before, for CHF 400 or less. " \
        "Ask me when uncertain."


def valid(body, name):
    jsonschema.validate(body, {"$ref": f"#/components/schemas/{name}", "components": SPEC["components"]})
    return body


@pytest.fixture
def api(test_database_url):
    migrate_and_seed(test_database_url, DATA)
    fake = FakeViseca(Pack(DATA), api_key="k")
    viseca = VisecaClient("k", "http://fake", transport=httpx.ASGITransport(app=fake.app))
    with TestClient(create_api(test_database_url, viseca, load_catalogue(DATA), background_seconds=30)) as http:
        draft = http.post("/api/policies/drafts", json={"instruction": CLEAR}).json()
        http.post(f"/api/policies/drafts/{draft['draft_id']}/submit")
        mandate = http.post(f"/api/policies/drafts/{draft['draft_id']}/confirm", json={"confirmed": True}).json()
        yield http, fake, viseca, test_database_url, mandate


def fetch(url, sql, *args):
    async def go():
        conn = await asyncpg.connect(url)
        try:
            return [tuple(r) for r in await conn.fetch(sql, *args)]
        finally:
            await conn.close()
    return asyncio.run(go())


def test_scenarios_come_from_the_connected_platform(api):
    http, fake, _, _, _ = api
    response = http.get("/api/scenarios")
    assert response.status_code == 200
    assert response.json()["scenarios"] == fake._scenarios()


def test_run_keeps_starting_version(api):
    http, fake, _, url, mandate = api
    started = http.post("/api/runs", json={"scenario_id": "SCEN0004", "mandate_id": mandate["mandate_id"]})
    assert started.status_code == 201, started.json()
    run = valid(started.json(), "Run")
    assert (run["mandate_id"], run["mandate_version"], run["status"]) == (mandate["mandate_id"], 1, "running")
    assert fetch(url, "select mandate_id, mandate_version, scenario_id from runs where run_id = $1", run["run_id"]) == [
        (mandate["mandate_id"], 1, "SCEN0004")]
    assert run["run_id"] in fake.runs  # started at the platform

    # the mandate is tightened after the start (LEASH-062 will do this through PATCH): the run keeps version 1
    fetch(url, "insert into mandate_versions select mandate_id, 2, hard_rules || '[{\"field\": "
               "\"authorization.billing_amount_chf\", \"operator\": \"<=\", \"value\": 100, \"currency\": \"CHF\", "
               "\"scope\": \"purchase\"}]'::jsonb, uncertainty_policy, compiled, now() from mandate_versions "
               "where mandate_id = $1 and version = 1 returning version", mandate["mandate_id"])
    assert valid(http.get(f"/api/runs/{run['run_id']}").json(), "Run")["mandate_version"] == 1
    mandates = StoredMandates()

    async def load():
        pool = await asyncpg.create_pool(url, min_size=1, max_size=1)
        try:
            await mandates.refresh(pool)
        finally:
            await pool.close()

    asyncio.run(load())
    assert len(mandates.for_run(run["run_id"]).rules) == len(mandate["hard_rules"])  # not the tightened v2


def test_runs_are_listed_newest_first_with_the_one_in_progress(api):
    http, _, _, _, mandate = api
    first = http.post("/api/runs", json={"scenario_id": "SCEN0000", "mandate_id": mandate["mandate_id"]}).json()
    second = http.post("/api/runs", json={"scenario_id": "SCEN0004", "mandate_id": mandate["mandate_id"]}).json()
    listing = valid(http.get("/api/runs").json(), "RunList")
    assert [r["run_id"] for r in listing["runs"]] == [second["run_id"], first["run_id"]]
    assert listing["current_run_id"] == second["run_id"]


def test_a_run_needs_a_known_active_mandate(api):
    http, _, _, url, mandate = api
    unknown = http.post("/api/runs", json={"scenario_id": "SCEN0004", "mandate_id": "TM-nope"})
    assert unknown.status_code == 404 and valid(unknown.json(), "Error")["error"]["code"] == "mandate_not_found"
    fetch(url, "update mandates set status = 'revoked' where mandate_id = $1 returning 1", mandate["mandate_id"])
    revoked = http.post("/api/runs", json={"scenario_id": "SCEN0004", "mandate_id": mandate["mandate_id"]})
    assert revoked.status_code == 409 and revoked.json()["error"]["code"] == "mandate_not_active"
    for body in ({}, {"scenario_id": "SCEN0004"}, {"scenario_id": "SCEN0004", "mandate_id": "x", "y": 1}, []):
        assert http.post("/api/runs", json=body).status_code == 422
    assert http.get("/api/runs/RUN-nope").status_code == 404


def test_the_platforms_snapshot_is_authoritative_and_a_difference_is_flagged(api, caplog):
    http, fake, viseca, url, mandate = api
    # the platform's copy gained a rule our store doesn't have (e.g. tightened elsewhere)
    platform = fake.mandates[mandate["mandate_id"]].body
    platform["hard_rules"] = platform["hard_rules"] + [{"field": "authorization.billing_amount_chf", "operator": "<=",
                                                       "value": 100, "currency": "CHF", "scope": "purchase"}]
    with caplog.at_level(logging.WARNING):
        run = http.post("/api/runs", json={"scenario_id": "SCEN0004", "mandate_id": mandate["mandate_id"]}).json()
    stored = fetch(url, "select v.hard_rules from runs r join mandate_versions v on v.mandate_id = r.mandate_id "
                        "and v.version = r.mandate_version where r.run_id = $1", run["run_id"])
    assert json.loads(stored[0][0]) == platform["hard_rules"] and run["mandate_version"] == 2
    assert any("INTEGRITY" in r.getMessage() and mandate["mandate_id"] in r.getMessage() for r in caplog.records)


def test_an_unreadable_platform_snapshot_never_becomes_the_runs_mandate(api, caplog):
    http, fake, viseca, url, mandate = api
    real = viseca.start_run

    async def partial(scenario_id, mandate_id):
        started = await real(scenario_id, mandate_id)
        started["mandate"] = {"mandate_id": mandate_id}  # no hard_rules, no policy
        return started

    viseca.start_run = partial
    with caplog.at_level(logging.WARNING):
        run = http.post("/api/runs", json={"scenario_id": "SCEN0004", "mandate_id": mandate["mandate_id"]}).json()
    assert run["mandate_version"] == 1  # the version the customer confirmed, not an empty one
    stored = fetch(url, "select v.hard_rules from runs r join mandate_versions v on v.mandate_id = r.mandate_id "
                        "and v.version = r.mandate_version where r.run_id = $1", run["run_id"])
    assert json.loads(stored[0][0]) == mandate["hard_rules"]
    assert any("INTEGRITY" in r.getMessage() for r in caplog.records)


def test_a_later_event_with_a_different_mandate_is_flagged_and_changes_nothing(api, caplog):
    http, _, _, url, mandate = api
    run = http.post("/api/runs", json={"scenario_id": "SCEN0004", "mandate_id": mandate["mandate_id"]}).json()
    from leash.adapters.postgres.repository import PostgresRepository

    async def event_arrives():
        pool = await asyncpg.create_pool(url, min_size=1, max_size=1)
        try:
            other = {"mandate": {"mandate_id": mandate["mandate_id"], "instruction": "x", "uncertainty_policy": "ask",
                                 "hard_rules": mandate["hard_rules"][:1]}}
            await PostgresRepository(pool).ensure_run(run["run_id"], other, "CA0001")
        finally:
            await pool.close()

    with caplog.at_level(logging.WARNING):
        asyncio.run(event_arrives())
    assert valid(http.get(f"/api/runs/{run['run_id']}").json(), "Run")["mandate_version"] == 1
    assert any("INTEGRITY" in r.getMessage() and run["run_id"] in r.getMessage() for r in caplog.records)


def test_live_shaped_run_reports_its_counts(api):
    """LEASH-159: the hosted platform sends unwrapped top-level *_count fields and no `counters` object."""
    http, _, viseca, _, mandate = api
    run = http.post("/api/runs", json={"scenario_id": "SCEN0004", "mandate_id": mandate["mandate_id"]}).json()

    async def live(run_id):
        return {"run_id": run_id, "scenario_id": "SCEN0004", "mandate_id": mandate["mandate_id"], "status": "running",
                "generated_event_count": 10, "delivered_event_count": 3, "finalized_event_count": 2,
                "processed_event_count": 2, "pending_event_count": 1, "queued_event_count": 7,
                "platform_rejected_count": 0}

    viseca.get_run = live
    view = valid(http.get(f"/api/runs/{run['run_id']}").json(), "Run")
    assert view["status"] == "running"
    assert view["counters"] == {"generated_event_count": 10, "delivered_event_count": 3, "finalized_event_count": 2,
                                "processed_event_count": 2, "pending_event_count": 1, "queued_event_count": 7,
                                "platform_rejected_count": 0}


def test_fake_platform_counters_still_reported(api):
    http, _, _, _, mandate = api
    run = http.post("/api/runs", json={"scenario_id": "SCEN0004", "mandate_id": mandate["mandate_id"]})
    assert run.json()["counters"], "the fake platform's nested counters must keep working"
    assert valid(http.get(f"/api/runs/{run.json()['run_id']}").json(), "Run")["counters"]


def test_live_shaped_start_reports_its_counts(api):
    """LEASH-159: POST /api/runs answers from the platform's start response, which is live-shaped too."""
    http, _, viseca, _, mandate = api
    real = viseca.start_run

    async def live(scenario_id, mandate_id):
        started = dict(await real(scenario_id, mandate_id))  # the fake answers unwrapped here, like the live API
        started.pop("counters", None)
        return {**started, "generated_event_count": 10, "queued_event_count": 10, "delivered_event_count": 0}

    viseca.start_run = live
    started = valid(http.post("/api/runs", json={"scenario_id": "SCEN0004",
                                                 "mandate_id": mandate["mandate_id"]}).json(), "Run")
    assert started["counters"] == {"generated_event_count": 10, "queued_event_count": 10, "delivered_event_count": 0}


def test_unusable_platform_counts_are_dropped_not_served(api):
    """The platform is untrusted input: a junk `counters` must not 500, and a bool is not a count."""
    http, _, viseca, _, mandate = api
    run = http.post("/api/runs", json={"scenario_id": "SCEN0004", "mandate_id": mandate["mandate_id"]}).json()

    async def junk(run_id):
        return {"run_id": run_id, "status": "running", "counters": "not a mapping",
                "queued_event_count": True, "delivered_event_count": 4}

    viseca.get_run = junk
    view = valid(http.get(f"/api/runs/{run['run_id']}").json(), "Run")
    assert view["counters"] == {"delivered_event_count": 4}


def test_a_repeated_start_returns_the_same_run_and_never_a_second_one(api):
    """LEASH-102: a retried handoff is the same handoff, not a second one.

    The customer presses once. A dropped response, a refreshed tab or a retrying client must not
    hand the agent two runs against one confirmed permission — two runs mean two sets of counters,
    and a spending limit enforced twice over is a limit enforced once.
    """
    http, _, _, url, mandate = api
    body = {"scenario_id": "SCEN0004", "mandate_id": mandate["mandate_id"]}
    first = http.post("/api/runs", json=body)
    assert first.status_code == 201, first.text
    again = http.post("/api/runs", json=body)
    assert again.status_code in (200, 201), again.text
    assert again.json()["run_id"] == first.json()["run_id"]
    assert again.json()["mandate_version"] == first.json()["mandate_version"]
    rows = fetch(url, "select run_id from runs where mandate_id = $1", mandate["mandate_id"])
    assert len(rows) == 1, f"one retried start, one run: {rows}"

    # But tightening is a new permission to run under, not a retry. LEASH-133's journey starts a
    # second run on this same scenario after lowering the limit and requires the new version; keying
    # idempotency on (mandate, scenario) alone silently handed back the old, looser run instead.
    tightened = http.post(f"/api/mandates/{mandate['mandate_id']}/tighten",
                          json={"add_hard_rules": [{"field": "authorization.billing_amount_chf", "operator": "<=",
                                                    "value": "300", "currency": "CHF", "scope": "purchase"}]})
    assert tightened.status_code == 200, tightened.text
    later = http.post("/api/runs", json=body)
    assert later.status_code == 201, later.text
    assert later.json()["run_id"] != first.json()["run_id"]
    assert later.json()["mandate_version"] > first.json()["mandate_version"]
    assert len(fetch(url, "select run_id from runs where mandate_id = $1", mandate["mandate_id"])) == 2
