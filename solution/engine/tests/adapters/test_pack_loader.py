from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from leash.adapters.pack.loader import Pack
from leash.domain.clock import SimTime
from leash.domain.purchase import Term

DATA = Path(__file__).resolve().parents[4] / "data"


@pytest.fixture(scope="module")
def pack() -> Pack:
    return Pack(DATA)


def test_loads_45_attempts_with_items(pack):
    attempts = pack.attempts()
    assert len(attempts) == 45
    assert sum(len(a.purchase.items) for a in attempts) == 56
    for scenario in {a.scenario_id for a in attempts}:
        orders = [a.replay_order for a in attempts if a.scenario_id == scenario]
        assert orders == sorted(orders) == list(range(1, len(orders) + 1))
    assert [a.purchase.source_authorization_id for a in pack.attempts("SCEN0004")][:3] == ["AU0035", "AU0036", "AU0037"]


def test_familiarity_counts_approved_only(pack):
    assert pack.baseline("CA0039").purchases_at("ME0022") == 6
    # CA0011 has 23 approved rows at ME0028 (TrailSpark), one of which is a refund.
    assert pack.baseline("CA0011").purchases_at("ME0028") == 22
    assert pack.baseline("CA0039").purchases_at("ME0059") == 0  # the lookalike has no history


def test_history_distinguishes_transaction_types(pack):
    kinds = {(r.transaction_type, r.status) for r in pack.history("CA0011")}
    assert ("refund", "approved") in kinds and ("purchase", "approved") in kinds
    assert {r.transaction_type for r in pack.history()} == {"purchase", "refund", "cash_withdrawal"}
    assert {r.status for r in pack.history()} == {"approved", "declined"}


def test_empty_fields_become_none_amounts_decimal_times_simtime(pack):
    au0012 = pack.attempt("AU0012").purchase
    assert au0012.delivery_by is None and au0012.related_authorization_id is None and au0012.related_status is None
    assert isinstance(au0012.billing_amount_chf, Decimal) and au0012.billing_amount_chf == Decimal("165.00")
    assert isinstance(au0012.sim_time, SimTime) and au0012.sim_time == SimTime.parse("2026-08-11T10:15:00Z")
    au0001 = pack.attempt("AU0001").purchase
    assert au0001.delivery_by == date(2026, 8, 10)
    assert (au0001.order_returnable, au0001.order_cancellable) == (Term.FALSE, Term.UNKNOWN)
    au0042 = pack.attempt("AU0042").purchase
    assert (au0042.related_authorization_id, au0042.related_status) == ("AU0037", "declined")


def test_foreign_currency_keeps_row_currency_and_chf(pack):
    au0038 = pack.attempt("AU0038").purchase
    assert (au0038.amount, au0038.currency, au0038.billing_amount_chf) == (Decimal("450.00"), "USD", Decimal("391.50"))
    assert au0038.merchant.country == "US"


def test_joins_are_by_id_only(pack):
    # PixelHarbor (ME0022) and PixelHarbour (ME0059) have near-identical names; IDs keep them apart.
    lookalike = pack.attempt("AU0039").purchase.merchant
    assert (lookalike.merchant_id, lookalike.name) == ("ME0059", "PixelHarbour")
    assert pack.merchants()["ME0022"].name == "PixelHarbor"
    items = pack.attempt("AU0018").purchase.items
    assert [(i.line_no, i.item_id, i.category) for i in items] == [(1, "IT0014", "sporting_goods"), (2, "IT0066", "subscriptions")]


def test_merchant_fields_are_typed(pack):
    m = pack.merchants()["ME0017"]
    assert m.recurring_capable is True and m.mcc == "5815"
    assert pack.merchants()["ME0001"].recurring_capable is False
