from decimal import Decimal

from factories import facts, line, mandate, purchase, snapshot
from leash.domain import mandate as m
from leash.domain.decide import combine
from leash.domain.mandate import Rule
from leash.domain.money import money
from leash.domain.rules.basket import basket_rule

MONITOR = mandate(Rule(m.F_ITEM_ID, "in", ("IT0017",)), Rule(m.F_UNREQUESTED_ITEMS, "=", Decimal("0")),
                  Rule(m.F_MAX_QUANTITY, "<=", Decimal("1")))
GROCERIES = mandate(Rule(m.F_ITEM_CATEGORY, "in", ("groceries",)))
MON = dict(item_id="IT0017", name="27-inch computer monitor", category="electronics", unit_price=money("380.00"))
PLAN = dict(item_id="IT0066", name="Extended protection plan", category="subscriptions", unit_price=money("79.00"), line_no=2)


def run(mm, *lines, **f):
    return basket_rule(purchase(items=tuple(lines)), mm, snapshot(), facts(**f))


def test_protection_plan_added_to_monitor_fails():
    [check] = run(MONITOR, line(**MON), line(**PLAN))
    assert (check.status, check.reason_code) == ("fail", "unrequested_addon")
    assert check.detail == 'The agent added "Extended protection plan" (CHF 79.00) that you didn\'t ask for.'


def test_different_item_fails():
    voucher = dict(item_id="IT0005", name="Digital gift voucher", category="gift_card", unit_price=money("195.00"))
    [check] = run(MONITOR, line(**voucher))
    assert (check.status, check.reason_code) == ("fail", "item_mismatch")
    assert check.detail == '"Digital gift voucher" is not the item you asked for.'


def test_requested_item_passes():
    [check] = run(MONITOR, line(**MON))
    assert check.status == "pass"


def test_cosmetics_in_grocery_basket_asks():
    cosmetics = dict(item_id="IT0062", name="Fragrance and beauty gift", category="cosmetics", line_no=2)
    [check] = run(GROCERIES, line(), line(**cosmetics))
    assert (check.status, check.reason_code) == ("warn", "outside_purpose")
    assert combine([check], "ask") == "step_up"


def test_addons_are_detected_by_item_category_and_facts_not_merchant():
    shoe = dict(item_id="IT0014", name="Road-running shoes", category="sporting_goods")
    plan_as_shoe = dict(item_id="IT0014", name="Road-running shoes", category="sporting_goods", line_no=2)
    shoes = mandate(Rule(m.F_ITEM_ID, "in", ("IT0014",)), Rule(m.F_UNREQUESTED_ITEMS, "=", Decimal("0")))
    # same catalogue item, but the shop's text reads as an add-on on line 2
    [check] = run(shoes, line(**shoe), line(**plan_as_shoe), addon_lines=frozenset({2}))
    assert check.reason_code == "unrequested_addon"


def test_quantity_three_fails_one_item():
    [check] = run(MONITOR, line(quantity=3, **MON))
    assert (check.status, check.reason_code) == ("fail", "quantity_exceeded")
    assert check.detail == "3 items in this order; you asked for at most 1."


def test_quantity_counts_across_lines():
    [check] = run(MONITOR, line(**MON), line(**{**MON, "line_no": 2}))
    assert check.reason_code == "quantity_exceeded"


def test_excluded_item_category_fails():
    mm = mandate(Rule(m.F_ITEM_CATEGORY, "not_in", ("cosmetics",)))
    cosmetics = dict(item_id="IT0062", name="Fragrance and beauty gift", category="cosmetics")
    [check] = run(mm, line(**cosmetics))
    assert (check.status, check.reason_code) == ("fail", "excluded_item")


def test_no_basket_rule_no_check():
    assert run(mandate(), line()) == []


def test_requested_item_is_never_treated_as_an_addon():
    voucher = mandate(Rule(m.F_ITEM_ID, "in", ("IT0005",)), Rule(m.F_UNREQUESTED_ITEMS, "=", Decimal("0")))
    p = purchase(items=(line("IT0005", name="Voucher", category="gift_card"),))
    [check] = basket_rule(p, voucher, snapshot(), facts())
    assert check.status == "pass"
    monitor = mandate(Rule(m.F_ITEM_ID, "in", ("IT0017",)), Rule(m.F_UNREQUESTED_ITEMS, "=", Decimal("0")))
    p = purchase(items=(line("IT0017", name="Monitor", category="electronics"),))
    [check] = basket_rule(p, monitor, snapshot(), facts(addon_lines=frozenset({1})))
    assert check.status == "pass"


def test_addon_message_shows_the_line_total_and_its_own_currency():
    monitor = mandate(Rule(m.F_ITEM_ID, "in", ("IT0017",)))
    two = line("IT0099", quantity=2, line_no=2, name="Plan", category="subscriptions", unit_price=money("25.00"))
    p = purchase(items=(line("IT0017", name="Monitor", category="electronics"), two))
    [check] = basket_rule(p, monitor, snapshot(), facts())
    assert 'added "Plan" (CHF 50.00)' in check.detail
    odd = line("IT0099", line_no=2, name="Plan", category="subscriptions", unit_price=money("9.00"), currency="JPY")
    p = purchase(items=(line("IT0017", name="Monitor", category="electronics"), odd))
    [check] = basket_rule(p, monitor, snapshot(), facts())
    assert 'added "Plan" (JPY 9.00)' in check.detail


