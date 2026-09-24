import asyncio
import json
import logging

import httpx
import pytest

from leash.adapters.viseca_api.client import (
    DEFAULT_BASE_URL,
    DEFAULT_MAX_CONNECTIONS,
    LONG_POLL_MARGIN_SECONDS,
    BootstrapSettings,
    ClientClosed,
    MissingApiKey,
    PoolSettings,
    VisecaApiError,
    VisecaClient,
)

KEY = "team-secret-key-123"


class Recorder:
    """Mock transport: returns canned responses by (method, path) and records every request."""

    def __init__(self, routes: dict[tuple[str, str], httpx.Response]):
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.routes.get((request.method, request.url.path), httpx.Response(404, json={"error": {"code": "not_found"}}))


def client_for(routes, **kw) -> tuple[VisecaClient, Recorder]:
    rec = Recorder(routes)
    return VisecaClient(api_key=KEY, transport=httpx.MockTransport(rec), **kw), rec


def run(coro):
    return asyncio.run(coro)


def test_204_means_no_work():
    # A 204 carries no body; the client must not try to parse one.
    c, _ = client_for({("GET", "/v1/decision-requests/next"): httpx.Response(204, content=b"not json at all")})
    assert run(c.next_decision_request()) is None


def test_200_returns_the_envelope():
    envelope = {"run_id": "RUN1", "event_id": "EV1", "data": {"type": "authorization.request"}}
    c, rec = client_for({("GET", "/v1/decision-requests/next"): httpx.Response(200, json=envelope)})
    assert run(c.next_decision_request(wait=25)) == envelope
    assert rec.requests[0].url.params["wait"] == "25"


def test_non_2xx_raises_with_the_api_error_object():
    body = {"error": {"code": "unauthorized", "message": "A valid team bearer token is required"}}
    c, _ = client_for({("GET", "/v1/bootstrap"): httpx.Response(401, json=body)})
    with pytest.raises(VisecaApiError) as exc:
        run(c.bootstrap())
    assert exc.value.status == 401
    assert exc.value.error == body["error"]
    assert "unauthorized" in str(exc.value)


def test_non_json_error_still_raises():
    c, _ = client_for({("GET", "/v1/bootstrap"): httpx.Response(502, text="Bad gateway")})
    with pytest.raises(VisecaApiError) as exc:
        run(c.bootstrap())
    assert exc.value.status == 502 and exc.value.error is None


def test_bearer_key_sent_everywhere_except_healthz():
    c, rec = client_for({
        ("GET", "/healthz"): httpx.Response(200, json={"status": "ok"}),
        ("GET", "/v1/reference-data"): httpx.Response(200, json={}),
    })
    run(c.healthz())
    run(c.reference_data())
    assert "authorization" not in rec.requests[0].headers
    assert rec.requests[1].headers["authorization"] == f"Bearer {KEY}"


def test_key_comes_from_team_api_key(monkeypatch):
    monkeypatch.setenv("TEAM_API_KEY", KEY)
    monkeypatch.delenv("LEASH_BASE_URL", raising=False)
    c = VisecaClient.from_env()
    assert c.base_url == DEFAULT_BASE_URL
    monkeypatch.delenv("TEAM_API_KEY")
    with pytest.raises(MissingApiKey, match="TEAM_API_KEY"):
        VisecaClient.from_env()


def test_key_is_never_logged_or_shown(caplog):
    caplog.set_level(logging.DEBUG)
    body = {"error": {"code": "bad_request", "message": "nope"}}
    c, _ = client_for({("POST", "/v1/mandates"): httpx.Response(400, json=body)})
    with pytest.raises(VisecaApiError) as exc:
        run(c.create_mandate({"instruction": "x"}))
    assert KEY not in caplog.text
    assert KEY not in repr(c) and KEY not in str(exc.value) and KEY not in repr(exc.value)


def test_timeouts_are_configurable_and_long_poll_outlasts_wait():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen[request.url.path] = request.extensions["timeout"]
        return httpx.Response(204)

    c = VisecaClient(api_key=KEY, timeout=7.5, transport=httpx.MockTransport(handler))
    run(c.next_decision_request(wait=25))
    assert seen["/v1/decision-requests/next"]["read"] >= 25 + 5
    c2 = VisecaClient(api_key=KEY, timeout=7.5, transport=httpx.MockTransport(lambda r: seen.__setitem__("t", r.extensions["timeout"]) or httpx.Response(200, json={})))
    run(c2.reference_data())
    assert seen["t"]["read"] == 7.5


