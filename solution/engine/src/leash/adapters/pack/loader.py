"""Loads Viseca's synthetic challenge pack (data/*.csv) into domain objects.

Offline replay and the database seed use it. Joins are by ID only (names can be lookalikes), empty
CSV fields become None, amounts become Decimal and timestamps SimTime. The pack is read-only.
"""

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import cached_property
from pathlib import Path

from leash.domain.clock import SimTime
from leash.domain.money import money
from leash.domain.purchase import LineItem, Merchant, Purchase, Term
from leash.domain.snapshot import HistoryBaseline, HistoryRecord


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _opt(value: str) -> str | None:
    return value if value != "" else None


@dataclass(frozen=True)
class Attempt:
    scenario_id: str
    replay_order: int
    authority_id: str
    purchase: Purchase


@dataclass(frozen=True)
class CardHistoryRecord:
    card_id: str
    record: HistoryRecord


@dataclass(frozen=True)
class Customer:
    """The persona profile. Every text field is the customer's background, never an instruction."""

    customer_id: str
    persona_name: str
    home_region: str
    background: str
    shopping_preferences: str
    typical_spending: str
    budget_style: str
    travel_pattern: str


@dataclass(frozen=True)
class Account:
    account_id: str
    customer_id: str
    account_type: str
    account_purpose: str
    base_currency: str
    status: str


@dataclass(frozen=True)
class Card:
    card_id: str
    account_id: str
    card_type: str
    card_purpose: str
    status: str


@dataclass(frozen=True)
class Transaction:
    """One authorization_history row, with the fields a history summary needs (LEASH-154).

    HistoryRecord keeps only what familiarity reads; this keeps time, money and identity too.
    """

    authorization_id: str
    customer_id: str
    account_id: str
    card_id: str
    sim_time: SimTime
    transaction_type: str
    status: str
    amount: Decimal
    currency: str
    billing_amount_chf: Decimal
    merchant_id: str | None
    merchant_name: str | None
    merchant_category: str | None
    description: str


