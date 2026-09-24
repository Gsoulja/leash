import pytest

from factories import facts, mandate, purchase, snapshot
from leash.domain import mandate as m
from leash.domain.mandate import Rule
from leash.domain.purchase import Term
from leash.domain.rules.returns import returns_rule
from decimal import Decimal

MIN_14 = mandate(Rule(m.F_RETURN_DAYS, ">=", Decimal("14")))


def run(returnable=Term.TRUE, mm=MIN_14, **f):
    return returns_rule(purchase(order_returnable=returnable), mm, snapshot(), facts(**f))


def test_exactly_14_days_passes():
    [check] = run(return_days=14, final_sale=False)
    assert (check.status, check.actual) == ("pass", "14 days")


def test_shorter_window_fails():
    [check] = run(return_days=7, final_sale=False)
    assert (check.status, check.reason_code) == ("fail", "returns_too_short")
    assert check.detail == "Only 7-day returns; you asked for at least 14 days."


def test_final_sale_fails():
    [check] = run(final_sale=True)
    assert (check.status, check.reason_code, check.actual) == ("fail", "final_sale", "Final sale")


def test_not_returnable_order_fails():
    [check] = run(returnable=Term.FALSE)
    assert (check.status, check.reason_code) == ("fail", "final_sale")


@pytest.mark.parametrize("returnable", [Term.UNKNOWN, Term.TRUE, Term.NOT_APPLICABLE])
def test_unknown_return_policy_asks(returnable):
    [check] = run(returnable=returnable, return_days=None)
    assert (check.status, check.reason_code, check.actual) == ("warn", "returns_unknown", "Not stated")


def test_stricter_fact_wins_when_they_disagree():
    [check] = run(returnable=Term.FALSE, return_days=30, final_sale=False)
    assert check.status == "fail"  # the order says not returnable; "30 days" in the text doesn't override it


def test_no_return_rule_no_check():
    assert run(mm=mandate(), return_days=1) == []
