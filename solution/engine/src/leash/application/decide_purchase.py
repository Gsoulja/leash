"""Decide one purchase before its deadline (DEC-007, DEC-008).

validate → dedupe → read facts (outside the lock) → lock → rebuild snapshot → decide → save with outbox
→ commit → POST immediately → mark sent. Decisions always use the mandate carried by the event.

The watchdog covers everything from dedupe up to the commit, and any failure there (a lock timeout, a
crashed reader or store) takes the same safe path. It fires at `deadline − (fallback + send)`: the stalled
work is cancelled without waiting for its cleanup, and a safe step_up is recorded — bounded in time, and
conditional in the store, so it only takes effect if no decision committed. If a commit landed first, that
committed decision is sent instead, so what is sent always matches what is stored. The fact reader's own
budget ends earlier still, leaving room for the lock wait, deciding and saving, and sending.

Claims (LEASH-131): `receive` returning None means this worker now owns the decision work under a short lease.
The lease is refreshed while the work runs and released once the answer is handled, or when handling is
cancelled, so a redelivery can take over at once. A delivery that finds the work claimed by someone else
doesn't give up: a missing answer is not proof the owner is alive, so it keeps checking until the owner's
answer is stored (and sends it) or the lease lapses (and takes the work over), with the watchdog as the
bound. If this worker dies instead, the lease runs out and a redelivery takes the work over; a stale owner that wakes up later can't commit (the stored state has moved on)
and sends the stored decision instead. The recovery path for each crash point is in RUNBOOK.md.
"""

import asyncio
import logging
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Protocol

from leash.domain.checks import Check
from leash.domain.clock import WallTime
from leash.domain.decide import Decision
from leash.domain.explain import explain
from leash.domain.facts import Facts
from leash.domain.mandate import CompiledMandate
from leash.domain.purchase import Purchase
from leash.ports.fact_reader import FactReader
from leash.ports.repository import SavedAuthorization

log = logging.getLogger("leash.decide")

TIMEOUT_CODE = "decision_timeout"
#: A live ID redelivered with a different amount, shop or basket (LEASH-102).
CHANGED_TERMS_CODE = "checkout_terms_changed"


@dataclass(frozen=True)
class DeadlinePlan:
    """How the time before `deadline_at` is split. All values in seconds."""

    send_seconds: float  # POSTing the answer
    lock_seconds: float  # the longest wait for the card lock (= lock_timeout)
    decide_seconds: float  # snapshot + decide + save + commit
    fallback_seconds: float  # recording the watchdog's step_up (waits out a stalled decision's row lock)

    @classmethod
    def for_lock_timeout(cls, *, lock_timeout_ms: int, send_seconds: float, decide_seconds: float = 0.5,
                         fallback_seconds: float | None = None) -> "DeadlinePlan":
        lock = lock_timeout_ms / 1000
        return cls(send_seconds=send_seconds, lock_seconds=lock, decide_seconds=decide_seconds,
                   fallback_seconds=lock if fallback_seconds is None else fallback_seconds)

    @property
    def watchdog_margin(self) -> timedelta:
        """The watchdog fires this long before the deadline: time to record the safe answer and send it."""
        return timedelta(seconds=self.fallback_seconds + self.send_seconds)

    @property
    def reader_margin(self) -> timedelta:
        """Fact reading must end this long before the deadline: lock wait, decide/save and send still follow."""
        return timedelta(seconds=self.send_seconds + self.lock_seconds + self.decide_seconds)


@dataclass(frozen=True)
class DecisionRequest:
    purchase: Purchase
    mandate: CompiledMandate  # compiled from the event's own mandate snapshot (DEC-003)
    run_id: str | None
    event: Mapping[str, Any]
    deadline_at: WallTime
    platform_period_spend_chf: Decimal | None


@dataclass
class HandleResult:
    path: str  # decided | repeat | watchdog | late
    verdict: str | None
    response: Mapping[str, Any] | None
    stages: list[tuple[str, float]] = field(default_factory=list)
    sent: bool = False


class Outcome(Protocol):
    @property
    def decision(self) -> Decision: ...

    @property
    def response(self) -> dict[str, Any]: ...

    @property
    def stages(self) -> list[tuple[str, float]]: ...


