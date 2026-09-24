"""LEASH-101: the permission assistant — an untrusted client of the policy service.

It reads the conversation, asks a model for candidate rules, and hands back a *draft*. That is the
whole of its authority. It cannot confirm, activate, tighten, revoke or persist a mandate, it cannot
evaluate an authorization or produce a verdict, and it has no import path to the decision code or the
database. Those are not promises in a docstring: the module imports nothing from `leash.domain.decide`,
`leash.application.decide_purchase` or `leash.adapters.postgres`, and a test asserts it stays that way.

Model output is a *suggestion*, never an instruction. Every proposed rule must survive three checks
before it is offered to the customer at all:

1. **Enforceable** — the field, operator and value pass the policy registry. Anything unknown,
   ambiguous or unsupported becomes a question instead (an unenforceable rule must never look
   confirmed, and a supported field proves enforceability, not fidelity to intent).
2. **Traceable** — it quotes an exact excerpt of something the *customer* actually said, in a turn
   that exists. A rule assembled from profile background, merchant copy or the model's own invention
   is not a customer instruction, so it becomes a question the customer can answer.
3. **No looser than what is already confirmed** — checked with `CompiledMandate.tighten`, which
   refuses anything that is not stricter.

Everything the model cannot do safely falls the same way: towards a question. A timeout, an exception,
malformed output or an empty answer all produce zero candidates and a visible clarification, never a
partial draft that could be mistaken for a reviewed one.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Protocol, cast, get_args

from leash.domain import mandate as m
from leash.domain.mandate import CompiledMandate, LooseningError, Operator, Rule
from leash.policy.compiler import compile_instruction
from leash.policy.registry import REGISTRY, problems

#: Wording shown when the model could not be reached or could not be understood. Model unavailability
#: is informational: it never approves anything, it only means the customer is asked instead.
MODEL_UNAVAILABLE = "I couldn't draft that automatically just now"

#: Bumped whenever the prompt changes, so a stored draft says which prompt produced it.
PROMPT_VERSION = "pa-1"

Status = Literal["needs_answers", "ready"]


@dataclass(frozen=True)
class Turn:
    """One message in the permission conversation."""

    turn_id: str
    speaker: Literal["customer", "assistant"]
    text: str


@dataclass(frozen=True)
class ProposalRequest:
    """What the model is given. `context` is background data, never instructions to follow."""

    turns: tuple[Turn, ...]
    context: Mapping[str, Any]
    catalogue: tuple[Any, ...] = ()
    #: Stated explicitly so a model adapter cannot quietly promote background to a system role.
    context_role: Literal["data"] = "data"


class AssistantModel(Protocol):
    """The only thing the assistant needs from a model: structured candidate rules."""

    name: str

    def propose(self, request: ProposalRequest) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class Question:
    text: str
    field: str | None = None


@dataclass(frozen=True)
class CandidateRule:
    """A rule the model proposed, validated and traced back to the customer's own words."""

    rule: Rule
    says: str  # the exact excerpt the customer wrote
    turn_id: str
    #: Always False here. Only the customer-facing policy workflow can confirm anything.
    confirmed: bool = False


@dataclass(frozen=True)
class ToolCall:
    """One lookup the assistant made, recorded so a draft can be audited without hidden reasoning."""

    tool: str
    reference: str
    resolved: str | None

    def as_dict(self) -> dict[str, str | None]:
        return {"tool": self.tool, "reference": self.reference, "resolved": self.resolved}


@dataclass(frozen=True)
class Proposal:
    """A candidate draft. It carries no verdict, and no hidden reasoning."""

    candidates: tuple[CandidateRule, ...] = ()
    questions: tuple[Question, ...] = ()
    model: str = ""
    prompt_version: str = PROMPT_VERSION
    tool_calls: tuple[ToolCall, ...] = ()

    @property
    def status(self) -> Status:
        """A draft with an open question is never ready, and a draft with nothing in it never is."""
        return "ready" if self.candidates and not self.questions else "needs_answers"

    def as_draft(self) -> dict[str, Any]:
        """The draft as it goes to the policy service: rules, questions and provenance only."""
        return {
            "rules": [{"field": c.rule.field, "operator": c.rule.operator, "value": str(c.rule.value)}
                      for c in self.candidates],
            "questions": [q.text for q in self.questions],
            "status": self.status,
            "provenance": [{"field": c.rule.field, "turn_id": c.turn_id, "says": c.says,
                            "confirmed": c.confirmed} for c in self.candidates],
            "model": self.model,
            "prompt_version": self.prompt_version,
            "tool_calls": [call.as_dict() for call in self.tool_calls],
        }


