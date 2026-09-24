"""Duplicate and split orders (DEC-023): both ask the customer, never decline on their own.

A duplicate is the same merchant, same items and quantities, and the same total as an approved or
waiting order within 24 h. A possible split is a second order at the same merchant within an hour that,
together with the earlier one, exceeds the per-order limit (only when the mandate turns the check on).
"""

from datetime import timedelta

from ..checks import Check
from ..facts import Facts
from ..mandate import CompiledMandate
from ..money import fmt_chf
from ..purchase import Purchase
from ..snapshot import PriorPurchase, Snapshot

DUPLICATE_WINDOW = timedelta(hours=24)
SPLIT_WINDOW = timedelta(hours=1)


def _hhmm(p: Purchase) -> str:
    return p.sim_time.local().strftime("%H:%M")


def _declined_requote_of(purchase: Purchase, earlier: Purchase) -> bool:
    return purchase.related_status == "declined" and purchase.related_authorization_id is not None and \
        purchase.related_authorization_id in (earlier.authorization_id, earlier.source_authorization_id)


def _candidates(purchase: Purchase, snapshot: Snapshot, window: timedelta) -> list[PriorPurchase]:
    return [p for p in snapshot.recent_at_merchant(purchase.merchant.merchant_id, purchase.sim_time, window)
            if p.purchase.authorization_id != purchase.authorization_id
            and not _declined_requote_of(purchase, p.purchase)]


def duplicates_rule(purchase: Purchase, mandate: CompiledMandate, snapshot: Snapshot, facts: Facts) -> list[Check]:
    for p in _candidates(purchase, snapshot, DUPLICATE_WINDOW):
        earlier = p.purchase
        if earlier.item_fingerprint == purchase.item_fingerprint and \
                earlier.billing_amount_chf == purchase.billing_amount_chf:
            return [Check("duplicate", "Repeat order", "warn", "Each order once",
                          f"Same as the {_hhmm(earlier)} order ({p.state})",
                          f"This is the same order as the one at {_hhmm(earlier)} "
                          f"({fmt_chf(earlier.billing_amount_chf)}, {p.state}).", "possible_duplicate")]
    limit = mandate.max_per_order
    if not mandate.split_check or limit is None:
        return []
    for p in _candidates(purchase, snapshot, SPLIT_WINDOW):
        total = p.purchase.billing_amount_chf + purchase.billing_amount_chf
        if total > limit.value or (not limit.inclusive and total == limit.value):
            earlier = p.purchase
            return [Check("split", "Split order", "warn", f"One order up to {fmt_chf(limit.value)}",
                          f"{fmt_chf(earlier.billing_amount_chf)} at {_hhmm(earlier)} + "
                          f"{fmt_chf(purchase.billing_amount_chf)} = {fmt_chf(total)}",
                          f"Together with the {_hhmm(earlier)} order at {purchase.merchant.name} this makes "
                          f"{fmt_chf(total)}, over your {fmt_chf(limit.value)} per-order limit: "
                          "possibly one order split in two.", "possible_split")]
    return []