class DecisionStore(Protocol):
    async def receive(self, purchase: Purchase, *, run_id: str | None, event: Mapping[str, Any],
                      received_at: datetime, deadline_at: datetime) -> SavedAuthorization | None: ...

    async def decide(self, purchase: Purchase, *, run_id: str | None, mandate: CompiledMandate, facts: Facts,
                     platform_period_spend_chf: Decimal | None,
                     ask_expires_at: datetime | None = None, mandate_id: str | None = None) -> Outcome: ...

    async def record_fallback(self, purchase: Purchase, *, run_id: str | None, response: Mapping[str, Any],
                              ask_expires_at: datetime) -> SavedAuthorization | None:
        """Record the watchdog's step_up only if no decision committed (received → waiting); otherwise
        return what did commit. Must wait for a stalled decision's row lock, so it tells the truth."""
        ...

    async def mark_sent(self, authorization_id: str) -> None: ...

    async def refresh_claim(self, authorization_id: str) -> bool:
        """Extend this worker's lease on undecided work; False when the claim is no longer ours."""
        ...

    async def release_claim(self, authorization_id: str) -> None:
        """Give up this worker's claim, so unanswered work can be taken over at once."""
        ...


class Sender(Protocol):
    async def send(self, authorization_id: str, body: Mapping[str, Any],
                   budget_seconds: float | None = None) -> None: ...
    """`budget_seconds` is the time actually left before `deadline_at`.

    It is part of the port rather than something the adapter is configured with once, so a sender that
    ignores it is a type error rather than a silent wait past the deadline. `None` means "no deadline to
    measure against" — the outbox's post-deadline recovery path (DEC-007/LEASH-054).
    """


class _Budget:
    def __init__(self, until: float) -> None:
        self._until = until  # time.monotonic() value

    def remaining_seconds(self) -> float:
        return self._until - time.monotonic()


def _mandate_id(event: Mapping[str, Any]) -> str | None:
    mandate = event.get("mandate")
    value = mandate.get("mandate_id") if isinstance(mandate, Mapping) else None
    return value if isinstance(value, str) else None


def _changed_terms_decision() -> Decision:
    check = Check("terms", "Checkout terms", "integrity", "The terms I checked", "Different terms now",
                  "This purchase came back with different terms than the ones I checked, so I'm asking you.",
                  CHANGED_TERMS_CODE)
    return Decision("step_up", (check,), (CHANGED_TERMS_CODE,))


def _timeout_decision() -> Decision:
    check = Check("deadline", "Answer time", "integrity", "Checked before the deadline", "Ran out of time",
                  "I couldn't finish checking this purchase in time, so I'm asking you.", TIMEOUT_CODE)
    return Decision("step_up", (check,), (TIMEOUT_CODE,))


@dataclass
class _Claim:
    held: bool = False


