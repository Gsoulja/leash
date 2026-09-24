"""Contract tests for solution/contracts: every example validates against its schema."""

import importlib.util
import json
import re
from pathlib import Path

import jsonschema
import pytest
import yaml
from fastapi.testclient import TestClient

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"
SPEC = yaml.safe_load((CONTRACTS / "policy-api.yaml").read_text())
EVENTS_MD = (CONTRACTS / "events.md").read_text()
METHODS = {"get", "post", "put", "patch", "delete"}

# What the app screens need (LEASH-092–096): if one is missing, the contract is incomplete.
APP_OPERATIONS = {
    ("post", "/api/policies/drafts"), ("post", "/api/policies/drafts/{draft_id}/answers"),
    ("post", "/api/policies/drafts/{draft_id}/submit"), ("post", "/api/policies/drafts/{draft_id}/confirm"),
    ("get", "/api/mandates/{mandate_id}"), ("post", "/api/mandates/{mandate_id}/tighten"),
    ("delete", "/api/mandates/{mandate_id}"), ("post", "/api/runs"), ("get", "/api/runs/{run_id}"),
    ("get", "/api/payments"), ("get", "/api/payments/{authorization_id}"), ("get", "/api/asks"),
    ("post", "/api/asks/{authorization_id}/answer"), ("get", "/api/spending"), ("get", "/api/events"),
    # reconnect / read model (LEASH-124): find current mandate and run, mandate history, reload a draft
    ("get", "/api/mandates"), ("get", "/api/mandates/{mandate_id}/versions"), ("get", "/api/runs"),
    ("get", "/api/policies/drafts/{draft_id}"),
}


def validator(schema: dict) -> jsonschema.Draft202012Validator:
    # Resolve "#/components/..." refs against the whole spec.
    return jsonschema.Draft202012Validator({"components": SPEC["components"], **schema})


def operations():
    for path, item in SPEC["paths"].items():
        for method, op in item.items():
            if method in METHODS:
                yield path, method, op


def json_examples():
    """(id, schema, example) for every JSON request and response example in the spec."""
    for path, method, op in operations():
        body = op.get("requestBody", {}).get("content", {}).get("application/json")
        if body:
            for name, ex in body.get("examples", {}).items():
                yield f"{method} {path} request {name}", body["schema"], ex["value"]
        for status, resp in op.get("responses", {}).items():
            media = resp.get("content", {}).get("application/json")
            if media:
                for name, ex in media.get("examples", {}).items():
                    yield f"{method} {path} {status} {name}", media["schema"], ex["value"]


EXAMPLES = list(json_examples())


def test_spec_is_a_valid_openapi_3_1_document():
    assert SPEC["openapi"].startswith("3.1")
    assert SPEC["info"]["title"] and SPEC["info"]["version"]


def test_every_app_operation_is_in_the_contract():
    present = {(m, p) for p, m, _ in operations()}
    assert APP_OPERATIONS <= present, APP_OPERATIONS - present


@pytest.mark.parametrize("path,method,op", list(operations()), ids=lambda v: v if isinstance(v, str) else "")
def test_every_operation_has_examples_for_bodies_and_success(path, method, op):
    assert op.get("operationId"), f"{method} {path} needs an operationId"
    body = op.get("requestBody", {}).get("content", {}).get("application/json")
    if body:
        assert body.get("examples"), f"{method} {path} request needs an example"
    ok = [s for s in op["responses"] if s.startswith("2")]
    assert ok, f"{method} {path} has no success response"
    for status in ok:
        content = op["responses"][status].get("content", {})
        assert any(m.get("examples") for m in content.values()), f"{method} {path} {status} needs an example"


@pytest.mark.parametrize("name,schema,example", EXAMPLES, ids=[e[0] for e in EXAMPLES])
def test_example_payload_validates(name, schema, example):
    errors = sorted(validator(schema).iter_errors(example), key=str)
    assert not errors, "; ".join(e.message for e in errors)


def test_money_is_never_a_json_number():
    def walk(node, where):
        if isinstance(node, dict):
            for k, v in node.items():
                if k.endswith("_chf") or k in {"amount", "unit_price"}:
                    assert v is None or isinstance(v, str), f"{where}.{k} must be a decimal string or null, got {v!r}"
                walk(v, f"{where}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{where}[{i}]")

    for name, _, example in EXAMPLES:
        walk(example, name)


