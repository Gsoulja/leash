"""Per-order price limit: the purchase total in CHF (delivery included) against the strictest limit."""

from ..checks import Check
from ..facts import Facts
from ..mandate import CompiledMandate
from ..money import fmt_chf
from ..purchase import Purchase
from ..snapshot import Snapshot


def price_rule(purchase: Purchase, mandate: CompiledMandate, snapshot: Snapshot, facts: Facts) -> list[Check]:
    limit = mandate.max_per_order
    if limit is None:
        return []
    total = purchase.billing_amount_chf
    ok = total <= limit.value if limit.inclusive else total < limit.value
    agreed = f"{'≤' if limit.inclusive else '<'} {fmt_chf(limit.value)}"
    actual = fmt_chf(total)
    if purchase.currency != "CHF":
        actual = f"{purchase.currency} {purchase.amount:.2f} = {actual}"
    if ok:
        detail = f"{fmt_chf(total)} is within your {fmt_chf(limit.value)} per-order limit."
    elif total == limit.value:
        detail = f"{fmt_chf(total)} is not below your limit: orders must stay under {fmt_chf(limit.value)}."
    else:
        detail = f"{fmt_chf(total)} is over your {fmt_chf(limit.value)} per-order limit."
    return [Check("price", "Price", "pass" if ok else "fail", agreed, actual, detail,
                  None if ok else "over_order_limit")]
