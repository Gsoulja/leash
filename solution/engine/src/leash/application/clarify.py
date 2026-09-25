"""The clarification loop (LEASH-123): a local draft, its open questions, the customer's answers, until nothing
blocking remains. Only then may the draft go to Viseca, which has no draft-update endpoint.

The draft is never recompiled as one text (earlier rounds showed that one answer could then change how the
instruction or another answer is read). It is the union of:
- the instruction's own reading;
- each accepted free-text answer, read on its own;
- the effects of chosen options, fixed at the moment they were chosen.
So answers only add, and every accepted answer takes effect.

A free-text answer is accepted only if it answers its question: it must be fully readable, with no unclear
part of its own, and must give that question's field. Anything else is refused with the reason, never half
applied. Before it counts, an answer is checked against everything so far (the instruction, earlier answers,
the settled uncertainty choice). An answer that adds nothing for a field already limited, that leaves no
purchase possible, or that states a different uncertainty choice becomes a blocking conflict question instead.

Question IDs are derived from the question itself. Fixed options with a deterministic effect exist for the
uncertainty choice, the split check, the shop kind, the amount as read ("Yes") and the chosen item ("Only the
item I chose"). The stored instruction stays the customer's original words.
"""

import hashlib
import re
from decimal import Decimal
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from leash.domain import mandate as m
from leash.domain.mandate import CompiledMandate, Rule, Uncertainty
from leash.policy.compiler import CatalogueItem, Classifier, Draft, Question, compile_instruction
from leash.policy.registry import REGISTRY
from leash.policy.render import describe_rule, permission_review
from leash.policy.hard_rules import mandate_to_api, rule_to_api

def optional(q: Question) -> bool:
    """Only the two offers of an extra restriction are optional; a question about the customer's own words
    (e.g. "Please confirm … only from sports shops") always blocks."""
    return q.field == m.F_SPLIT_CHECK or (q.field == m.F_MERCHANT_CATEGORY and "any kind of shop" in q.text)
_DEC = re.compile(r"\bDEC-\d{3}\b")
#: The same reference as it is written into a note: " (DEC-013)" at the end of the sentence.
_DEC_REF = re.compile(r"\s*\(DEC-\d{3}\)")
_POLICY_NOTES = {"ask": "When unsure, I ask you.", "decline": "When unsure, I decline.",
                 "approve": "When unsure, I approve."}
_UNCERTAINTY: dict[str, Uncertainty] = {"Ask me": "ask", "Decline": "decline", "Approve": "approve"}
_ANY_SHOP = "Any kind of shop"
_SPLIT = {"Yes, ask me": True, "No": False}


class AnswerError(ValueError):
    """An answer to a question the draft doesn't ask, or not one of its options."""


def question_id(q: Question) -> str:
    return "Q-" + hashlib.sha256(f"{q.field}|{q.text}".encode()).hexdigest()[:10]


def _shop_kind(draft: Draft) -> str | None:
    kinds = draft.mandate.item_categories
    return next(iter(kinds)) if kinds and len(kinds) == 1 else None


def _options(q: Question, draft: Draft) -> list[str] | None:
    if q.field == "uncertainty_policy":
        return list(_UNCERTAINTY)
    if q.field == m.F_SPLIT_CHECK:
        return list(_SPLIT)
    if q.field == m.F_ITEM_CATEGORY and _ONLY_CHOSEN_Q in q.text:
        return [_ONLY_CHOSEN]  # item mode already allows only that item: nothing to add
    if q.field == m.F_BILLING_CHF and q.text.startswith("Is CHF") and "the most I may spend" in q.text:
        return ["Yes"]  # the amount as read: nothing to add
    if q.field == m.F_MERCHANT_CATEGORY and "any kind of shop" in q.text:
        kind = _shop_kind(draft)
        return ([f"Only {kind.replace('_', ' ')} shops"] if kind else []) + [_ANY_SHOP]
    return None


