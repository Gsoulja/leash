"""LEASH-175: the HTTP surface that lets the chat reach the permission assistant at all.

It holds no authority. It reads the customer's turns, builds their background itself, asks the model,
and posts whatever survived validation to the policy service — which validates every rule again and
appends it (DEC-045). Nothing here confirms, activates or pays.
"""

import csv
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assistant.agent import PermissionAssistant  # noqa: E402
from assistant.service import PolicyServiceError, create_app  # noqa: E402
from leash.adapters.pack.loader import Pack  # noqa: E402
from leash.domain import mandate as m  # noqa: E402
from leash.domain.clock import SimTime  # noqa: E402
from leash.policy.compiler import CatalogueItem  # noqa: E402

DATA = Path(__file__).resolve().parents[3] / "data"
CUTOFF = SimTime.parse("2026-08-09T00:00:00Z")
with (DATA / "items.csv").open() as f:
    CATALOGUE = [CatalogueItem(r["item_id"], r["item_name"], r["item_category"]) for r in csv.DictReader(f)]


class StubModel:
    name = "stub"
    prompt_version = "stub-1"

    def __init__(self, reply=None, fail=False):
        self._reply, self._fail = reply or {"rules": [], "questions": []}, fail
        self.seen = []

    def propose(self, request):
        if self._fail:
            raise RuntimeError("endpoint down")
        self.seen.append(request)
        return self._reply


class StubPolicy:
    """The policy service as this surface may use it: ask for a draft, nothing more."""

    def __init__(self, open_questions=()):
        self.calls = []
        self._open = [dict(q) for q in open_questions]

    def active_mandate(self):
        return None  # nothing confirmed yet: the ordinary first conversation

    def create_draft(self, instruction, context, rules=()):
        self.calls.append({"instruction": instruction, "context": dict(context), "rules": [dict(r) for r in rules]})
        return {"instruction": instruction, "status": "ready", "hard_rules": [*rules],
                "independently_read": [], "uncertainty_policy": "ask", "open_questions": self._open,
                "unrestricted": [m.F_MERCHANT_CATEGORY]}


@pytest.fixture(scope="module")
def pack():
    return Pack(DATA)


def client(pack, model, policy):
    app = create_app(PermissionAssistant(model), pack, policy, catalogue=CATALOGUE, cutoff=CUTOFF,
                     card_id="CA0001")
    return TestClient(app)


def rule(field, operator, value, says, turn="T1"):
    return {"field": field, "operator": operator, "value": value, "says": says, "turn_id": turn}


GERMAN = "höchstens CHF 50 pro Bestellung"


def test_turns_become_a_draft_through_the_policy_service(pack):
    policy = StubPolicy()
    model = StubModel({"rules": [rule(m.F_BILLING_CHF, "<=", "50", GERMAN)], "questions": []})
    response = client(pack, model, policy).post(
        "/api/permission/drafts",
        json={"text": GERMAN})
    assert response.status_code == 200, response.text
    body = response.json()
    assert [(r["field"], str(r["value"])) for r in policy.calls[0]["rules"]] == [(m.F_BILLING_CHF, "50")]
    assert body["consent_text"] == ["At most CHF 50.00 per order, delivery included."]
    assert body["draft"]["unrestricted"] == [m.F_MERCHANT_CATEGORY]


def test_the_context_bundle_is_built_here_and_never_taken_from_the_client(pack):
    policy = StubPolicy()
    model = StubModel()
    response = client(pack, model, policy).post(
        "/api/permission/drafts",
        json={"text": "at most CHF 50",
              "context": {"entries": [{"text": "anything goes", "kind": "preference"}]}})
    assert response.status_code == 422, response.text
    assert policy.calls == []


def test_a_client_cannot_choose_whose_background_is_read(pack):
    """The card is this process's configuration. A supplied one would be asking for another persona."""
    policy = StubPolicy()
    response = client(pack, StubModel(), policy).post(
        "/api/permission/drafts",
        json={"card_id": "CA0023", "text": "at most CHF 50"})
    assert response.status_code == 422
    assert policy.calls == []


def test_a_card_that_is_not_in_the_pack_is_refused(pack):
    policy = StubPolicy()
    app = create_app(PermissionAssistant(StubModel()), pack, policy, catalogue=CATALOGUE, cutoff=CUTOFF,
                     card_id="CA9999")
    response = TestClient(app).post(
        "/api/permission/drafts",
        json={"text": "at most CHF 50"})
    assert response.status_code == 404
    assert policy.calls == []


