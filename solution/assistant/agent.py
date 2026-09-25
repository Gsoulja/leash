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

Unclear rules become questions. A timeout, exception or unreadable response produces a retryable
failure before any policy write, never a partial draft mistaken for a reviewed one.
"""

import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Protocol, cast, get_args

from leash.domain import mandate as m
from leash.domain.mandate import CompiledMandate, LooseningError, Operator, Rule
from leash.policy.compiler import compile_instruction
from leash.policy.hard_rules import rule_to_api
from leash.policy.registry import REGISTRY, problems
from leash.policy.render import describe_rule

#: Model failures ask for a retry, not a new instruction or permission.
MODEL_UNAVAILABLE = "I couldn't draft that automatically just now"
log = logging.getLogger("leash.assistant")

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
class QuestionSource:
    """Where a question came from, when it came from background rather than from the customer.

    Only background-derived questions carry one. A question the customer's own words prompted has no
    source and must not be given one: "your profile records this" and "you told me this" are
    different claims, and only the customer can make the second (DEC-034).
    """

    kind: str            # "preference" or "history" — which kind of background put the question here
    evidence: str        # the recorded words themselves, so the screen quotes rather than paraphrases
    file: str | None = None      # the row it was read from, kept as evidence for the draft revision
    row_id: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {"kind": self.kind, "evidence": self.evidence, "file": self.file, "row_id": self.row_id}


@dataclass(frozen=True)
class Question:
    text: str
    field: str | None = None
    source: QuestionSource | None = None
    #: The rule this question offers, when it offers one. Kept so a later stage can tell a suggestion
    #: the draft already enforces from one that would change it — the text alone cannot say.
    rule: Rule | None = None


@dataclass(frozen=True)
class CandidateRule:
    """A rule the model proposed, validated and traced back to the customer's own words."""

    rule: Rule
    says: str  # the excerpt the model attributed to the customer
    turn_id: str
    #: Always False here. Only the customer-facing policy workflow can confirm anything.
    confirmed: bool = False
    #: The quoted words carry the rule's value literally. False for a text value the customer wrote in
    #: their own language ("nur Lieferung" never contains `delivery`) — kept, but asked about, and shown
    #: as our reading rather than their words.
    evidenced: bool = True
    #: The deterministic compiler read the same rule from the same words. Corroboration, never a gate
    #: (DEC-045): it reads no German, French or Italian, so its silence proves nothing.
    corroborated: bool = False


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
    failure: str | None = None
    intent: Literal["permission", "history"] = "permission"
    #: Turns the model attributed a rule to, whether or not the rule survived validation. A turn that
    #: appears here stated something, even if what it stated became a question instead of a rule.
    attributed: tuple[str, ...] = ()

    @property
    def status(self) -> Status:
        """A draft with an open question is never ready, and a draft with nothing in it never is."""
        return "ready" if self.candidates and not self.questions else "needs_answers"

    def as_draft(self) -> dict[str, Any]:
        """The draft as it goes to the policy service: rules, questions and provenance only."""
        return {
            "rules": [rule_to_api(c.rule) for c in self.candidates],
            "questions": [{"text": q.text, "field": q.field,
                           "source": q.source.as_dict() if q.source else None}
                          for q in self.questions],
            "status": self.status,
            "provenance": [{"field": c.rule.field, "turn_id": c.turn_id, "says": c.says,
                            "confirmed": c.confirmed, "evidenced": c.evidenced,
                            "corroborated": c.corroborated}
                           for c in self.candidates],
            "model": self.model,
            "prompt_version": self.prompt_version,
            "tool_calls": [call.as_dict() for call in self.tool_calls],
        }


def _value(field_name: str, raw: Any) -> Any:
    """Registry value kinds: a number stays exact (Decimal, never float), text stays text.

    A model answers in JSON, so a set of allowed values arrives as a list — every `in` and `not_in`
    rule. `Rule` takes a tuple, so converting here is this adapter's job; without it the most common
    shape of rule the model can propose would always become a question.
    """
    spec = REGISTRY.get(field_name)
    if spec is None:
        return raw
    if spec.value_kind == "number":
        if isinstance(raw, float):
            raise ValueError("amounts must not arrive as float")
        return Decimal(str(raw))
    if isinstance(raw, list):
        return tuple(str(v) for v in raw)
    return raw


