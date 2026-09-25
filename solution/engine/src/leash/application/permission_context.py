"""LEASH-154: the bounded background a permission conversation may see.

The permission assistant clarifies what the customer meant. Knowing that they record a preference for
shops with returns lets it ask one good question about a jacket instead of five generic ones. That is
all background may do. A bundle never carries a rule: `hard_rules()` and `confirmed_rules()` are
empty by construction, and every entry says so (`grants_authority` is False, `role` is "data").
Rules appear only when the customer answers a question and the draft is reviewed (LEASH-123).

Four things every entry names, so a later reader can judge it:

- **scope** — which customer, account and card it belongs to, and which dataset it came from;
- **source** — the file and row it was read from, kept for the draft revision's evidence;
- **freshness** — when it was observed, or "unknown" for profile text that carries no date;
- **kind** — a recorded preference, observed history, the customer's own words, or authority they
  previously confirmed. These are not interchangeable: only the last two came from the customer.

Scope is resolved by ID (card → account → customer) and never by persona name. `data/` and
`additional-data-history/` are two unrelated populations that happen to share persona names
("Giulia Rossi" is CU0012 in one and CU1493 in the other), so a Pack only ever reads its own rows.

Money and time follow the house rules: `Decimal` throughout, each row converted with its own
currency, and simulated time only. Summaries stop at the evaluation cutoff, so a bundle built for a
purchase can never see rows that happen after it.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Literal

from leash.adapters.pack.loader import Pack, Transaction
from leash.domain import mandate as m
from leash.domain.clock import SimTime

Kind = Literal["preference", "history", "statement", "confirmed"]
Freshness = Literal["fresh", "stale", "unknown"]

# How long an observation stays current. Older history is still shown, but labelled, because a shop
# used once two years ago is a weaker reason to ask than one used last week.
STALE_AFTER = timedelta(days=180)


class UnknownScope(LookupError):
    """No such card, account or customer in this dataset. Never fall back to another persona."""


@dataclass(frozen=True)
class SourceRef:
    """Where an entry was read from, kept so a draft revision can be audited later."""

    dataset: str
    file: str
    row_id: str
    field: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {"dataset": self.dataset, "file": self.file, "row_id": self.row_id, "field": self.field}


@dataclass(frozen=True)
class Scope:
    """Whose information this is. A None card means the whole account, a None account the customer."""

    dataset: str
    customer_id: str
    account_id: str | None = None
    card_id: str | None = None

    def for_account(self) -> "Scope":
        return replace(self, card_id=None)

    def for_customer(self) -> "Scope":
        return replace(self, account_id=None, card_id=None)

    def as_dict(self) -> dict[str, str | None]:
        return {"dataset": self.dataset, "customer_id": self.customer_id,
                "account_id": self.account_id, "card_id": self.card_id}


@dataclass(frozen=True)
class ContextEntry:
    """One piece of background. It can suggest a question; it can never grant permission."""

    kind: Kind
    text: str
    scope: Scope
    source: SourceRef
    observed_at: SimTime | None = None
    freshness: Freshness = "unknown"
    merchant_id: str | None = None
    conflicting: bool = False  # the customer's current words say otherwise

    #: Profile and history text is data for the assistant to read, never instructions to follow.
    role: Literal["data"] = "data"
    #: No entry, of any kind, authorises a purchase. Confirmed authority is replayed elsewhere.
    grants_authority: bool = False

    @property
    def stale(self) -> bool:
        return self.freshness == "stale"


@dataclass(frozen=True)
class SuggestedQuestion:
    """A question the assistant may ask. Unanswered, it means nothing: silence is not acceptance."""

    text: str
    needs_confirmation: bool = False  # the answer must state an amount or a scope, not just "yes"
    source: SourceRef | None = None
    answered: bool = False
    #: Which kind of background put this question here, and the recorded words themselves. A question
    #: that reaches the customer wearing no origin reads as something they already agreed to — the one
    #: thing a preference must never look like (DEC-034). `evidence` is the entry's own text so the
    #: screen can quote it rather than paraphrase, and the customer can disagree with the actual words.
    kind: Kind | None = None
    evidence: str | None = None
    #: The rule this question is about, when it is about one. Never a rule itself: answering it is
    #: what may create one.
    field: str | None = None


@dataclass(frozen=True)
class ConfirmedPermission:
    """Authority the customer confirmed earlier, together with the scope it was recorded for.

    In a bundle it is still background: it tells the assistant what has already been settled so it
    does not ask again. It never enforces anything — the live mandate does that — and it applies
    only inside its own recorded scope. A permission recorded for one card says nothing about
    another card, and one recorded for the customer covers every card they hold.
    """

    text: str
    scope: Scope
    source: SourceRef
    confirmed_at: SimTime | None = None

    def covers(self, scope: Scope) -> bool:
        """True when `scope` lies inside the scope this permission was recorded for."""
        if (self.scope.dataset, self.scope.customer_id) != (scope.dataset, scope.customer_id):
            return False
        if self.scope.account_id is not None and self.scope.account_id != scope.account_id:
            return False
        return self.scope.card_id is None or self.scope.card_id == scope.card_id


@dataclass(frozen=True)
class HistorySummary:
    """Approved purchases only, at the cutoff, in the requested scope.

    Declines never happened, cash withdrawals are not purchases and refunds are not negative
    purchases, so none of them counts here. Refunds are reported beside the spend, never inside it:
    `refunds_chf` is the magnitude returned (the pack writes refund rows with a negative amount).
    """

    dataset: str
    customer_id: str
    account_id: str | None
    card_id: str | None
    cutoff: SimTime
    #: Most-used shops only. A summary is a summary; it never carries a whole history.
    MAX_MERCHANTS = 12

    completed_purchases: int = 0
    spend_chf: Decimal = Decimal("0.00")
    refunds_chf: Decimal = Decimal("0.00")
    declined: int = 0
    cash_withdrawals: int = 0
    merchants: Mapping[str, int] = field(default_factory=lambda: MappingProxyType({}))

    @property
    def net_of_refunds_chf(self) -> Decimal:
        """Spend minus refunds, labelled separately. Never use it as "what they spent"."""
        return self.spend_chf - self.refunds_chf

    def as_dict(self) -> dict[str, Any]:
        return {"completed_purchases": self.completed_purchases, "spend_chf": str(self.spend_chf),
                "refunds_chf": str(self.refunds_chf), "net_of_refunds_chf": str(self.net_of_refunds_chf),
                "declined": self.declined, "cash_withdrawals": self.cash_withdrawals,
                "merchants": dict(self.merchants), "cutoff": self.cutoff.at.isoformat()}


@dataclass(frozen=True)
class ContextBundle:
    """What the permission assistant is allowed to see for one clarification."""

    #: Upper bound on entries of every kind together, so a conversation never receives a whole
    #: transaction history — nor an unbounded list of earlier confirmations from its caller.
    MAX_ENTRIES = 12

    scope: Scope
    instruction: str
    summary: HistorySummary
    entries: tuple[ContextEntry, ...] = ()
    suggested_questions: tuple[SuggestedQuestion, ...] = ()
    #: True when the cap dropped entries. A reader that cannot see everything must be told, or it
    #: would treat a partial view as the whole background.
    truncated: bool = False
    #: History rows have no basket lines, so no past *item* can ever be identified from them.
    item_history: Literal["unavailable"] = "unavailable"

    def hard_rules(self) -> tuple[()]:
        """Always empty. Background is not a mandate; only a reviewed draft produces rules."""
        return ()

    def confirmed_rules(self) -> tuple[()]:
        """Always empty. A suggested question is not an answer, and no answer is not acceptance."""
        return ()

    def as_evidence(self) -> dict[str, Any]:
        """The bundle as it is retained next to a draft revision, with every source reference."""
        return {
            "scope": self.scope.as_dict(),
            "instruction": self.instruction,
            "summary": self.summary.as_dict(),
            "item_history": self.item_history,
            "truncated": self.truncated,
            "entries": [{"kind": e.kind, "text": e.text, "scope": e.scope.as_dict(),
                         "source": e.source.as_dict(), "freshness": e.freshness,
                         "observed_at": e.observed_at.at.isoformat() if e.observed_at else None,
                         "merchant_id": e.merchant_id, "conflicting": e.conflicting,
                         "grants_authority": e.grants_authority} for e in self.entries],
            "questions": [{"text": q.text, "needs_confirmation": q.needs_confirmation,
                           "answered": q.answered,
                           "source": q.source.as_dict() if q.source else None,
                           "kind": q.kind, "evidence": q.evidence}
                          for q in self.suggested_questions],
        }

    def log_line(self) -> str:
        """For ordinary logs: IDs and counts only, never persona text or a customer's own words."""
        return (f"context dataset={self.scope.dataset} customer={self.scope.customer_id} "
                f"account={self.scope.account_id} card={self.scope.card_id} "
                f"entries={len(self.entries)} questions={len(self.suggested_questions)} "
                f"purchases={self.summary.completed_purchases}")


