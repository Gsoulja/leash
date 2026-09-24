"""The decide-purchase use case, with fakes for the store, sender and reader (LEASH-052)."""

import asyncio
import inspect
import logging
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from factories import facts, mandate, max_per_order, purchase
from leash.adapters.fallback_reader import FallbackReader
from leash.application.decide_purchase import DeadlinePlan, DecidePurchase, DecisionRequest
from leash.domain.clock import WallTime
from leash.domain.decide import decide
from leash.domain.explain import explain
from leash.ports.repository import SavedAuthorization

from factories import snapshot


class FakeStore:
    def __init__(self, saved=None, decide_delay=0.0, fallback_delay=0.0):
        self.saved, self.decide_delay, self.fallback_delay = saved, decide_delay, fallback_delay
        self.committed: dict[str, dict] = {}
        self.mandate_ids: list = []
        self.calls: list[str] = []
        self.decided: dict[str, dict] = {}
        self.fallbacks: dict[str, dict] = {}
        self.sent_marks: list[str] = []
        self.mandates_used = []

    async def receive(self, p, *, run_id, event, received_at, deadline_at):
        self.calls.append("receive")
        if isinstance(self.saved, list):  # successive deliveries see successive stored states
            return self.saved.pop(0) if len(self.saved) > 1 else self.saved[0]
        return self.saved

    async def decide(self, p, *, run_id, mandate, facts, platform_period_spend_chf, ask_expires_at=None,
                     mandate_id=None):
        self.calls.append("decide")
        self.mandates_used.append(mandate)
        self.mandate_ids.append(mandate_id)
        await asyncio.sleep(self.decide_delay)
        d = decide(p, mandate, snapshot(), facts)
        body = explain(d, authorization_id=p.authorization_id, engine_version="test")
        self.decided[p.authorization_id] = body

        class Outcome:
            decision, response, stages = d, body, [("lock", 1.0), ("snapshot", 1.0)]
        return Outcome()

    async def record_fallback(self, p, *, run_id, response, ask_expires_at):
        self.calls.append("record_fallback")
        await asyncio.sleep(self.fallback_delay)
        if p.authorization_id in self.committed:  # the decision's commit landed first: that is the truth
            return SavedAuthorization(p.authorization_id, "approved", "approve", self.committed[p.authorization_id])
        self.fallbacks[p.authorization_id] = response
        return None

    async def mark_sent(self, authorization_id):
        self.calls.append("mark_sent")
        self.sent_marks.append(authorization_id)

    refreshes: list
    releases: list
    refresh_fails = False

    async def refresh_claim(self, authorization_id):
        self.__dict__.setdefault("refreshes", []).append(authorization_id)
        if self.refresh_fails:
            raise ConnectionError("database away")
        return True

    async def release_claim(self, authorization_id):
        self.__dict__.setdefault("releases", []).append(authorization_id)


class FakeSender:
    def __init__(self):
        self.sent: list[tuple[str, dict]] = []

    async def send(self, authorization_id, body):
        self.sent.append((authorization_id, body))


class Reader:
    def __init__(self, delay=0.0, result=None):
        self.delay, self.result, self.budgets = delay, result or facts(), []

    def read(self, p, budget):
        self.budgets.append(budget.remaining_seconds())
        time.sleep(self.delay)
        return self.result


class Hangs:
    def read(self, p, budget):
        time.sleep(5)
        return facts(reader="laya")


PLAN = DeadlinePlan(send_seconds=0.3, lock_seconds=0.3, decide_seconds=0.2, fallback_seconds=0.3)


def request(deadline_in=3.0, aid="AZ-1", chf="20.00", m=None):
    now = datetime.now(timezone.utc)
    return DecisionRequest(purchase=purchase(chf, authorization_id=aid), mandate=m or mandate(max_per_order("400")),
                           run_id="RUN1", event={"authorization": {"authorization_id": aid}},
                           deadline_at=WallTime(now + timedelta(seconds=deadline_in)), platform_period_spend_chf=None)


def use_case(store=None, reader=None, sender=None, plan=PLAN, claim_refresh_seconds=1.0):
    return DecidePurchase(store=store or FakeStore(), reader=reader or Reader(), sender=sender or FakeSender(),
                          plan=plan, engine_version="test", human_window_seconds=120,
                          claim_refresh_seconds=claim_refresh_seconds)


def run(coro):
    return asyncio.run(coro)