ENDPOINTS = [
    ("healthz", (), "GET", "/healthz", None),
    ("bootstrap", (), "GET", "/v1/bootstrap", None),
    ("reference_data", (), "GET", "/v1/reference-data", None),
    ("create_mandate", ({"instruction": "i", "hard_rules": []},), "POST", "/v1/mandates", {"instruction": "i", "hard_rules": []}),
    ("confirm_mandate", ("DR1",), "POST", "/v1/mandates/DR1/confirm", {"confirmed": True}),
    ("get_mandate", ("TM1",), "GET", "/v1/mandates/TM1", None),
    ("patch_mandate", ("TM1", {"uncertainty_policy": "decline"}), "PATCH", "/v1/mandates/TM1", {"uncertainty_policy": "decline"}),
    ("revoke_mandate", ("TM1",), "DELETE", "/v1/mandates/TM1", None),
    ("start_run", ("SCEN0000", "TM1"), "POST", "/v1/scenario-runs", {"scenario_id": "SCEN0000", "mandate_id": "TM1"}),
    ("get_run", ("RUN1",), "GET", "/v1/scenario-runs/RUN1", None),
    ("post_decision", ("AZ1", {"authorization_id": "AZ1", "decision": "approve"}), "POST", "/v1/authorizations/AZ1/decision", {"authorization_id": "AZ1", "decision": "approve"}),
    ("resolve", ("AZ1", {"decision": "decline"}), "POST", "/v1/authorizations/AZ1/resolve", {"decision": "decline"}),
    ("list_authorizations", (), "GET", "/v1/authorizations", None),
    ("events", (7,), "GET", "/v1/events", None),
]


@pytest.mark.parametrize("method_name,args,verb,path,body", ENDPOINTS, ids=[e[0] for e in ENDPOINTS])
def test_every_endpoint_we_use(method_name, args, verb, path, body):
    c, rec = client_for({(verb, path): httpx.Response(200, json={"ok": True})})
    result = run(getattr(c, method_name)(*args))
    assert (result.raw if isinstance(result, BootstrapSettings) else result) == {"ok": True}
    req = rec.requests[0]
    assert (req.method, req.url.path) == (verb, path)
    if body is not None:
        assert json.loads(req.content) == body


def test_events_passes_the_cursor():
    c, rec = client_for({("GET", "/v1/events"): httpx.Response(200, json={"events": [], "next_cursor": 9})})
    run(c.events(since=7))
    assert rec.requests[0].url.params["since"] == "7"


def test_history_csv_is_returned_as_text():
    csv = "authorization_id,card_id\nTR00001,CA0001\n"
    c, _ = client_for({("GET", "/v1/reference-data/authorization-history.csv"): httpx.Response(200, text=csv)})
    assert run(c.authorization_history_csv()) == csv


def test_bootstrap_is_parsed_into_typed_settings():
    body = {
        "api_version": "0.1.0", "data_version": "saw26",
        "timeouts": {"decision_seconds": 8, "human_window_seconds": 90},
        "scenarios": [{"scenario_id": "SCEN0000"}], "limits": {"max_runs": 5}, "features": {"reset": True},
    }
    c, _ = client_for({("GET", "/v1/bootstrap"): httpx.Response(200, json=body)})
    s = run(c.bootstrap())
    assert isinstance(s, BootstrapSettings)
    assert (s.api_version, s.data_version) == ("0.1.0", "saw26")
    assert s.human_window_seconds == 90 and s.decision_timeout_seconds == 8
    assert s.defaults_used == set()
    assert s.raw == body


def test_bootstrap_unknown_shape_falls_back_to_documented_defaults_visibly():
    c, _ = client_for({("GET", "/v1/bootstrap"): httpx.Response(200, json={"something": "else"})})
    s = run(c.bootstrap())
    assert s.human_window_seconds == 120 and s.decision_timeout_seconds == 8
    assert s.defaults_used == {"human_window_seconds", "decision_timeout_seconds"}


# --- LEASH-136: one pooled client, budgets that never outlive the deadline ---------------------

class Counting(httpx.AsyncBaseTransport):
    """Counts how many transports were opened and how many requests each served."""

    def __init__(self, fail_times: int = 0, response: httpx.Response | None = None):
        self.requests: list[httpx.Request] = []
        self.fail_times = fail_times
        self.response = response or httpx.Response(200, json={})
        self.closed = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if len(self.requests) <= self.fail_times:
            raise httpx.ConnectError("boom", request=request)
        return self.response

    async def aclose(self) -> None:
        self.closed += 1


