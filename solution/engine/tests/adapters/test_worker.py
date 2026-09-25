"""The long-poll worker (LEASH-053): against the fake platform for the full loop, and against small stubs for
204 handling, backoff and shutdown."""

import asyncio
import copy
import json
import logging
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from fake_api.app import FakeViseca
from fixtures.mandates import MANDATES
from leash.adapters.pack.loader import Pack
from leash.adapters.regex_reader import RegexReader
from leash.adapters.viseca_api.client import VisecaApiError, VisecaClient
from leash.adapters.viseca_api.event_schema import load_event_validator
from leash.adapters.viseca_api.worker import ApiSender, Worker
from leash.application.decide_purchase import DeadlinePlan, DecidePurchase
from leash.application.replay import InMemoryDecisionStore
from leash.policy.hard_rules import mandate_to_api

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "data"
VALIDATE = load_event_validator(DATA / "schemas" / "authorization_event.schema.json")
EXAMPLE = json.loads((DATA / "scenario_fixtures" / "example_authorization_request.json").read_text())
PLAN = DeadlinePlan(send_seconds=0.5, lock_seconds=0.5, decide_seconds=0.5, fallback_seconds=0.5)


def worker_for(api, pack, **kw):
    use_case = DecidePurchase(store=InMemoryDecisionStore(pack), reader=RegexReader(), sender=ApiSender(api),
                              plan=PLAN, engine_version="worker-test", human_window_seconds=120)
    return Worker(api, use_case, validate=VALIDATE, engine_version="worker-test", poll_wait=1, **kw)


async def start(client, scenario):
    body = {**mandate_to_api(MANDATES[scenario]), "guidance": [], "open_questions": []}
    draft = await client.create_mandate(body)
    mandate_id = (await client.confirm_mandate(draft["draft_id"]))["mandate_id"]
    return (await client.start_run(scenario, mandate_id))["run_id"]


def test_worker_keeps_polling_while_ask_open():
    pack = Pack(DATA)
    fake = FakeViseca(pack, api_key="k", human_window_seconds=2)
    client = VisecaClient("k", "http://fake", transport=httpx.ASGITransport(app=fake.app))
    worker = worker_for(client, pack)

    async def go():
        run_id = await start(client, "SCEN0001")
        await asyncio.wait_for(worker.run(run_id=run_id), timeout=60)
        return run_id

    run_id = asyncio.run(go())
    total = len(pack.attempts("SCEN0001"))
    decisions = [r["decision"] for r in fake.received]
    assert len(decisions) == total and not fake.rejected, fake.rejected
    first_ask = decisions.index("step_up")
    assert first_ask < total - 1  # later purchases were decided while that ask was still open
    assert not fake.resolutions  # nobody answered: the loop never waited for the customer
    assert fake.runs[run_id].queued[-1].decision is not None


def test_a_redelivered_cart_that_changed_is_answered_as_a_new_attempt(caplog):
    """LEASH-102: the platform re-delivers one live authorization with a warranty added to the basket.

    The first delivery was approved. The second is not a retry — it is different terms under the same
    live ID — so the approval must not be posted again. What the platform already recorded stands; our
    answer to this delivery is the safe one, and the mismatch is logged.
    """
    caplog.set_level(logging.WARNING, logger="leash.decide")
    pack = Pack(DATA)
    first = pack.attempts("SCEN0000")[0].purchase

    def add_a_warranty(purchase):
        warranty = replace(purchase.items[0], line_no=len(purchase.items) + 1, item_id="IT9999",
                           name="Extended warranty", unit_price=Decimal("79.00"), quantity=1)
        return replace(purchase, items=(*purchase.items, warranty),
                       amount=purchase.amount + Decimal("79.00"),
                       billing_amount_chf=purchase.billing_amount_chf + Decimal("79.00"),
                       items_subtotal=purchase.items_subtotal + Decimal("79.00"))

    fake = FakeViseca(pack, api_key="k", amend={first.authorization_id: add_a_warranty})
    client = VisecaClient("k", "http://fake", transport=httpx.ASGITransport(app=fake.app))
    worker = worker_for(client, pack)

    async def go():
        run_id = await start(client, "SCEN0000")
        await asyncio.wait_for(worker.run(run_id=run_id), timeout=60)
        return run_id

    run_id = asyncio.run(go())
    live = fake.runs[run_id].queued[0]
    assert live.deliveries == 2, "the amended cart has to arrive as its own delivery"
    assert live.decision == "approve"  # what the platform recorded on the terms it asked about stands
    posted = [r for r in fake.received if r["authorization_id"] == live.live_id]
    assert [r["decision"] for r in posted] == ["approve"], posted
    [refused] = [r for r in fake.rejected if r["authorization_id"] == live.live_id]
    assert refused["error"] == "already_decided" and refused["body"]["decision"] == "step_up", refused
    assert any("redelivered with different terms" in r.getMessage() for r in caplog.records)


