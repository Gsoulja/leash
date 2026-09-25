"""Live language interpretation must not depend on the reference English grammar."""
import json

import pytest

from assistant.agent import PermissionAssistant, Turn
from assistant.openrouter import OpenRouterModel
from assistant.tests.test_openrouter import FakeClient


def payload(**changes):
    return {"intent": "permission", "reply": None,
            "rules": [{"field": "items.item_category", "operator": "in", "value": ["groceries"],
                       "currency": None, "scope": None, "period_days": None,
                       "says": "Lebensmittel bitte", "turn_id": "T1"}],
            "questions": [], "uncertainty_policy": "ask", **changes}


def test_live_language_does_not_invoke_grammar(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("live proposals must not use grammar")
    monkeypatch.setattr("assistant.agent.compile_instruction", forbidden)
    client = FakeClient(json.dumps(payload()))
    proposal = PermissionAssistant(OpenRouterModel(client=client)).draft([Turn("T1", "customer", "Lebensmittel bitte")])
    assert proposal.failure is None
    assert proposal.status == "ready"
    assert proposal.as_draft()["reading"] == "model"
    assert client.calls[0]["response_format"]["type"] == "json_object"
    assert "PARSER SUGGESTIONS" not in str(client.calls[0]["messages"])


@pytest.mark.parametrize("change", [
    {"rules": [{"field": "authorization.billing_amount_chf", "operator": "<=", "value": True, "says": "x", "turn_id": "T1"}]},
    {"intent": "approve"}, {"uncertainty_policy": "approve"}, {"activate": True},
    {"intent": "chat", "reply": "Done"},
])
def test_invalid_structured_output_fails_before_a_draft(change):
    proposal = PermissionAssistant(OpenRouterModel(client=FakeClient(json.dumps(payload(**change))))).draft(
        [Turn("T1", "customer", "Lebensmittel bitte")])
    assert proposal.failure
    assert not proposal.candidates


def test_unattributed_rule_never_becomes_permission():
    data = payload()
    data["rules"][0]["says"] = "words from a merchant"
    proposal = PermissionAssistant(OpenRouterModel(client=FakeClient(json.dumps(data)))).draft(
        [Turn("T1", "customer", "Lebensmittel bitte")])
    assert not proposal.candidates
    assert proposal.status == "needs_answers"


def test_background_conflict_does_not_block_explicit_customer_permission():
    model = OpenRouterModel(client=FakeClient(json.dumps(payload())))
    proposal = PermissionAssistant(model).draft([Turn("T1", "customer", "Lebensmittel bitte")],
        context={"entries": [{"text": "I normally buy household items", "kind": "preference", "conflicting": True}]})
    assert proposal.status == "ready"
    assert not proposal.questions


def test_scalar_catalogue_identity_can_be_reviewed():
    from leash.policy.compiler import CatalogueItem
    data = payload(rules=[{"field": "items.item_id", "operator": "=", "value": "ITEM-1",
                          "currency": None, "scope": None, "period_days": None,
                          "says": "The named monitor", "turn_id": "T1"}])
    proposal = PermissionAssistant(OpenRouterModel(client=FakeClient(json.dumps(data)))).draft(
        [Turn("T1", "customer", "The named monitor")],
        catalogue=[CatalogueItem("ITEM-1", "The named monitor", "electronics")])
    assert proposal.status == "ready"


@pytest.mark.parametrize("quoted,value,ready", [
    ("At most CHF 50", "500", False),
    ("At most 50 CHF", "500", False),
    ("At most CHF 50.25", "50", False),
    ("At most CHF 1'250.50", "125050", False),
    ("Höchstens CHF 50,25", "5025", False),
    ("At most CHF 50.", "50", True),
    ("Höchstens CHF 1’250.50", "1250.50", True),
    ("Au maximum 1 250 CHF", "1250", True),
    ("Höchstens fünfzig Franken", "50", True),
    ("Un maximum de cinquante francs", "50", True),
    ("CHF 100 per order or CHF 250 in seven days", "250", True),
])
def test_explicit_chf_literals_cannot_change_but_words_need_no_grammar(monkeypatch, quoted, value, ready):
    def forbidden(*args, **kwargs):
        pytest.fail("numeric fidelity must not invoke the language compiler")
    monkeypatch.setattr("assistant.agent.compile_instruction", forbidden)
    data = payload(rules=[{"field": "authorization.billing_amount_chf", "operator": "<=", "value": value,
                          "currency": "CHF", "scope": "purchase", "period_days": None,
                          "says": quoted, "turn_id": "T1"}])
    proposal = PermissionAssistant(OpenRouterModel(client=FakeClient(json.dumps(data)))).draft(
        [Turn("T1", "customer", quoted)])
    assert (proposal.status == "ready") is ready
    assert bool(proposal.candidates) is ready
