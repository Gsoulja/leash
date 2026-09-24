"""Transport behaviour of VisecaClient (LEASH-136): one pooled connection, a closed lifecycle, and
timeouts derived from the operation's budget rather than one scalar.

Connection reuse is proved at the socket level against a real local HTTP/1.1 keep-alive server that
counts accepted TCP connections — asserting that two calls share one client object would only prove we
kept a reference, not that we stopped paying for a handshake per request.
"""

import asyncio

import httpx
import pytest

from keepalive_server import CountingServer, HangsUpAfterReadingTheBody, serving
from leash.adapters.viseca_api.client import VisecaClient

KEY = "team-secret-key-123"


# --- criterion 1: one managed client, reused for the service lifetime ---------------------------------

def test_repeated_requests_reuse_one_connection():
    async def go():
        async with serving() as (server, base):
            client = VisecaClient(KEY, base)
            try:
                for _ in range(5):
                    await client.healthz()
            finally:
                await client.aclose()
            return server

    server = asyncio.run(go())
    assert server.requests == 5
    assert server.connections == 1, f"expected one pooled connection, the server accepted {server.connections}"


def test_the_underlying_client_is_the_same_object_across_calls():
    async def go():
        async with serving() as (_, base):
            client = VisecaClient(KEY, base)
            try:
                await client.healthz()
                first = client.http
                await client.healthz()
                assert client.http is first
            finally:
                await client.aclose()

    asyncio.run(go())


# --- criterion 2: created and closed exactly once ------------------------------------------------------

def test_concurrent_first_use_shares_one_pool():
    """Eight callers race for the first use. With one connection allowed they queue on it and share it;
    a client built per request (the old behaviour) would open eight sockets regardless of the limit."""

    async def go():
        async with serving() as (server, base):
            client = VisecaClient(KEY, base, max_connections=1)
            try:
                same = [client.http for _ in range(8)]
                await asyncio.gather(*(client.healthz() for _ in range(8)))
                assert all(c is same[0] for c in same)
            finally:
                await client.aclose()
            return server

    server = asyncio.run(go())
    assert server.requests == 8
    assert server.connections == 1, f"the pool limit was not honoured ({server.connections} connections)"


def test_close_is_idempotent_and_the_client_reports_closed():
    async def go():
        async with serving() as (_, base):
            client = VisecaClient(KEY, base)
            await client.healthz()
            await client.aclose()
            await client.aclose()  # a second shutdown must not raise
            assert client.is_closed

    asyncio.run(go())


def test_a_closed_client_refuses_further_requests():
    async def go():
        async with serving() as (_, base):
            client = VisecaClient(KEY, base)
            await client.healthz()
            await client.aclose()
            with pytest.raises(RuntimeError, match="closed"):
                await client.healthz()

    asyncio.run(go())


def test_it_works_as_an_async_context_manager():
    async def go():
        async with serving() as (server, base):
            async with VisecaClient(KEY, base) as client:
                await client.healthz()
                await client.healthz()
            assert client.is_closed
            return server

    server = asyncio.run(go())
    assert server.connections == 1


# --- criterion 3: connection limits and keep-alive expiry are configurable -----------------------------

def test_connection_limits_and_keepalive_expiry_are_configurable():
    client = VisecaClient(KEY, "http://x", max_connections=7, max_keepalive_connections=3,
                          keepalive_expiry_seconds=11.5)
    limits = client.limits
    assert (limits.max_connections, limits.max_keepalive_connections, limits.keepalive_expiry) == (7, 3, 11.5)


def test_limits_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("TEAM_API_KEY", KEY)
    monkeypatch.setenv("LEASH_HTTP_MAX_CONNECTIONS", "12")
    monkeypatch.setenv("LEASH_HTTP_MAX_KEEPALIVE_CONNECTIONS", "6")
    monkeypatch.setenv("LEASH_HTTP_KEEPALIVE_EXPIRY_SECONDS", "45")
    client = VisecaClient.from_env()
    assert (client.limits.max_connections, client.limits.max_keepalive_connections,
            client.limits.keepalive_expiry) == (12, 6, 45.0)


def test_pool_exhaustion_surfaces_as_a_timeout_rather_than_an_extra_connection():
    """One connection allowed, held by a slow first call: the second waits, and when its pool timeout
    runs out it fails loudly instead of quietly opening a connection past the limit."""

    async def go():
        async with serving(delay=0.5) as (server, base):
            client = VisecaClient(KEY, base, max_connections=1, pool_timeout_seconds=0.05)
            try:
                first = asyncio.ensure_future(client.healthz())
                await asyncio.sleep(0.1)  # the first call now holds the only connection
                results = await asyncio.gather(first, client.healthz(), return_exceptions=True)
                return results, server
            finally:
                await client.aclose()

    results, server = asyncio.run(go())
    assert any(isinstance(r, httpx.PoolTimeout) for r in results), results
    assert server.connections == 1, f"the limit was exceeded ({server.connections} connections)"


# --- criterion 5: the long poll's timeout is separate from every other call's --------------------------

def test_the_long_poll_timeout_is_separate_from_the_decision_send_timeout():
    seen: dict[str, httpx.Timeout] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen[request.url.path] = request.extensions["timeout"]
        return httpx.Response(200, json={})

    async def go():
        client = VisecaClient(KEY, "http://x", timeout=7.5, transport=httpx.MockTransport(handler))
        try:
            await client.next_decision_request(wait=25)
            await client.post_decision("AZ-1", {"decision": "approve"})
        finally:
            await client.aclose()

    asyncio.run(go())
    poll = seen["/v1/decision-requests/next"]
    send = seen["/v1/authorizations/AZ-1/decision"]
    assert poll["read"] >= 25, "the long poll must outlast its own wait"
    assert send["read"] == 7.5, "the decision send must not inherit the long poll's read timeout"
    assert poll["read"] != send["read"]