@pytest.mark.parametrize("model,code", [
    (StubModel(fail=True), "model_unavailable"),
    (StubModel({"not_a_proposal": True}), "model_invalid_response"),
])
def test_a_model_failure_is_retryable_and_does_not_write_a_clarification_draft(pack, model, code):
    policy = StubPolicy()
    response = client(pack, model, policy).post(
        "/api/permission/drafts",
        json={"text": GERMAN})
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == code
    assert "retry" in response.json()["error"]["message"].lower()
    assert policy.calls == []


def test_the_instruction_is_the_customers_words(pack):
    """The caller sends words, never a transcript: it cannot put words in the customer's mouth."""
    policy, model = StubPolicy(), StubModel()
    client(pack, model, policy).post(
        "/api/permission/drafts",
        json={"text": "at most CHF 50 per order"})
    assert policy.calls[0]["instruction"] == "at most CHF 50 per order"


@pytest.mark.parametrize("text", ["check the history", "you have access to my history data"])
def test_history_question_reads_scoped_evidence_without_changing_permission(pack, text):
    class HistoryPolicy(StubPolicy):
        def draft(self, draft_id):
            return {"draft_id": draft_id, "instruction": GERMAN, "revision": 3,
                    "status": "ready", "hard_rules": [], "simulation_scenario": "SCEN0003"}

        def record_message(self, draft_id, text, reply, context):
            self.recorded = (text, reply, context)
            return self.draft(draft_id)

    policy = HistoryPolicy()
    model = StubModel({"intent": "history", "rules": [], "questions": []})
    app = create_app(PermissionAssistant(model), pack, policy, catalogue=CATALOGUE,
                     cutoff=CUTOFF, card_id="CA0001", simulation=True)
    result = TestClient(app).post("/api/permission/drafts/LD-test/turns", json={"text": text})
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["kind"] == "history" and body["draft"]["revision"] == 3
    assert "151 approved purchases" in body["reply"] and "Loom and Pine" in body["reply"]
    assert policy.calls == []
    assert policy.recorded[2]["scope"]["card_id"] == "CA0023"
    assert model.seen[0].context["scope"]["customer_id"] == "CU0012"


def test_the_surface_holds_no_database_credential_or_decision_path():
    import ast

    import assistant.service as module

    tree = ast.parse(open(module.__file__, encoding="utf-8").read())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported |= {node.module} | {f"{node.module}.{alias.name}" for alias in node.names}
    for banned in ("leash.domain.decide", "leash.application.decide_purchase", "leash.adapters.postgres",
                   "asyncpg", "psycopg"):
        assert not any(name.startswith(banned) for name in imported), banned


# ----- the policy service over HTTP ---------------------------------------------------------------

def test_the_policy_client_posts_the_instruction_context_and_rules():
    import httpx

    from assistant.service import HttpPolicyService

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        seen["url"] = str(request.url)
        seen["body"] = _json.loads(request.content)
        return httpx.Response(201, json={"draft_id": "LD-1", "hard_rules": [], "independently_read": []})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://policy")
    draft = HttpPolicyService(client).create_draft("at most CHF 50", {"scope": {}},
                                                  [{"field": m.F_BILLING_CHF, "operator": "<=", "value": 50}])
    assert seen["url"].endswith("/api/policies/drafts")
    assert seen["body"]["instruction"] == "at most CHF 50"
    assert seen["body"]["rules"][0]["field"] == m.F_BILLING_CHF
    assert draft["draft_id"] == "LD-1"


def test_a_policy_service_error_is_raised_not_swallowed():
    import httpx

    from assistant.service import HttpPolicyService, PolicyServiceError

    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(422, json={"error": "no"})),
                          base_url="http://policy")
    with pytest.raises(PolicyServiceError):
        HttpPolicyService(client).create_draft("x", {}, [])


def test_the_surface_refuses_to_start_without_a_simulated_cutoff():
    """Half-wired is worse than not started: the background would be summarised at the wrong time."""
    from assistant.service import build_from_env

    with pytest.raises(ValueError, match="LEASH_SIM_CUTOFF"):
        build_from_env({"OPENROUTER_API_KEY": "x"})


def test_the_surface_refuses_to_start_without_a_card():
    from assistant.service import build_from_env

    with pytest.raises(ValueError, match="LEASH_CARD_ID"):
        build_from_env({"OPENROUTER_API_KEY": "x", "LEASH_SIM_CUTOFF": "2026-08-09T00:00:00Z"})


