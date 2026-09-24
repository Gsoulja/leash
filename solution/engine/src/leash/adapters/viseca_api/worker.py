"""The long-poll worker (LEASH-053, DEC-007): the part the hosted simulator talks to.

Loop: poll /v1/decision-requests/next. A 200 envelope becomes a request through `request_from_envelope`
(the same path the offline slice proves) and is decided by DecidePurchase, which POSTs the answer right
after the commit and leaves the outbox for recovery only. A 204 checks the run's progress and polls again.
A step_up is answered and left to the customer: nothing here waits for a person, so asks never block.
Poll errors are logged and retried with exponential backoff. `stop()` ends the loop between events: a
poll in progress is abandoned, an event being handled is finished first (even if the task is cancelled).

Run it with `uv run leash-worker` (see `main`).
"""

import asyncio
import logging
import os
import signal
import time
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from leash.adapters.viseca_api.translate import InvalidEvent, invalid_event_response, request_from_envelope
from leash.application.decide_purchase import DecisionRequest

log = logging.getLogger("leash.worker")

POLL_WAIT_SECONDS = 25
BASE_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 30.0
_RUN_OVER = frozenset({"completed", "stopped", "finished", "failed", "cancelled", "canceled", "expired"})

Validate = Callable[[Mapping[str, Any]], None]


class WorkerApi(Protocol):
    async def next_decision_request(self, wait: int = POLL_WAIT_SECONDS) -> Any: ...

    async def get_run(self, run_id: str) -> Any: ...

    async def post_decision(self, authorization_id: str, decision: Mapping[str, Any],
                            budget_seconds: float | None = None) -> Any: ...


class Handler(Protocol):
    def handle(self, request: DecisionRequest) -> Awaitable[Any]: ...


class ApiSender:
    """DecidePurchase's Sender: POST /v1/authorizations/{id}/decision.

    `send` takes the remaining seconds, which bounds every phase of the POST inside httpx as well
    (LEASH-136), so no send outlives the authoritative deadline.
    """

    def __init__(self, api: WorkerApi) -> None:
        self._api = api

    async def send(self, authorization_id: str, body: Mapping[str, Any],
                   budget_seconds: float | None = None) -> None:
        await self._api.post_decision(authorization_id, body, budget_seconds)


def _run_over(body: Any) -> bool:
    data = body.get("data", body) if isinstance(body, Mapping) else None
    if not isinstance(data, Mapping):
        return False
    status = data.get("status")
    counters = data.get("counters")
    remaining = counters.get("remaining") if isinstance(counters, Mapping) else None
    return (isinstance(status, str) and status.lower() in _RUN_OVER) or remaining == 0


