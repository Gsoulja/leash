from decimal import Decimal

from factories import facts, line, mandate, purchase, snapshot
from leash.domain import mandate as m
from leash.domain.clock import SimTime
from leash.domain.decide import decide
from leash.domain.mandate import Rule
from leash.domain.rules.single import single_rule
from leash.domain.snapshot import PriorPurchase

MONITOR = (line("IT0017", name="27-inch monitor", category="electronics"),)
ONCE = mandate(Rule(m.F_ITEM_ID, "in", ("IT0017",)), Rule(m.F_MAX_PURCHASES, "<=", Decimal("1")))


def order(aid, ts, items=MONITOR):
    return purchase("289.00", authorization_id=aid, sim_time=SimTime.parse(ts), items=items)


def test_second_monitor_after_approval_asks():
    s = snapshot(PriorPurchase(order("A", "2026-08-12T09:15:00Z"), "approved"))
    now = order("B", "2026-08-14T09:15:00Z")
    [check] = single_rule(now, ONCE, s, facts())
    assert (check.status, check.reason_code) == ("warn", "already_purchased")
    assert check.detail.startswith('You already bought "27-inch monitor"')
    assert decide(now, ONCE, s, facts()).verdict == "step_up"


def test_nothing_approved_yet_no_check():
    for state in ("waiting", "declined", "timed_out"):
        s = snapshot(PriorPurchase(order("A", "2026-08-12T09:15:00Z"), state))
        assert single_rule(order("B", "2026-08-14T09:15:00Z"), ONCE, s, facts()) == []
    assert single_rule(order("B", "2026-08-14T09:15:00Z"), ONCE, snapshot(), facts()) == []


def test_every_approved_purchase_in_the_run_counts_even_with_an_item_rule():  # DEC-032: max_count.v2
    s = snapshot(PriorPurchase(order("A", "2026-08-12T09:15:00Z", items=(line("IT0001"),)), "approved"))
    [check] = single_rule(order("B", "2026-08-14T09:15:00Z"), ONCE, s, facts())
    assert check.reason_code == "already_purchased"


def test_adding_an_item_rule_never_lifts_the_purchase_count():  # DEC-032, found by LEASH-034 (pack AU0017)
    once = mandate(Rule(m.F_MAX_PURCHASES, "<=", Decimal("1")))
    s = snapshot(PriorPurchase(order("A", "2026-08-12T09:15:00Z", items=(line("IT0001"),)), "approved"))
    now = order("B", "2026-08-14T09:15:00Z")
    assert decide(now, once, s, facts()).verdict == "step_up"
    assert decide(now, once.tighten(Rule(m.F_ITEM_ID, "in", ("IT0017",))), s, facts()).verdict == "step_up"


def test_the_purchase_count_field_is_version_2():
    assert m.F_MAX_PURCHASES == "leash.purchase.max_count.v2"


def test_the_retired_version_1_count_never_approves():  # DEC-005: an unknown field is unsupported
    v1 = mandate(Rule("leash.purchase.max_count.v1", "<=", Decimal("1")))
    assert v1.unsupported_rules()
    assert decide(order("B", "2026-08-14T09:15:00Z"), v1, snapshot(), facts()).verdict != "approve"


def test_without_item_ids_any_approved_purchase_counts():
    once = mandate(Rule(m.F_MAX_PURCHASES, "<=", Decimal("1")))
    s = snapshot(PriorPurchase(order("A", "2026-08-12T09:15:00Z", items=(line("IT0001"),)), "approved"))
    [check] = single_rule(order("B", "2026-08-14T09:15:00Z", items=(line("IT0002"),)), once, s, facts())
    assert check.reason_code == "already_purchased"


def test_allows_up_to_the_stated_number():
    twice = mandate(Rule(m.F_MAX_PURCHASES, "<=", Decimal("2")))
    s = snapshot(PriorPurchase(order("A", "2026-08-12T09:15:00Z"), "approved"))
    assert single_rule(order("B", "2026-08-14T09:15:00Z"), twice, s, facts()) == []


def test_no_rule_no_check():
    s = snapshot(PriorPurchase(order("A", "2026-08-12T09:15:00Z"), "approved"))
    assert single_rule(order("B", "2026-08-14T09:15:00Z"), mandate(), s, facts()) == []


def test_a_zero_limit_warns_without_crashing():
    for rule in (Rule(m.F_MAX_PURCHASES, "<", Decimal("1")), Rule(m.F_MAX_PURCHASES, "<=", Decimal("0"))):
        [check] = single_rule(order("B", "2026-08-14T09:15:00Z"), mandate(rule), snapshot(), facts())
        assert (check.status, check.reason_code) == ("warn", "already_purchased")
        assert "no purchases" in check.detail