def _spans(needle: str, haystack: str) -> bool:
    """`needle` appears in `haystack` on token boundaries, so "50" never matches inside "500"."""
    if not needle.strip():
        return False
    return re.search(rf"(?<![0-9A-Za-z]){re.escape(needle.strip())}(?![0-9A-Za-z])", haystack) is not None


_WORD = re.compile(r"[0-9A-Za-z\u00c0-\u024f']+")
_SENTENCES = re.compile(r"(?<=[.!?;])\s+|\n")

#: Words that carry no evidence on their own, so a restatement may add or drop them. "only clothing"
#: is the customer's "clothing"; the "only" is the model's summary of the sentence around it.
_FUNCTION_WORDS = frozenset("""a an and any are as at be been but by can do does for from have has i if
in is it its me more my no nor not of on only or our per she that the their them they this to up us
was we with you your""".split())


def _pattern(phrase: str) -> str:
    """The phrase as the customer may have typed it: any punctuation or spacing between its words.

    A model normalises whitespace and punctuation ("at most  CHF 50" quoted back as "at most CHF 50"),
    which a literal substring search calls a different sentence.
    """
    words = _WORD.findall(phrase)
    return (rf"(?<![0-9A-Za-z]){'[^0-9A-Za-z]+'.join(map(re.escape, words))}(?![0-9A-Za-z])"
            if words else "")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCES.split(text) if s.strip()]


def _word_in(word: str, text: str) -> bool:
    """A number matches exactly ("50" never inside "500"); a word may be inflected ("return" in "returned")."""
    if word.isdigit():
        return _spans(word, text)
    return re.search(rf"(?<![0-9A-Za-z]){re.escape(word)}[A-Za-z\u00c0-\u024f']*", text, re.I) is not None


def _restated(says: str, text: str) -> str | None:
    """The customer's own sentence behind a quote that restates rather than copies.

    A model quotes the meaning far more often than a span: "one item" for "one ordinary grocery item",
    "only clothing" for "may buy clothing for me", "At most CHF 30 per order" for "Actually make it
    30." Measured live on 2026-09-25 against the five challenge instructions: 14 of the 19 rules
    Apertus read correctly were dropped here, corrections included.

    Requiring every content word of the quote to appear in one sentence the customer wrote keeps what
    the gate is for — the words are the customer's, not the background's and not the model's
    invention (DEC-034, DEC-048) — without demanding a transcription. What is returned is always the
    customer's own sentence, never the model's string.
    """
    words = [w.lower() for w in _WORD.findall(says)]
    content = [w for w in words if w not in _FUNCTION_WORDS]
    if not content:
        return None
    for sentence in _sentences(text):
        if all(_word_in(w, sentence) for w in content):
            return sentence
    return None


def _customer_excerpt(says: str, turns: Sequence[Turn], turn_id: str) -> str | None:
    """The customer's own words behind the model's quote, or None if they never wrote them.

    Their exact span where the model copied one, otherwise the sentence a restatement came from. A
    different speaker, a turn that does not exist, or words the customer never wrote: never.
    """
    if not says.strip():
        return None
    text = next((t.text for t in turns if t.turn_id == turn_id and t.speaker == "customer"), None)
    if text is None:
        return None
    pattern = _pattern(says)
    match = re.search(pattern, text, re.I) if pattern else None
    return match.group(0) if match else _restated(says, text)


def _value_is_evidenced(rule: Rule, says: str) -> bool:
    """The quoted words must actually carry the *number* the rule claims.

    Quoting "CHF 50" and attaching it to a CHF 500 limit is model output posing as the customer's
    words: the excerpt is genuine but it does not say what the rule says. Digits survive translation,
    so this holds in any language.

    It is deliberately **not** applied to text values. Those are the registry's canonical terms —
    `delivery`, `electronics` — and a customer writing "nur Lieferung" or "solo consegna" never types
    them, so requiring the term in the quote would reject every non-English categorical rule (LEASH-175).
    What stands in its place is DEC-045's gate: the customer approves "For delivery only.", generated
    from the rule, and rejects it if that is not what they meant. The quote must still be the
    customer's own words — that check is unchanged, and it is what keeps background text out.

    Item IDs are exempt for a different reason: they come from a recorded catalogue lookup, not from
    the customer's typing.
    """
    if rule.field == m.F_ITEM_ID:
        return True
    # Reuse the independent compiler for "one item", "used before", "no extras", and category
    # wording. A quote must support this exact rule, not merely contain the same number elsewhere.
    parsed = compile_instruction(says).mandate.rules
    if any((r.field, r.operator, r.value, r.period_days) ==
           (rule.field, rule.operator, rule.value, rule.period_days) for r in parsed):
        return True
    values = rule.value if isinstance(rule.value, tuple) else (rule.value,)
    if rule.period_days is not None and not _carried(rule.period_days, says):
        return False  # "across 30 days" from "any seven days" is a number the customer never wrote
    return all(_carried(v, says) for v in values)


