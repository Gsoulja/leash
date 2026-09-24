"""LEASH-056: a full SCEN0001 run against the fake platform and a throw-away Postgres.

Mandate created and confirmed at the platform → run started → the worker decides every purchase through
Postgres → one decision's first POST is lost after its commit (a crash between commit and POST) and the
platform delivers that purchase again → the repeat path answers it from the saved verdict, counted once →
the customer rejects one ask (the /resolve reaches the platform) and tries to approve another after later
approvals used up the 7-day limit (refused, DEC-012, nothing sent).
"""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
import httpx
from alembic import command

from adapters.test_schema import alembic
from fake_api.app import FakeViseca
from fixtures.mandates import MANDATES
from leash.adapters.pack.loader import Pack
from leash.adapters.pack.seed import seed
from leash.adapters.postgres.unit_of_work import PostgresDecisionStore, ResolutionTransaction
from leash.adapters.regex_reader import RegexReader
from leash.adapters.viseca_api.client import VisecaClient
from leash.adapters.viseca_api.event_schema import load_event_validator
from leash.adapters.viseca_api.outbox_sender import OutboxSender
from leash.adapters.viseca_api.worker import ApiSender, Worker
from leash.application.decide_purchase import DeadlinePlan, DecidePurchase
from leash.application.resolve import ResolveAsk
from leash.policy.hard_rules import mandate_from_api, mandate_to_api

DATA = Path(__file__).resolve().parents[4] / "data"
VALIDATE = load_event_validator(DATA / "schemas" / "authorization_event.schema.json")
PLAN = DeadlinePlan(send_seconds=0.5, lock_seconds=0.5, decide_seconds=0.5, fallback_seconds=0.5)
LOST = "AU0005"  # its first POST is lost after the commit


class LosesFirstPost(ApiSender):
    def __init__(self, api, fake, source_id):
        super().__init__(api)
        self.fake, self.source_id, self.lost = fake, source_id, []

    async def send(self, authorization_id, body):
        _, live = self.fake.live[authorization_id]
        if live.attempt.purchase.authorization_id == self.source_id and not self.lost:
            self.lost.append(authorization_id)
            raise ConnectionResetError("the process died between commit and POST")
        await super().send(authorization_id, body)


class RunMandates:
    """The run's mandate snapshot as stored, compiled from its hard_rules (DEC-003)."""

    def __init__(self):
        self.by_run = {}

    async def load(self, pool, run_id):
        row = await pool.fetchrow("select m.instruction, v.hard_rules, v.uncertainty_policy from runs r "
                                  "join mandate_versions v using (mandate_id) join mandates m using (mandate_id) "
                                  "where r.run_id = $1 and v.version = r.mandate_version", run_id)
        self.by_run[run_id], _ = mandate_from_api({"instruction": row["instruction"] or "x",
                                                   "hard_rules": json.loads(row["hard_rules"]),
                                                   "uncertainty_policy": row["uncertainty_policy"]})

    def for_run(self, run_id):
        return self.by_run[run_id]


def full_run(url):
    command.upgrade(alembic(url), "head")
    pack = Pack(DATA)
    fake = FakeViseca(pack, api_key="k", human_window_seconds=90, repeat=[LOST])
    client = VisecaClient("k", "http://fake", transport=httpx.ASGITransport(app=fake.app))
    sender = LosesFirstPost(client, fake, LOST)
    total = len(pack.attempts("SCEN0001"))

    async def go():
        conn = await asyncpg.connect(url)
        try:
            await seed(conn, pack)
        finally:
            await conn.close()
        pool = await asyncpg.create_pool(url, min_size=2, max_size=6)
        try:
            body = {**mandate_to_api(MANDATES["SCEN0001"]), "guidance": [], "open_questions": []}
            draft = await client.create_mandate(body)
            mandate_id = (await client.confirm_mandate(draft["draft_id"]))["mandate_id"]
            run_id = (await client.start_run("SCEN0001", mandate_id))["run_id"]

            use_case = DecidePurchase(store=PostgresDecisionStore(pool, engine_version="e2e"), reader=RegexReader(),
                                      sender=sender, plan=PLAN, engine_version="e2e", human_window_seconds=90)
            worker = Worker(client, use_case, validate=VALIDATE, poll_wait=1)
            outbox = OutboxSender(pool, client, grace_seconds=0.5, base_backoff_seconds=0.2)

            async def recovery():  # what the restarted process runs: resend what was committed but not sent
                while True:
                    await outbox.send_pending()
                    await asyncio.sleep(0.3)

            polling = asyncio.ensure_future(worker.run())
            recovering = asyncio.ensure_future(recovery())
            try:
                for _ in range(600):
                    if len({r["authorization_id"] for r in fake.received}) == total:
                        break
                    await asyncio.sleep(0.1)
                states = {r["source_authorization_id"]: (r["authorization_id"], r["state"]) for r in await pool.fetch(
                    "select authorization_id, source_authorization_id, state from authorizations where run_id = $1",
                    run_id)}
                mandates = RunMandates()
                await mandates.load(pool, run_id)
                resolve = ResolveAsk(ResolutionTransaction(pool), mandates, engine_version="e2e")
                now = datetime.now(timezone.utc)
                late = await resolve.answer(states["AU0006"][0], "approve", now=now)
                rejected = await resolve.answer(states["AU0007"][0], "decline", now=now)
                await asyncio.sleep(0.6)  # past the outbox grace; the resolve endpoint itself is LEASH-063
                await outbox.send_pending()
            finally:
                worker.stop()
                await asyncio.wait_for(polling, 5)
                recovering.cancel()
            decided = await pool.fetch("select authorization_id, count(*) n from decision_events "
                                       "where kind = 'decided' group by authorization_id")
            spend = await pool.fetchval("select coalesce(sum(billing_chf), 0) from authorizations "
                                        "where run_id = $1 and state = 'approved'", run_id)
            return run_id, states, late, rejected, decided, spend
        finally:
            await pool.close()

    return fake, sender, total, asyncio.run(go())