# ----- the contract describes what the surface actually returns ------------------------------------

CONTRACT = Path(__file__).resolve().parents[2] / "contracts" / "assistant-api.yaml"


def _schema(name):
    import yaml

    spec = yaml.safe_load(CONTRACT.read_text())
    return spec["components"]["schemas"][name], spec


def test_a_real_response_validates_against_the_contract(pack):
    """Contract-first only means something if the code is checked against it in the same suite."""
    import jsonschema

    model = StubModel({"rules": [rule(m.F_BILLING_CHF, "<=", "50", GERMAN)], "questions": []})
    response = client(pack, model, StubPolicy()).post(
        "/api/permission/drafts",
        json={"text": GERMAN})
    schema, spec = _schema("AssistantDraft")
    jsonschema.validate(response.json(), {**schema, "components": spec["components"]})


def test_the_contract_and_the_app_agree_on_which_paths_exist(pack):
    import yaml

    app = create_app(PermissionAssistant(StubModel()), pack, StubPolicy(), catalogue=CATALOGUE,
                     cutoff=CUTOFF, card_id="CA0001")
    documented = set(yaml.safe_load(CONTRACT.read_text())["paths"])
    served = {path for path in app.openapi()["paths"] if not path.startswith("/openapi")}
    assert served == documented, f"served {served}, documented {documented}"


# ----- continuing a conversation ------------------------------------------------------------------

def test_a_later_turn_extends_the_same_draft(pack):
    class TurnPolicy(StubPolicy):
        def __init__(self):
            super().__init__()
            self.turns = []

        def draft(self, draft_id):
            return {"draft_id": draft_id, "instruction": GERMAN}

        def add_turn(self, draft_id, text, rules=(), **kwargs):
            self.turns.append({"draft_id": draft_id, "text": text, "rules": [dict(r) for r in rules]})
            return {"draft_id": draft_id, "status": "ready", "hard_rules": [*rules],
                    "independently_read": [], "uncertainty_policy": "ask", "open_questions": [],
                    "unrestricted": []}

    policy = TurnPolicy()
    model = StubModel({"rules": [rule(m.F_FULFILLMENT, "in", ["delivery"], "nur Lieferung", turn="T2")],
                       "questions": []})
    response = client(pack, model, policy).post(
        "/api/permission/drafts/LD-1/turns",
        json={"text": "nur Lieferung"})
    assert response.status_code == 200, response.text
    assert policy.turns[0]["draft_id"] == "LD-1"
    assert policy.turns[0]["text"] == "nur Lieferung"
    assert [r["field"] for r in policy.turns[0]["rules"]] == [m.F_FULFILLMENT]
    assert policy.calls == []  # no second draft was created


# ----- running without a model --------------------------------------------------------------------

def test_the_offline_model_reads_with_the_compiler_and_says_which_turn_it_came_from():
    """A test double for rehearsals and CI, never a fallback: a model being *down* becomes questions."""
    from assistant.agent import Turn as T
    from assistant.service import OfflineModel

    class Request:
        turns = (T("T1", "customer", "at most CHF 50 per order"),)
        context: dict = {}
        catalogue: tuple = ()

    reply = OfflineModel().propose(Request())
    assert [r["field"] for r in reply["rules"]] == [m.F_BILLING_CHF]
    assert reply["rules"][0]["turn_id"] == "T1"
    assert reply["rules"][0]["says"] == "at most CHF 50 per order"
    assert str(reply["rules"][0]["value"]) == "50"


def test_the_offline_model_is_chosen_explicitly_and_needs_no_key():
    from assistant.service import build_from_env

    app = build_from_env({"LEASH_ASSISTANT_MODEL": "offline", "LEASH_CARD_ID": "CA0001",
                          "LEASH_SIM_CUTOFF": "2026-08-09T00:00:00Z",
                          "LEASH_PACK_DIR": str(DATA)})
    assert app is not None


def test_without_a_model_and_without_asking_for_offline_it_refuses_to_start():
    """Falling back to the compiler unasked would quietly change what read the customer's words."""
    from assistant.service import build_from_env

    with pytest.raises(Exception):
        build_from_env({"LEASH_CARD_ID": "CA0001", "LEASH_SIM_CUTOFF": "2026-08-09T00:00:00Z",
                        "LEASH_PACK_DIR": str(DATA)})