def test_purpose_mode_never_treats_the_wanted_category_or_the_only_line_as_an_addon():
    vouchers = mandate(Rule(m.F_ITEM_CATEGORY, "in", ("gift_card",)), Rule(m.F_UNREQUESTED_ITEMS, "=", Decimal("0")))
    [check] = basket_rule(purchase(items=(line("IT0005", name="Voucher", category="gift_card"),)), vouchers,
                          snapshot(), facts())
    assert check.status == "pass"
    groceries = mandate(Rule(m.F_ITEM_CATEGORY, "in", ("groceries",)), Rule(m.F_UNREQUESTED_ITEMS, "=", Decimal("0")))
    [check] = basket_rule(purchase(items=(line(),)), groceries, snapshot(), facts(addon_lines=frozenset({1})))
    assert check.status == "pass"


def test_purpose_mode_addon_is_named_with_its_price():
    groceries = mandate(Rule(m.F_ITEM_CATEGORY, "in", ("groceries",)), Rule(m.F_UNREQUESTED_ITEMS, "=", Decimal("0")))
    plan = line("IT0066", line_no=2, name="Delivery pass", category="subscriptions", unit_price=money("9.90"))
    [check] = basket_rule(purchase(items=(line(), plan)), groceries, snapshot(), facts())
    assert (check.status, check.reason_code) == ("fail", "unrequested_addon")
    assert 'added "Delivery pass" (CHF 9.90)' in check.detail
    flagged = line("IT0002", line_no=2, name="Fruit box club")
    [check] = basket_rule(purchase(items=(line(), flagged)), groceries, snapshot(), facts(addon_lines=frozenset({2})))
    assert check.reason_code == "unrequested_addon" and "Fruit box club" in check.detail


def test_excluded_item_id_fails():
    no_voucher = mandate(Rule(m.F_ITEM_ID, "not_in", ("IT0005",)))
    p = purchase(items=(line(), line("IT0005", line_no=2, name="Voucher", category="gift_card")))
    [check] = basket_rule(p, no_voucher, snapshot(), facts())
    assert (check.status, check.reason_code) == ("fail", "excluded_item")
    assert '"Voucher"' in check.detail
    [check] = basket_rule(purchase(items=(line(),)), no_voucher, snapshot(), facts())
    assert check.status == "pass"


def test_without_items_or_purpose_a_lone_addon_category_line_is_not_an_addon():
    extra_free = mandate(Rule(m.F_UNREQUESTED_ITEMS, "=", Decimal("0")))
    for category in ("gift_card", "subscriptions"):
        [check] = basket_rule(purchase(items=(line("IT0005", name="Voucher", category=category),)), extra_free,
                              snapshot(), facts())
        assert check.status == "pass"
    plan = line("IT0066", line_no=2, name="Plan", category="subscriptions", unit_price=money("9.00"))
    [check] = basket_rule(purchase(items=(line(), plan)), extra_free, snapshot(), facts())
    assert check.reason_code == "unrequested_addon"


def test_without_items_or_purpose_quantity_counts_every_line():
    one = mandate(Rule(m.F_MAX_QUANTITY, "<=", Decimal("1")))
    for items in ((line("IT0005", quantity=3, category="gift_card"),),
                  (line("IT0066", quantity=2, category="subscriptions"),),
                  (line(), line("IT0005", line_no=2, category="gift_card"))):
        [check] = basket_rule(purchase(items=items), one, snapshot(), facts())
        assert check.reason_code == "quantity_exceeded"


def test_unknown_category_is_not_permission_under_an_exclusion():
    no_cosmetics = mandate(Rule(m.F_ITEM_CATEGORY, "not_in", ("cosmetics",)))
    [check] = basket_rule(purchase(items=(line(category="unknown", name="Mystery box"),)), no_cosmetics,
                          snapshot(), facts())
    assert (check.status, check.reason_code) == ("warn", "unknown_item_category")
    [check] = basket_rule(purchase(items=(line(),)), no_cosmetics, snapshot(), facts())
    assert (check.status, check.detail) == ("pass", "The basket holds only allowed items.")


def test_purpose_mode_lone_out_of_purpose_line_warns_even_under_nothing_extra():
    groceries = mandate(Rule(m.F_ITEM_CATEGORY, "in", ("groceries",)), Rule(m.F_UNREQUESTED_ITEMS, "=", Decimal("0")))
    stream = line("IT0080", name="Streaming plan", category="subscriptions")
    [check] = basket_rule(purchase(items=(stream,)), groceries, snapshot(), facts())
    assert (check.status, check.reason_code) == ("warn", "outside_purpose")
    perfume = line("IT0081", name="Perfume", category="cosmetics")
    [check] = basket_rule(purchase(items=(perfume,)), groceries, snapshot(), facts(addon_lines=frozenset({1})))
    assert (check.status, check.reason_code) == ("warn", "outside_purpose")


