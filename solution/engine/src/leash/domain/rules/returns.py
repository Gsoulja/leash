"""Return window against the minimum days. The stricter of the order's structured term and the shop's
text wins; not stated (or unknown / not applicable) is missing and follows the uncertainty policy."""

from ..checks import Check
from ..facts import Facts
from ..mandate import CompiledMandate
from ..purchase import Purchase, Term
from ..snapshot import Snapshot


def returns_rule(purchase: Purchase, mandate: CompiledMandate, snapshot: Snapshot, facts: Facts) -> list[Check]:
    minimum = mandate.min_return_days
    if minimum is None:
        return []
    agreed = f"≥ {minimum} days"
    if purchase.order_returnable is Term.FALSE or facts.final_sale is True:
        return [Check("returns", "Returns", "fail", agreed, "Final sale",
                      "This order can't be returned (final sale).", "final_sale")]
    if facts.return_days is None or purchase.order_returnable is not Term.TRUE:
        return [Check("returns", "Returns", "warn", agreed, "Not stated",
                      "The shop doesn't state a return window.", "returns_unknown")]
    if facts.return_days < minimum:
        return [Check("returns", "Returns", "fail", agreed, f"{facts.return_days} days",
                      f"Only {facts.return_days}-day returns; you asked for at least {minimum} days.", "returns_too_short")]
    return [Check("returns", "Returns", "pass", agreed, f"{facts.return_days} days",
                  f"Returns accepted within {facts.return_days} days.")]
