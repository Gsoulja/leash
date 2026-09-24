"""Outbox sender against a throw-away Postgres (LEASH-054)."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg
import httpx
import pytest
from alembic import command

from fake_api.app import FakeViseca
from leash.adapters.pack.loader import Pack
from leash.adapters.viseca_api.client import VisecaApiError, VisecaClient
from leash.adapters.viseca_api.outbox_sender import OutboxSender
from test_schema import alembic, sql

DATA = Path(__file__).resolve().parents[4] / "data"
T0 = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def db(test_database_url):
    command.upgrade(alembic(test_database_url), "head")
    return test_database_url


def add_row(url, aid, endpoint="decision", body=None, created=T0):
    body = body or {"authorization_id": aid, "decision": "approve"}
    sql(url, f"insert into outbox (authorization_id, endpoint, body, created_at) values "
             f"('{aid}', '{endpoint}', '{json.dumps(body)}', '{created.isoformat()}')")


class FakeClient:
    def __init__(self, fail=None):
        self.calls: list[tuple[str, str, dict]] = []
        self.fail = fail or {}  # authorization_id -> exception to raise (once per entry in a list)

    async def post_decision(self, aid, body):
        return await self._call("decision", aid, body)

    async def resolve(self, aid, body):
        return await self._call("resolve", aid, body)

    async def _call(self, endpoint, aid, body):
        self.calls.append((endpoint, aid, body))
        errors = self.fail.get(aid)
        if errors:
            raise errors.pop(0)
        return {"data": {}}


def sender(url, client, now):
    async def make():
        pool = await asyncpg.create_pool(url, min_size=1, max_size=2)
        return pool, OutboxSender(pool, client, clock=lambda: now, grace_seconds=2, base_backoff_seconds=1,
                                  max_backoff_seconds=30)
    return make


def run_once(url, client, now):
    async def go():
        pool, s = await sender(url, client, now)()
        try:
            return await s.send_pending()
        finally:
            await pool.close()
    return asyncio.run(go())


def rows(url):
    return sql(url, "select authorization_id, sent_at, attempts, last_error from outbox order by id")


def test_unsent_row_is_resent_after_restart(db):
    # The process committed the decision, then crashed before sending it.
    add_row(db, "AZ-1")
    client = FakeClient()
    sent = run_once(db, client, T0 + timedelta(seconds=10))  # a fresh sender after the restart
    assert sent == 1 and client.calls == [("decision", "AZ-1", {"authorization_id": "AZ-1", "decision": "approve"})]
    [row] = rows(db)
    assert row["sent_at"] is not None and row["attempts"] == 1


def test_unsent_rows_are_sent_in_order_including_resolves(db):
    add_row(db, "AZ-2"), add_row(db, "AZ-1"), add_row(db, "AZ-2", "resolve", {"decision": "approve"})
    client = FakeClient()
    run_once(db, client, T0 + timedelta(seconds=10))
    assert [(e, a) for e, a, _ in client.calls] == [("decision", "AZ-2"), ("decision", "AZ-1"), ("resolve", "AZ-2")]


def test_it_never_races_the_workers_first_send(db):
    add_row(db, "AZ-1", created=T0)
    client = FakeClient()
    assert run_once(db, client, T0 + timedelta(seconds=1)) == 0  # inside the grace period: the worker's job
    assert client.calls == []


def test_mark_sent_is_what_the_worker_calls_after_its_immediate_send(db):
    add_row(db, "AZ-1")

    async def go():
        pool, s = await sender(db, FakeClient(), T0)()
        try:
            await s.mark_sent("AZ-1")
        finally:
            await pool.close()
    asyncio.run(go())
    assert rows(db)[0]["sent_at"] is not None
    client = FakeClient()
    assert run_once(db, client, T0 + timedelta(seconds=10)) == 0 and client.calls == []


def test_failures_increase_attempts_and_back_off(db):
    add_row(db, "AZ-1")
    down = lambda: httpx.ConnectError("platform down")  # noqa: E731
    client = FakeClient(fail={"AZ-1": [down(), down(), down()]})
    t = T0 + timedelta(seconds=10)
    run_once(db, client, t)                                  # attempt 1 fails
    assert rows(db)[0]["attempts"] == 1 and "platform down" in rows(db)[0]["last_error"]
    run_once(db, client, t + timedelta(seconds=0.5))         # before 1 s backoff: skipped
    assert len(client.calls) == 1
    run_once(db, client, t + timedelta(seconds=1.1))         # attempt 2 fails → next wait 2 s
    run_once(db, client, t + timedelta(seconds=2.5))         # 1.4 s later: skipped
    assert len(client.calls) == 2
    run_once(db, client, t + timedelta(seconds=3.2))         # attempt 3 fails → wait 4 s
    run_once(db, client, t + timedelta(seconds=7.3))         # attempt 4 succeeds
    [row] = rows(db)
    assert len(client.calls) == 4 and row["attempts"] == 4 and row["sent_at"] is not None


def test_server_errors_retry_but_a_final_refusal_is_not_retried_forever(db):
    add_row(db, "AZ-5xx"), add_row(db, "AZ-409")
    client = FakeClient(fail={
        "AZ-5xx": [VisecaApiError(503, "POST", "/x", {"code": "unavailable"})],
        "AZ-409": [VisecaApiError(409, "POST", "/x", {"code": "deadline_passed"})]})
    run_once(db, client, T0 + timedelta(seconds=10))
    by_id = {r["authorization_id"]: r for r in rows(db)}
    assert by_id["AZ-5xx"]["sent_at"] is None and by_id["AZ-5xx"]["attempts"] == 1
    assert by_id["AZ-409"]["sent_at"] is not None and "deadline_passed" in by_id["AZ-409"]["last_error"]
    run_once(db, client, T0 + timedelta(seconds=60))
    assert [a for _, a, _ in client.calls].count("AZ-409") == 1


def test_resending_an_already_accepted_decision_is_harmless(db, test_database_url):
    # Against the fake Viseca API: the decision was accepted, but we crashed before marking it sent.
    clock_now = [datetime.now(timezone.utc)]
    fake = FakeViseca(Pack(DATA), api_key="k", clock=lambda: clock_now[0])
    client = VisecaClient("k", "http://fake", transport=httpx.ASGITransport(app=fake.app))

    async def go():
        draft = await client.create_mandate({"instruction": "t", "hard_rules": [], "uncertainty_policy": "ask",
                                             "guidance": [], "open_questions": []})
        mid = (await client.confirm_mandate(draft["draft_id"]))["mandate_id"]
        await client.start_run("SCEN0000", mid)
        e = await client.next_decision_request(wait=0)
        aid = e["data"]["authorization"]["authorization_id"]
        body = {"authorization_id": aid, "decision": "approve"}
        await client.post_decision(aid, body)  # accepted the first time
        return aid, body

    aid, body = asyncio.run(go())
    add_row(db, aid, body=body)
    sent = run_once(db, client, T0 + timedelta(seconds=10))
    [row] = rows(db)
    assert sent == 1 and row["sent_at"] is not None and row["last_error"] is None
    assert len(fake.received) == 1 and fake.rejected == []  # the platform treated it as the same answer


def test_concurrent_senders_do_not_double_send(db):
    for i in range(6):
        add_row(db, f"AZ-{i}")
    client = FakeClient()

    async def go():
        pool = await asyncpg.create_pool(db, min_size=2, max_size=4)
        try:
            a = OutboxSender(pool, client, clock=lambda: T0 + timedelta(seconds=10), grace_seconds=2)
            b = OutboxSender(pool, client, clock=lambda: T0 + timedelta(seconds=10), grace_seconds=2)
            return await asyncio.gather(a.send_pending(), b.send_pending())
        finally:
            await pool.close()

    counts = asyncio.run(go())
    assert sum(counts) == 6 and sorted(a for _, a, _ in client.calls) == [f"AZ-{i}" for i in range(6)]


def test_a_resolve_never_overtakes_its_own_decision(db):
    # Review finding: while the step_up decision backed off, the resolve went first and was closed as a 409.
    add_row(db, "AZ-1", body={"authorization_id": "AZ-1", "decision": "step_up"})
    add_row(db, "AZ-1", "resolve", {"decision": "approve"})
    add_row(db, "AZ-2")
    client = FakeClient(fail={"AZ-1": [VisecaApiError(503, "POST", "/x", {"code": "unavailable"})]})
    t = T0 + timedelta(seconds=10)
    run_once(db, client, t)
    assert [(e, a) for e, a, _ in client.calls] == [("decision", "AZ-1"), ("decision", "AZ-2")]  # resolve waits
    run_once(db, client, t + timedelta(seconds=1.1))
    assert [(e, a) for e, a, _ in client.calls][2:] == [("decision", "AZ-1"), ("resolve", "AZ-1")]
    assert all(r["sent_at"] is not None for r in rows(db))


def test_backoff_counts_from_when_a_slow_attempt_failed(db):
    # Review finding: a failure slower than the backoff was retried at once and held up other rows.
    add_row(db, "SLOW"), add_row(db, "OTHER")
    now = [T0 + timedelta(seconds=10)]

    class SlowFailure(FakeClient):
        async def _call(self, endpoint, aid, body):
            self.calls.append((endpoint, aid, body))
            if aid == "SLOW":
                now[0] += timedelta(seconds=1.5)  # the platform took 1.5 s to fail
                raise VisecaApiError(503, "POST", "/x", {"code": "unavailable"})
            return {"data": {}}

    client = SlowFailure()

    async def go():
        pool = await asyncpg.create_pool(db, min_size=1, max_size=2)
        try:
            s = OutboxSender(pool, client, clock=lambda: now[0], grace_seconds=2, base_backoff_seconds=1)
            return await s.send_pending()
        finally:
            await pool.close()

    asyncio.run(go())
    assert [a for _, a, _ in client.calls] == ["SLOW", "OTHER"]  # not retried within the same pass
    [slow] = [r for r in rows(db) if r["authorization_id"] == "SLOW"]
    assert slow["attempts"] == 1


def test_one_pass_tries_each_row_at_most_once(db):
    # Review finding: slow failures whose backoff ran out mid-pass were retried again, starving healthy rows.
    for i in range(7):
        add_row(db, f"SLOW{i}")
    add_row(db, "OK")
    now = [T0 + timedelta(seconds=10)]

    class Timeouts(FakeClient):
        async def _call(self, endpoint, aid, body):
            self.calls.append((endpoint, aid, body))
            if aid.startswith("SLOW"):
                now[0] += timedelta(seconds=10)
                raise httpx.ReadTimeout("timed out")
            return {"data": {}}

    client = Timeouts()

    async def go():
        pool = await asyncpg.create_pool(db, min_size=1, max_size=2)
        try:
            return await OutboxSender(pool, client, clock=lambda: now[0], grace_seconds=2).send_pending()
        finally:
            await pool.close()

    asyncio.run(asyncio.wait_for(go(), 10))
    assert [a for _, a, _ in client.calls] == [f"SLOW{i}" for i in range(7)] + ["OK"]


def test_a_pass_only_covers_rows_that_existed_when_it_started(db):
    # Review caveat: with new failing rows arriving during every slow attempt, a pass never ended.
    add_row(db, "R0")
    now = [T0 + timedelta(seconds=10)]
    added = [0]

    class Arriving(FakeClient):
        async def _call(self, endpoint, aid, body):
            self.calls.append((endpoint, aid, body))
            added[0] += 1
            add_row(db, f"NEW{added[0]}", created=T0)  # a new unsent row arrives meanwhile
            now[0] += timedelta(seconds=10)
            raise httpx.ReadTimeout("timed out")

    client = Arriving()

    async def go():
        pool = await asyncpg.create_pool(db, min_size=1, max_size=2)
        try:
            return await OutboxSender(pool, client, clock=lambda: now[0], grace_seconds=2).send_pending()
        finally:
            await pool.close()

    asyncio.run(asyncio.wait_for(go(), 10))
    assert [a for _, a, _ in client.calls] == ["R0"]  # new rows wait for the next pass