#: Small numbers as a customer writes them. A quantity or a count is spelled far more often than an
#: amount is, and "one item" carries the number 1 exactly as "1 item" does (DEC-048).
_WRITTEN_OUT: Mapping[str, int] = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                                   "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
                                   "twelve": 12, "fourteen": 14, "thirty": 30}


def _carried(value: Any, says: str) -> bool:
    """The quoted words carry this value, in digits or written out."""
    if _spans(str(value), says.lower()) or _spans(str(value), says):
        return True
    try:
        wanted = int(Decimal(str(value)))
    except (ArithmeticError, InvalidOperation, TypeError, ValueError):
        return False
    return any(_WRITTEN_OUT.get(word) == wanted for word in _WORD.findall(says.lower()))


#: A number written right after a currency is an amount, whatever rule quotes it.
_MONEY_BOUND = re.compile(r"(?:CHF|EUR|USD|GBP|fr\.?|francs?|\u20ac|\$|\u00a3)\s*$", re.I)
#: Any currency but ours next to a number. The engine's limits are CHF and it converts nothing here.
_OTHER_MONEY = re.compile(r"\b(EUR|USD|GBP|JPY|euros?|dollars?|pounds?|yen)\b|[\u20ac$\u00a3]", re.I)


def _turn_text(turns: Sequence[Turn], turn_id: str) -> str:
    return next((t.text for t in turns if t.turn_id == turn_id and t.speaker == "customer"), "")


def _value_anchor(rule: Rule, text: str) -> str | None:
    """The customer's own sentence carrying this rule's number, when the model restated the rest.

    "Actually make it 30." is a whole correction in four words: the customer typed the number and
    nothing else, so the model's quote ("At most CHF 30 per order") shares no other word with it.
    Measured live on 2026-09-25: both tightening and loosening corrections were dropped here, which
    loses a tightening the customer asked for.

    A number written straight after a currency is an amount and may only evidence the amount field —
    "CHF 2" is two francs, never two earlier purchases at a shop.
    """
    spec = REGISTRY.get(rule.field)
    if spec is None or spec.value_kind != "number":
        return None
    wanted = {str(rule.value)}
    if isinstance(rule.value, Decimal) and rule.value == rule.value.to_integral_value():
        wanted.add(str(int(rule.value)))
    for sentence in _sentences(text):
        for needle in wanted:
            for found in re.finditer(rf"(?<![0-9A-Za-z]){re.escape(needle)}(?![0-9A-Za-z])", sentence):
                if _MONEY_BOUND.search(sentence[:found.start()]) and rule.field != m.F_BILLING_CHF:
                    continue
                return sentence
    return None


def _wrong_currency(field_name: str, says: str) -> str | None:
    """A currency the engine does not limit in. Converting it ourselves would invent a limit.

    Measured live on 2026-09-25: Apertus read "at most USD 450 per order" as `billing_amount_chf <=
    450`, which is CHF 450 against an intended cap of about CHF 391 — a looser rule than the customer
    asked for, and the one direction a mandate may never move.
    """
    if field_name != m.F_BILLING_CHF:
        return None
    found = _OTHER_MONEY.search(says)
    return found.group(0) if found else None


#: What the engine can actually match a text value against. The event's own vocabulary, not the
#: model's: `fulfillment_method = "lieferung"` is enforceable in form and unmatchable in fact.
#: ponytail: merchant categories and sizes are not here — they come from the pack, which this process
#: reads only through the catalogue. Add them when the vocabulary reaches the assistant.
_VOCABULARY: Mapping[str, frozenset[str]] = {
    m.F_FULFILLMENT: frozenset({"delivery", "pickup", "digital"}),
    m.F_SPLIT_CHECK: frozenset({"on"}),
}


