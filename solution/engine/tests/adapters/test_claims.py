"""Durable processing claims (LEASH-131): a received authorization is owned by one worker under a short lease,
so a redelivery can take over from a worker that died after receiving it, and a live owner is never doubled."""

import asyncio
from datetime import timedelta

import pytest

from factories import facts
from leash.adapters.postgres.unit_of_work import PostgresDecisionStore
from leash.application.decide_purchase import DeadlinePlan, DecidePurchase, DecisionRequest
from leash.domain.clock import WallTime
from test_decision_transaction import NOW, WEEK_300, buy, db, with_pool  # noqa: F401 - db is a fixture
from test_schema import sql

EVENT = {"mandate": {"mandate_id": "TM1"}}


def store(pool, owner, lease_seconds=5.0):
    return PostgresDecisionStore(pool, engine_version="leash-test", owner=owner, lease_seconds=lease_seconds)


async def receive(s, p):
    return await s.receive(p, run_id="RUN1", event=EVENT, received_at=NOW, deadline_at=NOW + timedelta(seconds=8))


async def claim_of(pool, aid):
    return await pool.fetchrow("select claim_owner, claim_expires_at > now() as live from authorizations "
                               "where authorization_id = $1", aid)


async def expire(pool, aid):
    await pool.execute("update authorizations set claim_expires_at = now() - interval '1 second' "
                       "where authorization_id = $1", aid)


def test_a_received_authorization_has_an_owner_and_a_live_lease(db):
    async def body(pool):
        assert await receive(store(pool, "worker-a"), buy("A", "20.00")) is None
        claim = await claim_of(pool, "A")
        assert (claim["claim_owner"], claim["live"]) == ("worker-a", True)
    with_pool(db, body)


def test_a_live_claim_by_another_worker_prevents_duplicate_work(db):
    async def body(pool):
        await receive(store(pool, "worker-a"), buy("A", "20.00"))
        saved = await receive(store(pool, "worker-b"), buy("A", "20.00"))
        assert saved is not None and saved.response is None  # in flight elsewhere: nothing to do
        assert (await claim_of(pool, "A"))["claim_owner"] == "worker-a"
    with_pool(db, body)


def test_a_redelivery_reclaims_an_expired_claim(db):
    async def body(pool):
        await receive(store(pool, "worker-a"), buy("A", "20.00"))
        await expire(pool, "A")
        assert await receive(store(pool, "worker-b"), buy("A", "20.00")) is None  # b now owns the work
        assert (await claim_of(pool, "A"))["claim_owner"] == "worker-b"
        kinds = [r["kind"] for r in await pool.fetch(
            "select kind from decision_events where authorization_id = 'A' order by seq")]
        assert kinds == ["received", "reclaimed"]
    with_pool(db, body)


def test_only_one_of_two_concurrent_redeliveries_reclaims(db):
    async def body(pool):
        await receive(store(pool, "worker-a"), buy("A", "20.00"))
        await expire(pool, "A")
        results = await asyncio.gather(receive(store(pool, "worker-b"), buy("A", "20.00")),
                                       receive(store(pool, "worker-c"), buy("A", "20.00")))
        assert sorted(r is None for r in results) == [False, True]
    with_pool(db, body)


def test_an_answered_authorization_is_never_reclaimed(db):
    async def body(pool):
        a = store(pool, "worker-a")
        await receive(a, buy("A", "20.00"))
        await a.decide(buy("A", "20.00"), run_id="RUN1", mandate=WEEK_300, facts=facts(), platform_period_spend_chf=None)
        await expire(pool, "A")
        saved = await receive(store(pool, "worker-b"), buy("A", "20.00"))
        assert saved is not None and saved.response is not None  # a repeat, answered from what is stored
    with_pool(db, body)


