from decimal import Decimal

from factories import facts, mandate, merchant, purchase, snapshot
from leash.domain import mandate as m
from leash.domain.clock import SimTime
from leash.domain.decide import decide
from leash.domain.mandate import Rule
from leash.domain.rules.session import session_points, session_rule
from leash.domain.snapshot import HistoryBaseline, PriorPurchase

RISK = mandate(Rule(m.F_SESSION_RISK, "<", Decimal("2")))
HOME = HistoryBaseline(devices=frozenset({"DVC-HOME"}), countries=frozenset({"CH"}))
DAY = "2026-08-12T10:00:00Z"  # 12:00 in Zurich


def at(ts=DAY, device="DVC-HOME", attempts=0, country="CH", aid="NOW"):
    return purchase(authorization_id=aid, sim_time=SimTime.parse(ts), device_id=device, recent_attempts_10m=attempts,
                    merchant=merchant(country=country))


def test_new_device_asks():
    [check] = session_rule(at(device="DVC-NEW"), RISK, snapshot(baseline=HOME), facts())
    assert (check.status, check.reason_code) == ("warn", "session_risk")
    assert "new device" in check.detail.lower() and check.actual == "2 points"
    assert decide(at(device="DVC-NEW"), RISK, snapshot(baseline=HOME), facts()).verdict == "step_up"


def test_known_device_normal_pace_passes():
    [check] = session_rule(at(), RISK, snapshot(baseline=HOME), facts())
    assert (check.status, check.actual, check.label) == ("pass", "0 points", "Session")


def test_velocity_uses_the_event_attempt_count():
    assert session_points(at(attempts=1), snapshot(baseline=HOME)) == [("1 other attempt in 10 minutes", 1)]
    assert session_points(at(attempts=3), snapshot(baseline=HOME)) == [("3 other attempts in 10 minutes", 2)]


def test_night_uses_zurich_local_time():
    # 23:30 UTC in August is 01:30 in Zurich: night. 04:30 UTC is 06:30 in Zurich: day.
    assert session_points(at("2026-08-11T23:30:00Z"), snapshot(baseline=HOME)) == [("01:30 at night in Zurich", 1)]
    assert session_points(at("2026-08-12T04:30:00Z"), snapshot(baseline=HOME)) == []
    # Winter: 23:30 UTC is 00:30 in Zurich.
    assert session_points(at("2026-01-11T23:30:00Z"), snapshot(baseline=HOME)) == [("00:30 at night in Zurich", 1)]


def test_first_time_country_scores_two():
    assert session_points(at(country="RO"), snapshot(baseline=HOME)) == [("first purchase in RO", 2)]


def test_burst_at_night_on_new_device_adds_up():
    burst = at("2026-08-12T00:14:00Z", device="DVC-NEW", attempts=4)
    [check] = session_rule(burst, RISK, snapshot(baseline=HOME), facts())
    assert check.actual == "5 points"
    assert "02:14" in check.detail


def test_known_device_recovers():
    burst = at("2026-08-12T00:14:00Z", device="DVC-NEW", attempts=4, aid="BURST")
    s = snapshot(PriorPurchase(burst, "declined"), baseline=HOME)
    [check] = session_rule(at("2026-08-12T08:00:00Z"), RISK, s, facts())
    assert check.status == "pass"


def test_missing_device_counts_as_new():
    assert session_points(at(device=None), snapshot(baseline=HOME)) == [("no device ID", 2)]


def test_inclusive_limit():
    limit = mandate(Rule(m.F_SESSION_RISK, "<=", Decimal("2")))
    [check] = session_rule(at(device="DVC-NEW"), limit, snapshot(baseline=HOME), facts())
    assert check.status == "pass"


def test_no_rule_no_check():
    assert session_rule(at(device="DVC-NEW", attempts=5), mandate(), snapshot(baseline=HOME), facts()) == []


def test_agreed_wording():
    [check] = session_rule(at(), RISK, snapshot(baseline=HOME), facts())
    assert check.agreed == "Under 2 risk points"
    one = mandate(Rule(m.F_SESSION_RISK, "<=", Decimal("1")))
    assert session_rule(at(), one, snapshot(baseline=HOME), facts())[0].agreed == "At most 1 risk point"
