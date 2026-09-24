import asyncio
import io
import logging
from datetime import timedelta

import httpx
import pytest

from leash.adapters.viseca_api.client import VisecaClient
from leash.config import ConfigError, IncompatibleApi, Settings, check_compatibility, install_redaction, load_runtime, platform_client
from leash.domain.clock import WallTime

KEY = "team-secret-key-123"
ENV = {"TEAM_API_KEY": KEY, "DATABASE_URL": "postgresql://leash:db-pass-456@localhost:55432/leash"}


def api(bootstrap: dict, health: dict | None = None) -> VisecaClient:
    health = health or {"status": "ok", "api_version": "0.1.0", "pack_version": "saw26"}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=bootstrap if request.url.path == "/v1/bootstrap" else health)

    return VisecaClient(api_key=KEY, transport=httpx.MockTransport(handler))


def test_human_window_comes_from_bootstrap():
    settings = Settings.from_env(ENV)
    rt = asyncio.run(load_runtime(settings, api({"timeouts": {"human_window_seconds": 90, "decision_seconds": 8}})))
    asked = WallTime.parse("2026-09-23T14:00:00Z")
    assert rt.human_window_seconds == 90
    assert rt.ask_expires_at(asked) == WallTime.parse("2026-09-23T14:01:30Z")
    assert rt.for_app()["human_window_seconds"] == 90


def test_bootstrap_decision_timeout_bounds_the_watchdog_margin():
    settings = Settings.from_env({**ENV, "LEASH_WATCHDOG_MARGIN_SECONDS": "2"})
    rt = asyncio.run(load_runtime(settings, api({"timeouts": {"decision_seconds": 8}})))
    deadline = WallTime.parse("2026-09-23T14:00:08Z")
    assert rt.watchdog_fires_at(deadline) == WallTime.parse("2026-09-23T14:00:06Z")
    short = asyncio.run(load_runtime(settings, api({"timeouts": {"decision_seconds": 3}})))
    # the margin never eats more than half of the platform's decision window
    assert short.watchdog_margin == timedelta(seconds=1.5)


def test_documented_defaults_are_used_visibly_when_bootstrap_is_silent():
    rt = asyncio.run(load_runtime(Settings.from_env(ENV), api({})))
    assert rt.human_window_seconds == 120 and rt.decision_timeout_seconds == 8
    assert set(rt.for_app()["defaults_used"]) == {"human_window_seconds", "decision_timeout_seconds"}


def test_missing_or_invalid_configuration_fails_with_a_clear_message():
    with pytest.raises(ConfigError) as exc:
        Settings.from_env({"DATABASE_URL": "mysql://x", "LEASH_API_TIMEOUT_SECONDS": "-1"})
    message = str(exc.value)
    assert "TEAM_API_KEY" in message and "DATABASE_URL" in message and "LEASH_API_TIMEOUT_SECONDS" in message


def test_versions_are_checked_for_compatibility():
    check_compatibility("0.1.0", "saw26")
    check_compatibility("0.4.2", "saw26")  # same major version
    with pytest.raises(IncompatibleApi, match="api"):
        check_compatibility("1.0.0", "saw26")
    with pytest.raises(IncompatibleApi, match="data"):
        check_compatibility("0.1.0", "saw27")
    with pytest.raises(IncompatibleApi, match="unknown"):
        check_compatibility(None, None)


def test_load_runtime_falls_back_to_healthz_versions_and_rejects_mismatch():
    settings = Settings.from_env(ENV)
    rt = asyncio.run(load_runtime(settings, api({"timeouts": {}})))  # versions only on /healthz
    assert (rt.api_version, rt.data_version) == ("0.1.0", "saw26")
    with pytest.raises(IncompatibleApi):
        asyncio.run(load_runtime(settings, api({}, {"status": "ok", "api_version": "2.0.0", "pack_version": "saw26"})))


@pytest.fixture
def redaction():
    uninstall = install_redaction(Settings.from_env(ENV))
    yield
    uninstall()


def test_api_key_never_logged(redaction, caplog):
    # Installed before any handler exists (caplog's handler is attached afterwards), logged from a child logger.
    caplog.set_level(logging.DEBUG)
    logging.getLogger("leash.worker.poll").info("calling with key %s and url %s", KEY, ENV["DATABASE_URL"])
    assert KEY not in caplog.text and "db-pass-456" not in caplog.text
    assert "[redacted]" in caplog.text
    assert KEY not in repr(Settings.from_env(ENV)) and "db-pass-456" not in repr(Settings.from_env(ENV))


