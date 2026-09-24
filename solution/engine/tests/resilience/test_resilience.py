"""Resilience and performance (LEASH-126): the worker, Postgres and the recovery outbox against the fake platform
with faults injected — queue delay, delivery lag, slow answers and polls, refused POSTs, a held card lock, a
restart mid-run — and fact readers that fail or lie. Deadlines hold, nothing counts twice, no verdict loosens.

The deadline report (p50/p95/max from queueing to the accepted decision) is printed, attached to the test as
properties, and written to $LEASH_RESILIENCE_REPORT when that is set.
"""

import asyncio
import dataclasses
import json
import os
import time
from datetime import timedelta
from pathlib import Path

import asyncpg
import httpx
import pytest
from alembic import command

from adapters.test_schema import alembic
from fake_api.app import FakeViseca
from fixtures.mandates import MANDATES
from leash.adapters.fallback_reader import FallbackReader
from leash.adapters.pack.loader import Pack
from leash.adapters.pack.seed import seed
from leash.adapters.postgres.unit_of_work import PostgresDecisionStore, card_lock_key
from leash.adapters.regex_reader import RegexReader
from leash.adapters.viseca_api.client import VisecaClient
from leash.adapters.viseca_api.event_schema import load_event_validator
from leash.adapters.viseca_api.outbox_sender import OutboxSender
from leash.adapters.viseca_api.worker import ApiSender, Worker
from leash.application.decide_purchase import DeadlinePlan, DecidePurchase
from leash.application.replay import replay
from leash.policy.hard_rules import mandate_to_api

DATA = Path(__file__).resolve().parents[4] / "data"
VALIDATE = load_event_validator(DATA / "schemas" / "authorization_event.schema.json")
DECISION_SECONDS = 8.0
PLAN = DeadlinePlan(send_seconds=0.5, lock_seconds=0.5, decide_seconds=0.5, fallback_seconds=0.5)
STRICT = {"approve": 0, "step_up": 1, "decline": 2}
SCENARIOS = ("SCEN0000", "SCEN0001", "SCEN0002", "SCEN0003", "SCEN0004")


def percentile(values, q):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))]


async def start(client, scenario):
    body = {**mandate_to_api(MANDATES[scenario]), "guidance": [], "open_questions": []}
    draft = await client.create_mandate(body)
    mandate_id = (await client.confirm_mandate(draft["draft_id"]))["mandate_id"]
    return (await client.start_run(scenario, mandate_id))["run_id"]


async def seeded_pool(url, pack):
    command.upgrade(alembic(url), "head")
    conn = await asyncpg.connect(url)
    try:
        await seed(conn, pack)
    finally:
        await conn.close()
    return await asyncpg.create_pool(url, min_size=2, max_size=8)


def process(pool, client, sender=None):
    use_case = DecidePurchase(store=PostgresDecisionStore(pool, engine_version="res"), reader=RegexReader(),
                              sender=sender or ApiSender(client), plan=PLAN, engine_version="res",
                              human_window_seconds=120)
    return Worker(client, use_case, validate=VALIDATE, poll_wait=1)


async def recovery(outbox):
    while True:
        await outbox.send_pending()
        await asyncio.sleep(0.2)


async def until(predicate, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.1)
    return predicate()


