from decimal import Decimal

from factories import facts, mandate, max_per_order, purchase, snapshot
from leash.domain import mandate as m
from leash.domain.decide import decide
from leash.domain.mandate import Rule
from leash.domain.rules.unsupported import unsupported_rule

UNKNOWN = Rule("leash.merchant.carbon_score.v1", "<=", Decimal("3"))


def test_unknown_rule_never_approves_under_approve_policy():
    d = decide(purchase("20.00"), mandate(max_per_order("400"), UNKNOWN, uncertainty="approve"), snapshot(), facts())
    assert d.verdict == "step_up" and "unsupported_mandate_rule" in d.reason_codes


def test_decline_policy_declines_and_ask_asks():
    for policy, verdict in (("decline", "decline"), ("ask", "step_up")):
        d = decide(purchase("20.00"), mandate(UNKNOWN, uncertainty=policy), snapshot(), facts())
        assert d.verdict == verdict


def test_the_check_names_the_field():
    [check] = unsupported_rule(purchase(), mandate(UNKNOWN), snapshot(), facts())
    assert (check.status, check.reason_code) == ("integrity", "unsupported_mandate_rule")
    assert "leash.merchant.carbon_score.v1" in check.detail and "leash.merchant.carbon_score.v1" in check.actual


def test_a_known_field_with_an_unenforceable_value_is_unsupported_too():
    eur_limit = Rule(m.F_BILLING_CHF, "<=", Decimal("400"), currency="EUR", scope="purchase")
    [check] = unsupported_rule(purchase(), mandate(eur_limit), snapshot(), facts())
    assert check.reason_code == "unsupported_mandate_rule" and m.F_BILLING_CHF in check.detail


def test_one_check_per_unsupported_rule_and_none_when_all_supported():
    other = Rule("leash.shop.rating.v1", ">=", Decimal("4"))
    assert len(unsupported_rule(purchase(), mandate(UNKNOWN, other), snapshot(), facts())) == 2
    assert unsupported_rule(purchase(), mandate(max_per_order("400")), snapshot(), facts()) == []


def test_it_never_loosens_a_decline():
    d = decide(purchase("520.00"), mandate(max_per_order("400"), UNKNOWN, uncertainty="approve"), snapshot(), facts())
    assert d.verdict == "decline"


def test_the_message_reads_as_plain_words_with_the_currency():
    eur = Rule(m.F_BILLING_CHF, "<=", Decimal("100"), currency="EUR", scope="purchase")
    [check] = unsupported_rule(purchase(), mandate(eur), snapshot(), facts())
    assert "Decimal(" not in check.detail and "EUR 100" in check.detail
    [check] = unsupported_rule(purchase(), mandate(Rule("leash.x.v1", "in", ("a", "b"))), snapshot(), facts())
    assert "leash.x.v1 in a, b" in check.detail
