"""The fake Viseca API, driven through our real VisecaClient over an in-process transport."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import jsonschema
import pytest

from fake_api.app import FakeViseca
from leash.adapters.pack.loader import Pack
from leash.adapters.viseca_api.client import VisecaApiError, VisecaClient

DATA = Path(__file__).resolve().parents[4] / "data"
SCHEMA = json.loads((DATA / "schemas" / "authorization_event.schema.json").read_text())
KEY = "fake-team-key"
RULE = {"field": "authorization.billing_amount_chf", "operator": "<=", "value": 400, "currency": "CHF",
        "scope": "purchase"}


class Clock:
    def __init__(self):
        self.now = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


@pytest.fixture(scope="module")
def pack():
    return Pack(DATA)


def setup(pack, **config):
    clock = Clock()
    fake = FakeViseca(pack, api_key=KEY, clock=clock, **config)
    client = VisecaClient(KEY, "http://fake", transport=httpx.ASGITransport(app=fake.app))
    return fake, client, clock


def run(coro):
    return asyncio.run(coro)


async def start(client, scenario="SCEN0004", rules=(RULE,), policy="ask"):
    draft = await client.create_mandate({"instruction": "test", "hard_rules": list(rules),
                                         "uncertainty_policy": policy, "guidance": [], "open_questions": []})
    mandate = await client.confirm_mandate(draft["draft_id"])
    return await client.start_run(scenario, mandate["mandate_id"])


async def drain(client, decision="approve"):
    seen = []
    while (envelope := await client.next_decision_request(wait=0)) is not None:
        aid = envelope["data"]["authorization"]["authorization_id"]
        seen.append(envelope)
        await client.post_decision(aid, {"authorization_id": aid, "decision": decision})
    return seen


def test_fake_api_serves_scenario_in_order(pack):
    fake, client, _ = setup(pack)

    async def go():
        started = await start(client)
        return started, await drain(client)

    started, seen = run(go())
    sources = [e["data"]["authorization"]["source_authorization_id"] for e in seen]
    assert sources == [a.purchase.authorization_id for a in pack.attempts("SCEN0004")]
    live = [e["data"]["authorization"]["authorization_id"] for e in seen]
    assert len(set(live)) == len(live) and not set(live) & set(sources)  # live IDs differ from pack IDs
    for e in seen:
        jsonschema.validate(e["data"], SCHEMA)
        assert e["run_id"] == started["run_id"] and e["type"] == "authorization.request"
        assert e["authorization_id"] == e["data"]["authorization"]["authorization_id"]


def test_live_ids_change_between_runs(pack):
    fake, client, _ = setup(pack)

    async def go():
        await start(client, "SCEN0000")
        [first] = await drain(client)
        await start(client, "SCEN0000")
        [second] = await drain(client)
        return first, second

    first, second = run(go())
    ids = [e["data"]["authorization"]["authorization_id"] for e in (first, second)]
    assert ids[0] != ids[1]


def test_event_carries_the_run_snapshot_of_the_mandate(pack):
    fake, client, _ = setup(pack)

    async def go():
        await start(client, "SCEN0000", policy="decline")
        return await client.next_decision_request(wait=0)

    mandate = run(go())["data"]["mandate"]
    assert mandate["hard_rules"] == [RULE] and mandate["uncertainty_policy"] == "decline"
    assert (mandate["card_id"], mandate["customer_id"]) == ("CA0001", "CU0001")


def test_empty_queue_returns_204(pack):
    fake, client, _ = setup(pack)
    assert run(client.next_decision_request(wait=0)) is None


def test_long_poll_waits_for_the_queue_delay_and_the_deadline_counts_from_queueing(pack):
    fake, client, clock = setup(pack, queue_delay_seconds=3)

    async def go():
        await start(client, "SCEN0000")
        assert await client.next_decision_request(wait=0) is None  # not yet queued
        clock.advance(3)
        return await client.next_decision_request(wait=0)

    envelope = run(go())
    deadline = datetime.fromisoformat(envelope["data"]["deadline_at"].replace("Z", "+00:00"))
    assert deadline - fake.clock() == timedelta(seconds=8)


def test_slow_queue_delivers_late_with_less_time_left(pack):
    fake, client, clock = setup(pack, delivery_lag_seconds=5)

    async def go():
        await start(client, "SCEN0000")
        assert await client.next_decision_request(wait=0) is None
        clock.advance(5)
        return await client.next_decision_request(wait=0)

    envelope = run(go())
    deadline = datetime.fromisoformat(envelope["data"]["deadline_at"].replace("Z", "+00:00"))
    assert deadline - fake.clock() == timedelta(seconds=3)  # queued 5 s ago, 8 s deadline


def test_repeat_delivery_sends_the_same_live_id_again(pack):
    fake, client, _ = setup(pack, repeat={"AU0001"})

    async def go():
        await start(client, "SCEN0000")
        a = await client.next_decision_request(wait=0)
        b = await client.next_decision_request(wait=0)
        return a, b

    a, b = run(go())
    assert a["data"]["authorization"]["authorization_id"] == b["data"]["authorization"]["authorization_id"]
    assert a["data"]["deadline_at"] == b["data"]["deadline_at"]


def test_records_received_decisions(pack):
    fake, client, _ = setup(pack)

    async def go():
        await start(client, "SCEN0000")
        e = await client.next_decision_request(wait=0)
        aid = e["data"]["authorization"]["authorization_id"]
        await client.post_decision(aid, {"authorization_id": aid, "decision": "decline", "reason_codes": ["x"],
                                         "customer_message": "No."})
        return aid

    aid = run(go())
    [received] = fake.received
    assert (received["authorization_id"], received["decision"], received["reason_codes"]) == (aid, "decline", ["x"])


def test_decision_rules(pack):
    fake, client, clock = setup(pack)

    async def go():
        await start(client, "SCEN0000")
        e = await client.next_decision_request(wait=0)
        aid = e["data"]["authorization"]["authorization_id"]
        errors = {}
        for name, call in {
            "unknown": client.post_decision("AZ-nope", {"authorization_id": "AZ-nope", "decision": "approve"}),
            "mismatch": client.post_decision(aid, {"authorization_id": "other", "decision": "approve"}),
            "bad": client.post_decision(aid, {"authorization_id": aid, "decision": "maybe"}),
        }.items():
            try:
                await call
            except VisecaApiError as exc:
                errors[name] = exc.status
        await client.post_decision(aid, {"authorization_id": aid, "decision": "step_up"})
        await client.post_decision(aid, {"authorization_id": aid, "decision": "step_up"})  # same answer: fine
        try:
            await client.post_decision(aid, {"authorization_id": aid, "decision": "approve"})
        except VisecaApiError as exc:
            errors["second_automated"] = exc.status
        return errors

    assert run(go()) == {"unknown": 404, "mismatch": 422, "bad": 422, "second_automated": 409}


def test_late_decision_is_rejected(pack):
    fake, client, clock = setup(pack)

    async def go():
        await start(client, "SCEN0000")
        e = await client.next_decision_request(wait=0)
        aid = e["data"]["authorization"]["authorization_id"]
        clock.advance(9)
        with pytest.raises(VisecaApiError) as exc:
            await client.post_decision(aid, {"authorization_id": aid, "decision": "approve"})
        return exc.value, await client.list_authorizations()

    error, listing = run(go())
    assert error.status == 409 and error.error["code"] == "deadline_passed"
    assert listing["data"][0]["status"] == "timed_out"


def test_ask_expiry_and_conflicting_answers(pack):
    fake, client, clock = setup(pack, human_window_seconds=120)

    async def go():
        await start(client, "SCEN0004")
        out = {}
        e1 = await client.next_decision_request(wait=0)
        a1 = e1["data"]["authorization"]["authorization_id"]
        await client.post_decision(a1, {"authorization_id": a1, "decision": "step_up"})
        await client.resolve(a1, {"decision": "approve"})
        await client.resolve(a1, {"decision": "approve"})  # the same answer again is fine
        try:
            await client.resolve(a1, {"decision": "decline"})
        except VisecaApiError as exc:
            out["conflict"] = (exc.status, exc.error["code"])
        e2 = await client.next_decision_request(wait=0)
        a2 = e2["data"]["authorization"]["authorization_id"]
        await client.post_decision(a2, {"authorization_id": a2, "decision": "step_up"})
        e3 = await client.next_decision_request(wait=0)  # the queue moves on while the customer decides
        a3 = e3["data"]["authorization"]["authorization_id"]
        await client.post_decision(a3, {"authorization_id": a3, "decision": "approve"})
        clock.advance(121)
        try:
            await client.resolve(a2, {"decision": "approve"})
        except VisecaApiError as exc:
            out["expired"] = (exc.status, exc.error["code"])
        try:
            await client.resolve(a3, {"decision": "approve"})
        except VisecaApiError as exc:
            out["not_asked"] = (exc.status, exc.error["code"])
        statuses = {a["authorization_id"]: a["status"] for a in (await client.list_authorizations())["data"]}
        return out, statuses, (a1, a2, a3)

    out, statuses, (a1, a2, a3) = run(go())
    assert out == {"conflict": (409, "conflicting_answer"), "expired": (409, "ask_expired"),
                   "not_asked": (409, "not_waiting_for_customer")}
    assert (statuses[a1], statuses[a2], statuses[a3]) == ("approved", "timed_out", "approved")


def test_context_reflects_final_approvals_in_this_run(pack):
    fake, client, _ = setup(pack)

    async def go():
        await start(client, "SCEN0001")
        first = await client.next_decision_request(wait=0)
        a1 = first["data"]["authorization"]["authorization_id"]
        await client.post_decision(a1, {"authorization_id": a1, "decision": "approve"})
        second = await client.next_decision_request(wait=0)
        return first, second

    first, second = run(go())
    assert first["data"]["context"]["approved_spend_in_period_chf"] == 0.0
    assert second["data"]["context"]["approved_spend_in_period_chf"] == 44.5
    jsonschema.validate(second["data"], SCHEMA)


def test_run_progress(pack):
    fake, client, _ = setup(pack)

    async def go():
        started = await start(client, "SCEN0001")
        e = await client.next_decision_request(wait=0)
        aid = e["data"]["authorization"]["authorization_id"]
        await client.post_decision(aid, {"authorization_id": aid, "decision": "step_up"})
        middle = await client.get_run(started["run_id"])
        await client.resolve(aid, {"decision": "approve"})
        await drain(client)
        return middle, await client.get_run(started["run_id"])

    middle, end = run(go())
    assert middle["data"]["counters"] == {"total": 10, "delivered": 1, "decided": 1, "waiting_for_customer": 1,
                                          "final": 0, "remaining": 10}
    assert end["data"]["status"] == "completed" and end["data"]["counters"]["final"] == 10


def test_mandate_rules_and_auth(pack):
    fake, client, _ = setup(pack)

    async def go():
        draft = await client.create_mandate({"instruction": "t", "hard_rules": [RULE], "uncertainty_policy": "ask",
                                             "guidance": [], "open_questions": []})
        try:
            await client.start_run("SCEN0000", draft["draft_id"])
        except VisecaApiError as exc:
            not_active = exc.status
        mid = (await client.confirm_mandate(draft["draft_id"]))["mandate_id"]
        errors = {"not_active": not_active}
        for name, change in {"remove_rule": {"hard_rules": []},
                             "loosen_policy": {"uncertainty_policy": "approve"}}.items():
            try:
                await client.patch_mandate(mid, change)
            except VisecaApiError as exc:
                errors[name] = exc.status
        tightened = await client.patch_mandate(mid, {"hard_rules": [RULE, {**RULE, "value": 300}],
                                                     "uncertainty_policy": "decline"})
        await client.revoke_mandate(mid)
        try:
            await client.start_run("SCEN0000", mid)
        except VisecaApiError as exc:
            errors["revoked"] = exc.status
        wrong = VisecaClient("wrong-key", "http://fake", transport=httpx.ASGITransport(app=fake.app))
        try:
            await wrong.bootstrap()
        except VisecaApiError as exc:
            errors["auth"] = exc.status
        return errors, tightened, await client.bootstrap()

    errors, tightened, settings = run(go())
    assert errors == {"not_active": 409, "remove_rule": 422, "loosen_policy": 422, "revoked": 409, "auth": 401}
    assert len(tightened["data"]["hard_rules"]) == 2
    assert (settings.decision_timeout_seconds, settings.human_window_seconds) == (8, 120)
    assert not settings.defaults_used


def test_long_poll_holds_the_request_until_wait_expires(pack):
    import time as _time

    fake, client, _ = setup(pack)
    start_ = _time.monotonic()
    assert run(client.next_decision_request(wait=1)) is None
    assert 0.9 <= _time.monotonic() - start_ < 2


def test_related_authorization_id_is_rewritten_to_the_live_id(pack):
    fake, client, _ = setup(pack)

    async def go():
        await start(client, "SCEN0004")
        return await drain(client, decision="decline")

    seen = run(go())
    live_of = {e["data"]["authorization"]["source_authorization_id"]: e["data"]["authorization"]["authorization_id"]
               for e in seen}
    related = [e["data"]["authorization"] for e in seen if e["data"]["authorization"]["related_authorization_id"]]
    assert related, "SCEN0004 has re-quotes"
    for a in related:
        source = pack.attempt(a["source_authorization_id"]).purchase.related_authorization_id
        assert a["related_authorization_id"] == live_of[source]


def test_revoking_the_mandate_stops_further_purchases(pack):
    fake, client, _ = setup(pack)

    async def go():
        started = await start(client, "SCEN0001")
        e = await client.next_decision_request(wait=0)
        aid = e["data"]["authorization"]["authorization_id"]
        await client.revoke_mandate(e["data"]["mandate"]["mandate_id"])
        await client.post_decision(aid, {"authorization_id": aid, "decision": "approve"})
        return await client.next_decision_request(wait=0), await client.get_run(started["run_id"])

    nxt, progress = run(go())
    assert nxt is None
    assert progress["data"]["status"] == "stopped" and progress["data"]["counters"]["delivered"] == 1


def test_rejected_posts_are_recorded_too(pack):
    fake, client, clock = setup(pack)

    async def go():
        await start(client, "SCEN0000")
        e = await client.next_decision_request(wait=0)
        aid = e["data"]["authorization"]["authorization_id"]
        clock.advance(9)
        with pytest.raises(VisecaApiError):
            await client.post_decision(aid, {"authorization_id": aid, "decision": "approve"})

    run(go())
    assert fake.received == [] and [r["error"] for r in fake.rejected] == ["deadline_passed"]