def test_local_simulation_selects_supplied_customer_not_client_background(pack):
    policy, model = StubPolicy(), StubModel()
    app = create_app(PermissionAssistant(model), pack, policy, cutoff=CUTOFF,
                     card_id="CA0001", simulation=True)
    with TestClient(app) as http:
        response = http.post("/api/permission/drafts", json={"text": GERMAN, "scenario_id": "SCEN0002"})
        assert response.status_code == 200, response.text
        assert policy.calls[-1]["context"]["scope"]["card_id"] == "CA0011"
        assert policy.calls[-1]["context"]["simulation_scenario"] == "SCEN0002"
        # A scenario the pack does not hold keeps this deployment's own customer rather than being
        # refused — hosted scenarios are never in the pack. What stays refused is the client naming a
        # persona directly, which is the part that would let it choose whose background it sees.
        unknown = http.post("/api/permission/drafts", json={"text": GERMAN, "scenario_id": "unknown"})
        assert unknown.status_code == 200, unknown.text
        assert policy.calls[-1]["context"]["scope"]["card_id"] == "CA0001"
        assert http.post("/api/permission/drafts", json={"text": GERMAN, "card_id": "CA0011"}).status_code == 422
    with client(pack, model, policy) as http:
        assert http.post("/api/permission/drafts", json={"text": GERMAN, "scenario_id": "SCEN0002"}).status_code == 422


# --- LEASH-174 -------------------------------------------------------------------------------

def test_the_consent_sentence_comes_from_the_rule_not_the_model(pack):
    """DEC-045: the customer agrees to a sentence generated from the `Rule`, never to model prose.

    If the model's wording were what was shown, the words the customer consented to and the rule the
    engine enforces could drift apart — and the model chooses the words.
    """
    prose = "Ich achte auf ein gutes Angebot und kaufe nur Vernünftiges"
    policy = StubPolicy()
    model = StubModel({"rules": [rule(m.F_BILLING_CHF, "<=", "50", GERMAN)], "questions": [prose]})
    cheap = client(pack, model, policy).post("/api/permission/drafts", json={"text": GERMAN}).json()
    assert cheap["consent_text"] == ["At most CHF 50.00 per order, delivery included."]
    assert not any(prose in sentence for sentence in cheap["consent_text"])
    assert not any(GERMAN in sentence for sentence in cheap["consent_text"]), \
        "not even the customer's own words: the sentence is rendered from the rule"

    # change the rule, and the sentence changes with it. The quote has to carry the new number:
    # for a numeric field that half of the `says` gate still holds (DEC-048).
    louder = "höchstens CHF 120 pro Bestellung"
    dearer = StubModel({"rules": [rule(m.F_BILLING_CHF, "<=", "120", louder)], "questions": []})
    body = client(pack, dearer, StubPolicy()).post("/api/permission/drafts", json={"text": louder}).json()
    assert body["consent_text"] == ["At most CHF 120.00 per order, delivery included."]


# --- LEASH-145 AC10 ---------------------------------------------------------------------------

def test_a_background_question_tells_the_customer_where_it_came_from(pack):
    """A question the customer never asked for must say whose idea it was.

    `_blocking` already rewrites a draft question's wording with the background's phrasing when the
    field matches. Today that swap is invisible, so a recorded preference reaches the chat looking
    exactly like something the customer said — which is the one thing DEC-034 forbids background from
    looking like. The origin travels with the question, and the screen quotes the recorded words.
    """
    returns_question = {"question_id": "Q-returns", "text": "How many days to return it?",
                        "blocking": True, "field": m.F_RETURN_DAYS}
    policy = StubPolicy(open_questions=[returns_question])
    model = StubModel({"rules": [], "questions": []})
    # CU0012 (card CA0024) records a clothing preference mentioning returns.
    app = create_app(PermissionAssistant(model), pack, policy, catalogue=CATALOGUE, cutoff=CUTOFF,
                     card_id="CA0024")
    body = TestClient(app).post("/api/permission/drafts",
                                json={"text": "Buy me a jacket for the autumn"}).json()
    asked = [q for q in body["questions"] if q.get("field") == m.F_RETURN_DAYS]
    assert asked, body["questions"]
    source = asked[0]["source"]
    assert source and source["kind"] == "preference"
    assert "return" in source["evidence"].lower(), "the recorded words, quoted, not paraphrased"
    assert source["file"] == "customers.csv"


def test_a_question_the_customer_prompted_claims_no_background_source(pack):
    """The other half: an ordinary question must not wear a source it does not have."""
    policy = StubPolicy(open_questions=[{"question_id": "Q-limit", "text": "What is the limit?",
                                         "blocking": True, "field": m.F_BILLING_CHF}])
    body = client(pack, StubModel({"rules": [], "questions": []}), policy).post(
        "/api/permission/drafts", json={"text": "Buy me a jacket"}).json()
    assert all(q.get("source") is None for q in body["questions"])