class DecidePurchase:
    def __init__(self, *, store: DecisionStore, reader: FactReader, sender: Sender, plan: DeadlinePlan,
                 engine_version: str, human_window_seconds: float, claim_refresh_seconds: float = 1.0,
                 in_flight_poll_seconds: float = 0.2) -> None:
        self._store, self._reader, self._sender, self._plan = store, reader, sender, plan
        self._engine_version = engine_version
        self._human_window = timedelta(seconds=human_window_seconds)
        self._claim_refresh = claim_refresh_seconds
        self._in_flight_poll = in_flight_poll_seconds

    async def handle(self, request: DecisionRequest) -> HandleResult:
        claim = _Claim()
        try:
            return await self._handle(request, claim)
        finally:
            if claim.held:
                await self._release(request.purchase.authorization_id)

    async def _release(self, aid: str) -> None:
        try:
            await asyncio.wait_for(self._store.release_claim(aid), timeout=self._plan.send_seconds)
        except Exception:  # the lease runs out by itself; a redelivery then takes the work over
            log.warning("could not release the claim; it expires by itself", exc_info=True,
                        extra={"authorization_id": aid})

    async def _keep_claim(self, aid: str) -> None:
        while True:
            await asyncio.sleep(self._claim_refresh)
            try:
                if not await self._store.refresh_claim(aid):
                    log.warning("lost the claim: another worker took the work over", extra={"authorization_id": aid})
                    return
            except Exception:  # a missed refresh only risks a redundant takeover, never a double commit
                log.warning("could not refresh the claim", exc_info=True, extra={"authorization_id": aid})

    async def _handle(self, request: DecisionRequest, claim: _Claim) -> HandleResult:
        aid = request.purchase.authorization_id
        result = HandleResult(path="decided", verdict=None, response=None)
        timer = _StageTimer(aid, result.stages)

        now = datetime.now(timezone.utc)
        if now >= request.deadline_at.at:
            timer.done("validate")
            log.warning("deadline already passed; not deciding", extra={"authorization_id": aid})
            result.path = "late"
            return result
        timer.done("validate")

        watchdog_in = (request.deadline_at.at - self._plan.watchdog_margin - datetime.now(timezone.utc)).total_seconds()
        work = asyncio.ensure_future(self._receive_and_decide(request, timer, claim))
        try:
            done, _ = await asyncio.wait({work}, timeout=max(0.0, watchdog_in))
        except asyncio.CancelledError:  # shutdown: stop the work too, so the released claim is really free
            work.cancel()
            raise
        if not done:
            work.cancel()  # rolls the transaction back; its cleanup is not waited for before answering
            try:
                return await self._fallback(request, result, timer)
            finally:
                await asyncio.wait({work}, timeout=self._plan.fallback_seconds)
                work.add_done_callback(_retrieve)  # an abandoned failure is never reported as unhandled
        if work.exception() is not None:  # e.g. LockTimeout, a crashed reader or store: answer safely
            log.warning("deciding failed (%s); sending a safe step_up", type(work.exception()).__name__,
                        exc_info=work.exception(), extra={"authorization_id": aid})
            return await self._fallback(request, result, timer)
        kind, payload = work.result()
        if kind == "repeat":
            assert isinstance(payload, SavedAuthorization) and payload.response is not None
            if payload.changed_terms:
                return await self._changed_terms(request, payload, result, timer)
            result.path, result.verdict, result.response = "repeat", payload.engine_verdict, payload.response
            await self._send(request, payload.response, result, timer)
            return result
        outcome = payload
        assert not isinstance(outcome, SavedAuthorization) and outcome is not None
        result.verdict, result.response = outcome.decision.verdict, outcome.response
        await self._send(request, outcome.response, result, timer)
        return result

    async def _receive_and_decide(self, request: DecisionRequest, timer: "_StageTimer", claim: _Claim) \
            -> tuple[str, "Outcome | SavedAuthorization | None"]:
        now = datetime.now(timezone.utc)
        saved = await self._store.receive(request.purchase, run_id=request.run_id, event=request.event,
                                          received_at=now, deadline_at=request.deadline_at.at)
        timer.done("dedupe")
        while saved is not None and saved.response is None:  # claimed elsewhere: wait for its answer or its lapse
            await asyncio.sleep(self._in_flight_poll)
            saved = await self._store.receive(request.purchase, run_id=request.run_id, event=request.event,
                                              received_at=now, deadline_at=request.deadline_at.at)
        if saved is not None:
            return "repeat", saved
        claim.held = True
        beat = asyncio.ensure_future(self._keep_claim(request.purchase.authorization_id))
        try:
            return "decided", await self._decide(request, timer)
        finally:
            beat.cancel()

    async def _decide(self, request: DecisionRequest, timer: "_StageTimer") -> Outcome:
        reader_until = time.monotonic() + (
            request.deadline_at.at - self._plan.reader_margin - datetime.now(timezone.utc)).total_seconds()
        facts = await _in_daemon_thread(self._reader.read, request.purchase, _Budget(reader_until))
        timer.done("read_facts")
        outcome = await self._store.decide(
            request.purchase, run_id=request.run_id, mandate=request.mandate, facts=facts,
            platform_period_spend_chf=request.platform_period_spend_chf,
            ask_expires_at=datetime.now(timezone.utc) + self._human_window,
            mandate_id=_mandate_id(request.event))
        timer.inner(outcome.stages)
        timer.done("transaction")
        return outcome

    async def _changed_terms(self, request: DecisionRequest, saved: SavedAuthorization, result: HandleResult,
                             timer: "_StageTimer") -> HandleResult:
        """This live ID has been decided already, but not on the terms just delivered (LEASH-102).

        The saved verdict stays the record of what was decided and is not rewritten (DEC-003); it is
        simply not an answer to this delivery. Re-deciding under the same ID would put a second verdict
        on one authorization, so the honest answer is the safe one: ask the customer.
        """
        aid = request.purchase.authorization_id
        for change in saved.changed_terms:
            log.warning("INTEGRITY: the same authorization was redelivered with different terms (%s); "
                        "the saved %s is not being replayed", change, saved.engine_verdict,
                        extra={"authorization_id": aid})
        body = explain(_changed_terms_decision(), authorization_id=aid,
                       engine_version=self._engine_version)
        body["evidence"] = [*body["evidence"],
                            *({"check": "terms", "label": "Changed checkout terms", "status": "integrity",
                               "agreed": "The terms this purchase was decided on", "actual": change[:300],
                               "reason_code": CHANGED_TERMS_CODE} for change in saved.changed_terms)]
        result.path, result.verdict, result.response = "changed_terms", "step_up", body
        await self._send(request, body, result, timer)
        return result

    async def _fallback(self, request: DecisionRequest, result: HandleResult, timer: "_StageTimer") -> HandleResult:
        timer.done("watchdog")
        aid = request.purchase.authorization_id
        unsupported = [r.field for r in request.mandate.unsupported_rules()]
        if unsupported:  # the transaction didn't run, so raise the operational alert here (DEC-005)
            log.warning("unsupported mandate rule(s) %s in mandate %s (engine %s)", unsupported,
                        _mandate_id(request.event), self._engine_version, extra={"authorization_id": aid})
        log.warning("watchdog fired: sending a safe step_up", extra={"authorization_id": aid})
        body: Mapping[str, Any] = explain(_timeout_decision(), authorization_id=aid, engine_version=self._engine_version)
        verdict: str | None = "step_up"
        try:
            committed = await asyncio.wait_for(
                self._store.record_fallback(request.purchase, run_id=request.run_id, response=body,
                                            ask_expires_at=datetime.now(timezone.utc) + self._human_window),
                timeout=self._plan.fallback_seconds)
            if committed is not None and committed.response is not None:
                body, verdict = committed.response, committed.engine_verdict  # the commit landed first
        except Exception:  # the answer matters more than the record: send the safe step_up regardless
            log.error("INTEGRITY: the watchdog step_up could not be recorded; the stored state may differ",
                      exc_info=True, extra={"authorization_id": aid})
        timer.done("record_fallback")
        result.path, result.verdict, result.response = "watchdog", verdict, body
        await self._send(request, body, result, timer)
        return result

    async def _send(self, request: DecisionRequest, body: Mapping[str, Any], result: HandleResult,
                    timer: "_StageTimer") -> None:
        aid = request.purchase.authorization_id
        left = (request.deadline_at.at - datetime.now(timezone.utc)).total_seconds()
        if left <= 0:
            # Nothing to gain by starting: the platform refuses an answer after `deadline_at`, and
            # holding the connection open cannot change that. The outbox delivers it (LEASH-054).
            timer.done("send")
            log.warning("no time left to send before the deadline; leaving it to the outbox",
                        extra={"authorization_id": aid})
            return
        # Capped by the time left, never extended past it: `deadline_at` is authoritative. The same
        # number goes to the sender, so connect, read, write and the pool wait are bounded inside httpx
        # too — the `wait_for` is the outer guard, not the only one.
        budget = max(0.0, min(self._plan.send_seconds, left))
        try:
            await asyncio.wait_for(self._sender.send(aid, body, budget), timeout=budget)
        except Exception:  # left unmarked: the outbox resends it (LEASH-054)
            timer.done("send")
            log.exception("sending the decision failed; the outbox will retry", extra={"authorization_id": aid})
            return
        timer.done("send")
        result.sent = True
        try:
            await self._store.mark_sent(aid)
        except Exception:  # sent but not marked: the outbox resends the same body, which is harmless
            log.exception("could not mark the decision sent", extra={"authorization_id": aid})
        timer.done("mark_sent")