def _unknown_values(rule: Rule, catalogue: Any) -> tuple[str, ...]:
    """Values outside a vocabulary the event schema fixes, which no purchase could ever satisfy.

    Only `_VOCABULARY` is checked here, because only those values are ours to know. A category comes
    from whichever scenario pack the platform is running, so a value missing from the catalogue this
    process happens to hold is not evidence of a mistake — see `_off_catalogue`.
    """
    known = _VOCABULARY.get(rule.field)
    if known is None:
        return ()
    values = rule.value if isinstance(rule.value, tuple) else (rule.value,)
    return tuple(str(v) for v in values if str(v).strip().lower() not in known)


def _off_catalogue(rule: Rule, catalogue: Any) -> tuple[str, ...]:
    """Categories the loaded catalogue does not have, which may still be the live pack's own.

    Refusing them would drop a correct rule the moment the scenario pack differs from the one this
    process holds — and on event day the scenarios, cards and items are ones we have not seen. Such a
    rule is kept (an unmatchable category only narrows what passes, never widens it) and marked as our
    reading, so the customer is shown it as unconfirmed rather than told they said it.
    """
    if rule.field != m.F_ITEM_CATEGORY:
        return ()
    items = _items(catalogue)
    if not items:
        return ()
    known = frozenset(i.category.strip().lower() for i in items)
    values = rule.value if isinstance(rule.value, tuple) else (rule.value,)
    return tuple(str(v) for v in values if str(v).strip().lower() not in known)


def _items(catalogue: Any) -> tuple[Any, ...]:
    if hasattr(catalogue, "search"):
        return tuple(catalogue.search(name="").candidates)
    return tuple(catalogue or ())


def _read_by_the_engine(rule: Rule, compiled: Sequence[Rule]) -> bool:
    """The deterministic compiler read this very rule from the customer's own words.

    The policy service compiles the same instruction, so the rule is in the draft — labelled as the
    customer's own — whatever we do with the model's version of it. A question about it therefore asks
    the customer to confirm a boundary their draft already shows them, which blocks them for nothing.
    Seen live three times on 2026-09-25: "One purchase in total" offered as an unconfirmed suggestion,
    "I read 'specialist sports retailer' as … those are my words", and "Which exact catalogue product do
    you want?" — each about a rule the engine had read from the same sentence (DEC-058a).
    """
    return any(_same_restriction(rule, read) for read in compiled)


def _compiler_rules(turns: Sequence[Turn], catalogue: Any) -> tuple[Rule, ...]:
    """What the deterministic compiler reads from the customer's own words, or nothing on failure."""
    said = " ".join(t.text for t in turns if t.speaker == "customer")
    if not said.strip():
        return ()
    try:
        return tuple(compile_instruction(said, catalogue=_items(catalogue)).mandate.rules)
    except Exception:  # noqa: BLE001 — an advisory reading; it must never break the draft
        return ()


def _same_restriction(a: Rule, b: Rule) -> bool:
    """The same restriction, whatever bookkeeping (currency, scope labels) either reading carries."""
    def value(rule: Rule) -> Any:
        if isinstance(rule.value, tuple):
            return frozenset(str(v) for v in rule.value)
        spec = REGISTRY.get(rule.field)
        if spec is not None and spec.value_kind == "number":
            try:
                return Decimal(str(rule.value)).normalize()
            except (ArithmeticError, InvalidOperation, ValueError):
                return str(rule.value)
        return str(rule.value)

    return ((a.field, a.operator, a.period_days) == (b.field, b.operator, b.period_days)
            and value(a) == value(b))


