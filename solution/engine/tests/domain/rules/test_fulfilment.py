from factories import facts, mandate, max_per_order, purchase, snapshot
from fixtures.mandates import MANDATES
from leash.domain import mandate as m
from leash.domain.decide import decide
from leash.domain.mandate import Rule
from leash.domain.rules.fulfilment import fulfilment_rule

DELIVERY = mandate(Rule(m.F_FULFILLMENT, "in", ("delivery",)))


def test_pickup_fails_delivery_rule():
    [check] = fulfilment_rule(purchase(fulfillment="pickup"), DELIVERY, snapshot(), facts())
    assert (check.status, check.reason_code) == ("fail", "fulfilment_not_allowed")
    assert check.detail == "This order is for pickup, but you asked for delivery."
    assert decide(purchase(fulfillment="pickup"), DELIVERY, snapshot(), facts()).verdict == "decline"


def test_digital_fails_delivery_rule():
    [check] = fulfilment_rule(purchase(fulfillment="digital"), DELIVERY, snapshot(), facts())
    assert check.status == "fail" and "digital" in check.detail


def test_delivery_passes():
    [check] = fulfilment_rule(purchase(fulfillment="delivery"), DELIVERY, snapshot(), facts())
    assert (check.status, check.actual) == ("pass", "Delivery")


def test_excluded_method_fails():
    no_pickup = mandate(Rule(m.F_FULFILLMENT, "not_in", ("pickup",)))
    [check] = fulfilment_rule(purchase(fulfillment="pickup"), no_pickup, snapshot(), facts())
    assert check.status == "fail"
    [check] = fulfilment_rule(purchase(fulfillment="delivery"), no_pickup, snapshot(), facts())
    assert check.status == "pass"


def test_an_unknown_method_is_not_permission():
    [check] = fulfilment_rule(purchase(fulfillment="unknown"), DELIVERY, snapshot(), facts())
    assert (check.status, check.reason_code) == ("warn", "fulfilment_unknown")
    assert decide(purchase(fulfillment="unknown"), DELIVERY, snapshot(), facts()).verdict == "step_up"


def test_no_fulfilment_rule_no_check():
    assert fulfilment_rule(purchase(fulfillment="pickup"), mandate(max_per_order("400")), snapshot(), facts()) == []


def test_the_compiled_scen0001_mandate_includes_the_delivery_rule():
    assert MANDATES["SCEN0001"].fulfillment == frozenset({"delivery"})
    p = purchase("50.00", fulfillment="pickup")
    assert "fulfilment_not_allowed" in decide(p, MANDATES["SCEN0001"], snapshot(), facts()).reason_codes


def test_rule_values_are_normalised_like_the_order():
    # Review finding: a capitalised exclusion was silently ignored and a padded value wrongly declined.
    no_pickup = mandate(Rule(m.F_FULFILLMENT, "not_in", ("Pickup",)))
    [check] = fulfilment_rule(purchase(fulfillment="pickup"), no_pickup, snapshot(), facts())
    assert check.status == "fail"
    padded = mandate(Rule(m.F_FULFILLMENT, "in", (" Delivery ",)))
    [check] = fulfilment_rule(purchase(fulfillment="delivery"), padded, snapshot(), facts())
    assert check.status == "pass"


def test_contradictory_rules_explain_themselves():
    nothing = mandate(Rule(m.F_FULFILLMENT, "in", ("pickup",)), Rule(m.F_FULFILLMENT, "in", ("delivery",)))
    [check] = fulfilment_rule(purchase(fulfillment="delivery"), nothing, snapshot(), facts())
    assert check.status == "fail" and check.detail == "Your rules allow no fulfilment method, so this delivery order can't pass."
    both = mandate(Rule(m.F_FULFILLMENT, "in", ("delivery",)), Rule(m.F_FULFILLMENT, "not_in", ("delivery",)))
    [check] = fulfilment_rule(purchase(fulfillment="delivery"), both, snapshot(), facts())
    assert check.detail == "This order is for delivery, which you excluded."


def test_rules_differing_only_in_case_or_spacing_combine_correctly():
    # Review round 2: raw values were intersected before normalising, so equal methods cancelled out.
    for rules, method, status in (
            ((Rule(m.F_FULFILLMENT, "in", ("Delivery",)), Rule(m.F_FULFILLMENT, "in", ("delivery",))), "delivery", "pass"),
            ((Rule(m.F_FULFILLMENT, "=", " delivery"), Rule(m.F_FULFILLMENT, "in", ("DELIVERY",))), "delivery", "pass"),
            ((Rule(m.F_FULFILLMENT, "in", ("delivery", "pickup")), Rule(m.F_FULFILLMENT, "in", ("Pickup",))), "pickup", "pass"),
            ((Rule(m.F_FULFILLMENT, "in", ("delivery", "pickup")), Rule(m.F_FULFILLMENT, "in", ("Pickup",))), "delivery", "fail")):
        [check] = fulfilment_rule(purchase(fulfillment=method), mandate(*rules), snapshot(), facts())
        assert check.status == status, (rules, method)


def test_an_empty_allowed_value_reads_sensibly():
    [check] = fulfilment_rule(purchase(fulfillment="delivery"), mandate(Rule(m.F_FULFILLMENT, "in", ("",))),
                              snapshot(), facts())
    assert check.status == "fail" and "asked for ." not in check.detail


def test_an_empty_excluded_value_is_ignored():
    for rules in ((Rule(m.F_FULFILLMENT, "not_in", ("",)),), (Rule(m.F_FULFILLMENT, "not_in", ("", "pickup")),)):
        [check] = fulfilment_rule(purchase(fulfillment="delivery"), mandate(*rules), snapshot(), facts()) or [None]
        assert check is None or "never " not in check.agreed.replace("never pickup", "")
