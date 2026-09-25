"""LEASH-174 / DEC-045: the sentence the customer approves is generated from the Rule object.

The model's prose never becomes consent text, so these sentences are the contract the customer agrees
to. A change here changes what a customer was shown, which is why they are pinned exactly.
"""

from decimal import Decimal

import pytest

from leash.domain import mandate as m
from leash.domain.mandate import Rule
from leash.policy.registry import REGISTRY
from leash.policy.render import describe_rule


def test_a_per_order_limit_reads_as_the_customer_agreed_it():
    rule = Rule(m.F_BILLING_CHF, "<=", Decimal("50"), currency="CHF", scope="purchase")
    assert describe_rule(rule) == "At most CHF 50.00 per order, delivery included."


def test_a_strict_limit_says_under_not_at_most():
    rule = Rule(m.F_BILLING_CHF, "<", Decimal("50"), currency="CHF", scope="purchase")
    assert describe_rule(rule) == "Under CHF 50.00 per order, delivery included."


def test_review_distinguishes_requirements_and_customer_interventions():
    from leash.policy.render import permission_review
    review = permission_review((Rule(m.F_BILLING_CHF, "<=", Decimal("20")),
                                Rule(m.F_MAX_PURCHASES, "<=", Decimal("1"))), "ask")
    assert review["must_follow"] == ["At most CHF 20.00 per order, delivery included."]
    assert any("1 approved purchase" in line for line in review["must_ask"])
    assert any("shop" in line for line in review["may_choose"])


def test_a_period_limit_names_its_window():
    rule = Rule(m.F_BILLING_CHF, "<=", Decimal("300"), currency="CHF", scope="period", period_days=7)
    assert describe_rule(rule) == "At most CHF 300.00 across any 7 days."


def test_a_limit_with_no_scope_still_reads_as_per_order():
    """A model-supplied rule carries no scope bookkeeping; period_days is what actually decides."""
    assert describe_rule(Rule(m.F_BILLING_CHF, "<=", Decimal("50"))) == \
        "At most CHF 50.00 per order, delivery included."


def test_paid_before_is_singular_for_one_and_counted_above_it():
    assert describe_rule(Rule(m.F_PRIOR_PURCHASES, ">=", Decimal("1"))) == \
        "Only shops you have paid before."
    assert describe_rule(Rule(m.F_PRIOR_PURCHASES, ">=", Decimal("3"))) == \
        "Only shops you have paid at least 3 times before."


def test_one_item_and_many_items_read_differently():
    assert describe_rule(Rule(m.F_MAX_QUANTITY, "<=", Decimal("1"))) == "One item per order."
    assert describe_rule(Rule(m.F_MAX_QUANTITY, "<=", Decimal("4"))) == "At most 4 items per order."


def test_a_list_of_allowed_values_is_read_back_in_plain_words():
    assert describe_rule(Rule(m.F_ITEM_CATEGORY, "in", ("home_electronics",))) == \
        "Only home electronics in the basket."
    assert describe_rule(Rule(m.F_FULFILLMENT, "in", ("delivery",))) == "For delivery only."


def test_an_excluded_value_says_never():
    assert describe_rule(Rule(m.F_ITEM_CATEGORY, "not_in", ("vouchers",))) == \
        "Never vouchers in the basket."


@pytest.mark.parametrize("field", sorted(REGISTRY))
def test_every_registry_field_has_a_sentence(field):
    """No field may fall through to its raw name: the customer would be consenting to jargon."""
    spec = REGISTRY[field]
    operator = "in" if "in" in spec.operators else sorted(spec.operators)[0]
    value = ("example_value",) if spec.value_kind == "text" else Decimal("2")
    if field == m.F_SPLIT_CHECK:
        operator, value = "=", "on"
    sentence = describe_rule(Rule(field, operator, value))
    assert field not in sentence, sentence
    assert sentence and sentence[0].isupper() and sentence.endswith("."), sentence


def test_changing_the_rule_changes_the_sentence():
    a = describe_rule(Rule(m.F_BILLING_CHF, "<=", Decimal("50")))
    b = describe_rule(Rule(m.F_BILLING_CHF, "<=", Decimal("500")))
    assert a != b and "50.00" in a and "500.00" in b


def test_a_rule_the_engine_cannot_enforce_never_reads_as_a_permission():
    """An amount that arrived as text is not a limit; saying "At most CHF 20" would be a lie."""
    unenforceable = Rule(m.F_BILLING_CHF, "<=", "20", currency="CHF", scope="purchase")
    assert describe_rule(unenforceable) == \
        "A restriction I cannot enforce, so I would ask you about this purchase."


@pytest.mark.parametrize("rule, expected", [
    (Rule(m.F_PRIOR_PURCHASES, ">", Decimal("1")), "at least 2 times"),
    (Rule(m.F_PRIOR_PURCHASES, ">=", Decimal("1.5")), "at least 2 times"),
    (Rule(m.F_MAX_QUANTITY, "<", Decimal("2")), "One item per order."),
    (Rule(m.F_RETURN_DAYS, ">", Decimal("14")), "at least 15 days"),
    (Rule(m.F_ITEM_CATEGORY, "!=", "vouchers"), "Never vouchers"),
])
def test_review_preserves_strict_bounds_and_exclusions(rule, expected):
    from leash.policy.render import permission_review
    assert m.supported(rule)
    assert expected in describe_rule(rule)
    assert any(expected in line for line in permission_review([rule], "ask")["must_follow"])


def test_review_does_not_truncate_a_fractional_session_threshold():
    from leash.policy.render import permission_review
    rule = Rule(m.F_SESSION_RISK, "<", Decimal("1.5"))
    assert "below 1.5" in describe_rule(rule)
    assert any("at or above 1.5" in line for line in permission_review([rule], "ask")["must_ask"])