class PermissionAssistant:
    """Proposes a draft. Holds no authority over the control layer."""

    #: The complete tool list. There is no decision, confirmation or database tool, and this
    #: attribute is what the tests assert against, so adding one is a visible change.
    tools: tuple[str, ...] = ("propose_draft", "lookup_catalogue")

    def __init__(self, model: AssistantModel):
        self._model = model

    def draft(self, turns: Sequence[Turn], *, context: Mapping[str, Any] | None = None,
              catalogue: Sequence[Any] | None = None,
              confirmed: CompiledMandate | None = None) -> Proposal:
        """Ask the model, then keep only what is enforceable, traceable and no looser than confirmed."""
        items = tuple(catalogue.search(name="").candidates) if hasattr(catalogue, "search") else tuple(catalogue or ())
        request = ProposalRequest(tuple(turns), dict(context or {}), items)
        try:
            reply = self._model.propose(request)
        except Exception as exc:  # noqa: BLE001 — a failed extraction never permits proceeding
            # Exception text may contain request data or credentials; record only its type.
            log.warning("Permission model failed: %s", type(exc).__name__)
            return self._fallback(f"{MODEL_UNAVAILABLE}. Please retry; you do not need to reword your task.",
                                  "model_unavailable")
        return self._read(reply, tuple(turns), confirmed, catalogue, dict(context or {}))

    def _fallback(self, text: str, failure: str) -> Proposal:
        return Proposal(questions=(Question(text),), model=getattr(self._model, "name", ""), failure=failure)

    def _read(self, reply: Any, turns: tuple[Turn, ...], confirmed: CompiledMandate | None,
              catalogue: Any, context: Mapping[str, Any]) -> Proposal:
        name = getattr(self._model, "name", "")
        if isinstance(reply, Mapping) and reply.get("intent") == "history":
            if reply.get("rules") != []:
                return self._fallback("The model mixed a history answer with permission changes. Please retry.",
                                      "model_invalid_response")
            return Proposal(model=name, prompt_version=str(getattr(self._model, "prompt_version", PROMPT_VERSION)),
                            intent="history")
        if not isinstance(reply, Mapping) or not isinstance(reply.get("rules"), list):
            log.warning("Permission model returned an invalid proposal")
            return self._fallback("The model returned an unreadable proposal. Please retry; you do not need to reword your task.",
                                  "model_invalid_response")
        asked = reply.get("questions", [])
        if not isinstance(asked, list) or not all(isinstance(q, str) for q in asked):
            # Not pedantry: a bare string iterates into one question per character, and `None` or a
            # number raises. Either way the customer gets a broken chat instead of a retry, so an
            # unreadable `questions` is the same failure as an unreadable `rules` (DEC-047).
            log.warning("Permission model returned unreadable questions")
            return self._fallback("The model returned an unreadable proposal. Please retry; you do not need to reword your task.",
                                  "model_invalid_response")
        candidates: list[CandidateRule] = []
        # What the deterministic compiler reads from the same words. The policy service compiles the very
        # same instruction, so a rule in here is already in the draft whatever we do with the model's
        # version of it — which is what makes a question about it redundant rather than a safeguard.
        compiled = _compiler_rules(turns, catalogue)
        questions: list[Question] = [Question(q) for q in asked if q.strip()]
        calls: list[ToolCall] = []
        for raw in reply["rules"]:
            candidate, question = self._one(raw, turns, confirmed, catalogue, calls, compiled)
            if candidate is not None:
                candidates.append(candidate)
            if question is not None:
                questions.append(question)
        questions += _omitted(turns, candidates, catalogue)
        questions += _context_gaps(context)
        # Nothing from the model *and* nothing from the deterministic reader: there is no draft to show,
        # so the customer retries rather than being handed an empty one (DEC-045, DEC-047). When the
        # compiler did read their words, the draft is real even if the model proposed nothing — the
        # policy service enforces those rules and the customer consents to them (DEC-058b).
        if not candidates and not questions and not compiled:
            return self._fallback("The model returned no proposal. Please retry; you do not need to reword your task.",
                                  "model_invalid_response")
        version = str(getattr(self._model, "prompt_version", PROMPT_VERSION))
        # A turn counts as read only when the model's quote is the customer's words in *that* turn —
        # the same test a rule must pass to exist at all. Live on SCEN0002 the model tagged a rule
        # `turn_id` T2 while quoting T1, and trusting the claim made "yes i mean that" an instruction:
        # it was appended to the draft, burned a revision, and left the grammar's unreadable-sentence
        # question blocking with no answer that could clear it.
        attributed = tuple(dict.fromkeys(
            str(raw["turn_id"]) for raw in reply["rules"]
            if isinstance(raw, Mapping) and raw.get("turn_id")
            and _customer_excerpt(str(raw.get("says", "")), turns, str(raw["turn_id"])) is not None))
        return Proposal(tuple(candidates), tuple(dict.fromkeys(questions)), name, version,
                        tuple(calls), attributed=attributed)

    def _one(self, raw: Any, turns: tuple[Turn, ...], confirmed: CompiledMandate | None,
             catalogue: Any, calls: list[ToolCall],
             compiled: Sequence[Rule] = ()) -> tuple[CandidateRule | None, Question | None]:
        """One proposed rule, or the question it becomes instead."""
        if not isinstance(raw, Mapping):
            return None, Question("I couldn't read one of the rules I drafted. Could you say it again?")
        field_name, operator = str(raw.get("field", "")), str(raw.get("operator", ""))
        says, turn_id = str(raw.get("says", "")), str(raw.get("turn_id", ""))
        if operator not in get_args(Operator):
            return None, Question(f"I can't enforce \"{operator}\" as a rule. Could you say it as a simple "
                                  "rule (for example: at most CHF 50 per order)?", field_name or None)
        if "value" not in raw:
            return None, Question(f"I couldn't read a value for {_label(field_name) or 'a rule'}. What should it be?")
        try:
            days = raw.get("period_days")
            if days is not None and (type(days) is not int or days <= 0):
                raise ValueError("period_days must be a positive integer")
            rule = Rule(field_name, cast(Operator, operator), _value(field_name, raw["value"]),
                        currency=raw.get("currency"), scope="period" if days is not None else raw.get("scope"),
                        period_days=days)
        except (ValueError, TypeError, ArithmeticError, InvalidOperation):
            return None, Question(f"I couldn't read the value for {_label(field_name) or 'a rule'}. What should it be?")

        # 0. a product the customer named in words, not by ID: look it up rather than invent one
        if field_name == m.F_ITEM_ID:
            requested = rule.value if isinstance(rule.value, tuple) else (rule.value,)
            rule, unresolved = _resolve_item(rule, catalogue, calls)
            if unresolved is not None:
                return None, unresolved
            # A real catalogue ID is not evidence that the customer selected it. Require their
            # quoted name/ID or an independent resolution of the quote to the same product.
            if not all(_spans(str(v).lower(), says.lower()) for v in requested):
                items = tuple(catalogue.search(name="").candidates) if hasattr(catalogue, "search") else tuple(catalogue or ())
                read = compile_instruction(says, catalogue=items)
                if not any(r.field == m.F_ITEM_ID and r.value == rule.value for r in read.mandate.rules) \
                        and not _read_by_the_engine(rule, compiled):
                    return None, Question("Which exact catalogue product do you want? I cannot infer a selection from your history.", m.F_ITEM_ID)

        # 1. enforceable exactly as written, or it becomes a question
        found = problems([rule])
        if found:
            return None, Question(f"I can't enforce that as written ({'; '.join(found)}). "
                                  "Could you say it as a simple rule?", field_name)
        # 2. traceable to the customer's own words. DEC-045 moved the *reading* to the model, not the
        # provenance: a rule still has to come from something the customer actually wrote, or the model
        # could launder a background preference into authority (DEC-034).
        unknown = _unknown_values(rule, catalogue)
        if unknown:
            return None, Question(f"I don't know \"{unknown[0]}\" as a value for {_label(field_name)}, so I "
                                  "can't enforce it. Which of the shop's own terms do you mean?", field_name)
        excerpt = _customer_excerpt(says, turns, turn_id) or _value_anchor(rule, _turn_text(turns, turn_id))
        if excerpt is None:
            # ponytail: the premise — what the compiler reads is in the draft — is pinned over a corpus
            # of instructions in test_every_rule_the_compiler_reads_is_carried_by_the_draft, because on
            # event day the wording is unseen. Exact enforcement would need the draft itself, which only
            # the policy service has: serialise the rule with the question and filter in `_assessed`.
            if _read_by_the_engine(rule, compiled):
                # The compiler read this very rule from the customer's own words, so it is in the draft
                # already — the policy service compiles the same instruction. Asking "do you want this
                # rule?" about a rule they already have blocks the draft for nothing, and the customer
                # sees it twice: once as theirs, once as a suggestion. Seen live on 2026-09-25, where
                # the model quoted "One purchase" — words the customer never wrote — for a rule DEC-013
                # had already read from "Buy one ordinary grocery item".
                return None, None
            return None, Question(f"Unconfirmed suggestion: {describe_rule(rule)} "
                                  "Do you want this rule?", field_name, rule=rule)
        says = excerpt
        wrong = _wrong_currency(field_name, says)
        if wrong:
            return None, Question(f'You said "{says}". My limits are in CHF and I must not convert '
                                  f"{wrong} myself — what is the limit in CHF?", field_name)
        # A number that is not in the quoted words is the model putting its own figure in the
        # customer's mouth, and digits survive translation — so that stays a refusal. A *text* value is
        # the registry's canonical term (`delivery`, `electronics`), which a customer writing "nur
        # Lieferung" never types: refusing there would be refusing the language, not the reading. So it
        # is kept, marked as our wording, and asked about (LEASH-175).
        off_pack = _off_catalogue(rule, catalogue)
        evidenced = _value_is_evidenced(rule, says) and not off_pack
        spec = REGISTRY.get(field_name)
        numeric = spec is not None and spec.value_kind == "number"
        if not evidenced and numeric:
            # A model may quote a noun phrase ("shops I have used before") without the "from"
            # that makes it a complete instruction. Check the original customer turn, keeping the
            # expanded quote as evidence; never treat an unrelated digit as corroboration.
            original = next(t.text for t in turns if t.turn_id == turn_id and t.speaker == "customer")
            if any((r.field, r.operator, r.value, r.period_days) ==
                   (rule.field, rule.operator, rule.value, rule.period_days)
                   for r in compile_instruction(original).mandate.rules):
                says, evidenced = original, True
        if not evidenced and numeric:
            missing = (f"{rule.period_days} days as the period"
                       if rule.period_days is not None and not _spans(str(rule.period_days), says)
                       else f"{rule.value} for {_label(field_name)}")
            return None, Question(f'You said "{says}", which doesn\'t give me {missing}. It stays an '
                                  "unconfirmed suggestion — what should it be?", field_name)
        unevidenced: Question | None = None
        if not evidenced and _read_by_the_engine(rule, compiled):
            # Our wording, yes — but the engine read the same restriction from the same words, so the
            # draft already shows it as the customer's own and there is nothing to confirm.
            evidenced = True
        elif off_pack:
            unevidenced = Question(f'I read "{says}" as {_label(field_name)}: {describe_rule(rule)} '
                                   f"I don't have \"{off_pack[0]}\" in the catalogue I can see, so nothing "
                                   "may match it until the shop's own wording does — did you mean that?",
                                   field_name)
        elif not evidenced:
            unevidenced = Question(f'I read "{says}" as {_label(field_name)}: {describe_rule(rule)} '
                                   "Those are my words, not yours — did you mean that?", field_name)
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
                                      f"about {_label(field_name)}. Could you say it again?", field_name)
        return CandidateRule(rule, says, turn_id, evidenced=evidenced), unevidenced


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


