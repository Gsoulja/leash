"""A local stand-in for the hosted Viseca API, for end-to-end tests and rehearsals without the team key.

It follows technical_details.md: mandates (draft → confirm → PATCH/DELETE), scenario runs, a long-poll
queue with real-clock deadlines, decisions, /resolve for customer answers, authorizations and bootstrap.
Behaviour the brief leaves unspecified (late decisions, expired asks, conflicting answers) is modelled
conservatively and documented here; perfect fidelity is out of scope.

Test knobs:
- clock: the real-clock `now()` used for deadlines and the human window (inject one to move time).
- queue_delay_seconds: pause before each next purchase is queued (after the previous one is answered).
- delivery_lag_seconds: a slow queue; a queued purchase is delivered only this long after queueing,
  while its deadline still counts from queueing.
- repeat: pack authorization IDs that are delivered twice (same live ID and deadline).
- `received` / `resolutions`: every decision and customer answer accepted; `rejected`: every one refused
  (with its error code), for assertions.

Documented behaviour it follows: a non-null related_authorization_id is rewritten to the related
purchase's live ID in that run; a revoked mandate stops further purchases from being queued (what
happens to one already queued or waiting is unspecified, so it is left as it is).

Only the in-order flow is modelled: the next purchase is queued once the previous one has an automated
answer (or its deadline passed), so a step_up waiting for the customer doesn't hold up the queue.
"""

import asyncio
import csv
import json
import time
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from leash.adapters.pack.loader import Attempt, Pack
from leash.domain.purchase import Purchase

DECISION_SECONDS = 8
HUMAN_WINDOW_SECONDS = 120
HISTORY_WINDOW_MINUTES = 10
POLL_STEP_SECONDS = 0.02


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _num(value: Decimal) -> float:
    return float(value)


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def bad_evidence(body: Any) -> bool:
    """The hosted API validates `evidence` as a list of objects and 422s on a list of strings
    (`dict_type`, measured 2026-09-25). A fake that accepts strings hides that until event day."""
    evidence = body.get("evidence") if isinstance(body, Mapping) else None
    if evidence is None:
        return False
    return not isinstance(evidence, list) or any(not isinstance(e, Mapping) for e in evidence)


@dataclass
class Mandate:
    mandate_id: str
    status: str  # draft | active | revoked
    body: dict[str, Any]


@dataclass
class LiveAuthorization:
    live_id: str
    attempt: Attempt
    queued_at: datetime
    deadline_at: datetime
    deliveries: int = 0
    decision: str | None = None  # approve | decline | step_up
    answer: str | None = None  # the customer's approve | decline
    human_expires_at: datetime | None = None
    decided_at: datetime | None = None
    late: bool = False

    def status(self, now: datetime) -> str:
        if self.decision is None:
            return "timed_out" if self.late or now >= self.deadline_at else "pending"
        if self.decision == "approve":
            return "approved"
        if self.decision == "decline":
            return "declined"
        if self.answer is not None:
            return "approved" if self.answer == "approve" else "declined"
        assert self.human_expires_at is not None
        return "timed_out" if now >= self.human_expires_at else "waiting_for_customer"

    @property
    def purchase(self) -> Purchase:
        return self.attempt.purchase


@dataclass
class Run:
    run_id: str
    scenario_id: str
    mandate: dict[str, Any]
    attempts: list[Attempt]
    started_at: datetime
    queued: list[LiveAuthorization] = field(default_factory=list)