def test_p95_from_queueing_to_accepted_decision_stays_inside_the_deadline(test_database_url, record_property):
    """All five scenarios at once (45 purchases, several runs queueing together), 0.5 s queue delay, 0.2 s
    delivery lag, slow answers and polls, and three answers refused once with 503 (the outbox resends them)."""
    pack = Pack(DATA)
    refused = {"AU0003": 1, "AU0020": 1, "AU0035": 1}
    fake = FakeViseca(pack, api_key="k", decision_seconds=DECISION_SECONDS, queue_delay_seconds=0.5,
                      delivery_lag_seconds=0.2, decision_delay_seconds=0.15, poll_delay_seconds=0.05,
                      fail_decisions=refused, repeat=["AU0002", "AU0036"])  # re-delivered while unanswered
    client = VisecaClient("k", "http://fake", transport=httpx.ASGITransport(app=fake.app))
    total = sum(len(pack.attempts(s)) for s in SCENARIOS)

    async def go():
        pool = await seeded_pool(test_database_url, pack)
        try:
            worker = process(pool, client)
            outbox = OutboxSender(pool, client, grace_seconds=0.5, base_backoff_seconds=0.2)
            for scenario in SCENARIOS:
                await start(client, scenario)
            polling, recovering = asyncio.ensure_future(worker.run()), asyncio.ensure_future(recovery(outbox))
            try:
                assert await until(lambda: sum(q.decision is not None for r in fake.runs.values()
                                               for q in r.queued) == total, 120)
            finally:
                worker.stop()
                await asyncio.wait_for(polling, 5)
                recovering.cancel()
            return await pool.fetch("select authorization_id, count(*) n from decision_events "
                                    "where kind = 'decided' group by authorization_id")
        finally:
            await pool.close()

    decided = asyncio.run(go())
    queued = [q for r in fake.runs.values() for q in r.queued]
    latencies = [(q.decided_at - q.queued_at).total_seconds() for q in queued]
    margin = PLAN.watchdog_margin.total_seconds()
    report = {"purchases": len(latencies), "p50_s": round(percentile(latencies, 0.50), 3),
              "p95_s": round(percentile(latencies, 0.95), 3), "max_s": round(max(latencies), 3),
              "deadline_s": DECISION_SECONDS, "margin_s": margin,
              "refused_then_resent": sorted(refused), "late": [r for r in fake.rejected if r["error"] == "deadline_passed"]}
    print("\nresilience report:", json.dumps(report))
    for key, value in report.items():
        record_property(key, value)
    if os.environ.get("LEASH_RESILIENCE_REPORT"):
        Path(os.environ["LEASH_RESILIENCE_REPORT"]).write_text(json.dumps(report, indent=2))

    assert len(latencies) == total and all(q.decided_at < q.deadline_at for q in queued)
    assert report["p95_s"] < DECISION_SECONDS - margin, report
    assert not report["late"]
    assert all(r["n"] == 1 for r in decided) and len(decided) == total  # every purchase counted once
    for source in refused:  # refused once (the fault really happened), then delivered by the outbox
        [q] = [q for q in queued if q.attempt.purchase.authorization_id == source]
        assert q.decision is not None
        assert any(r["authorization_id"] == q.live_id and r["status"] == 503 for r in fake.rejected)


def test_a_restart_mid_run_resends_unsent_answers_and_resumes_polling(test_database_url):
    """The first process loses the POST of a purchase after committing it, then stops mid-run (between events,
    with that row committed and unsent). The restarted process resends it from the outbox and carries the run
    to its end."""
    pack = Pack(DATA)
    fake = FakeViseca(pack, api_key="k", decision_seconds=DECISION_SECONDS)
    client = VisecaClient("k", "http://fake", transport=httpx.ASGITransport(app=fake.app))
    total = len(pack.attempts("SCEN0001"))
    lost_sources = {"AU0003", "AU0005"}

    class LosesSome(ApiSender):
        lost: list[str] = []

        async def send(self, authorization_id, body, budget_seconds=None):
            source = fake.live[authorization_id][1].attempt.purchase.authorization_id
            if source in lost_sources:
                self.lost.append(authorization_id)
                raise ConnectionResetError("lost after the commit")
            await super().send(authorization_id, body)

    async def go():
        pool = await seeded_pool(test_database_url, pack)
        await start(client, "SCEN0001")
        crashing = LosesSome(client)
        first = process(pool, client, crashing)
        # the first process has no recovery loop: a lost answer stays unsent until the restart
        polling = asyncio.ensure_future(first.run())
        assert await until(lambda: len(crashing.lost) >= 1, 30)
        first.stop()
        await asyncio.wait_for(polling, 5)
        await pool.close()
        unanswered = [aid for aid in crashing.lost if fake.live[aid][1].decision is None]
        assert unanswered

        pool = await asyncpg.create_pool(test_database_url, min_size=2, max_size=8)  # the restart
        try:
            outbox = OutboxSender(pool, client, grace_seconds=0.3, base_backoff_seconds=0.2)
            second = process(pool, client)
            polling, recovering = asyncio.ensure_future(second.run()), asyncio.ensure_future(recovery(outbox))
            try:
                done = await until(lambda: sum(q.decision is not None for r in fake.runs.values()
                                               for q in r.queued) == total, 90)
            finally:
                second.stop()
                await asyncio.wait_for(polling, 5)
                recovering.cancel()
            decided = await pool.fetch("select authorization_id, count(*) n from decision_events "
                                       "where kind = 'decided' group by authorization_id")
            unsent = await pool.fetchval("select count(*) from outbox where sent_at is null")
            return done, unanswered, decided, unsent
        finally:
            await pool.close()

    done, unanswered, decided, unsent = asyncio.run(go())
    queued = [q for r in fake.runs.values() for q in r.queued]
    assert done and len(queued) == total  # polling resumed and reached the run's end
    for aid in unanswered:
        live = fake.live[aid][1]
        assert live.decision is not None and live.decided_at < live.deadline_at and live.deliveries == 1
    assert all(r["n"] == 1 for r in decided) and len(decided) == total and unsent == 0
    assert not [r for r in fake.rejected if r["error"] == "deadline_passed"]