def resolve_scope(pack: Pack, card_id: str) -> Scope:
    """card → account → customer, by ID. An unknown ID is an error, never another persona's rows."""
    card = pack.cards().get(card_id)
    if card is None:
        raise UnknownScope(f"{card_id} is not a card in {pack.dataset}")
    account = pack.accounts().get(card.account_id)
    if account is None:
        raise UnknownScope(f"{card.account_id} is not an account in {pack.dataset}")
    if account.customer_id not in pack.customers():
        raise UnknownScope(f"{account.customer_id} is not a customer in {pack.dataset}")
    return Scope(pack.dataset, account.customer_id, account.account_id, card.card_id)


# --- relevance ------------------------------------------------------------------------------------

# ponytail: a small hand-written lexicon, not an embedding. It only decides which profile lines are
# worth showing; a miss costs one unasked question, never a wrong verdict. Widen it when a demo
# scenario needs a topic it lacks.
_TOPICS: dict[str, tuple[str, ...]] = {
    "clothing": ("jacket", "coat", "dress", "shirt", "trousers", "jeans", "jumper", "shoes", "boots",
                 "clothing", "clothes", "fashion", "apparel", "wardrobe"),
    "sports": ("running", "trail", "bike", "bicycle", "cycling", "sport", "sports", "fitness", "ski"),
    "electronics": ("laptop", "monitor", "phone", "camera", "headphones", "electronics", "computer"),
    "groceries": ("groceries", "grocery", "supermarket", "food", "household"),
    "travel": ("hotel", "flight", "train", "travel", "trip", "abroad", "holiday"),
    "dining": ("restaurant", "dining", "lunch", "dinner", "cafe"),
    "health": ("pharmacy", "health", "medicine", "prescription"),
}