# --- criterion 4/6: a per-call budget bounds the request, and retries stay inside it -------------------

def test_a_budget_bounds_every_phase_of_the_request():
    seen: dict[str, httpx.Timeout] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen[request.url.path] = request.extensions["timeout"]
        return httpx.Response(200, json={})

    async def go():
        client = VisecaClient(KEY, "http://x", timeout=30.0, transport=httpx.MockTransport(handler))
        try:
            await client.post_decision("AZ-1", {"decision": "approve"}, budget_seconds=1.25)
        finally:
            await client.aclose()

    asyncio.run(go())
    timeout = seen["/v1/authorizations/AZ-1/decision"]
    # Every phase is bounded by the remaining budget, not by the generous default.
    assert timeout["connect"] <= 1.25 and timeout["read"] <= 1.25
    assert timeout["write"] <= 1.25 and timeout["pool"] <= 1.25


def test_a_budget_that_has_already_run_out_is_refused_without_a_request():
    tried: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        tried.append(request)
        return httpx.Response(200, json={})

    async def go():
        client = VisecaClient(KEY, "http://x", transport=httpx.MockTransport(handler))
        try:
            with pytest.raises(TimeoutError):
                await client.post_decision("AZ-1", {"decision": "approve"}, budget_seconds=0)
        finally:
            await client.aclose()

    asyncio.run(go())
    assert tried == [], "nothing may go out once the budget is gone"


def test_the_configured_connect_retry_count_reaches_the_connection_pool():
    """Retries are a *connection* setting: httpcore retries inside `_connect()`, before the request is
    written, so a POST body is never replayed. This pins that the count actually reaches the pool."""
    client = VisecaClient(KEY, "http://x", connect_retries=2)
    assert client.connect_retries == 2
    transport = client.http._transport
    assert getattr(transport, "_pool", None) is not None
    assert transport._pool._retries == 2


def test_a_write_failure_is_not_retried_so_a_posted_body_is_never_replayed():
    """The no-replay property itself: once the request is being handled, a failure surfaces to us
    rather than being resent — a second /decision POST must never be issued by the transport."""
    attempts: list[httpx.Request] = []

    class FailsWhileWriting(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            attempts.append(request)
            raise httpx.WriteError("connection dropped mid-body")

    async def go():
        client = VisecaClient(KEY, "http://x", transport=FailsWhileWriting(), connect_retries=3)
        try:
            with pytest.raises(httpx.WriteError):
                await client.post_decision("AZ-1", {"decision": "approve"})
        finally:
            await client.aclose()

    asyncio.run(go())
    assert len(attempts) == 1, f"the body was sent {len(attempts)} times"


# --- criterion 2: the pool belongs to the loop it was used in -----------------------------------------

def test_closing_from_a_second_event_loop_fails_on_a_real_connection():
    """Why `service.serve_until_stopped` exists (LEASH-136).

    A pooled keep-alive socket is bound to the loop that opened it. Serving under one `asyncio.run` and
    then closing under another — which is what `uvicorn.run(...)` followed by `asyncio.run(aclose())`
    does — tears the transport down against a closed loop. This pins the hazard with a real socket; an
    in-memory ASGI transport cannot show it, because it owns no socket at all.
    """

    left_open: dict[str, VisecaClient] = {}

    async def loop_a() -> None:
        server = CountingServer()
        base = await server.start()
        client = VisecaClient(KEY, base)
        await client.healthz()  # opens a connection that stays keep-alive in the pool
        left_open["client"] = client  # deliberately not closed here: that is the whole point

    asyncio.run(loop_a())  # loop A ends with a live pooled socket bound to it
    with pytest.raises(RuntimeError, match="[Ee]vent loop is closed"):
        asyncio.run(left_open["client"].aclose())  # loop B: the socket's loop is gone


def test_serving_and_closing_in_one_loop_releases_a_real_connection():
    from leash.service import serve_until_stopped

    async def go():
        async with serving() as (_, base):
            client = VisecaClient(KEY, base)

            class StubServer:
                async def serve(self):
                    await client.healthz()  # a live keep-alive connection exists when shutdown begins

            await serve_until_stopped(StubServer(), client)  # must not raise
            assert client.is_closed
            return client

    client = asyncio.run(go())
    assert client.http.is_closed


def test_a_real_failure_after_the_body_was_written_is_never_replayed():
    """The no-replay property through the real httpcore path, not a stand-in transport.

    The server accepts, reads the whole POST body, then hangs up without answering. `connect_retries`
    is deliberately high: if retries covered anything past connection setup, the platform would see the
    same decision posted twice. It must see it exactly once.
    """
    server = HangsUpAfterReadingTheBody()

    async def go():
        async with serving(server=server) as (_, base):
            client = VisecaClient(KEY, base, connect_retries=3)
            try:
                with pytest.raises((httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError)):
                    await client.post_decision("AZ-1", {"decision": "approve", "reason_codes": []})
            finally:
                await client.aclose()

    asyncio.run(go())
    assert server.requests == 1, f"the decision body reached the platform {server.requests} times"
    assert server.connections == 1, f"{server.connections} connections were opened for one POST"
