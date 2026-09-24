"""The API process (LEASH-127): policy, read and event endpoints in one app, with the ask sweeper, the
mandate snapshot refresh, liveness and readiness, CORS for the app, and the built app itself.

Readiness fails until the database is reachable, migrated to head and seeded, so nothing is served from a
half-set-up database. Run it with `uv run leash-api`; `leash-migrate` must have run first (Compose does
this as a one-shot service).
"""

import asyncio
import contextlib
import csv
import logging
import os
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import asyncpg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from leash.adapters.http.events import EventHub, events_router
from leash.adapters.http.policy_api import (MandateChanges, PlatformMandates, ResolveApi, RunApi, asks_router,
                                            mandate_changes_router, policy_router, runs_router)
from leash.adapters.http.query_api import query_router
from leash.adapters.pack.loader import Pack
from leash.adapters.postgres.mandates import StoredMandates
from leash.adapters.postgres.migrate import ENGINE, head_revision
from leash.adapters.postgres.unit_of_work import ResolutionTransaction
from leash.application.resolve import Sweeper
from leash.policy.compiler import CatalogueItem

log = logging.getLogger("leash.service")


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


async def _readiness(pool: asyncpg.Pool, head: str) -> list[str]:
    reasons = []
    try:
        async with pool.acquire() as conn:
            applied = await conn.fetchval("select version_num from alembic_version") \
                if await conn.fetchval("select to_regclass('alembic_version') is not null") else None
            if applied != head:
                reasons.append(f"migrations not at head ({applied or 'none'} ≠ {head})")
            elif not await conn.fetchval("select exists (select 1 from merchants)"):
                reasons.append("the pack seed has not run")
    except (OSError, asyncpg.PostgresError) as exc:
        reasons.append(f"database unreachable ({type(exc).__name__})")
    return reasons


class PlatformApi(PlatformMandates, MandateChanges, ResolveApi, RunApi, Protocol):
    """What the API process needs from Viseca: mandates (draft, confirm, tighten, revoke), /resolve, and runs."""


def create_api(database_url: str, viseca: PlatformApi, catalogue: Sequence[CatalogueItem], *,
               engine_version: str = "leash",
               cors_origins: Sequence[str] = ("http://localhost:5173",), app_dist: Path | None = None,
               background_seconds: float = 1.0, scenario_cards: Mapping[str, str] | None = None) -> FastAPI:
    state: dict[str, Any] = {}
    mandates = StoredMandates()
    if scenario_cards is None:  # each scenario's card, from its first purchase in the pack
        scenario_cards = {}
        pack = Pack(Path(os.environ.get("LEASH_DATA_DIR", str(ENGINE.parents[1] / "data"))))
        for attempt in pack.attempts():
            scenario_cards.setdefault(attempt.scenario_id, attempt.purchase.card_id)
    head = head_revision()

    async def every(seconds: float, what: str, job: Any) -> None:
        while True:
            try:
                if not await _readiness(state["pool"], head):
                    await job()
            except Exception:
                log.exception("%s failed", what)
            await asyncio.sleep(seconds)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        state["pool"] = await asyncpg.create_pool(database_url, min_size=2, max_size=12)
        sweeper = Sweeper(ResolutionTransaction(state["pool"]))
        tasks = [asyncio.ensure_future(every(background_seconds, "mandate refresh",
                                             lambda: mandates.refresh(state["pool"]))),
                 asyncio.ensure_future(every(background_seconds, "ask sweep",
                                             lambda: sweeper.run_once(now=datetime.now(timezone.utc))))]
        state["hub"] = None

        async def start_hub() -> None:  # once the database is ready (Compose runs leash-migrate first)
            if state["hub"] is None:
                hub_ = EventHub(state["pool"], mandates)
                await hub_.start()
                state["hub"] = hub_

        if not await _readiness(state["pool"], head):
            await start_hub()
        else:
            tasks.append(asyncio.ensure_future(every(background_seconds, "event stream start", start_hub)))
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            if state["hub"] is not None:
                await state["hub"].stop()
            await state["pool"].close()
            # The platform client is *not* closed here: `create_api` is given it, so it does not own it.
            # Whoever built it closes it (see `main`), which also lets a process share one client between
            # the API and a worker without the app's shutdown pulling the pool out from under the worker.

    app = FastAPI(title="Leash", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=list(cors_origins),
                       allow_methods=["GET", "POST", "PATCH", "DELETE"],
                       allow_headers=["Content-Type", "Last-Event-ID"])

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unexpected error")
        return _error(500, "internal_error", "Something went wrong. Please try again.")

    @app.exception_handler(RequestValidationError)
    async def invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _error(422, "invalid_request", "The request body must be a JSON object of the documented shape.")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> Any:
        reasons = await _readiness(state["pool"], head)
        if reasons or state["hub"] is None:
            return JSONResponse({"status": "not_ready", "reasons": reasons or ["the event stream is starting"]},
                                status_code=503)
        return {"status": "ready"}

    def hub() -> EventHub:
        if state["hub"] is None:
            raise RuntimeError("the event stream starts once the database is ready")
        hub_: EventHub = state["hub"]
        return hub_

    app.include_router(policy_router(lambda: state["pool"], viseca, catalogue))
    app.include_router(asks_router(lambda: state["pool"], mandates, viseca, engine_version=engine_version))
    app.include_router(runs_router(lambda: state["pool"], viseca, scenario_cards))
    app.include_router(mandate_changes_router(lambda: state["pool"], viseca))
    app.include_router(query_router(lambda: state["pool"], mandates, lambda: datetime.now(timezone.utc)))
    app.include_router(events_router(hub))
    if app_dist is not None and (app_dist / "index.html").exists():
        app.mount("/", StaticFiles(directory=app_dist, html=True), name="app")
    return app