def test_full_run(test_database_url):
    fake, sender, total, (run_id, states, late, rejected, decided, spend) = full_run(test_database_url)
    run = fake.runs[run_id]

    # every purchase got a decision before its deadline
    assert len(run.queued) == total and all(q.decision is not None for q in run.queued)
    assert all(q.decided_at < q.deadline_at for q in run.queued)
    assert not [r for r in fake.rejected if r["error"] == "deadline_passed"], fake.rejected

    # the lost POST: committed, delivered again, answered from the saved verdict, counted once
    [lost_live] = sender.lost
    lost = next(q for q in run.queued if q.live_id == lost_live)
    assert lost.deliveries == 2 and states[LOST] == (lost_live, "approved")
    assert all(row["n"] == 1 for row in decided) and len(decided) == total
    assert str(spend) == "300.00"  # the 7-day total the agreed replay reaches, not a cent counted twice

    # the customer's rejection reaches the platform through /resolve
    assert rejected.state == "declined"
    assert fake.resolutions == [{"authorization_id": states["AU0007"][0], "decision": "decline",
                                 "customer_message": "The customer rejected this purchase.", "evidence": []}]

    # a late approval after later approvals used up the limit is refused and nothing is sent (DEC-012)
    assert late.state == "waiting" and "over_period_limit" in late.blocked
    assert all(r["authorization_id"] != states["AU0006"][0] for r in fake.resolutions)


