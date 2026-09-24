"""LEASH-101: what joins the permission assistant to the rest of the system.

`agent.py` is deliberately alone: it takes turns and context and hands back a `Proposal`. Something
has to *produce* that context, decide which earlier confirmations may be seen, and put the proposed
rules in front of the deterministic policy service. That is this module, and it is the only place
where the three meet.

It keeps the same posture as the agent. It reads a pack, it calls a policy-service port, and it
holds no authority: there is no confirm, no activate, no verdict and no database here either, and a
structural test reads this module's imports to keep it that way.

Two rules of its own:

- **`instruction` is the customer's own words.** `build_context` uses it to choose which questions
  to suggest, so putting assistant, agent or merchant text there would let untrusted text pick the
  questions. `customer_words()` is the only way this module builds one.
- **A proposal the policy service did not itself derive is a suggestion, not a rule.** The model may
  read the conversation better than a regex does, but "better" is not "authoritative": a candidate
  the deterministic compiler did not produce from the same words becomes a question the customer
  answers, never a rule that slipped through because a model was confident.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from assistant.agent import CandidateRule, PermissionAssistant, Proposal, Question, Status, Turn
from leash.application.permission_context import (
    ConfirmedPermission,
    ContextBundle,
    Scope,
    SourceRef,
    build_context,
)
from leash.domain.clock import SimTime
from leash.domain.mandate import CompiledMandate, Rule
from leash.policy.hard_rules import rule_from_api
from leash.policy.registry import REGISTRY


def customer_words(turns: Sequence[Turn]) -> str:
    """The customer's own turns, and nothing else — the only honest input to `build_context`."""
    return " ".join(t.text.strip() for t in turns if t.speaker == "customer" and t.text.strip())


def scoped_permissions(records: Sequence[Mapping[str, Any]], *,
                       dataset: str) -> tuple[ConfirmedPermission, ...]:
    """Stored confirmations as background, each keeping the scope it was actually recorded for.

    A record that does not name its own customer is dropped rather than widened to whoever is
    talking: authority recorded for one person says nothing about another, and a missing scope is a
    missing fact, not a permission. `build_context` then drops any that do not cover this scope.
    """
    permissions = []
    for record in records:
        scope, text = record.get("scope"), record.get("text")
        source = _source(record.get("source"), dataset)
        if not isinstance(scope, Mapping) or not scope.get("customer_id") or not isinstance(text, str):
            continue
        if scope.get("dataset") != dataset or source is None:
            continue
        permissions.append(ConfirmedPermission(
            text=text,
            scope=Scope(dataset, str(scope["customer_id"]),
                        scope.get("account_id"), scope.get("card_id")),
            source=source,
            # A time we cannot read is no time at all: the entry is then labelled "unknown"
            # freshness rather than crashing the bundle that has to date it.
            confirmed_at=record["confirmed_at"] if isinstance(record.get("confirmed_at"), SimTime) else None))
    return tuple(permissions)


def _source(raw: Any, dataset: str) -> SourceRef | None:
    """Where the confirmation was recorded. A record that cannot say is dropped, not guessed."""
    if isinstance(raw, SourceRef):
        return raw
    if isinstance(raw, Mapping) and raw.get("row_id"):
        return SourceRef(dataset, str(raw.get("file") or "mandates"), str(raw["row_id"]),
                         raw.get("field"))
    if isinstance(raw, str) and raw.strip():
        return SourceRef(dataset, "mandates", raw.strip())
    return None


