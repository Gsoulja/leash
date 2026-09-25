"""Familiar shop: earlier approved purchases at this merchant ID on this card (history + this run).
Names never grant familiarity; a name close to a known shop is reported as a possible lookalike."""

from ..checks import Check
from ..facts import Facts
from ..mandate import CompiledMandate
from ..purchase import Purchase
from ..snapshot import Snapshot


def _norm(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def _distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _lookalike(name: str, snapshot: Snapshot, own_id: str) -> tuple[str, int] | None:
    target = _norm(name)
    for mid, count in sorted(snapshot.familiar_merchants().items()):
        known = snapshot.merchant_names.get(mid)
        if mid == own_id or not known:
            continue
        other = _norm(known)
        contained = min(len(target), len(other)) >= 5 and (target in other or other in target)
        if _distance(target, other) <= 2 or contained:
            return known, count
    return None


def _count_text(n: int) -> str:
    return "Never paid here" if n == 0 else f"{n} earlier payment{'s' if n != 1 else ''}"


def familiar_rule(purchase: Purchase, mandate: CompiledMandate, snapshot: Snapshot, facts: Facts) -> list[Check]:
    shop = purchase.merchant
    count = snapshot.familiarity(shop.merchant_id)
    need = mandate.familiar_min
    look = _lookalike(shop.name, snapshot, shop.merchant_id) if count == 0 else None
    look_text = (f" The name is almost identical to {look[0]} ({_count_text(look[1]).lower()}): "
                 "possibly a lookalike shop.") if look else ""
    if need > 0:
        agreed = "Paid there before" if need == 1 else f"Paid there at least {need} times"
        if count >= need:
            return [Check("known", "Known shop", "pass", agreed, _count_text(count),
                          f"{shop.name}: {_count_text(count).lower()} on this card.")]
        how = "before" if need == 1 else "regularly"
        if count == 0 and not snapshot.has_purchase_history():
            # Nothing is known about this card's shopping at all, so "new shop" is not established: it is
            # a missing fact, and missing facts follow the uncertainty policy rather than declining (DEC-046).
            return [Check("known", "Known shop", "warn", agreed, "No purchase history",
                          f"This card has no earlier payments on record, so I can't tell whether "
                          f"{shop.name} is one of your usual shops.{look_text}",
                          "merchant_history_unknown")]
        return [Check("known", "Known shop", "fail", agreed, _count_text(count),
                      f"You haven't paid {shop.name} {how} ({_count_text(count).lower()}).{look_text}",
                      "lookalike_merchant" if look else "unfamiliar_merchant")]
    if look:
        return [Check("known", "Known shop", "warn", "Any shop", _count_text(count), f"New shop.{look_text}",
                      "lookalike_merchant")]
    return [Check("known", "Known shop", "info", "Any shop", _count_text(count),
                  f"{shop.name}: {_count_text(count).lower()} on this card.")]
