from dataclasses import FrozenInstanceError, replace
from datetime import date

import pytest

from leash.domain.clock import SimTime
from leash.domain.money import money
from leash.domain.purchase import LineItem, Merchant, Purchase, Term


def merchant(**kw) -> Merchant:
    base = dict(merchant_id="ME0022", name="PixelHarbor", category="electronics", mcc="5732", country="CH",
                city="Zurich", availability="store_and_online", recurring_capable=False)
    return Merchant(**{**base, **kw})


def line(item_id="IT0017", quantity=1, **kw) -> LineItem:
    base = dict(line_no=1, item_id=item_id, name="27-inch computer monitor", category="electronics",
                quantity=quantity, unit_price=money("289.00"), currency="CHF",
                details="27-inch IPS panel, 2-year seller warranty; returns accepted within 14 days")
    return LineItem(**{**base, **kw})


def purchase(**kw) -> Purchase:
    base = dict(
        authorization_id="AZ-7f3a", source_authorization_id="AU0035", card_id="CA0039", merchant=merchant(),
        sim_time=SimTime.parse("2026-08-12T09:40:00Z"), amount=money("289.00"), currency="CHF",
        billing_amount_chf=money("289.00"), items_subtotal=money("289.00"), delivery_fee=money("0.00"),
        channel="ecommerce", device_id="DVC-785971", recent_attempts_10m=0, fulfillment="delivery", delivery_by=None,
        order_returnable=Term.TRUE, order_cancellable=Term.UNKNOWN, related_authorization_id=None, related_status=None,
        description="27-inch computer monitor", items=(line(),),
    )
    return Purchase(**{**base, **kw})


def test_fingerprint_includes_quantities():
    one = purchase(items=(line(quantity=1),))
    three = purchase(items=(line(quantity=3),))
    assert one.item_fingerprint != three.item_fingerprint
    assert three.item_fingerprint == (("IT0017", 3),)


def test_fingerprint_ignores_line_order():
    a = purchase(items=(line("IT0001", line_no=1), line("IT0004", 2, line_no=2)))
    b = purchase(items=(line("IT0004", 2, line_no=1), line("IT0001", line_no=2)))
    assert a.item_fingerprint == b.item_fingerprint == (("IT0001", 1), ("IT0004", 2))


def test_fingerprint_is_a_multiset_of_lines():
    # One pair per line: two lines of 1 are not the same fingerprint as one line of 2.
    split = purchase(items=(line("IT0004", 1, line_no=1), line("IT0004", 1, line_no=2)))
    assert split.item_fingerprint == (("IT0004", 1), ("IT0004", 1))
    assert split.item_fingerprint != purchase(items=(line("IT0004", 2),)).item_fingerprint


def test_unknown_return_term_is_not_true():
    p = purchase(order_returnable=Term.UNKNOWN)
    assert p.order_returnable is not Term.TRUE
    assert not p.order_returnable.is_true
    with pytest.raises(TypeError):
        bool(p.order_returnable)  # no silent truthiness: "unknown" must never read as permission


def test_terms_parse_the_four_api_values_only():
    assert [Term.parse(v) for v in ("true", "false", "unknown", "not_applicable")] == [
        Term.TRUE, Term.FALSE, Term.UNKNOWN, Term.NOT_APPLICABLE]
    with pytest.raises(ValueError):
        Term.parse("maybe")


def test_missing_values_stay_missing():
    p = purchase(delivery_by=None, related_authorization_id=None, related_status=None, device_id=None,
                 source_authorization_id=None)
    assert (p.delivery_by, p.related_authorization_id, p.related_status, p.device_id) == (None, None, None, None)
    assert purchase(delivery_by=date(2026, 8, 10)).delivery_by == date(2026, 8, 10)


def test_carries_every_decision_relevant_fact():
    p = purchase(related_authorization_id="AZ-9d10", related_status="declined", fulfillment="digital",
                 recent_attempts_10m=2, currency="USD", amount=money("450.00"), billing_amount_chf=money("391.50"))
    assert (p.authorization_id, p.source_authorization_id, p.card_id) == ("AZ-7f3a", "AU0035", "CA0039")
    assert p.merchant.merchant_id == "ME0022" and p.sim_time == SimTime.parse("2026-08-12T09:40:00Z")
    assert (p.amount, p.currency, p.billing_amount_chf) == (money("450.00"), "USD", money("391.50"))
    assert (p.device_id, p.recent_attempts_10m, p.fulfillment) == ("DVC-785971", 2, "digital")
    assert (p.related_authorization_id, p.related_status) == ("AZ-9d10", "declined")
    assert p.order_cancellable is Term.UNKNOWN


def test_is_immutable():
    p = purchase()
    with pytest.raises(FrozenInstanceError):
        p.amount = money("1.00")  # type: ignore[misc]


def test_rejects_invalid_facts():
    with pytest.raises(ValueError, match="at least one"):
        purchase(items=())
    with pytest.raises(ValueError, match="quantity"):
        line(quantity=0)
    with pytest.raises(TypeError):
        purchase(billing_amount_chf=289.0)
    with pytest.raises(TypeError):
        purchase(order_returnable="true")
    with pytest.raises(ValueError, match="related_status"):
        purchase(related_status="maybe")
    with pytest.raises(ValueError, match="attempts"):
        purchase(recent_attempts_10m=-1)


def test_replace_keeps_validation():
    with pytest.raises(ValueError):
        replace(purchase(), items=())