class Stub:
    """A scripted platform: each poll takes the next item (an envelope, None for 204, or an exception)."""

    def __init__(self, polls, statuses=("running",)):
        self.polls, self.statuses = list(polls), list(statuses)
        self.poll_calls = self.run_calls = 0
        self.posted: list[tuple[str, dict]] = []

    async def next_decision_request(self, wait=25):
        self.poll_calls += 1
        if not self.polls:
            await asyncio.sleep(wait)
            return None
        item = self.polls.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def get_run(self, run_id):
        self.run_calls += 1
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        return {"data": {"run_id": run_id, "status": status}}

    async def post_decision(self, authorization_id, decision):
        self.posted.append((authorization_id, dict(decision)))
        return {"data": {}}


class Recorder:
    def __init__(self, delay=0.0):
        self.delay, self.handled, self.finished = delay, [], []

    async def handle(self, request):
        self.handled.append(request.purchase.authorization_id)
        await asyncio.sleep(self.delay)
        self.finished.append(request.purchase.authorization_id)


def envelope(live_id="AZ-1", **changes):
    data = copy.deepcopy(EXAMPLE)
    data["authorization"]["authorization_id"] = live_id
    data["deadline_at"] = "2999-01-01T00:00:08Z"
    for key, value in changes.items():
        data[key] = value
    return {"run_id": "RUN1", "event_id": "EV1", "type": "authorization.request", "data": data}


def test_204_checks_run_progress_and_polls_again():
    api = Stub([None, None, envelope(), None], statuses=("running", "running", "completed"))
    handler = Recorder()
    asyncio.run(asyncio.wait_for(Worker(api, handler, validate=VALIDATE, poll_wait=0).run(run_id="RUN1"), 5))
    assert api.run_calls == 3 and api.poll_calls == 4 and handler.handled == ["AZ-1"]


def test_without_a_run_id_the_worker_keeps_polling_after_204():
    api = Stub([None, None, None, envelope()])
    handler = Recorder()
    worker = Worker(api, handler, validate=VALIDATE, poll_wait=0)

    async def go():
        task = asyncio.ensure_future(worker.run())
        while not handler.finished:
            await asyncio.sleep(0.01)
        worker.stop()
        await asyncio.wait_for(task, 2)

    asyncio.run(go())
    assert api.poll_calls >= 4 and api.run_calls == 0


def test_errors_are_logged_and_retried_with_backoff(caplog):
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)

    api = Stub([VisecaApiError(503, "GET", "/v1/decision-requests/next", {"code": "busy"}),
                httpx.ConnectError("down"), VisecaApiError(500, "GET", "/v1/x", None), envelope(), None,
                httpx.ConnectError("down again"), None], statuses=("running", "completed"))
    handler = Recorder()
    worker = Worker(api, handler, validate=VALIDATE, poll_wait=0, base_backoff_seconds=0.5, max_backoff_seconds=1.5,
                    sleep=sleep)
    asyncio.run(asyncio.wait_for(worker.run(run_id="RUN1"), 5))
    assert sleeps == [0.5, 1.0, 1.5, 0.5]  # doubles, capped, and starts over after a success
    assert handler.handled == ["AZ-1"]
    assert sum("poll failed" in r.getMessage() for r in caplog.records) == 4


def test_graceful_shutdown_finishes_the_current_event():
    api = Stub([envelope("AZ-1"), envelope("AZ-2")])
    handler = Recorder(delay=0.3)
    worker = Worker(api, handler, validate=VALIDATE, poll_wait=0)

    async def go():
        task = asyncio.ensure_future(worker.run())
        while not handler.handled:
            await asyncio.sleep(0.01)
        worker.stop()  # mid-event
        await asyncio.wait_for(task, 2)

    asyncio.run(go())
    assert handler.finished == ["AZ-1"] and api.poll_calls == 1