def _omitted(turns: Sequence[Turn], candidates: Sequence[CandidateRule], catalogue: Any = None) -> list[Question]:
    """Restrictions the customer stated that the model left out.

    The deterministic compiler reads the customer's own words independently of the model. Anything
    it finds that the draft does not cover is raised as a question rather than quietly dropped —
    a draft that silently loses a restriction is looser than what the customer asked for.
    """
    said = " ".join(t.text for t in turns if t.speaker == "customer")
    if not said.strip():
        return []
    try:
        items = tuple(catalogue.search(name="").candidates) if hasattr(catalogue, "search") else tuple(catalogue or ())
        read = compile_instruction(said, catalogue=items)
    except Exception:  # noqa: BLE001 — the cross-check is advisory; it must never break the draft
        return []
    # DEC-058(b): a rule the compiler read is never "left out of the draft". The policy service compiles
    # the same instruction, so its readings are in `hard_rules` whatever the model produced — verified
    # with no model rules supplied at all (test_every_rule_the_compiler_reads_is_carried_by_the_draft).
    # Asking "should it be a rule too?" about a rule the customer can see in their own draft is untrue,
    # and it blocked them: a well-read English instruction carried one such question per compiler rule
    # the model had not independently proposed, and no answer could clear them.
    #
    # What the question used to carry that was real — *who* read a rule — is now visible in the review
    # itself, where a reading from the customer's own words is labelled theirs and a default of ours is
    # labelled ours (LEASH-146). What stays here is the omission that is real: a sentence *neither*
    # reader turned into a rule has no field in the draft, so nothing else can show it.
    questions: list[Question] = []
    # A sentence the compiler could not turn into a rule at all (a foreign currency, "no
    # subscriptions") carries a restriction that would otherwise vanish: the draft has no field for
    # it, so it must be asked rather than dropped.
    #
    # Unless the model read that same sentence (DEC-045). The compiler reads no German, French or
    # Italian, so its silence about "höchstens CHF 50 pro Bestellung" proves nothing — asking there
    # would make every non-English instruction unanswerable, which is the grammar deciding what may
    # become a rule by the back door. The excerpt is verbatim from the customer's turn, so a rule the
    # model read out of this sentence shows up inside the question's own quotation of it.
    # ponytail: substring match on the quoted sentence. A `says` spanning two sentences matches
    # neither and the question stands — the safe direction. Carry the sentence on the compiler's
    # Question if that ever needs to be exact.
    questions += [Question(q.text, "instruction") for q in read.questions
                  if q.field == "instruction" and not _accounted_for(q.about, candidates)]
    if read.mandate.uncertainty != _DEFAULT_UNCERTAINTY:
        questions.append(Question(f'You said what I should do when I am unsure ("{read.mandate.uncertainty}"), '
                                  "which is not part of this draft. Shall I add it?", "uncertainty_policy"))
    return questions