def test_a_later_turn_survives_stored_questions_carrying_their_provenance(pack):
    """The stored draft's assistant questions became objects when provenance was added (AC10).

    The second turn of a conversation joins the questions the customer was asked into an assistant
    turn, so the model can read what was answered. Joining objects as strings raised TypeError, which
    is a 500 on the chat's own path — every conversation with an open question hit it on turn two.
    """
    class StoredPolicy(StubPolicy):
        def draft(self, draft_id):
            return {"draft_id": draft_id, "instruction": GERMAN,
                    "open_questions": [{"text": "What kind of items may I buy?", "blocking": True}],
                    "assistant": {"questions": [{"text": "Did you mean delivery?", "field": None,
                                                 "source": None},
                                                "an older draft stored a bare string"]}}

        def add_turn(self, draft_id, text, rules=(), **kwargs):
            return {"draft_id": draft_id, "status": "ready", "hard_rules": [*rules],
                    "independently_read": [], "uncertainty_policy": "ask", "open_questions": [],
                    "unrestricted": []}

        def record_message(self, draft_id, text, reply, context):
            return {"draft_id": draft_id, "status": "ready", "hard_rules": [],
                    "independently_read": [], "uncertainty_policy": "ask", "open_questions": [],
                    "unrestricted": []}

    model = StubModel({"rules": [rule(m.F_FULFILLMENT, "in", ["delivery"], "nur Lieferung", turn="T3")],
                       "questions": []})
    response = client(pack, model, StoredPolicy()).post("/api/permission/drafts/LD-1/turns",
                                                        json={"text": "nur Lieferung"})
    assert response.status_code == 200, response.text
    asked = [t.text for t in model.seen[0].turns if t.speaker == "assistant"]
    assert asked and "Did you mean delivery?" in asked[0]
    assert "an older draft stored a bare string" in asked[0]


# --- LEASH-174 criterion 7: a loosening rule is refused before it is ever shown (DEC-006) ---------

class ActivePolicy(StubPolicy):
    """A policy service with one active permission: at most CHF 50 per order."""

    def __init__(self, mandates=None, fail=False):
        super().__init__()
        self._fail = fail
        self.mandates = mandates if mandates is not None else [{
            "mandate_id": "TM-1", "version": 1, "status": "active", "instruction": "At most CHF 50 per order.",
            "hard_rules": [{"field": m.F_BILLING_CHF, "operator": "<=", "value": 50,
                            "currency": "CHF", "scope": "purchase"}],
            "uncertainty_policy": "ask",
        }]

    def active_mandate(self):
        if self._fail:
            raise PolicyServiceError("could not reach the policy service")
        current = next((x for x in self.mandates if x["status"] == "active"), None)
        return current


def test_a_rule_that_would_loosen_the_active_permission_is_not_shown_as_a_draft_rule(pack):
    """The engine refuses a loosening change at /tighten, but by then the customer has already read it
    as their new permission. It must not reach them: it is a question, not a candidate."""
    policy = ActivePolicy()
    model = StubModel({"rules": [rule(m.F_BILLING_CHF, "<=", "500", "at most CHF 500 per order")],
                       "questions": []})
    body = client(pack, model, policy).post("/api/permission/drafts",
                                            json={"text": "at most CHF 500 per order"}).json()
    assert policy.calls and policy.calls[0]["rules"] == [], "a looser rule may not be posted as a rule"
    assert body["consent_text"] == [], "and it is never read back as something the customer agreed to"
    assert any("loosen" in q["text"] for q in body["questions"]), body["questions"]


def test_a_stricter_rule_against_the_active_permission_still_becomes_a_draft_rule(pack):
    policy = ActivePolicy()
    model = StubModel({"rules": [rule(m.F_BILLING_CHF, "<=", "20", "at most CHF 20 per order")],
                       "questions": []})
    body = client(pack, model, policy).post("/api/permission/drafts",
                                            json={"text": "at most CHF 20 per order"}).json()
    assert [str(r["value"]) for r in policy.calls[0]["rules"]] == ["20"]
    assert body["consent_text"] == ["At most CHF 20.00 per order, delivery included."]


