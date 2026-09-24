"""Postgres implementation of the repository port (asyncpg).

Every state change goes through the purchase state machine under a row lock, and is written together
with an append-only decision event in one transaction. Purchases are stored in the adapter's own JSON
form (column `purchase`) so a snapshot can rebuild them exactly; the raw event is kept for audit.
"""

import json
import logging
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import asyncpg

from leash.domain.clock import SimTime
from leash.domain.decide import Decision
from leash.domain.money import fmt_chf
from leash.domain.purchase import LineItem, Merchant, Purchase, Term
from leash.domain.snapshot import FinalState, HistoryBaseline, PriorPurchase, Snapshot
from leash.domain.states import Actor, PurchaseState, purchase_transition
from leash.ports.repository import SavedAuthorization

log = logging.getLogger("leash.repository")

EVENTS_LOCK_KEY = 0x4C45415348  # "LEASH": advisory lock guarding writes to decision_events

_STATE_OF_VERDICT: dict[str, PurchaseState] = {"approve": "approved", "decline": "declined", "step_up": "waiting"}
_FINAL_STATES: tuple[FinalState, ...] = ("approved", "waiting", "declined", "timed_out")
# How the platform's recent_authorizations statuses correspond to our states.
_MATCHING_STATES: dict[str, frozenset[str]] = {
    "approved": frozenset({"approved"}),
    "declined": frozenset({"declined", "timed_out"}),
    "pending": frozenset({"received", "waiting"}),
    "cancelled": frozenset({"declined", "timed_out", "waiting", "received"}),
}


def purchase_to_json(p: Purchase) -> dict[str, Any]:
    m = p.merchant
    return {
        "authorization_id": p.authorization_id, "source_authorization_id": p.source_authorization_id,
        "card_id": p.card_id,
        "merchant": {"merchant_id": m.merchant_id, "name": m.name, "category": m.category, "mcc": m.mcc,
                     "country": m.country, "city": m.city, "availability": m.availability,
                     "recurring_capable": m.recurring_capable},
        "sim_time": p.sim_time.at.isoformat(), "amount": str(p.amount), "currency": p.currency,
        "billing_amount_chf": str(p.billing_amount_chf), "items_subtotal": str(p.items_subtotal),
        "delivery_fee": str(p.delivery_fee), "channel": p.channel, "device_id": p.device_id,
        "recent_attempts_10m": p.recent_attempts_10m, "fulfillment": p.fulfillment,
        "delivery_by": p.delivery_by.isoformat() if p.delivery_by else None,
        "order_returnable": p.order_returnable.value, "order_cancellable": p.order_cancellable.value,
        "related_authorization_id": p.related_authorization_id, "related_status": p.related_status,
        "description": p.description,
        "items": [{"line_no": i.line_no, "item_id": i.item_id, "name": i.name, "category": i.category,
                   "quantity": i.quantity, "unit_price": str(i.unit_price), "currency": i.currency,
                   "details": i.details} for i in p.items],
    }


def purchase_from_json(d: Mapping[str, Any]) -> Purchase:
    return Purchase(
        authorization_id=d["authorization_id"], source_authorization_id=d["source_authorization_id"],
        card_id=d["card_id"], merchant=Merchant(**d["merchant"]), sim_time=SimTime(datetime.fromisoformat(d["sim_time"])),
        amount=Decimal(d["amount"]), currency=d["currency"], billing_amount_chf=Decimal(d["billing_amount_chf"]),
        items_subtotal=Decimal(d["items_subtotal"]), delivery_fee=Decimal(d["delivery_fee"]), channel=d["channel"],
        device_id=d["device_id"], recent_attempts_10m=d["recent_attempts_10m"], fulfillment=d["fulfillment"],
        delivery_by=date.fromisoformat(d["delivery_by"]) if d["delivery_by"] else None,
        order_returnable=Term.parse(d["order_returnable"]), order_cancellable=Term.parse(d["order_cancellable"]),
        related_authorization_id=d["related_authorization_id"], related_status=d["related_status"],
        description=d["description"],
        items=tuple(LineItem(**{**i, "unit_price": Decimal(i["unit_price"])}) for i in d["items"]),
    )