class FakeViseca:
    def __init__(self, pack: Pack, *, api_key: str = "fake-team-key",
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 decision_seconds: float = DECISION_SECONDS, human_window_seconds: float = HUMAN_WINDOW_SECONDS,
                 queue_delay_seconds: float = 0, delivery_lag_seconds: float = 0, repeat: Iterable[str] = (),
                 api_version: str = "fake-1", data_version: str = "fake-pack",
                 decision_delay_seconds: float = 0, poll_delay_seconds: float = 0,
                 fail_decisions: Mapping[str, int] | None = None, state_file: Path | None = None):
        self.pack, self.api_key, self.clock = pack, api_key, clock
        self.decision_seconds, self.human_window_seconds = decision_seconds, human_window_seconds
        self.queue_delay = timedelta(seconds=queue_delay_seconds)
        self.delivery_lag = timedelta(seconds=delivery_lag_seconds)
        self.repeat = set(repeat)
        self.api_version, self.data_version = api_version, data_version
        # fault injection (LEASH-126): slow answers and polls, and the first N decision POSTs per source ID
        # refused with 503 before they are recorded
        self.decision_delay, self.poll_delay = decision_delay_seconds, poll_delay_seconds
        self.fail_decisions = dict(fail_decisions or {})
        self.received: list[dict[str, Any]] = []
        self.resolutions: list[dict[str, Any]] = []
        self.rejected: list[dict[str, Any]] = []
        self.mandates: dict[str, Mandate] = {}
        self.runs: dict[str, Run] = {}
        self.live: dict[str, tuple[Run, LiveAuthorization]] = {}
        self._authorities = self._load_authorities()
        self.state_file = state_file
        if state_file is not None and state_file.exists():
            self._restore(json.loads(state_file.read_text()))
        self.app = self._build()

    def _restore(self, state: dict[str, Any]) -> None:
        """Restore our own local snapshot; malformed state fails startup instead of being discarded."""
        if state["version"] != 1:
            raise ValueError("unknown fake-platform state version")
        self.mandates = {row["mandate_id"]: Mandate(**row) for row in state["mandates"]}
        for row in state["runs"]:
            run = Run(row["run_id"], row["scenario_id"], row["mandate"],
                      self.pack.attempts(row["scenario_id"]), datetime.fromisoformat(row["started_at"]))
            attempts = {a.purchase.authorization_id: a for a in run.attempts}
            for raw in row["queued"]:
                values = dict(raw)
                attempt = attempts[values.pop("source_id")]
                for key in ("queued_at", "deadline_at", "human_expires_at", "decided_at"):
                    values[key] = datetime.fromisoformat(values[key]) if values[key] else None
                live = LiveAuthorization(attempt=attempt, **values)
                run.queued.append(live)
                self.live[live.live_id] = run, live
            self.runs[run.run_id] = run
        self.received, self.resolutions, self.rejected = state["received"], state["resolutions"], state["rejected"]

    def _save(self) -> None:
        if self.state_file is None:
            return
        runs = []
        for run in self.runs.values():
            queued = []
            for live in run.queued:
                row = {key: getattr(live, key) for key in
                       ("live_id", "deliveries", "decision", "answer", "late")}
                row["source_id"] = live.attempt.purchase.authorization_id
                for key in ("queued_at", "deadline_at", "human_expires_at", "decided_at"):
                    value = getattr(live, key)
                    row[key] = _iso(value) if value else None
                queued.append(row)
            runs.append({"run_id": run.run_id, "scenario_id": run.scenario_id, "mandate": run.mandate,
                         "started_at": _iso(run.started_at), "queued": queued})
        state = {"version": 1, "mandates": [vars(m) for m in self.mandates.values()], "runs": runs,
                 "received": self.received, "resolutions": self.resolutions, "rejected": self.rejected}
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(state))
        temporary.replace(self.state_file)

    def _load_authorities(self) -> dict[str, dict[str, str]]:
        with (self.pack.data_dir / "scenario_authorities.csv").open(encoding="utf-8", newline="") as f:
            return {r["authority_id"]: r for r in csv.DictReader(f)}

    def _scenarios(self) -> list[dict[str, Any]]:
        """The pack's scenarios in the hosted API's shape: id, name, instruction and event count."""
        counts: dict[str, int] = {}
        for a in self.pack.attempts():
            counts[a.scenario_id] = counts.get(a.scenario_id, 0) + 1
        with (self.pack.data_dir / "scenario_catalogue.csv").open(encoding="utf-8", newline="") as f:
            return [{"scenario_id": r["scenario_id"], "scenario_name": r["scenario_name"],
                     "cardholder_instruction": r["cardholder_instruction"],
                     "event_count": counts.get(r["scenario_id"], 0)}
                    for r in csv.DictReader(f) if r["scenario_id"] in counts]

    # --- queue -------------------------------------------------------------------------------------

    def _advance(self, run: Run) -> None:
        """Queue the next purchase once the previous one has an automated answer or missed its deadline."""
        now = self.clock()
        if not self._mandate_active(run):
            return  # the platform rejects a revoked mandate before queueing anything new
        while len(run.queued) < len(run.attempts):
            if run.queued:
                last = run.queued[-1]
                if last.decision is None and now < last.deadline_at:
                    return
                ready_since = last.deadline_at if last.decided_at is None else last.decided_at
            else:
                ready_since = run.started_at
            queued_at = ready_since + self.queue_delay
            if now < queued_at:
                return
            attempt = run.attempts[len(run.queued)]
            live = LiveAuthorization(f"AZ-{uuid.uuid4().hex[:12]}", attempt, queued_at,
                                     queued_at + timedelta(seconds=self.decision_seconds))
            run.queued.append(live)
            self.live[live.live_id] = (run, live)

    def _mandate_active(self, run: Run) -> bool:
        mandate = self.mandates.get(run.mandate["mandate_id"])
        return mandate is not None and mandate.status == "active"

    def _live_id_of(self, run: Run, source_id: str | None) -> str | None:
        if source_id is None:
            return None
        return next((q.live_id for q in run.queued if q.purchase.authorization_id == source_id), source_id)

    def _deliverable(self) -> tuple[Run, LiveAuthorization] | None:
        now = self.clock()
        for run in self.runs.values():
            self._advance(run)
            for live in run.queued:
                if live.decision is not None or now >= live.deadline_at or now < live.queued_at + self.delivery_lag:
                    continue
                allowed = 2 if live.attempt.purchase.authorization_id in self.repeat else 1
                if live.deliveries < allowed:
                    return run, live
        return None

    # --- event -------------------------------------------------------------------------------------

    def _approved_spend(self, run: Run, current: LiveAuthorization) -> float | None:
        # The wire has one counter but no window identifier. Only report it when the confirmed
        # snapshot names exactly one period; null leaves Leash's own rolling ledger authoritative.
        days = {r.get("period_days") for r in run.mandate["hard_rules"]
                if r.get("field") == "authorization.billing_amount_chf"
                and r.get("scope") == "period" and type(r.get("period_days")) is int
                and r["period_days"] > 0}
        if len(days) != 1:
            return None
        now, window = self.clock(), timedelta(days=days.pop())
        total = sum((q.purchase.billing_amount_chf for q in run.queued
                     if q is not current and q.status(now) == "approved"
                     and current.purchase.sim_time.within(q.purchase.sim_time, window)), Decimal("0"))
        return _num(total)

    def _recent(self, run: Run, current: LiveAuthorization) -> list[dict[str, Any]]:
        now, window = self.clock(), timedelta(minutes=HISTORY_WINDOW_MINUTES)
        status = {"approved": "approved", "declined": "declined", "timed_out": "declined"}
        out = []
        for q in run.queued:
            if q is current or not current.purchase.sim_time.within(q.purchase.sim_time, window):
                continue
            out.append({"authorization_id": q.live_id, "timestamp": _iso(q.purchase.sim_time.at),
                        "merchant_id": q.purchase.merchant.merchant_id,
                        "billing_amount_chf": _num(q.purchase.billing_amount_chf),
                        "status": status.get(q.status(now), "pending")})
        return out

    def _event(self, run: Run, live: LiveAuthorization) -> dict[str, Any]:
        p, a = live.purchase, live.attempt
        m = p.merchant
        authority = self._authorities[a.authority_id]
        return {
            "type": "authorization.request",
            "request_id": f"req_{live.live_id}",
            "deadline_at": _iso(live.deadline_at),
            "authorization": {
                "authorization_id": live.live_id, "source_authorization_id": p.authorization_id,
                "scenario_id": a.scenario_id, "replay_order": a.replay_order,
                "mandate_id": run.mandate["mandate_id"], "profile_id": run.mandate["profile_id"],
                "card_id": p.card_id, "initiator_type": "agent",
                "merchant": {"merchant_id": m.merchant_id, "merchant_name": m.name, "merchant_category": m.category,
                             "merchant_mcc": m.mcc, "merchant_country": m.country, "merchant_city": m.city,
                             "availability": m.availability, "recurring_capable": str(m.recurring_capable).lower()},
                "timestamp": _iso(p.sim_time.at), "amount": _num(p.amount), "currency": p.currency,
                "billing_amount_chf": _num(p.billing_amount_chf), "items_subtotal": _num(p.items_subtotal),
                "delivery_fee": _num(p.delivery_fee), "channel": p.channel, "customer_device_id": p.device_id,
                "authority_status": authority["initial_status"], "card_status_at_attempt": "active",
                "spend_in_period_before_chf": None, "recent_attempt_count_10m": p.recent_attempts_10m,
                "fulfillment_method": p.fulfillment,
                "delivery_by": p.delivery_by.isoformat() if p.delivery_by else None,
                "order_returnable": p.order_returnable.value, "order_cancellable": p.order_cancellable.value,
                "related_authorization_id": self._live_id_of(run, p.related_authorization_id),
                "related_authorization_status": p.related_status,
                "purchase_description": p.description,
                "items": [{"line_no": i.line_no, "item_id": i.item_id, "item_name": i.name,
                           "item_category": i.category, "quantity": i.quantity, "unit_price": _num(i.unit_price),
                           "currency": i.currency, "item_details": i.details} for i in p.items],
            },
            "mandate": {**run.mandate, "customer_id": authority["customer_id"], "card_id": authority["card_id"]},
            "context": {"approved_spend_in_period_chf": self._approved_spend(run, live),
                        "recent_authorizations": self._recent(run, live)},
            "runtime": {"received_at": _iso(self.clock()), "history_window_minutes": HISTORY_WINDOW_MINUTES,
                        "context_basis": "run_decisions_and_scenario_timestamps"},
        }

    # --- app ---------------------------------------------------------------------------------------

    def _build(self) -> FastAPI:  # noqa: C901 - one route table, kept together for readability
        app = FastAPI(title="Fake Viseca API")

        @app.middleware("http")
        async def auth(request: Request, call_next: Any) -> Response:
            if request.url.path.startswith("/v1/") and \
                    request.headers.get("authorization") != f"Bearer {self.api_key}":
                return _error(401, "unauthorized", "missing or wrong bearer key")
            response: Response = await call_next(request)
            # ponytail: one local simulator process; atomic JSON snapshots suffice for the 45-event pack.
            # Use a transactional store if multiple simulator workers are ever needed.
            self._save()
            return response

        @app.get("/healthz")
        async def healthz() -> dict[str, Any]:
            return {"status": "ok"}

        @app.get("/v1/bootstrap")
        async def bootstrap() -> dict[str, Any]:
            return {"data": {"api_version": self.api_version, "data_version": self.data_version,
                             "timeouts": {"decision_timeout_seconds": self.decision_seconds,
                                          "human_window_seconds": self.human_window_seconds},
                             # objects, as the hosted API sends them: a bare list of IDs let a client
                             # look fine locally and then find no instruction to compile on event day
                             "scenarios": self._scenarios(),
                             "limits": {}, "features": {"team_reset": True}}}

        @app.post("/v1/mandates")
        async def create_mandate(request: Request) -> JSONResponse:
            body = await request.json()
            if not body.get("instruction") or body.get("uncertainty_policy") not in ("ask", "decline", "approve"):
                return _error(422, "invalid_mandate", "instruction and uncertainty_policy are required")
            draft_id = f"TD-{uuid.uuid4().hex[:10]}"
            self.mandates[draft_id] = Mandate(draft_id, "draft", {
                "instruction": body["instruction"], "hard_rules": list(body.get("hard_rules") or []),
                "uncertainty_policy": body["uncertainty_policy"], "guidance": list(body.get("guidance") or []),
                "open_questions": list(body.get("open_questions") or [])})
            return JSONResponse({"draft_id": draft_id, **self.mandates[draft_id].body}, status_code=201)

        @app.post("/v1/mandates/{draft_id}/confirm")
        async def confirm(draft_id: str, request: Request) -> JSONResponse:
            draft = self.mandates.get(draft_id)
            if draft is None or draft.status != "draft":
                return _error(404, "not_found", "no such draft")
            if (await request.json()).get("confirmed") is not True:
                return _error(422, "not_confirmed", "confirmed must be true")
            mandate_id = f"TM-{uuid.uuid4().hex[:10]}"
            draft.status = "confirmed"
            self.mandates[mandate_id] = Mandate(mandate_id, "active", dict(draft.body))
            return JSONResponse({"mandate_id": mandate_id, "status": "active", **draft.body}, status_code=201)

        def mandate_view(m: Mandate) -> dict[str, Any]:
            return {"data": {"mandate_id": m.mandate_id, "status": m.status, **m.body}}

        @app.get("/v1/mandates/{mandate_id}")
        async def get_mandate(mandate_id: str) -> Any:
            m = self.mandates.get(mandate_id)
            return mandate_view(m) if m and m.status != "draft" else _error(404, "not_found", "no such mandate")

        @app.patch("/v1/mandates/{mandate_id}")
        async def patch_mandate(mandate_id: str, request: Request) -> Any:
            m = self.mandates.get(mandate_id)
            if m is None or m.status != "active":
                return _error(409 if m else 404, "not_active", "only an active mandate can change")
            change = await request.json()
            rules = change.get("hard_rules")
            if rules is not None and rules[:len(m.body["hard_rules"])] != m.body["hard_rules"]:
                return _error(422, "rules_removed", "existing hard rules must stay unchanged")
            policy = change.get("uncertainty_policy")
            if policy is not None and policy != m.body["uncertainty_policy"] and policy != "decline":
                return _error(422, "policy_loosened", "the uncertainty policy can only change to decline")
            for key in ("hard_rules", "uncertainty_policy", "guidance", "open_questions"):
                if key in change:
                    m.body[key] = change[key]
            return mandate_view(m)

        @app.delete("/v1/mandates/{mandate_id}")
        async def revoke(mandate_id: str) -> Any:
            m = self.mandates.get(mandate_id)
            if m is None or m.status == "draft":
                return _error(404, "not_found", "no such mandate")
            m.status = "revoked"
            return mandate_view(m)

        @app.post("/v1/scenario-runs")
        async def start_run(request: Request) -> JSONResponse:
            body = await request.json()
            m = self.mandates.get(body.get("mandate_id", ""))
            if m is None or m.status != "active":
                return _error(409, "mandate_not_active", "a run needs an active, confirmed mandate")
            attempts = self.pack.attempts(body.get("scenario_id", ""))
            if not attempts:
                return _error(404, "unknown_scenario", "no such scenario")
            run_id = f"RUN-{uuid.uuid4().hex[:10]}"
            snapshot = {"mandate_id": m.mandate_id, "status": "active", "instruction": m.body["instruction"],
                        "hard_rules": list(m.body["hard_rules"]), "uncertainty_policy": m.body["uncertainty_policy"],
                        "profile_id": f"PROFILE-{run_id}"}
            self.runs[run_id] = Run(run_id, body["scenario_id"], snapshot, attempts, self.clock())
            return JSONResponse({"run_id": run_id, "scenario_id": body["scenario_id"], "mandate": snapshot,
                                 "counters": self._counters(self.runs[run_id])}, status_code=201)

        @app.get("/v1/scenario-runs/{run_id}")
        async def get_run(run_id: str) -> Any:
            run = self.runs.get(run_id)
            if run is None:
                return _error(404, "not_found", "no such run")
            self._advance(run)
            counters = self._counters(run)
            status = "completed" if counters["final"] == counters["total"] else \
                "running" if self._mandate_active(run) else "stopped"
            return {"data": {"run_id": run_id, "scenario_id": run.scenario_id, "counters": counters,
                             "status": status}}

        @app.get("/v1/decision-requests/next")
        async def next_request(wait: int = 25) -> Response:
            until = time.monotonic() + max(0, min(wait, 25))
            while True:
                found = self._deliverable()
                if found is not None:
                    run, live = found
                    live.deliveries += 1
                    if self.poll_delay:
                        await asyncio.sleep(self.poll_delay)
                    return JSONResponse({"run_id": run.run_id, "event_id": f"EV-{uuid.uuid4().hex[:10]}",
                                         "type": "authorization.request", "authorization_id": live.live_id,
                                         "status": "pending", "occurred_at": _iso(live.queued_at),
                                         "data": self._event(run, live)})
                if time.monotonic() >= until:
                    return Response(status_code=204)
                await asyncio.sleep(POLL_STEP_SECONDS)

        @app.post("/v1/authorizations/{authorization_id}/decision")
        async def decision(authorization_id: str, request: Request) -> Any:
            body = await request.json()
            found = self.live.get(authorization_id)
            if found is None:
                return self._reject(authorization_id, body, 404, "not_found", "unknown live authorization ID")
            if body.get("authorization_id") != authorization_id or \
                    body.get("decision") not in ("approve", "decline", "step_up"):
                return self._reject(authorization_id, body, 422, "invalid_decision", "authorization_id must match; decision approve|decline|step_up")
            if bad_evidence(body):
                return self._reject(authorization_id, body, 422, "validation_error",
                                    "evidence must be a list of objects")
            run, live = found
            if self.decision_delay:
                await asyncio.sleep(self.decision_delay)
            source = live.attempt.purchase.authorization_id
            if self.fail_decisions.get(source, 0) > 0:
                self.fail_decisions[source] -= 1
                return self._reject(authorization_id, body, 503, "unavailable", "injected fault")
            now = self.clock()
            if live.decision is not None:
                if live.decision == body["decision"]:
                    return {"data": self._view(live)}  # a retry of the same answer
                return self._reject(authorization_id, body, 409, "already_decided", "an automated decision was already recorded; use /resolve")
            if now >= live.deadline_at:
                live.late = True
                return self._reject(authorization_id, body, 409, "deadline_passed", "the automated deadline has passed")
            live.decision = body["decision"]
            live.decided_at = now
            if live.decision == "step_up":
                live.human_expires_at = now + timedelta(seconds=self.human_window_seconds)
            self.received.append(dict(body))
            return {"data": self._view(live)}

        @app.post("/v1/authorizations/{authorization_id}/resolve")
        async def resolve(authorization_id: str, request: Request) -> Any:
            body = await request.json()
            if bad_evidence(body):
                return self._reject(authorization_id, body, 422, "validation_error",
                                    "evidence must be a list of objects")
            found = self.live.get(authorization_id)
            if found is None:
                return self._reject(authorization_id, body, 404, "not_found", "unknown live authorization ID")
            if body.get("decision") not in ("approve", "decline"):
                return self._reject(authorization_id, body, 422, "invalid_answer", "decision must be approve or decline")
            _, live = found
            if live.decision != "step_up":
                return self._reject(authorization_id, body, 409, "not_waiting_for_customer", "only a step_up waits for the customer")
            if live.answer is not None:
                if live.answer == body["decision"]:
                    return {"data": self._view(live)}
                return self._reject(authorization_id, body, 409, "conflicting_answer", "the customer already answered differently")
            if live.status(self.clock()) == "timed_out":
                return self._reject(authorization_id, body, 409, "ask_expired", "the customer's window has closed")
            live.answer = body["decision"]
            self.resolutions.append({"authorization_id": authorization_id, **body})
            return {"data": self._view(live)}

        @app.get("/v1/authorizations")
        async def authorizations() -> dict[str, Any]:
            return {"data": [self._view(live, run) for run, live in self.live.values()]}

        @app.post("/v1/team/reset")
        async def reset() -> dict[str, Any]:
            self.mandates.clear(), self.runs.clear(), self.live.clear()
            self.received.clear(), self.resolutions.clear(), self.rejected.clear()
            return {"data": {"reset": True}}

        return app

    def _reject(self, authorization_id: str, body: Any, status: int, code: str, message: str) -> JSONResponse:
        self.rejected.append({"authorization_id": authorization_id, "body": body, "status": status, "error": code})
        return _error(status, code, message)

    def _view(self, live: LiveAuthorization, run: "Run | None" = None) -> dict[str, Any]:
        """One authorization as the hosted API lists it: `run_id` present, `decision` an object.

        Both were missing here, and both matter: a client filtering this list by `run_id` silently
        matched nothing against the fake, and read `decision.decision` off a bare string.
        """
        return {"authorization_id": live.live_id, "source_authorization_id": live.purchase.authorization_id,
                "run_id": run.run_id if run is not None else self._run_of(live),
                "decision": self._decision_view(live), "customer_answer": live.answer,
                "status": live.status(self.clock()), "deadline_at": _iso(live.deadline_at)}

    def _run_of(self, live: LiveAuthorization) -> str | None:
        found = self.live.get(live.live_id)
        return found[0].run_id if found else None

    def _decision_view(self, live: LiveAuthorization) -> dict[str, Any] | None:
        """The last body accepted for this purchase, as the platform echoes it back."""
        if live.decision is None:
            return None
        bodies = [b for b in self.received if b.get("authorization_id") == live.live_id]
        answers = [r for r in self.resolutions if r.get("authorization_id") == live.live_id]
        body = dict(answers[-1] if answers else bodies[-1] if bodies else {"decision": live.decision})
        return {**body, "decision_source": "human" if answers else "team"}

    def _counters(self, run: Run) -> dict[str, int]:
        now = self.clock()
        statuses = [q.status(now) for q in run.queued]
        final = sum(s in ("approved", "declined", "timed_out") for s in statuses)
        return {"total": len(run.attempts), "delivered": sum(q.deliveries > 0 for q in run.queued),
                "decided": sum(q.decision is not None for q in run.queued),
                "waiting_for_customer": statuses.count("waiting_for_customer"), "final": final,
                "remaining": len(run.attempts) - final}
