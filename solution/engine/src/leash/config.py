"""Runtime configuration.

`Settings` comes from the environment and is validated at startup: every problem is reported at
once, with the variable name. `RuntimeSettings` adds what the platform says in /v1/bootstrap
(decision timeout, human answer window, versions) and turns it into the values the watchdog, the ask
expiry and the app use (DEC-008). Secrets are wrapped so they never appear in reprs, and a log filter
redacts them from log lines.
"""

import json
import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from urllib.parse import quote, quote_plus, unquote, unquote_plus, urlsplit

from pydantic import BaseModel, Field, SecretStr, ValidationError, field_validator

from leash.adapters.viseca_api.client import (DEFAULT_BASE_URL, DEFAULT_CONNECT_RETRIES,
                                              DEFAULT_CONNECT_TIMEOUT_SECONDS,
                                              DEFAULT_KEEPALIVE_EXPIRY_SECONDS, DEFAULT_MAX_CONNECTIONS,
                                              DEFAULT_MAX_KEEPALIVE_CONNECTIONS, BootstrapSettings,
                                              VisecaClient)
from leash.domain.clock import WallTime

EXPECTED_API_MAJOR = "0"
EXPECTED_DATA_VERSION = "saw26"  # the pack family; the hosted API adds a suffix ("saw26-hackaton-api")
_ENV = {
    "team_api_key": "TEAM_API_KEY",
    "database_url": "DATABASE_URL",
    "base_url": "LEASH_BASE_URL",
    "api_timeout_seconds": "LEASH_API_TIMEOUT_SECONDS",
    "watchdog_margin_seconds": "LEASH_WATCHDOG_MARGIN_SECONDS",
    # HTTP connection pool to the platform (LEASH-136). Both processes build their client from these, so
    # the variables configure what is deployed rather than only what `VisecaClient.from_env` would make.
    "http_max_connections": "LEASH_HTTP_MAX_CONNECTIONS",
    "http_max_keepalive_connections": "LEASH_HTTP_MAX_KEEPALIVE_CONNECTIONS",
    "http_keepalive_expiry_seconds": "LEASH_HTTP_KEEPALIVE_EXPIRY_SECONDS",
    "http_connect_timeout_seconds": "LEASH_HTTP_CONNECT_TIMEOUT_SECONDS",
    "http_pool_timeout_seconds": "LEASH_HTTP_POOL_TIMEOUT_SECONDS",
    "http_connect_retries": "LEASH_HTTP_CONNECT_RETRIES",
}


class ConfigError(RuntimeError):
    """Configuration is missing or invalid."""


class IncompatibleApi(RuntimeError):
    """The hosted API or data pack version is not the one this engine was built for."""