class _StageTimer:
    def __init__(self, authorization_id: str, stages: list[tuple[str, float]]) -> None:
        self._aid, self._stages, self._last = authorization_id, stages, time.perf_counter()

    def done(self, stage: str) -> None:
        now = time.perf_counter()
        self._record(stage, (now - self._last) * 1000)
        self._last = now

    def inner(self, stages: list[tuple[str, float]]) -> None:
        for stage, ms in stages:
            self._record(stage, ms)

    def _record(self, stage: str, ms: float) -> None:
        self._stages.append((stage, ms))
        log.info("stage %s took %.1f ms", stage, ms, extra={"authorization_id": self._aid, "stage": stage, "ms": ms})


def _retrieve(task: "asyncio.Future[Any]") -> None:
    if not task.cancelled() and task.exception() is not None:
        log.warning("abandoned decision work failed during cleanup: %r", task.exception())


async def _in_daemon_thread(fn: Any, *args: Any) -> Facts:
    """Run a blocking reader without tying up the event loop or blocking shutdown if it hangs."""
    loop = asyncio.get_running_loop()
    future: asyncio.Future[Facts] = loop.create_future()

    def settle(ok: bool, value: Any) -> None:
        if not future.done():
            (future.set_result if ok else future.set_exception)(value)

    def run() -> None:
        try:
            outcome: tuple[bool, Any] = (True, fn(*args))
        except BaseException as exc:  # noqa: BLE001 - handed to the awaiting coroutine
            outcome = (False, exc)
        try:
            loop.call_soon_threadsafe(settle, *outcome)
        except RuntimeError:  # the loop is gone: nobody is waiting for this (abandoned) read any more
            pass

    threading.Thread(target=run, name="fact-reader", daemon=True).start()
    return await future