def test_flagging_every_line_of_a_multi_line_basket_never_loosens_nothing_extra():
    # LEASH-034: flagging line 2 declines; flagging lines 1 and 2 must not approve.
    for rules in ((Rule(m.F_UNREQUESTED_ITEMS, "=", Decimal("0")),),
                  (Rule(m.F_ITEM_CATEGORY, "in", ("groceries",)), Rule(m.F_UNREQUESTED_ITEMS, "=", Decimal("0")))):
        p = purchase(items=(line("IT0001"), line("IT0002", line_no=2)))
        [one] = basket_rule(p, mandate(*rules), snapshot(), facts(addon_lines=frozenset({2})))
        [both] = basket_rule(p, mandate(*rules), snapshot(), facts(addon_lines=frozenset({1, 2})))
        assert one.status == "fail" and both.status == "fail"
        assert both.reason_code == "unrequested_addon"


def test_adding_a_category_or_item_rule_never_escapes_a_quantity_limit():
    # LEASH-034 review: [max_quantity <= 1] declined; adding "gift cards only" made the quantity count zero.
    p = purchase(items=(line("IT0001", quantity=2), line("IT0002", line_no=2)))
    [before] = basket_rule(p, mandate(Rule(m.F_MAX_QUANTITY, "<=", Decimal("1"))), snapshot(), facts())
    assert before.reason_code == "quantity_exceeded"
    for extra in (Rule(m.F_ITEM_CATEGORY, "in", ("gift_card",)), Rule(m.F_ITEM_ID, "in", ("IT0099",))):
        [after] = basket_rule(p, mandate(Rule(m.F_MAX_QUANTITY, "<=", Decimal("1")), extra), snapshot(), facts())
        assert after.status == "fail", (extra, after)


def test_adding_a_category_rule_never_escapes_nothing_extra():
    plan = line("IT0066", line_no=2, name="Delivery pass", category="subscriptions")
    p = purchase(items=(line(), plan))
    none_extra = Rule(m.F_UNREQUESTED_ITEMS, "=", Decimal("0"))
    [before] = basket_rule(p, mandate(none_extra), snapshot(), facts())
    assert before.reason_code == "unrequested_addon"
    [after] = basket_rule(p, mandate(none_extra, Rule(m.F_ITEM_CATEGORY, "in", ("subscriptions",))), snapshot(), facts())
    assert after.status == "fail", after


def test_nothing_extra_with_a_purpose_names_the_line_outside_it():
    cards = mandate(Rule(m.F_ITEM_CATEGORY, "in", ("gift_card",)), Rule(m.F_UNREQUESTED_ITEMS, "=", Decimal("0")))
    p = purchase(items=(line("IT0005", name="Voucher", category="gift_card"), line("IT0001", line_no=2, name="Milk")))
    [check] = basket_rule(p, cards, snapshot(), facts())
    assert (check.status, check.reason_code) == ("fail", "unrequested_addon") and '"Milk"' in check.detail


def test_item_category_rules_with_nothing_in_common_fail():
    rules = (Rule(m.F_ITEM_CATEGORY, "in", ("groceries",)), Rule(m.F_ITEM_CATEGORY, "in", ("electronics",)))
    [check] = basket_rule(purchase(items=(line(),)), mandate(*rules), snapshot(), facts())
    assert check.status == "fail"


def test_an_item_rule_covering_every_line_never_escapes_nothing_extra():
    # LEASH-034 round 2 (pack AU0007): groceries + cosmetics under "groceries, nothing extra" declines;
    # adding "item_id in (both lines)" must not turn the cosmetics line into a mere warning.
    lipstick = line("IT0062", line_no=2, name="Lipstick", category="cosmetics")
    p = purchase(items=(line(), lipstick))
    base = (Rule(m.F_UNREQUESTED_ITEMS, "=", Decimal("0")), Rule(m.F_ITEM_CATEGORY, "in", ("groceries",)))
    [before] = basket_rule(p, mandate(*base), snapshot(), facts())
    [after] = basket_rule(p, mandate(*base, Rule(m.F_ITEM_ID, "in", ("IT0001", "IT0062"))), snapshot(), facts())
    assert before.status == "fail" and after.status == "fail", after


def test_a_narrower_category_rule_that_leaves_no_line_never_escapes_nothing_extra():
    lipstick = line("IT0062", line_no=2, name="Lipstick", category="cosmetics")
    p = purchase(items=(line(), lipstick))
    base = (Rule(m.F_ITEM_CATEGORY, "in", ("clothing", "cosmetics")), Rule(m.F_UNREQUESTED_ITEMS, "=", Decimal("0")))
    [before] = basket_rule(p, mandate(*base), snapshot(), facts())
    [after] = basket_rule(p, mandate(*base, Rule(m.F_ITEM_CATEGORY, "in", ("clothing",))), snapshot(), facts())
    assert before.status == "fail" and after.status == "fail", after
