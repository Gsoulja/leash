"""Pins the behaviours agreed in CLAUDE.md across the 45 pack purchases (LEASH-033).

Not an answer key: only the behaviours we decided on are asserted. Each scenario is replayed in its pack
order through decide() with an in-memory ledger (application/replay.py) and the hand-compiled mandates.
Where the pack has no purchase for a rule family (fulfilment, quantity), one real pack purchase is replayed
with only that one field changed. Scenario IDs appear only in tests.
"""

import dataclasses
from pathlib import Path

import pytest

from fixtures.mandates import MANDATES
from leash.adapters.pack.loader import Pack
from leash.adapters.regex_reader import RegexReader
from leash.application.replay import replay
from leash.domain.decide import decide
from leash.domain.snapshot import Snapshot

DATA = Path(__file__).resolve().parents[4] / "data"


@pytest.fixture(scope="module")
def pack():
    return Pack(DATA)


@pytest.fixture(scope="module")
def runs(pack):
    return {s: {r.authorization_id: r for r in replay(pack, s, MANDATES[s])} for s in MANDATES}


class _Budget:
    def remaining_seconds(self):
        return 1.0


def alone(pack, purchase, scenario):
    """One purchase decided on its own, against the card's history and the scenario's mandate."""
    snap = Snapshot(card_id=purchase.card_id, baseline=pack.baseline(purchase.card_id), prior=(),
                    platform_period_spend_chf=None,
                    merchant_names={mid: m.name for mid, m in pack.merchants().items()})
    return decide(purchase, MANDATES[scenario], snap, RegexReader().read(purchase, _Budget()))


def test_scen0000_chf_20_exactly_is_approved(runs):
    row = runs["SCEN0000"]["AU0001"]
    assert (str(row.chf), row.verdict) == ("20.00", "approve")


def test_scen0001_total_reaching_300_is_approved_and_the_next_order_over_300_declined(runs):
    s1 = runs["SCEN0001"]
    assert s1["AU0008"].verdict == "approve"  # 44.50 + 120.00 + 70.00 + 65.50 = 300.00 in the window
    assert s1["AU0009"].verdict == "decline" and "over_period_limit" in s1["AU0009"].reasons


def test_usd_450_converted_to_chf_391_50_is_not_declined_for_price(runs, pack):
    p = pack.attempt("AU0038").purchase
    assert (p.currency, str(p.amount), str(p.billing_amount_chf)) == ("USD", "450.00", "391.50")
    row = runs["SCEN0004"]["AU0038"]
    assert "over_order_limit" not in row.reasons and row.verdict != "decline"


def test_injection_text_never_raises_a_limit(runs):
    row = runs["SCEN0004"]["AU0037"]
    assert row.verdict == "decline"
    assert {"over_order_limit", "instruction_in_shop_text"} <= set(row.reasons)


def test_lookalike_shop_is_declined_with_lookalike_evidence(runs):
    row = runs["SCEN0004"]["AU0039"]
    assert row.verdict == "decline" and "lookalike_merchant" in row.reasons


def test_unfamiliar_shop_under_a_used_before_rule_is_declined(runs):  # DEC-023
    for scenario, aid in (("SCEN0003", "AU0027"), ("SCEN0004", "AU0044")):
        row = runs[scenario][aid]
        assert row.verdict == "decline" and "unfamiliar_merchant" in row.reasons


def test_duplicate_goes_to_step_up(runs):
    row = runs["SCEN0004"]["AU0036"]
    assert row.verdict == "step_up" and "possible_duplicate" in row.reasons


def test_split_order_and_already_bought_go_to_step_up_not_decline(runs):  # DEC-023
    assert runs["SCEN0001"]["AU0006"].verdict == "step_up" and "possible_split" in runs["SCEN0001"]["AU0006"].reasons
    already = [r for r in runs["SCEN0004"].values() if r.reasons == ("already_purchased",)]
    assert already and all(r.verdict == "step_up" for r in already)


