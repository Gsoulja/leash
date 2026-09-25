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
from dataclasses import dataclass, replace
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
from leash.policy.hard_rules import rule_from_api, rule_to_api
from leash.policy.registry import REGISTRY
from leash.policy.render import describe_rule


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

    def create_draft(self, instruction: str, context: Mapping[str, Any],
                     rules: Sequence[Mapping[str, Any]] = ()) -> Mapping[str, Any]: ...

    def add_turn(self, draft_id: str, text: str,
                 rules: Sequence[Mapping[str, Any]] = (), **kwargs: Any) -> Mapping[str, Any]: ...

    def draft(self, draft_id: str) -> Mapping[str, Any]: ...

    def record_message(self, draft_id: str, text: str, reply: str,
                       context: Mapping[str, Any]) -> Mapping[str, Any]: ...


class ModelUnavailable(RuntimeError):
    """Extraction failed before any policy write; retry the task, not a clarification answer."""

    def __init__(self, proposal: Proposal):
        super().__init__(proposal.questions[0].text)
        self.code = proposal.failure


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
    reply: str | None = None

    @property
    def status(self) -> Status:
        return "ready" if self.validated and not self.questions else "needs_answers"

    @property
    def consent_text(self) -> tuple[str, ...]:
        """What the customer is asked to agree to, one sentence per rule (DEC-045).

        Generated from the `Rule` objects, never from the model's prose, so the words the customer
        approves and the rule the engine enforces cannot drift apart.

        Read from the draft's own `hard_rules`, not from what the model proposed: the policy service
        reads the instruction too, and its rules are enforced just as hard. Showing only the model's
        would have the customer agree to part of what binds them — found by running the thing, where an
        English instruction produced five enforced rules and nothing at all to agree to.
        """
        return tuple(dict.fromkeys(describe_rule(r) for r in _derived_rules(self.draft)))


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
                active: CompiledMandate | None = None,
                draft_id: str | None = None, replace_instruction: bool = False,
                simulation_scenario: str | None = None) -> Clarification:
        """One turn of the conversation.

        `draft_id` continues an existing draft instead of starting one: a conversation has exactly one
        draft, and creating a second would abandon the revisions the customer has already reviewed.
        The model still reads the whole transcript — only the newest words are added to the draft.
        """
        instruction = customer_words(turns)
        if not instruction:
            raise ValueError("a permission conversation needs the customer's own words")
        bundle = build_context(self._pack, self._scope, instruction, cutoff=cutoff, confirmed=confirmed)
        evidence = bundle.as_evidence()
        if simulation_scenario:
            evidence["simulation_scenario"] = simulation_scenario
        # `None` is passed through, never turned into an empty catalogue: the assistant branches on it
        # to ask "which exact product?" instead of searching something that cannot be searched.
        proposal = self._assistant.draft(turns, context=evidence, catalogue=self._catalogue,
                                         confirmed=active)
        if proposal.failure:
            raise ModelUnavailable(proposal)
        if proposal.intent == "history":
            summary = bundle.summary
            shops = [e.text for e in bundle.entries if e.kind == "history"]
            reply = (f"I checked the supplied history for card {bundle.scope.card_id}, through "
                     f"{summary.cutoff.at.date().isoformat()}: {summary.completed_purchases} approved purchases, "
                     f"totalling CHF {summary.spend_chf:.2f}. "
                     f"Refunds (CHF {summary.refunds_chf:.2f}) and {summary.declined} declines are counted separately. "
                     + ("Recorded shops include: " + "; ".join(shops) + ". " if shops else
                        "No approved shops are available in this summary. ")
                     + "The history does not contain item-level baskets, so it cannot establish an exact past product. "
                     "Source: authorization_history.csv, scoped by customer, account and card. "
                     "This is evidence for checking your rules, not permission to buy. Your permission is unchanged.")
            draft = self._policy.record_message(draft_id, turns[-1].text, reply, evidence) if draft_id else {}
            return Clarification(bundle, proposal, (), (), draft, reply)
        evidence["assistant"] = proposal.as_draft()
        evidence["assistant"]["history_checked"] = (
            f"History checked: {bundle.summary.completed_purchases} approved purchases on card "
            f"{bundle.scope.card_id}, through {bundle.summary.cutoff.at.date().isoformat()}. "
            "Past activity is evidence, not permission.")
        # DEC-045: the rules the assistant read go to the policy service, which validates them against
        # the registry and appends them. It reads the instruction itself too, and reports that reading
        # separately, so corroboration still means an independent reading and not our own echo.
        rules = [rule_to_api(c.rule) for c in proposal.candidates]
        if draft_id is None:
            draft = self._policy.create_draft(instruction, evidence, rules)
        else:
            draft = self._policy.add_turn(draft_id, turns[-1].text, rules,
                                          assessment=evidence["assistant"], replace_instruction=replace_instruction, context=evidence)
        return self._check(bundle, proposal, draft)

    def _check(self, bundle: ContextBundle, proposal: Proposal,
               draft: Mapping[str, Any]) -> Clarification:
        # DEC-045: the deterministic compiler no longer decides what becomes a rule — it reads no
        # German, French or Italian, and little ordinary English. Candidates arrive already validated
        # against the registry (`agent._one` step 1) and checked against the confirmed mandate (step 3).
        # What the compiler still gives is corroboration: when it read the same rule from the same
        # words, the review can say so. The customer approving the rendered rule is the gate now.
        derived = _derived(draft)
        validated: list[CandidateRule] = []
        questions = list(proposal.questions)
        for candidate in proposal.candidates:
            same_field = [d for d in derived if d.field == candidate.rule.field]
            corroborated = any(_same(candidate.rule, d) for d in same_field)
            if same_field and not corroborated:
                # The compiler read the same words and got a *different* rule for this field. That is a
                # disagreement about what the customer said, not a language gap, so it is asked about.
                questions.append(Question(f'I drafted a rule from "{candidate.says}" that the rule engine '
                                          "read differently, so it stays an unconfirmed suggestion. "
                                          "Do you want it?", candidate.rule.field))
                continue
            validated.append(replace(candidate, corroborated=corroborated))
        questions += _blocking(draft, bundle)
        return Clarification(bundle, proposal, tuple(validated),
                             tuple(dict.fromkeys(questions)), draft)