def test_tracebacks_are_redacted(redaction, caplog):
    caplog.set_level(logging.DEBUG)
    try:
        raise RuntimeError(f"boom {KEY}")
    except RuntimeError:
        logging.getLogger("httpx").exception("request failed")
    assert "boom [redacted]" in caplog.text and KEY not in caplog.text


def test_uninstall_restores_normal_logging(caplog):
    uninstall = install_redaction(Settings.from_env(ENV))
    uninstall()
    caplog.set_level(logging.DEBUG)
    logging.getLogger("leash.x").info("plain %s", "text")
    assert "plain text" in caplog.text


# ---- review round 2 ----
@pytest.mark.parametrize("url,password", [
    ("postgresql://leash:p%40ss%3Aw%2Frd%21@localhost/db", "p@ss:w/rd!"),
    ("postgresql://localhost/db?user=u&password=qs-secret-789", "qs-secret-789"),
    ("postgresql://u:ab@cd@localhost/db", "ab@cd"),
])
def test_database_password_is_redacted_in_every_url_form(url, password, caplog):
    uninstall = install_redaction(Settings.from_env({"TEAM_API_KEY": KEY, "DATABASE_URL": url}))
    try:
        caplog.set_level(logging.DEBUG)
        logging.getLogger("leash.db").info("connecting %s with %s", url, password)
    finally:
        uninstall()
    assert password not in caplog.text


def test_extra_fields_are_redacted(redaction):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s %(token)s"))
    logger = logging.getLogger("leash.extra")
    logger.addHandler(handler)
    try:
        logger.warning("hi", extra={"token": KEY})
    finally:
        logger.removeHandler(handler)
    assert KEY not in stream.getvalue() and "[redacted]" in stream.getvalue()


def test_rebuilt_records_are_redacted(redaction, caplog):
    caplog.set_level(logging.DEBUG)
    record = logging.makeLogRecord({"name": "remote", "levelno": logging.INFO, "levelname": "INFO",
                                    "msg": f"remote {KEY}", "args": None})
    logging.getLogger("remote").handle(record)
    assert KEY not in caplog.text


def test_malformed_log_call_does_not_raise_in_the_caller(redaction, caplog):
    caplog.set_level(logging.DEBUG)
    logging.getLogger("leash.bad").info("count %d", "not-a-number")  # must not raise
    assert "count" in caplog.text


# ---- review round 3 ----
def settings_with(key=KEY, url=ENV["DATABASE_URL"]) -> Settings:
    return Settings.from_env({"TEAM_API_KEY": key, "DATABASE_URL": url})


def emitted(record_or_call, fmt="%(message)s") -> str:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter(fmt))
    logger = logging.getLogger("leash.round3")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    try:
        record_or_call(logger)
    finally:
        logger.removeHandler(handler)
    return stream.getvalue()


def test_non_string_extras_are_redacted():
    uninstall = install_redaction(settings_with())
    try:
        out = emitted(lambda log: log.warning("hi", extra={"headers": {"Authorization": f"Bearer {KEY}"}}),
                      "%(message)s %(headers)s")
    finally:
        uninstall()
    assert KEY not in out


def test_hand_built_records_and_custom_loggers_are_redacted():
    class Rogue(logging.Logger):
        def makeRecord(self, name, level, fn, lno, msg, args, exc_info, func=None, extra=None, sinfo=None):
            return logging.LogRecord(name, level, fn, lno, msg, args, exc_info, func, sinfo)

    uninstall = install_redaction(settings_with())
    try:
        out = emitted(lambda log: log.handle(logging.LogRecord("x", logging.INFO, "f", 1, f"raw {KEY}", None, None)))
        rogue = Rogue("rogue")
        stream = io.StringIO()
        rogue.addHandler(logging.StreamHandler(stream))
        rogue.warning("rogue %s", KEY)
    finally:
        uninstall()
    assert KEY not in out and KEY not in stream.getvalue()


@pytest.mark.parametrize("key,url,shown", [
    (KEY, "postgresql://localhost/db?password=a+b-secret", "password=a+b-secret"),
    (KEY, "postgresql://leash:p%40ss%2fwd-77@localhost/db", "p%40ss%2Fwd-77"),
    ("k+ey/with=chars-999", ENV["DATABASE_URL"], "key=k%2Bey%2Fwith%3Dchars-999"),
    ("quote'and\\slash-555", ENV["DATABASE_URL"], repr("quote'and\\slash-555")),
])
def test_secrets_are_redacted_in_their_encoded_forms(key, url, shown):
    uninstall = install_redaction(settings_with(key, url))
    try:
        out = emitted(lambda log: log.info("value %s", shown))
    finally:
        uninstall()
    assert "[redacted]" in out, out