@pytest.mark.parametrize("scenario, aid, verdict, reason", [
    ("SCEN0001", "AU0004", "decline", "over_order_limit"),         # price
    ("SCEN0001", "AU0009", "decline", "over_period_limit"),        # period
    ("SCEN0002", "AU0022", "decline", "merchant_category"),        # shop type
    ("SCEN0003", "AU0027", "decline", "unfamiliar_merchant"),      # familiarity
    ("SCEN0002", "AU0017", "decline", "item_mismatch"),            # basket: item
    ("SCEN0002", "AU0018", "decline", "unrequested_addon"),        # basket: add-on
    ("SCEN0001", "AU0007", "step_up", "outside_purpose"),          # basket: purpose
    ("SCEN0002", "AU0013", "decline", "size_mismatch"),            # size
    ("SCEN0002", "AU0015", "decline", "returns_too_short"),        # returns
    ("SCEN0004", "AU0040", "step_up", "instruction_in_shop_text"), # shop text
    ("SCEN0004", "AU0036", "step_up", "possible_duplicate"),       # duplicates
    ("SCEN0001", "AU0006", "step_up", "possible_split"),           # split
    ("SCEN0002", "AU0019", "step_up", "already_purchased"),        # single purchase
    ("SCEN0003", "AU0026", "step_up", "session_risk"),             # session
])
def test_every_rule_family_has_an_integrated_case(runs, scenario, aid, verdict, reason):
    row = runs[scenario][aid]
    assert row.verdict == verdict and reason in row.reasons


def test_fulfilment_integrated_case_a_pickup_order_fails_for_delivery(pack):
    p = dataclasses.replace(pack.attempt("AU0005").purchase, fulfillment="pickup")  # a real SCEN0001 order
    d = alone(pack, p, "SCEN0001")
    assert d.verdict == "decline" and "fulfilment_not_allowed" in d.reason_codes
    digital = pack.attempt("AU0043").purchase  # the pack's only digital order
    assert "fulfilment_not_allowed" in alone(pack, digital, "SCEN0001").reason_codes


def test_quantity_integrated_case_one_line_of_three_fails_one_item(pack):
    real = pack.attempt("AU0001").purchase  # SCEN0000: "one ordinary grocery item"
    triple = dataclasses.replace(real, items=(dataclasses.replace(real.items[0], quantity=3),))
    d = alone(pack, triple, "SCEN0000")
    assert d.verdict == "decline" and "quantity_exceeded" in d.reason_codes
    assert alone(pack, real, "SCEN0000").verdict == "approve"


def test_unsupported_rule_integrated_case_never_approves(pack):
    from decimal import Decimal

    from leash.domain.mandate import CompiledMandate, Rule

    base = MANDATES["SCEN0000"]
    odd = CompiledMandate(base.instruction, (*base.rules, Rule("leash.merchant.carbon_score.v1", "<=", Decimal("3"))),
                          "approve")
    p = pack.attempt("AU0001").purchase
    snap = Snapshot(card_id=p.card_id, baseline=pack.baseline(p.card_id), prior=(), platform_period_spend_chf=None)
    d = decide(p, odd, snap, RegexReader().read(p, _Budget()))
    assert d.verdict == "step_up" and "unsupported_mandate_rule" in d.reason_codes


def test_familiarity_counts_approved_purchases_only_on_the_real_history(pack):
    import csv
    from collections import Counter

    with (DATA / "authorization_history.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for card in sorted({pack.attempt(a).purchase.card_id for a in ("AU0001", "AU0024", "AU0035")}):
        approved = Counter(r["merchant_id"] for r in rows if r["card_id"] == card
                           and r["transaction_type"] == "purchase" and r["status"] == "approved")
        other = Counter(r["merchant_id"] for r in rows if r["card_id"] == card
                        and not (r["transaction_type"] == "purchase" and r["status"] == "approved"))
        baseline = pack.baseline(card)
        assert dict(baseline.merchant_purchases) == dict(approved)
        assert other, "the card's history also holds refunds, withdrawals or declines that must not count"
