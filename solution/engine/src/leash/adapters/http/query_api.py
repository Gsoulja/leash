"""Durable read endpoints for the app (LEASH-124), in the shapes of contracts/policy-api.yaml.

The app loads all current state from here on (re)connect; the event stream (LEASH-064) only carries
changes. Engine verdict and final outcome are separate fields. Spending is computed from the same ledger
the engine decides with. An ask's `can_approve` re-checks the hard rules now (DEC-012), exactly as an
approval would, so the app never offers an approval the engine would refuse.

`GET /api/mandates` (the plain-language rule view) comes with the mandate service (LEASH-060/061).
"""

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import asyncpg
from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse

from leash.policy.render import permission_review
from leash.policy.hard_rules import rule_from_api
from leash.adapters.postgres.repository import PostgresRepository, purchase_from_json
from leash.application.resolve import MandateSource
from leash.domain.clock import SimTime
from leash.domain.decide import decide
from leash.domain.facts import Facts

Clock = Callable[[], datetime]


def _money(value: Decimal | str | float) -> str:
    return f"{Decimal(str(value)).quantize(Decimal('0.01'))}"


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _not_found(what: str) -> JSONResponse:
    return JSONResponse({"error": {"code": "not_found", "message": f"no such {what}"}}, status_code=404)


def payment_view(row: asyncpg.Record) -> dict[str, Any]:
    """A stored authorization in the contract's Payment shape (select PAYMENT_COLUMNS from authorizations a)."""
    p = purchase_from_json(json.loads(row["purchase"]))
    stored = json.loads(row["checks"]) if row["checks"] else {}
    response = stored.get("response") or {}
    m = p.merchant
    return {
        "authorization_id": p.authorization_id, "source_authorization_id": p.source_authorization_id,
        "run_id": row["run_id"],
        "merchant": {"merchant_id": m.merchant_id, "name": m.name, "category": m.category, "country": m.country,
                     **({"city": m.city} if m.city else {})},
        "sim_time": _iso(p.sim_time.at), "amount": _money(p.amount), "currency": p.currency,
        "billing_amount_chf": _money(p.billing_amount_chf),
        "items": [{"item_id": i.item_id, "name": i.name, "quantity": i.quantity, "unit_price": _money(i.unit_price)}
                  for i in p.items],
        "engine_verdict": row["engine_verdict"],
        "final_state": row["state"] if row["state"] != "received" else "waiting",
        # Kept apart from the verdict on purpose: what we decided, and what the platform did with it.
        "delivery": row["delivery"],
        "platform_outcome": row["platform_outcome"],
        "resolved_by": row["resolved_by"],
        "customer_message": response.get("customer_message", ""),
    }


async def approval_check(conn: asyncpg.Connection, pool: asyncpg.Pool, mandates: MandateSource,
                         row: asyncpg.Record) -> tuple[bool, str | None]:
    """Would the customer's approval go through now? The same re-check as application.resolve (DEC-012)."""
    purchase = purchase_from_json(json.loads(row["purchase"]))
    platform = await PostgresRepository.platform_spend_now(conn, row["authorization_id"])
    snapshot = await PostgresRepository(pool).snapshot(row["card_id"], run_id=row["run_id"],
                                                       platform_period_spend_chf=platform, conn=conn)
    try:
        mandate = mandates.for_run(row["run_id"])
    except LookupError:  # a run started a moment ago: load it now rather than fail (never an empty mandate)
        refresh = getattr(mandates, "refresh", None)
        if refresh is None:
            raise
        await refresh(pool)
        mandate = mandates.for_run(row["run_id"])
    recheck = decide(purchase, mandate, snapshot, Facts.not_stated("recheck"))
    failing = [c for c in recheck.checks if c.status == "fail"]
    return (not failing), (failing[0].detail if failing else None)


PAYMENT_COLUMNS = ("a.authorization_id, a.run_id, a.state, a.engine_verdict, a.resolved_by, a.checks, "
                   "a.purchase, a.delivery, a.platform_outcome")
_ORDER = """(select min(e.seq) from decision_events e
             where e.authorization_id = a.authorization_id and e.kind = 'received')"""