class Worker:
    def __init__(self, api: WorkerApi, use_case: Handler, *, validate: Validate | None = None,
                 engine_version: str = "leash", poll_wait: int = POLL_WAIT_SECONDS,
                 base_backoff_seconds: float = BASE_BACKOFF_SECONDS, max_backoff_seconds: float = MAX_BACKOFF_SECONDS,
                 sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._api, self._use_case, self._validate = api, use_case, validate
        self._engine_version, self._poll_wait = engine_version, poll_wait
        self._base, self._max, self._sleep = base_backoff_seconds, max_backoff_seconds, sleep
        self._stopping = asyncio.Event()
        self._failures = 0
        self._clock = clock
        self.last_poll_ok_at: float | None = None  # monotonic time of the last poll that reached the platform

    def stop(self) -> None:
        """Finish the current event, then return from run()."""
        self._stopping.set()

    async def run(self, *, run_id: str | None = None) -> None:
        """Poll until stop() — or, given a run ID, until the platform reports that run over."""
        while not self._stopping.is_set():
            got, envelope = await self._poll()
            if not got:
                if self._stopping.is_set():
                    return
                continue
            if envelope is None:  # 204: not "finished", only "nothing right now"
                if run_id is not None and await self._run_is_over(run_id):
                    log.info("run %s is over; worker stops", run_id)
                    return
                continue
            current = asyncio.ensure_future(self._handle(envelope))
            try:
                await asyncio.shield(current)
            except asyncio.CancelledError:  # finish the event in hand before giving up
                await asyncio.wait({current})
                raise

    async def _poll(self) -> tuple[bool, Any]:
        """(True, envelope or None for 204), or (False, None) after an error or on stop."""
        poll = asyncio.ensure_future(self._api.next_decision_request(wait=self._poll_wait))
        stopping = asyncio.ensure_future(self._stopping.wait())
        try:
            await asyncio.wait({poll, stopping}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            stopping.cancel()
        if not poll.done():  # stop() while waiting: nothing was received, so nothing is left half-done
            poll.cancel()
            await asyncio.wait({poll})
            return False, None
        try:
            envelope = poll.result()
        except Exception as exc:
            await self._backoff("poll failed", exc)
            return False, None
        self._failures = 0
        self.last_poll_ok_at = self._clock()
        return True, envelope

    async def _backoff(self, what: str, exc: BaseException) -> None:
        delay = min(self._max, self._base * 2 ** self._failures)
        self._failures += 1
        log.warning("%s (%s: %s); retrying in %.1f s", what, type(exc).__name__, exc, delay)
        waiting = asyncio.ensure_future(self._sleep(delay))
        stopping = asyncio.ensure_future(self._stopping.wait())
        try:  # stop() ends the wait: no event is in hand during a backoff
            await asyncio.wait({waiting, stopping}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            waiting.cancel()
            stopping.cancel()

    async def _run_is_over(self, run_id: str) -> bool:
        try:
            progress = await self._api.get_run(run_id)
        except Exception as exc:
            await self._backoff("run progress check failed", exc)
            return False
        return _run_over(progress)

    async def _handle(self, envelope: Any) -> None:
        try:
            request, translated = request_from_envelope(envelope, validate=self._validate)
        except InvalidEvent as exc:
            await self._answer_invalid(exc)
            return
        aid = request.purchase.authorization_id
        for alert in translated.integrity:
            log.warning("INTEGRITY: %s", alert, extra={"authorization_id": aid})
        try:
            result = await self._use_case.handle(request)
        except Exception:  # DecidePurchase answers safely itself; this is a last resort so the loop goes on
            log.exception("handling failed", extra={"authorization_id": aid})
            return
        log.info("handled %s: %s, verdict %s", aid, getattr(result, "path", "done"), getattr(result, "verdict", None),
                 extra={"authorization_id": aid})

    async def _answer_invalid(self, exc: InvalidEvent) -> None:
        if exc.authorization_id is None:
            log.error("unreadable event without a live ID; nothing can be answered: %s", exc)
            return
        body = invalid_event_response(exc.authorization_id, str(exc), engine_version=self._engine_version)
        log.error("unreadable event, answering step_up: %s", exc, extra={"authorization_id": exc.authorization_id})
        try:
            await self._api.post_decision(exc.authorization_id, body)
        except Exception as send_error:  # nothing about one unreadable event may end the loop
            log.error("could not send the invalid_event answer: %s", send_error,
                      extra={"authorization_id": exc.authorization_id})


def health_app(worker: Worker, *, stale_seconds: float = POLL_WAIT_SECONDS * 2 + 10) -> Any:
    """/healthz: the process is alive. /readyz: a poll reached the platform recently."""
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI(title="Leash worker health")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> Any:
        last = worker.last_poll_ok_at
        if last is None or worker._clock() - last > stale_seconds:
            return JSONResponse({"status": "not_ready", "reasons": ["no successful poll recently"]}, status_code=503)
        return {"status": "ready"}

    return app


# ----- process entry point -----------------------------------------------------------------------------

async def _serve(run_id: str | None) -> None:  # pragma: no cover - wiring, exercised by the end-to-end test
    import asyncpg

    from leash.adapters.postgres.unit_of_work import DEFAULT_LEASE_SECONDS, DEFAULT_LOCK_TIMEOUT_MS, PostgresDecisionStore
    from leash.adapters.regex_reader import RegexReader
    from leash.adapters.viseca_api.event_schema import load_event_validator
    from leash.adapters.viseca_api.outbox_sender import OutboxSender
    from leash.application.decide_purchase import DeadlinePlan, DecidePurchase
    from leash.config import Settings, install_redaction, load_runtime, platform_client

    settings = Settings.from_env(os.environ)
    install_redaction(settings)
    client = platform_client(settings)  # this process owns the pool and closes it below (LEASH-136)
    runtime = await load_runtime(settings, client)
    schema = Path(os.environ.get("LEASH_EVENT_SCHEMA", "../../data/schemas/authorization_event.schema.json"))
    version = f"leash-{runtime.api_version}"
    pool = await asyncpg.create_pool(settings.database_url.get_secret_value(), min_size=1, max_size=8)
    try:  # the HTTP pool is closed with the database pool: one create, one close per process (LEASH-136)
        store = PostgresDecisionStore(pool, engine_version=version, lock_timeout_ms=DEFAULT_LOCK_TIMEOUT_MS)
        plan = DeadlinePlan.for_lock_timeout(lock_timeout_ms=DEFAULT_LOCK_TIMEOUT_MS,
                                             send_seconds=settings.watchdog_margin_seconds / 2)
        use_case = DecidePurchase(store=store, reader=RegexReader(), sender=ApiSender(client), plan=plan,
                                  engine_version=version, human_window_seconds=runtime.human_window_seconds,
                                  claim_refresh_seconds=DEFAULT_LEASE_SECONDS / 3)
        worker = Worker(client, use_case, validate=load_event_validator(schema), engine_version=version)
        outbox = OutboxSender(pool, client)

        async def recover() -> None:  # the outbox is for recovery only: rows the worker could not send
            while True:
                try:
                    await outbox.send_pending()
                except Exception:
                    log.exception("outbox pass failed")
                await asyncio.sleep(2)

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, worker.stop)
        import uvicorn

        health = uvicorn.Server(uvicorn.Config(health_app(worker), host="0.0.0.0", log_config=None,
                                               port=int(os.environ.get("LEASH_WORKER_HEALTH_PORT", "8081"))))
        # uvicorn captures SIGINT/SIGTERM while serving and replays them to our handlers (worker.stop) on exit
        serving = asyncio.ensure_future(health.serve())
        recovery = asyncio.ensure_future(recover())
        try:
            await worker.run(run_id=run_id)
        finally:
            recovery.cancel()
            health.should_exit = True
            await outbox.send_pending()
            await serving
    finally:
        await pool.close()
        await client.aclose()


def main() -> None:  # pragma: no cover - process entry point
    from leash.config import configure_logging

    configure_logging(os.environ.get("LEASH_LOG_LEVEL", "INFO"))
    asyncio.run(_serve(os.environ.get("LEASH_RUN_ID") or None))
