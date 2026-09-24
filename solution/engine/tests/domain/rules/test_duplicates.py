
from factories import facts, line, mandate, max_per_order, merchant, purchase, snapshot
from leash.domain import mandate as m
from leash.domain.clock import SimTime
from leash.domain.decide import decide
from leash.domain.mandate import Rule
from leash.domain.rules.duplicates import duplicates_rule
from leash.domain.snapshot import PriorPurchase

MONITOR = (line("IT0017", name="27-inch monitor", category="electronics"),)
SPLIT_120 = mandate(max_per_order("120"), Rule(m.F_SPLIT_CHECK, "=", "on"))


def order(aid, ts, chf, items=MONITOR, **kw):
    return purchase(chf, authorization_id=aid, source_authorization_id=f"SRC-{aid}", sim_time=SimTime.parse(ts),
                    items=items, **kw)


def test_same_monitor_25_minutes_later_asks():
    s = snapshot(PriorPurchase(order("A", "2026-08-12T09:15:00Z", "289.00"), "approved"))
    [check] = duplicates_rule(order("B", "2026-08-12T09:40:00Z", "289.00"), mandate(), s, facts())
    assert (check.status, check.reason_code) == ("warn", "possible_duplicate")
    assert "11:15" in check.detail and "approved" in check.detail  # Zurich local time, earlier state
    assert decide(order("B", "2026-08-12T09:40:00Z", "289.00"), mandate(), s, facts()).verdict == "step_up"


def test_waiting_order_is_also_a_duplicate_source():
    s = snapshot(PriorPurchase(order("A", "2026-08-12T09:15:00Z", "289.00"), "waiting"))
    [check] = duplicates_rule(order("B", "2026-08-12T10:15:00Z", "289.00"), mandate(), s, facts())
    assert check.reason_code == "possible_duplicate" and "waiting" in check.detail


def test_after_24_hours_or_different_amount_items_or_shop_is_not_a_duplicate():
    s = snapshot(PriorPurchase(order("A", "2026-08-12T09:15:00Z", "289.00"), "approved"))
    assert duplicates_rule(order("B", "2026-08-13T09:15:00Z", "289.00"), mandate(), s, facts()) == []
    assert duplicates_rule(order("B", "2026-08-12T09:40:00Z", "279.00"), mandate(), s, facts()) == []
    assert duplicates_rule(order("B", "2026-08-12T09:40:00Z", "289.00", items=(line("IT0018"),)),
                           mandate(), s, facts()) == []
    assert duplicates_rule(order("B", "2026-08-12T09:40:00Z", "289.00", merchant=merchant(merchant_id="ME0099")),
                           mandate(), s, facts()) == []


def test_fingerprint_compares_item_ids_with_quantities():
    s = snapshot(PriorPurchase(order("A", "2026-08-12T09:15:00Z", "289.00"), "approved"))
    two = (line("IT0017", quantity=2, name="27-inch monitor", category="electronics"),)
    assert duplicates_rule(order("B", "2026-08-12T09:40:00Z", "289.00", items=two), mandate(), s, facts()) == []


def test_declined_orders_are_never_duplicate_sources():
    s = snapshot(PriorPurchase(order("A", "2026-08-12T09:15:00Z", "289.00"), "declined"))
    assert duplicates_rule(order("B", "2026-08-12T09:40:00Z", "289.00"), mandate(), s, facts()) == []


def test_requote_of_a_declined_order_is_not_its_duplicate():
    # The platform says the related order was declined, even if our run still shows it waiting.
    s = snapshot(PriorPurchase(order("A", "2026-08-12T09:15:00Z", "289.00"), "waiting"))
    requote = order("B", "2026-08-12T09:40:00Z", "289.00", related_authorization_id="SRC-A", related_status="declined")
    assert duplicates_rule(requote, mandate(), s, facts()) == []


def test_70_plus_65_within_6_minutes_asks():
    groceries = (line("IT0003"),)
    s = snapshot(PriorPurchase(order("A", "2026-08-13T17:20:00Z", "70.00", items=groceries), "approved"))
    now = order("B", "2026-08-13T17:26:00Z", "65.00", items=(line("IT0004"),))
    [check] = duplicates_rule(now, SPLIT_120, s, facts())
    assert (check.status, check.reason_code) == ("warn", "possible_split")
    assert "CHF 135.00" in check.detail and "CHF 120.00" in check.detail and "19:20" in check.detail
    assert decide(now, SPLIT_120, s, facts()).verdict == "step_up"


def test_split_needs_the_hour_the_limit_and_the_switch():
    s = snapshot(PriorPurchase(order("A", "2026-08-13T17:20:00Z", "70.00", items=(line("IT0003"),)), "approved"))
    later = order("B", "2026-08-13T18:20:00Z", "65.00", items=(line("IT0004"),))
    assert duplicates_rule(later, SPLIT_120, s, facts()) == []  # exactly 60 min apart is outside
    small = order("B", "2026-08-13T17:26:00Z", "50.00", items=(line("IT0004"),))
    assert duplicates_rule(small, SPLIT_120, s, facts()) == []  # 120.00 total is not over
    now = order("B", "2026-08-13T17:26:00Z", "65.00", items=(line("IT0004"),))
    assert duplicates_rule(now, mandate(max_per_order("120")), s, facts()) == []  # split check not on


def test_split_is_not_reported_when_already_a_duplicate():
    s = snapshot(PriorPurchase(order("A", "2026-08-13T17:20:00Z", "70.00"), "approved"))
    checks = duplicates_rule(order("B", "2026-08-13T17:26:00Z", "70.00"), SPLIT_120, s, facts())
    assert [c.reason_code for c in checks] == ["possible_duplicate"]


def test_no_history_no_check():
    assert duplicates_rule(order("B", "2026-08-12T09:40:00Z", "289.00"), SPLIT_120, snapshot(), facts()) == []