def test_a_cancelled_worker_still_finishes_the_current_event():
    api = Stub([envelope("AZ-1")])
    handler = Recorder(delay=0.3)
    worker = Worker(api, handler, validate=VALIDATE, poll_wait=0)

    async def go():
        task = asyncio.ensure_future(worker.run())
        while not handler.handled:
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(go())
    assert handler.finished == ["AZ-1"]


def test_stop_while_polling_returns_promptly():
    api = Stub([])  # every poll waits for its full wait
    worker = Worker(api, Recorder(), validate=VALIDATE, poll_wait=25)

    async def go():
        task = asyncio.ensure_future(worker.run())
        await asyncio.sleep(0.05)
        worker.stop()
        await asyncio.wait_for(task, 1)

    asyncio.run(go())


def test_an_unreadable_event_with_a_live_id_gets_a_safe_step_up():
    api = Stub([envelope("AZ-9", currency_note=1) | {"data": {**envelope("AZ-9")["data"], "deadline_at": "soon"}},
                None], statuses=("completed",))
    handler = Recorder()
    asyncio.run(asyncio.wait_for(Worker(api, handler, validate=VALIDATE, poll_wait=0,
                                        engine_version="w").run(run_id="RUN1"), 5))
    assert not handler.handled
    [(aid, body)] = api.posted
    assert aid == "AZ-9" and body["decision"] == "step_up" and "invalid_event" in body["reason_codes"]


def test_a_handler_crash_is_logged_and_the_loop_goes_on(caplog):
    class Crashes(Recorder):
        async def handle(self, request):
            await super().handle(request)
            if request.purchase.authorization_id == "AZ-1":
                raise RuntimeError("boom")

    api = Stub([envelope("AZ-1"), envelope("AZ-2"), None], statuses=("completed",))
    handler = Crashes()
    asyncio.run(asyncio.wait_for(Worker(api, handler, validate=VALIDATE, poll_wait=0).run(run_id="RUN1"), 5))
    assert handler.handled == ["AZ-1", "AZ-2"]
    assert any("handling failed" in r.getMessage() for r in caplog.records)


def test_on_postgres_every_decision_is_posted_at_once_and_the_outbox_has_nothing_to_resend(test_database_url):
    import asyncpg
    from alembic import command

    from adapters.test_schema import alembic
    from leash.adapters.pack.seed import seed
    from leash.adapters.postgres.unit_of_work import PostgresDecisionStore

    command.upgrade(alembic(test_database_url), "head")
    pack = Pack(DATA)
    fake = FakeViseca(pack, api_key="k", human_window_seconds=1)
    client = VisecaClient("k", "http://fake", transport=httpx.ASGITransport(app=fake.app))

    async def go():
        conn = await asyncpg.connect(test_database_url)
        try:
            await seed(conn, pack)
        finally:
            await conn.close()
        pool = await asyncpg.create_pool(test_database_url, min_size=1, max_size=4)
        try:
            use_case = DecidePurchase(store=PostgresDecisionStore(pool, engine_version="w"), reader=RegexReader(),
                                      sender=ApiSender(client), plan=PLAN, engine_version="w", human_window_seconds=120)
            worker = Worker(client, use_case, validate=VALIDATE, poll_wait=1)
            await asyncio.wait_for(worker.run(run_id=await start(client, "SCEN0001")), 60)
            return await pool.fetch("select authorization_id, sent_at, attempts from outbox where endpoint = 'decision'")
        finally:
            await pool.close()

    rows = asyncio.run(go())
    assert len(rows) == len(fake.received) == len(pack.attempts("SCEN0001")) and not fake.rejected
    assert all(r["sent_at"] is not None and r["attempts"] == 1 for r in rows)


def test_a_failing_invalid_event_answer_never_ends_the_loop(caplog):
    class BadPost(Stub):
        async def post_decision(self, authorization_id, decision):
            raise ValueError("2xx with a body that is not JSON")

    bad = {"data": {**envelope("AZ-9")["data"], "deadline_at": "soon"}} | {"run_id": "RUN1"}
    api = BadPost([bad, envelope("AZ-2"), None], statuses=("completed",))
    handler = Recorder()
    asyncio.run(asyncio.wait_for(Worker(api, handler, validate=VALIDATE, poll_wait=0).run(run_id="RUN1"), 5))
    assert handler.handled == ["AZ-2"]