def test_uninstall_order_does_not_matter():
    original = logging.Logger.makeRecord
    first = install_redaction(settings_with())
    second = install_redaction(settings_with(key="other-key-222"))
    first()
    still = emitted(lambda log: log.info("k %s", "other-key-222"))
    second()
    assert "other-key-222" not in still
    assert logging.Logger.makeRecord is original


def test_structured_log_lines_carry_the_authorization_id():
    import io
    import json
    import logging

    from leash.config import JsonFormatter

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    log = logging.getLogger("leash.test.structured")
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    try:
        log.info("handled %s", "AZ-1", extra={"authorization_id": "AZ-1"})
        log.info("no purchase here")
    finally:
        log.removeHandler(handler)
    first, second = (json.loads(line) for line in stream.getvalue().splitlines())
    assert first["authorization_id"] == "AZ-1" and first["message"] == "handled AZ-1" and first["logger"]
    assert "authorization_id" not in second and second["level"] == "INFO"


def test_structured_log_lines_are_redacted_too(redaction):
    import io
    import json

    from leash.config import JsonFormatter

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    log = logging.getLogger("leash.test.structured.redacted")
    log.addHandler(handler)
    try:
        try:
            raise RuntimeError(f"connect failed with key {KEY}")
        except RuntimeError:
            log.exception("failed %s", ENV["DATABASE_URL"], extra={"authorization_id": KEY})
    finally:
        log.removeHandler(handler)
    text = stream.getvalue()
    assert KEY not in text and "db-pass-456" not in text and json.loads(text.splitlines()[0])


# --- LEASH-136: the pool is configured once, in Settings, and a bad value is loud ----------------

def env(**extra):
    base = {"TEAM_API_KEY": "k", "DATABASE_URL": "postgresql://u:p@localhost/leash"}
    return {**base, **extra}


def test_the_pool_variables_reach_the_client():
    settings = Settings.from_env(env(LEASH_HTTP_MAX_CONNECTIONS="7",
                                     LEASH_HTTP_MAX_KEEPALIVE_CONNECTIONS="3",
                                     LEASH_HTTP_KEEPALIVE_EXPIRY_SECONDS="2.5",
                                     LEASH_HTTP_CONNECT_TIMEOUT_SECONDS="1.25",
                                     LEASH_HTTP_CONNECT_RETRIES="0"))
    client = platform_client(settings)
    limits = client.limits
    assert (limits.max_connections, limits.max_keepalive_connections, limits.keepalive_expiry) == (7, 3, 2.5)
    assert client.connect_timeout_seconds == 1.25 and client.connect_retries == 0
    inner = client.http._transport._pool  # the real pool, not just what we asked for
    assert (inner._max_connections, inner._max_keepalive_connections) == (7, 3)


@pytest.mark.parametrize("bad,why", [
    ({"LEASH_HTTP_MAX_CONNECTIONS": "0"}, "greater than 0"),
    ({"LEASH_HTTP_MAX_CONNECTIONS": "abc"}, "LEASH_HTTP_MAX_CONNECTIONS"),
    ({"LEASH_HTTP_MAX_CONNECTIONS": "inf"}, "LEASH_HTTP_MAX_CONNECTIONS"),
    ({"LEASH_HTTP_MAX_CONNECTIONS": "nan"}, "LEASH_HTTP_MAX_CONNECTIONS"),
    ({"LEASH_HTTP_MAX_CONNECTIONS": "1e400"}, "LEASH_HTTP_MAX_CONNECTIONS"),
    ({"LEASH_HTTP_CONNECT_RETRIES": "-1"}, "greater than or equal to 0"),
    ({"LEASH_HTTP_KEEPALIVE_EXPIRY_SECONDS": "0"}, "greater than 0"),
    ({"LEASH_HTTP_POOL_TIMEOUT_SECONDS": "-3"}, "greater than 0"),
])
def test_a_misconfigured_pool_is_a_loud_startup_error_naming_the_variable(bad, why):
    """Never silently rewritten. A value someone deliberately set and got wrong is worth a failure that
    names it, not a default quietly substituted behind their back."""
    with pytest.raises(ConfigError) as raised:
        Settings.from_env(env(**bad))
    assert why in str(raised.value)


def test_the_defaults_are_the_documented_ones():
    settings = Settings.from_env(env())
    assert (settings.http_max_connections, settings.http_max_keepalive_connections) == (20, 10)
    assert settings.http_connect_retries == 1 and settings.http_pool_timeout_seconds is None