def test_one_pooled_client_serves_every_request():
    transport = Counting()
    c = VisecaClient(api_key=KEY, transport=transport)

    async def go():
        await c.reference_data()
        first = c._client()
        await c.list_authorizations()
        assert c._client() is first  # the same pool, not a fresh one per request
        await c.aclose()

    run(go())
    assert len(transport.requests) == 2


def test_the_pool_is_closed_exactly_once_and_never_reopened():
    transport = Counting()
    c = VisecaClient(api_key=KEY, transport=transport)

    async def go():
        await c.reference_data()
        await c.aclose()
        await c.aclose()  # a second shutdown pass must not explode
        assert c.closed
        with pytest.raises(ClientClosed):
            await c.reference_data()

    run(go())
    assert transport.closed == 1


def test_nothing_is_opened_until_the_first_request():
    transport = Counting()
    c = VisecaClient(api_key=KEY, transport=transport)
    assert c._http is None
    run(c.aclose())
    assert transport.closed == 0


def test_async_with_opens_and_closes_the_pool():
    transport = Counting()

    async def go():
        async with VisecaClient(api_key=KEY, transport=transport) as c:
            assert c._http is not None
            await c.reference_data()
        return c

    c = run(go())
    assert c.closed and transport.closed == 1


def test_connection_limits_and_keepalive_are_configurable():
    pool = PoolSettings(max_connections=3, max_keepalive_connections=2, keepalive_expiry_seconds=1.5)
    c = VisecaClient(api_key=KEY, transport=Counting(), pool=pool)
    limits = pool.limits()
    assert (limits.max_connections, limits.max_keepalive_connections, limits.keepalive_expiry) == (3, 2, 1.5)
    assert c.pool is pool
    run(c.aclose())


def test_pool_settings_come_from_the_environment():
    env = {"LEASH_HTTP_MAX_CONNECTIONS": "5", "LEASH_HTTP_MAX_KEEPALIVE_CONNECTIONS": "4",
           "LEASH_HTTP_KEEPALIVE_EXPIRY_SECONDS": "2.5", "LEASH_HTTP_CONNECT_TIMEOUT_SECONDS": "1.25",
           "LEASH_HTTP_RETRIES": "0"}
    pool = PoolSettings.from_env(env)
    assert (pool.max_connections, pool.max_keepalive_connections) == (5, 4)
    assert (pool.keepalive_expiry_seconds, pool.connect_timeout_seconds, pool.retries) == (2.5, 1.25, 0)


def test_an_unreadable_setting_falls_back_to_the_default():
    pool = PoolSettings.from_env({"LEASH_HTTP_MAX_CONNECTIONS": "lots"})
    assert pool.max_connections == DEFAULT_MAX_CONNECTIONS


def test_the_decision_post_timeout_is_the_remaining_budget():
    transport = Counting()
    c = VisecaClient(api_key=KEY, timeout=10.0, transport=transport)
    run(c.post_decision("AZ1", {"decision": "approve"}, 1.5))
    seen = transport.requests[0].extensions["timeout"]
    assert seen["read"] == seen["write"] == seen["pool"] == 1.5
    assert seen["connect"] == 1.5  # even connecting may not outlive the budget
    run(c.aclose())


def test_the_decision_post_falls_back_to_the_client_timeout_without_a_budget():
    transport = Counting()
    c = VisecaClient(api_key=KEY, timeout=4.0, transport=transport)
    run(c.post_decision("AZ1", {"decision": "approve"}))
    assert transport.requests[0].extensions["timeout"]["read"] == 4.0
    run(c.aclose())


def test_the_long_poll_budget_stays_separate_from_the_decision_send_budget():
    transport = Counting(response=httpx.Response(204))
    c = VisecaClient(api_key=KEY, timeout=8.0, transport=transport)

    async def go():
        await c.next_decision_request(wait=25)
        await c.post_decision("AZ1", {"decision": "approve"}, 1.0)

    run(go())
    poll, send = (r.extensions["timeout"] for r in transport.requests)
    assert poll["read"] == 25 + LONG_POLL_MARGIN_SECONDS
    assert send["read"] == 1.0  # sending an answer is not a 35-second wait


def test_a_safe_request_is_retried_inside_its_budget():
    transport = Counting(fail_times=1)
    c = VisecaClient(api_key=KEY, transport=transport, pool=PoolSettings(retries=1))
    assert run(c.reference_data()) == {}
    assert len(transport.requests) == 2  # one failure, one retry, same pool
    run(c.aclose())