def _suggested(q: Question) -> bool:  # options offered next to the customer's own words
    return q.field != "uncertainty_policy" and (q.field in (m.F_BILLING_CHF, m.F_ITEM_CATEGORY)
                                                or "conflicts with" in q.text)


def _rule_views(notes: Sequence[str], origins: Mapping[str, str] = {}) -> list[dict[str, Any]]:
    r"""How each boundary is shown to the customer, and whose it is.

    `origins` comes from the compiler, which knows whether it read a rule out of the customer's words
    or supplied it because they said nothing. The decision reference stays on the view either way: it
    records HOW we read a sentence, which is not the same claim as whose boundary it is. Guessing the
    source from a `DEC-\d{3}` in the note conflated the two, so "At most 1 item per order." — typed by
    the customer — came back as our default, inviting them to disagree with their own instruction.
    """
    views = []
    for note in notes:
        if note in _POLICY_NOTES.values():
            continue
        decision = _DEC.search(note)
        # Real provenance where we have it. Notes that did not come from a compiler reading — a rule
        # the model proposed, an option the customer picked — have none to carry, and for those the
        # old guess stands: a note citing a decision is ours. That keeps a model echoing a session
        # default (DEC-024) from being relabelled as something the customer said, which is this bug
        # pointing the other way. Narrowing the guess further needs provenance on those paths too.
        # The code is provenance, not a boundary: it stays on the view, out of the sentence a customer
        # is asked to agree to (LEASH-146). The app shows it where it explains how a draft was read.
        views.append({"text": _DEC_REF.sub("", note).rstrip(". ").strip(),
                      "source": origins.get(note) or ("team" if decision else "customer"),
                      "decision": decision.group(0) if decision else None, "tightened": False})
    return views


_ONLY_CHOSEN = "Only the item I chose"
_KEEP = "Keep what I had"  # withdraws a conflicting answer, which was never used
_ONLY_CHOSEN_Q = "only the item you chose"  # the compiler's question when a chosen item comes with other kinds


@dataclass
class _State:
    accepted: list[Draft] = field(default_factory=list)  # each accepted free-text answer, read on its own
    option_rules: list[tuple[Rule, str]] = field(default_factory=list)  # effects of chosen options, as chosen
    policy: Uncertainty | None = None  # an uncertainty choice made through answers
    closed: set[str] = field(default_factory=set)  # questions answered
    conflicts: dict[str, Question] = field(default_factory=dict)  # open conflict questions


@dataclass
class _Built:
    rules: list[Rule]
    notes: list[str]
    policy: Uncertainty
    decided: bool
    open: list[tuple[str, Question, list[str] | None]]


def _answer_fields(state: _State) -> set[str]:
    fields = {r.field for d in state.accepted for r in d.mandate.rules} | {r.field for r, _ in state.option_rules}
    if m.F_ITEM_ID in fields:
        fields.add(m.F_ITEM_CATEGORY)  # a named item answers "what kind of items"
    return fields


_STRICT: dict[Uncertainty, int] = {"approve": 0, "ask": 1, "decline": 2}


def _as_strict(policy: Uncertainty) -> list[str]:
    """Uncertainty options no looser than the choice already settled: a draft only adds to what was said."""
    return [k for k, v in _UNCERTAINTY.items() if _STRICT[v] >= _STRICT[policy]]


def _restriction(rule: Rule) -> tuple[Any, ...]:
    """What the rule actually restricts, without the bookkeeping two readers can spell differently.

    The compiler reads "At most CHF 50 per order" with `currency="CHF", scope="purchase"`; the model
    reads the same limit with neither. As whole `Rule` objects those are two rules, so the customer
    reviewed one limit twice and both were submitted to the platform. A set written in another order
    is the same restriction too.
    """
    value = rule.value
    if isinstance(value, tuple):
        value = frozenset(value)
    elif isinstance(value, Decimal):
        value = value.normalize()
    return (rule.field, rule.operator, value, rule.period_days)


