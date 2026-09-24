"""Small builders for test data. Override only what a test is about."""

from decimal import Decimal
from typing import Any

from leash.domain import mandate as m
from leash.domain.clock import SimTime
from leash.domain.facts import Facts
from leash.domain.mandate import CompiledMandate, Rule
from leash.domain.money import money
from leash.domain.purchase import LineItem, Merchant, Purchase, Term
from leash.domain.snapshot import HistoryBaseline, PriorPurchase, Snapshot


def merchant(**kw: Any) -> Merchant:
    base: dict[str, Any] = dict(merchant_id="ME0001", name="Alpine Basket", category="groceries", mcc="5411",
                                country="CH", city="Zurich", availability="store_and_online", recurring_capable=False)
    return Merchant(**{**base, **kw})


def line(item_id: str = "IT0001", quantity: int = 1, **kw: Any) -> LineItem:
    base: dict[str, Any] = dict(line_no=1, item_id=item_id, name="Fresh produce selection", category="groceries",
                                quantity=quantity, unit_price=money("13.00"), currency="CHF",
                                details="One small basket of seasonal fruit and vegetables")
    return LineItem(**{**base, **kw})


def purchase(chf: str = "20.00", **kw: Any) -> Purchase:
    base: dict[str, Any] = dict(
        authorization_id="AZ-0001", source_authorization_id="AU0001", card_id="CA0001", merchant=merchant(),
        sim_time=SimTime.parse("2026-08-09T10:04:00Z"), amount=money(chf), currency="CHF",
        billing_amount_chf=money(chf), items_subtotal=money(chf), delivery_fee=money("0.00"), channel="ecommerce",
        device_id="DVC-13A598", recent_attempts_10m=0, fulfillment="delivery", delivery_by=None,
        order_returnable=Term.FALSE, order_cancellable=Term.UNKNOWN, related_authorization_id=None,
        related_status=None, description="Grocery delivery order", items=(line(),),
    )
    return Purchase(**{**base, **kw})


def mandate(*rules: Rule, uncertainty: str = "ask", instruction: str = "test") -> CompiledMandate:
    return CompiledMandate(instruction=instruction, rules=tuple(rules), uncertainty=uncertainty)  # type: ignore[arg-type]


def max_per_order(chf: str) -> Rule:
    return Rule(m.F_BILLING_CHF, "<=", Decimal(chf), currency="CHF", scope="purchase")


def snapshot(*prior: PriorPurchase, card_id: str = "CA0001", baseline: HistoryBaseline | None = None,
             platform: Decimal | None = None, merchant_names: dict[str, str] | None = None) -> Snapshot:
    return Snapshot(card_id=card_id, baseline=baseline or HistoryBaseline(), prior=tuple(prior),
                    platform_period_spend_chf=platform, merchant_names=merchant_names or {})


def facts(**kw: Any) -> Facts:
    base: dict[str, Any] = dict(reader="regex", sizes=None, return_days=None, final_sale=None, injection_excerpt=None)
    return Facts(**{**base, **kw})
