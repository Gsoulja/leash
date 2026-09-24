import asyncio
import json
import logging

import httpx
import pytest

from leash.adapters.viseca_api.client import (
    DEFAULT_BASE_URL,
    BootstrapSettings,
    MissingApiKey,
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
