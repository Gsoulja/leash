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


def test_the_app_never_closes_a_platform_client_it_was_handed(test_database_url):
    """LEASH-136: the pool belongs to whoever made it.

    A worker in the same process can share this client, so the app closing it at shutdown would pull
    the pool out from under it. The process entry point closes it instead.
    """
    fake = FakeViseca(Pack(DATA), api_key="k")
    viseca = VisecaClient("k", "http://fake", transport=httpx.ASGITransport(app=fake.app))
    with TestClient(create_api(test_database_url, viseca, CATALOGUE, background_seconds=0.2)) as http:
        http.get("/healthz")
    assert not viseca.closed


# --- LEASH-151: the served bundle must be the one this image was built with --------------------

import json  # noqa: E402

from leash.service import build_stamp, bundle_hash, bundle_problems  # noqa: E402


def dist_with(tmp_path, stamp: dict | None, *, name: str = "build.json", body: str | None = None):
    """A dist directory whose stamp is honest unless the test deliberately makes it lie."""
    (tmp_path / "index.html").write_text(body or "<!doctype html><div id=root></div>")
    if stamp is not None:
        (tmp_path / name).write_text(json.dumps({**stamp, "bundle": stamp.get("bundle") or bundle_hash(tmp_path)}))
    return tmp_path


def test_the_served_bundle_reports_its_revision_and_build_identifier(test_database_url, tmp_path):
    dist = dist_with(tmp_path, {"revision": "abc1234", "files": 3})
    with TestClient(api(test_database_url, app_dist=dist, expected_app_revision="abc1234")) as http:
        body = http.get("/api/build").json()
    assert body["app"]["revision"] == "abc1234" and body["app"]["bundle"] == bundle_hash(dist)
    assert body["expected_app_revision"] == "abc1234" and body["problem"] is None


def test_readiness_fails_when_the_served_bundle_is_not_the_expected_revision(test_database_url, tmp_path):
    """A stale volume shadowing dist/ is exactly this: an older stamp under a newer image."""
    migrate_and_seed(test_database_url, DATA)
    dist = dist_with(tmp_path, {"revision": "old0000"})
    with TestClient(api(test_database_url, app_dist=dist, expected_app_revision="new1111")) as http:
        answer = http.get("/readyz")
    assert answer.status_code == 503
    [reason] = [r for r in answer.json()["reasons"] if "revision" in r]
    assert "'old0000'" in reason and "'new1111'" in reason and "volume" in reason


def test_readiness_fails_when_the_served_bundle_carries_no_stamp(test_database_url, tmp_path):
    migrate_and_seed(test_database_url, DATA)
    dist = dist_with(tmp_path, None)
    with TestClient(api(test_database_url, app_dist=dist, expected_app_revision="new1111")) as http:
        answer = http.get("/readyz")
    assert answer.status_code == 503
    assert any("build.json" in r for r in answer.json()["reasons"])


def test_a_matching_bundle_does_not_block_readiness(test_database_url, tmp_path):
    migrate_and_seed(test_database_url, DATA)
    dist = dist_with(tmp_path, {"revision": "same111"})
    with TestClient(api(test_database_url, app_dist=dist, expected_app_revision="same111",
                        background_seconds=0.1)) as http:
        for _ in range(60):
            if http.get("/readyz").status_code == 200:
                break
        assert http.get("/readyz").status_code == 200, http.get("/readyz").json()


def test_no_expected_revision_means_nothing_to_compare(tmp_path):
    """Local `npm run dev` and plain `uv run leash-api` must not be told the bundle is wrong."""
    assert bundle_problems(dist_with(tmp_path, None), None) == []
    assert bundle_problems(None, "abc1234") == []


def test_an_unreadable_stamp_is_reported_not_ignored(tmp_path):
    dist = dist_with(tmp_path, None)
    (dist / "build.json").write_text("{not json")
    [problem] = bundle_problems(dist, "abc1234")
    assert "unreadable" in problem
    assert build_stamp(dist)["served"] is None


def test_a_swapped_asset_is_caught_even_when_the_revision_matches(test_database_url, tmp_path):
    """The hole a revision string alone leaves: Compose stamps every build `dev` by default, and a
    replaced dist brings its own build.json with it. The content is what settles it."""
    migrate_and_seed(test_database_url, DATA)
    dist = dist_with(tmp_path, {"revision": "dev"})
    (dist / "index.html").write_text("<!doctype html><title>STALE APP FROM LAST WEEK</title>")
    with TestClient(api(test_database_url, app_dist=dist, expected_app_revision="dev")) as http:
        answer = http.get("/readyz")
    assert answer.status_code == 503
    [reason] = [r for r in answer.json()["reasons"] if "hash" in r]
    assert "build.json says" in reason and "remove the volume" in reason


def test_a_bundle_that_does_not_match_its_own_stamp_is_wrong_with_no_expected_revision(tmp_path):
    """No `LEASH_APP_REVISION` gives nothing to compare a revision against, but a bundle that
    contradicts its own stamp is wrong under any configuration."""
    dist = dist_with(tmp_path, {"revision": "dev"})
    (dist / "assets.js").write_text("// added after the stamp was written")
    [problem] = bundle_problems(dist, None)
    assert "hash" in problem


def test_a_missing_asset_is_caught(tmp_path):
    (tmp_path / "extra.css").write_text("body{}")
    dist = dist_with(tmp_path, {"revision": "dev"})  # stamped with extra.css present
    assert bundle_problems(dist, "dev") == []
    (tmp_path / "extra.css").unlink()                # then it disappears
    assert any("hash" in p for p in bundle_problems(dist, "dev"))