def _value(field_name: str, raw: Any) -> Any:
    """Registry value kinds: a number stays exact (Decimal, never float), text stays text."""
    spec = REGISTRY.get(field_name)
    if spec is None:
        return raw
    if spec.value_kind == "number":
        if isinstance(raw, float):
            raise ValueError("amounts must not arrive as float")
        return Decimal(str(raw))
    return raw


def _spans(needle: str, haystack: str) -> bool:
    """`needle` appears in `haystack` on token boundaries, so "50" never matches inside "500"."""
    if not needle.strip():
        return False
    return re.search(rf"(?<![0-9A-Za-z]){re.escape(needle.strip())}(?![0-9A-Za-z])", haystack) is not None


def _excerpt_is_the_customers(says: str, turns: Sequence[Turn], turn_id: str) -> bool:
    """True when `says` is an exact excerpt of that customer turn. Paraphrase does not count."""
    for turn in turns:
        if turn.turn_id == turn_id and turn.speaker == "customer":
            return _spans(says, turn.text)
    return False


def _value_is_evidenced(rule: Rule, says: str) -> bool:
    """The quoted words must actually carry the value the rule claims.

    Quoting "CHF 50" and attaching it to a CHF 500 limit is model output posing as the customer's
    words: the excerpt is genuine but it does not say what the rule says. Item IDs are exempt —
    they come from a recorded catalogue lookup, not from the customer's typing.
    """
    if rule.field == m.F_ITEM_ID:
        return True
    values = rule.value if isinstance(rule.value, tuple) else (rule.value,)
    return all(_spans(str(v), says.lower()) or _spans(str(v), says) for v in values)


