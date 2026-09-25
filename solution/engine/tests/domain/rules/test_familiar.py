from decimal import Decimal
from types import MappingProxyType

from factories import facts, mandate, merchant, purchase, snapshot
from leash.domain import mandate as m
from leash.domain.mandate import Rule
from leash.domain.rules.familiar import familiar_rule
from leash.domain.snapshot import HistoryBaseline

KNOWN = HistoryBaseline(merchant_purchases=MappingProxyType({"ME0022": 6, "ME0024": 21}))
NAMES = {"ME0022": "PixelHarbor", "ME0024": "HarborByte", "ME0059": "PixelHarbour", "ME0023": "Circuit and Pine"}
USED_BEFORE = mandate(Rule(m.F_PRIOR_PURCHASES, ">=", Decimal("1")))


def at(mid, mm=USED_BEFORE, baseline=KNOWN):
    p = purchase(merchant=merchant(merchant_id=mid, name=NAMES[mid], category="electronics"))
    return familiar_rule(p, mm, snapshot(baseline=baseline, merchant_names=NAMES), facts())


def test_lookalike_shop_is_declined_with_evidence():
    [check] = at("ME0059")
    assert (check.status, check.reason_code) == ("fail", "lookalike_merchant")
    assert "PixelHarbor" in check.detail and "6 earlier payments" in check.detail


def test_plain_unfamiliar_shop_fails_without_lookalike():
    [check] = at("ME0023")
    assert (check.status, check.reason_code) == ("fail", "unfamiliar_merchant")
    assert check.actual == "Never paid here"


def test_familiar_shop_passes():
    [check] = at("ME0024")
    assert (check.status, check.actual) == ("pass", "21 earlier payments")


def test_name_similarity_never_grants_familiarity():
    # A shop named exactly like a known one, but with a different ID, is still unknown.
    names = {**NAMES, "ME9999": "PixelHarbor"}
    p = purchase(merchant=merchant(merchant_id="ME9999", name="PixelHarbor"))
    [check] = familiar_rule(p, USED_BEFORE, snapshot(baseline=KNOWN, merchant_names=names), facts())
    assert check.status == "fail"


def test_regularly_threshold():
    mm = mandate(Rule(m.F_PRIOR_PURCHASES, ">=", Decimal("3")))
    few = HistoryBaseline(merchant_purchases=MappingProxyType({"ME0022": 2}))
    [check] = at("ME0022", mm=mm, baseline=few)
    assert check.status == "fail" and check.agreed == "Paid there at least 3 times"


def test_without_a_familiarity_rule_lookalike_warns_and_new_shop_is_info():
    [look] = at("ME0059", mm=mandate())
    assert (look.status, look.reason_code) == ("warn", "lookalike_merchant")
    [new] = at("ME0023", mm=mandate())
    assert new.status == "info"


def test_a_card_with_no_purchase_history_asks_instead_of_declining():
    """No history at all is a missing fact, not proof the shop is new to the customer (DEC-046).

    The hosted pack's cards carry no history rows, so treating absence as established unfamiliarity
    declined every first purchase of every scenario that says "shops I use".
    """
    [check] = at("ME0023", baseline=HistoryBaseline())
    assert (check.status, check.reason_code) == ("warn", "merchant_history_unknown")
    assert "no earlier payments" in check.detail.lower()


def test_absence_is_still_unfamiliar_once_the_card_has_a_history():
    """A card that shops elsewhere says something: this shop really is not one of them."""
    [check] = at("ME0023")
    assert (check.status, check.reason_code) == ("fail", "unfamiliar_merchant")