#: Where one restriction ends and the next begins, in any of the four national languages. Punctuation
#: first, then the conjunctions; deliberately generous, because over-splitting asks one more question
#: while under-splitting drops a restriction.
_CLAUSE = re.compile(r",(?=\s)|;|:|\b(?:and|but|or|und|aber|oder|et|mais|ou|oppure|e|ma|o)\b", re.I)


def _clauses(sentence: str) -> list[str]:
    return [c for c in _CLAUSE.split(sentence) if _WORD.search(c)]


def _accounted_for(sentence: str, candidates: Sequence[CandidateRule]) -> bool:
    """Did the model read everything in a sentence the compiler's grammar could not read?

    Its quote alone cannot answer that. A model that quotes the whole sentence accounts for all of it
    while reading one restriction out of three, and an excerpt recovered from the customer's own turn
    (DEC-054) is the whole sentence by construction — so "covered" can be manufactured by expansion.
    Found in review on 2026-09-25: "Buy me a jacket, at most CHF 120 per order, and no subscriptions."
    kept the limit and lost "no subscriptions" with no question at all, and neither other net sees it —
    the grammar produced no rule to miss, and "no subscriptions" maps to no registry field, so
    `unrestricted` cannot show it either.

    So the comparison is per clause, which needs no grammar and no language: the sentence is accounted
    for only when at least as many rules were read from it as it has clauses.

    ponytail: two restrictions inside one clause with no conjunction ("keine Abos höchstens CHF 50")
    still count as one. Much narrower than the hole it replaces; counting restrictions instead would
    need exactly the reading this design says we cannot have.
    """
    clauses = _clauses(sentence or "")
    if not clauses:
        return False
    return len([c for c in candidates if _reads(c, sentence)]) >= len(clauses)


