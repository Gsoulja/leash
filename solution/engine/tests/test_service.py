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