_WORD = re.compile(r"[a-z]+")


def _topics(text: str) -> frozenset[str]:
    words = set(_WORD.findall(text.lower()))
    return frozenset(topic for topic, cues in _TOPICS.items() if words & set(cues))


# A cue is a subject the customer may care about. When their own words already mention it, the
# assistant must not ask again — they have spoken, and background cannot reopen it.
_CUES: dict[str, tuple[str, ...]] = {
    "returns": ("return", "returns", "returnable", "refund"),
    "pickup": ("pickup", "pick-up", "collection", "collect", "in-store", "store"),
    "budget": ("budget", "usual", "normally", "spend"),
}

#: cue -> (the rule this is about, the question to ask). The field lets a draft that is *missing*
#: this restriction ask it in the customer's own terms instead of the compiler's generic wording.
_QUESTION_FOR = {
    "returns": (m.F_RETURN_DAYS,
                "You usually buy where returns are possible. Should I only buy where the order can be returned?"),
    "pickup": (m.F_FULFILLMENT,
               "You usually collect orders from a shop. Should I only buy where collection is possible?"),
}

_NEGATION = re.compile(r"\b(?:no|not|don'?t|doesn'?t|never|without|ignore|skip|forget)\b", re.I)
_CLAUSE = re.compile(r"[,;.!?]")
_PAST_ITEM = re.compile(r"\b(?:same|again|already|before|last time|usual one|repeat)\b", re.I)
_USUAL_BUDGET = re.compile(r"\b(?:usual|normal|typical|my)\b[^.,;]{0,20}\bbudget\b|\bbudget\b[^.,;]{0,20}"
                           r"\b(?:as usual|i usually)\b", re.I)


def _clause_with(instruction: str, cues: Sequence[str]) -> str | None:
    """The clause of the customer's own words that mentions one of these cues, if any."""
    for clause in _CLAUSE.split(instruction):
        words = set(_WORD.findall(clause.lower()))
        if words & set(cues):
            return clause
    return None


