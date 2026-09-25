"""LEASH-175: the HTTP surface of the permission assistant.

The chat talks to this; this talks to the policy service. It holds no authority of its own: it reads
the customer's turns, builds their background itself, asks the model, and hands whatever survived
validation to the policy service, which validates every rule again against the registry and appends it
(DEC-045). Nothing here confirms a draft, activates a mandate or decides a payment, and it has no path
to the decision engine or its database — `test_service.py` asserts that structurally.

Two things are deliberately not taken from the client:

- **the background.** The bundle is built here, from a card this process was configured with, so a
  caller can neither inject a preference nor ask for another customer's history (DEC-034). The
  prototype has no login (DEC-019), so there is exactly one customer; authenticated consent and a
  per-request identity belong to LEASH-140/143.
  ponytail: one card per process. Take the card from an authenticated session when there is one.
- **the instruction.** It is derived from the customer's own turns, never sent as a field, so an agent
  turn in the transcript cannot become the thing we compile.
"""

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from fastapi import Body, FastAPI
from fastapi.responses import JSONResponse

from assistant.agent import PermissionAssistant, Turn
from assistant.conversation import ModelUnavailable, PermissionConversation, PolicyService
from leash.application.permission_context import UnknownScope, resolve_scope
from leash.domain.clock import SimTime
from leash.domain.mandate import CompiledMandate
from leash.policy.hard_rules import mandate_from_api

log = logging.getLogger("leash.assistant")

SPEAKERS = frozenset({"customer", "assistant"})


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def _text(body: Any, *, simulation: bool = False) -> str | None:
    """The customer's own words, or None. `context` and `card_id` are deliberately not accepted."""
    if not isinstance(body, Mapping) or set(body) - ({"replace_instruction", "scenario_id"} if simulation else {"replace_instruction"}) != {"text"}:
        return None
    if "replace_instruction" in body and not isinstance(body["replace_instruction"], bool):
        return None
    text = body.get("text")
    return text.strip() if isinstance(text, str) and text.strip() else None


def _asked(question: Any) -> str:
    """The text of a question the customer was shown, whichever shape the draft stored it in.

    An assistant question carries its provenance as an object since LEASH-145 AC10; drafts written
    before that stored a bare string, and one of those is still read back here. Joining the objects as
    strings raised TypeError on the chat's own path — the second turn of every conversation that had an
    open question.
    """
    if isinstance(question, Mapping):
        text = question.get("text")
        return text if isinstance(text, str) else ""
    return question if isinstance(question, str) else ""


def _said(earlier: str, text: str) -> list[Turn]:
    """The conversation the model reads: what the service has recorded, then the newest words.

    The earlier words come from the stored draft rather than from the client, so the transcript stays
    derived and a caller cannot put words in the customer's mouth by replaying a transcript of its own.
    """
    said = [Turn("T1", "customer", earlier)] if earlier.strip() else []
    return [*said, Turn(f"T{len(said) + 1}", "customer", text)]


class PolicyServiceError(RuntimeError):
    """The policy service refused or could not be reached. Never swallowed: a draft we could not
    create must not look like a draft with no restrictions in it."""


