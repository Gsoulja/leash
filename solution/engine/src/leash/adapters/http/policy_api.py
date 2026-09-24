"""Mandate lifecycle endpoints of the policy service (LEASH-061), in the shapes of contracts/policy-api.yaml.

Two drafts, never confused: the local policy draft (LD-…) is the compiled instruction the customer is
still shaping; submitting posts it to Viseca as a platform draft, and the customer is shown exactly that
body. Only the customer's explicit confirm calls Viseca's /confirm; the returned mandate_id is stored
with the rules as version 1. The draft row is locked for the whole confirm, so a double click confirms at
Viseca once and both clicks get the same mandate. A draft whose mandate was revoked can't be confirmed
again; the customer starts a new draft.

Tighten and revoke are LEASH-062.
"""

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Protocol

import asyncpg
import httpx
from fastapi import APIRouter, Body, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from leash.adapters.http.query_api import PAYMENT_COLUMNS, payment_view
from leash.adapters.postgres.mandates import StoredMandates
from leash.adapters.postgres.repository import PostgresRepository
from leash.adapters.postgres.unit_of_work import LockTimeout, ResolutionTransaction
from leash.adapters.viseca_api.client import VisecaApiError
from leash.application.resolve import ResolveAsk
from leash.domain import mandate as m
from leash.domain.mandate import LooseningError, Rule
from leash.domain.money import fmt_chf
from leash.domain.states import IllegalTransition
from leash.application.clarify import AnswerError, clarify
from leash.policy.compiler import CatalogueItem
from leash.policy.hard_rules import (AppendOnlyError, HardRulesError, check_append_only, mandate_from_api,
                                     mandate_to_api, rule_from_api, rule_to_api)
from leash.policy.registry import describe_field

log = logging.getLogger("leash.policy")
_UNANSWERED = datetime(2000, 1, 1, tzinfo=timezone.utc)  # a call that ended without an answer, not in progress
CONFIRM_WAIT_SECONDS = 15.0  # a second click waits this long for the first; an older claim counts as unanswered


class PlatformMandates(Protocol):
    async def create_mandate(self, draft: Mapping[str, Any]) -> Any: ...

    async def confirm_mandate(self, draft_id: str) -> Any: ...


_STALE = ("This draft moved on since you reviewed it (you reviewed revision {reviewed}, it is now "
          "revision {current}). Review the current one before submitting or confirming.")


class _BadRevision(ValueError):
    """A revision was stated but is not a whole number: refuse rather than skip the staleness check."""


def _reviewed_revision(body: Any) -> int | None:
    """The revision the customer reviewed, when the caller states one. Absent means "whatever is current"."""
    if not isinstance(body, Mapping) or "revision" not in body:
        return None
    value = body["revision"]
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise _BadRevision(f"revision must be a whole number from 1, not {value!r}")
    return value


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def _pick(body: Any, key: str) -> str:
    """A field of a Viseca response, at the top level or inside its `data` object."""
    for node in (body, body.get("data") if isinstance(body, Mapping) else None):
        if isinstance(node, Mapping) and isinstance(node.get(key), str) and node[key]:
            return str(node[key])
    raise ValueError(f"the Viseca response has no {key}")


async def _mandate_view(conn: asyncpg.Connection, mandate_id: str) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """select m.mandate_id, m.instruction, m.status, v.version, v.hard_rules, v.uncertainty_policy, v.compiled
           from mandates m join mandate_versions v using (mandate_id)
           where m.mandate_id = $1 order by v.version desc limit 1""", mandate_id)
    if row is None:
        return None
    compiled = json.loads(row["compiled"]) if row["compiled"] else {}
    return {"mandate_id": row["mandate_id"], "version": row["version"], "status": row["status"],
            "instruction": row["instruction"], "rules": compiled.get("rules", []),
            "hard_rules": json.loads(row["hard_rules"]), "uncertainty_policy": row["uncertainty_policy"],
            "applies_from": "next run",
            "revocation": None if row["status"] == "active" else {"platform_confirmed": True, "note": None}}


