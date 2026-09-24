"""One transaction per decision (DEC-007): lock → rebuild snapshot → decide → save → commit.

Facts are read by the caller before this runs, so a model reader can never hold the lock. Inside one
transaction: a per-card advisory lock (bounded by lock_timeout, so the deadline can still be met), the
snapshot rebuilt under that lock, the pure decision, the saved verdict with its decision event, the
outbox row carrying the exact body to send, and NOTIFY `asks` for a step_up. They commit together or
not at all; NOTIFY is delivered only on commit.
"""

import json
import logging
import os
import socket
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

import asyncpg

from leash.adapters.postgres.repository import PostgresRepository, purchase_from_json
from leash.domain.decide import Decision, decide
from leash.domain.explain import explain
from leash.domain.facts import Facts
from leash.domain.mandate import CompiledMandate
from leash.domain.purchase import Purchase
from leash.domain.snapshot import Snapshot
from leash.domain.states import PurchaseState, purchase_transition
from leash.ports.repository import SavedAuthorization

log = logging.getLogger("leash.decide")

DEFAULT_LOCK_TIMEOUT_MS = 1500
DEFAULT_LEASE_SECONDS = 3.0  # a claim not refreshed for this long can be taken over by a redelivery (LEASH-131)


def worker_identity() -> str:
    """A claim owner unique to this process: host, pid and a random part (a restarted process is a new owner)."""
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
ASKS_CHANNEL = "asks"


class LockTimeout(RuntimeError):
    """The card's lock wasn't free within lock_timeout; the caller answers with a safe step_up instead."""


@dataclass(frozen=True)
class DecisionOutcome:
    decision: Decision
    response: dict[str, Any]  # the body for POST /v1/authorizations/{id}/decision, also in the outbox
    stages: list[tuple[str, float]] = field(default_factory=list)  # (stage, milliseconds), in order


def card_lock_key(card_id: str) -> str:
    return f"card:{card_id}"


async def _write_outbox(conn: asyncpg.Connection, authorization_id: str, body: Mapping[str, Any]) -> None:
    await conn.execute("insert into outbox (authorization_id, endpoint, body) values ($1, 'decision', $2::jsonb)",
                       authorization_id, json.dumps(dict(body), default=str))


class DecisionTransaction:
    def __init__(self, pool: asyncpg.Pool, *, engine_version: str,
                 lock_timeout_ms: int = DEFAULT_LOCK_TIMEOUT_MS) -> None:
        self._pool = pool
        self._repo = PostgresRepository(pool)
        self._engine_version = engine_version
        self._lock_timeout_ms = int(lock_timeout_ms)

    async def decide(self, purchase: Purchase, *, run_id: str | None, mandate: CompiledMandate, facts: Facts,
                     platform_period_spend_chf: Decimal | None,
                     ask_expires_at: datetime | None = None, mandate_id: str | None = None) -> DecisionOutcome:
        stages: list[tuple[str, float]] = []
        clock = time.perf_counter()

        def stage(name: str) -> None:
            nonlocal clock
            now = time.perf_counter()
            stages.append((name, (now - clock) * 1000))
            clock = now

        async with self._pool.acquire() as conn:
            # READ COMMITTED is pinned: the snapshot must see approvals committed by whoever held the card
            # lock before us. Under a repeatable-read default every waiter would decide on stale spend.
            transaction = conn.transaction(isolation="read_committed")
            await transaction.start()
            try:
                await conn.execute(f"set local lock_timeout = {self._lock_timeout_ms}")
                await conn.execute("select pg_advisory_xact_lock(hashtext($1))", card_lock_key(purchase.card_id))
                stage("lock")
                snapshot = await self._repo.snapshot(purchase.card_id, run_id=run_id,
                                                     platform_period_spend_chf=platform_period_spend_chf, conn=conn)
                stage("snapshot")
                decision = decide(purchase, mandate, snapshot, facts)
                response = explain(decision, authorization_id=purchase.authorization_id,
                                   engine_version=self._engine_version)
                stage("decide")
                await self._repo.record_decision(purchase.authorization_id, decision, response=response,
                                                 ask_expires_at=ask_expires_at, conn=conn,
                                                 reader={"name": facts.reader, "model_unavailable": facts.model_unavailable})
                await _write_outbox(conn, purchase.authorization_id, response)
                unsupported = [r.field for r in mandate.unsupported_rules()]
                if unsupported:  # an operational alert for the operator (DEC-005)
                    await self._repo.alert(conn, purchase.authorization_id, {
                        "kind": "unsupported_mandate_rule", "mandate_id": mandate_id,
                        "fields": list(dict.fromkeys(unsupported)), "engine_version": self._engine_version})
                    log.warning("unsupported mandate rule(s) %s in mandate %s", unsupported, mandate_id,
                                extra={"authorization_id": purchase.authorization_id})
                if decision.verdict == "step_up":
                    await conn.execute("select pg_notify($1, $2)", ASKS_CHANNEL, purchase.authorization_id)
                stage("save")
            except asyncpg.exceptions.LockNotAvailableError as exc:  # the card lock or a row lock
                await transaction.rollback()
                raise LockTimeout(f"{purchase.authorization_id}: a lock stayed taken for "
                                  f"{self._lock_timeout_ms} ms") from exc
            except BaseException:
                await transaction.rollback()
                raise
            await transaction.commit()
            stage("commit")
        return DecisionOutcome(decision, response, stages)


