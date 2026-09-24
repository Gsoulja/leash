"""Server-sent events for the app (LEASH-064), in the shapes of contracts/events.md.

The append-only decision_events table is the source: each row maps to contract events with increasing
integer IDs (a decision is 2·seq; its ask.created is 2·seq+1).

One EventHub per process follows the table and fans events out to every connected client, so a client
holds no database connection while it waits (connections are borrowed only for its initial snapshot and
replay). Sequence numbers are assigned at insert but become visible at commit, so the hub never moves its
cursor past a number that a still-running transaction may yet commit. Every writer holds an advisory lock
shared until it commits (repository._event); the hub reads the last number handed out, then briefly takes
that lock exclusively (bounded by a short lock_timeout, so writers are never held up for long). Once it
has it, everyone who may hold a number up to the one read has committed or rolled back, so everything up
to it is settled. Events therefore go out in ID order and none is skipped; unrelated transactions, in this
database or others, don't matter. A slow decision transaction delays the stream only until it ends.
A step_up's NOTIFY on `asks` wakes the hub at once; a short poll covers every other change.

On connect a client first gets the current open asks — without an `id:` line, so its resume point never
moves backwards — then everything after a valid `Last-Event-ID`, then live events. Shop text never appears
in events (the injection excerpt lives in check evidence, not in messages or reasons).

Spend mismatches stream as `spend_counter_mismatch`, and a reconciler disagreement about delivery as
`platform_delivery_mismatch` (LEASH-130). Anything else stays in decision_events and the server log.
"""

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import asyncpg
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import StreamingResponse

from leash.adapters.http.query_api import approval_check
from leash.adapters.postgres.repository import EVENTS_LOCK_KEY, purchase_from_json
from leash.application.resolve import MandateSource

log = logging.getLogger("leash.events")

Event = dict[str, Any]
_ROW_COLUMNS = """e.seq, e.kind, e.payload, e.at, e.authorization_id as event_authorization_id, a.authorization_id,
                  a.run_id, a.card_id, a.state, a.engine_verdict, a.checks, a.purchase, a.ask_expires_at"""
_EVENT_ID = re.compile(r"^[0-9]{1,18}$")  # ASCII digits that fit a bigint
QUEUE_LIMIT = 1000
BARRIER_TIMEOUT_MS = 100


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _money(value: Decimal | str | float) -> str:
    return f"{Decimal(str(value)).quantize(Decimal('0.01'))}"


def _wire(message_id: str | None, event: Event) -> str:
    head = f"id: {message_id}\n" if message_id is not None else ""
    return f"{head}event: {event['type']}\ndata: {json.dumps(event, separators=(',', ':'))}\n\n"