def _once(rules: Sequence[Rule]) -> list[Rule]:
    """The same restriction once, keeping the first reading (the one that named its scope)."""
    seen: dict[tuple[Any, ...], Rule] = {}
    for rule in rules:
        seen.setdefault(_restriction(rule), rule)
    return list(seen.values())


#: Where one restriction ends and the next begins, in any of the four national languages. Generous on
#: purpose: over-splitting asks one more question, under-splitting drops a restriction.
_CLAUSE = re.compile(r",(?=\s)|;|:|\b(?:and|but|or|und|aber|oder|et|mais|ou|oppure|e|ma|o)\b", re.I)


def _read_by_model(q: Question, proposed: Sequence[Rule]) -> bool:
    """The compiler could not read this sentence, but the model read a rule out of it (DEC-045).

    The grammar is English-only, so "I'm not sure how to read …" and "Please confirm what … means for
    this rule" fire for every German, French and Italian sentence. Asking them there is the retired
    grammar deciding what may become a rule by the back door: measured on 2026-09-25, a correctly read
    German instruction carried six blocking questions and no answer could clear them, because a
    free-text answer has to be readable by the same grammar.

    Only a sentence the model actually read is covered. One it did not is still asked about, which is
    what keeps the omission net (DEC-045's compensating control) intact.
    """
    about = (q.about or "").strip().lower()
    if not about or not proposed:
        return False
    # Per clause, not per sentence: one rule read out of "Buy me a jacket, at most CHF 120 per order,
    # and no subscriptions." is not a reading of that sentence, and the restriction nobody read would
    # vanish silently (found in review, 2026-09-25 — DEC-056 amended).
    clauses = [c for c in _CLAUSE.split(about) if re.search(r"\w", c)]
    if clauses and len([r for r in proposed if _states(r, about)]) >= len(clauses):
        # The sentence was read, so the compiler's guess at which field it was about is answered too.
        # Its cues are keyword guesses: "Only from shops with at least 3 previous purchases on this
        # card." matched "shops" and asked about the merchant category, while the rule the model read
        # was familiarity. Seen in a live chat on 2026-09-25 as a blocking question no answer clears.
        return True
    # Sharing a field is not being read: the rule has to come from this sentence.
    return q.field != "instruction" and any(r.field == q.field and _states(r, about) for r in proposed)


def _states(rule: Rule, sentence: str) -> bool:
    """The sentence carries this rule's value, so the rule was read out of these words."""
    values = rule.value if isinstance(rule.value, tuple) else (rule.value,)
    for value in values:
        text = str(value)
        if isinstance(value, Decimal):
            text = str(value.normalize())
            if value == value.to_integral_value():
                text = str(int(value))
        if re.search(rf"(?<![0-9A-Za-z]){re.escape(text.lower())}(?![0-9A-Za-z])", sentence):
            return True
    return False


def _build(base: Draft, stated_policy: Uncertainty | None, state: _State,
           proposed: Sequence[Rule] = ()) -> _Built:
    # `proposed` are rules the model read from the customer's words that the compiler did not read the
    # same way — since DEC-045 that includes everything not written in the compiler's English grammar.
    # They are appended like any other rule, so the strictest per field still wins and a draft can only
    # get tighter. Their sentence is generated from the rule itself, never from the model's prose.
    rules = _once([*base.mandate.rules, *(r for d in state.accepted for r in d.mandate.rules),
                   *(r for r, _ in state.option_rules), *proposed])
    independently_read = {_restriction(r) for r in base.mandate.rules}
    notes = [n for n in dict.fromkeys([*base.notes, *(n for d in state.accepted for n in d.notes),
                                       *(n for _, n in state.option_rules),
                                       *(describe_rule(r) for r in proposed
                                         if _restriction(r) not in independently_read)])
             if n not in _POLICY_NOTES.values()]
    policy: Uncertainty = state.policy or stated_policy or base.mandate.uncertainty
    decided = stated_policy is not None or state.policy is not None
    notes.append(_POLICY_NOTES[policy])
    answered_fields = _answer_fields(state)
    open_: list[tuple[str, Question, list[str] | None]] = [
        (qid, q, _as_strict(policy) if q.field == "uncertainty_policy" else [_KEEP]) for qid, q in state.conflicts.items()]
    for q in base.questions:
        qid = question_id(q)
        if qid in state.closed or (q.field == "uncertainty_policy" and decided):
            continue
        if _read_by_model(q, proposed):
            continue
        if q.field in (m.F_ITEM_CATEGORY, m.F_MERCHANT_CATEGORY) and '"' not in q.text and not optional(q) \
                and q.field in answered_fields:
            continue  # asked for missing items or shops, and an answer elsewhere already gave them
        open_.append((qid, q, _options(q, base)))
    return _Built(rules, list(dict.fromkeys(notes)), policy, decided, open_)