def policy_router(pool: Callable[[], asyncpg.Pool], viseca: PlatformMandates,
                  catalogue: Sequence[CatalogueItem]) -> APIRouter:
    router = APIRouter()
    items = list(catalogue)

    @router.post("/api/policies/drafts", status_code=201)
    async def create_draft(body: dict[str, Any] = Body(...)) -> Any:
        instruction = body.get("instruction")
        if not isinstance(instruction, str) or not instruction.strip() or set(body) - {"context"} != {"instruction"}:
            return _error(422, "invalid_request", "Send exactly one non-empty instruction.")
        if "context" in body and not isinstance(body["context"], dict):
            return _error(422, "invalid_request", "context must be an object.")
        draft_id = f"LD-{uuid.uuid4().hex[:12]}"
        view = {"draft_id": draft_id, "revision": 1, **clarify(instruction, [], items)}
        context = body.get("context") if isinstance(body.get("context"), dict) else {}
        async with pool().acquire() as conn, conn.transaction():
            await conn.execute("insert into policy_drafts (draft_id, instruction, draft, revision) "
                               "values ($1, $2, $3::jsonb, 1)", draft_id, instruction, json.dumps(view))
            await conn.execute("insert into draft_revisions (draft_id, revision, draft, answers, context) "
                               "values ($1, 1, $2::jsonb, '[]'::jsonb, $3::jsonb)",
                               draft_id, json.dumps(view), json.dumps(context))
        return view

    @router.get("/api/policies/drafts/{draft_id}")
    async def get_draft(draft_id: str) -> Any:
        async with pool().acquire() as conn:
            draft = await conn.fetchval("select draft from policy_drafts where draft_id = $1", draft_id)
        return json.loads(draft) if draft else _error(404, "draft_not_found", "No draft with this ID.")

    @router.post("/api/policies/drafts/{draft_id}/answers")
    async def answer_questions(draft_id: str, body: Any = Body(...)) -> Any:
        given = body.get("answers") if isinstance(body, dict) and set(body) == {"answers"} else None
        if not isinstance(given, list) or not given or not all(
                isinstance(a, dict) and set(a) == {"question_id", "answer"}
                and all(isinstance(v, str) for v in a.values()) for a in given):
            return _error(422, "invalid_request", 'Send {"answers": [{"question_id": …, "answer": …}]}.')
        async with pool().acquire() as conn, conn.transaction():
            row = await conn.fetchrow("select instruction, answers, platform_draft_id, revision from policy_drafts "
                                      "where draft_id = $1 for update", draft_id)
            if row is None:
                return _error(404, "draft_not_found", "No draft with this ID.")
            if row["platform_draft_id"] is not None:  # Viseca has no draft update: start a new draft instead
                return _error(409, "already_submitted",
                              "This draft is already at Viseca; start a new one to change it.")
            answers = list(json.loads(row["answers"])) + given
            revision = int(row["revision"]) + 1
            try:
                view = {"draft_id": draft_id, "revision": revision, **clarify(row["instruction"], answers, items)}
            except AnswerError as exc:
                return _error(422, "invalid_answer", str(exc))
            await conn.execute("update policy_drafts set answers = $2::jsonb, draft = $3::jsonb, revision = $4 "
                               "where draft_id = $1", draft_id, json.dumps(answers), json.dumps(view), revision)
            # the earlier proposal is marked, never deleted: the transcript stays reviewable
            await conn.execute("update draft_revisions set superseded = true where draft_id = $1 and revision < $2",
                               draft_id, revision)
            await conn.execute(
                "insert into draft_revisions (draft_id, revision, draft, answers, context) "
                "values ($1, $2, $3::jsonb, $4::jsonb, coalesce((select context from draft_revisions "
                "where draft_id = $1 and revision = $2 - 1), '{}'::jsonb))",
                draft_id, revision, json.dumps(view), json.dumps(answers))
            return view

    @router.post("/api/policies/drafts/{draft_id}/submit")
    async def submit(draft_id: str, body: dict[str, Any] | None = Body(default=None)) -> Any:
        try:
            reviewed = _reviewed_revision(body)
        except _BadRevision as exc:
            return _error(422, "invalid_request", str(exc))
        async with pool().acquire() as conn, conn.transaction():
            row = await conn.fetchrow("select draft, platform_body, revision from policy_drafts "
                                      "where draft_id = $1 for update", draft_id)
            if row is None:
                return _error(404, "draft_not_found", "No draft with this ID.")
            if reviewed is not None and reviewed != int(row["revision"]):
                return _error(409, "stale_revision", _STALE.format(reviewed=reviewed, current=row["revision"]))
            if row["platform_body"]:  # submitted already: the same platform draft, never a second one
                return json.loads(row["platform_body"])
            draft = json.loads(row["draft"])
            if draft["status"] != "ready":
                return _error(409, "questions_open", "Answer the open questions before submitting.")
            body = {"instruction": draft["instruction"], "hard_rules": draft["hard_rules"],
                    "uncertainty_policy": draft["uncertainty_policy"], "guidance": draft["notes"],
                    "open_questions": [q["text"] for q in draft["open_questions"]]}
            try:
                platform_id = _pick(await viseca.create_mandate(body), "draft_id")
            except (VisecaApiError, httpx.HTTPError, ValueError) as exc:
                return _error(502, "platform_error", f"Viseca did not take the draft ({exc}).")
            posted = {"draft_id": draft_id, "platform_draft_id": platform_id, **body}
            await conn.execute("update policy_drafts set platform_draft_id = $2, platform_body = $3::jsonb "
                               "where draft_id = $1", draft_id, platform_id, json.dumps(posted))
            return posted

    async def confirm_state(draft_id: str) -> asyncpg.Record | None:
        async with pool().acquire() as conn:
            row: asyncpg.Record | None = await conn.fetchrow(
                "select draft, platform_draft_id, platform_body, mandate_id, confirmed_mandate_id, confirm_started_at, "
                "revision from policy_drafts where draft_id = $1", draft_id)
            return row

    async def finish(draft_id: str, mandate_id: str) -> Any:
        """Store the mandate Viseca confirmed as version 1 and link the draft (idempotent)."""
        try:
            async with pool().acquire() as conn, conn.transaction():
                row = await conn.fetchrow("select draft, platform_body, mandate_id, revision from policy_drafts "
                                          "where draft_id = $1 for update", draft_id)
                if row["mandate_id"] is None:
                    posted, draft = json.loads(row["platform_body"]), json.loads(row["draft"])
                    await conn.execute("insert into mandates (mandate_id, instruction, status) "
                                       "values ($1, $2, 'active')", mandate_id, posted["instruction"])
                    await conn.execute(
                        "insert into mandate_versions (mandate_id, version, hard_rules, uncertainty_policy, compiled) "
                        "values ($1, 1, $2::jsonb, $3, $4::jsonb)", mandate_id, json.dumps(posted["hard_rules"]),
                        posted["uncertainty_policy"], json.dumps({"rules": draft["rules"], "notes": draft["notes"],
                                                                  "draft_id": draft_id,
                                                                  "revision": int(row["revision"])}))
                    await conn.execute("update policy_drafts set mandate_id = $2, confirm_started_at = null "
                                       "where draft_id = $1", draft_id, mandate_id)
                view = await _mandate_view(conn, mandate_id)
        except asyncpg.PostgresError as exc:
            log.error("INTEGRITY: Viseca confirmed mandate %s for draft %s but saving it failed: %s",
                      mandate_id, draft_id, exc)
            return _error(500, "local_write_failed", f"Viseca confirmed mandate {mandate_id}, but saving it "
                                                     "failed. Confirm again to finish; Viseca is not asked twice.")
        if view is None or view["status"] != "active":
            return _error(409, "mandate_revoked", "This mandate is no longer active; start a new draft.")
        return view

    @router.post("/api/policies/drafts/{draft_id}/confirm")
    async def confirm(draft_id: str, body: dict[str, Any] = Body(...)) -> Any:
        if set(body) - {"revision"} != {"confirmed"} or body["confirmed"] is not True:  # 1 == True: compare identity
            return _error(422, "not_confirmed", "The customer must confirm with confirmed: true.")
        try:
            reviewed = _reviewed_revision(body)
        except _BadRevision as exc:
            return _error(422, "invalid_request", str(exc))
        deadline = time.monotonic() + CONFIRM_WAIT_SECONDS
        waited = False  # a click that waited on another request's call reports its outcome, never calls again
        while True:
            row = await confirm_state(draft_id)
            if row is None:
                return _error(404, "draft_not_found", "No draft with this ID.")
            if row["platform_draft_id"] is None:
                return _error(409, "not_submitted", "Submit the draft to Viseca before confirming.")
            if reviewed is not None and reviewed != int(row["revision"]):
                return _error(409, "stale_revision", _STALE.format(reviewed=reviewed, current=row["revision"]))
            known = row["mandate_id"] or row["confirmed_mandate_id"]
            if known is not None:  # confirmed already (a double click), or only our write is left
                return await finish(draft_id, str(known))
            # Claim the call: only one request talks to Viseca at a time; the others wait for its outcome.
            started = row["confirm_started_at"]
            window = timedelta(seconds=CONFIRM_WAIT_SECONDS)
            fresh = started is not None and started > datetime.now(timezone.utc) - window
            if not fresh:
                if waited:
                    return _error(409, "confirm_outcome_unknown",
                                  "The confirmation in progress got no answer from Viseca; the mandate may already "
                                  "be active. Please check again in a moment.")
                async with pool().acquire() as conn:
                    claim = await conn.fetchval(
                        "update policy_drafts set confirm_started_at = now() where draft_id = $1 "
                        "and mandate_id is null and confirmed_mandate_id is null "
                        "and confirm_started_at is not distinct from $2 returning confirm_started_at",
                        draft_id, started)
                if claim is not None:
                    unknown_before = started is not None  # an earlier call ended without an answer
                    break
                continue  # someone else claimed it between our read and our update
            waited = True
            if time.monotonic() >= deadline:
                return _error(409, "confirm_in_progress", "This confirmation is still being processed; "
                                                          "please check again in a moment.")
            await asyncio.sleep(0.1)
        try:  # cut well inside the claim window, so no other request can take over while this call runs
            mandate_id = _pick(await asyncio.wait_for(viseca.confirm_mandate(row["platform_draft_id"]),
                                                      timeout=CONFIRM_WAIT_SECONDS * 0.8), "mandate_id")
        except VisecaApiError as exc:
            if 400 <= exc.status < 500 and unknown_before:
                log.error("INTEGRITY: draft %s: an earlier confirm got no answer and Viseca now refuses (%s); "
                          "the mandate may be active at Viseca", draft_id, exc)
                return _error(409, "confirm_outcome_unknown",
                              "An earlier confirmation got no answer; the mandate may already be active at "
                              "Viseca. An operator must check before you confirm again.")
            if 400 <= exc.status < 500:  # a definite no: nothing is pending any more
                async with pool().acquire() as conn:
                    await conn.execute("update policy_drafts set confirm_started_at = null where draft_id = $1 "
                                       "and confirm_started_at = $2", draft_id, claim)
                return _error(409, "platform_refused", f"Viseca refused the confirmation ({exc}).")
            return _error(502, "platform_error", f"Viseca did not confirm ({exc}).")
        except (httpx.HTTPError, ValueError, TimeoutError) as exc:  # no answer: Viseca may have confirmed
            async with pool().acquire() as conn:
                await conn.execute("update policy_drafts set confirm_started_at = $3 where draft_id = $1 "
                                   "and confirm_started_at = $2", draft_id, claim, _UNANSWERED)
            return _error(502, "platform_error", f"Viseca did not confirm ({exc}); please try again.")
        try:
            async with pool().acquire() as conn:
                await conn.execute("update policy_drafts set confirmed_mandate_id = $2 where draft_id = $1 "
                                   "and confirmed_mandate_id is null", draft_id, mandate_id)  # never overwritten
        except asyncpg.PostgresError as exc:
            log.error("INTEGRITY: Viseca confirmed mandate %s for draft %s but it could not be recorded: %s",
                      mandate_id, draft_id, exc)
            return _error(500, "local_write_failed", f"Viseca confirmed mandate {mandate_id}, but saving it failed.")
        return await finish(draft_id, mandate_id)

    @router.get("/api/mandates")
    async def mandates() -> Any:
        async with pool().acquire() as conn:
            rows = await conn.fetch("select mandate_id, status from mandates order by created_at, mandate_id")
            views = [v for r in rows if (v := await _mandate_view(conn, r["mandate_id"])) is not None]
        current = [v["mandate_id"] for v in views if v["status"] == "active"]
        return {"mandates": views, "current_mandate_id": current[-1] if current else None}

    @router.get("/api/mandates/{mandate_id}")
    async def mandate(mandate_id: str) -> Any:
        async with pool().acquire() as conn:
            view = await _mandate_view(conn, mandate_id)
        return view if view is not None else _error(404, "mandate_not_found", "No mandate with this ID.")

    return router