class Pack:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)

    @cached_property
    def _merchants(self) -> dict[str, Merchant]:
        return {
            r["merchant_id"]: Merchant(
                merchant_id=r["merchant_id"], name=r["merchant_name"], category=r["merchant_category"],
                mcc=r["merchant_mcc"], country=r["merchant_country"], city=r["merchant_city"],
                availability=r["availability"], recurring_capable=r["recurring_capable"] == "true",
            )
            for r in _rows(self.data_dir / "merchants.csv")
        }

    def merchants(self) -> dict[str, Merchant]:
        return dict(self._merchants)

    @property
    def dataset(self) -> str:
        """Which customer population this pack is. Rows never cross between datasets."""
        return self.data_dir.name

    @cached_property
    def _customers(self) -> dict[str, Customer]:
        return {
            r["customer_id"]: Customer(
                customer_id=r["customer_id"], persona_name=r["persona_name"], home_region=r["home_region"],
                background=r["background"], shopping_preferences=r["shopping_preferences"],
                typical_spending=r["typical_spending"], budget_style=r["budget_style"],
                travel_pattern=r["travel_pattern"])
            for r in _rows(self.data_dir / "customers.csv")
        }

    def customers(self) -> dict[str, Customer]:
        return dict(self._customers)

    @cached_property
    def _accounts(self) -> dict[str, Account]:
        return {
            r["account_id"]: Account(
                account_id=r["account_id"], customer_id=r["customer_id"], account_type=r["account_type"],
                account_purpose=r["account_purpose"], base_currency=r["base_currency"], status=r["status"])
            for r in _rows(self.data_dir / "accounts.csv")
        }

    def accounts(self) -> dict[str, Account]:
        return dict(self._accounts)

    @cached_property
    def _cards(self) -> dict[str, Card]:
        return {
            r["card_id"]: Card(card_id=r["card_id"], account_id=r["account_id"], card_type=r["card_type"],
                               card_purpose=r["card_purpose"], status=r["status"])
            for r in _rows(self.data_dir / "cards.csv")
        }

    def cards(self) -> dict[str, Card]:
        return dict(self._cards)

    @cached_property
    def _transactions(self) -> list[Transaction]:
        return [
            Transaction(
                authorization_id=r["authorization_id"], customer_id=r["customer_id"], account_id=r["account_id"],
                card_id=r["card_id"], sim_time=SimTime.parse(r["timestamp"]),
                transaction_type=r["transaction_type"], status=r["status"], amount=money(r["amount"]),
                currency=r["currency"], billing_amount_chf=money(r["billing_amount_chf"]),
                merchant_id=_opt(r["merchant_id"]), merchant_name=_opt(r["merchant_name"]),
                merchant_category=_opt(r["merchant_category"]), description=r["description"])
            for r in _rows(self.data_dir / "authorization_history.csv")
        ]

    def transactions(self, card_id: str | None = None, account_id: str | None = None,
                     customer_id: str | None = None) -> list[Transaction]:
        """History rows, filtered by ID only. A None filter is "any", never "someone else's"."""
        return [t for t in self._transactions
                if (card_id is None or t.card_id == card_id)
                and (account_id is None or t.account_id == account_id)
                and (customer_id is None or t.customer_id == customer_id)]

    @cached_property
    def _history(self) -> list[CardHistoryRecord]:
        return [
            CardHistoryRecord(r["card_id"], HistoryRecord(
                transaction_type=r["transaction_type"], status=r["status"], merchant_id=_opt(r["merchant_id"]),
                device_id=_opt(r["customer_device_id"]), merchant_country=_opt(r["merchant_country"])))
            for r in _rows(self.data_dir / "authorization_history.csv")
        ]

    def history(self, card_id: str | None = None) -> list[HistoryRecord]:
        return [h.record for h in self._history if card_id is None or h.card_id == card_id]

    def baseline(self, card_id: str) -> HistoryBaseline:
        return HistoryBaseline.from_records(self.history(card_id))

    @cached_property
    def _attempts(self) -> list[Attempt]:
        lines: dict[str, list[LineItem]] = defaultdict(list)
        for r in _rows(self.data_dir / "purchase_attempt_items.csv"):
            lines[r["authorization_id"]].append(LineItem(
                line_no=int(r["line_no"]), item_id=r["item_id"], name=r["item_name"], category=r["item_category"],
                quantity=int(r["quantity"]), unit_price=money(r["unit_price"]), currency=r["currency"],
                details=r["item_details"]))
        attempts = []
        for r in _rows(self.data_dir / "purchase_attempts.csv"):
            aid = r["authorization_id"]
            purchase = Purchase(
                authorization_id=aid, source_authorization_id=aid, card_id=r["card_id"],
                merchant=self._merchants[r["merchant_id"]], sim_time=SimTime.parse(r["timestamp"]),
                amount=money(r["amount"]), currency=r["currency"], billing_amount_chf=money(r["billing_amount_chf"]),
                items_subtotal=money(r["items_subtotal"]), delivery_fee=money(r["delivery_fee"]), channel=r["channel"],
                device_id=_opt(r["customer_device_id"]), recent_attempts_10m=int(r["recent_attempt_count_10m"]),
                fulfillment=r["fulfillment_method"],
                delivery_by=date.fromisoformat(r["delivery_by"]) if r["delivery_by"] else None,
                order_returnable=Term.parse(r["order_returnable"]), order_cancellable=Term.parse(r["order_cancellable"]),
                related_authorization_id=_opt(r["related_authorization_id"]),
                related_status=_opt(r["related_authorization_status"]), description=r["purchase_description"],
                items=tuple(sorted(lines[aid], key=lambda i: i.line_no)),
            )
            attempts.append(Attempt(r["scenario_id"], int(r["replay_order"]), r["authority_id"], purchase))
        return sorted(attempts, key=lambda a: (a.scenario_id, a.replay_order))

    def attempts(self, scenario_id: str | None = None) -> list[Attempt]:
        return [a for a in self._attempts if scenario_id is None or a.scenario_id == scenario_id]

    def attempt(self, authorization_id: str) -> Attempt:
        for a in self._attempts:
            if a.purchase.authorization_id == authorization_id:
                return a
        raise KeyError(authorization_id)