def query_router(pool: Callable[[], asyncpg.Pool], mandates: MandateSource, clock: Clock) -> APIRouter:
    router = APIRouter()

    async def latest_run(conn: asyncpg.Connection) -> str | None:
        run: str | None = await conn.fetchval("select run_id from runs order by started_at desc, run_id desc limit 1")
        return run

    @router.get("/api/payments")
    async def payments(run_id: str | None = None) -> dict[str, Any]:
        async with pool().acquire() as conn:
            rows = await conn.fetch(f"select {PAYMENT_COLUMNS} from authorizations a "
                                    f"where $1::text is null or a.run_id = $1 order by {_ORDER}", run_id)
        return {"payments": [payment_view(r) for r in rows]}

    @router.get("/api/payments/{authorization_id}")
    async def payment(authorization_id: str) -> Any:
        async with pool().acquire() as conn:
            row = await conn.fetchrow(f"select {PAYMENT_COLUMNS} from authorizations a "
                                      f"where a.authorization_id = $1", authorization_id)
            if row is None:
                return _not_found("payment")
            # `last_error is null` matters: the outbox closes a terminally refused row too, so
            # `sent_at` alone would report a body the platform never accepted (LEASH-130).
            sent = await conn.fetchval("select body from outbox where authorization_id = $1 and endpoint = 'decision' "
                                       "and sent_at is not null and last_error is null order by id limit 1",
                                       authorization_id)
        stored = json.loads(row["checks"]) if row["checks"] else {}
        response = stored.get("response") or {}
        reader = stored.get("reader") or {"name": "unknown", "model_unavailable": False}
        p = purchase_from_json(json.loads(row["purchase"]))
        return {**payment_view(row),
                "checks": stored.get("checks", []), "evidence": response.get("evidence", []),
                "shop_texts": [{"item_id": i.item_id, "text": i.details} for i in p.items],
                "sent_to_viseca": json.loads(sent) if sent else None,
                "engine_version": response.get("engine_version", ""),
                "reader": {"name": reader["name"], "model_unavailable": bool(reader["model_unavailable"])}}

    @router.get("/api/asks")
    async def asks() -> dict[str, Any]:
        now = clock()
        async with pool().acquire() as conn:
            rows = await conn.fetch(f"select {PAYMENT_COLUMNS}, a.card_id, a.ask_expires_at from authorizations a "
                                    f"where a.state = 'waiting' and a.ask_expires_at > $1 order by a.ask_expires_at",
                                    now)
            out = []
            for row in rows:
                stored = json.loads(row["checks"]) if row["checks"] else {}
                checks = stored.get("checks", [])
                can_approve, reason = await approval_check(conn, pool(), mandates, row)
                out.append({
                    "authorization_id": row["authorization_id"], "payment": payment_view(row),
                    "reasons": [c["detail"] for c in checks if c["status"] in ("warn", "integrity")],
                    "passed": [c["label"] for c in checks if c["status"] == "pass"],
                    "expires_at": _iso(row["ask_expires_at"]),
                    "can_approve": can_approve,
                    "cannot_approve_reason": reason,
                })
        return {"asks": out}

    @router.get("/api/spending")
    async def spending(run_id: str | None = None) -> Any:
        async with pool().acquire() as conn:
            run = run_id or await latest_run(conn)
            if run is None:
                return _not_found("run")
            card = await conn.fetchval("select card_id from runs where run_id = $1", run)
            if card is None:
                return _not_found("run")
            snapshot = await PostgresRepository(pool()).snapshot(card, run_id=run, platform_period_spend_chf=None,
                                                                 conn=conn)
            last = await conn.fetchrow(f"select a.authorization_id, a.event, a.purchase from authorizations a "
                                       f"where a.run_id = $1 order by {_ORDER} desc limit 1", run)
            acknowledged = {r["authorization_id"] for r in await conn.fetch(
                "select authorization_id from authorizations where run_id = $1 and state = 'approved' "
                "and delivery = 'accepted'", run)}
            approved_before = [] if last is None else await conn.fetch(
                """select a.authorization_id from authorizations a where a.run_id = $1 and a.state = 'approved'
                   and (select min(e.seq) from decision_events e where e.authorization_id = a.authorization_id
                        and ((e.kind = 'decided' and e.payload->>'verdict' = 'approve')
                             or (e.kind = 'customer_resolved' and e.payload->>'state' = 'approved')))
                     < (select min(e.seq) from decision_events e
                        where e.authorization_id = $2 and e.kind = 'received')""", run, last["authorization_id"])
        approved = [p.purchase for p in snapshot.prior if p.state == "approved"]
        periods = mandates.for_run(run).periods
        period = periods[0] if periods else None
        latest_at: SimTime | None = max((p.sim_time for p in approved), default=None)
        if period is not None and approved and latest_at is not None:
            spent = snapshot.approved_spend_in_window(latest_at, timedelta(days=period.days))
        else:
            spent = sum((p.billing_amount_chf for p in approved), Decimal("0.00"))
        # The platform's counter in an event is the spend *before* that purchase (DEC-010): compare it with our
        # ledger as it stood when that purchase arrived — approvals recorded before it was received, in the
        # window ending at it. Like the engine, only a single period rule is compared.
        counter, mismatch = None, False
        if last is not None:
            context = (json.loads(last["event"]) or {}).get("context", {})
            counter = context.get("approved_spend_in_period_chf")
            if counter is not None and period is not None and len(periods) == 1:
                current = purchase_from_json(json.loads(last["purchase"]))
                window = timedelta(days=period.days)
                known = {r["authorization_id"] for r in approved_before}
                before = sum((p.billing_amount_chf for p in approved if p.authorization_id in known
                              and p.authorization_id != current.authorization_id
                              and current.sim_time.within(p.sim_time, window)), Decimal("0.00"))
                mismatch = Decimal(str(counter)).quantize(Decimal("0.01")) != before
        # `approved_chf` is what the *engine* approved — a reservation the moment it is decided, whether
        # or not the platform has acknowledged it yet. It is what the limit is enforced against, because
        # counting only acknowledged spend would let two concurrent purchases both pass while their
        # acknowledgements were still outstanding. `accepted_chf` is the narrower fact: the part the
        # platform has actually accepted. A terminal refusal releases its reservation by leaving
        # `approved`, so the difference is only ever spend still in flight (LEASH-130).
        # Over the *same* window as `approved_chf`, or the two are not comparable: an accepted purchase
        # outside the period would otherwise make `accepted_chf` exceed the total it is a part of, and
        # `awaiting_platform_chf` would clamp to zero while spend was genuinely outstanding.
        counted = [p for p in approved
                   if period is None or latest_at is None
                   or latest_at.within(p.sim_time, timedelta(days=period.days))]
        accepted_chf = sum((p.billing_amount_chf for p in counted if p.authorization_id in acknowledged),
                           Decimal("0.00"))
        return {
            "run_id": run, "period_days": period.days if period else None,
            "limit_chf": _money(period.limit.value) if period else None,
            "approved_chf": _money(spent),
            "accepted_chf": _money(accepted_chf),
            "awaiting_platform_chf": _money(max(spent - accepted_chf, Decimal("0.00"))),
            "remaining_chf": _money(max(period.limit.value - spent, Decimal("0"))) if period else None,
            "platform_counter_chf": _money(counter) if counter is not None else None,
            "mismatch": mismatch,
        }

    @router.get("/api/mandates/{mandate_id}/versions")
    async def mandate_versions(mandate_id: str) -> Any:
        async with pool().acquire() as conn:
            rows = await conn.fetch("select version, hard_rules, uncertainty_policy, created_at from mandate_versions "
                                    "where mandate_id = $1 order by version", mandate_id)
        if not rows:
            return _not_found("mandate")
        return {"mandate_id": mandate_id, "versions": [
            {"version": r["version"], "change": "confirmed" if r["version"] == 1 else "tightened",
             "hard_rules": json.loads(r["hard_rules"]), "uncertainty_policy": r["uncertainty_policy"],
             "review": permission_review([rule_from_api(x) for x in json.loads(r["hard_rules"])], r["uncertainty_policy"]),
             "created_at": _iso(r["created_at"])} for r in rows]}

    return router


def create_query_app(database_url: str, mandates: MandateSource,
                     clock: Clock = lambda: datetime.now(timezone.utc)) -> FastAPI:
    state: dict[str, asyncpg.Pool] = {}

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        state["pool"] = await asyncpg.create_pool(database_url, min_size=1, max_size=4)
        try:
            yield
        finally:
            await state["pool"].close()

    app = FastAPI(title="Leash read API", lifespan=lifespan)
    app.include_router(query_router(lambda: state["pool"], mandates, clock))
    return app