def _reads(candidate: CandidateRule, sentence: str) -> bool:
    """This rule came out of this sentence: its quote overlaps it, or its value is written in it."""
    quote, low = candidate.says.strip().lower(), sentence.strip().lower()
    if quote and (quote in low or low in quote):
        return True
    values = candidate.rule.value if isinstance(candidate.rule.value, tuple) else (candidate.rule.value,)
    return any(_carried(v, sentence) for v in values)


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
            # These two are about the background itself rather than about one entry, so the source
            # names the kind and quotes the entries at issue: the customer is being asked to overrule
            # something on file, and cannot do that fairly without seeing what it says.
            first = clashing[0]
            questions.append(Question(
                "Some of what I have on file conflicts with what you just told me, so I haven't "
                "used it. Which one should I go by?",
                source=QuestionSource(
                    str(first.get("kind") or "preference"),
                    "; ".join(str(e.get("text", "")) for e in clashing if e.get("text"))[:400],
                    file=(first.get("source") or {}).get("file"),
                    row_id=(first.get("source") or {}).get("row_id"))))
    if context.get("truncated"):
        questions.append(Question(
            "I couldn't see all of your background just now, so I may have missed something. "
            "Is there anything else I should know?",
            source=QuestionSource("preference", "some of your background could not be read in full")))
    return questions