def test_watchdog_sends_step_up_when_reader_hangs():
    # The model hangs; even with no fallback reader in front, the watchdog answers before the deadline.
    store, sender = FakeStore(), FakeSender()
    uc = use_case(store=store, reader=Hangs(), sender=sender)
    start = time.monotonic()
    result = run(uc.handle(request(deadline_in=1.5)))
    elapsed = time.monotonic() - start
    assert result.path == "watchdog" and result.verdict == "step_up"
    assert elapsed < 1.5 - PLAN.send_seconds + 0.15  # answered well before the deadline
    [(aid, body)] = sender.sent
    assert aid == "AZ-1" and body["decision"] == "step_up" and body["reason_codes"] == ["decision_timeout"]
    assert store.fallbacks["AZ-1"] == body and store.sent_marks == ["AZ-1"]
    assert "decide" not in store.calls  # never reached the transaction


def test_watchdog_also_covers_a_stalled_transaction():
    store = FakeStore(decide_delay=5)
    result = run(use_case(store=store).handle(request(deadline_in=1.2)))
    assert result.path == "watchdog" and store.fallbacks


def test_normal_path_order_and_immediate_send():
    store, sender = FakeStore(), FakeSender()
    result = run(use_case(store=store, sender=sender).handle(request()))
    assert result.path == "decided" and result.verdict == "approve"
    assert store.calls == ["receive", "decide", "mark_sent"]
    assert sender.sent == [("AZ-1", store.decided["AZ-1"])]


def test_each_stage_is_timed_and_logged(caplog):
    caplog.set_level(logging.INFO, logger="leash.decide")
    result = run(use_case().handle(request()))
    names = [name for name, _ in result.stages]
    assert names == ["validate", "dedupe", "read_facts", "lock", "snapshot", "transaction", "send", "mark_sent"]
    assert all(ms >= 0 for _, ms in result.stages)
    logged = [r for r in caplog.records if r.name == "leash.decide"]
    assert {getattr(r, "stage", None) for r in logged} >= set(names)
    assert all(getattr(r, "authorization_id", None) == "AZ-1" for r in logged)


def test_a_reader_that_times_out_yields_regex_facts_marked_model_unavailable():
    class Slow:
        def read(self, p, budget):
            time.sleep(2)
            return facts(reader="laya")

    fallback = FallbackReader(Slow(), Reader(result=facts(reader="regex")), timeout_seconds=0.2)
    store = FakeStore()
    seen = []
    original = store.decide

    async def spy(p, **kw):
        seen.append(kw["facts"])
        return await original(p, **kw)

    store.decide = spy
    result = run(use_case(store=store, reader=fallback).handle(request()))
    assert result.path == "decided"
    assert seen[0].reader == "regex" and seen[0].model_unavailable


def test_repeat_delivery_short_circuits_to_the_saved_verdict():
    saved_body = {"authorization_id": "AZ-1", "decision": "decline", "reason_codes": ["over_order_limit"]}
    store, sender, reader = FakeStore(saved=SavedAuthorization("AZ-1", "declined", "decline", saved_body)), \
        FakeSender(), Reader()
    result = run(use_case(store=store, sender=sender, reader=reader).handle(request()))
    assert (result.path, result.verdict) == ("repeat", "decline")
    assert sender.sent == [("AZ-1", saved_body)]  # the same answer again, never a second decision
    assert reader.budgets == [] and "decide" not in store.calls


IN_FLIGHT = SavedAuthorization("AZ-1", "received", None, None)


def test_a_repeat_while_the_first_delivery_is_in_flight_waits_for_its_answer_and_sends_it():  # LEASH-131
    answered = SavedAuthorization("AZ-1", "approved", "approve", {"decision": "approve"})
    store, sender = FakeStore(saved=[IN_FLIGHT, IN_FLIGHT, answered]), FakeSender()
    result = run(use_case(store=store, sender=sender).handle(request()))
    assert result.path == "repeat" and sender.sent == [("AZ-1", {"decision": "approve"})]
    assert "decide" not in store.calls


def test_a_repeat_takes_the_work_over_when_the_dead_owners_lease_lapses():  # LEASH-131 review: crash inside the lease
    store, sender = FakeStore(saved=[IN_FLIGHT, IN_FLIGHT, None]), FakeSender()
    result = run(use_case(store=store, sender=sender).handle(request()))
    assert result.path == "decided" and sender.sent and store.__dict__.get("releases") == ["AZ-1"]


def test_a_repeat_that_never_sees_an_answer_still_gets_a_safe_step_up_before_the_deadline():
    store, sender = FakeStore(saved=IN_FLIGHT), FakeSender()
    start = time.monotonic()
    result = run(use_case(store=store, sender=sender).handle(request(deadline_in=1.2)))
    assert result.path == "watchdog" and [b["decision"] for _, b in sender.sent] == ["step_up"]
    assert time.monotonic() - start < 1.2


def test_watchdog_margin_covers_lock_wait_and_send_not_only_reading():
    reader = Reader()
    run(use_case(reader=reader).handle(request(deadline_in=3.0)))
    [budget] = reader.budgets
    # The reader must stop early enough for lock wait + decide/save + send before the deadline.
    assert budget <= 3.0 - (PLAN.send_seconds + PLAN.lock_seconds + PLAN.decide_seconds) + 0.05
    assert PLAN.reader_margin == timedelta(seconds=0.8)
    assert PLAN.watchdog_margin == timedelta(seconds=0.6)  # recording the fallback + sending it


