"""The API process (LEASH-127): all routers in one app, health and readiness, CORS, the built app."""

import csv
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from fake_api.app import FakeViseca
from leash.adapters.pack.loader import Pack
from leash.adapters.postgres.migrate import migrate_and_seed
from leash.adapters.viseca_api.client import VisecaClient
from leash.policy.compiler import CatalogueItem
from leash.service import create_api

DATA = Path(__file__).resolve().parents[3] / "data"
with (DATA / "items.csv").open() as f:
    CATALOGUE = [CatalogueItem(r["item_id"], r["item_name"], r["item_category"]) for r in csv.DictReader(f)]


def api(url, **kw):
    fake = FakeViseca(Pack(DATA), api_key="k")
    viseca = VisecaClient("k", "http://fake", transport=httpx.ASGITransport(app=fake.app))
    return create_api(url, viseca, CATALOGUE, **kw)


def test_ready_only_after_migrations_and_seed(test_database_url):
    with TestClient(api(test_database_url, background_seconds=0.2)) as http:
        assert http.get("/healthz").json() == {"status": "ok"}
        not_ready = http.get("/readyz")
        assert not_ready.status_code == 503 and "migrations" in not_ready.json()["reasons"][0]
    migrate_and_seed(test_database_url, DATA)
    migrate_and_seed(test_database_url, DATA)  # idempotent: a restart runs it again
    with TestClient(api(test_database_url, background_seconds=0.2)) as http:
        ready = http.get("/readyz")
        assert ready.status_code == 200, ready.json()
        assert http.get("/api/mandates").json() == {"mandates": [], "current_mandate_id": None}
        assert http.get("/api/payments").json() == {"payments": []}


def test_becomes_ready_without_a_restart_once_migrated(test_database_url):
    import time

    with TestClient(api(test_database_url, background_seconds=0.1)) as http:
        assert http.get("/readyz").status_code == 503
        migrate_and_seed(test_database_url, DATA)
        for _ in range(50):
            if http.get("/readyz").status_code == 200:
                break
            time.sleep(0.1)
        assert http.get("/readyz").status_code == 200


def test_cors_allows_only_the_configured_app_origin(test_database_url):
    migrate_and_seed(test_database_url, DATA)
    with TestClient(api(test_database_url, cors_origins=["http://localhost:5173"])) as http:
        ok = http.get("/healthz", headers={"Origin": "http://localhost:5173"})
        other = http.get("/healthz", headers={"Origin": "http://evil.example"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in other.headers


def test_the_built_app_is_served_next_to_the_api(test_database_url, tmp_path):
    migrate_and_seed(test_database_url, DATA)
    (tmp_path / "index.html").write_text("<!doctype html><title>Leash</title>")
    with TestClient(api(test_database_url, app_dist=tmp_path)) as http:
        assert "<title>Leash</title>" in http.get("/").text
        assert http.get("/healthz").json() == {"status": "ok"}


def test_the_app_does_not_close_a_platform_client_it_was_only_given(test_database_url):
    """LEASH-136: `create_api` is handed the client, so it must not close it on shutdown.

    A process that runs the API and a worker shares one pooled client; closing it when the app stops
    would leave the worker polling a dead pool.
    """
    fake = FakeViseca(Pack(DATA), api_key="k")
    viseca = VisecaClient("k", "http://fake", transport=httpx.ASGITransport(app=fake.app))
    migrate_and_seed(test_database_url, DATA)
    with TestClient(create_api(test_database_url, viseca, CATALOGUE, background_seconds=0.2)) as http:
        assert http.get("/healthz").status_code == 200
    assert not viseca.is_closed, "the app closed a client it does not own"


def test_main_serves_and_closes_the_pooled_client_in_one_loop(monkeypatch):
    """LEASH-136: `main()` itself must serve and close in one loop, not only `serve_until_stopped`.

    A real local server provides a real pooled socket, and `uvicorn.run` is stubbed to serve in its own
    loop the way the real one does. So the pre-fix shape — `uvicorn.run(...)` followed by a second
    `asyncio.run(viseca.aclose())` — fails here with "Event loop is closed", while the current shape
    passes. Without this, `main()` is `# pragma: no cover` and the regression is invisible.
    """
    import asyncio
    import logging
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    import uvicorn

    import leash.config as config
    import leash.service as service

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"  # keep-alive, so a connection is left in the pool at shutdown

        def do_GET(self):
            body = b'{"status": "ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    platform = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=platform.serve_forever, daemon=True)
    thread.start()
    built = {}

    real_platform_client = config.platform_client

    def recording(settings):
        built["client"] = real_platform_client(settings)
        return built["client"]

    class StubServer:  # stands in for uvicorn.Server: serves once, having touched the platform
        def __init__(self, *_args, **_kw):
            pass

        async def serve(self):
            await built["client"].healthz()

    # Logging is patched globally by install_redaction, which main() never undoes.
    saved = (logging.Logger.makeRecord, logging.makeLogRecord, logging.Formatter.format)
    try:
        monkeypatch.setattr(config, "platform_client", recording)
        monkeypatch.setattr(uvicorn, "Server", StubServer)
        monkeypatch.setattr(uvicorn, "run", lambda *a, **kw: asyncio.run(StubServer().serve()), raising=False)
        monkeypatch.setenv("TEAM_API_KEY", "k")
        monkeypatch.setenv("DATABASE_URL", "postgresql://leash:leash@127.0.0.1:1/leash")
        monkeypatch.setenv("LEASH_BASE_URL", f"http://127.0.0.1:{platform.server_address[1]}")
        monkeypatch.setenv("LEASH_DATA_DIR", str(DATA))
        monkeypatch.delenv("LEASH_APP_DIST", raising=False)

        service.main()  # must not raise "Event loop is closed"
    finally:
        platform.shutdown()
        logging.Logger.makeRecord, logging.makeLogRecord, logging.Formatter.format = saved
        config._ACTIVE.clear()

    assert built["client"].is_closed, "main() left the pooled client open"