def _blocking(draft: Mapping[str, Any], bundle: ContextBundle) -> list[Question]:
    """The policy service's blocking questions, asked in the customer's own terms where we can.

    The compiler decides *what* is missing; background only changes *how* it is asked. A suggestion
    with no blocking question behind it is never asked on its own — that would be the assistant
    inventing a restriction the draft does not need.
    """
    from_background = {q.field: q.text for q in bundle.suggested_questions if q.field}
    asked = []
    for q in draft.get("open_questions", []):
        if not isinstance(q, Mapping) or not q.get("blocking"):
            continue
        field = q.get("field") if isinstance(q.get("field"), str) else None
        text = from_background.get(field) or str(q.get("text", ""))
        if text.strip():
            asked.append(Question(text, field))
    return asked


def _derived_rules(draft: Mapping[str, Any]) -> tuple[Rule, ...]:
    """Every rule the draft will enforce, whoever read it. Unreadable entries are skipped: a rule we
    cannot render is one we must not claim the customer agreed to."""
    return _read(draft.get("hard_rules"))


def _derived(draft: Mapping[str, Any]) -> tuple[Rule, ...]:
    """The rules the policy service read *itself*. Unreadable output validates nothing.

    `hard_rules` now contains our own proposal as well, so reading corroboration from it would have the
    assistant confirming itself. `independently_read` is the service's own reading; when it is absent
    (an older draft, or a caller that supplied no rules) the two are the same thing.
    """
    return _read(draft.get("independently_read", draft.get("hard_rules")))


def _read(rules: Any) -> tuple[Rule, ...]:
    if not isinstance(rules, list):
        return ()
    out = []
    for raw in rules:
        try:
            out.append(rule_from_api(raw))
        except Exception:  # noqa: BLE001 — a rule we cannot read validates nothing; it is not a pass
            continue
    return tuple(out)
