"""Loads Viseca's synthetic challenge pack (data/*.csv) into domain objects.

Offline replay and the database seed use it. Joins are by ID only (names can be lookalikes), empty
CSV fields become None, amounts become Decimal and timestamps SimTime. The pack is read-only.
"""

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
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
