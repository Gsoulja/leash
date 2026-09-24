from datetime import timedelta
from decimal import Decimal

import pytest

from leash.domain.clock import SimTime
from leash.domain.money import money
from leash.domain.purchase import LineItem, Merchant, Purchase, Term
from leash.domain.snapshot import HistoryBaseline, HistoryRecord, PriorPurchase, Snapshot

WEEK = timedelta(days=7)


def merchant(mid="ME0001", country="CH") -> Merchant:
    return Merchant(merchant_id=mid, name=f"Shop {mid}", category="groceries", mcc="5411", country=country,
                    city="Zurich", availability="store_and_online", recurring_capable=False)


def purchase(aid, ts, chf, mid="ME0001", device="DVC-A", country="CH") -> Purchase:
    item = LineItem(line_no=1, item_id="IT0001", name="Produce", category="groceries", quantity=1,
                    unit_price=money(chf), currency="CHF", details="")
    return Purchase(authorization_id=aid, source_authorization_id=None, card_id="CA0001",
                    merchant=merchant(mid, country), sim_time=SimTime.parse(ts), amount=money(chf), currency="CHF",
                    billing_amount_chf=money(chf), items_subtotal=money(chf), delivery_fee=money("0.00"),
                    channel="ecommerce", device_id=device, recent_attempts_10m=0, fulfillment="delivery",
                    delivery_by=None, order_returnable=Term.FALSE, order_cancellable=Term.UNKNOWN,
                    related_authorization_id=None, related_status=None, description="Groceries", items=(item,))


def rec(ttype="purchase", status="approved", mid="ME0001", device="DVC-A", country="CH") -> HistoryRecord:
    return HistoryRecord(transaction_type=ttype, status=status, merchant_id=mid, device_id=device, merchant_country=country)


def snapshot(prior=(), history=(), platform=None) -> Snapshot:
    return Snapshot(card_id="CA0001", baseline=HistoryBaseline.from_records(history), prior=tuple(prior),
                    platform_period_spend_chf=platform)


def test_waiting_purchase_is_not_spend():
    now = SimTime.parse("2026-08-13T17:30:00Z")
    s = snapshot(prior=[
        PriorPurchase(purchase("A1", "2026-08-13T17:20:00Z", "70.00"), "approved"),
        PriorPurchase(purchase("A2", "2026-08-13T17:26:00Z", "65.00"), "waiting"),
        PriorPurchase(purchase("A3", "2026-08-12T10:05:00Z", "126.00"), "declined"),
        PriorPurchase(purchase("A4", "2026-08-12T11:00:00Z", "20.00"), "timed_out"),
    ])
    assert s.approved_spend_in_window(now, WEEK) == Decimal("70.00")


def test_window_is_trailing_and_by_simulated_time():
    now = SimTime.parse("2026-08-19T09:45:00Z")
    s = snapshot(prior=[
        PriorPurchase(purchase("OLD", "2026-08-12T09:45:00Z", "100.00"), "approved"),  # exactly 7 days: outside
        PriorPurchase(purchase("IN", "2026-08-12T09:45:01Z", "50.00"), "approved"),
        PriorPurchase(purchase("LATER", "2026-08-19T10:00:00Z", "9.00"), "approved"),  # after now: outside
    ])
    assert s.approved_spend_in_window(now, WEEK) == Decimal("50.00")


def test_run_approval_counts_as_familiar():
    s = snapshot(history=[rec(mid="ME0001")], prior=[
        PriorPurchase(purchase("A1", "2026-08-10T09:00:00Z", "10.00", mid="ME0001"), "approved"),
        PriorPurchase(purchase("A2", "2026-08-10T10:00:00Z", "10.00", mid="ME0002"), "approved"),
        PriorPurchase(purchase("A3", "2026-08-10T11:00:00Z", "10.00", mid="ME0003"), "waiting"),
    ])
    assert s.familiarity("ME0001") == 2  # 1 in history + 1 earlier in this run (DEC-015)
    assert s.familiarity("ME0002") == 1
    assert s.familiarity("ME0003") == 0  # waiting is not an approval
    assert s.familiarity("ME9999") == 0


def test_familiarity_counts_approved_purchases_only():
    history = [rec(), rec(), rec(ttype="refund"), rec(ttype="cash_withdrawal"), rec(status="declined")]
    assert HistoryBaseline.from_records(history).purchases_at("ME0001") == 2


def test_known_devices_and_countries_include_run_approvals():
    s = snapshot(history=[rec(device="DVC-A", country="CH"), rec(status="declined", device="DVC-X", country="GB"),
                          rec(device=None, country="IT")],
                 prior=[PriorPurchase(purchase("A1", "2026-08-10T09:00:00Z", "10.00", device="DVC-B", country="DE"), "approved"),
                        PriorPurchase(purchase("A2", "2026-08-10T09:05:00Z", "10.00", device="DVC-C", country="FR"), "waiting")])
    assert s.known_device("DVC-A") and s.known_device("DVC-B")
    assert not s.known_device("DVC-X")  # only seen on a declined row
    assert not s.known_device("DVC-C")  # only on a waiting purchase
    assert not s.known_device(None)
    assert s.known_country("CH") and s.known_country("IT") and s.known_country("DE")
    assert not s.known_country("GB") and not s.known_country("FR")


def test_recent_at_merchant_returns_approved_and_waiting_orders():
    now = SimTime.parse("2026-08-13T17:30:00Z")
    s = snapshot(prior=[
        PriorPurchase(purchase("A1", "2026-08-13T17:20:00Z", "70.00"), "approved"),
        PriorPurchase(purchase("A2", "2026-08-13T17:26:00Z", "65.00"), "waiting"),
        PriorPurchase(purchase("A3", "2026-08-13T17:27:00Z", "65.00"), "declined"),
        PriorPurchase(purchase("A4", "2026-08-13T17:28:00Z", "65.00", mid="ME0002"), "approved"),
        PriorPurchase(purchase("A5", "2026-08-12T17:28:00Z", "65.00"), "approved"),
    ])
    assert [p.purchase.authorization_id for p in s.recent_at_merchant("ME0001", now, timedelta(hours=24))] == ["A1", "A2"]


def test_carries_the_platform_counter():
    assert snapshot(platform=money("234.50")).platform_period_spend_chf == Decimal("234.50")
    assert snapshot().platform_period_spend_chf is None


def test_rejects_unknown_states_and_other_cards():
    with pytest.raises(ValueError):
        PriorPurchase(purchase("A1", "2026-08-10T09:00:00Z", "10.00"), "pending")  # type: ignore[arg-type]
    other = purchase("B1", "2026-08-10T09:00:00Z", "10.00")
    other = type(other)(**{**other.__dict__, "card_id": "CA0002"})
    with pytest.raises(ValueError, match="card"):
        snapshot(prior=[PriorPurchase(other, "approved")])