def test_plan_from_runtime_settings_uses_the_lock_timeout():
    plan = DeadlinePlan.for_lock_timeout(lock_timeout_ms=1500, send_seconds=1.0)
    assert plan.lock_seconds == 1.5 and plan.reader_margin > timedelta(seconds=2.5)


def test_decisions_use_the_events_mandate_snapshot():
    store = FakeStore()
    strict = mandate(max_per_order("10"))
    result = run(use_case(store=store).handle(request(m=strict)))
    assert store.mandates_used == [strict] and result.verdict == "decline"
    params = inspect.signature(DecidePurchase.__init__).parameters
    assert not any("mandate" in name for name in params)  # no local mandate source to fall back on


def test_a_request_past_its_deadline_is_not_decided():
    store, sender = FakeStore(), FakeSender()
    result = run(use_case(store=store, sender=sender).handle(request(deadline_in=-1)))
    assert result.path == "late" and sender.sent == [] and store.calls == []


def test_send_failure_leaves_it_unmarked_for_the_outbox():
    class Down:
        async def send(self, aid, body):
            raise ConnectionError("platform down")

    store = FakeStore()
    result = run(use_case(store=store, sender=Down()).handle(request()))
    assert result.path == "decided" and result.sent is False and store.sent_marks == []


class SentAt(FakeSender):
    def __init__(self):
        super().__init__()
        self.at: list[float] = []

    async def send(self, authorization_id, body):
        self.at.append(time.monotonic())
        await super().send(authorization_id, body)


def test_a_slow_fallback_record_still_answers_before_the_deadline():
    store, sender = FakeStore(decide_delay=5, fallback_delay=2), SentAt()
    start = time.monotonic()
    result = run(use_case(store=store, sender=sender).handle(request(deadline_in=1.5)))
    assert result.verdict == "step_up" and sender.at[0] - start < 1.5 - 0.1


def test_slow_cleanup_after_cancellation_does_not_delay_the_answer():
    class SlowCleanup(FakeStore):
        async def decide(self, p, **kw):
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                await asyncio.sleep(0.8)  # e.g. a rollback round-trip
                raise

    sender = SentAt()
    start = time.monotonic()
    result = run(use_case(store=SlowCleanup(), sender=sender).handle(request(deadline_in=1.5)))
    assert result.verdict == "step_up" and sender.at[0] - start < 1.5 - 0.1


def test_a_commit_that_lands_at_the_watchdog_sends_the_committed_decision():
    class CommitsThenStalls(FakeStore):
        async def decide(self, p, **kw):
            body = {"authorization_id": p.authorization_id, "decision": "approve", "reason_codes": []}
            self.committed[p.authorization_id] = body  # committed on the server...
            await asyncio.sleep(5)  # ...but the acknowledgement never arrives in time

    store, sender = CommitsThenStalls(), FakeSender()
    result = run(use_case(store=store, sender=sender).handle(request(deadline_in=1.2)))
    assert (result.path, result.verdict) == ("watchdog", "approve")
    assert sender.sent == [("AZ-1", store.committed["AZ-1"])]  # what we sent is what we stored
    assert store.fallbacks == {}


def test_a_hanging_send_is_bounded():
    class Hanging:
        async def send(self, aid, body):
            await asyncio.sleep(10)

    start = time.monotonic()
    result = run(use_case(sender=Hanging()).handle(request(deadline_in=1.5)))
    assert result.sent is False and time.monotonic() - start < 2.0


def test_mark_sent_failure_is_logged_not_raised():
    class Unmarkable(FakeStore):
        async def mark_sent(self, aid):
            raise ConnectionError("db gone")

    result = run(use_case(store=Unmarkable()).handle(request()))
    assert result.sent is True and result.path == "decided"


def test_a_lock_timeout_or_any_failure_of_the_work_is_answered_with_a_safe_step_up():
    from leash.adapters.postgres.unit_of_work import LockTimeout

    class Locked(FakeStore):
        async def decide(self, p, **kw):
            await asyncio.sleep(0.1)
            raise LockTimeout("card stayed locked")

    class BrokenReader:
        def read(self, p, budget):
            raise RuntimeError("reader crashed")

    for store, reader in ((Locked(), Reader()), (FakeStore(), BrokenReader())):
        sender = FakeSender()
        result = run(use_case(store=store, reader=reader, sender=sender).handle(request()))
        assert (result.path, result.verdict) == ("watchdog", "step_up")
        assert sender.sent and sender.sent[0][1]["decision"] == "step_up"
        assert store.fallbacks  # recorded, so a repeat delivery resends it instead of doing nothing


