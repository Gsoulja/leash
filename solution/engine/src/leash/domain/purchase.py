"""Our model of a proposed purchase, independent of the Viseca event format.

Translation from the API's JSON (string tri-states, nulls, live vs source IDs) happens in the
anti-corruption layer. Here every fact is typed, and a missing fact stays missing.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from .clock import SimTime

RELATED_STATUSES = frozenset({"pending", "approved", "declined", "cancelled"})


class Term(Enum):
    """An order term such as `order_returnable`. `UNKNOWN` means not supplied and is never a yes."""

    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"

    @classmethod
    def parse(cls, value: str) -> "Term":
        try:
            return cls(value)
        except ValueError:
            raise ValueError(f"not an order term: {value!r}") from None

    @property
    def is_true(self) -> bool:
        return self is Term.TRUE

    def __bool__(self) -> bool:
        raise TypeError("compare a Term explicitly (e.g. `term is Term.TRUE`); unknown must never read as permission")


def _require_decimal(**values: object) -> None:
    for name, value in values.items():
        if not isinstance(value, Decimal):
            raise TypeError(f"{name} must be a Decimal, got {type(value).__name__}")


@dataclass(frozen=True)
class Merchant:
    merchant_id: str
    name: str
    category: str
    mcc: str
    country: str
    city: str
    availability: str
    recurring_capable: bool


@dataclass(frozen=True)
class LineItem:
    line_no: int
    item_id: str
    name: str
    category: str
    quantity: int
    unit_price: Decimal
    currency: str
    details: str  # merchant-supplied text: untrusted data, never instructions

    def __post_init__(self) -> None:
        if self.quantity < 1:
            raise ValueError(f"line {self.line_no}: quantity must be at least 1")
        _require_decimal(unit_price=self.unit_price)


@dataclass(frozen=True)
class Purchase:
    authorization_id: str  # live ID: idempotency key, changes between runs
    source_authorization_id: str | None  # the AU... row in the challenge pack
    card_id: str
    merchant: Merchant
    sim_time: SimTime
    amount: Decimal  # in `currency`, delivery included
    currency: str
    billing_amount_chf: Decimal  # the same total in CHF
    items_subtotal: Decimal
    delivery_fee: Decimal
    channel: str
    device_id: str | None
    recent_attempts_10m: int
    fulfillment: str
    delivery_by: date | None
    order_returnable: Term
    order_cancellable: Term
    related_authorization_id: str | None
    related_status: str | None
    description: str
    items: tuple[LineItem, ...]

    def __post_init__(self) -> None:
        if not self.items:
            raise ValueError("a purchase needs at least one line item")
        _require_decimal(amount=self.amount, billing_amount_chf=self.billing_amount_chf,
                         items_subtotal=self.items_subtotal, delivery_fee=self.delivery_fee)
        if not isinstance(self.sim_time, SimTime):
            raise TypeError("sim_time must be a SimTime")
        for name in ("order_returnable", "order_cancellable"):
            if not isinstance(getattr(self, name), Term):
                raise TypeError(f"{name} must be a Term")
        if self.related_status is not None and self.related_status not in RELATED_STATUSES:
            raise ValueError(f"related_status must be one of {sorted(RELATED_STATUSES)} or None")
        if self.recent_attempts_10m < 0:
            raise ValueError("recent attempts can't be negative")

    @property
    def item_fingerprint(self) -> tuple[tuple[str, int], ...]:
        """Sorted multiset of (item_id, quantity), one pair per line: independent of line order."""
        return tuple(sorted((item.item_id, item.quantity) for item in self.items))