def test_a_held_card_lock_still_gets_a_safe_answer_in_time(test_database_url):
    """Another transaction holds SCEN0000's card lock for longer than the whole deadline: the purchase is
    answered with a safe step_up before its deadline, never left unanswered."""
    pack = Pack(DATA)
    fake = FakeViseca(pack, api_key="k", decision_seconds=DECISION_SECONDS)
    client = VisecaClient("k", "http://fake", transport=httpx.ASGITransport(app=fake.app))
    card = pack.attempts("SCEN0000")[0].purchase.card_id

    async def go():
        pool = await seeded_pool(test_database_url, pack)
        holder = await asyncpg.connect(test_database_url)
        try:
            tx = holder.transaction()
            await tx.start()
            await holder.execute("select pg_advisory_xact_lock(hashtext($1))", card_lock_key(card))
            await start(client, "SCEN0000")
            worker = process(pool, client)
            polling = asyncio.ensure_future(worker.run())
            try:
                assert await until(lambda: any(q.decision for r in fake.runs.values() for q in r.queued), 15)
            finally:
                worker.stop()
                await asyncio.wait_for(polling, 10)
                await tx.rollback()
        finally:
            await holder.close()
            await pool.close()

    asyncio.run(go())
    [live] = [q for r in fake.runs.values() for q in r.queued]
    assert live.decision == "step_up" and live.decided_at < live.deadline_at


# ----- fact readers that fail or lie never loosen a verdict --------------------------------------------------

class Raises:
    def read(self, purchase, budget):
        raise RuntimeError("model crashed")


class Hangs:
    def read(self, purchase, budget):
        time.sleep(0.3)
        raise TimeoutError("never answered in time")


class Lies:
    """A model that reads every shop text in the most permissive way it can."""

    def read(self, purchase, budget):
        honest = RegexReader().read(purchase, budget)
        return dataclasses.replace(honest, reader="laya", sizes=None, return_days=365, final_sale=False,
                                   injection_excerpt=None, addon_lines=frozenset(), recurring_lines=frozenset(),
                                   oversized_text=False, deterministic=None)


@pytest.mark.parametrize("primary", [Raises(), Hangs(), Lies()], ids=["raises", "times-out", "lies"])
def test_reader_failure_never_produces_a_less_strict_verdict(primary):
    pack = Pack(DATA)
    for scenario in SCENARIOS:
        baseline = replay(pack, scenario, MANDATES[scenario], reader=RegexReader())
        guarded = replay(pack, scenario, MANDATES[scenario],
                         reader=FallbackReader(primary, RegexReader(), timeout_seconds=0.05))
        for base, row in zip(baseline, guarded, strict=True):
            assert STRICT[row.verdict] >= STRICT[base.verdict], (scenario, base.authorization_id, base, row)
