"""What the engine knows about the past when it decides one purchase.

Repositories build a Snapshot; the pure core only reads it. It combines the card's history
(approved purchases only, DEC-011) with this run's earlier purchases and their final states.
Only final approvals count as spend or familiarity (DEC-010, DEC-015); a waiting purchase is paused.
"""

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import Literal, get_args

from .clock import SimTime
from .purchase import Purchase

FinalState = Literal["approved", "waiting", "declined", "timed_out"]


@dataclass(frozen=True)
class HistoryRecord:
    """One row of the card's authorization history, reduced to what familiarity needs."""

    transaction_type: str  # purchase | refund | cash_withdrawal
    status: str  # approved | declined
    merchant_id: str | None
    device_id: str | None
    merchant_country: str | None


@dataclass(frozen=True)
class HistoryBaseline:
    """Familiarity from history: approved purchases only, never refunds, withdrawals or declines."""

    merchant_purchases: Mapping[str, int] = field(default_factory=lambda: MappingProxyType({}))
    devices: frozenset[str] = frozenset()
    countries: frozenset[str] = frozenset()

    @classmethod
    def from_records(cls, records: Iterable[HistoryRecord]) -> "HistoryBaseline":
        purchases = [r for r in records if r.transaction_type == "purchase" and r.status == "approved"]
        per_merchant = Counter(r.merchant_id for r in purchases if r.merchant_id)
        return cls(
            merchant_purchases=MappingProxyType(dict(per_merchant)),
            devices=frozenset(r.device_id for r in purchases if r.device_id),
            countries=frozenset(r.merchant_country for r in purchases if r.merchant_country),
        )

    def purchases_at(self, merchant_id: str) -> int:
        return self.merchant_purchases.get(merchant_id, 0)


@dataclass(frozen=True)
class PriorPurchase:
    purchase: Purchase
    state: FinalState

    def __post_init__(self) -> None:
        if self.state not in get_args(FinalState):
            raise ValueError(f"unknown final state {self.state!r}")


@dataclass(frozen=True)
class Snapshot:
    card_id: str
    baseline: HistoryBaseline
    prior: tuple[PriorPurchase, ...]  # earlier purchases in this run, in delivery order
    platform_period_spend_chf: Decimal | None  # the event's context.approved_spend_in_period_chf (DEC-010)
    merchant_names: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))  # id → name, for lookalikes

    def __post_init__(self) -> None:
        for p in self.prior:
            if p.purchase.card_id != self.card_id:
                raise ValueError(f"prior purchase {p.purchase.authorization_id} is for another card")

    def _approved(self) -> list[Purchase]:
        return [p.purchase for p in self.prior if p.state == "approved"]

    def approved_spend_in_window(self, now: SimTime, window: timedelta) -> Decimal:
        """Final approvals whose simulated time falls in the trailing window (now - window, now]."""
        return sum((p.billing_amount_chf for p in self._approved() if now.within(p.sim_time, window)), Decimal("0.00"))

    def familiarity(self, merchant_id: str) -> int:
        """Approved purchases at this merchant: history plus earlier approvals in this run."""
        return self.baseline.purchases_at(merchant_id) + sum(
            1 for p in self._approved() if p.merchant.merchant_id == merchant_id)

    def known_device(self, device_id: str | None) -> bool:
        if device_id is None:
            return False
        return device_id in self.baseline.devices or any(p.device_id == device_id for p in self._approved())

    def known_country(self, country: str) -> bool:
        return country in self.baseline.countries or any(p.merchant.country == country for p in self._approved())

    def familiar_merchants(self) -> dict[str, int]:
        """merchant_id → approved purchases, for every merchant this card has used (history or this run)."""
        ids = set(self.baseline.merchant_purchases) | {p.merchant.merchant_id for p in self._approved()}
        return {mid: self.familiarity(mid) for mid in ids if self.familiarity(mid) > 0}

    def recent_at_merchant(self, merchant_id: str, now: SimTime, window: timedelta) -> list[PriorPurchase]:
        """Approved or waiting purchases at this merchant within the trailing window, oldest first."""
        return [p for p in self.prior
                if p.state in ("approved", "waiting") and p.purchase.merchant.merchant_id == merchant_id
                and now.within(p.purchase.sim_time, window)]