def create_policy_app(database_url: str, viseca: PlatformMandates, catalogue: Sequence[CatalogueItem]) -> FastAPI:
    state: dict[str, asyncpg.Pool] = {}

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        state["pool"] = await asyncpg.create_pool(database_url, min_size=1, max_size=4)
        try:
            yield
        finally:
            await state["pool"].close()

    app = FastAPI(title="Leash policy service", lifespan=lifespan)

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception) -> JSONResponse:  # never a plain-text 500
        log.exception("unexpected error in the policy service")
        return _error(500, "internal_error", "Something went wrong; nothing was confirmed twice. Please try again.")

    @app.exception_handler(RequestValidationError)
    async def invalid(_: Request, exc: RequestValidationError) -> JSONResponse:  # the contract's error shape
        return _error(422, "invalid_request", "The request body must be a JSON object of the documented shape.")

    app.include_router(policy_router(lambda: state["pool"], viseca, catalogue))
    return app



# ----- the customer's answer to an ask (LEASH-063) --------------------------------------------------------

RESOLVE_SEND_SECONDS = 2.0  # below the outbox grace period (3 s), so the outbox never overlaps this send


class ResolveApi(Protocol):
    async def resolve(self, authorization_id: str, answer: Mapping[str, Any]) -> Any: ...