_PROFILE_FIELDS = ("shopping_preferences", "typical_spending", "background", "travel_pattern", "budget_style")
# Fields that describe how the customer spends rather than what they buy. They match no product
# topic, so they are shown only when the customer's own words raise the subject of a budget.
_BUDGET_FIELDS = ("budget_style", "typical_spending")


def _preference_entries(pack: Pack, scope: Scope, instruction: str) -> list[ContextEntry]:
    """Profile lines that share a topic with the request. Unrelated persona detail stays unread."""
    customer = pack.customers()[scope.customer_id]
    wanted = _topics(instruction)
    about_budget = bool(_USUAL_BUDGET.search(instruction)) or _clause_with(instruction, _CUES["budget"]) is not None
    if not wanted and not about_budget:
        return []
    entries = []
    for name in _PROFILE_FIELDS:
        text = getattr(customer, name)
        relevant = bool(_topics(text) & wanted) or (about_budget and name in _BUDGET_FIELDS)
        if not text or not relevant:
            continue
        stated = _stated_cues(instruction, text)
        entries.append(ContextEntry(
            kind="preference", text=text, scope=scope.for_customer(),
            source=SourceRef(scope.dataset, "customers.csv", customer.customer_id, name),
            observed_at=None, freshness="unknown",  # profile text carries no observation date
            conflicting=any(negated for _, negated in stated)))
    return entries


def _stated_cues(instruction: str, text: str) -> list[tuple[str, bool]]:
    """Cues this profile line raises that the customer's own words already settle, and whether
    they settled them the other way (a conflict) rather than the same way."""
    settled = []
    for cue, words in _CUES.items():
        if not set(_WORD.findall(text.lower())) & set(words):
            continue
        clause = _clause_with(instruction, words)
        if clause is not None:
            settled.append((cue, bool(_NEGATION.search(clause))))
    return settled


def _history_entries(pack: Pack, scope: Scope, rows: Sequence[Transaction], cutoff: SimTime,
                     limit: int) -> list[ContextEntry]:
    """The shops this card actually used, by merchant ID. Approved purchases only."""
    approved = [r for r in rows if r.transaction_type == "purchase" and r.status == "approved" and r.merchant_id]
    counts: dict[str, int] = {}
    last: dict[str, SimTime] = {}
    for r in approved:
        assert r.merchant_id is not None
        counts[r.merchant_id] = counts.get(r.merchant_id, 0) + 1
        if r.merchant_id not in last or r.sim_time > last[r.merchant_id]:
            last[r.merchant_id] = r.sim_time
    ranked = sorted(counts, key=lambda m: (-counts[m], m))[:limit]
    entries = []
    for merchant_id in ranked:
        seen = last[merchant_id]
        name = next(r.merchant_name for r in approved if r.merchant_id == merchant_id)
        entries.append(ContextEntry(
            kind="history", text=f"{counts[merchant_id]} approved purchases at {name}",
            scope=scope,
            source=SourceRef(scope.dataset, "authorization_history.csv", merchant_id, "merchant_id"),
            observed_at=seen,
            freshness="stale" if cutoff.at - seen.at > STALE_AFTER else "fresh",
            merchant_id=merchant_id))
    return entries


def _summarise(scope: Scope, rows: Sequence[Transaction], cutoff: SimTime) -> HistorySummary:
    purchases = [r for r in rows if r.transaction_type == "purchase" and r.status == "approved"]
    refunds = [r for r in rows if r.transaction_type == "refund" and r.status == "approved"]
    merchants: dict[str, int] = {}
    for r in purchases:
        if r.merchant_id:
            merchants[r.merchant_id] = merchants.get(r.merchant_id, 0) + 1
    return HistorySummary(
        dataset=scope.dataset, customer_id=scope.customer_id, account_id=scope.account_id,
        card_id=scope.card_id, cutoff=cutoff,
        completed_purchases=len(purchases),
        spend_chf=sum((r.billing_amount_chf for r in purchases), Decimal("0.00")),
        refunds_chf=sum((abs(r.billing_amount_chf) for r in refunds), Decimal("0.00")),
        declined=sum(1 for r in rows if r.status == "declined"),
        cash_withdrawals=sum(1 for r in rows if r.transaction_type == "cash_withdrawal"),
        merchants=MappingProxyType(dict(sorted(merchants.items(),
                                               key=lambda kv: (-kv[1], kv[0]))[:HistorySummary.MAX_MERCHANTS])))