def test_a_stale_owner_cannot_commit_after_a_reclaim_and_the_spend_counts_once(db):
    async def body(pool):
        a, b, p = store(pool, "worker-a"), store(pool, "worker-b"), buy("A", "200.00")
        await receive(a, p)
        await expire(pool, "A")  # a stalls past its lease
        await receive(b, p)
        await b.decide(p, run_id="RUN1", mandate=WEEK_300, facts=facts(), platform_period_spend_chf=None)
        with pytest.raises(Exception):  # a wakes up: its commit is refused, the state already left 'received'
            await a.decide(p, run_id="RUN1", mandate=WEEK_300, facts=facts(), platform_period_spend_chf=None)
        committed = await a.record_fallback(p, run_id="RUN1", response={"decision": "step_up"},
                                            ask_expires_at=NOW + timedelta(seconds=120))
        assert committed is not None and committed.engine_verdict == "approve"  # a sends b's stored decision
        assert await pool.fetchval("select count(*) from decision_events where authorization_id = 'A' "
                                   "and kind = 'decided'") == 1
        assert await pool.fetchval("select count(*) from outbox where authorization_id = 'A'") == 1
    with_pool(db, body)


def test_the_owner_refreshes_its_claim_and_releases_it(db):
    async def body(pool):
        a, b = store(pool, "worker-a", lease_seconds=1.0), store(pool, "worker-b")
        await receive(a, buy("A", "20.00"))
        await expire(pool, "A")
        assert await b.refresh_claim("A") is False  # not b's claim
        assert await a.refresh_claim("A") is True
        assert (await claim_of(pool, "A"))["live"] is True
        await a.release_claim("A")
        assert (await claim_of(pool, "A"))["claim_owner"] is None
        assert await receive(b, buy("A", "20.00")) is None  # released work is taken over at once
    with_pool(db, body)


def test_crash_after_receive_then_a_redelivery_after_restart_completes_the_decision(db):
    class Sender:
        def __init__(self):
            self.sent = []

        async def send(self, aid, body):
            self.sent.append((aid, body["decision"]))

    async def body(pool):
        p = buy("A", "20.00")
        await receive(store(pool, "worker-before-crash"), p)  # received, then the process died
        await expire(pool, "A")
        sender = Sender()
        restarted = DecidePurchase(store=store(pool, "worker-after-restart"), reader=_Regex(), sender=sender,
                                   plan=DeadlinePlan(send_seconds=0.5, lock_seconds=0.5, decide_seconds=0.5,
                                                     fallback_seconds=0.5),
                                   engine_version="leash-test", human_window_seconds=120)
        from datetime import datetime, timezone
        result = await restarted.handle(DecisionRequest(
            purchase=p, mandate=WEEK_300, run_id="RUN1", event=EVENT, platform_period_spend_chf=None,
            deadline_at=WallTime(datetime.now(timezone.utc) + timedelta(seconds=8))))
        assert (result.path, result.sent, sender.sent) == ("decided", True, [("A", "approve")])
        assert await pool.fetchval("select state from authorizations where authorization_id = 'A'") == "approved"
    with_pool(db, body)


class _Regex:
    def read(self, p, budget):
        return facts()


def test_the_claim_columns_exist(db):
    sql(db, "select claim_owner, claim_expires_at from authorizations limit 0")


def test_a_lease_that_is_not_refreshed_runs_out_by_itself(db):
    async def body(pool):
        await receive(store(pool, "worker-a", lease_seconds=0.3), buy("A", "20.00"))
        assert await receive(store(pool, "worker-b"), buy("A", "20.00")) is not None  # still live
        await asyncio.sleep(0.5)
        assert await receive(store(pool, "worker-b"), buy("A", "20.00")) is None  # lapsed: taken over
    with_pool(db, body)


def test_a_stale_owners_release_never_frees_the_new_owners_claim(db):
    async def body(pool):
        a, b = store(pool, "worker-a"), store(pool, "worker-b")
        await receive(a, buy("A", "20.00"))
        await expire(pool, "A")
        await receive(b, buy("A", "20.00"))
        await a.release_claim("A")  # a wakes up and cleans up after itself
        claim = await claim_of(pool, "A")
        assert (claim["claim_owner"], claim["live"]) == ("worker-b", True)
        assert await receive(store(pool, "worker-c"), buy("A", "20.00")) is not None  # no third worker gets in
    with_pool(db, body)