def asks_router(pool: Callable[[], asyncpg.Pool], mandates: StoredMandates, viseca: ResolveApi, *,
                engine_version: str) -> APIRouter:
    """POST /api/asks/{authorization_id}/answer: record the answer under the card lock (application/resolve),
    queue /resolve in the outbox with it, then POST it at once unless an earlier row for that purchase (its
    decision) is still unsent. An approval is re-checked against the run's stored mandate (DEC-012)."""
    router = APIRouter()

    @router.post("/api/asks/{authorization_id}/answer")
    async def answer(authorization_id: str, body: Any = Body(...)) -> Any:
        if not isinstance(body, dict) or set(body) != {"decision"} or body["decision"] not in ("approve", "decline"):
            return _error(422, "invalid_request", 'Send {"decision": "approve"} or {"decision": "decline"}.')
        async with pool().acquire() as conn:
            if not await conn.fetchval("select exists (select 1 from authorizations where authorization_id = $1)",
                                       authorization_id):
                return _error(404, "not_found", "No such payment.")
        await mandates.refresh(pool())  # a run started a moment ago is known before its approval is re-checked
        resolve = ResolveAsk(ResolutionTransaction(pool()), mandates, engine_version=engine_version)
        try:
            outcome = await resolve.answer(authorization_id, body["decision"], now=datetime.now(timezone.utc))
        except IllegalTransition:
            return _error(409, "not_waiting", "This payment is no longer waiting for an answer.")
        except LockTimeout:
            return _error(503, "busy", "This card is busy right now; please try again.")
        if outcome.state == "timed_out":
            return _error(409, "not_waiting", "The time to answer this payment has expired.")
        if outcome.blocked:
            return _error(422, "cannot_approve", outcome.explanation or "A rule you set now blocks this payment.")
        if outcome.response is not None:
            await _send_now(pool(), viseca, authorization_id, outcome.response)
        async with pool().acquire() as conn:
            row = await conn.fetchrow(f"select {PAYMENT_COLUMNS} from authorizations a where a.authorization_id = $1",
                                      authorization_id)
        return payment_view(row)

    return router