class HttpPolicyService:
    """The policy service as this surface uses it: ask for a draft, and read the confirmed permission.

    Deliberately narrow — there is no method for confirming, submitting, activating or revoking
    anything, so this process cannot do those things by mistake. Reading the active permission is a
    read: a candidate rule has to be checked against it before a customer ever sees it (DEC-006).
    """

    def __init__(self, client: Any, *, timeout_seconds: float = 10.0) -> None:
        self._client, self._timeout = client, timeout_seconds

    def create_draft(self, instruction: str, context: Mapping[str, Any],
                     rules: Sequence[Mapping[str, Any]] = ()) -> Mapping[str, Any]:
        return self._post("/api/policies/drafts",
                          {"instruction": instruction, "context": dict(context),
                           "rules": [dict(r) for r in rules]})

    def add_turn(self, draft_id: str, text: str,
                 rules: Sequence[Mapping[str, Any]] = (), *, assessment: Mapping[str, Any] | None = None,
                 replace_instruction: bool = False, context: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        from urllib.parse import quote

        return self._post(f"/api/policies/drafts/{quote(draft_id, safe='')}/turns",
                          {"text": text, "rules": [dict(r) for r in rules],
                           "assessment": assessment, "replace_instruction": replace_instruction,
                           "context": dict(context) if context is not None else None})

    def draft(self, draft_id: str) -> Mapping[str, Any]:
        from urllib.parse import quote

        try:
            response = self._client.get(f"/api/policies/drafts/{quote(draft_id, safe='')}",
                                        timeout=self._timeout)
        except Exception as exc:  # noqa: BLE001
            raise PolicyServiceError(f"could not reach the policy service: {exc}") from exc
        if response.status_code >= 400:
            raise PolicyServiceError(f"no draft {draft_id} ({response.status_code})")
        return response.json()

    def active_mandate(self) -> Mapping[str, Any] | None:
        """The current active mandate as the policy service lists it, or None if there is none."""
        try:
            response = self._client.get("/api/mandates", timeout=self._timeout)
        except Exception as exc:  # noqa: BLE001
            raise PolicyServiceError(f"could not reach the policy service: {exc}") from exc
        if response.status_code >= 400:
            raise PolicyServiceError(f"could not read the confirmed permission ({response.status_code})")
        body = response.json()
        current = body.get("current_mandate_id")
        mandates = [x for x in body.get("mandates", []) if isinstance(x, Mapping)]
        active = [x for x in mandates if x.get("status") == "active"]
        return next((x for x in active if x.get("mandate_id") == current), None) or (active[0] if active else None)

    def record_message(self, draft_id: str, text: str, reply: str,
                       context: Mapping[str, Any]) -> Mapping[str, Any]:
        from urllib.parse import quote

        return self._post(f"/api/policies/drafts/{quote(draft_id, safe='')}/messages",
                          {"text": text, "reply": reply, "context": dict(context)})

    def _post(self, path: str, body: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            response = self._client.post(path, json=body, timeout=self._timeout)
        except Exception as exc:  # noqa: BLE001 — unreachable is an error the customer must see
            raise PolicyServiceError(f"could not reach the policy service: {exc}") from exc
        if response.status_code >= 400:
            raise PolicyServiceError(f"the policy service refused the draft ({response.status_code})")
        return response.json()


def _active(policy: PolicyService) -> CompiledMandate | None:
    """The confirmed permission a candidate rule must not loosen, compiled from its own hard_rules.

    A `PolicyServiceError` is left to the caller: not knowing what is already confirmed is not the same
    as nothing being confirmed, and drafting without the check is the loosening it exists to prevent.
    """
    stored = policy.active_mandate()
    if not stored:
        return None
    compiled, _ = mandate_from_api({"instruction": str(stored.get("instruction") or "x"),
                                    "hard_rules": stored.get("hard_rules") or [],
                                    "uncertainty_policy": stored.get("uncertainty_policy") or "ask"})
    return compiled


def create_app(assistant: PermissionAssistant, pack: Any, policy: PolicyService, *,
               catalogue: Any = None, cutoff: SimTime, card_id: str, simulation: bool = False) -> FastAPI:
    app = FastAPI(title="Leash permission assistant")

    @app.post("/api/permission/drafts/{draft_id}/turns")
    def add_turn(draft_id: str, body: dict[str, Any] = Body(...)) -> Any:
        """One more thing the customer said, on the draft the conversation already has.

        The earlier words are read back from the draft, not sent by the caller: the transcript stays
        derived, exactly as the app's own screen treats it. The model sees the whole conversation —
        a later sentence can change how an earlier one should be read — while only the newest words
        are added to the draft, so the revisions the customer reviewed stay as they were.
        """
        text = _text(body)
        if text is None:
            return _error(422, "invalid_request", 'Send {"text": "…"} with the customer\'s own words.')
        try:
            stored = policy.draft(draft_id)
        except PolicyServiceError as exc:
            log.warning("no draft to add to", exc_info=exc)
            return _error(404, "draft_not_found", "No draft with this ID.")
        replacing = body.get("replace_instruction", False)
        earlier = "" if replacing else str(stored.get("instruction", ""))
        turns = _said(earlier, text)
        if not replacing:
            questions = [q["text"] for q in stored.get("open_questions", []) if isinstance(q.get("text"), str)]
            questions += [_asked(q) for q in stored.get("assistant", {}).get("questions", [])]
            questions = [q for q in questions if q.strip()]
            turns[-1:-1] = [Turn("Q", "assistant", "\n".join(questions))] if questions else []
        return _reply(turns, draft_id=draft_id, replace_instruction=replacing,
                      scenario_id=stored.get("simulation_scenario"))

    @app.post("/api/permission/drafts")
    def create_draft(body: dict[str, Any] = Body(...)) -> Any:
        text = _text(body, simulation=simulation)
        if text is None:
            return _error(422, "invalid_request",
                          'Send {"text": "…"}; the background and whose it is are decided here.')
        return _reply(_said("", text), draft_id=None, scenario_id=body.get("scenario_id"))

    def _reply(said: list[Turn], *, draft_id: str | None, replace_instruction: bool = False,
               scenario_id: str | None = None) -> Any:
        scoped_card = card_id
        if scenario_id is not None:
            if not simulation or not isinstance(scenario_id, str):
                return _error(422, "invalid_scenario", "Scenario selection is only available in local simulation.")
            attempts = pack.attempts(scenario_id)
            cards = {a.purchase.card_id for a in attempts}
            if len(cards) != 1:
                return _error(422, "invalid_scenario", "Choose a supplied scenario with one customer card.")
            scoped_card = cards.pop()
        try:
            scope = resolve_scope(pack, scoped_card)
        except UnknownScope as exc:
            log.error("this assistant is configured for a card that is not in the pack", exc_info=exc)
            return _error(404, "unknown_card", str(exc))
        conversation = PermissionConversation(assistant, pack, scope, policy, catalogue=catalogue)
        try:
            # DEC-006, before anything is shown: a candidate that would loosen the confirmed permission
            # is a question, not a rule. Without this the customer reads a looser limit as their new
            # permission and only the engine's /tighten refuses it — after they believed it.
            active = _active(policy)
            result = conversation.clarify(said, cutoff=cutoff, draft_id=draft_id, active=active,
                                          replace_instruction=replace_instruction, simulation_scenario=scenario_id)
        except ModelUnavailable as exc:
            return _error(503, exc.code or "model_unavailable", str(exc))
        except ValueError as exc:  # no customer words yet: a question, not a failure
            return _error(422, "invalid_request", str(exc))
        except PolicyServiceError as exc:
            # Never a draft of our own invention: without the policy service there is no validated
            # draft, and an empty one would read to the customer as "nothing is restricted".
            log.error("the policy service could not produce a draft", exc_info=exc)
            return _error(503, "policy_service_unavailable",
                          "I couldn't check your permission just now. Nothing was saved; please try again.")
        return {
            "draft": result.draft or None,
            "kind": result.proposal.intent,
            "reply": result.reply,
            "consent_text": list(result.consent_text),
            "questions": [{"text": q.text, "field": q.field,
                           "source": q.source.as_dict() if q.source else None}
                          for q in result.questions],
            "status": result.status,
            "model": result.proposal.model,
            "prompt_version": result.proposal.prompt_version,
        }

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


class OfflineModel:
    """Reads the customer's words with the deterministic compiler instead of a model.

    A **test double**, for rehearsals and CI where no model key exists. It is not a fallback: a model
    that is down must become questions for the customer (DEC-045), never a quieter second-best reading
    nobody chose. So it is selected only by an explicit `LEASH_ASSISTANT_MODEL=offline`, and it says so
    in the log every time it starts.

    Each turn is read on its own, so every rule can name the turn it came from and quote it — the
    provenance `agent.py` requires of any model.
    """

    name = "offline-compiler"
    prompt_version = "offline-1"

    def propose(self, request: Any) -> Mapping[str, Any]:
        from leash.policy.compiler import compile_instruction

        rules = []
        for turn in request.turns:
            if turn.speaker != "customer" or not turn.text.strip():
                continue
            draft = compile_instruction(turn.text, catalogue=tuple(getattr(request, "catalogue", ()) or ()))
            for rule in draft.mandate.rules:
                value = list(rule.value) if isinstance(rule.value, tuple) else str(rule.value)
                rules.append({"field": rule.field, "operator": rule.operator, "value": value,
                              "says": turn.text, "turn_id": turn.turn_id})
        return {"rules": rules, "questions": []}


# ----- running it -------------------------------------------------------------------------------

DEFAULT_POLICY_URL = "http://localhost:8000"
DEFAULT_PACK = "data"


def build_from_env(environ: Mapping[str, str] | None = None) -> FastAPI:
    """Assemble the surface from the environment. Fails loudly rather than starting half-wired.

    `OPENROUTER_API_KEY` is read by the model adapter alone, and nothing here reads `TEAM_API_KEY`: this
    process must not hold a control-layer credential (DEC-044).
    """
    import os
    from pathlib import Path

    import httpx

    from leash.adapters.pack.loader import Pack

    env = os.environ if environ is None else environ
    cutoff = env.get("LEASH_SIM_CUTOFF")
    if not cutoff:
        raise ValueError("set LEASH_SIM_CUTOFF to the simulated time the background is summarised at")
    card_id = env.get("LEASH_CARD_ID")
    if not card_id:
        raise ValueError("set LEASH_CARD_ID to the card this assistant speaks for")
    pack = Pack(Path(env.get("LEASH_PACK_DIR", DEFAULT_PACK)))
    policy = HttpPolicyService(httpx.Client(base_url=env.get("LEASH_POLICY_URL", DEFAULT_POLICY_URL)))
    from leash.adapters.pack.catalogue import Catalogue
    catalogue = Catalogue(pack.data_dir)
    choice = env.get("LEASH_ASSISTANT_MODEL", "openrouter").strip().lower()
    if choice == "offline":
        log.warning("LEASH_ASSISTANT_MODEL=offline: reading with the compiler, not a model. "
                    "For rehearsals and tests only — it reads no language the compiler cannot.")
        model: Any = OfflineModel()
    elif choice == "openrouter":
        from assistant.openrouter import OpenRouterModel
        from leash.adapters.jev import JevClient

        model = OpenRouterModel(environ=env, verifier=JevClient(env))
    else:
        raise ValueError("LEASH_ASSISTANT_MODEL must be openrouter or offline")
    return create_app(PermissionAssistant(model), pack, policy, catalogue=catalogue,
                      cutoff=SimTime.parse(cutoff), card_id=card_id,
                      simulation=env.get("LEASH_SIMULATION") == "1")


def main() -> None:  # pragma: no cover - process entry point
    import os

    import uvicorn

    uvicorn.run(build_from_env(), host=os.environ.get("HOST", "127.0.0.1"),
                port=int(os.environ.get("PORT", "8100")))


if __name__ == "__main__":  # pragma: no cover
    main()
