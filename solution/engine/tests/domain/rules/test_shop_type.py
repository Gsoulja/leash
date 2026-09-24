from factories import facts, mandate, merchant, purchase, snapshot
from leash.domain import mandate as m
from leash.domain.mandate import Rule
from leash.domain.rules.shop_type import shop_type_rule


def run(p, mm):
    return shop_type_rule(p, mm, snapshot(), facts())


def test_sustainable_goods_shop_fails_specialist_rule():
    p = purchase(merchant=merchant(merchant_id="ME0053", name="GreenLoop", category="sustainable_goods"))
    [check] = run(p, mandate(Rule(m.F_MERCHANT_CATEGORY, "in", ("sporting_goods",))))
    assert (check.status, check.reason_code) == ("fail", "merchant_category")
    assert check.detail == "GreenLoop is a sustainable goods shop, not a sporting goods shop."
    assert check.actual == "GreenLoop: sustainable goods"


def test_allowed_category_passes():
    p = purchase(merchant=merchant(name="TrailSpark", category="sporting_goods"))
    [check] = run(p, mandate(Rule(m.F_MERCHANT_CATEGORY, "in", ("sporting_goods",))))
    assert check.status == "pass" and check.agreed == "sporting goods shop"


def test_excluded_category_fails():
    [check] = run(purchase(), mandate(Rule(m.F_MERCHANT_CATEGORY, "not_in", ("groceries",))))
    assert check.status == "fail" and "groceries" in check.detail


def test_no_shop_type_restriction_produces_no_check():
    assert run(purchase(), mandate()) == []