class EventHub:
    def __init__(self, pool: asyncpg.Pool, mandates: MandateSource, *, poll_seconds: float = 0.5) -> None:
        self._pool, self._mandates, self._poll = pool, mandates, poll_seconds
        self._subscribers: set[asyncio.Queue[tuple[int, Event] | None]] = set()
        self._settled = 0  # every seq ≤ this is visible or permanently gone, and has been emitted
        self._behind = False  # the last settle attempt timed out: retry soon
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._listener: asyncpg.Connection | None = None

    # --- lifecycle ---------------------------------------------------------------------------------

    async def start(self) -> None:
        self._listener = await self._pool.acquire()
        await self._listener.add_listener("asks", self._on_notify)
        async with self._pool.acquire() as conn:
            while not await self._settle(conn):  # settle what exists now; clients get it from the read model
                await asyncio.sleep(0.02)
        self._task = asyncio.ensure_future(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        if self._listener is not None:
            await self._listener.remove_listener("asks", self._on_notify)
            await self._pool.release(self._listener)
            self._listener = None
        for queue in list(self._subscribers):
            self._close(queue)

    def _on_notify(self, *_: Any) -> None:
        self._wake.set()

    @staticmethod
    def _close(queue: "asyncio.Queue[tuple[int, Event] | None]") -> None:
        while True:  # make room for the end marker
            try:
                queue.put_nowait(None)
                return
            except asyncio.QueueFull:
                queue.get_nowait()

    # --- following the table -----------------------------------------------------------------------

    async def _settle(self, conn: asyncpg.Connection) -> bool:
        """Advance the settled point to the last seq handed out, once no writer that may hold one is left."""
        row = await conn.fetchrow("select last_value, is_called from decision_events_seq_seq")
        handed_out = row["last_value"] if row["is_called"] else row["last_value"] - 1
        if handed_out <= self._settled:
            return True
        try:
            async with conn.transaction():
                await conn.execute(f"set local lock_timeout = {BARRIER_TIMEOUT_MS}")
                await conn.execute("select pg_advisory_xact_lock($1)", EVENTS_LOCK_KEY)  # released at commit
        except asyncpg.exceptions.LockNotAvailableError:
            return False  # a writer is still running; try again shortly
        self._settled = handed_out
        return True

    async def _run(self) -> None:
        emitted = self._settled
        while True:
            try:
                async with self._pool.acquire() as conn:
                    self._behind = not await self._settle(conn)
                    if self._settled > emitted:
                        for event_id, event in await self.events_between(conn, 2 * emitted + 1, self._settled,
                                                                         live=True):
                            self._publish(event_id, event)
                        emitted = self._settled
            except asyncio.CancelledError:
                raise
            except Exception:  # keep following; a transient database error must not end the stream
                log.exception("event hub poll failed")
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), 0.05 if self._behind else self._poll)
            except TimeoutError:
                pass

    def _publish(self, event_id: int, event: Event) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait((event_id, event))
            except asyncio.QueueFull:  # a stuck client: drop it; it reconnects and resumes with Last-Event-ID
                self._subscribers.discard(queue)
                self._close(queue)

    # --- building events ---------------------------------------------------------------------------

    async def _ask(self, conn: asyncpg.Connection, row: asyncpg.Record, event_id: str, at: datetime) -> Event:
        stored = json.loads(row["checks"]) if row["checks"] else {}
        purchase = purchase_from_json(json.loads(row["purchase"]))
        can_approve, _ = await approval_check(conn, self._pool, self._mandates, row)
        return {"id": event_id, "type": "ask.created", "at": _iso(at), "data": {
            "authorization_id": row["authorization_id"], "merchant_name": purchase.merchant.name,
            "billing_amount_chf": _money(purchase.billing_amount_chf),
            "reasons": [c["detail"] for c in stored.get("checks", []) if c["status"] in ("warn", "integrity")],
            "expires_at": _iso(row["ask_expires_at"]), "can_approve": can_approve}}

    async def _events(self, conn: asyncpg.Connection, row: asyncpg.Record, *, live: bool) -> list[tuple[int, Event]]:
        seq, kind, at = row["seq"], row["kind"], row["at"]
        payload = json.loads(row["payload"]) if row["payload"] else {}
        if row["authorization_id"] is None and kind != "integrity_alert":
            return []  # an event for a purchase we hold no record of: nothing the app can show
        if kind == "decided" and payload.get("verdict") in ("approve", "decline", "step_up"):
            verdict = payload["verdict"]
            stored = json.loads(row["checks"]) if row["checks"] else {}
            purchase = purchase_from_json(json.loads(row["purchase"]))
            out = [(2 * seq, {"id": str(2 * seq), "type": "payment.decided", "at": _iso(at), "data": {
                "authorization_id": row["authorization_id"], "engine_verdict": verdict,
                "final_state": {"approve": "approved", "decline": "declined", "step_up": "waiting"}[verdict],
                "billing_amount_chf": _money(purchase.billing_amount_chf),
                "customer_message": (stored.get("response") or {}).get("customer_message", "")}})]
            if verdict == "step_up" and row["ask_expires_at"] is not None:
                out.append((2 * seq + 1, await self._ask(conn, row, str(2 * seq + 1), at)))
            return out
        if kind in ("customer_resolved", "timed_out") and payload.get("state") in ("approved", "declined", "timed_out"):
            return [(2 * seq, {"id": str(2 * seq), "type": "ask.resolved", "at": _iso(at), "data": {
                "authorization_id": row["authorization_id"], "outcome": payload["state"],
                "resolved_by": "customer" if kind == "customer_resolved" else "platform"}})]
        if kind == "delivered" and payload.get("delivery") in ("accepted", "refused"):
            # A decision already made; only its fate at the platform is new. The app reloads its read
            # model on this, which is how a refusal stops showing as an approval without a page refresh.
            return [(2 * seq, {"id": str(2 * seq), "type": "payment.delivered", "at": _iso(at), "data": {
                "authorization_id": row["authorization_id"], "delivery": payload["delivery"],
                "platform_outcome": payload.get("platform_outcome"),
                "final_state": payload.get("state") or row["state"]}})]
        if kind == "integrity_alert" and payload.get("kind") == "unsupported_mandate_rule":
            fields = ", ".join(payload.get("fields", []))
            mandate = payload.get("mandate_id") or "unknown mandate"
            return [(2 * seq, {"id": str(2 * seq), "type": "integrity.alert", "at": _iso(at), "data": {
                "kind": "unsupported_mandate_rule", "run_id": row["run_id"],
                "detail": f"Mandate {mandate} has rules the engine can't check: {fields} "
                          f"(engine {payload.get('engine_version', '?')}); the engine never approves such purchases on its own."}})]
        if kind == "integrity_alert":
            spend = [m for m in payload.get("mismatches", []) if m.startswith("approved spend")]
            others = [m for m in payload.get("mismatches", []) if not m.startswith("approved spend")]
            if others and live:
                log.warning("integrity mismatches not streamed (no contract kind): %s", others,
                            extra={"authorization_id": row["event_authorization_id"]})
            if spend:
                return [(2 * seq, {"id": str(2 * seq), "type": "integrity.alert", "at": _iso(at), "data": {
                    "kind": "spend_counter_mismatch", "run_id": row["run_id"], "detail": "; ".join(spend)}})]
            if others and payload.get("source") == "reconcile":
                # Our record and the platform's disagree about something already settled (LEASH-130).
                # Nothing was changed; a person has to look, so it reaches the screen rather than only
                # the log.
                return [(2 * seq, {"id": str(2 * seq), "type": "integrity.alert", "at": _iso(at), "data": {
                    "kind": "platform_delivery_mismatch", "run_id": row["run_id"],
                    "detail": "; ".join(others)}})]
        return []

    async def events_between(self, conn: asyncpg.Connection, after_id: int, upto_seq: int, *,
                             live: bool = False) -> list[tuple[int, Event]]:
        """Events with id > after_id from settled rows up to upto_seq, in ID order."""
        rows = await conn.fetch(
            f"""select {_ROW_COLUMNS} from decision_events e
                left join authorizations a on a.authorization_id = e.authorization_id
                where e.seq >= $1 and e.seq <= $2 order by e.seq""", after_id // 2, upto_seq)
        out = []
        for r in rows:
            out += [(i, e) for i, e in await self._events(conn, r, live=live) if i > after_id]
        return out

    async def open_asks(self, conn: asyncpg.Connection) -> list[Event]:
        rows = await conn.fetch(
            f"""select distinct on (a.authorization_id) {_ROW_COLUMNS}
                from authorizations a join decision_events e on e.authorization_id = a.authorization_id
                where a.state = 'waiting' and a.ask_expires_at > now() and e.kind = 'decided'
                order by a.authorization_id, e.seq""")
        asks = [await self._ask(conn, r, str(2 * r["seq"] + 1), r["at"]) for r in rows]
        return sorted(asks, key=lambda e: int(e["id"]))

    # --- one client --------------------------------------------------------------------------------

    async def stream(self, *, last_event_id: str | None,
                     stop: asyncio.Event) -> AsyncIterator[tuple[str | None, Event]]:
        """Yields (message id, or None for a snapshot ask; event) until `stop` is set."""
        queue: asyncio.Queue[tuple[int, Event] | None] = asyncio.Queue(QUEUE_LIMIT)
        self._subscribers.add(queue)  # first: nothing published from now on can be missed
        try:
            upto = self._settled
            resume = int(last_event_id) if last_event_id and _EVENT_ID.match(last_event_id) else None
            if resume is not None and resume > 2 * upto + 1:
                resume = None  # an ID from the future (e.g. an older database): treat as a fresh connect
            sent = 2 * upto + 1
            async with self._pool.acquire() as conn:
                snapshot = await self.open_asks(conn)
                replay = await self.events_between(conn, resume, upto) if resume is not None else []
            for ask in snapshot:
                yield None, ask
            for event_id, event in replay:
                yield str(event_id), event
            while not stop.is_set():
                getter = asyncio.ensure_future(queue.get())
                stopper = asyncio.ensure_future(stop.wait())
                try:
                    done, _ = await asyncio.wait({getter, stopper}, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    stopper.cancel()
                    if not getter.done():
                        getter.cancel()
                if getter not in done:
                    return
                item = getter.result()
                if item is None:
                    return  # dropped (too slow) or the hub stopped: the client reconnects and resumes
                event_id, event = item
                if event_id > sent:
                    sent = event_id
                    yield str(event_id), event
        finally:
            self._subscribers.discard(queue)  # synchronous: a cancelled client can never leak anything


def events_router(hub: Callable[[], EventHub]) -> APIRouter:
    router = APIRouter()

    @router.get("/api/events")
    async def events(request: Request) -> StreamingResponse:
        stop = asyncio.Event()

        async def watch_disconnect() -> None:
            while not stop.is_set():
                if await request.is_disconnected():
                    stop.set()
                    return
                await asyncio.sleep(0.5)

        async def body() -> AsyncIterator[str]:
            watcher = asyncio.ensure_future(watch_disconnect())
            try:
                async for message_id, event in hub().stream(last_event_id=request.headers.get("last-event-id"),
                                                            stop=stop):
                    yield _wire(message_id, event)
            finally:
                stop.set()
                watcher.cancel()

        return StreamingResponse(body(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return router


def create_events_app(database_url: str, mandates: MandateSource, *, poll_seconds: float = 0.5) -> FastAPI:
    state: dict[str, Any] = {}

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        state["pool"] = await asyncpg.create_pool(database_url, min_size=2, max_size=8)
        state["hub"] = EventHub(state["pool"], mandates, poll_seconds=poll_seconds)
        await state["hub"].start()
        try:
            yield
        finally:
            await state["hub"].stop()
            await state["pool"].close()

    app = FastAPI(title="Leash event stream", lifespan=lifespan)
    app.include_router(events_router(lambda: state["hub"]))
    return app