def _json(value: Any) -> str:
    return json.dumps(value, default=str)


def _check_json(decision: Decision) -> list[dict[str, Any]]:
    return [{"key": c.key, "label": c.label, "status": c.status, "agreed": c.agreed, "actual": c.actual,
             "detail": c.detail, "reason_code": c.reason_code} for c in decision.checks]


class PostgresRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def receive(self, purchase: Purchase, *, run_id: str | None, event: Mapping[str, Any],
                      received_at: datetime, deadline_at: datetime, owner: str | None = None,
                      lease_seconds: float | None = None) -> SavedAuthorization | None:
        """Store a newly received purchase; None means the caller now does the decision work.

        With an `owner`, the work is claimed under a lease measured on the database clock (LEASH-131): a new
        row is claimed, and a row still 'received' whose claim has expired (or has none) is taken over and
        recorded as 'reclaimed'. A live claim, or a row already answered, returns what is saved instead."""
        state = purchase_transition(None, "received", "engine")
        lease = timedelta(seconds=lease_seconds or 0)
        async with self._pool.acquire() as conn, conn.transaction():
            claimed = await conn.fetchrow(
                """insert into authorizations (authorization_id, source_authorization_id, run_id, card_id,
                       merchant_id, sim_ts, billing_chf, item_fingerprint, state, received_at, deadline_at,
                       event, purchase, claim_owner, claim_expires_at)
                   values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb, $13::jsonb, $14,
                           case when $14::text is null then null else now() + $15::interval end)
                   on conflict (authorization_id) do update
                       set claim_owner = excluded.claim_owner, claim_expires_at = excluded.claim_expires_at
                       where $14::text is not null and authorizations.state = 'received'
                         and (authorizations.claim_expires_at is null or authorizations.claim_expires_at <= now())
                   returning (xmax = 0) as inserted""",
                purchase.authorization_id, purchase.source_authorization_id, run_id, purchase.card_id,
                purchase.merchant.merchant_id, purchase.sim_time.at, purchase.billing_amount_chf,
                _json(purchase.item_fingerprint), state, received_at, deadline_at, _json(event),
                _json(purchase_to_json(purchase)), owner, lease)
            if claimed is not None:
                if claimed["inserted"]:
                    await self._event(conn, purchase.authorization_id, "received", {"run_id": run_id})
                else:
                    log.warning("reclaimed an expired claim on %s", purchase.authorization_id,
                                extra={"authorization_id": purchase.authorization_id})
                    await self._event(conn, purchase.authorization_id, "reclaimed", {"owner": owner})
                return None
            row = await conn.fetchrow("select state, engine_verdict, checks from authorizations "
                                      "where authorization_id = $1", purchase.authorization_id)
        checks = json.loads(row["checks"]) if row["checks"] else None
        return SavedAuthorization(purchase.authorization_id, row["state"], row["engine_verdict"],
                                  checks["response"] if checks else None)

    async def refresh_claim(self, authorization_id: str, owner: str, lease_seconds: float) -> bool:
        """Extend the owner's lease while the work is still undecided. False: the claim is no longer ours."""
        async with self._pool.acquire() as conn:
            done = await conn.fetchval(
                "update authorizations set claim_expires_at = now() + $3::interval where authorization_id = $1 "
                "and claim_owner = $2 and state = 'received' returning true",
                authorization_id, owner, timedelta(seconds=lease_seconds))
        return bool(done)

    async def release_claim(self, authorization_id: str, owner: str) -> None:
        """Give the claim up: answered work needs none, and unanswered work can be taken over at once."""
        async with self._pool.acquire() as conn:
            await conn.execute("update authorizations set claim_owner = null, claim_expires_at = null "
                               "where authorization_id = $1 and claim_owner = $2", authorization_id, owner)

    async def ensure_run(self, run_id: str, event: Mapping[str, Any], card_id: str) -> None:
        """Record a run first seen in a live event, with the event's mandate as its snapshot (DEC-003).

        Runs we start are recorded when started (LEASH-066); this covers any other run, so a purchase is never
        refused locally for an unknown run. The snapshot version is the stored one with the same rules, or a
        new version holding exactly the event's rules."""
        raw = event.get("mandate")
        mandate: Mapping[str, Any] = raw if isinstance(raw, Mapping) else {}
        mandate_id = str(mandate.get("mandate_id") or f"unknown:{run_id}")
        hard_rules = _json(list(mandate.get("hard_rules") or []))
        policy = mandate.get("uncertainty_policy")
        policy = policy if policy in ("ask", "decline", "approve") else "ask"
        async with self._pool.acquire() as conn, conn.transaction():
            stored = await conn.fetchrow("select v.hard_rules, v.uncertainty_policy from runs r join mandate_versions v "
                                         "on v.mandate_id = r.mandate_id and v.version = r.mandate_version "
                                         "where r.run_id = $1", run_id)
            if stored is not None:  # a run keeps its first snapshot (DEC-003); a different one is only flagged
                if raw is not None and (json.loads(stored["hard_rules"]) != list(mandate.get("hard_rules") or [])
                                        or stored["uncertainty_policy"] != policy):
                    log.error("INTEGRITY: run %s: an event carries a mandate that differs from the run's stored "
                              "snapshot; the stored one is kept for re-checks, the event's decides that purchase",
                              run_id)
                return
            await conn.execute("select pg_advisory_xact_lock(hashtext($1))", f"mandate:{mandate_id}")
            await conn.execute("insert into mandates (mandate_id, instruction, status) values ($1, $2, 'active') "
                               "on conflict (mandate_id) do nothing", mandate_id, str(mandate.get("instruction") or ""))
            version = await conn.fetchval(
                "select version from mandate_versions where mandate_id = $1 and hard_rules = $2::jsonb "
                "and uncertainty_policy = $3 order by version desc limit 1", mandate_id, hard_rules, policy)
            if version is None:
                version = await conn.fetchval("select coalesce(max(version), 0) + 1 from mandate_versions "
                                              "where mandate_id = $1", mandate_id)
                await conn.execute("insert into mandate_versions (mandate_id, version, hard_rules, uncertainty_policy, "
                                   "compiled) values ($1, $2, $3::jsonb, $4, $5::jsonb)", mandate_id, version,
                                   hard_rules, policy, _json({"source": "live event"}))
            await conn.execute("insert into runs (run_id, scenario_id, mandate_id, mandate_version, card_id) "
                               "values ($1, $2, $3, $4, $5) on conflict (run_id) do nothing",
                               run_id, str(event.get("scenario_id") or "unknown"), mandate_id, version, card_id)

    @staticmethod
    async def platform_spend_now(conn: asyncpg.Connection, authorization_id: str) -> Decimal | None:
        """The platform's approved spend for a re-check (DEC-010, DEC-012): the counter in this purchase's event
        (spend before it, as of its decision) plus every approval recorded since the purchase arrived. The
        snapshot takes the higher of this and our ledger, so a re-check is never looser than the decision."""
        row = await conn.fetchrow("select card_id, run_id, event->'context'->>'approved_spend_in_period_chf' counter "
                                  "from authorizations where authorization_id = $1", authorization_id)
        if row is None or row["counter"] is None:
            return None
        since = await conn.fetchval(
            """select coalesce(sum(a.billing_chf), 0) from authorizations a
               where a.card_id = $2 and a.run_id is not distinct from $3 and a.state = 'approved'
                 and a.authorization_id <> $1
                 and (select min(e.seq) from decision_events e where e.authorization_id = a.authorization_id
                      and ((e.kind = 'decided' and e.payload->>'verdict' = 'approve')
                           or (e.kind = 'customer_resolved' and e.payload->>'state' = 'approved')))
                   > (select min(e.seq) from decision_events e
                      where e.authorization_id = $1 and e.kind = 'received')""",
            authorization_id, row["card_id"], row["run_id"])
        return Decimal(str(row["counter"])).quantize(Decimal("0.01")) + Decimal(since)

    async def snapshot(self, card_id: str, *, run_id: str | None,
                       platform_period_spend_chf: Decimal | None, conn: asyncpg.Connection | None = None) -> Snapshot:
        if conn is None:
            async with self._pool.acquire() as own:
                return await self.snapshot(card_id, run_id=run_id, platform_period_spend_chf=platform_period_spend_chf,
                                           conn=own)
        familiar = await conn.fetch("select merchant_id, approved_purchases from card_merchant_familiarity "
                                    "where card_id = $1", card_id)
        seen = await conn.fetchrow(
            """select array_agg(distinct device_id) filter (where device_id is not null) devices,
                      array_agg(distinct country) filter (where country is not null) countries
               from auth_history where card_id = $1 and transaction_type = 'purchase' and status = 'approved'""",
            card_id)
        names = await conn.fetch("select merchant_id, name from merchants")
        rows = await conn.fetch(
            """select a.purchase, a.state from authorizations a
               where a.card_id = $1 and a.run_id is not distinct from $2 and a.state = any($3::text[])
               order by (select min(e.seq) from decision_events e
                         where e.authorization_id = a.authorization_id and e.kind = 'received')""",
            card_id, run_id, list(_FINAL_STATES))
        baseline = HistoryBaseline(merchant_purchases={r["merchant_id"]: r["approved_purchases"] for r in familiar},
                                   devices=frozenset(seen["devices"] or ()), countries=frozenset(seen["countries"] or ()))
        prior = tuple(PriorPurchase(purchase_from_json(json.loads(r["purchase"])), r["state"]) for r in rows)
        return Snapshot(card_id=card_id, baseline=baseline, prior=prior,
                        platform_period_spend_chf=platform_period_spend_chf,
                        merchant_names={r["merchant_id"]: r["name"] for r in names})

    async def record_decision(self, authorization_id: str, decision: Decision, *, response: Mapping[str, Any],
                              ask_expires_at: datetime | None = None, conn: asyncpg.Connection | None = None,
                              reader: Mapping[str, Any] | None = None) -> None:
        """Save the engine's decision. With `conn`, runs inside the caller's transaction (LEASH-044)."""
        if conn is None:
            async with self._pool.acquire() as own, own.transaction():
                return await self.record_decision(authorization_id, decision, response=response,
                                                  ask_expires_at=ask_expires_at, conn=own, reader=reader)
        current = await self._lock(conn, authorization_id)
        target = purchase_transition(current, _STATE_OF_VERDICT[decision.verdict], "engine")
        await conn.execute(
            """update authorizations set state = $2, engine_verdict = $3, checks = $4::jsonb,
                   resolved_by = $5, ask_expires_at = $6 where authorization_id = $1""",
            authorization_id, target, decision.verdict,
            _json({"checks": _check_json(decision), "reason_codes": list(decision.reason_codes),
                   "alerts": list(decision.alerts), "response": dict(response),
                   "reader": dict(reader) if reader else None}),
            None if target == "waiting" else "engine", ask_expires_at if target == "waiting" else None)
        await self._event(conn, authorization_id, "decided",
                          {"verdict": decision.verdict, "reason_codes": list(decision.reason_codes)})

    async def record_fallback(self, authorization_id: str, response: Mapping[str, Any], *, ask_expires_at: datetime,
                              conn: asyncpg.Connection) -> SavedAuthorization | None:
        """The watchdog's safe step_up, only if no decision committed. Waits for a stalled decision's row lock,
        so the answer is the truth: None if the step_up was recorded, else what had committed."""
        current = await self._lock(conn, authorization_id)
        if current != "received":
            row = await conn.fetchrow("select state, engine_verdict, checks from authorizations "
                                      "where authorization_id = $1", authorization_id)
            checks = json.loads(row["checks"]) if row["checks"] else None
            return SavedAuthorization(authorization_id, row["state"], row["engine_verdict"],
                                      checks["response"] if checks else None)
        target = purchase_transition(current, "waiting", "engine")
        reasons = [str(r) for r in response.get("reason_codes") or []]
        await conn.execute(
            """update authorizations set state = $2, engine_verdict = 'step_up', checks = $3::jsonb,
                   resolved_by = null, ask_expires_at = $4 where authorization_id = $1""",
            authorization_id, target,
            _json({"checks": [], "reason_codes": reasons, "alerts": [], "response": dict(response), "reader": None,
                   "fallback": True}), ask_expires_at)
        await self._event(conn, authorization_id, "decided", {"verdict": "step_up", "reason_codes": reasons,
                                                              "fallback": True})
        return None

    async def transition(self, authorization_id: str, target: PurchaseState, *, by: Actor,
                         payload: Mapping[str, Any] | None = None, conn: asyncpg.Connection | None = None) -> None:
        """A later change by the customer or the platform. With `conn`, runs in the caller's transaction."""
        if conn is None:
            async with self._pool.acquire() as own, own.transaction():
                return await self.transition(authorization_id, target, by=by, payload=payload, conn=own)
        current = await self._lock(conn, authorization_id)
        purchase_transition(current, target, by)
        await conn.execute("update authorizations set state = $2, resolved_by = $3 where authorization_id = $1",
                           authorization_id, target, by)
        kind = "customer_resolved" if by == "customer" else "timed_out" if target == "timed_out" else "decided"
        await self._event(conn, authorization_id, kind, {"state": target, "by": by, **(payload or {})})

    async def reconcile(self, purchase: Purchase, snapshot: Snapshot, context: Mapping[str, Any], *,
                        period: timedelta | None) -> list[str]:
        mismatches: list[str] = []
        recent = [r for r in context.get("recent_authorizations") or []
                  if r.get("authorization_id") != purchase.authorization_id]
        async with self._pool.acquire() as conn:
            ours = {r["authorization_id"]: r["state"] for r in await conn.fetch(
                "select authorization_id, state from authorizations where authorization_id = any($1::text[])",
                [r["authorization_id"] for r in recent])}
            for r in recent:
                aid, theirs = r["authorization_id"], r.get("status")
                state = ours.get(aid)
                if state is None:
                    mismatches.append(f"{aid}: the platform lists it as {theirs}; we have no record of it")
                elif state not in _MATCHING_STATES.get(str(theirs), frozenset()):
                    mismatches.append(f"{aid}: the platform says {theirs}; we have it {state}")
            platform = context.get("approved_spend_in_period_chf")
            if period is not None and platform is not None:
                ours_spend = snapshot.approved_spend_in_window(purchase.sim_time, period).quantize(Decimal("0.01"))
                theirs_spend = Decimal(str(platform)).quantize(Decimal("0.01"))
                if theirs_spend != ours_spend:
                    mismatches.append(f"approved spend: the platform says {fmt_chf(theirs_spend)}; "
                                      f"our records give {fmt_chf(ours_spend)}")
            if mismatches:
                async with conn.transaction():
                    await self._event(conn, purchase.authorization_id, "integrity_alert", {"mismatches": mismatches})
        return mismatches

    @staticmethod
    async def _lock(conn: asyncpg.Connection, authorization_id: str) -> PurchaseState:
        state = await conn.fetchval("select state from authorizations where authorization_id = $1 for update",
                                    authorization_id)
        if state is None:
            raise KeyError(f"unknown authorization {authorization_id}")
        return state  # type: ignore[no-any-return]

    async def alert(self, conn: asyncpg.Connection, authorization_id: str, payload: Mapping[str, Any]) -> None:
        """An operational integrity alert, inside the caller's transaction."""
        await self._event(conn, authorization_id, "integrity_alert", payload)

    @staticmethod
    async def _event(conn: asyncpg.Connection, authorization_id: str, kind: str, payload: Mapping[str, Any]) -> None:
        # Writers hold this lock shared until they commit, so the event stream can wait out everyone who may
        # still commit a lower seq (LEASH-064). Shared holders never block each other.
        await conn.execute("select pg_advisory_xact_lock_shared($1)", EVENTS_LOCK_KEY)
        await conn.execute("insert into decision_events (authorization_id, kind, payload) values ($1, $2, $3::jsonb)",
                           authorization_id, kind, _json(dict(payload)))