def test_a_hanging_dedupe_is_covered_by_the_watchdog():
    class SlowReceive(FakeStore):
        async def receive(self, p, **kw):
            await asyncio.sleep(5)

    sender = SentAt()
    start = time.monotonic()
    result = run(use_case(store=SlowReceive(), sender=sender).handle(request(deadline_in=1.5)))
    assert result.verdict == "step_up" and sender.at[0] - start < 1.5 - 0.1


def test_a_late_cleanup_failure_is_retrieved(caplog):
    class FailingCleanup(FakeStore):
        async def decide(self, p, **kw):
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                await asyncio.sleep(0.6)
                raise ValueError("rollback failed")

    async def go():
        await use_case(store=FailingCleanup()).handle(request(deadline_in=1.2))
        await asyncio.sleep(0.8)  # let the abandoned cleanup finish

    with caplog.at_level(logging.ERROR, logger="asyncio"):
        run(go())
    assert not any("never retrieved" in r.getMessage() for r in caplog.records)


def test_the_events_mandate_id_reaches_the_store_for_alerts():
    store = FakeStore()
    req = request()
    req = DecisionRequest(purchase=req.purchase, mandate=req.mandate, run_id="RUN1",
                          event={"mandate": {"mandate_id": "TM-9"}}, deadline_at=req.deadline_at,
                          platform_period_spend_chf=None)
    run(use_case(store=store).handle(req))
    assert store.mandate_ids == ["TM-9"]


def test_the_fallback_path_still_raises_the_unsupported_rule_alert(caplog):
    from leash.domain import mandate as mm
    from leash.domain.mandate import Rule as R

    caplog.set_level(logging.WARNING, logger="leash.decide")
    odd = mandate(R("leash.merchant.carbon_score.v1", "<=", Decimal("3")))
    run(use_case(reader=Hangs()).handle(request(deadline_in=1.2, m=odd)))
    alerts = [r for r in caplog.records if "unsupported mandate rule" in r.getMessage()]
    assert alerts and "leash.merchant.carbon_score.v1" in alerts[0].getMessage()
    assert mm  # keep import


# ----- durable claims (LEASH-131) -----

def test_the_claim_is_refreshed_while_the_decision_work_runs():
    store = FakeStore(decide_delay=0.35)
    result = run(use_case(store=store, claim_refresh_seconds=0.1).handle(request()))
    assert result.path == "decided" and len(store.__dict__.get("refreshes", [])) >= 2


def test_the_claim_is_released_once_the_answer_is_handled():
    store = FakeStore()
    run(use_case(store=store).handle(request()))
    assert store.__dict__.get("releases") == ["AZ-1"]


def test_the_claim_is_released_after_the_watchdog_answers():
    store = FakeStore(decide_delay=5)
    result = run(use_case(store=store).handle(request(deadline_in=1.2)))
    assert result.path == "watchdog" and store.__dict__.get("releases") == ["AZ-1"]


def test_the_claim_is_released_when_handling_is_cancelled_at_shutdown():
    store = FakeStore(decide_delay=5)

    async def go():
        task = asyncio.ensure_future(use_case(store=store).handle(request(deadline_in=6)))
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    run(go())
    assert store.__dict__.get("releases") == ["AZ-1"]  # a redelivery can take over at once


def test_work_in_flight_elsewhere_is_neither_refreshed_nor_released():
    answered = SavedAuthorization("AZ-1", "approved", "approve", {"decision": "approve"})
    store = FakeStore(saved=[IN_FLIGHT, answered])
    result = run(use_case(store=store, claim_refresh_seconds=0.01).handle(request()))
    assert result.path == "repeat"
    assert "refreshes" not in store.__dict__ and "releases" not in store.__dict__


def test_a_failing_refresh_never_stops_the_decision():
    store = FakeStore(decide_delay=0.2)
    store.refresh_fails = True
    result = run(use_case(store=store, claim_refresh_seconds=0.05).handle(request()))
    assert result.path == "decided" and result.sent


# --- LEASH-136: the send never outlives the deadline ------------------------------------------

def test_a_hanging_send_is_abandoned_before_the_deadline():
    """The POST timeout is capped by the time left, so a stalled platform cannot run past it."""

    class Hangs(FakeSender):
        async def send(self, authorization_id, body):
            await asyncio.sleep(30)

    plan = DeadlinePlan(send_seconds=5.0, lock_seconds=0.2, decide_seconds=0.2, fallback_seconds=0.2)
    start = time.monotonic()
    result = run(use_case(sender=Hangs(), plan=plan).handle(request(deadline_in=0.6)))
    elapsed = time.monotonic() - start
    # send_seconds (5 s) is longer than the deadline: the deadline wins, not the plan
    assert result.sent is False and elapsed < 1.0, elapsed
