"""LEASH-175: the engine forwards the chat's calls to the permission assistant.

The engine serves the app's bundle, so the browser's origin is the engine. The assistant is a separate
process — the engine imports nothing from it — so the one thing the engine does for it is pass the
request along. Forwarding is not authority: the engine does not read, validate or store anything here.
"""

import ast
import inspect

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from leash.adapters.http import assistant_proxy
from leash.adapters.http.assistant_proxy import assistant_router


def app_with(handler, base_url="http://assistant:8100"):
    app = FastAPI()
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=base_url)
    app.include_router(assistant_router(base_url, client=client))
    return TestClient(app)


def test_a_chat_call_reaches_the_assistant_and_its_answer_comes_back():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["body"] = str(request.url), request.content
        return httpx.Response(200, json={"draft": {"draft_id": "LD-1"}, "consent_text": [],
                                         "questions": [], "status": "ready"})

    response = app_with(handler).post("/api/permission/drafts", json={"text": "at most CHF 50"})
    assert response.status_code == 200
    assert response.json()["draft"]["draft_id"] == "LD-1"
    assert seen["url"] == "http://assistant:8100/api/permission/drafts"
    assert b"at most CHF 50" in seen["body"]


def test_the_assistants_own_refusal_is_passed_through_unchanged():
    """A 422 from the assistant is the customer's answer, not an engine error."""
    handler = lambda r: httpx.Response(422, json={"error": {"code": "invalid_request", "message": "no"}})
    response = app_with(handler).post("/api/permission/drafts", json={"text": "x"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_an_assistant_that_is_not_running_says_so_rather_than_404():
    def handler(request):
        raise httpx.ConnectError("no route to host")

    response = app_with(handler).post("/api/permission/drafts", json={"text": "x"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "assistant_unavailable"


def test_without_a_configured_assistant_the_chat_is_told_plainly():
    app = FastAPI()
    app.include_router(assistant_router(None))
    response = TestClient(app).post("/api/permission/drafts", json={"text": "x"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "assistant_unavailable"


def test_the_engine_still_imports_nothing_from_the_assistant_package():
    """The proxy is HTTP only. An import would put the model's package in the decision process."""
    tree = ast.parse(inspect.getsource(assistant_proxy))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    assert not [n for n in names if n == "assistant" or n.startswith("assistant.")], sorted(names)


# --- LEASH-102: the chat route is a permission route, never a payment one ----------------------

@pytest.mark.parametrize("path", ["/api/runs", "/api/policies/drafts/LD-1/confirm",
                                  "/api/mandates/TM-1/tighten", "/api/asks/AU-1/answer"])
def test_the_chat_route_cannot_start_a_run_or_answer_a_decision(path):
    """The permission chat's credential reaches `/api/permission/*` and nothing else.

    The assistant is untrusted by construction: if its route could start a run or answer an ask, a
    model that talked its way into the chat would be holding the payment path. The proxy is mounted
    under one prefix, so these are not its routes at all — asserted rather than assumed, because a
    future prefix widening would be invisible otherwise.
    """
    reached = []

    def handler(request: httpx.Request) -> httpx.Response:
        reached.append(str(request.url))
        return httpx.Response(200, json={})

    assert app_with(handler).post(path, json={}).status_code == 404
    assert reached == [], "the chat route forwarded a request it must not carry"