async def _send_now(pool: asyncpg.Pool, viseca: ResolveApi, authorization_id: str, body: Mapping[str, Any]) -> None:
    """POST /resolve right after the commit; the outbox resends it if this fails (DEC-007)."""
    async with pool.acquire() as conn:
        earlier = await conn.fetchval("select count(*) from outbox where authorization_id = $1 and sent_at is null "
                                      "and endpoint <> 'resolve'", authorization_id)
    if earlier:  # its decision hasn't reached Viseca yet: the outbox sends both, in order
        return
    try:
        await asyncio.wait_for(viseca.resolve(authorization_id, body), timeout=RESOLVE_SEND_SECONDS)
    except Exception as exc:  # left unsent: the outbox retries with backoff
        log.warning("sending /resolve failed (%s); the outbox will retry", exc,
                    extra={"authorization_id": authorization_id})
        return
    async with pool.acquire() as conn:
        await conn.execute("update outbox set sent_at = now(), attempts = attempts + 1, last_attempt_at = now() "
                           "where authorization_id = $1 and endpoint = 'resolve' and sent_at is null", authorization_id)


# ----- scenario runs with their mandate snapshot (LEASH-066) ---------------------------------------------

RUN_STATUS_SECONDS = 2.0
_FINISHED = frozenset({"completed", "finished"})
_FAILED = frozenset({"stopped", "failed", "cancelled", "canceled", "expired"})


class RunApi(Protocol):
    async def start_run(self, scenario_id: str, mandate_id: str) -> Any: ...

    async def get_run(self, run_id: str) -> Any: ...


