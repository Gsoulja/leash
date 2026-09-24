"""The customer's answer to an ask, and the ask timeout (LEASH-045, DEC-012, DEC-016).

An approval re-checks the hard rules under the card lock with a fresh snapshot: if a limit now fails,
nothing changes and the explanation says why, so only Reject remains and what is sent through /resolve
stays truthful. Each accepted answer writes a /resolve outbox row. An ask past its own stored expiry
(set from the bootstrap window when it was asked) becomes timed_out and never counts as spend. The
timeout treatment is an assumption until LEASH-110.
"""

from datetime import datetime
from typing import Any, Literal, Protocol

from leash.adapters.postgres.unit_of_work import ResolveOutcome
from leash.domain.decide import Decision, decide
from leash.domain.explain import explain
from leash.domain.facts import Facts
from leash.domain.mandate import CompiledMandate
from leash.domain.purchase import Purchase
from leash.domain.snapshot import Snapshot

Answer = Literal["approve", "decline"]
_MESSAGES = {"approve": "The customer confirmed this purchase.", "decline": "The customer rejected this purchase."}


class MandateSource(Protocol):
    def for_run(self, run_id: str | None) -> CompiledMandate:
        """The compiled mandate snapshot the run's decisions used (DEC-003)."""
        ...


class ResolutionStore(Protocol):
    async def resolve(self, authorization_id: str, answer: str, *, now: datetime, recheck: Any,
                      body: Any) -> ResolveOutcome: ...

    async def sweep(self, now: datetime) -> list[str]: ...


class ResolveAsk:
    def __init__(self, store: ResolutionStore, mandates: MandateSource, *, engine_version: str) -> None:
        self._store, self._mandates, self._engine_version = store, mandates, engine_version

    async def answer(self, authorization_id: str, answer: Answer, *, now: datetime) -> ResolveOutcome:
        if answer not in _MESSAGES:
            raise ValueError(f"answer must be approve or decline, not {answer!r}")

        def recheck(purchase: Purchase, run_id: str | None, snapshot: Snapshot) -> Decision:
            # Facts are not re-read: the customer resolved the uncertainty; only hard rules can block now.
            return decide(purchase, self._mandates.for_run(run_id), snapshot, Facts.not_stated("recheck"))

        def body(given: str, decision: Decision | None) -> dict[str, Any]:
            evidence = explain(decision, authorization_id=authorization_id,
                               engine_version=self._engine_version)["evidence"] if decision else []
            return {"decision": given, "customer_message": _MESSAGES[given], "evidence": evidence}

        return await self._store.resolve(authorization_id, answer, now=now, recheck=recheck, body=body)


class Sweeper:
    def __init__(self, store: ResolutionStore) -> None:
        self._store = store

    async def run_once(self, *, now: datetime) -> list[str]:
        return await self._store.sweep(now)