class Settings(BaseModel):
    model_config = {"frozen": True}

    team_api_key: SecretStr = Field(min_length=1)
    database_url: SecretStr
    base_url: str = DEFAULT_BASE_URL
    api_timeout_seconds: float = Field(default=10.0, gt=0)
    watchdog_margin_seconds: float = Field(default=2.0, gt=0)
    # Constrained on purpose: a misconfigured pool is a loud startup error naming the variable, not a
    # value silently rewritten to something that happens to work.
    http_max_connections: int = Field(default=DEFAULT_MAX_CONNECTIONS, gt=0)
    http_max_keepalive_connections: int = Field(default=DEFAULT_MAX_KEEPALIVE_CONNECTIONS, ge=0)
    http_keepalive_expiry_seconds: float = Field(default=DEFAULT_KEEPALIVE_EXPIRY_SECONDS, gt=0)
    http_connect_timeout_seconds: float = Field(default=DEFAULT_CONNECT_TIMEOUT_SECONDS, gt=0)
    http_pool_timeout_seconds: float | None = Field(default=None, gt=0)
    http_connect_retries: int = Field(default=DEFAULT_CONNECT_RETRIES, ge=0)

    @field_validator("database_url")
    @classmethod
    def _postgres_only(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith(("postgresql://", "postgres://")):
            raise ValueError("must be a postgresql:// URL")
        return value

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Settings":
        raw = {name: env[var] for name, var in _ENV.items() if env.get(var)}
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            problems = []
            for err in exc.errors():
                name = str(err["loc"][0]) if err["loc"] else "?"
                problems.append(f"{_ENV.get(name, name)}: {err['msg']}")
            raise ConfigError("invalid configuration — " + "; ".join(problems)) from None

    def secrets(self) -> list[str]:
        """The raw secrets: API key and database password (userinfo or query string), decoded and not."""
        found = {self.team_api_key.get_secret_value()}
        parts = urlsplit(self.database_url.get_secret_value())
        if "@" in parts.netloc:
            raw = parts.netloc.rpartition("@")[0].partition(":")[2]
            found |= {raw, unquote(raw)}
        for pair in parts.query.split("&"):
            key, _, raw = pair.partition("=")
            if key.lower() in {"password", "pass", "pwd", "sslpassword"}:
                found |= {raw, unquote(raw), unquote_plus(raw)}
        return sorted((s for s in found if s), key=len, reverse=True)


_ACTIVE: list[frozenset[str]] = []  # one entry per install_redaction call still in effect
_ORIGINALS: dict[str, Any] = {}


def _variants(secret: str) -> set[str]:
    """Every way a secret may be written in a log line: raw, URL-encoded (either hex case), repr-escaped."""
    forms = {secret, unquote(secret), unquote_plus(secret), quote(secret, safe=""), quote_plus(secret, safe=""),
             repr(secret)[1:-1]}
    hexed = {re.sub(r"%[0-9a-fA-F]{2}", lambda m: m.group(0).lower(), f) for f in forms}
    hexed |= {re.sub(r"%[0-9a-fA-F]{2}", lambda m: m.group(0).upper(), f) for f in forms}
    return {f for f in forms | hexed if len(f) >= 3}


def _redact(text: str) -> str:
    secrets = sorted(set().union(*_ACTIVE), key=len, reverse=True) if _ACTIVE else []
    for secret in secrets:
        text = text.replace(secret, "[redacted]")
    return text


def _scrub(record: logging.LogRecord) -> logging.LogRecord:
    try:
        message = record.getMessage()
    except Exception:  # a malformed log call must not raise in the caller
        message = f"{record.msg} {record.args!r}"
    record.msg, record.args = _redact(message), None
    if record.exc_info and not record.exc_text:
        record.exc_text = logging.Formatter().formatException(record.exc_info)
    for key, value in list(vars(record).items()):
        if isinstance(value, str):
            setattr(record, key, _redact(value))
    return record


def platform_client(settings: Settings) -> VisecaClient:
    """The one pooled client a process uses to talk to the platform (LEASH-136).

    Both entry points build it here, so the pool variables configure the deployed processes rather than
    only `VisecaClient.from_env`, and there is a single place to look for how the client is made.
    Whoever calls this owns the client and closes it — the API app never closes a client it was handed,
    because a worker in the same process may share it.
    """
    return VisecaClient(settings.team_api_key.get_secret_value(), settings.base_url,
                        settings.api_timeout_seconds,
                        max_connections=settings.http_max_connections,
                        max_keepalive_connections=settings.http_max_keepalive_connections,
                        keepalive_expiry_seconds=settings.http_keepalive_expiry_seconds,
                        connect_timeout_seconds=settings.http_connect_timeout_seconds,
                        pool_timeout_seconds=settings.http_pool_timeout_seconds,
                        connect_retries=settings.http_connect_retries)


def install_redaction(settings: Settings) -> Callable[[], None]:
    """Redact secrets from everything logging emits. Returns an uninstaller (order-independent).

    Early: `Logger.makeRecord` and `logging.makeLogRecord` scrub records as they are born (after
    `extra=` is attached). Late: `Formatter.format` redacts the final text, which also covers non-string
    extras, custom Logger subclasses and hand-built records. The originals return when the last
    uninstaller runs.
    """
    entry = frozenset(v for secret in settings.secrets() for v in _variants(secret))
    if not _ACTIVE:
        _ORIGINALS.update(make_record=logging.Logger.makeRecord, make_log_record=logging.makeLogRecord,
                          format=logging.Formatter.format)
        original_make_record, original_make_log_record, original_format = (
            _ORIGINALS["make_record"], _ORIGINALS["make_log_record"], _ORIGINALS["format"])

        def make_record(self: logging.Logger, *args: Any, **kwargs: Any) -> logging.LogRecord:
            return _scrub(original_make_record(self, *args, **kwargs))

        def make_log_record(fields: Mapping[str, object]) -> logging.LogRecord:
            return _scrub(original_make_log_record(fields))

        def format_record(self: logging.Formatter, record: logging.LogRecord) -> str:
            return _redact(original_format(self, record))

        logging.Logger.makeRecord = make_record  # type: ignore[method-assign]
        logging.makeLogRecord = make_log_record  # type: ignore[assignment]  # stdlib names its parameter `dict`
        logging.Formatter.format = format_record  # type: ignore[method-assign]
    _ACTIVE.append(entry)

    def uninstall() -> None:
        if entry in _ACTIVE:
            _ACTIVE.remove(entry)
        if not _ACTIVE and _ORIGINALS:
            logging.Logger.makeRecord = _ORIGINALS["make_record"]  # type: ignore[method-assign]
            logging.makeLogRecord = _ORIGINALS["make_log_record"]
            logging.Formatter.format = _ORIGINALS["format"]  # type: ignore[method-assign]
            _ORIGINALS.clear()

    return uninstall


def check_compatibility(api_version: str | None, data_version: str | None) -> None:
    if api_version is None or data_version is None:
        raise IncompatibleApi("api or data version unknown; refusing to run against an unidentified platform")
    if api_version.split(".")[0] != EXPECTED_API_MAJOR:
        raise IncompatibleApi(f"api version {api_version} is not {EXPECTED_API_MAJOR}.x")
    # The family, not the exact string: the practice pack reports "saw26" and the hosted one
    # "saw26-hackaton-api". Pinning the full version refused the real platform (LEASH-158); pinning
    # nothing would let us run against a pack we have never seen.
    if not data_version.startswith(EXPECTED_DATA_VERSION):
        raise IncompatibleApi(f"data version {data_version} is not a {EXPECTED_DATA_VERSION} pack")


@dataclass(frozen=True)
class RuntimeSettings:
    settings: Settings
    bootstrap: BootstrapSettings
    api_version: str
    data_version: str

    @property
    def decision_timeout_seconds(self) -> float:
        return self.bootstrap.decision_timeout_seconds

    @property
    def human_window_seconds(self) -> float:
        return self.bootstrap.human_window_seconds

    @property
    def watchdog_margin(self) -> timedelta:
        """Configured margin, never more than half the platform's decision window."""
        return timedelta(seconds=min(self.settings.watchdog_margin_seconds, self.decision_timeout_seconds / 2))

    def watchdog_fires_at(self, deadline_at: WallTime) -> WallTime:
        return WallTime(deadline_at.at - self.watchdog_margin)

    def ask_expires_at(self, asked_at: WallTime) -> WallTime:
        return WallTime(asked_at.at + timedelta(seconds=self.human_window_seconds))

    def for_app(self) -> dict[str, Any]:
        return {"human_window_seconds": self.human_window_seconds,
                "decision_timeout_seconds": self.decision_timeout_seconds,
                "defaults_used": sorted(self.bootstrap.defaults_used)}


async def load_runtime(settings: Settings, client: VisecaClient) -> RuntimeSettings:
    """Read bootstrap (and /healthz for versions it doesn't state) and check compatibility."""
    bootstrap = await client.bootstrap()
    api_version, data_version = bootstrap.api_version, bootstrap.data_version
    if api_version is None or data_version is None:
        health = await client.healthz() or {}
        api_version = api_version or health.get("api_version")
        data_version = data_version or health.get("pack_version") or health.get("data_version")
    check_compatibility(api_version, data_version)
    return RuntimeSettings(settings, bootstrap, str(api_version), str(data_version))


class JsonFormatter(logging.Formatter):
    """One JSON object per line: time, level, logger, message, and the authorization ID when there is one."""

    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {"time": self.formatTime(record), "level": record.levelname, "logger": record.name,
                               "message": record.getMessage()}
        aid = getattr(record, "authorization_id", None)
        if aid is not None:
            out["authorization_id"] = aid
        if record.exc_info:
            out["exception"] = record.exc_text or self.formatException(record.exc_info)
        return _redact(json.dumps(out, default=str))  # the same masking as every other log path


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)