def test_a_decision_post_is_never_retried():
    """The platform documents no idempotency guarantee for it; the outbox resends instead."""
    transport = Counting(fail_times=1)
    c = VisecaClient(api_key=KEY, transport=transport, pool=PoolSettings(retries=3))
    with pytest.raises(httpx.ConnectError):
        run(c.post_decision("AZ1", {"decision": "approve"}, 2.0))
    assert len(transport.requests) == 1
    run(c.aclose())


def test_no_retry_once_the_budget_is_spent():
    transport = Counting(fail_times=5)
    c = VisecaClient(api_key=KEY, transport=transport, pool=PoolSettings(retries=5))
    with pytest.raises(httpx.ConnectError):
        run(c._json("GET", "/v1/reference-data", timeout=0.0))
    assert len(transport.requests) == 1  # the budget was already gone; nothing is tried twice
    run(c.aclose())


def test_pool_exhaustion_surfaces_as_a_transport_error_not_a_hang():
    """A request that cannot get a connection inside the budget fails; it never waits forever."""

    class Exhausted(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            raise httpx.PoolTimeout("no free connection", request=request)

    c = VisecaClient(api_key=KEY, transport=Exhausted(), pool=PoolSettings(retries=0))
    with pytest.raises(httpx.PoolTimeout):
        run(c.post_decision("AZ1", {"decision": "approve"}, 0.5))
    run(c.aclose())


def test_only_one_async_client_is_ever_constructed(monkeypatch):
    """Identity is not enough on its own: count the constructions, not just compare two handles."""
    made: list[httpx.AsyncClient] = []
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: made.append(real(**kw)) or made[-1])
    c = VisecaClient(api_key=KEY, transport=Counting())

    async def go():
        await c.reference_data()
        await c.list_authorizations()
        await c.healthz()
        await c.aclose()

    run(go())
    assert len(made) == 1


def test_a_startup_failure_still_closes_the_pool():
    """What the worker relies on: the pool is open before bootstrap can fail, so the close must not
    live in a try/finally that failure never reaches."""
    transport = Counting()
    c = VisecaClient(api_key=KEY, transport=transport)

    async def go():
        async with c:
            raise RuntimeError("bootstrap failed (incompatible api_version)")

    with pytest.raises(RuntimeError):
        run(go())
    assert c.closed and transport.closed == 1


def test_the_configured_limits_reach_the_real_connection_pool():
    """Without a fake transport, so the numbers land where the sockets actually are.

    httpcore's attributes are private; there is no public reader for them, and asserting on
    `PoolSettings.limits()` alone would pass even if the client never passed them on.
    """
    c = VisecaClient(api_key=KEY, pool=PoolSettings(max_connections=3, max_keepalive_connections=2,
                                                    keepalive_expiry_seconds=1.5))
    inner = c._client()._transport._pool  # type: ignore[attr-defined]
    assert (inner._max_connections, inner._max_keepalive_connections, inner._keepalive_expiry) == (3, 2, 1.5)
    run(c.aclose())


def test_a_negative_retry_setting_still_sends_once():
    """An out-of-range number is as unusable as an unreadable one: it must never skip the request."""
    assert PoolSettings.from_env({"LEASH_HTTP_RETRIES": "-1"}).retries == 0
    assert PoolSettings.from_env({"LEASH_HTTP_MAX_CONNECTIONS": "0"}).max_connections == 1
    transport = Counting()
    c = VisecaClient(api_key=KEY, transport=transport, pool=PoolSettings(retries=-1))
    assert run(c.reference_data()) == {}
    assert len(transport.requests) == 1
    run(c.aclose())


def test_the_pool_reuses_one_tcp_connection_across_requests():
    """The point of the ticket: a real socket, counted. A fake transport can't show this."""

    async def go() -> tuple[int, int]:
        accepted = 0

        async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            nonlocal accepted
            accepted += 1
            try:
                while not reader.at_eof():  # keep-alive: answer request after request on the same socket
                    head = await reader.readuntil(b"\r\n\r\n")
                    if not head:
                        return
                    writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                                 b"Content-Length: 2\r\n\r\n{}")
                    await writer.drain()
            except (asyncio.IncompleteReadError, ConnectionResetError):
                return

        server = await asyncio.start_server(serve, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        client = VisecaClient(api_key=KEY, base_url=f"http://127.0.0.1:{port}",
                              pool=PoolSettings(keepalive_expiry_seconds=30.0))
        try:
            async with client:
                for _ in range(4):
                    await client.reference_data()
        finally:
            server.close()  # not wait_closed(): it waits on a handler that is already parked on EOF
        return accepted, 4

    accepted, requests = run(go())
    assert requests == 4
    assert accepted == 1, f"{requests} requests opened {accepted} connections; the pool is not reusing one"
