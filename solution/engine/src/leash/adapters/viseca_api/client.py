"""HTTP client for the hosted Viseca challenge API.

Transport only: it returns the API's JSON as-is (translation into our domain happens in the
anti-corruption layer). Errors arrive as {"error": {...}} with a non-2xx status; a 204 on the
long-poll means "no work right now". The team key comes from TEAM_API_KEY and never appears
in logs, reprs or error messages.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://saw26api.ashyground-364e1d07.switzerlandnorth.azurecontainerapps.io"
DEFAULT_TIMEOUT_SECONDS = 10.0
LONG_POLL_MARGIN_SECONDS = 10.0

# Documented in technical_details.md; used only when bootstrap doesn't state them.
DOCUMENTED_DECISION_TIMEOUT_SECONDS = 8.0
DOCUMENTED_HUMAN_WINDOW_SECONDS = 120.0

JSON = Any


class MissingApiKey(RuntimeError):
    """TEAM_API_KEY is not set."""


class VisecaApiError(RuntimeError):
    """A non-2xx response. `error` is the API's error object when the body had one."""

    def __init__(self, status: int, method: str, path: str, error: Mapping[str, Any] | None, text: str = ""):
        self.status = status
        self.method = method
        self.path = path
        self.error = error
        detail = f"{error.get('code', '?')}: {error.get('message', '')}" if error else text[:200]
        super().__init__(f"{method} {path} → HTTP {status} ({detail})")


@dataclass(frozen=True)
class BootstrapSettings:
    """Team settings from /v1/bootstrap.

    The response shape is not documented, so known keys are looked up anywhere in the body. Values
    that can't be found fall back to the documented defaults and are listed in `defaults_used`.
    """

    api_version: str | None
    data_version: str | None
    decision_timeout_seconds: float
    human_window_seconds: float
    scenarios: list[Any]
    limits: dict[str, Any]
    features: dict[str, Any]
    raw: dict[str, Any]
    defaults_used: set[str] = field(default_factory=set)

    _HUMAN_KEYS = ("human_window_seconds", "human_timeout_seconds", "step_up_timeout_seconds",
                   "resolve_timeout_seconds", "human_window")
    _DECISION_KEYS = ("decision_timeout_seconds", "decision_deadline_seconds", "decision_seconds",
                      "deadline_seconds")

    @classmethod
    def parse(cls, body: Mapping[str, Any]) -> "BootstrapSettings":
        data = dict(body.get("data", body)) if isinstance(body.get("data"), Mapping) else dict(body)
        defaults: set[str] = set()

        def number(keys: tuple[str, ...], name: str, default: float) -> float:
            value = _find(data, keys)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
            defaults.add(name)
            return default

        return cls(
            api_version=_as_str(_find(data, ("api_version",))),
            data_version=_as_str(_find(data, ("data_version", "pack_version"))),
            decision_timeout_seconds=number(cls._DECISION_KEYS, "decision_timeout_seconds", DOCUMENTED_DECISION_TIMEOUT_SECONDS),
            human_window_seconds=number(cls._HUMAN_KEYS, "human_window_seconds", DOCUMENTED_HUMAN_WINDOW_SECONDS),
            scenarios=list(data.get("scenarios") or []),
            limits=dict(data.get("limits") or {}),
            features=dict(data.get("features") or {}),
            raw=dict(body),
            defaults_used=defaults,
        )


def _find(data: Any, keys: tuple[str, ...]) -> Any:
    """First value for any of `keys`, searching nested objects breadth-first."""
    queue = [data]
    while queue:
        node = queue.pop(0)
        if isinstance(node, Mapping):
            for key in keys:
                if key in node:
                    return node[key]
            queue.extend(v for v in node.values() if isinstance(v, Mapping))
    return None


def _as_str(value: Any) -> str | None:
    return None if value is None else str(value)