def _questions(instruction: str, entries: Sequence[ContextEntry]) -> list[SuggestedQuestion]:
    questions: list[SuggestedQuestion] = []
    for entry in entries:
        if entry.kind != "preference":
            continue
        settled = {cue for cue, _ in _stated_cues(instruction, entry.text)}
        for cue, (field, text) in _QUESTION_FOR.items():
            if cue in settled:
                continue  # the customer already said; background does not reopen it
            if set(_WORD.findall(entry.text.lower())) & set(_CUES[cue]):
                questions.append(SuggestedQuestion(text, source=entry.source, field=field,
                                                   kind=entry.kind, evidence=entry.text))
    if _USUAL_BUDGET.search(instruction):
        # "my usual budget" is not an amount. History can show what was spent; only the customer
        # can say what the limit is, and for which orders it holds.
        questions.append(SuggestedQuestion(
            "What is your usual budget, as an amount in CHF, and does it apply per order or per week?",
            needs_confirmation=True))
    if _PAST_ITEM.search(instruction):
        # Past rows name a shop and a description, never the basket lines, so the exact item that
        # was bought cannot be recovered from them.
        questions.append(SuggestedQuestion(
            "Your history shows shops and amounts but not which items were in each order. "
            "Which product do you mean? Please confirm it.",
            needs_confirmation=True))
    return list({q.text: q for q in questions}.values())


def _confirmed_entries(scope: Scope, confirmed: Sequence[ConfirmedPermission],
                       cutoff: SimTime) -> list[ContextEntry]:
    """Earlier confirmations that cover this scope. One recorded for another card is dropped."""
    entries = []
    for permission in confirmed:
        if not permission.covers(scope):
            continue
        seen = permission.confirmed_at
        entries.append(ContextEntry(
            kind="confirmed", text=permission.text, scope=permission.scope, source=permission.source,
            observed_at=seen,
            freshness="unknown" if seen is None else ("stale" if cutoff.at - seen.at > STALE_AFTER else "fresh")))
    return entries


def build_context(pack: Pack, scope: Scope, instruction: str, *, cutoff: SimTime,
                  confirmed: Sequence[ConfirmedPermission] = ()) -> ContextBundle:
    """The bundle for one clarification: relevant background only, at the cutoff, in this scope.

    `cutoff` is simulated time. Rows after it do not exist yet for this conversation.
    `instruction` must be the customer's own words: it steers which questions are suggested, so
    passing agent or merchant text here would let untrusted text choose the questions.
    `confirmed` is what the customer settled before; each entry is admitted only if its recorded
    scope covers this one. Supplying it grants nothing — enforcement stays with the live mandate.
    """
    if scope.dataset != pack.dataset:
        raise UnknownScope(f"scope is from {scope.dataset}, pack is {pack.dataset}")
    if scope.customer_id not in pack.customers():
        raise UnknownScope(f"{scope.customer_id} is not a customer in {pack.dataset}")
    rows = [r for r in pack.transactions(card_id=scope.card_id, account_id=scope.account_id,
                                         customer_id=scope.customer_id) if r.sim_time <= cutoff]
    # Relevance order: what the customer recorded, then what they already settled, then where they
    # shopped. The total is capped, so a caller passing many confirmations squeezes history out
    # rather than growing the bundle.
    preferences = _preference_entries(pack, scope, instruction)
    settled = _confirmed_entries(scope, confirmed, cutoff)
    room = ContextBundle.MAX_ENTRIES - len(preferences) - len(settled)
    history = _history_entries(pack, scope, rows, cutoff, max(room, 0))
    found = preferences + settled + history
    entries = tuple(found[:ContextBundle.MAX_ENTRIES])
    return ContextBundle(scope=scope, instruction=instruction, summary=_summarise(scope, rows, cutoff),
                         entries=entries, suggested_questions=tuple(_questions(instruction, entries)),
                         truncated=len(found) > len(entries))