_CENT = Decimal("0.01")
_SETS = ("merchant_categories", "item_categories", "target_item_ids", "sizes", "fulfillment")


def _unsatisfiable(mandate: CompiledMandate, catalogue: Sequence[CatalogueItem]) -> str | None:
    """Rules no purchase can meet together: an empty allowed set, or chosen items all excluded by the other
    item rules (a chosen item outside the allowed categories), or a spending limit not even CHF 0.01 can meet."""
    for name in _SETS:
        if getattr(mandate, name) == frozenset():
            return name
    for r in mandate.rules:  # a spending limit no purchase can stay within
        if r.field != m.F_BILLING_CHF:
            continue
        cap = Decimal(str(r.value))  # the smallest purchase is CHF 0.01
        if cap < _CENT if r.operator == "<=" else cap <= _CENT:
            return "billing_amount_chf"
    targets = mandate.target_item_ids
    if targets is not None and catalogue:
        kinds, excluded = mandate.item_categories, mandate.excluded_item_categories
        fits = [i for i in catalogue if i.item_id in targets and i.item_id not in mandate.excluded_item_ids
                and i.category not in excluded and (kinds is None or i.category in kinds)]
        if not fits:
            return "items"
    return None


_SENTENCE = re.compile(r"(?<=[.!?;])\s+")
_UNSURE = re.compile(r"\b(?:uncertain|unsure|in doubt|not sure)\b", re.I)


def _conflict(alone: Draft, answer: str, so_far: _Built, base: Draft,
              catalogue: Sequence[CatalogueItem]) -> str | None:
    """What of an answer can't be honoured next to everything so far: a rule that adds nothing for a field
    already limited, rules no purchase can then meet, or an uncertainty choice other than the settled one."""
    clash = _clashing_rule(alone.mandate.rules, so_far, base, catalogue)
    if clash is not None:
        return clash
    if _states_policy(alone, answer) and so_far.decided and alone.mandate.uncertainty != so_far.policy:
        return "uncertainty_policy"
    return None


def _clashing_rule(rules: Sequence[Rule], so_far: _Built, base: Draft,
                   catalogue: Sequence[CatalogueItem]) -> str | None:
    """The field of the first rule that can't be honoured next to everything so far, if any."""
    current = replace(base.mandate, rules=tuple(so_far.rules), uncertainty=so_far.policy)
    for rule in rules:
        same = lambda r: (r.field, r.operator, r.value, r.period_days) == (rule.field, rule.operator, rule.value, rule.period_days)
        if any(same(r) for r in current.rules):
            without = replace(current, rules=tuple(r for r in current.rules if not same(r)))
            if without._snapshot() == current._snapshot():  # a stricter rule overrides it: the answer can't apply
                return rule.field
            continue
        if rule.field == m.F_ITEM_CATEGORY and current.target_item_ids is not None:
            return rule.field  # next to a chosen item a kind never widens: it adds nothing or excludes the item
        after = replace(current, rules=current.rules + (rule,))
        limited = any(r.field == rule.field for r in current.rules)
        if (limited and after._snapshot() == current._snapshot()) or _unsatisfiable(after, catalogue):
            return rule.field
    return None