class PermissionAssistant:
    """Proposes a draft. Holds no authority over the control layer."""

    #: The complete tool list. There is no decision, confirmation or database tool, and this
    #: attribute is what the tests assert against, so adding one is a visible change.
    tools: tuple[str, ...] = ("propose_draft", "lookup_catalogue")

    def __init__(self, model: AssistantModel):
        self._model = model

    def draft(self, turns: Sequence[Turn], *, context: Mapping[str, Any] | None = None,
              catalogue: Sequence[Any] = (), confirmed: CompiledMandate | None = None) -> Proposal:
        """Ask the model, then keep only what is enforceable, traceable and no looser than confirmed."""
        request = ProposalRequest(tuple(turns), dict(context or {}), ())
        try:
            reply = self._model.propose(request)
        except Exception:  # noqa: BLE001 — any model failure means "ask the customer", never "proceed"
            return self._fallback(f"{MODEL_UNAVAILABLE}. Could you say the rule in your own words?")
        return self._read(reply, tuple(turns), confirmed, catalogue, dict(context or {}))

    def _fallback(self, text: str) -> Proposal:
        return Proposal(questions=(Question(text),), model=getattr(self._model, "name", ""))

    def _read(self, reply: Any, turns: tuple[Turn, ...], confirmed: CompiledMandate | None,
              catalogue: Any, context: Mapping[str, Any]) -> Proposal:
        name = getattr(self._model, "name", "")
        if not isinstance(reply, Mapping) or not isinstance(reply.get("rules"), list):
            return self._fallback(f"{MODEL_UNAVAILABLE}. Could you say the rule in your own words?")
        candidates: list[CandidateRule] = []
        questions: list[Question] = [Question(str(q)) for q in reply.get("questions", []) if str(q).strip()]
        calls: list[ToolCall] = []
        for raw in reply["rules"]:
            candidate, question = self._one(raw, turns, confirmed, catalogue, calls)
            if candidate is not None:
                candidates.append(candidate)
            if question is not None:
                questions.append(question)
        questions += _omitted(turns, candidates)
        questions += _context_gaps(context)
        if not candidates and not questions:
            questions.append(Question(f"{MODEL_UNAVAILABLE}. Could you say the rule in your own words?"))
        return Proposal(tuple(candidates), tuple(dict.fromkeys(questions)), name, PROMPT_VERSION,
                        tuple(calls))

    def _one(self, raw: Any, turns: tuple[Turn, ...], confirmed: CompiledMandate | None,
             catalogue: Any, calls: list[ToolCall]) -> tuple[CandidateRule | None, Question | None]:
        """One proposed rule, or the question it becomes instead."""
        if not isinstance(raw, Mapping):
            return None, Question("I couldn't read one of the rules I drafted. Could you say it again?")
        field_name, operator = str(raw.get("field", "")), str(raw.get("operator", ""))
        says, turn_id = str(raw.get("says", "")), str(raw.get("turn_id", ""))
        if operator not in get_args(Operator):
            return None, Question(f"I can't enforce \"{operator}\" as a rule. Could you say it as a simple "
                                  "rule (for example: at most CHF 50 per order)?", field_name or None)
        if "value" not in raw:
            return None, Question(f"I couldn't read a value for {field_name or 'a rule'}. What should it be?")
        try:
            rule = Rule(field_name, cast(Operator, operator), _value(field_name, raw["value"]))
        except (ValueError, TypeError, ArithmeticError, InvalidOperation):
            return None, Question(f"I couldn't read the value for {field_name or 'a rule'}. What should it be?")

        # 0. a product the customer named in words, not by ID: look it up rather than invent one
        if field_name == m.F_ITEM_ID:
            rule, unresolved = _resolve_item(rule, catalogue, calls)
            if unresolved is not None:
                return None, unresolved

        # 1. enforceable exactly as written, or it becomes a question
        found = problems([rule])
        if found:
            return None, Question(f"I can't enforce that as written ({'; '.join(found)}). "
                                  "Could you say it as a simple rule?", field_name)
        # 2. traceable to the customer's own words
        if not _excerpt_is_the_customers(says, turns, turn_id):
            return None, Question("I drafted a rule you didn't say in those words, so it stays an "
                                  f"unconfirmed suggestion: {field_name}. Do you want it?", field_name)
        if not _value_is_evidenced(rule, says):
            return None, Question(f'You said "{says}", which doesn\'t give me {rule.value} for '
                                  f"{_label(field_name)}. It stays an unconfirmed suggestion — "
                                  "what should the value be?", field_name)
        # 3. no looser than a permission already confirmed
        if confirmed is not None:
            try:
                confirmed.tighten(rule)
            except LooseningError:
                return None, Question("That would loosen a permission you already confirmed, and a "
                                      "change can only make it stricter. Shall I keep the current one?",
                                      field_name)
            except Exception:  # noqa: BLE001 — an unusable rule is a question, never a silent pass
                return None, Question(f"I couldn't check that against your confirmed permission "
                                      f"({field_name}). Could you say it again?", field_name)
        return CandidateRule(rule, says, turn_id), None


def _resolve_item(rule: Rule, catalogue: Any, calls: list[ToolCall]) -> tuple[Rule, Question | None]:
    """A named product becomes an item ID only when the catalogue reads it as exactly one item.

    Several matches are a question for the customer, never a pick; none is a question too. Either
    way readiness is blocked: an unresolved reference must never look like a verified guarantee.
    """
    values = rule.value if isinstance(rule.value, tuple) else (rule.value,)
    reference = " ".join(str(v) for v in values)
    if all(isinstance(v, str) and _known_item(v, catalogue) for v in values):
        return rule, None  # real catalogue item IDs
    if catalogue is None:
        return rule, Question(f'I couldn\'t look up "{reference}". Which exact product do you mean?',
                              m.F_ITEM_ID)
    resolution = catalogue.search(name=reference)
    one = resolution.resolved
    calls.append(ToolCall("lookup_catalogue", reference, one.item_id if one else None))
    if one is None:
        names = ", ".join(c.name for c in resolution.candidates[:5])
        asked = (f'I couldn\'t match "{reference}" to one product'
                 + (f" — it could be: {names}." if names else ".")
                 + " Which exact product do you mean?")
        return rule, Question(asked, m.F_ITEM_ID)
    return Rule(rule.field, rule.operator, (one.item_id,)), None