def _run_counters(body: Mapping[str, Any]) -> dict[str, int]:
    """Run progress, whichever shape the platform used: the live API sends top-level `*_event_count` fields, the
    fake platform a nested `counters` object (LEASH-159). Names are passed through as the platform spells them."""
    def counts(items: Any) -> dict[str, int]:  # the platform is untrusted input: bools and junk are not counts
        pairs = items.items() if isinstance(items, Mapping) else ()
        return {k: v for k, v in pairs if isinstance(v, int) and not isinstance(v, bool)}

    return counts(body.get("counters")) or {k: v for k, v in counts(body).items() if k.endswith("_count")}


def _data(body: Any) -> Mapping[str, Any]:
    if isinstance(body, Mapping):
        inner = body.get("data")
        return inner if isinstance(inner, Mapping) else body
    return {}


def runs_router(pool: Callable[[], asyncpg.Pool], viseca: RunApi, scenario_cards: Mapping[str, str]) -> APIRouter:
    """POST /api/runs starts a run at Viseca and stores it with the mandate version it uses (DEC-003). The
    platform's snapshot is authoritative: it is stored as the run's version (the local version with the same
    rules, or a new one), and a snapshot that differs from our latest version is logged for a person."""
    router = APIRouter()
    repo_of = PostgresRepository

    async def platform_status(run_id: str) -> tuple[str, dict[str, int]]:
        try:
            body = _data(await asyncio.wait_for(viseca.get_run(run_id), timeout=RUN_STATUS_SECONDS))
        except Exception as exc:  # the platform is unreachable: show the run as still running
            log.warning("run %s: status unavailable (%s)", run_id, exc)
            return "running", {}
        status = str(body.get("status", "running")).lower()
        counters = _run_counters(body)
        return ("finished" if status in _FINISHED else "failed" if status in _FAILED else "running"), counters

    async def view(row: asyncpg.Record) -> dict[str, Any]:
        status, counters = await platform_status(row["run_id"])
        return {"run_id": row["run_id"], "scenario_id": row["scenario_id"], "mandate_id": row["mandate_id"],
                "mandate_version": row["mandate_version"], "status": status, "counters": counters}

    @router.post("/api/runs", status_code=201)
    async def start(body: Any = Body(...)) -> Any:
        if not isinstance(body, dict) or set(body) != {"scenario_id", "mandate_id"} or \
                not all(isinstance(v, str) and v for v in body.values()):
            return _error(422, "invalid_request", 'Send {"scenario_id": …, "mandate_id": …}.')
        scenario, mandate_id = body["scenario_id"], body["mandate_id"]
        async with pool().acquire() as conn:
            local = await conn.fetchrow(
                "select m.status, m.instruction, v.version, v.hard_rules, v.uncertainty_policy from mandates m "
                "join mandate_versions v using (mandate_id) where mandate_id = $1 order by v.version desc limit 1",
                mandate_id)
        if local is None:
            return _error(404, "mandate_not_found", "No mandate with this ID.")
        if local["status"] != "active":
            return _error(409, "mandate_not_active", "Only an active mandate can start a run.")
        try:
            started = _data(await viseca.start_run(scenario, mandate_id))
        except VisecaApiError as exc:
            return _error(409 if 400 <= exc.status < 500 else 502, "platform_refused" if exc.status < 500
                          else "platform_error", f"Viseca did not start the run ({exc}).")
        except (httpx.HTTPError, OSError) as exc:
            return _error(502, "platform_error", f"Viseca did not start the run ({exc}).")
        run_id = started.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            return _error(502, "platform_error", "Viseca started a run but sent no run_id.")
        snapshot = started.get("mandate")
        if isinstance(snapshot, Mapping):
            try:  # the platform's copy is authoritative only when it is a readable mandate
                mandate_from_api({"instruction": snapshot.get("instruction") or local["instruction"] or "(mandate)",
                                  "hard_rules": snapshot.get("hard_rules"),
                                  "uncertainty_policy": snapshot.get("uncertainty_policy")})
            except (HardRulesError, TypeError, AttributeError) as exc:
                log.error("INTEGRITY: run %s: Viseca's snapshot of mandate %s can't be read (%s); storing the version "
                          "the customer confirmed", run_id, mandate_id, exc)
                snapshot = None
        if not isinstance(snapshot, Mapping):
            log.warning("run %s: no readable mandate snapshot from Viseca; storing our latest version", run_id)
            snapshot = {"mandate_id": mandate_id, "instruction": local["instruction"],
                        "hard_rules": json.loads(local["hard_rules"]),
                        "uncertainty_policy": local["uncertainty_policy"]}
        elif json.loads(local["hard_rules"]) != list(snapshot.get("hard_rules") or []) or \
                snapshot.get("uncertainty_policy") != local["uncertainty_policy"]:
            log.error("INTEGRITY: run %s: the platform's snapshot of mandate %s differs from our version %s; the "
                      "platform's is used for this run", run_id, mandate_id, local["version"])
        card = snapshot.get("card_id") if isinstance(snapshot.get("card_id"), str) else scenario_cards.get(scenario)
        if card is None:
            return _error(502, "platform_error", f"No card is known for scenario {scenario}.")
        await repo_of(pool()).ensure_run(run_id, {"mandate": dict(snapshot, mandate_id=mandate_id),
                                                  "scenario_id": scenario}, card)
        async with pool().acquire() as conn:
            row = await conn.fetchrow("select run_id, scenario_id, mandate_id, mandate_version from runs "
                                      "where run_id = $1", run_id)
        counters = _run_counters(started)
        return {"run_id": row["run_id"], "scenario_id": row["scenario_id"], "mandate_id": row["mandate_id"],
                "mandate_version": row["mandate_version"], "status": "running", "counters": counters}

    @router.get("/api/runs")
    async def runs() -> Any:
        async with pool().acquire() as conn:
            rows = await conn.fetch("select run_id, scenario_id, mandate_id, mandate_version from runs "
                                    "order by started_at desc, run_id desc")
        views = [await view(r) for r in rows]
        current = next((v["run_id"] for v in views if v["status"] == "running"), None)
        return {"runs": views, "current_run_id": current}

    @router.get("/api/runs/{run_id}")
    async def run(run_id: str) -> Any:
        async with pool().acquire() as conn:
            row = await conn.fetchrow("select run_id, scenario_id, mandate_id, mandate_version from runs "
                                      "where run_id = $1", run_id)
        return await view(row) if row is not None else _error(404, "run_not_found", "No run with this ID.")

    return router


