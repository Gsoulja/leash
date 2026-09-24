import json
from decimal import Decimal
from pathlib import Path

import jsonschema
import pytest

from fixtures.mandates import MANDATES
from leash.domain import mandate as m
from leash.domain.mandate import CompiledMandate, Rule
from leash.policy.hard_rules import (AppendOnlyError, HardRulesError, check_append_only, mandate_from_api,
                                     mandate_to_api, rule_from_api, rule_to_api)

SCHEMA = json.loads((Path(__file__).resolve().parents[4] / "data" / "schemas" / "authorization_event.schema.json")
                    .read_text())
RULE_SCHEMA = {"$ref": "#/$defs/mandate_rule", "$defs": SCHEMA["$defs"]}


def test_price_rule_serialises_like_the_docs_example():
    rule = Rule(m.F_BILLING_CHF, "<=", Decimal("20"), currency="CHF", scope="purchase")
    assert rule_to_api(rule) == {"field": "authorization.billing_amount_chf", "operator": "<=", "value": 20,
                                 "currency": "CHF", "scope": "purchase"}


@pytest.mark.parametrize("scenario", sorted(MANDATES))
def test_every_scenario_mandate_validates_and_round_trips(scenario):
    mandate = MANDATES[scenario]
    body = mandate_to_api(mandate, open_questions=("Is a gift card ok?",))
    for rule in body["hard_rules"]:
        jsonschema.validate(rule, RULE_SCHEMA)
    assert set(body) == {"instruction", "hard_rules", "uncertainty_policy", "guidance", "open_questions"}
    assert body["guidance"] == list(mandate.notes)
    parsed, questions = mandate_from_api(json.loads(json.dumps(body)))  # through real JSON
    assert parsed == mandate and questions == ("Is a gift card ok?",)


def test_values_keep_their_exact_meaning():
    for value in (Decimal("0.05"), Decimal("120.50"), Decimal("999999999.99"), Decimal("7")):
        rule = Rule(m.F_BILLING_CHF, "<=", value, currency="CHF", scope="purchase")
        assert rule_from_api(json.loads(json.dumps(rule_to_api(rule)))) == rule
    lists = Rule(m.F_ITEM_CATEGORY, "in", ("groceries", "household"))
    assert rule_to_api(lists)["value"] == ["groceries", "household"]
    assert rule_from_api(rule_to_api(lists)) == lists
    period = Rule(m.F_BILLING_CHF, "<=", Decimal("300"), currency="CHF", scope="period", period_days=7)
    assert rule_to_api(period)["period_days"] == 7 and rule_from_api(rule_to_api(period)) == period


def test_unknown_fields_are_kept_to_be_enforced_as_unsupported():
    rule = rule_from_api({"field": "leash.merchant.carbon_score.v1", "operator": "<=", "value": 3})
    mandate = CompiledMandate("x", (rule,), "ask")
    assert mandate.unsupported_rules() == (rule,)


def test_schema_invalid_rules_are_rejected():
    for bad in ({"field": "x", "operator": "~", "value": 1}, {"field": "", "operator": "<", "value": 1},
                {"field": "x", "operator": "<", "value": 1, "extra": True},
                {"field": "x", "operator": "<", "value": 1, "period_days": 0},
                {"field": "x", "operator": "in", "value": [1, 2]}):
        with pytest.raises(HardRulesError):
            rule_from_api(bad)
    with pytest.raises(HardRulesError):
        mandate_from_api({"instruction": "x", "hard_rules": [], "uncertainty_policy": "maybe"})


def test_existing_rules_are_preserved_when_serialising_a_tightened_mandate():
    before = MANDATES["SCEN0001"]
    after = before.tighten_max_per_order(Decimal("100")).tighten_uncertainty("decline")
    old, new = mandate_to_api(before)["hard_rules"], mandate_to_api(after)["hard_rules"]
    assert new[:len(old)] == old and len(new) == len(old) + 1
    check_append_only(old, new)
    with pytest.raises(AppendOnlyError):
        check_append_only(old, new[1:])  # a rule removed
    with pytest.raises(AppendOnlyError):
        check_append_only(old, [{**old[0], "value": 999}] + new[1:])  # a rule replaced


def test_the_hand_written_check_agrees_with_the_official_schema():
    samples = [
        {"field": "f", "operator": "<=", "value": 20}, {"field": "f", "operator": "in", "value": ["a"]},
        {"field": "f", "operator": "=", "value": "43", "currency": None, "scope": None, "period_days": None},
        {"field": "f", "operator": "<=", "value": 1.5, "currency": "EUR", "scope": "period", "period_days": 7},
        {"field": "f", "operator": "~", "value": 1}, {"field": "", "operator": "<", "value": 1},
        {"field": "f", "operator": "<", "value": 1, "x": 1}, {"field": "f", "operator": "<", "value": [1]},
        {"field": "f", "operator": "<", "value": 1, "period_days": 0}, {"field": "f", "operator": "<", "value": 1,
                                                                        "currency": "JPY"},
        {"field": "f", "operator": "<", "value": 1, "scope": "day"}, {"field": "f", "operator": "<"},
        {"field": "f", "operator": "<", "value": {"a": 1}}, {"field": 3, "operator": "<", "value": 1},
        {"field": "f", "operator": "<", "value": 1, "period_days": 2.5},
    ]
    from leash.policy.hard_rules import _check_rule
    for body in samples:
        official = jsonschema.Draft202012Validator(RULE_SCHEMA).is_valid(body)
        try:
            _check_rule(body)
            ours = True
        except HardRulesError:
            ours = False
        assert ours == official, body


def test_rules_the_api_format_cannot_hold_are_refused_not_emitted():
    # Review: an out-of-enum currency was emitted schema-invalid; Infinity crashed with OverflowError.
    for rule in (Rule(m.F_BILLING_CHF, "<=", Decimal("20"), currency="chf"),
                 Rule(m.F_BILLING_CHF, "<=", Decimal("20"), currency="JPY"),
                 Rule(m.F_BILLING_CHF, "<=", Decimal("Infinity")), Rule(m.F_BILLING_CHF, "<=", Decimal("-Infinity"))):
        with pytest.raises(HardRulesError):
            rule_to_api(rule)
    with pytest.raises(HardRulesError):
        mandate_to_api(CompiledMandate("", (), "ask"))


def test_parsing_agrees_with_the_schema_on_edge_types():
    assert rule_from_api({"field": "f", "operator": "<=", "value": 1, "scope": "period", "period_days": 7.0,
                          "currency": "CHF"}).period_days == 7
    for bad in ({"field": "f", "operator": ["<"], "value": 1}, {"field": "f", "operator": "<", "value": 1,
                                                                 "currency": {"a": 1}},
                {"field": "f", "operator": "<", "value": 1, "scope": ["period"]}):
        with pytest.raises(HardRulesError):
            rule_from_api(bad)
    with pytest.raises(HardRulesError):
        rule_from_api({"field": "f", "operator": "<=", "value": 1e400})


def test_append_only_compares_canonically():
    old = [{"field": "f", "operator": "<=", "value": 1}]
    check_append_only(old, [{"field": "f", "operator": "<=", "value": 1, "currency": None, "scope": None,
                             "period_days": None}])  # an echoed rule with explicit nulls is the same rule
    with pytest.raises(AppendOnlyError):
        check_append_only(old, [{"field": "f", "operator": "<=", "value": True}])
