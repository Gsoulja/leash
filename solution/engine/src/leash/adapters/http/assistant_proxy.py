"""Forward the chat's calls to the permission assistant (LEASH-175).

The engine serves the app's bundle, so the browser's origin is the engine. The assistant is a separate
process on purpose — the engine imports nothing from `solution/assistant/`, which keeps the model's
package out of the process that decides payments — so the one thing the engine does for it is pass the
request along.

Forwarding is not authority. Nothing here reads, validates, stores or answers on the assistant's
behalf; the body goes out as it arrived and the answer comes back as it was given, refusals included.
When the assistant is not configured or not running, the chat is told plainly rather than shown a 404,
because "there is no such endpoint" and "the assistant is down" are different things to a customer.
"""

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("leash.assistant_proxy")

PREFIX = "/api/permission"
DEFAULT_TIMEOUT_SECONDS = 45.0  # a model call, not a payment decision: no deadline budget applies here


def _unavailable(detail: str) -> JSONResponse:
    return JSONResponse({"error": {"code": "assistant_unavailable", "message": detail}}, status_code=503)


def assistant_router(base_url: str | None, *, client: Any = None,
                     timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> APIRouter:
    router = APIRouter()

    @router.post(PREFIX + "/{rest:path}")
    async def forward(rest: str, request: Request) -> Any:
        if not base_url:
            return _unavailable("The permission assistant is not configured for this deployment.")
        body = await request.body()
        http = client or httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds)
        try:
            response = await http.post(f"{PREFIX}/{rest}", content=body,
                                       headers={"content-type": "application/json"},
                                       timeout=timeout_seconds)
        except Exception as exc:  # noqa: BLE001 — unreachable is the customer's problem to be told about
            log.warning("the permission assistant did not answer", exc_info=exc)
            return _unavailable("I couldn't reach the permission assistant. Nothing was saved.")
        finally:
            if client is None:
                await http.aclose()
        return JSONResponse(_json(response), status_code=response.status_code)

    return router


def _json(response: Any) -> Any:
    """The assistant's answer, or a plain error when it did not send JSON at all."""
    try:
        return response.json()
    except Exception:  # noqa: BLE001
        return {"error": {"code": "assistant_unavailable", "message": "The assistant sent no answer."}}