class VisecaClient:
    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS,
                 transport: httpx.AsyncBaseTransport | None = None):
        if not api_key:
            raise MissingApiKey("TEAM_API_KEY is empty")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._api_key = api_key
        self._transport = transport

    @classmethod
    def from_env(cls, transport: httpx.AsyncBaseTransport | None = None) -> "VisecaClient":
        key = os.environ.get("TEAM_API_KEY", "")
        if not key:
            raise MissingApiKey("set TEAM_API_KEY to the team's bearer key")
        timeout = float(os.environ.get("LEASH_API_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
        return cls(key, os.environ.get("LEASH_BASE_URL", DEFAULT_BASE_URL), timeout, transport)

    def __repr__(self) -> str:
        return f"VisecaClient(base_url={self.base_url!r}, timeout={self.timeout}, api_key=<redacted>)"

    async def _request(self, method: str, path: str, *, auth: bool = True, json: JSON = None,
                       params: Mapping[str, Any] | None = None, timeout: float | None = None) -> httpx.Response:
        headers = {"Accept": "application/json"}
        if auth:
            headers["Authorization"] = f"Bearer {self._api_key}"
        async with httpx.AsyncClient(base_url=self.base_url, transport=self._transport,
                                     timeout=timeout or self.timeout) as http:
            response = await http.request(method, path, headers=headers, json=json, params=params)
        if not response.is_success:
            error = None
            try:
                body = response.json()
                if isinstance(body, Mapping) and isinstance(body.get("error"), Mapping):
                    error = dict(body["error"])
            except ValueError:
                pass
            raise VisecaApiError(response.status_code, method, path, error, response.text)
        return response

    async def _json(self, method: str, path: str, **kw: Any) -> JSON:
        response = await self._request(method, path, **kw)
        return None if response.status_code == 204 else response.json()

    # --- service and reference data ---
    async def healthz(self) -> JSON:
        return await self._json("GET", "/healthz", auth=False)

    async def bootstrap(self) -> BootstrapSettings:
        return BootstrapSettings.parse(await self._json("GET", "/v1/bootstrap"))

    async def reference_data(self) -> JSON:
        return await self._json("GET", "/v1/reference-data")

    async def authorization_history_csv(self) -> str:
        return (await self._request("GET", "/v1/reference-data/authorization-history.csv")).text

    # --- mandates ---
    async def create_mandate(self, draft: Mapping[str, Any]) -> JSON:
        return await self._json("POST", "/v1/mandates", json=draft)

    async def confirm_mandate(self, draft_id: str) -> JSON:
        return await self._json("POST", f"/v1/mandates/{draft_id}/confirm", json={"confirmed": True})

    async def get_mandate(self, mandate_id: str) -> JSON:
        return await self._json("GET", f"/v1/mandates/{mandate_id}")

    async def patch_mandate(self, mandate_id: str, changes: Mapping[str, Any]) -> JSON:
        return await self._json("PATCH", f"/v1/mandates/{mandate_id}", json=changes)

    async def revoke_mandate(self, mandate_id: str) -> JSON:
        return await self._json("DELETE", f"/v1/mandates/{mandate_id}")

    # --- runs ---
    async def start_run(self, scenario_id: str, mandate_id: str) -> JSON:
        return await self._json("POST", "/v1/scenario-runs", json={"scenario_id": scenario_id, "mandate_id": mandate_id})

    async def get_run(self, run_id: str) -> JSON:
        return await self._json("GET", f"/v1/scenario-runs/{run_id}")

    # --- decisions ---
    async def next_decision_request(self, wait: int = 25) -> JSON:
        """Long-poll. Returns the envelope, or None on 204 (no work right now; the run may continue)."""
        return await self._json("GET", "/v1/decision-requests/next", params={"wait": wait},
                                timeout=wait + LONG_POLL_MARGIN_SECONDS)

    async def post_decision(self, authorization_id: str, decision: Mapping[str, Any]) -> JSON:
        return await self._json("POST", f"/v1/authorizations/{authorization_id}/decision", json=decision)

    async def resolve(self, authorization_id: str, answer: Mapping[str, Any]) -> JSON:
        return await self._json("POST", f"/v1/authorizations/{authorization_id}/resolve", json=answer)

    async def list_authorizations(self) -> JSON:
        return await self._json("GET", "/v1/authorizations")

    async def events(self, since: int = 0) -> JSON:
        return await self._json("GET", "/v1/events", params={"since": since})