def _states_policy(alone: Draft, answer: str) -> bool:
    return bool(_UNSURE.search(answer)) and not any(q.field == "uncertainty_policy" for q in alone.questions)


def _default_questions(catalogue: Sequence[CatalogueItem]) -> frozenset[str]:
    return frozenset(q.text for q in compile_instruction("At most CHF 1 per order.", catalogue=catalogue).questions)


def _why_not(alone: Draft, answer: str, q: Question, catalogue: Sequence[CatalogueItem]) -> str | None:
    """None when a free-text answer answers its question; otherwise why it doesn't."""
    defaults = _default_questions(catalogue)  # what any short answer raises because it doesn't mention it
    unclear = [x.text for x in alone.questions if not optional(x) and (x.text not in defaults
               or (x.field == "uncertainty_policy" and _UNSURE.search(answer)))]  # its own wording isn't clear
    if unclear:
        return "part of your answer is unclear: " + " ".join(unclear)
    fields = {r.field for r in alone.mandate.rules}
    dropped = [p for p in _SENTENCE.split(answer) if p.strip() and not
               {r.field for r in compile_instruction(p, catalogue=catalogue).mandate.rules} <= fields]
    if dropped:  # a sentence gives a rule on its own that the whole answer loses: the sentences disagree
        return "part of your answer is unclear: these parts don't fit together: " + " ".join(dropped)
    if m.F_ITEM_ID in fields:
        fields.add(m.F_ITEM_CATEGORY)
    if q.field in ("instruction",) and (fields or not alone.questions):
        return None
    if q.field in fields:
        return None
    return "it doesn't say anything I can use for this question"


def _raise_conflict(state: _State, answer: str, clash: str) -> None:
    conflict = Question(clash, f'Your answer "{answer}" conflicts with your instruction or an earlier '
                               f"answer ({clash}): a draft can only add to what you wrote. Answer with a "
                               "rule that fits, or start a new draft to change it.")
    state.conflicts[question_id(conflict)] = conflict