def test_stop_interrupts_a_backoff_wait():
    api = Stub([httpx.ConnectError("down")] * 5)
    worker = Worker(api, Recorder(), validate=VALIDATE, poll_wait=0, base_backoff_seconds=30, max_backoff_seconds=30)

    async def go():
        task = asyncio.ensure_future(worker.run())
        await asyncio.sleep(0.05)
        worker.stop()
        await asyncio.wait_for(task, 1)

    asyncio.run(go())


def test_worker_health_is_ready_only_while_polls_succeed():
    from fastapi.testclient import TestClient

    from leash.adapters.viseca_api.worker import health_app

    now = [1000.0]
    api = Stub([None])
    worker = Worker(api, Recorder(), validate=VALIDATE, poll_wait=0, clock=lambda: now[0])
    http = TestClient(health_app(worker, stale_seconds=60))
    assert http.get("/healthz").json() == {"status": "ok"}
    assert http.get("/readyz").status_code == 503  # no successful poll yet

    async def one_poll():
        await worker._poll()

    asyncio.run(one_poll())
    assert http.get("/readyz").status_code == 200
    now[0] += 61
    assert http.get("/readyz").status_code == 503


# --- LEASH-136: the live budget reaches the platform call ---------------------------------------

def test_the_api_sender_passes_the_live_budget_through_to_the_platform():
    """Per call, not per adapter: the number that bounds the POST is the time actually left before
    `deadline_at`, so the transport is told it rather than a planned figure fixed at construction."""

    class Records:
        def __init__(self):
            self.calls = []

        async def post_decision(self, authorization_id, decision, budget_seconds=None):
            self.calls.append((authorization_id, budget_seconds))
            return {"data": {}}

    api = Records()
    asyncio.run(ApiSender(api).send("AZ-1", {"decision": "approve"}, 0.75))
    asyncio.run(ApiSender(api).send("AZ-2", {"decision": "approve"}))
    assert api.calls == [("AZ-1", 0.75), ("AZ-2", None)]


def test_the_worker_opens_the_pool_before_anything_that_can_fail():
    """Structural, because `_serve` is process wiring with no seam to inject into.

    Both implementations of LEASH-136 got this wrong at some point: the client is created, then the
    bootstrap call opens its pool, then the database pool is created — and only *then* did the
    try/finally that closes the client begin. A version mismatch or a down database leaked the pool.
    `async with client:` has to come before both, and this fails if anyone reorders it.
    """
    import inspect

    from leash.adapters.viseca_api import worker as module

    body = inspect.getsource(module._serve)
    guard = body.index("async with client:")
    for risky in ("platform_client(settings)",):
        assert body.index(risky) < guard, f"{risky} must be inside the guard, not before it"
    for after in ("_work(", ):
        assert body.index(after) > guard, f"{after} must run inside the guard"
    # and the things that open sockets or connections live in `_work`, under the guard
    work = inspect.getsource(module._work)
    assert "load_runtime" in work and "create_pool" in work, \
        "bootstrap and the database pool must sit inside the guarded call, not beside it"


def test_the_sender_treats_a_refused_second_decision_as_already_delivered():
    """409 step_up_resolution_required means the platform has our answer and wants /resolve next. Raising
    here left the outbox row unsent, so it retried the same refused POST every 2 s, for ever."""

    class Refuses:
        async def post_decision(self, authorization_id, decision, budget_seconds=None):
            raise VisecaApiError(409, "POST", f"/v1/authorizations/{authorization_id}/decision",
                                 {"code": "step_up_resolution_required", "message": "Resolve the pending step-up"})

    asyncio.run(ApiSender(Refuses()).send("AZ-1", {"decision": "step_up"}))  # returns: it is delivered


def test_the_sender_still_raises_on_any_other_conflict():
    class Refuses:
        async def post_decision(self, authorization_id, decision, budget_seconds=None):
            raise VisecaApiError(409, "POST", "/v1/authorizations/AZ-1/decision", {"code": "something_else"})

    with pytest.raises(VisecaApiError):
        asyncio.run(ApiSender(Refuses()).send("AZ-1", {"decision": "approve"}))
