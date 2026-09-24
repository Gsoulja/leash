"""Sends outbox rows the worker could not (DEC-007): after a crash, a restart, or a failed first send.

The worker POSTs each decision immediately and marks its row sent; this sender only picks rows older than
a grace period, so it never delays or races that first send. Rows go out in order, and a row never
overtakes an earlier unsent row for the same authorization (a resolve waits for its decision). A network error, a
5xx or a 429 is retried with exponential backoff that survives restarts (attempts and last_attempt_at are
stored). A final refusal (any other 4xx, e.g. 409 deadline_passed) is not retried forever: the row is
closed with its error recorded, for the operator. Resending an accepted decision is harmless: the platform
accepts the same answer again.
"""

import json
import logging
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

import asyncpg
import httpx

from leash.adapters.viseca_api.client import VisecaApiError

log = logging.getLogger("leash.outbox")

GRACE_SECONDS = 3.0
BASE_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 60.0
_RETRY_STATUSES = frozenset({408, 429})


class DecisionApi(Protocol):
    async def post_decision(self, authorization_id: str, decision: Mapping[str, Any]) -> Any: ...

    async def resolve(self, authorization_id: str, answer: Mapping[str, Any]) -> Any: ...


def _retryable(exc: Exception) -> bool:
    if isinstance(exc, VisecaApiError):
        return exc.status >= 500 or exc.status in _RETRY_STATUSES
    return isinstance(exc, (httpx.HTTPError, OSError, TimeoutError))


def _describe(exc: Exception) -> str:
    if isinstance(exc, VisecaApiError):
        code = (exc.error or {}).get("code", "")
        return f"HTTP {exc.status} {code}".strip()
    return f"{type(exc).__name__}: {exc}"


class OutboxSender:
    def __init__(self, pool: asyncpg.Pool, api: DecisionApi, *,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 grace_seconds: float = GRACE_SECONDS, base_backoff_seconds: float = BASE_BACKOFF_SECONDS,
                 max_backoff_seconds: float = MAX_BACKOFF_SECONDS) -> None:
        self._pool, self._api, self._clock = pool, api, clock
        self._grace = timedelta(seconds=grace_seconds)
        self._base, self._max = base_backoff_seconds, max_backoff_seconds

    async def mark_sent(self, authorization_id: str, endpoint: str = "decision") -> None:
        """The worker's immediate send succeeded: close its row so it is never resent."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """update outbox set sent_at = $3, attempts = attempts + 1, last_attempt_at = $3
                   where authorization_id = $1 and endpoint = $2 and sent_at is null""",
                authorization_id, endpoint, self._clock())

    async def send_pending(self) -> int:
        """Send every eligible unsent row once, in order. Returns how many were delivered or closed."""
        closed = 0
        tried: list[int] = []  # each row at most once per pass, so slow failures can't starve the others
        async with self._pool.acquire() as conn:  # and only rows that exist now, so every pass ends
            last_id = await conn.fetchval("select coalesce(max(id), 0) from outbox")
        while True:
            outcome = await self._send_next(tried, last_id)
            if outcome is None:
                return closed
            closed += outcome

    async def _send_next(self, tried: list[int], last_id: int) -> int | None:
        now = self._clock()
        async with self._pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """select id, authorization_id, endpoint, body, attempts from outbox
                   where sent_at is null and created_at <= $1
                     and not exists (select 1 from outbox earlier where earlier.authorization_id = outbox.authorization_id
                                     and earlier.sent_at is null and earlier.id < outbox.id)
                     and (last_attempt_at is null or last_attempt_at
                          + least($3::float8, $2::float8 * power(2, greatest(attempts - 1, 0))) * interval '1 second'
                          <= $4)
                     and id <> all($5::bigint[]) and id <= $6
                   order by id for update skip locked limit 1""",
                now - self._grace, self._base, self._max, now, tried, last_id)
            if row is None:
                return None
            tried.append(row["id"])
            body = json.loads(row["body"])
            try:
                if row["endpoint"] == "resolve":
                    await self._api.resolve(row["authorization_id"], body)
                else:
                    await self._api.post_decision(row["authorization_id"], body)
            except Exception as exc:
                retry = _retryable(exc)
                await conn.execute(
                    """update outbox set attempts = attempts + 1, last_attempt_at = $2::timestamptz, last_error = $3,
                           sent_at = case when $4::boolean then null else $2::timestamptz end where id = $1""",
                    row["id"], self._clock(), _describe(exc), retry)  # backoff counts from when it failed
                level = logging.WARNING if retry else logging.ERROR
                log.log(level, "outbox %s for %s failed (%s); %s", row["endpoint"], row["authorization_id"],
                        _describe(exc), "will retry" if retry else "closed without delivery",
                        extra={"authorization_id": row["authorization_id"]})
                return 0 if retry else 1
            await conn.execute("update outbox set attempts = attempts + 1, last_attempt_at = $2, sent_at = $2, "
                               "last_error = null where id = $1", row["id"], self._clock())
            return 1