# ----- tighten and revoke (LEASH-062, DEC-006) ------------------------------------------------------------

class MandateChanges(Protocol):
    async def patch_mandate(self, mandate_id: str, changes: Mapping[str, Any]) -> Any: ...

    async def get_mandate(self, mandate_id: str) -> Any: ...

    async def revoke_mandate(self, mandate_id: str) -> Any: ...


def _rule_text(rule: Rule) -> str:
    """A tightened rule in the customer's words."""
    if rule.field == m.F_BILLING_CHF and isinstance(rule.value, Decimal):
        words = "At most" if rule.operator == "<=" else "Under" if rule.operator == "<" else rule.operator
        where = f"across any {rule.period_days} days" if rule.scope == "period" else "per order, delivery included"
        return f"{words} {fmt_chf(rule.value)} {where}"
    value = ", ".join(rule.value) if isinstance(rule.value, tuple) else str(rule.value)
    return f"{describe_field(rule.field)} {rule.operator} {value}"


async def _applied_at_viseca(viseca: MandateChanges, mandate_id: str, hard_rules: list[dict[str, Any]],
                             policy: str) -> bool:
    """After a PATCH got no answer: does Viseca now hold exactly the rules and policy we sent?"""
    try:
        held = _data(await asyncio.wait_for(viseca.get_mandate(mandate_id), timeout=RUN_STATUS_SECONDS))
    except Exception:
        return False
    if held.get("status", "active") != "active":  # revoked meanwhile: nothing to store as a tightening
        return False
    try:
        check_append_only(hard_rules, list(held.get("hard_rules") or []))
    except (AppendOnlyError, AttributeError, TypeError):  # different, or not rules at all
        return False
    return len(held.get("hard_rules") or []) == len(hard_rules) and held.get("uncertainty_policy") == policy