def test_without_the_active_permission_nothing_is_drafted(pack):
    """Missing is not permission: if the confirmed permission can't be read, a rule cannot be checked
    against it, and a draft that skipped the check would be exactly the loosening this prevents."""
    policy = ActivePolicy(fail=True)
    model = StubModel({"rules": [rule(m.F_BILLING_CHF, "<=", "500", "at most CHF 500 per order")],
                       "questions": []})
    response = client(pack, model, policy).post("/api/permission/drafts",
                                                json={"text": "at most CHF 500 per order"})
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "policy_service_unavailable"
    assert policy.calls == []


def test_with_no_active_permission_a_rule_is_drafted_normally(pack):
    policy = ActivePolicy(mandates=[])
    model = StubModel({"rules": [rule(m.F_BILLING_CHF, "<=", "500", "at most CHF 500 per order")],
                       "questions": []})
    body = client(pack, model, policy).post("/api/permission/drafts",
                                            json={"text": "at most CHF 500 per order"}).json()
    assert [str(r["value"]) for r in policy.calls[0]["rules"]] == ["500"]


def test_a_scenario_the_pack_does_not_hold_keeps_the_deployments_own_customer(pack):
    """Live scenarios are not in the supplied pack: the platform says
    `purchase_attempts: delivered one at a time by scenario runs`, and only publishes whose card a run
    used once it has started (`fixture_profiles`). The assistant holds no platform key (DEC-044), so it
    cannot look it up. The picker therefore chooses the story, never the persona: an unknown scenario
    keeps this deployment's configured customer, and the client still cannot select someone else's.
    """
    policy, model = StubPolicy(), StubModel()
    app = create_app(PermissionAssistant(model), pack, policy, cutoff=CUTOFF,
                     card_id="CA0001", simulation=True)
    with TestClient(app) as http:
        response = http.post("/api/permission/drafts", json={"text": GERMAN, "scenario_id": "SCEN0101"})
        assert response.status_code == 200, response.text
        assert policy.calls[-1]["context"]["scope"]["card_id"] == "CA0001", "not another persona's rows"
        assert policy.calls[-1]["context"]["simulation_scenario"] == "SCEN0101", "the run still needs it"


def test_a_targeted_parser_answer_uses_answer_workflow_without_appending_words(pack):
    class AnswerPolicy(StubPolicy):
        def draft(self, draft_id):
            return {'draft_id': draft_id, 'instruction': GERMAN, 'open_questions': [
                {'question_id': 'Q-items', 'text': 'What kind of items may I buy?', 'field': m.F_ITEM_CATEGORY}]}

        def answer_draft(self, draft_id, question_id, answer):
            self.calls.append((draft_id, question_id, answer))
            return {'draft_id': draft_id, 'instruction': GERMAN, 'status': 'ready', 'open_questions': [],
                    'answers': [{'question_id': question_id, 'answer': answer}], 'hard_rules': []}

    policy, model = AnswerPolicy(), StubModel()
    response = client(pack, model, policy).post('/api/permission/drafts/LD-1/turns',
        json={'text': 'Only groceries.', 'question_id': 'Q-items'})
    assert response.status_code == 200, response.text
    assert response.json()['draft']['instruction'] == GERMAN
    assert policy.calls == [('LD-1', 'Q-items', 'Only groceries.')]
    assert not model.seen
    stale = client(pack, model, policy).post('/api/permission/drafts/LD-1/turns',
        json={'text': 'Only groceries.', 'question_id': 'Q-gone'})
    assert stale.status_code == 409
    assert len(policy.calls) == 1


def test_targeted_model_reply_supplies_only_the_question_being_answered(pack):
    class StoredPolicy(StubPolicy):
        def draft(self, draft_id):
            return {'instruction': GERMAN, 'open_questions': [
                {'question_id': 'AQ-shop', 'text': 'Which shops?', 'origin': 'model'},
                {'question_id': 'AQ-item', 'text': 'Which items?', 'origin': 'model'}]}

        def add_turn(self, draft_id, text, rules=(), **kwargs):
            return {'instruction': GERMAN + ' ' + text, 'hard_rules': list(rules), 'open_questions': []}

    model = StubModel({'rules': [rule(m.F_ITEM_CATEGORY, 'in', ['groceries'], 'Only groceries.', 'T2')], 'questions': []})
    response = client(pack, model, StoredPolicy()).post('/api/permission/drafts/LD-1/turns',
        json={'text': 'Only groceries.', 'question_id': 'AQ-item'})
    assert response.status_code == 200, response.text
    asked = [t.text for t in model.seen[0].turns if t.speaker == 'assistant']
    assert asked == ['Which items?']
