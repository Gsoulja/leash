"""Port for durable decision state. The Postgres adapter implements it; the application service only
talks to this interface."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from leash.domain.decide import Decision
from leash.domain.purchase import Purchase
from leash.domain.snapshot import Snapshot
from leash.domain.states import Actor, PurchaseState


@dataclass(frozen=True)
class SavedAuthorization:
    """What is already stored for a live authorization ID (repeat delivery)."""

    authorization_id: str
    state: PurchaseState
    engine_verdict: str | None  # None while the first delivery is still being decided
    response: Mapping[str, Any] | None  # the decision body that was (or will be) sent
    #: How this delivery's terms differ from the ones the saved decision was made on (LEASH-102). A
    #: redelivery carrying a different amount, shop or basket is a new attempt, not a retry, so the
    #: saved verdict must not be handed back as though it had covered these terms.
    changed_terms: tuple[str, ...] = ()


@runtime_checkable
class Repository(Protocol):
    async def receive(self, purchase: Purchase, *, run_id: str | None, event: Mapping[str, Any],
                      received_at: datetime, deadline_at: datetime) -> SavedAuthorization | None:
        """Store a newly received purchase. Returns None when new, or what is saved for a repeat delivery."""

    async def snapshot(self, card_id: str, *, run_id: str | None,
                       platform_period_spend_chf: Decimal | None) -> Snapshot:
        """History baseline plus this run's decided purchases for the card, for the pure core."""

    async def record_decision(self, authorization_id: str, decision: Decision, *, response: Mapping[str, Any],
                              ask_expires_at: datetime | None = None) -> None:
        """Save the engine's decision (received → approved | declined | waiting); illegal changes raise."""

    async def transition(self, authorization_id: str, target: PurchaseState, *, by: Actor,
                         payload: Mapping[str, Any] | None = None) -> None:
        """A later change by the customer or the platform (e.g. waiting → approved); illegal changes raise."""

    async def reconcile(self, purchase: Purchase, snapshot: Snapshot, context: Mapping[str, Any], *,
                        period: timedelta | None) -> list[str]:
        """Compare our records with the event's context; each mismatch is returned and logged as an alert."""
