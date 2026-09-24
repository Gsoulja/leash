"""Mock of the Leash policy service, built from the contract.

Every operation in policy-api.yaml returns the first example of its success response, and
/api/events streams the examples documented in events.md. The app can be built against it
before the backend exists:

    cd solution/contracts
    uv run --project ../engine uvicorn mock_server:app --port 8787
"""

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

HERE = Path(__file__).resolve().parent
SPEC: dict[str, Any] = yaml.safe_load((HERE / "policy-api.yaml").read_text())
EVENTS = [json.loads(block) for _, block in re.findall(r"^### `([a-z_.]+)`.*?```json\n(.*?)```",
                                                         (HERE / "events.md").read_text(), re.S | re.M)]

app = FastAPI(title=SPEC["info"]["title"] + " (mock)", version=SPEC["info"]["version"])
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _first_success(op: dict[str, Any]) -> tuple[int, Any]:
    status = min(s for s in op["responses"] if s.startswith("2"))
    examples = op["responses"][status]["content"]["application/json"]["examples"]
    return int(status), next(iter(examples.values()))["value"]


def _handler(status: int, body: Any):  # type: ignore[no-untyped-def]
    async def handle(request: Request) -> JSONResponse:
        return JSONResponse(body, status_code=status)
    return handle


for path, item in SPEC["paths"].items():
    for method, op in item.items():
        if path == "/api/events" or method not in {"get", "post", "put", "patch", "delete"}:
            continue
        status, body = _first_success(op)
        app.add_api_route(path, _handler(status, body), methods=[method.upper()], name=op["operationId"])


@app.get("/api/events", name="streamEvents")
async def stream_events() -> StreamingResponse:
    def frames() -> Iterator[str]:
        for event in EVENTS:
            yield f"id: {event['id']}\nevent: {event['type']}\ndata: {json.dumps(event)}\n\n"
    return StreamingResponse(frames(), media_type="text/event-stream")
