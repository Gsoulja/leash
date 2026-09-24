"""Explicit state machines. Anything not in a table is an IllegalTransition.

Purchase: received → approved | declined | waiting (by the engine); waiting → approved | declined (by
the customer) or timed_out (by the platform). A purchase the platform rejects before it reaches the
engine starts and ends as not_sent. Mandate: draft → active (customer confirms) → revoked (customer) or
expired (platform). The engine never ends a wait and never activates or revokes a mandate.
"""

from typing import Literal

PurchaseState = Literal["received", "approved", "declined", "waiting", "timed_out", "not_sent"]
MandateState = Literal["draft", "active", "revoked", "expired"]
Actor = Literal["engine", "customer", "platform"]

#: Whether our answer reached the platform (LEASH-130). Deliberately not part of `PurchaseState`: the
#: engine's verdict and the platform's acceptance are two different facts, and collapsing them is how a
#: decision nobody accepted gets counted as spent.
DeliveryState = Literal["pending", "accepted", "refused"]


class IllegalTransition(ValueError):
    """The requested state change is not allowed, or not allowed for this actor."""


_PURCHASE: dict[tuple[str | None, str], frozenset[str]] = {
    (None, "received"): frozenset({"engine"}),
    (None, "not_sent"): frozenset({"platform"}),
    ("received", "approved"): frozenset({"engine"}),
    ("received", "declined"): frozenset({"engine"}),
    ("received", "waiting"): frozenset({"engine"}),
    ("waiting", "approved"): frozenset({"customer"}),
    ("waiting", "declined"): frozenset({"customer"}),
    ("waiting", "timed_out"): frozenset({"platform"}),
    # The platform terminally refused our answer (LEASH-130). The decision happened, but nothing was
    # accepted, so the purchase ends non-approved and stops counting toward anything.
    ("approved", "not_sent"): frozenset({"platform"}),
    ("declined", "not_sent"): frozenset({"platform"}),
    ("waiting", "not_sent"): frozenset({"platform"}),
    ("received", "not_sent"): frozenset({"platform"}),
}

#: pending → accepted or refused, once. A delivery outcome is never revised: a second, different answer
#: from the platform is a disagreement to reconcile (LEASH-130), not a state change to apply.
_DELIVERY: dict[tuple[str | None, str], frozenset[str]] = {
    (None, "pending"): frozenset({"engine"}),
    ("pending", "accepted"): frozenset({"platform"}),
    ("pending", "refused"): frozenset({"platform"}),
}

_MANDATE: dict[tuple[str | None, str], frozenset[str]] = {
    (None, "draft"): frozenset({"customer"}),
    ("draft", "active"): frozenset({"customer"}),
    ("active", "revoked"): frozenset({"customer"}),
    ("active", "expired"): frozenset({"platform"}),
}


def _check(table: dict[tuple[str | None, str], frozenset[str]], kind: str, current: str | None, target: str,
           by: str) -> None:
    actors = table.get((current, target))
    if actors is None:
        raise IllegalTransition(f"{kind} can't go from {current or 'nothing'} to {target}")
    if by not in actors:
        raise IllegalTransition(f"{kind} {current or 'new'} → {target} must be done by {' or '.join(sorted(actors))}, not {by}")


def purchase_transition(current: PurchaseState | None, target: PurchaseState, by: Actor) -> PurchaseState:
    _check(_PURCHASE, "purchase", current, target, by)
    return target


def delivery_transition(current: DeliveryState | None, target: DeliveryState, by: Actor) -> DeliveryState:
    _check(_DELIVERY, "delivery", current, target, by)
    return target


def mandate_transition(current: MandateState | None, target: MandateState, by: Actor) -> MandateState:
    _check(_MANDATE, "mandate", current, target, by)
    return target
