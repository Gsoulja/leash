"""HTTP client for the hosted Viseca challenge API.

Transport only: it returns the API's JSON as-is (translation into our domain happens in the
anti-corruption layer). Errors arrive as {"error": {...}} with a non-2xx status; a 204 on the
long-poll means "no work right now". The team key comes from TEAM_API_KEY and never appears
in logs, reprs or error messages.
"""

import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://saw26api.ashyground-364e1d07.switzerlandnorth.azurecontainerapps.io"
DEFAULT_TIMEOUT_SECONDS = 10.0
LONG_POLL_MARGIN_SECONDS = 10.0

# Connection reuse (LEASH-136). A fresh TLS handshake per request is time taken out of an 8-second
# decision budget, so one pool is kept for the process lifetime.
DEFAULT_MAX_CONNECTIONS = 20
DEFAULT_MAX_KEEPALIVE_CONNECTIONS = 10
DEFAULT_KEEPALIVE_EXPIRY_SECONDS = 30.0
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5.0

#: Methods that may be repeated without changing anything at the platform. A decision POST is not
#: here: the platform documents no idempotency guarantee for it, and the outbox is what resends it.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
DEFAULT_RETRIES = 1

# Documented in technical_details.md; used only when bootstrap doesn't state them.
DOCUMENTED_DECISION_TIMEOUT_SECONDS = 8.0
DOCUMENTED_HUMAN_WINDOW_SECONDS = 120.0

JSON = Any


class ClientClosed(RuntimeError):
    """The pool was closed. A closed client is never silently reopened."""


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


@dataclass(frozen=True)
class PoolSettings:
    """How the connection pool behaves. Every value is an environment variable (LEASH-136)."""

    max_connections: int = DEFAULT_MAX_CONNECTIONS
    max_keepalive_connections: int = DEFAULT_MAX_KEEPALIVE_CONNECTIONS
    keepalive_expiry_seconds: float = DEFAULT_KEEPALIVE_EXPIRY_SECONDS
    connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS
    #: Extra attempts for a safe method only, and never past the call's remaining budget.
    retries: int = DEFAULT_RETRIES

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "PoolSettings":
        e = os.environ if env is None else env

        def number(var: str, default: float) -> float:
            try:
                return float(e[var])
            except (KeyError, ValueError):
                return default

        return cls(max_connections=max(1, int(number("LEASH_HTTP_MAX_CONNECTIONS", DEFAULT_MAX_CONNECTIONS))),
                   max_keepalive_connections=max(0, int(number("LEASH_HTTP_MAX_KEEPALIVE_CONNECTIONS",
                                                              DEFAULT_MAX_KEEPALIVE_CONNECTIONS))),
                   keepalive_expiry_seconds=max(0.0, number("LEASH_HTTP_KEEPALIVE_EXPIRY_SECONDS",
                                                            DEFAULT_KEEPALIVE_EXPIRY_SECONDS)),
                   connect_timeout_seconds=max(0.0, number("LEASH_HTTP_CONNECT_TIMEOUT_SECONDS",
                                                           DEFAULT_CONNECT_TIMEOUT_SECONDS)),
                   retries=max(0, int(number("LEASH_HTTP_RETRIES", DEFAULT_RETRIES))))

    def limits(self) -> httpx.Limits:
        return httpx.Limits(max_connections=self.max_connections,
                            max_keepalive_connections=self.max_keepalive_connections,
                            keepalive_expiry=self.keepalive_expiry_seconds)