def mandate_changes_router(pool: Callable[[], asyncpg.Pool], viseca: MandateChanges) -> APIRouter:
    """Tighten: every new rule must be stricter on its own (CompiledMandate.tighten), uncertainty may only move to
    decline. The PATCH carries every existing rule unchanged plus the new ones; the new version is stored only
    after Viseca accepts it. Revoke: DELETE at Viseca, then the mandate is revoked here (idempotent)."""
    router = APIRouter()

    @router.post("/api/mandates/{mandate_id}/tighten")
    async def tighten(mandate_id: str, body: Any = Body(...)) -> Any:
        if not isinstance(body, dict) or not body or set(body) - {"add_hard_rules", "uncertainty_policy"}:
            return _error(422, "invalid_request", "Send add_hard_rules and/or uncertainty_policy.")
        raw = body.get("add_hard_rules")
        if "add_hard_rules" in body and (not isinstance(raw, list) or not raw):  # null is not "not sent"
            return _error(422, "invalid_request", "add_hard_rules must be a non-empty list.")
        policy = body.get("uncertainty_policy")
        if "uncertainty_policy" in body and policy != "decline":
            return _error(422, "would_loosen", "When unsure, the agent can only be told to decline more.")
        try:
            new_rules = [rule_from_api(r) for r in raw or []]
        except HardRulesError as exc:
            return _error(422, "invalid_rule", str(exc))
        async with pool().acquire() as conn, conn.transaction():
            row = await conn.fetchrow("select status, instruction from mandates where mandate_id = $1 for update",
                                      mandate_id)
            if row is None:
                return _error(404, "mandate_not_found", "No mandate with this ID.")
            if row["status"] != "active":
                return _error(409, "mandate_not_active", "Only an active mandate can be tightened.")
            latest = await conn.fetchrow("select version, hard_rules, uncertainty_policy, compiled "
                                         "from mandate_versions "
                                         "where mandate_id = $1 order by version desc limit 1", mandate_id)
            before = json.loads(latest["hard_rules"])
            current, _ = mandate_from_api({"instruction": row["instruction"] or "(stored mandate)",
                                           "hard_rules": before,
                                           "uncertainty_policy": latest["uncertainty_policy"]})
            try:
                after = current
                for rule in new_rules:  # each one on its own: a looser rule can't hide next to a stricter one
                    after = after.tighten(rule)
                if policy is not None:
                    after = after.tighten_uncertainty(policy)
            except LooseningError as exc:
                return _error(422, "would_loosen", f"{str(exc)[:1].upper()}{str(exc)[1:]}. "
                                                   "Create a new permission to loosen it.")
            hard_rules = before + [rule_to_api(r) for r in new_rules]
            check_append_only(before, hard_rules)
            change: dict[str, Any] = {"hard_rules": hard_rules}
            if policy is not None:
                change["uncertainty_policy"] = policy
            try:
                await viseca.patch_mandate(mandate_id, change)
            except VisecaApiError as exc:
                return _error(409 if 400 <= exc.status < 500 else 502, "platform_refused" if exc.status < 500
                              else "platform_error", f"Viseca did not accept the change ({exc}).")
            except (httpx.HTTPError, OSError) as exc:  # no answer: read back what Viseca holds now
                if not await _applied_at_viseca(viseca, mandate_id, hard_rules, after.uncertainty):
                    return _error(502, "platform_error", f"Viseca did not accept the change ({exc}).")
                log.warning("mandate %s: the PATCH got no answer, but Viseca holds the change; storing it", mandate_id)
            compiled = json.loads(latest["compiled"]) if latest["compiled"] else {}
            views = list(compiled.get("rules", [])) + [
                {"text": _rule_text(r), "source": "customer", "decision": None, "tightened": True} for r in new_rules]
            await conn.execute(
                "insert into mandate_versions (mandate_id, version, hard_rules, uncertainty_policy, compiled) "
                "values ($1, $2, $3::jsonb, $4, $5::jsonb)", mandate_id, latest["version"] + 1, json.dumps(hard_rules),
                after.uncertainty, json.dumps({**compiled, "rules": views}))
            return await _mandate_view(conn, mandate_id)

    @router.delete("/api/mandates/{mandate_id}")
    async def revoke(mandate_id: str) -> Any:
        async with pool().acquire() as conn, conn.transaction():
            status = await conn.fetchval("select status from mandates where mandate_id = $1 for update", mandate_id)
            if status is None:
                return _error(404, "mandate_not_found", "No mandate with this ID.")
            if status == "active":
                try:
                    await viseca.revoke_mandate(mandate_id)
                except VisecaApiError as exc:
                    if exc.status != 404 and exc.status != 409:
                        return _error(502, "platform_error", f"Viseca did not revoke it ({exc}); it is still active.")
                    log.warning("mandate %s: Viseca says it is not active (%s); revoking it here too", mandate_id, exc)
                except (httpx.HTTPError, OSError) as exc:
                    return _error(502, "platform_error", f"Viseca did not revoke it ({exc}); it is still active.")
                await conn.execute("update mandates set status = 'revoked' where mandate_id = $1", mandate_id)
            return await _mandate_view(conn, mandate_id)

    return router