def _known_item(value: str, catalogue: Any) -> bool:
    """An item ID the catalogue actually has. An invented ID must never pass for a resolved one."""
    if not value.startswith("IT") or catalogue is None:
        return False
    return any(c.item_id == value for c in catalogue.search(name="").candidates)


def _omitted(turns: Sequence[Turn], candidates: Sequence[CandidateRule]) -> list[Question]:
    """Restrictions the customer stated that the model left out.

    The deterministic compiler reads the customer's own words independently of the model. Anything
    it finds that the draft does not cover is raised as a question rather than quietly dropped —
    a draft that silently loses a restriction is looser than what the customer asked for.
    """
    said = " ".join(t.text for t in turns if t.speaker == "customer")
    if not said.strip():
        return []
    try:
        read = compile_instruction(said)
    except Exception:  # noqa: BLE001 — the cross-check is advisory; it must never break the draft
        return []
    # Keyed by field *and* period: "CHF 120 per order" and "CHF 300 across seven days" are the same
    # field, and a draft that keeps only one of them has quietly dropped the other.
    drafted = {_key(c.rule) for c in candidates}
    missing = [r for r in read.mandate.rules if _key(r) not in drafted]
    questions = [Question(f"You also said something about {_label(r.field)}{_over(r)}, which I left out "
                          "of the draft. Should it be a rule too?", r.field)
                 for r in {_key(r): r for r in missing}.values()]
    # A sentence the compiler could not turn into a rule at all (a foreign currency, "no
    # subscriptions") carries a restriction that would otherwise vanish: the draft has no field for
    # it, so it must be asked rather than dropped.
    questions += [Question(q.text, "instruction") for q in read.questions if q.field == "instruction"]
    if read.mandate.uncertainty != _DEFAULT_UNCERTAINTY:
        questions.append(Question(f'You said what I should do when I am unsure ("{read.mandate.uncertainty}"), '
                                  "which is not part of this draft. Shall I add it?", "uncertainty_policy"))
    return questions


#: What the compiler assumes when the customer says nothing, so only a stated choice is flagged.
_DEFAULT_UNCERTAINTY = "ask"


def _key(rule: Rule) -> tuple[str, int | None]:
    return rule.field, getattr(rule, "period_days", None)


def _over(rule: Rule) -> str:
    days = getattr(rule, "period_days", None)
    return f" over {days} days" if days else ""


#: Customer-facing names for the fields the compiler can read. The registry's own `meaning` is
#: written for the engine, so it is too technical to show someone in a chat.
_LABELS: Mapping[str, str] = {
    m.F_BILLING_CHF: "how much I may spend", m.F_MAX_QUANTITY: "how many items an order may have",
    m.F_MAX_PURCHASES: "how many orders I may place", m.F_ITEM_CATEGORY: "what kind of items",
    m.F_MERCHANT_CATEGORY: "what kind of shops", m.F_SIZE: "the size", m.F_RETURN_DAYS: "returns",
    m.F_FULFILLMENT: "delivery or collection", m.F_PRIOR_PURCHASES: "shops you have used before",
    m.F_UNREQUESTED_ITEMS: "extra items you didn't ask for", m.F_SPLIT_CHECK: "orders split in two",
    m.F_SESSION_RISK: "how risky the checkout looks", m.F_ITEM_ID: "which exact product",
}


def _label(field_name: str) -> str:
    """A short phrase a customer would recognise, or a readable fallback for a new field."""
    if field_name in _LABELS:
        return _LABELS[field_name]
    parts = [p for p in field_name.split(".") if p not in ("leash", "authorization", "items", "merchant")]
    return (parts[0] if parts else field_name).replace("_", " ")


def _context_gaps(context: Mapping[str, Any]) -> list[Question]:
    """Background the assistant cannot take at face value is said out loud, never used quietly."""
    questions = []
    entries = context.get("entries")
    if isinstance(entries, list):
        clashing = [e for e in entries if isinstance(e, Mapping) and e.get("conflicting")]
        if clashing:
            questions.append(Question(
                "Some of what I have on file conflicts with what you just told me, so I haven't "
                "used it. Which one should I go by?"))
    if context.get("truncated"):
        questions.append(Question(
            "I couldn't see all of your background just now, so I may have missed something. "
            "Is there anything else I should know?"))
    return questions
