"""Instruction compiler v1: the customer's words → a draft mandate, notes on how each part was read, and
open questions for everything unclear (LEASH-065). The customer confirms the draft; only the confirmed
hard_rules are ever enforced (DEC-003, DEC-004).

The reading is deliberately conservative: a rule is produced only from wording that is unambiguous in its
own clause and not negated; anything else becomes a question, never a silent default, and never a rule
looser than the words. Amounts, periods, sizes and day counts are extracted by pattern. Shop, item,
familiarity, fulfilment, quantity and session wording go through a pluggable Classifier; the default
KeywordClassifier is deterministic. The API wires Jev behind the same port to independently check these
readings; uncertainty remains a blocking question.
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

from leash.domain import mandate as m
from leash.domain.mandate import CompiledMandate, Operator, Rule, Uncertainty
from leash.domain.money import fmt_chf

_UNITS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
          "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
          "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
         "ninety": 90}
_NEGATION = re.compile(r"\b(not|never|no|don't|dont|do not|doesn't|except|without|other than|avoid|excluding|"
                       r"nor|isn't|aren't)\b", re.I)


@dataclass(frozen=True)
class Question:
    field: str  # the hard_rule field (or "uncertainty_policy") the answer decides
    text: str
    #: The customer's own sentence this question is about, when it is about one. A reader that can
    #: read what this grammar cannot (DEC-045) needs the sentence itself to tell whether anything in
    #: it went unread — quoting it back out of `text` would be reparsing our own message.
    about: str = ""


@dataclass(frozen=True)
class Reading:
    rule: Rule
    note: str
    #: Whose boundary this is, where the reading knows. "customer" when it was read out of their own
    #: words even though the note records HOW we read them ("(DEC-013)"); "team" where we supplied it
    #: because they said nothing. `None` means this reading makes no claim and the view falls back to
    #: its older guess, so marking one site changes only that site. Provenance used to be guessed
    #: entirely from a DEC in the note, which labelled a sentence the customer typed as our
    #: suggestion and invited them to disagree with their own instruction.
    origin: str | None = None


@dataclass(frozen=True)
class CatalogueItem:
    item_id: str
    name: str
    category: str


@dataclass(frozen=True)
class Draft:
    mandate: CompiledMandate
    notes: tuple[str, ...]
    questions: tuple[Question, ...]
    #: note -> "customer" | "team". Whose each note is, so the review can say so without guessing
    #: from the note's wording.
    origins: Mapping[str, str] = field(default_factory=dict)


@dataclass
class Classified:
    readings: list[Reading] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)


class Classifier(Protocol):
    def classify(self, instruction: str, catalogue: Sequence[CatalogueItem]) -> Classified: ...


# ----- text helpers ---------------------------------------------------------------------------------------

def _number(word: str) -> int | None:
    """Digits or English number words up to ninety-nine ("twenty-one", "fourteen")."""
    word = word.lower().strip()
    if word.isdigit():
        return int(word)
    if word in _UNITS:
        return _UNITS[word]
    if word in _TENS:
        return _TENS[word]
    parts = re.split(r"[- ]", word)
    if len(parts) == 2 and parts[0] in _TENS and parts[1] in _UNITS and _UNITS[parts[1]] < 10:
        return _TENS[parts[0]] + _UNITS[parts[1]]
    return None


def _clauses(text: str) -> list[str]:
    """Sentences split into clauses at commas, semicolons, 'and' and 'but'."""
    out = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n", text):
        out += [c for c in re.split(r",(?=\s)|;|\b(?:and|but)\b", sentence) if c.strip()]
    return out


def _negated(clause: str, position: int) -> bool:
    return bool(_NEGATION.search(clause[:position]))


# ----- amounts --------------------------------------------------------------------------------------------

_AMOUNT = re.compile(r"\bCHF\s*(\d{1,3}(?:[,'’]\d{3})+|\d+)(?:[.,](\d{1,2}))?(?![\d.,'’]*\d)", re.I)
_OTHER_MONEY = re.compile(r"\b\d+(?:[.,'’]\d+)*\s*(?:CHF|francs?|fr\.?|EUR|euros?|USD|dollars?|GBP|pounds?)\b|"
                          r"(?:\bfr\.|\bEUR|\bUSD|\bGBP|€|\$|£)\s*\d|\bCHF\s+(?!\d)[a-z]+", re.I)
_INCLUSIVE_BEFORE = re.compile(r"(no more than|not more than|up to|at most|at or below|maximum of|max\.?|"
                               r"a maximum of)\s*$", re.I)
_INCLUSIVE_AFTER = re.compile(r"^\s*(?:\S+\s+)?(or less|or below|or under|max(?:imum)?)\b", re.I)
_STRICT_BEFORE = re.compile(r"(?<!at or )(less than|under|below|lower than)\s*$", re.I)
_MINIMUM_BEFORE = re.compile(r"(?<!no )(?<!not )(over|more than|above|at least|minimum of)\s*$", re.I)
_PER_ITEM = re.compile(r"\b(?:per|each|one|a single|any)\s+item\b|\bper\s+piece\b", re.I)
_PERIOD = re.compile(r"\b(?:any|over|in|within|across)\s+([\w-]+)\s+days?\b|\b(?:per|a|each|every)\s+week\b|"
                     r"\bweekly\b|\bfortnight(?:ly)?\b", re.I)
_TIME_WORDS = re.compile(r"\b(days?|daily|weeks?|weekly|weekend|months?|monthly|years?|yearly|annual(?:ly)?|"
                         r"totals?|altogether|overall|fortnight(?:ly)?|in total)\b", re.I)
# Item names are removed before looking for a spending window, but a span never crosses an amount or a
# period word, so it can't swallow a stated window. "the … I chose" has a clear end and may hold "weekly";
# an open "my …" span may not (a "weekly" there is read as a window: stricter, never looser).
_PERIOD_WORD = r"(?:daily|weekly|monthly|yearly|annual\w*|fortnight\w*)"
_SPAN_STOP = r"(?:the|my|chf|for|in|from|only|up|at|under|no|per|any|over|within|across|every|each|total)"
_CHOSEN_SPAN = re.compile(rf"\bthe\s+(?:(?!{_SPAN_STOP}\b)[\w-]+\s+){{1,6}}?i\s+(?:chose|picked|selected)\b|"
                          rf"\bmy\s+(?:(?!(?:{_SPAN_STOP}|{_PERIOD_WORD})\b)[\w-]+\s*){{1,6}}?"
                          rf"(?=\s+(?:{_SPAN_STOP}|{_PERIOD_WORD})\b|,|$)", re.I)
_PER_ORDER = re.compile(r"\b(?:each|per|every|an|a|one|a single)\s+(?:order|purchase|payment)\b", re.I)


def _amounts(text: str) -> tuple[list[Reading], list[Question]]:
    readings: list[Reading] = []
    questions: list[Question] = []
    for clause in _clauses(text):
        if len(_AMOUNT.findall(clause)) > 1:  # "CHF 20 up to CHF 50": a range, not one cap
            questions.append(Question(m.F_BILLING_CHF, f'How should "{clause.strip()}" limit spending? Please give '
                                                       "one most-per-order amount."))
            continue
        for match in _AMOUNT.finditer(clause):
            if match.group(2) and match.string[match.start(2) - 1] == ",":  # "CHF 200,5": cents or a list?
                questions.append(Question(m.F_BILLING_CHF, f'How much exactly is "{match.group(0).strip()}"? Please '
                                                           "write amounts with a point, e.g. CHF 200.50."))
                continue
            whole = re.sub(r"[,'’]", "", match.group(1))
            value = Decimal(f"{whole}.{match.group(2)}" if match.group(2) else whole)
            before, after = clause[:match.start()], clause[match.end():]
            amount = fmt_chf(value)
            if _MINIMUM_BEFORE.search(before[-20:]) or _PER_ITEM.search(clause):
                questions.append(Question(m.F_BILLING_CHF, f'How should "{clause.strip()}" limit spending? I can limit '
                                                           "each order or a total over a number of days."))
                continue
            op: Operator
            if _INCLUSIVE_BEFORE.search(before[-30:]) or _INCLUSIVE_AFTER.search(after):
                op, words = "<=", "at most"
            elif _STRICT_BEFORE.search(before[-20:]):
                op, words = "<", "under"
            else:
                op, words = "<=", "at most"
                questions.append(Question(m.F_BILLING_CHF, f"Is {amount} the most I may spend, including delivery?"))
            scan = _RETURNS.sub(" ", _CHOSEN_SPAN.sub(" ", clause))  # a return window is not a spending window
            windows = list(_PERIOD.finditer(scan))
            if len(windows) > 1:
                questions.append(Question(m.F_BILLING_CHF, f"For {amount}: over how many days in a row? I read "
                                                           "more than one period."))
                continue
            period = windows[0] if windows else None
            days: int | None = None
            if period:
                if period.group(1) is not None:
                    days = _number(period.group(1))
                else:
                    days = 14 if "fortnight" in period.group(0).lower() else 7
            if days is not None and days < 1:
                days = None
            if days is None and (period or _TIME_WORDS.search(scan)):
                questions.append(Question(m.F_BILLING_CHF, f"For {amount}: is that per order, or a total over how "
                                                           "many days in a row?"))
                continue
            if days is not None and _PER_ORDER.search(clause):
                questions.append(Question(m.F_BILLING_CHF, f"Is {amount} a limit per order or over {days} days?"))
                continue
            if days is not None:
                readings.append(Reading(Rule(m.F_BILLING_CHF, op, value, currency="CHF", scope="period",
                                             period_days=days),
                                        f"{words.capitalize()} {amount} across any {days} days (a rolling window of "
                                        "paid orders; an order waiting for you counts once you approve it)."))
            else:
                readings.append(Reading(Rule(m.F_BILLING_CHF, op, value, currency="CHF", scope="purchase"),
                                        f"{words.capitalize()} {amount} per order, delivery included."))
    if _OTHER_MONEY.search(text):
        questions.append(Question(m.F_BILLING_CHF, "I keep limits as CHF amounts written in digits (e.g. CHF 50): "
                                                   "what is your limit?"))
    return readings, questions


# ----- sizes and day counts -------------------------------------------------------------------------------

_SIZE = re.compile(r"\bsizes?\s+([0-9]{1,3}(?:[.,]5)?|x{0,2}[sml]|xl|xxl)\b"
                   r"(\s*(?:or|/|and|,|-|to)\s*(?:[0-9]{1,3}|x{0,2}[sml]|xl|xxl)\b)?", re.I)
_RETURNS = re.compile(r"\breturn(?:ed|able|s)?\s+(?:with)?in\s+(?:([\w-]+)\s+(days?|weeks?)|a\s+(fortnight))", re.I)


def _sizes_and_days(text: str) -> tuple[list[Reading], list[Question]]:
    readings: list[Reading] = []
    questions: list[Question] = []
    for clause in _clauses(text):
        for match in _SIZE.finditer(clause):
            if match.group(2) or _negated(clause, match.start()):
                questions.append(Question(m.F_SIZE, f'Which size exactly? I read "{match.group(0).strip()}".'))
                continue
            size = match.group(1).upper()
            readings.append(Reading(Rule(m.F_SIZE, "=", size), f"Size {size}, as stated by the shop."))
        for match in _RETURNS.finditer(clause):
            count = 14 if match.group(3) else _number(match.group(1))
            if count is None or _negated(clause, match.start()):
                questions.append(Question(m.F_RETURN_DAYS, f'How many days to return? I read "{match.group(0)}".'))
                continue
            days = count * 7 if match.group(2) and match.group(2).lower().startswith("week") else count
            readings.append(Reading(Rule(m.F_RETURN_DAYS, ">=", Decimal(days)),
                                    f"Returnable for at least {days} days; if the shop doesn't say, I ask you."))
    if re.search(r"\bsizes?\b", text, re.I) and not any(r.rule.field == m.F_SIZE for r in readings) \
            and not any(q.field == m.F_SIZE for q in questions):
        questions.append(Question(m.F_SIZE, "Which size exactly?"))
    if re.search(r"\breturn", text, re.I) and not any(r.rule.field == m.F_RETURN_DAYS for r in readings) \
            and not any(q.field == m.F_RETURN_DAYS for q in questions):
        questions.append(Question(m.F_RETURN_DAYS, "For how many days must the order be returnable?"))
    return readings, questions


# ----- uncertainty ----------------------------------------------------------------------------------------

_UNSURE = r"(?:uncertain|unsure|in doubt|not sure)"
_UNSURE_CUE = re.compile(r"\b(?:uncertain\w*|unsure|doubt\w*|not sure)\b", re.I)
_CHOICES: tuple[tuple[Uncertainty, str], ...] = (
    ("ask", rf"\bask me\b[\w\s]{{0,10}}\b(?:when|if)\s+{_UNSURE}|\b(?:when|if)\s+{_UNSURE},?\s+ask me\b"),
    ("decline", rf"\b(?:decline|don't buy|do not buy|skip)(?: it)?\s+(?:when|if)\s+{_UNSURE}|"
                rf"\b(?:when|if)\s+{_UNSURE},?\s+(?:just\s+)?(?:decline|don't buy|do not buy|skip)"),
    ("approve", rf"\b(?:approve|buy it|go ahead)\s+(?:when|if)\s+{_UNSURE}|"
                rf"\b(?:when|if)\s+{_UNSURE},?\s+(?:just\s+)?(?:approve|buy it|go ahead)"),
)
_NOTES = {"ask": "When unsure, I ask you.", "decline": "When unsure, I decline.", "approve": "When unsure, I approve."}


def _uncertainty(text: str) -> tuple[Uncertainty, str | None, Question | None]:
    found: set[Uncertainty] = set()
    unclear = False
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        for choice, pattern in _CHOICES:
            for match in re.finditer(pattern, sentence, re.I):
                if _negated(sentence, match.start()) or _NEGATION.search(match.group(0)) and choice == "ask":
                    unclear = True
                    continue
                found.add(choice)
                if re.search(r"\b(otherwise|unless|except|but)\b", sentence, re.I):
                    unclear = True
        if re.search(rf"\b(never|don't|do not)\b[\w\s]{{0,15}}\b(ask|approve|decline)\b[\w\s]{{0,15}}{_UNSURE}",
                     sentence, re.I):
            unclear = True
        if _UNSURE_CUE.search(sentence) and not _UNCERTAINTY_FORMS.fullmatch(sentence.strip()):
            unclear = True  # only an exact, known form of the choice is read
    if len(found) == 1 and not unclear:
        choice = next(iter(found))
        return choice, _NOTES[choice], None
    return "ask", None, Question("uncertainty_policy", "When I'm unsure about a purchase, should I ask you, decline, "
                                                       "or approve it? Until you choose, I ask you.")


# ----- keyword classification -----------------------------------------------------------------------------

_SHOP_TYPES = [
    (r"specialist sports retailer|sports? (?:shop|store|retailer)", "sporting_goods", "a specialist sports retailer"),
    (r"grocery (?:shop|store)|supermarket", "groceries", "a grocery shop"),
    (r"clothing (?:shop|store)|clothes (?:shop|store)|boutique", "clothing", "a clothing shop"),
    (r"electronics (?:shop|store|retailer)", "electronics", "an electronics shop"),
    (r"book ?(?:shop|store)", "books", "a bookshop"),
]
_ITEM_TYPES = [
    (r"\bgrocer(?:y|ies)\b", "groceries"), (r"\bcloth(?:ing|es)\b", "clothing"), (r"\bbooks?\b", "books"),
    (r"\bcosmetics\b", "cosmetics"),
    # "household" is a kind of its own ("household items"), but only describes another kind ("household groceries")
    (r"\bhousehold\b(?!\s+(?:grocer|cloth|books?\b|cosmetics|shoes?\b))", "household"),
]
_SHOES = re.compile(r"\bshoes?\b", re.I)
_NOT_A_CATEGORY = re.compile(r"\bclothes\s*(?:hanger|rack|peg|line|brush|horse)s?\b|\bbook\s*(?:shelf|case|end)s?\b",
                             re.I)
# Words that never sit between a count and "items": another number, an amount or a period ends the phrase.
_NOT_BETWEEN = (r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|a|single|chf|days?|weeks?|per|each|any|over|"
                r"in|within|across|or|less|up|to|at|most|buy|orders?|purchases?|the|my|i|chose|size)\b")
# "my X" anywhere names one item ("replace my shoes", "buy my book", "up to CHF 30 my paperback book order").
_MY_ITEM = (r"\bmy\s+(?!own\b)([\w\s-]+?)(?:\s+(?:for|in|from|up|at|under|no|over|within|per|any|and)\b|"
            r"\s*[.,;!?]|$)")
_FILLER = {"worn", "old", "new", "my", "the", "a", "an", "same", "one"}


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9-]+", text.lower())
    out = {w for w in words if w not in _FILLER}
    for w in words:  # a hyphenated word also matches its parts ("road-running" is a kind of "running")
        out |= {p for p in w.split("-") if p and p not in _FILLER}
    return out


def _find(patterns: Sequence[tuple[str, ...]], text: str) -> tuple[list[tuple[str, ...]], bool]:
    """Kinds mentioned (not negated) and whether any mention was negated."""
    kinds, negated = [], False
    for clause in _clauses(text):
        for entry in patterns:
            for match in re.finditer(entry[0], clause, re.I):
                if _negated(clause, match.start()):
                    negated = True
                elif entry[1:] not in kinds:
                    kinds.append(entry[1:])
    return kinds, negated


def _clause_match(pattern: str, text: str) -> tuple[bool, bool]:
    """(found un-negated, found negated) for a pattern, checked clause by clause."""
    found = negated = False
    for clause in _clauses(text):
        for match in re.finditer(pattern, clause, re.I):
            if _negated(clause, match.start()):
                negated = True
            else:
                found = True
    return found, negated


class KeywordClassifier:
    """Deterministic, conservative reading: a rule only from unambiguous, un-negated wording."""

    def classify(self, instruction: str, catalogue: Sequence[CatalogueItem]) -> Classified:
        t = instruction.lower()
        out = Classified()
        add, ask = out.readings.append, out.questions.append

        named = re.search(r"\bthe\s+([\w\s-]+?)\s+i\s+(?:chose|picked|selected)\b", t) or \
            re.search(r"\breplace\s+my\s+([\w\s-]+?)(?:\s+in\s+size|\s*[.,]|$)", t) or \
            re.search(_MY_ITEM, t)
        item_mode = False
        # Every "my …" and every "… I chose" names an item, whatever phrase follows it (a regex span can miss one).
        chosen = len(re.findall(r"\bi\s+(?:chose|picked|selected)\b", t)) + \
            len(re.findall(r"\bmy\s+(?!own\b)\w", t))
        if chosen > 1:  # several named items: which one this mandate buys is the customer's call
            ask(Question(m.F_ITEM_ID, "Which one item should I buy? I read several."))
            named = None
        elif chosen == 1 and named is None:  # an item was named but its name couldn't be read
            ask(Question(m.F_ITEM_ID, "Which item do you mean? I couldn't read its name."))
        if named:
            wanted = _tokens(named.group(1))
            matches = [i for i in catalogue if wanted and wanted <= _tokens(i.name)]
            if len(matches) == 1:
                item_mode = True
                add(Reading(Rule(m.F_ITEM_ID, "in", (matches[0].item_id,)),
                            f'"{named.group(1).strip()}" = {matches[0].name} (catalogue item {matches[0].item_id}).'))
            else:
                options = ", ".join(i.name for i in matches[:6]) or "nothing in the catalogue"
                ask(Question(m.F_ITEM_ID, f'Which item is "{named.group(1).strip()}"? It matches {options}.'))
        for item in catalogue:
            if re.search(rf"\bcatalogue item {re.escape(item.item_id)}\b", t, re.I):
                item_mode = True
                add(Reading(Rule(m.F_ITEM_ID, "in", (item.item_id,)),
                            f'Only catalogue item {item.item_id}: {item.name}.'))
        if item_mode or re.search(r"(?:do not|don't) add anything|nothing extra|only what i asked", t):
            add(Reading(Rule(m.F_UNREQUESTED_ITEMS, "=", Decimal("0")),
                        "Nothing extra: no add-ons, protection plans or vouchers next to what you asked for."))

        quantity_read = False
        for clause in _clauses(t):
            clause_read = False
            for match in re.finditer(r"(?<![\d.,'’])"  # never the digits after an amount's separator
                                     r"\b(one|two|three|four|five|six|seven|eight|nine|ten|\d+|a single|single)\s+"
                                     rf"(?:(?!{_NOT_BETWEEN})[\w-]+\s+){{0,6}}?(?:items?|books?)\b", clause):
                prefix = clause[:match.start()]
                if re.search(r"chf\s*$", prefix) or re.search(r"\b(per|each)\b", match.group(0)):
                    continue
                if re.search(r"\b(?:sizes?|eu)\s*$", prefix):  # "size 43 items", "at most 2 …": not a count
                    continue
                clause_read = True
                if _negated(clause, match.start()) or re.search(r"(more than|over|at least|than)\s*$", prefix):
                    ask(Question(m.F_MAX_QUANTITY, f'How many items per order? I read "{match.group(0)}".'))
                    continue
                count = 1 if "single" in match.group(1) else _number(match.group(1))
                if count is None:
                    ask(Question(m.F_MAX_QUANTITY, f'How many items per order? I read "{match.group(0)}".'))
                    continue
                quantity_read = True
                add(Reading(Rule(m.F_MAX_QUANTITY, "<=", Decimal(count)),
                            f"At most {count} item{'s' if count != 1 else ''} per order (DEC-013).",
                            origin="customer"))
                if count == 1:
                    add(Reading(Rule(m.F_MAX_PURCHASES, "<=", Decimal("1")),
                                "One purchase: a second matching order asks you first (DEC-013).",
                                origin="customer"))
            # Safety net: a clause that states a count next to "items" is read or asked, never dropped.
            bare = re.sub(r"\bchf\s*[\d.,'’]+|\b(?:any|over|within|in)\s+\S+\s+days?\b|\bsize\s+\S+", " ",
                          clause)
            if not clause_read and re.search(r"\b(?:items?|books?)\b", bare) and \
                    re.search(r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|single|dozen|couple|\d+)\b", bare):
                ask(Question(m.F_MAX_QUANTITY, f'How many items per order? I read "{clause.strip()}".'))
        if item_mode and not quantity_read:
            add(Reading(Rule(m.F_MAX_QUANTITY, "<=", Decimal("1")), "One item per order (DEC-013).",
                        origin="team"))  # item mode supplies it; they stated no count
        if item_mode:
            add(Reading(Rule(m.F_MAX_PURCHASES, "<=", Decimal("1")),
                        "One purchase: a second matching order asks you first (DEC-013).",
                        origin="team"))
        once = re.search(r"\b(?:only\s+)?(?:buy|order|purchase)\s+(?:it\s+)?once\b", t)
        if once:
            add(Reading(Rule(m.F_MAX_PURCHASES, "<=", Decimal("1")), "One purchase in total (DEC-013).",
                        origin="customer"))
        # a frequency ("2 orders per week") is asked below; any other "at most N orders" is read
        for count in re.findall(r"\bat most\s+([\w-]+)\s+(?:orders?|purchases?)\b"
                                r"(?!\s+(?:per|a|each|every)\s+(?:day|week|month|year)\b)", t):
            total = _number(count)
            if total is None or total < 1:  # a count no reader knows is asked, never dropped
                ask(Question(m.F_MAX_PURCHASES, f'How many purchases in total? I read "{count}".'))
                continue
            add(Reading(Rule(m.F_MAX_PURCHASES, "<=", Decimal(total)), f"At most {total} purchases in total."))
        if re.search(r"\b(?:\w+|\d+)\s+(?:orders?|purchases?)\s+(?:per|a|each|every)\s+(?:day|week|month|year)\b", t):
            ask(Question(m.F_MAX_PURCHASES, "How many purchases in total may I make? (I can limit purchases in total, "
                                            "or spending over a number of days.)"))

        shops, shop_negated = _find(_SHOP_TYPES, instruction)
        if len(shops) == 1 and not shop_negated:
            add(Reading(Rule(m.F_MERCHANT_CATEGORY, "in", (shops[0][0],)),
                        f'"{shops[0][1]}" = shops in the category {shops[0][0].replace("_", " ")}.'))
        purpose = None
        # the chosen item's own name ("paperback book order") names no other kind of item
        beyond_name = instruction[:named.start(1)] + instruction[named.end(1):] if item_mode and named else instruction
        if item_mode and (_find(_ITEM_TYPES, re.sub(_NOT_A_CATEGORY, "", beyond_name))[0] or _SHOES.search(beyond_name)):
            ask(Question(m.F_ITEM_CATEGORY, "Should I buy only the item you chose, or also other kinds of items?"))
        if not item_mode:
            kinds, item_negated = _find(_ITEM_TYPES, re.sub(_NOT_A_CATEGORY, "", instruction))
            shoes = bool(_SHOES.search(instruction))  # shoes are in two categories (sporting goods, clothing)
            if shoes:
                kinds = [*kinds, ("shoes",)]
            if len(kinds) == 1 and not shoes and not item_negated and not _NOT_A_CATEGORY.search(instruction):
                purpose = kinds[0][0]
                add(Reading(Rule(m.F_ITEM_CATEGORY, "in", (purpose,)),
                            f"Only {purpose.replace('_', ' ')} in the basket (a shop's category doesn't make every "
                            "item in it that kind)."))
            elif kinds:  # named, but not as one clear kind: say what was read, so it isn't mistaken for "none given"
                read = ", ".join(sorted({k[0].replace("_", " ") for k in kinds}))
                ask(Question(m.F_ITEM_CATEGORY, f"What kind of items may I buy? I read {read}, which isn't one "
                                                "kind I can limit to."))
            elif item_negated or _NOT_A_CATEGORY.search(instruction):
                ask(Question(m.F_ITEM_CATEGORY, "What kind of items may I buy? I couldn't read the kind you named."))
        if len(shops) > 1 or shop_negated:
            ask(Question(m.F_MERCHANT_CATEGORY, "Which kind of shop may I buy from?"))

        shop_words = r"(?:shops?|stores?|sellers?|merchants?|retailers?)"
        regular, regular_neg = _clause_match(rf"\b{shop_words}\b[\w\s']{{0,20}}\b(?:regular\w*|often|frequently)\b|"
                                             r"\bregular\w*\s+(?:use|shop)|\buse\s+regular\w*", t)
        before, before_neg = _clause_match(rf"\b{shop_words}\s+(?:that\s+)?i(?:'ve|\s+have)?\s+(?:already\s+)?"
                                           r"(?:used|bought from|shopped at|paid)(?:\s+\w+)?\s+before", t)
        never = re.search(rf"\b{shop_words}\b[\w\s']{{0,25}}\b(?:never|not)\b[\w\s']{{0,15}}\b(?:used|bought|shopped)", t)
        vague = re.search(rf"\b(?:familiar|usual|known|trusted|favou?rite)\s+{shop_words}", t)
        explicit_prior = re.search(r"by a regular shop i mean at least (\d+) earlier purchases on this card", t)
        if explicit_prior:
            n = int(explicit_prior.group(1))
            add(Reading(Rule(m.F_PRIOR_PURCHASES, ">=", Decimal(n)),
                        f"Only shops with at least {n} earlier purchases on this card."))
        elif regular_neg or before_neg or never or (regular and before) or (vague and not (regular or before)):
            ask(Question(m.F_PRIOR_PURCHASES, "Which shops may I use: only ones you've paid before, or any shop?"))
        elif regular:
            add(Reading(Rule(m.F_PRIOR_PURCHASES, ">=", Decimal("3")),
                        '"A shop I use regularly" = at least 3 earlier purchases there on this card (DEC-014).'))
        elif before:
            add(Reading(Rule(m.F_PRIOR_PURCHASES, ">=", Decimal("1")),
                        "Only shops you have paid before on this card (an earlier approved purchase in the run counts)."))

        delivery, delivery_neg = _clause_match(r"\bfor delivery\b|\bdelivered\b|\bdelivery only\b", t)
        pickup, pickup_neg = _clause_match(r"\bpick[- ]?up\b|\bcollect(?:ion)?\b", t)
        if delivery_neg or pickup_neg or (delivery and pickup):
            ask(Question(m.F_FULFILLMENT, "How should orders be fulfilled: delivery, pickup, or either?"))
        elif delivery:
            add(Reading(Rule(m.F_FULFILLMENT, "in", ("delivery",)),
                        "For delivery: a pickup or digital order fails this rule (DEC-022)."))
        elif pickup:
            add(Reading(Rule(m.F_FULFILLMENT, "in", ("pickup",)), "For pickup only (DEC-022)."))
        if re.search(r"someone other than me|someone else (?:is )?(?:driving|using|shopping)", t):
            add(Reading(Rule(m.F_SESSION_RISK, "<", Decimal("2")),
                        "Someone else driving = new device, bursts, night-time or a first-time country; two or more "
                        "risk points (a new device alone is two) and I ask you (DEC-024)."))
        return out


# Constructions the compiler fully understands; they are removed before the risk check below.
_SAFE = re.compile("|".join([
    r"\b(?:no|not) more than\b", r"\bat or below\b", r"\bor (?:less|below)\b", r"\bdays? or more\b",
    r"\b(?:do not|don't) add anything i (?:did not|didn't) ask for\b", r"\bsomeone other than me\b",
    r"\b(?:only )?if (?:it|the order|they) can be returned\b", r"\bnothing extra\b",
    r"\b(?:each|per|every|an?) (?:order|purchase|payment)\b", r"\bover \w+ days?\b",
    r"\b(?:shops?|stores?|sellers?|merchants?) (?:that )?i(?:'ve| have)? (?:already )?(?:used|bought from|shopped at|paid)"
    r"(?: \w+)? before\b",
    r"\bask me\b[\w\s]{0,10}\b(?:when|if) (?:uncertain|unsure|in doubt|not sure)\b",
]), re.I)
# Anything here means the sentence isn't fully understood: no rules from it, only questions.
_RISKY = re.compile("|".join([
    r"\b(?:not|never|no|nor|nothing|none|don't|dont|do not|doesn't|isn't|aren't|won't|except|excluding|without|but|"
    r"unless|if|otherwise|instead|either|minimum|min|more|above|over|exceed\w*|least|between|plus|cheaper|"
    r"hundred|thousand|million|shipping)\b",
    r"\bother than\b", r"\bor\b", r"\beach\b", r"\bper item\b", r"\bfrom chf\b", r"\bbefore (?:delivery|shipping)\b",
    r"\bof them\b", r"\d\s*[-–]\s*\d", r"\d\s*\+", r"\d\s*k\b", r"\d \d{3}\b", r"\d\.\d{3}\b", r"\d\.-",
    r"\band up\b",
]), re.I)
_CUES = [
    (r"chf|franc|fr\.|eur|usd|gbp|€|\$|£|\d|budget|spend|limit|cheap|expensive|\bdays?\b|\bweek|daily|monthly|"
     r"yearly|\btotal\b|fortnight", m.F_BILLING_CHF),
    (r"shop|store|seller|merchant|retailer|supermarket|boutique", m.F_MERCHANT_CATEGORY),
    (r"used before|bought from|regular|often|familiar|usual", m.F_PRIOR_PURCHASES),
    (r"deliver|pick ?-?up|collect|shipping", m.F_FULFILLMENT),
    (r"\bitems?\b|\bone\b|\btwo\b|single|of them", m.F_MAX_QUANTITY),
    (r"grocer|cloth|book|cosmetic|electronic|anything", m.F_ITEM_CATEGORY),
    (r"\bsizes?\b", m.F_SIZE), (r"\breturn", m.F_RETURN_DAYS), (r"\bi chose\b|\breplace\b|\bthe [\w-]+ i\b", m.F_ITEM_ID),
    (r"\bonce\b|\borders?\b|\bpurchases?\b", m.F_MAX_PURCHASES),
]


# The confidence gate is a grammar, not a word list (LEASH-065 review rounds 3 and 4): a sentence is read only
# when every clause of it is consumed, start to end, by a sequence of the phrases below. Words that are safe
# alone recombine into other meanings ("pause clothing", "ask me for delivery", "in any 7 days, buy …"),
# so no word is trusted outside a phrase the readers were built for. Anything else becomes a question.
_N = (r"(?:\d{1,4}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
      r"sixteen|seventeen|eighteen|nineteen|(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
      r"(?:-(?:one|two|three|four|five|six|seven|eight|nine))?)")
_CHF = r"chf\s*(?:\d{1,3}(?:[,'’]\d{3})+|\d{1,6})(?:[.,]\d{1,2})?"
_SHOPS = r"(?:shops?|stores?|sellers?|retailers?|merchants?)"
_ORDER = r"(?:(?:per|each|every|an?) (?:order|purchase|payment))"
_PHRASES = [
    # what to buy
    r"(?:the agent may |please )?(?:buy|order|purchase)(?: only)?",
    # a count only before "item(s)" or "book(s)", which the count reader reads; "two cosmetics" is asked
    r"(?:(?:one|two|a single) )?(?:ordinary |household |our |some )*(?:grocery items?|items? of clothing|items?|"
    r"books?)",
    r"(?:only )?(?:ordinary |household |our |some )*(?:groceries|grocery|clothing(?: for me)?|clothes|cosmetics|shoes|"
    r"running shoes)",
    r"a single (?:item of clothing|book|grocery item)",
    # amounts (the amount readers take the operator and period from these)
    rf"(?:for |and )?(?:pay |spend )?(?:no more than|not more than|at most|up to|at or below|under|less than|below) {_CHF}",
    rf"(?:for )?{_CHF}(?: or less| or below)?",
    rf"keep {_ORDER} (?:at or below|under|below) {_CHF}", r"(?:keep )?the (?:weekly )?total",
    r"(?:(?:,\s*)?including delivery|delivery included)", rf"{_ORDER}",
    rf"(?:across |over |in |within )?any {_N} days", rf"over {_N} days", r"per week", r"weekly total",
    rf"(?:at or below|at most|up to) {_CHF}",
    # shops
    r"only supermarkets?",
    rf"from (?:a |the )?{_SHOPS} (?:that )?i (?:use regularly|use regulary|often use|regularly use)",
    rf"from (?:a |the )?{_SHOPS} (?:that )?i(?:'ve| have)? (?:already )?(?:used|bought from|shopped at|paid)(?: at)? before",
    r"(?:buy )?(?:only )?from (?:a |the )?(?:specialist sports retailer|sports? (?:shop|store|retailer)|"
    r"grocery (?:shop|store)|supermarket|clothing (?:shop|store)|electronics (?:shop|store|retailer)|book ?(?:shop|store))",
    # fulfilment
    r"for delivery", r"(?:for )?pick ?-?up only",
    # sizes and returns
    r"in size (?:\d{1,3}(?:[.,]5)?|x{0,2}[sml]|xl|xxl)",
    rf"(?:and )?(?:only )?if (?:it|the order|they) can be returned within {_N} (?:days?|weeks?)(?: or more)?",
    rf"returnable within (?:{_N} (?:days?|weeks?)|a fortnight)",
    # counts
    r"(?:and )?only buy once", rf"at most {_N} (?:orders?|purchases?)", rf"at most {_N} items?",
    rf"by a regular shop i mean at least {_N} earlier purchases on this card",
    # fixed sentences of the public instructions
    r"(?:do not|don't) add anything i (?:did not|didn't) ask for", r"nothing extra",
    r"pause anything that looks like someone other than me is driving the session",
]
_UNCERTAINTY_FORMS = re.compile(
    r"^(?:ask me (?:when|if) (?:uncertain|unsure|in doubt|not sure)|(?:when|if) (?:uncertain|unsure|in doubt|not sure),? "
    r"(?:ask me|decline|approve)|(?:decline|approve) (?:when|if) (?:uncertain|unsure|in doubt|not sure))[.!]?$", re.I)


def _chosen(catalogue_words: str) -> list[str]:
    word = rf"(?:{catalogue_words}|\d+-inch|worn|old|new)"
    return [rf"the (?:{word} ){{0,5}}{word} i (?:chose|picked|selected)", rf"(?:replace )?my (?:{word} ){{0,4}}{word}"]


def _grammar(catalogue: Sequence[CatalogueItem]) -> re.Pattern[str]:
    words = sorted({w for i in catalogue for w in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", i.name.lower())},
                   key=len, reverse=True) or ["monitor"]
    phrases = _PHRASES + _chosen("|".join(re.escape(w) for w in words))
    if catalogue:
        phrases += [r"catalogue item (?:" + "|".join(re.escape(i.item_id) for i in catalogue) + r")"]
    return re.compile(rf"^\s*(?:(?:{'|'.join(phrases)})(?:\s+|\s*,\s*|$))+\s*$", re.I)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?;])\s+|\n", text) if s.strip()]


def _understood(sentence: str, grammar: re.Pattern[str]) -> bool:
    body = re.sub(r"[.!?;]+$", "", sentence.strip().lower())
    clauses = [c for c in _clauses(body) if c.strip(" ,")]  # the readers' own clause split, never a different one
    for clause in clauses:
        if not grammar.fullmatch(clause.strip(" ,")):
            return False
        # a period is read only with the amount it limits, in the same clause (never "In any 7 days, buy …")
        rest = _RETURNS.sub(" ", clause)  # the return window's own day count is not a spending period
        rest = re.sub(r"\b(?:only\s+)?if\s+(?:it|the order|they)\s+can\s+be\s+", " ", rest)
        if re.search(r"\b(?:days?|weeks?|weekly|total|fortnight)\b", rest) and "chf" not in rest:
            return False
    return bool(clauses)


def compile_instruction(instruction: str, *, catalogue: Iterable[CatalogueItem] = (),
                        classifier: Classifier | None = None) -> Draft:
    items = list(catalogue)
    readings: list[Reading] = []
    questions: list[Question] = []
    understood = []
    grammar = _grammar(items)
    text = re.sub(r",(?=[^\s\d])", ", ", instruction)  # "CHF 20,one item": the gate and readers see one text
    for sentence in _sentences(text):
        if _UNCERTAINTY_FORMS.fullmatch(sentence.strip()):
            continue  # exactly an uncertainty choice: read separately (_uncertainty)
        if _understood(sentence, grammar):
            understood.append(sentence)
            continue
        questions.append(Question("instruction", f'I\'m not sure how to read "{sentence}". Could you say it as a '
                                                 "simple rule (for example: at most CHF 50 per order)?",
                                  about=sentence))
        for cue, field_name in _CUES:
            if re.search(cue, sentence, re.I):
                questions.append(Question(field_name, f'Please confirm what "{sentence}" means for this rule.',
                                          about=sentence))
    confident = " ".join(understood)
    more, asked = _amounts(confident)
    readings += more
    questions += asked
    more, asked = _sizes_and_days(confident)
    readings += more
    questions += asked
    classified = (classifier or KeywordClassifier()).classify(confident, items)
    readings += classified.readings
    questions += classified.questions
    values: dict[tuple[str, str | None, int | None], set[object]] = {}
    for r in readings:  # the same limit stated twice differently: which one did the customer mean?
        values.setdefault((r.rule.field, r.rule.scope, r.rule.period_days), set()).add((r.rule.operator, r.rule.value))
    for (field_name, *_), seen in values.items():
        if len(seen) > 1:
            questions.append(Question(field_name, "I read more than one value for the same rule: which one applies?"))
    fields = {r.rule.field for r in readings}
    if not fields & {m.F_ITEM_ID, m.F_ITEM_CATEGORY} and not any(q.field == m.F_ITEM_CATEGORY for q in questions):
        questions.append(Question(m.F_ITEM_CATEGORY, "What kind of items may I buy?"))
    if m.F_MERCHANT_CATEGORY not in fields:
        kind = next((r.rule.value[0] for r in readings if r.rule.field == m.F_ITEM_CATEGORY
                     and isinstance(r.rule.value, tuple)), "certain")
        questions.append(Question(m.F_MERCHANT_CATEGORY, f"Should I only buy from {str(kind).replace('_', ' ')} shops, "
                                                         "or is any kind of shop fine?"))
    unparsed = len(re.findall(r"\bCHF\b", confident, re.I)) - sum(
        1 for r in readings if r.rule.field == m.F_BILLING_CHF) - sum(1 for q in questions if q.field == m.F_BILLING_CHF)
    if unparsed > 0:
        questions.append(Question(m.F_BILLING_CHF, "I couldn't read every amount: what are your limits in CHF?"))
    per_order = [r.rule.value for r in readings if r.rule.field == m.F_BILLING_CHF and r.rule.scope == "purchase"]
    if per_order and isinstance(per_order[0], Decimal):
        questions.append(Question(m.F_SPLIT_CHECK, "If two orders at the same shop within an hour together go over "
                                                   f"{fmt_chf(per_order[0])}, should I ask you (it may be one order "
                                                   "split in two)?"))
    policy, policy_note, policy_question = _uncertainty(text)
    if policy_question:
        questions.append(policy_question)
    notes = [r.note for r in readings] + ([policy_note] if policy_note else [])
    rules = tuple(dict.fromkeys(r.rule for r in readings))
    # A note the customer's words produced wins over the same note supplied as a default: if they
    # stated it, it is theirs, whichever branch happened to add it first.
    origins: dict[str, str] = {}
    for r in readings:
        if origins.get(r.note) != "customer":
            origins[r.note] = r.origin
    return Draft(CompiledMandate(instruction, rules, policy, notes=tuple(dict.fromkeys(notes))), tuple(dict.fromkeys(notes)),
                 tuple(dict.fromkeys(questions)), origins)