class PostgresDecisionStore:
    """The DecisionStore port of DecidePurchase on Postgres (LEASH-053), with durable claims (LEASH-131)."""

    def __init__(self, pool: asyncpg.Pool, *, engine_version: str,
                 lock_timeout_ms: int = DEFAULT_LOCK_TIMEOUT_MS, owner: str | None = None,
                 lease_seconds: float = DEFAULT_LEASE_SECONDS) -> None:
        self._pool = pool
        self.owner = owner or worker_identity()
        self.lease_seconds = lease_seconds
        self._repo = PostgresRepository(pool)
        self._tx = DecisionTransaction(pool, engine_version=engine_version, lock_timeout_ms=lock_timeout_ms)

    async def receive(self, purchase: Purchase, *, run_id: str | None, event: Mapping[str, Any],
                      received_at: datetime, deadline_at: datetime) -> SavedAuthorization | None:
        if run_id is not None:
            await self._repo.ensure_run(run_id, event, purchase.card_id)
        return await self._repo.receive(purchase, run_id=run_id, event=event, received_at=received_at,
                                        deadline_at=deadline_at, owner=self.owner, lease_seconds=self.lease_seconds)

    async def refresh_claim(self, authorization_id: str) -> bool:
        return await self._repo.refresh_claim(authorization_id, self.owner, self.lease_seconds)

    async def release_claim(self, authorization_id: str) -> None:
        await self._repo.release_claim(authorization_id, self.owner)

    async def decide(self, purchase: Purchase, *, run_id: str | None, mandate: CompiledMandate, facts: Facts,
                     platform_period_spend_chf: Decimal | None, ask_expires_at: datetime | None = None,
                     mandate_id: str | None = None) -> DecisionOutcome:
        return await self._tx.decide(purchase, run_id=run_id, mandate=mandate, facts=facts,
                                     platform_period_spend_chf=platform_period_spend_chf,
                                     ask_expires_at=ask_expires_at, mandate_id=mandate_id)

    async def record_fallback(self, purchase: Purchase, *, run_id: str | None, response: Mapping[str, Any],
                              ask_expires_at: datetime) -> SavedAuthorization | None:
        aid = purchase.authorization_id
        async with self._pool.acquire() as conn, conn.transaction(isolation="read_committed"):
            committed = await self._repo.record_fallback(aid, response, ask_expires_at=ask_expires_at, conn=conn)
            if committed is None:
                await _write_outbox(conn, aid, response)
                await conn.execute("select pg_notify($1, $2)", ASKS_CHANNEL, aid)
            return committed

    async def mark_sent(self, authorization_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("update outbox set sent_at = now(), attempts = attempts + 1, last_attempt_at = now() "
                               "where authorization_id = $1 and endpoint = 'decision' and sent_at is null",
                               authorization_id)


@dataclass(frozen=True)
class ResolveOutcome:
    state: str  # the purchase's state afterwards
    blocked: tuple[str, ...] = ()  # reason codes that stopped an approval (DEC-012)
    explanation: str = ""
    response: dict[str, Any] | None = None  # the /resolve body written to the outbox


# (purchase, run_id, snapshot under the lock) -> the re-checked decision
Recheck = Callable[[Purchase, str | None, Snapshot], Decision]
# (answer, re-checked decision or None) -> the /resolve body
ResolveBody = Callable[[str, Decision | None], dict[str, Any]]


class ResolutionTransaction:
    """The customer's answer and the ask timeout, under the same per-card lock as decisions (LEASH-045)."""

    def __init__(self, pool: asyncpg.Pool, *, lock_timeout_ms: int = DEFAULT_LOCK_TIMEOUT_MS) -> None:
        self._pool = pool
        self._repo = PostgresRepository(pool)
        self._lock_timeout_ms = int(lock_timeout_ms)

    async def _begin(self, conn: asyncpg.Connection, card_id: str) -> None:
        await conn.execute(f"set local lock_timeout = {self._lock_timeout_ms}")
        await conn.execute("select pg_advisory_xact_lock(hashtext($1))", card_lock_key(card_id))

    async def resolve(self, authorization_id: str, answer: str, *, now: datetime, recheck: Recheck,
                      body: ResolveBody) -> ResolveOutcome:
        async with self._pool.acquire() as conn:
            card_id = await conn.fetchval("select card_id from authorizations where authorization_id = $1",
                                          authorization_id)
            if card_id is None:
                raise KeyError(f"unknown authorization {authorization_id}")
            try:
                async with conn.transaction(isolation="read_committed"):
                    await self._begin(conn, card_id)
                    row = await conn.fetchrow("select state, run_id, ask_expires_at, purchase from authorizations "
                                              "where authorization_id = $1 for update", authorization_id)
                    if row["state"] == "waiting" and row["ask_expires_at"] is not None \
                            and now >= row["ask_expires_at"]:
                        await self._repo.transition(authorization_id, "timed_out", by="platform",
                                                    payload={"reason": "ask expired"}, conn=conn)
                        return ResolveOutcome("timed_out", explanation="The time to answer this purchase expired.")
                    target: PurchaseState = "approved" if answer == "approve" else "declined"
                    purchase_transition(row["state"], target, "customer")  # not waiting → IllegalTransition
                    decision = None
                    if answer == "approve":
                        purchase = purchase_from_json(json.loads(row["purchase"]))
                        platform = await self._repo.platform_spend_now(conn, authorization_id)
                        snapshot = await self._repo.snapshot(card_id, run_id=row["run_id"],
                                                             platform_period_spend_chf=platform, conn=conn)
                        decision = recheck(purchase, row["run_id"], snapshot)
                        failing = [c for c in decision.checks if c.status == "fail"]
                        if failing:  # a hard rule now fails: nothing changes, only Reject remains (DEC-012)
                            return ResolveOutcome("waiting", tuple(dict.fromkeys(
                                c.reason_code for c in failing if c.reason_code)), failing[0].detail)
                    response = body(answer, decision)
                    await self._repo.transition(authorization_id, target, by="customer",
                                                payload={"answer": answer}, conn=conn)
                    await conn.execute("insert into outbox (authorization_id, endpoint, body) "
                                       "values ($1, 'resolve', $2::jsonb)", authorization_id,
                                       json.dumps(response, default=str))
                    return ResolveOutcome(target, response=response)
            except asyncpg.exceptions.LockNotAvailableError as exc:
                raise LockTimeout(f"{authorization_id}: a lock stayed taken for {self._lock_timeout_ms} ms") from exc

    async def sweep(self, now: datetime) -> list[str]:
        """Time out every ask whose explicit expiry has passed (DEC-016). Returns the IDs timed out."""
        async with self._pool.acquire() as conn:
            due = await conn.fetch("select authorization_id, card_id from authorizations where state = 'waiting' "
                                   "and ask_expires_at <= $1 order by ask_expires_at", now)
            timed_out = []
            for row in due:
                try:
                    async with conn.transaction(isolation="read_committed"):
                        await self._begin(conn, row["card_id"])
                        still = await conn.fetchval("select state = 'waiting' and ask_expires_at <= $2 "
                                                    "from authorizations where authorization_id = $1 for update",
                                                    row["authorization_id"], now)
                        if still:
                            await self._repo.transition(row["authorization_id"], "timed_out", by="platform",
                                                        payload={"reason": "ask expired"}, conn=conn)
                            timed_out.append(row["authorization_id"])
                except asyncpg.exceptions.LockNotAvailableError:
                    continue  # that card is busy; its ask is swept on the next run, the others now
            return timed_out
