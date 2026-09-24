"""Offline replay: runs a scenario's attempts in order through decide(), with an in-memory ledger.

The ledger stands in for the Postgres repository (LEASH-043) and keeps only what the engine reads back:
each earlier purchase in this run and its final state. Customer answers to a step_up can be scripted:
none (it stays waiting), approve all, decline all, or per authorization ID.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from leash.adapters.pack.loader import Pack
from leash.adapters.regex_reader import RegexReader
from leash.domain.decide import Decision, decide
from leash.domain.explain import explain
from leash.domain.facts import Facts
from leash.domain.mandate import CompiledMandate
from leash.domain.money import fmt_chf
from leash.domain.purchase import Purchase
from leash.domain.snapshot import FinalState, PriorPurchase, Snapshot
from leash.ports.fact_reader import FactReader
from leash.ports.repository import SavedAuthorization

Answer = Literal["approve", "decline"]
Answers = Literal["none", "approve", "decline"] | Mapping[str, Answer]


class _NoDeadline:
    def remaining_seconds(self) -> float:
        return 60.0


@dataclass
class Recorded:
    purchase: Purchase
    decision: Decision
    state: FinalState


class InMemoryLedger:
    def __init__(self) -> None:
        self.decisions: list[Recorded] = []

    def prior(self, card_id: str) -> tuple[PriorPurchase, ...]:
        return tuple(PriorPurchase(r.purchase, r.state) for r in self.decisions if r.purchase.card_id == card_id)

    def record(self, purchase: Purchase, decision: Decision, state: FinalState) -> None:
        self.decisions.append(Recorded(purchase, decision, state))


@dataclass
class _Outcome:
    decision: Decision
    response: dict[str, Any]
    stages: list[tuple[str, float]] = field(default_factory=list)


_STATE: dict[str, FinalState] = {"approve": "approved", "decline": "declined", "step_up": "waiting"}


class InMemoryDecisionStore:
    """The DecisionStore port without Postgres, for offline runs of the worker's path (LEASH-121): the same
    snapshot as replay (pack history + this ledger), idempotent by live authorization ID."""

    def __init__(self, pack: Pack, ledger: InMemoryLedger | None = None, *, engine_version: str = "offline") -> None:
        self._pack, self._version = pack, engine_version
        self.ledger = ledger if ledger is not None else InMemoryLedger()
        self._names = {mid: m.name for mid, m in pack.merchants().items()}
        self._saved: dict[str, SavedAuthorization] = {}

    async def receive(self, purchase: Purchase, *, run_id: str | None, event: Mapping[str, Any],
                      received_at: datetime, deadline_at: datetime) -> SavedAuthorization | None:
        saved = self._saved.get(purchase.authorization_id)
        if saved is None:
            self._saved[purchase.authorization_id] = SavedAuthorization(purchase.authorization_id, "received", None,
                                                                         None)
        return saved

    async def decide(self, purchase: Purchase, *, run_id: str | None, mandate: CompiledMandate, facts: Facts,
                     platform_period_spend_chf: Decimal | None, ask_expires_at: datetime | None = None,
                     mandate_id: str | None = None) -> _Outcome:
        snapshot = Snapshot(card_id=purchase.card_id, baseline=self._pack.baseline(purchase.card_id),
                            prior=self.ledger.prior(purchase.card_id),
                            platform_period_spend_chf=platform_period_spend_chf, merchant_names=self._names)
        decision = decide(purchase, mandate, snapshot, facts)
        response = explain(decision, authorization_id=purchase.authorization_id, engine_version=self._version)
        self.ledger.record(purchase, decision, _STATE[decision.verdict])
        self._saved[purchase.authorization_id] = SavedAuthorization(
            purchase.authorization_id, _STATE[decision.verdict], decision.verdict, response)
        return _Outcome(decision, response)

    async def record_fallback(self, purchase: Purchase, *, run_id: str | None, response: Mapping[str, Any],
                              ask_expires_at: datetime) -> SavedAuthorization | None:
        saved = self._saved.get(purchase.authorization_id)
        if saved is not None and saved.engine_verdict is not None:
            return saved
        self._saved[purchase.authorization_id] = SavedAuthorization(purchase.authorization_id, "waiting", "step_up",
                                                                     response)
        return None

    async def mark_sent(self, authorization_id: str) -> None:
        return None

    async def refresh_claim(self, authorization_id: str) -> bool:
        return True  # one process, no other worker to take the work over

    async def release_claim(self, authorization_id: str) -> None:
        return None


@dataclass(frozen=True)
class ReplayRow:
    authorization_id: str
    shop: str
    chf: Decimal
    verdict: str
    reasons: tuple[str, ...]
    final_state: FinalState


def _answer(answers: Answers, authorization_id: str) -> Answer | None:
    if isinstance(answers, str):
        return None if answers == "none" else answers
    return answers.get(authorization_id)


def _final_state(decision: Decision, answer: Answer | None) -> FinalState:
    if decision.verdict == "approve":
        return "approved"
    if decision.verdict == "decline":
        return "declined"
    return "waiting" if answer is None else ("approved" if answer == "approve" else "declined")


def replay(pack: Pack, scenario_id: str, mandate: CompiledMandate, *, answers: Answers = "none",
           ledger: InMemoryLedger | None = None, reader: FactReader | None = None) -> list[ReplayRow]:
    attempts = pack.attempts(scenario_id)
    if not attempts:
        raise KeyError(scenario_id)
    ledger = ledger if ledger is not None else InMemoryLedger()
    reader = reader or RegexReader()
    names = {mid: m.name for mid, m in pack.merchants().items()}
    rows = []
    for attempt in attempts:
        purchase = attempt.purchase
        snapshot = Snapshot(card_id=purchase.card_id, baseline=pack.baseline(purchase.card_id),
                            prior=ledger.prior(purchase.card_id), platform_period_spend_chf=None,
                            merchant_names=names)
        decision = decide(purchase, mandate, snapshot, reader.read(purchase, _NoDeadline()))
        state = _final_state(decision, _answer(answers, purchase.authorization_id))
        ledger.record(purchase, decision, state)
        rows.append(ReplayRow(purchase.authorization_id, purchase.merchant.name, purchase.billing_amount_chf,
                              decision.verdict, decision.reason_codes, state))
    return rows


def format_rows(rows: Iterable[ReplayRow]) -> str:
    lines = [f"{'ID':<8} {'Shop':<28} {'Amount':>12}  {'Verdict':<8} {'Final':<9} Reasons"]
    for r in rows:
        lines.append(f"{r.authorization_id:<8} {r.shop[:28]:<28} {fmt_chf(r.chf):>12}  {r.verdict:<8} "
                     f"{r.final_state:<9} {', '.join(r.reasons) or '-'}")
    return "\n".join(lines)