class VisecaClient:
    """One pooled `httpx.AsyncClient` for the process lifetime.

    The pool is created on first use and closed once by `aclose()` (or by leaving `async with`).
    Reopening a closed client is an error, not a quiet new pool: a client closed at shutdown must not
    keep a socket alive because some straggler made one more call.

    Every request carries an explicit timeout built from the *remaining budget* for that call, so a
    decision POST can never hold a socket longer than the time left before `deadline_at`. The
    long-poll keeps its own, much longer, read timeout: waiting 25 seconds for work is not the same
    kind of wait as sending an answer.
    """

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS,
                 transport: httpx.AsyncBaseTransport | None = None, pool: PoolSettings | None = None):
        if not api_key:
            raise MissingApiKey("TEAM_API_KEY is empty")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.pool = pool or PoolSettings()
        self._api_key = api_key
        self._transport = transport
        self._http: httpx.AsyncClient | None = None
        self._closed = False

    @classmethod
    def from_env(cls, transport: httpx.AsyncBaseTransport | None = None) -> "VisecaClient":
        key = os.environ.get("TEAM_API_KEY", "")
        if not key:
            raise MissingApiKey("set TEAM_API_KEY to the team's bearer key")
        timeout = float(os.environ.get("LEASH_API_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
        return cls(key, os.environ.get("LEASH_BASE_URL", DEFAULT_BASE_URL), timeout, transport,
                   PoolSettings.from_env())

    def __repr__(self) -> str:
        return f"VisecaClient(base_url={self.base_url!r}, timeout={self.timeout}, api_key=<redacted>)"

    # --- pool lifecycle ---
    @property
    def closed(self) -> bool:
        return self._closed

    def _client(self) -> httpx.AsyncClient:
        """The one pooled client. Created once, never recreated after `aclose()`."""
        if self._closed:
            raise ClientClosed("the Viseca client is closed; create a new one to reconnect")
        if self._http is None:
            self._http = httpx.AsyncClient(base_url=self.base_url, transport=self._transport,
                                           timeout=self._timeout(self.timeout), limits=self.pool.limits())
        return self._http

    async def aclose(self) -> None:
        """Close the pool. Calling it twice is a no-op, so shutdown paths can overlap safely."""
        http, self._http, self._closed = self._http, None, True
        if http is not None:
            await http.aclose()

    async def __aenter__(self) -> "VisecaClient":
        self._client()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    def _timeout(self, budget: float) -> httpx.Timeout:
        """Connect, read, write and pool all inside `budget`: no phase may outlive the whole call."""
        left = max(0.0, budget)
        return httpx.Timeout(connect=min(self.pool.connect_timeout_seconds, left), read=left, write=left,
                             pool=left)

    async def _request(self, method: str, path: str, *, auth: bool = True, json: JSON = None,
                       params: Mapping[str, Any] | None = None, timeout: float | None = None) -> httpx.Response:
        headers = {"Accept": "application/json"}
        if auth:
            headers["Authorization"] = f"Bearer {self._api_key}"
        budget = self.timeout if timeout is None else timeout
        ends_at = time.monotonic() + max(0.0, budget)
        attempts = 1 + (max(0, self.pool.retries) if method in SAFE_METHODS else 0)
        for attempt in range(1, attempts + 1):
            left = budget if attempt == 1 else ends_at - time.monotonic()  # a retry gets only what is left
            try:
                response = await self._client().request(method, path, headers=headers, json=json, params=params,
                                                        timeout=self._timeout(left))
                break
            except httpx.TransportError:
                # A retry is only ever an extra attempt inside the same budget, and only for a method
                # that changes nothing at the platform.
                if attempt == attempts or ends_at - time.monotonic() <= 0:
                    raise
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

    async def post_decision(self, authorization_id: str, decision: Mapping[str, Any],
                            timeout: float | None = None) -> JSON:
        """`timeout` is the time left before `deadline_at`: the POST never outlives the deadline."""
        return await self._json("POST", f"/v1/authorizations/{authorization_id}/decision", json=decision,
                                timeout=timeout)

    async def resolve(self, authorization_id: str, answer: Mapping[str, Any]) -> JSON:
        return await self._json("POST", f"/v1/authorizations/{authorization_id}/resolve", json=answer)

    async def list_authorizations(self) -> JSON:
        return await self._json("GET", "/v1/authorizations")

    async def events(self, since: int = 0) -> JSON:
        return await self._json("GET", "/v1/events", params={"since": since})