def load_catalogue(data_dir: Path) -> list[CatalogueItem]:
    with (data_dir / "items.csv").open(encoding="utf-8", newline="") as f:
        return [CatalogueItem(r["item_id"], r["item_name"], r["item_category"]) for r in csv.DictReader(f)]


class Servable(Protocol):
    async def serve(self) -> Any: ...


class Closeable(Protocol):
    async def aclose(self) -> None: ...


async def serve_until_stopped(server: Servable, viseca: Closeable) -> None:
    """Serve, then close the platform client — in the loop the pool's sockets were opened on.

    Closing from a second `asyncio.run` after serving has finished raises "Event loop is closed" from
    httpcore while it tears down an idle keep-alive connection, so the process would exit on a traceback
    with the socket left uncleanly closed (LEASH-136).
    """
    try:
        await server.serve()
    finally:
        await viseca.aclose()


def main() -> None:  # pragma: no cover - process entry point
    import uvicorn

    from leash.config import Settings, configure_logging, install_redaction, platform_client

    configure_logging(os.environ.get("LEASH_LOG_LEVEL", "INFO"))
    settings = Settings.from_env(os.environ)
    install_redaction(settings)
    data_dir = Path(os.environ.get("LEASH_DATA_DIR", str(ENGINE.parents[1] / "data")))
    dist = os.environ.get("LEASH_APP_DIST")
    # This process builds the pooled platform client, so this process closes it — exactly once, in the
    # loop that served with it (LEASH-136).
    viseca = platform_client(settings)
    app = create_api(settings.database_url.get_secret_value(), viseca, load_catalogue(data_dir),
                     cors_origins=[o for o in os.environ.get("LEASH_CORS_ORIGINS", "http://localhost:5173").split(",")
                                   if o],
                     app_dist=Path(dist) if dist else None)
    server = uvicorn.Server(uvicorn.Config(app, host=os.environ.get("LEASH_API_HOST", "0.0.0.0"),
                                           port=int(os.environ.get("LEASH_API_PORT", "8080")),
                                           log_config=None))
    asyncio.run(serve_until_stopped(server, viseca))