def test_errors_use_the_viseca_error_shape():
    err = validator({"$ref": "#/components/schemas/Error"})
    err.validate({"error": {"code": "not_waiting", "message": "This payment is no longer waiting for an answer."}})
    with pytest.raises(jsonschema.ValidationError):
        err.validate({"message": "flat errors are not allowed"})


# ---------- event stream ----------
EVENT_BLOCK = re.compile(r"^### `([a-z_.]+)`.*?```json\n(.*?)```", re.S | re.M)
EVENT_DOCS = EVENT_BLOCK.findall(EVENTS_MD)


def test_events_md_documents_every_event_type_in_the_spec():
    spec_types = set(SPEC["components"]["schemas"]["StreamEvent"]["properties"]["type"]["enum"])
    documented = {t for t, _ in EVENT_DOCS}
    assert documented == spec_types


@pytest.mark.parametrize("event_type,payload", EVENT_DOCS, ids=[t for t, _ in EVENT_DOCS])
def test_event_examples_validate(event_type, payload):
    event = json.loads(payload)
    assert event["type"] == event_type
    validator({"$ref": "#/components/schemas/StreamEvent"}).validate(event)


def test_events_endpoint_is_server_sent_events():
    op = SPEC["paths"]["/api/events"]["get"]
    assert "text/event-stream" in op["responses"]["200"]["content"]
    assert any(p["name"] == "Last-Event-ID" and p["in"] == "header" for p in op.get("parameters", []))


# ---------- mock server ----------
def load_mock():
    spec = importlib.util.spec_from_file_location("mock_server", CONTRACTS / "mock_server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return TestClient(module.app)


def test_mock_server_serves_the_first_example_of_every_operation():
    client = load_mock()
    for path, method, op in operations():
        if path == "/api/events":
            continue
        concrete = re.sub(r"\{[^}]+\}", "X1", path)
        body = None
        req = op.get("requestBody", {}).get("content", {}).get("application/json")
        if req:
            body = next(iter(req["examples"].values()))["value"]
        response = client.request(method.upper(), concrete, json=body)
        status = min(s for s in op["responses"] if s.startswith("2"))
        assert response.status_code == int(status), f"{method} {path}"
        expected = next(iter(op["responses"][status]["content"]["application/json"]["examples"].values()))["value"]
        assert response.json() == expected, f"{method} {path}"


def test_mock_server_streams_documented_events():
    client = load_mock()
    with client.stream("GET", "/api/events") as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        text = "".join(response.iter_text())
    types = re.findall(r"^event: (.+)$", text, re.M)
    assert set(types) == {t for t, _ in EVENT_DOCS}


def test_payment_states_cover_every_cockpit_status():
    # LEASH-093: paid, waiting, blocked (declined), no answer (timed out) and not sent are distinct.
    states = SPEC["components"]["schemas"]["Payment"]["properties"]["final_state"]["enum"]
    assert set(states) == {"approved", "waiting", "declined", "timed_out", "not_sent"}


def test_a_payment_that_was_never_sent_is_expressible():
    detail = SPEC["paths"]["/api/payments/{authorization_id}"]["get"]["responses"]["200"]["content"]["application/json"]
    not_sent = [ex["value"] for ex in detail["examples"].values() if ex["value"]["final_state"] == "not_sent"]
    assert not_sent and all(v["sent_to_viseca"] is None and v["engine_verdict"] is None for v in not_sent)


@pytest.mark.parametrize("event_type,payload", EVENT_DOCS, ids=[t for t, _ in EVENT_DOCS])
def test_event_payload_fields_are_schema_checked(event_type, payload):
    event = json.loads(payload)
    event["data"] = {"unexpected": True}
    with pytest.raises(jsonschema.ValidationError):
        validator({"$ref": "#/components/schemas/StreamEvent"}).validate(event)


def test_sse_sample_in_the_spec_is_a_valid_event():
    sample = SPEC["paths"]["/api/events"]["get"]["responses"]["200"]["content"]["text/event-stream"]["examples"]["ask"]["value"]
    data = json.loads(re.search(r"^data: (.+)$", sample, re.M).group(1))
    validator({"$ref": "#/components/schemas/StreamEvent"}).validate(data)
