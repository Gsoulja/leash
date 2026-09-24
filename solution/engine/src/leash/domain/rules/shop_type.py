"""Shop type: the merchant's category against the allowed (and excluded) shop types."""

from ..checks import Check
from ..facts import Facts
from ..mandate import CompiledMandate
from ..purchase import Purchase
from ..snapshot import Snapshot


def _words(category: str) -> str:
    return category.replace("_", " ")


def shop_type_rule(purchase: Purchase, mandate: CompiledMandate, snapshot: Snapshot, facts: Facts) -> list[Check]:
    allowed, excluded = mandate.merchant_categories, mandate.excluded_merchant_categories
    if allowed is None and not excluded:
        return []
    shop = purchase.merchant
    wanted = " or ".join(_words(c) for c in sorted(allowed)) if allowed is not None else ""
    agreed = f"{wanted} shop" if allowed is not None else "not " + ", ".join(_words(c) for c in sorted(excluded))
    actual = f"{shop.name}: {_words(shop.category)}"
    if allowed is not None and shop.category not in allowed:
        return [Check("shoptype", "Shop type", "fail", agreed, actual,
                      f"{shop.name} is a {_words(shop.category)} shop, not a {wanted} shop.", "merchant_category")]
    if shop.category in excluded:
        return [Check("shoptype", "Shop type", "fail", agreed, actual,
                      f"{shop.name} is a {_words(shop.category)} shop, which you excluded.", "merchant_category")]
    return [Check("shoptype", "Shop type", "pass", agreed, actual, f"{shop.name} is a {_words(shop.category)} shop.")]
