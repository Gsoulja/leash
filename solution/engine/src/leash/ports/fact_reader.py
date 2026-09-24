"""Port for anything that reads facts from merchant text (regex, Laya, …)."""

from typing import Protocol, runtime_checkable

from leash.domain.facts import Facts
from leash.domain.purchase import Purchase


@runtime_checkable
class Budget(Protocol):
    """Time left before the decision deadline (real clock)."""

    def remaining_seconds(self) -> float: ...


@runtime_checkable
class FactReader(Protocol):
    def read(self, purchase: Purchase, budget: Budget) -> Facts: ...