class PolicyService(Protocol):
    """The policy service as this layer may use it: ask for a draft. Nothing confirms here."""

    def create_draft(self, instruction: str, context: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class Clarification:
    """One turn of the conversation: what was seen, what was proposed, what survived validation."""

    bundle: ContextBundle
    proposal: Proposal
    #: Candidates the policy service derived from the same words. Only these may go to review.
    validated: tuple[CandidateRule, ...]
    questions: tuple[Question, ...]
    #: The policy service's own draft view, kept whole so the revision can be audited.
    draft: Mapping[str, Any]

    @property
    def status(self) -> Status:
        return "ready" if self.validated and not self.questions else "needs_answers"


#: Operators whose value is a set, whatever shape it arrived in.
_SET_OPERATORS = frozenset({"in", "not_in"})


def _values(rule: Rule) -> Any:
    """The rule's value in one comparable shape: a set for lists, an exact number for amounts.

    The API carries amounts as strings, so "50" and Decimal("50.00") are the same restriction and
    must compare equal — otherwise a rule the policy service did derive would look invented. The same
    holds for a one-element set written as a bare string: the engine reads both identically.
    """
    if isinstance(rule.value, tuple):
        return frozenset(rule.value)
    if rule.operator in _SET_OPERATORS:
        return frozenset({rule.value})
    spec = REGISTRY.get(rule.field)
    if spec is not None and spec.value_kind == "number":
        try:
            return Decimal(str(rule.value))
        except (InvalidOperation, ValueError):
            return rule.value
    return rule.value


def _same(a: Rule, b: Rule) -> bool:
    """Same restriction, ignoring the bookkeeping the compiler adds (currency, scope labels)."""
    return ((a.field, a.operator, a.period_days) == (b.field, b.operator, b.period_days)
            and _values(a) == _values(b))


class PermissionConversation:
    """Gives the assistant its background and puts what it proposes in front of the policy service."""

    def __init__(self, assistant: PermissionAssistant, pack: Any, scope: Scope,
                 policy: PolicyService, *, catalogue: Any = None):
        self._assistant = assistant
        self._pack = pack
        self._scope = scope
        self._policy = policy
        self._catalogue = catalogue

    def clarify(self, turns: Sequence[Turn], *, cutoff: SimTime,
                confirmed: Sequence[ConfirmedPermission] = (),
                active: CompiledMandate | None = None) -> Clarification:
        instruction = customer_words(turns)
        if not instruction:
            raise ValueError("a permission conversation needs the customer's own words")
        bundle = build_context(self._pack, self._scope, instruction, cutoff=cutoff, confirmed=confirmed)
        evidence = bundle.as_evidence()
        # `None` is passed through, never turned into an empty catalogue: the assistant branches on it
        # to ask "which exact product?" instead of searching something that cannot be searched.
        proposal = self._assistant.draft(turns, context=evidence, catalogue=self._catalogue,
                                         confirmed=active)
        draft = self._policy.create_draft(instruction, evidence)
        return self._check(bundle, proposal, draft)

    def _check(self, bundle: ContextBundle, proposal: Proposal,
               draft: Mapping[str, Any]) -> Clarification:
        derived = _derived(draft)
        validated = tuple(c for c in proposal.candidates if any(_same(c.rule, d) for d in derived))
        questions = list(proposal.questions)
        questions += [Question(f'I drafted a rule from "{c.says}" that the rule engine did not read '
                               "the same way, so it stays an unconfirmed suggestion. Do you want it?",
                               c.rule.field)
                      for c in proposal.candidates if c not in validated]
        questions += [Question(str(q.get("text", "")), None)
                      for q in draft.get("open_questions", []) if isinstance(q, Mapping)
                      and q.get("blocking") and str(q.get("text", "")).strip()]
        return Clarification(bundle, proposal, validated,
                             tuple(dict.fromkeys(questions)), draft)


def _derived(draft: Mapping[str, Any]) -> tuple[Rule, ...]:
    """The rules the policy service itself compiled. Unreadable output validates nothing."""
    rules = draft.get("hard_rules")
    if not isinstance(rules, list):
        return ()
    derived = []
    for raw in rules:
        try:
            derived.append(rule_from_api(raw))
        except Exception:  # noqa: BLE001 — a rule we cannot read validates nothing; it is not a pass
            continue
    return tuple(derived)
