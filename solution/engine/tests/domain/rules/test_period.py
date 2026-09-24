from decimal import Decimal

from factories import facts, mandate, purchase, snapshot
from leash.domain import mandate as m
from leash.domain.clock import SimTime
from leash.domain.decide import decide
from leash.domain.mandate import Rule
from leash.domain.rules.period import period_rule
from leash.domain.snapshot import PriorPurchase

WEEK_300 = mandate(Rule(m.F_BILLING_CHF, "<=", Decimal("300"), currency="CHF", scope="period", period_days=7))


def prior(aid, ts, chf, state="approved"):
    return PriorPurchase(purchase(chf, authorization_id=aid, sim_time=SimTime.parse(ts)), state)


def at(ts, chf):
    return purchase(chf, authorization_id="NOW", sim_time=SimTime.parse(ts))


def test_total_reaching_exactly_300_is_approved():
    s = snapshot(prior("A", "2026-08-10T09:12:00Z", "44.50"), prior("B", "2026-08-11T18:35:00Z", "120.00"),
                 prior("C", "2026-08-13T17:20:00Z", "70.00"))
    [check] = period_rule(at("2026-08-15T09:30:00Z", "65.50"), WEEK_300, s, facts())
    assert check.status == "pass"
    assert check.actual == "CHF 234.50 paid + CHF 65.50 = CHF 300.00"
    assert (check.label, check.agreed) == ("7-day total", "≤ CHF 300.00 in any 7 days")


def test_one_cent_over_fails():
    s = snapshot(prior("A", "2026-08-15T09:30:00Z", "300.00"))
    [check] = period_rule(at("2026-08-16T16:10:00Z", "0.01"), WEEK_300, s, facts())
    assert (check.status, check.reason_code) == ("fail", "over_period_limit")
    assert check.detail == "This would bring the last 7 days to CHF 300.01, over your CHF 300.00 limit."


def test_waiting_order_not_counted():
    s = snapshot(prior("A", "2026-08-13T17:20:00Z", "250.00", "waiting"), prior("B", "2026-08-13T17:21:00Z", "40.00", "declined"))
    [check] = period_rule(at("2026-08-14T10:00:00Z", "60.00"), WEEK_300, s, facts())
    assert check.status == "pass" and check.actual.startswith("CHF 0.00 paid")


def test_exactly_seven_days_older_is_outside():
    s = snapshot(prior("A", "2026-08-12T09:45:00Z", "250.00"))
    [check] = period_rule(at("2026-08-19T09:45:00Z", "100.00"), WEEK_300, s, facts())
    assert check.status == "pass"


def test_platform_counter_higher_is_used_and_alerted():
    s = snapshot(prior("A", "2026-08-13T17:20:00Z", "100.00"), platform=Decimal("280.00"))
    checks = period_rule(at("2026-08-14T10:00:00Z", "30.00"), WEEK_300, s, facts())
    assert [c.status for c in checks] == ["fail", "info"]
    assert checks[0].actual == "CHF 280.00 paid + CHF 30.00 = CHF 310.00"
    assert checks[1].reason_code == "spend_counter_mismatch"
    decision = decide(at("2026-08-14T10:00:00Z", "30.00"), WEEK_300, s, facts(), rules=(period_rule,))
    assert decision.alerts == ("spend_counter_mismatch",)


def test_platform_counter_lower_keeps_our_ledger_and_still_alerts():
    s = snapshot(prior("A", "2026-08-13T17:20:00Z", "280.00"), platform=Decimal("100.00"))
    checks = period_rule(at("2026-08-14T10:00:00Z", "30.00"), WEEK_300, s, facts())
    assert checks[0].status == "fail" and checks[1].reason_code == "spend_counter_mismatch"


def test_no_period_rule_no_check():
    assert period_rule(at("2026-08-14T10:00:00Z", "30.00"), mandate(), snapshot(), facts()) == []


def test_every_window_containing_the_purchase_counts_not_only_the_one_ending_at_it():
    # A purchase dated before an approved one: the window ending at the later approval holds both.
    s = snapshot(prior("LATER", "2026-08-13T09:00:00Z", "200.00"))
    [check] = period_rule(at("2026-08-12T09:00:00Z", "150.00"), WEEK_300, s, facts())
    assert (check.status, check.reason_code) == ("fail", "over_period_limit")
    assert check.actual == "CHF 200.00 paid + CHF 150.00 = CHF 350.00"


def test_a_later_approval_outside_the_window_does_not_count():
    s = snapshot(prior("LATER", "2026-08-19T09:00:00Z", "200.00"))  # exactly 7 days later: no shared window
    [check] = period_rule(at("2026-08-12T09:00:00Z", "150.00"), WEEK_300, s, facts())
    assert check.status == "pass"


def test_the_worst_window_is_reported():
    s = snapshot(prior("A", "2026-08-06T09:00:00Z", "100.00"), prior("B", "2026-08-14T09:00:00Z", "120.00"),
                 prior("C", "2026-08-15T09:00:00Z", "60.00"))
    [check] = period_rule(at("2026-08-10T09:00:00Z", "50.00"), WEEK_300, s, facts())
    # windows containing 10 Aug: ending 10 Aug → A (100); ending 14 Aug → B (120); ending 15 Aug → B + C (180)
    assert check.actual == "CHF 180.00 paid + CHF 50.00 = CHF 230.00" and check.status == "pass"


def test_adding_a_second_period_rule_never_drops_the_platform_counter():  # LEASH-034 round 4
    # The platform doesn't say which window its counter covers, so the higher total is used for every period rule:
    # otherwise appending "CHF 1000 in 30 days" would switch the counter off and loosen the 7-day limit.
    s = snapshot(prior("A", "2026-08-13T17:20:00Z", "100.00"), platform=Decimal("280.00"))
    now = at("2026-08-14T10:00:00Z", "30.00")
    tight = WEEK_300.tighten(Rule(m.F_BILLING_CHF, "<=", Decimal("1000"), currency="CHF", scope="period", period_days=30))
    assert decide(now, WEEK_300, s, facts()).verdict == "decline"
    assert decide(now, tight, s, facts()).verdict == "decline"
    week = next(c for c in period_rule(now, tight, s, facts()) if c.label == "7-day total")
    assert (week.status, week.actual) == ("fail", "CHF 280.00 paid + CHF 30.00 = CHF 310.00")


def test_the_mismatch_alert_is_raised_once_with_several_period_rules():
    s = snapshot(prior("A", "2026-08-13T17:20:00Z", "100.00"), platform=Decimal("280.00"))
    tight = WEEK_300.tighten(Rule(m.F_BILLING_CHF, "<=", Decimal("1000"), currency="CHF", scope="period", period_days=30))
    checks = period_rule(at("2026-08-14T10:00:00Z", "30.00"), tight, s, facts())
    assert [c.reason_code for c in checks].count("spend_counter_mismatch") == 1