def clarify(instruction: str, answers: Sequence[Mapping[str, str]],
            catalogue: Sequence[CatalogueItem], *, proposed: Sequence[Rule] = (),
            classifier: Classifier | None = None) -> dict[str, Any]:
    """The draft view (the contract's PolicyDraft without draft_id) for an instruction and its answers so far.

    Answers are replayed in order; each must answer a question that is open at that point."""
    base = compile_instruction(instruction, catalogue=catalogue, classifier=classifier)
    stated_policy = None if any(q.field == "uncertainty_policy" for q in base.questions) else base.mandate.uncertainty
    state = _State()
    replayed: list[dict[str, str]] = []  # what a caller may truthfully show as answered (LEASH-145 AC8)
    for a in answers:
        built = _build(base, stated_policy, state, proposed)
        qid, answer = a["question_id"], a["answer"].strip()
        found = next(((q, options) for i, q, options in built.open if i == qid), None)
        if found is None:
            raise AnswerError(f"{qid} is not an open question")
        q, options = found
        record = {"question_id": qid, "question": q.text, "answer": answer}
        if options is not None and (answer in options or not _suggested(q)):
            if answer not in options:
                raise AnswerError(f"answer one of: {', '.join(options)}")
            if q.field == "uncertainty_policy":
                state.policy = _UNCERTAINTY[answer]
            elif q.field == m.F_SPLIT_CHECK and _SPLIT[answer]:
                state.option_rules.append((Rule(m.F_SPLIT_CHECK, "=", "on"), "Two orders at the same shop within an "
                                           "hour that together go over the limit: I ask you (it may be one order "
                                           "split in two)."))
            elif q.field == m.F_MERCHANT_CATEGORY and answer.startswith("Only "):
                kinds = replace(base.mandate, rules=tuple(built.rules)).item_categories
                kind = next(iter(kinds)) if kinds and len(kinds) == 1 else None
                if kind:
                    rule = Rule(m.F_MERCHANT_CATEGORY, "in", (kind,))
                    clash = _clashing_rule([rule], built, base, catalogue)
                    if clash is not None:  # an option is checked like any answer before it counts
                        _raise_conflict(state, answer, clash)
                        continue
                    state.option_rules.append((rule, f"Only shops in the category {kind.replace('_', ' ')}, "
                                                     "as you answered."))
            replayed.append(record)
            state.closed.add(qid)
            state.conflicts.pop(qid, None)
            continue
        if not answer:
            raise AnswerError("the answer is empty")
        alone = compile_instruction(answer, catalogue=catalogue, classifier=classifier)
        reason = _why_not(alone, answer, q, catalogue)
        if reason is not None:
            raise AnswerError(f"\"{answer}\" doesn't answer this question: {reason}")
        clash = _conflict(alone, answer, built, base, catalogue)
        if clash is not None:  # never used and never dropped silently: the customer is told, the question stays
            _raise_conflict(state, answer, clash)
            continue
        state.accepted.append(alone)
        if _states_policy(alone, answer) and not built.decided:
            state.policy = alone.mandate.uncertainty
        replayed.append(record)
        state.closed.add(qid)
        state.conflicts.pop(qid, None)
    built = _build(base, stated_policy, state, proposed)
    mandate = replace(base.mandate, rules=tuple(built.rules), uncertainty=built.policy,
                      instruction=instruction, notes=tuple(built.notes))
    # Whose each note is, from every reading that contributed one: the instruction's own draft and
    # each accepted answer. A note the customer's words produced stays theirs even if a default added
    # the same note first.
    origins: dict[str, str] = {}
    for source in (base, *state.accepted):
        for note, who in getattr(source, "origins", {}).items():
            if who and origins.get(note) != "customer":
                origins[note] = who
    open_questions = []
    impossible = _unsatisfiable(mandate, catalogue)
    if impossible is not None:  # only an instruction that contradicts itself gets here: answers are checked first
        open_questions.append({"question_id": question_id(Question("impossible", impossible)),
                               "text": f"Your rules can't all be met together ({impossible}): no purchase could pass "
                                       "them. A draft can only add to what you wrote, so start a new draft.",
                               "blocking": True})
    for qid, q, options in built.open:
        view: dict[str, Any] = {"question_id": qid, "text": q.text, "blocking": not optional(q),
                                "field": q.field}
        if options:
            view["options"] = options
        open_questions.append(view)
    return {"instruction": instruction,
            "review": permission_review(mandate.rules, mandate.uncertainty),
            "status": "needs_answers" if any(q["blocking"] for q in open_questions) else "ready",
            "rules": _rule_views(mandate.notes, origins), "hard_rules": mandate_to_api(mandate)["hard_rules"],
            "uncertainty_policy": mandate.uncertainty, "notes": list(mandate.notes),
            "open_questions": open_questions,
            # DEC-045: what the customer did not limit. The model can silently drop a restriction and
            # every rule shown will still be correct, so the omission has to be visible (LEASH-146).
            "unrestricted": [name for name in REGISTRY if not any(r.field == name for r in mandate.rules)],
            # What this compiler read on its own, without the proposal. A caller that handed us rules
            # gets them back inside `hard_rules`, so only this tells it whether we agreed independently
            # or are simply echoing it — "the compiler agreed" would otherwise mean nothing (DEC-045).
            "independently_read": [rule_to_api(r) for r in _build(base, stated_policy, state).rules],
            # What the caller supplied, kept so a later turn or answer recompiles with it. Dropping it
            # would silently loosen the draft, which is the one direction a mandate may never move.
            "proposed": [rule_to_api(r) for r in proposed],
            # The answers this view was actually built from. A turn can drop one (its question closed or
            # was re-asked under another id), and a transcript that kept showing it would be claiming a
            # settled point the draft no longer holds.
            "answers": replayed}
