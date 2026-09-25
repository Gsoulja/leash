"""LEASH-130: make our record agree with the platform's, or say loudly that it does not.

Our projection is written from what we sent. The platform's is written from what it accepted. They can
drift for ordinary reasons — a crash between the POST and the acknowledgement, an answer that arrived
after `deadline_at`, a redelivery we answered from storage — and a demo that shows a purchase as paid
when the platform never accepted it is worse than one that shows nothing.

Two outcomes, and only two:

- **Repair**, when the platform is telling us something our record simply does not have yet: a delivery
  still `pending` that the platform has clearly decided. That is new information, not a conflict.
- **An integrity alert**, when the two disagree about something already settled. Nothing is overwritten.
  A disagreement about money is for a person to look at, and the alert names both sides and the IDs.

The reconciler never invents a verdict, never approves anything, and never moves a purchase toward a
less restrictive state: the only state change it can cause is the one a terminal refusal already
implies, `approved | declined | waiting → not_sent`.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

import asyncpg

from leash.adapters.postgres.repository import PostgresRepository, RepositoryEvents

log = logging.getLogger("leash.reconcile")

#: What a platform status means for our delivery record. Anything else is unknown and is raised, never
#: assumed: a status we do not understand is a missing fact, not a pass.
ACCEPTED_STATUSES = frozenset({"approved", "declined", "accepted", "resolved", "completed"})
REFUSED_STATUSES = frozenset({"not_sent", "refused", "rejected", "expired", "deadline_passed", "timed_out"})

#: Our purchase state, against the platform statuses that agree with it. Same table the decision path
#: uses for the event's own `recent_authorizations`.
AGREES: Mapping[str, frozenset[str]] = {
    "approved": frozenset({"approved", "accepted", "completed"}),
    "declined": frozenset({"declined", "rejected", "refused"}),
    "waiting": frozenset({"pending", "waiting", "waiting_for_customer", "pending_step_up"}),
    "received": frozenset({"pending", "waiting"}),
    "timed_out": frozenset({"declined", "expired", "timed_out", "cancelled"}),
    "not_sent": frozenset({"not_sent", "refused", "rejected", "expired", "deadline_passed", "cancelled"}),
}


class PlatformAuthorizations(Protocol):
    async def list_authorizations(self) -> Any: ...


@dataclass
class Reconciliation:
    """What one pass found. `repaired` changed our record; `alerts` did not change anything."""

    checked: int = 0
    repaired: list[str] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)
    unknown_to_us: list[str] = field(default_factory=list)
    #: Still being decided. Neither repaired nor alerted: there is nothing to compare yet.
    in_flight: list[str] = field(default_factory=list)


def _rows(body: Any) -> list[Mapping[str, Any]]:
    """The platform answers unwrapped or nested under `data`; both shapes, neither trusted."""
    data = body.get("data", body) if isinstance(body, Mapping) else body
    if isinstance(data, Mapping):
        data = data.get("authorizations", data.get("items", []))
    return [r for r in data if isinstance(r, Mapping)] if isinstance(data, list) else []


def _status(row: Mapping[str, Any]) -> str:
    value = row.get("status") or row.get("state") or row.get("outcome")
    return str(value).lower() if value is not None else "unknown"


class Reconciler:
    """Compares the platform's list of authorizations with ours, for one run or all of them."""

    def __init__(self, pool: asyncpg.Pool, api: PlatformAuthorizations, *,
                 clock: Any = lambda: datetime.now(timezone.utc)) -> None:
        self._pool, self._api, self._clock = pool, api, clock

    async def run_once(self, *, run_id: str | None = None) -> Reconciliation:
        found = Reconciliation()
        rows = _rows(await self._api.list_authorizations())
        if not rows:
            return found
        by_id = {str(r.get("authorization_id")): r for r in rows if r.get("authorization_id")}
        async with self._pool.acquire() as conn:
            ours = {r["authorization_id"]: r for r in await conn.fetch(
                "select authorization_id, state, delivery, platform_outcome, run_id from authorizations "
                "where authorization_id = any($1::text[]) and ($2::text is null or run_id = $2)",
                list(by_id), run_id)}
        for aid, row in by_id.items():
            mine = ours.get(aid)
            if mine is None:
                # Not ours to repair: it may belong to another run, or to another team's mandate.
                found.unknown_to_us.append(aid)
                continue
            found.checked += 1
            await self._one(aid, _status(row), mine, found)
        return found

    async def _one(self, aid: str, theirs: str, mine: asyncpg.Record, found: Reconciliation) -> None:
        if mine["state"] == "received":
            # Still being decided: the worker owns this row and will record its own delivery. Writing
            # one here would be an acknowledgement of a decision that does not exist yet — and, because
            # a delivery outcome is recorded once, it would make the real one unrecordable. Taking it to
            # `not_sent` is no better: it would collide with the decision the worker is about to commit.
            found.in_flight.append(aid)
            return
        if mine["delivery"] == "refused" and mine["state"] != "not_sent":
            # A refusal whose release never happened (a row backfilled by an older migration). Releasing
            # it is a repair, not a conflict: it only ever stops something counting.
            async with self._pool.acquire() as conn, conn.transaction():
                await conn.execute(
                    "update authorizations set state = 'not_sent' where authorization_id = $1 "
                    "and state in ('approved','declined','waiting')", aid)
                await RepositoryEvents.write(conn, aid, "delivered",
                                             {"delivery": "refused", "platform_outcome": mine["platform_outcome"],
                                              "state": "not_sent", "repaired": True})
            found.repaired.append(f"{aid}: refused but still counted as {mine['state']} → not_sent")
            return
        agreed = AGREES.get(str(mine["state"]), frozenset())
        if mine["delivery"] == "pending":
            # Only two readings are new information rather than a conflict: the platform agrees with the
            # decision we sent (so it was accepted), or it says it never took it (so it was refused).
            # A platform outcome that contradicts our decision is a disagreement even while pending —
            # repairing it would quietly adopt the platform's verdict as our own.
            if theirs in agreed:
                accepted = True
            elif theirs in REFUSED_STATUSES:
                accepted = False
            else:
                await self._alert(aid, theirs, mine, found)
                return
            async with self._pool.acquire() as conn, conn.transaction():
                changed = await PostgresRepository.record_delivery(
                    conn, aid, accepted=accepted, outcome=theirs, at=self._clock())
            if changed:
                found.repaired.append(f"{aid}: delivery pending → {'accepted' if accepted else 'refused'} "
                                      f"(the platform says {theirs})")
                log.info("reconciled %s: the platform says %s", aid, theirs, extra={"authorization_id": aid})
            return
        if theirs in agreed:
            if str(mine["platform_outcome"] or "").startswith("conflict:"):
                async with self._pool.acquire() as conn:
                    await conn.execute("update authorizations set platform_outcome=$2 where authorization_id=$1 "
                                       "and state=$3 and delivery=$4", aid, theirs, mine["state"], mine["delivery"])
            return
        await self._alert(aid, theirs, mine, found)

    async def _alert(self, aid: str, theirs: str, mine: asyncpg.Record, found: Reconciliation) -> None:
        alert = (f"{aid}: the platform says {theirs}; we have it {mine['state']} "
                 f"(delivery {mine['delivery']}). Not changed — a person must look.")
        found.alerts.append(alert)
        async with self._pool.acquire() as conn, conn.transaction():
            # Expose the disagreement in the existing outcome field, without adopting a verdict
            # or changing spend. A resolved checkout can otherwise look falsely refused in the UI.
            await conn.execute("update authorizations set platform_outcome=$2 where authorization_id=$1 "
                               "and state=$3 and delivery=$4", aid, f"conflict:{theirs}", mine["state"], mine["delivery"])
            # The same disagreement every 30 s is one disagreement, not sixty an hour: an append-only log
            # nobody can read is as bad as no log. It is recorded once and repeated only if it changes.
            already = await conn.fetchval(
                "select exists (select 1 from decision_events where authorization_id = $1 "
                "and kind = 'integrity_alert' and payload->'mismatches'->>0 = $2)", aid, alert)
            if already:
                return
            await RepositoryEvents.write(conn, aid, "integrity_alert", {"mismatches": [alert], "source": "reconcile"})
        log.error("INTEGRITY: %s", alert, extra={"authorization_id": aid})


async def reconcile(pool: asyncpg.Pool, api: PlatformAuthorizations, *,
                    run_id: str | None = None) -> Reconciliation:
    return await Reconciler(pool, api).run_once(run_id=run_id)


def summary(found: Reconciliation) -> str:
    return (f"reconciled {found.checked}: {len(found.repaired)} repaired, {len(found.alerts)} alerts, "
            f"{len(found.in_flight)} still being decided, {len(found.unknown_to_us)} not ours")