def test_a_restart_between_commit_and_post_is_recovered_by_the_outbox(test_database_url):
    """No repeat delivery here: the first worker commits AU0005's decision, its POST is lost, and the process
    stops. A new process (new pool, new worker, the recovery outbox) must deliver that committed verdict
    before its deadline, and the run carries on. Only the outbox can answer it (DEC-007)."""
    url = test_database_url
    command.upgrade(alembic(url), "head")
    pack = Pack(DATA)
    fake = FakeViseca(pack, api_key="k", human_window_seconds=90)
    client = VisecaClient("k", "http://fake", transport=httpx.ASGITransport(app=fake.app))
    total = len(pack.attempts("SCEN0001"))

    def process(pool, sender):
        use_case = DecidePurchase(store=PostgresDecisionStore(pool, engine_version="e2e"), reader=RegexReader(),
                                  sender=sender, plan=PLAN, engine_version="e2e", human_window_seconds=90)
        return Worker(client, use_case, validate=VALIDATE, poll_wait=1)

    async def go():
        conn = await asyncpg.connect(url)
        try:
            await seed(conn, pack)
        finally:
            await conn.close()
        body = {**mandate_to_api(MANDATES["SCEN0001"]), "guidance": [], "open_questions": []}
        draft = await client.create_mandate(body)
        run_id = (await client.start_run("SCEN0001", (await client.confirm_mandate(draft["draft_id"]))["mandate_id"]))[
            "run_id"]

        first_pool = await asyncpg.create_pool(url, min_size=1, max_size=4)
        crashing = LosesFirstPost(client, fake, LOST)
        first = process(first_pool, crashing)
        polling = asyncio.ensure_future(first.run())
        for _ in range(200):
            if crashing.lost:
                break
            await asyncio.sleep(0.05)
        first.stop()  # the process goes down right after the lost POST
        await asyncio.wait_for(polling, 5)
        await first_pool.close()
        [lost_live] = crashing.lost
        assert fake.live[lost_live][1].decision is None  # committed here, unknown to the platform

        pool = await asyncpg.create_pool(url, min_size=1, max_size=4)  # the restarted process
        try:
            outbox = OutboxSender(pool, client, grace_seconds=0.5, base_backoff_seconds=0.2)
            second = process(pool, ApiSender(client))

            async def recovery():
                while True:
                    await outbox.send_pending()
                    await asyncio.sleep(0.3)

            recovering = asyncio.ensure_future(recovery())
            polling = asyncio.ensure_future(second.run())
            try:
                for _ in range(600):
                    if len({r["authorization_id"] for r in fake.received}) == total:
                        break
                    await asyncio.sleep(0.1)
            finally:
                second.stop()
                await asyncio.wait_for(polling, 5)
                recovering.cancel()
            row = await pool.fetchrow("select state, (select attempts from outbox o where o.authorization_id = a.authorization_id"
                                      " and o.endpoint = 'decision') attempts from authorizations a "
                                      "where a.authorization_id = $1", lost_live)
            decided = await pool.fetch("select authorization_id, count(*) n from decision_events "
                                       "where kind = 'decided' group by authorization_id")
            return run_id, lost_live, row, decided
        finally:
            await pool.close()

    run_id, lost_live, row, decided = asyncio.run(go())
    run = fake.runs[run_id]
    lost = next(q for q in run.queued if q.live_id == lost_live)
    assert lost.deliveries == 1  # never delivered again: only the outbox could answer it
    assert lost.decision == "approve" and lost.decided_at < lost.deadline_at
    assert row["state"] == "approved" and row["attempts"] == 1  # sent once, by the recovery outbox
    assert len(run.queued) == total and all(q.decision is not None for q in run.queued)
    assert not [r for r in fake.rejected if r["error"] == "deadline_passed"], fake.rejected
    assert all(r["n"] == 1 for r in decided) and len(decided) == total


def test_a_run_started_through_the_policy_api_is_decided_with_its_stored_snapshot(test_database_url):
    """LEASH-066: draft → submit → confirm → POST /api/runs through the API process, then the worker decides
    every purchase of that run against the same database; the run keeps mandate version 1."""
    from fastapi.testclient import TestClient

    from leash.adapters.postgres.migrate import migrate_and_seed
    from leash.service import create_api, load_catalogue

    url = test_database_url
    migrate_and_seed(url, DATA)
    pack = Pack(DATA)
    fake = FakeViseca(pack, api_key="k", human_window_seconds=90)
    client = VisecaClient("k", "http://fake", transport=httpx.ASGITransport(app=fake.app))
    instruction = ("Buy the 27-inch monitor I chose, from a seller I have bought from before, for CHF 400 or less. "
                   "Ask me when uncertain.")
    with TestClient(create_api(url, client, load_catalogue(DATA), background_seconds=30)) as http:
        draft = http.post("/api/policies/drafts", json={"instruction": instruction}).json()
        assert http.post(f"/api/policies/drafts/{draft['draft_id']}/submit").status_code == 200
        mandate = http.post(f"/api/policies/drafts/{draft['draft_id']}/confirm", json={"confirmed": True}).json()
        run = http.post("/api/runs", json={"scenario_id": "SCEN0004", "mandate_id": mandate["mandate_id"]}).json()
    total = len(pack.attempts("SCEN0004"))

    async def go():
        pool = await asyncpg.create_pool(url, min_size=1, max_size=4)
        try:
            use_case = DecidePurchase(store=PostgresDecisionStore(pool, engine_version="e2e"), reader=RegexReader(),
                                      sender=ApiSender(client), plan=PLAN, engine_version="e2e", human_window_seconds=90)
            worker = Worker(client, use_case, validate=VALIDATE, poll_wait=1)
            polling = asyncio.ensure_future(worker.run())
            try:
                for _ in range(600):
                    if len({r["authorization_id"] for r in fake.received}) == total:
                        break
                    await asyncio.sleep(0.1)
            finally:
                worker.stop()
                await asyncio.wait_for(polling, 5)
            return await pool.fetch("select a.run_id, r.mandate_version from authorizations a join runs r using (run_id)")
        finally:
            await pool.close()

    rows = asyncio.run(go())
    assert run["mandate_version"] == 1 and len(rows) == total
    assert {(r["run_id"], r["mandate_version"]) for r in rows} == {(run["run_id"], 1)}
    assert all(q.decision is not None and q.decided_at < q.deadline_at for q in fake.runs[run["run_id"]].queued)
