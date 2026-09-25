import csv
from decimal import Decimal
from pathlib import Path

import pytest

from fixtures.mandates import INSTRUCTIONS, MANDATES
from leash.domain import mandate as m
from leash.domain.mandate import Rule
from leash.policy.compiler import CatalogueItem, compile_instruction
from leash.policy.registry import REGISTRY

DATA = Path(__file__).resolve().parents[4] / "data"
with (DATA / "items.csv").open(encoding="utf-8") as f:
    CATALOGUE = [CatalogueItem(r["item_id"], r["item_name"], r["item_category"]) for r in csv.DictReader(f)]


def rules_of(draft):
    return set(draft.mandate.rules)


def test_exact_catalogue_answer_is_understood_without_guessing_or_ignoring_negation():
    draft = compile_instruction("Buy only catalogue item IT0017.", catalogue=CATALOGUE)
    assert Rule(m.F_ITEM_ID, "in", ("IT0017",)) in rules_of(draft)
    assert not any(q.field == "instruction" for q in draft.questions)
    for words in ("Buy only catalogue item IT9999.", "Do not buy catalogue item IT0017."):
        refused = compile_instruction(words, catalogue=CATALOGUE)
        assert not any(r.field == m.F_ITEM_ID for r in refused.mandate.rules)
        assert refused.questions


def test_extracts_chf_200_and_size_43():
    draft = compile_instruction("Buy running shoes in size 43 for no more than CHF 200. Ask me when uncertain.",
                                catalogue=CATALOGUE)
    assert Rule(m.F_BILLING_CHF, "<=", Decimal("200"), currency="CHF", scope="purchase") in rules_of(draft)
    assert Rule(m.F_SIZE, "=", "43") in rules_of(draft)
    assert any("CHF 200.00" in n for n in draft.notes) and any("43" in n for n in draft.notes)


def test_period_limits_and_day_counts():
    draft = compile_instruction("Keep each order under CHF 120 and the total across any seven days at or below "
                                "CHF 300. Only if it can be returned within 14 days or more. Ask me when uncertain.")
    rules = rules_of(draft)
    assert Rule(m.F_BILLING_CHF, "<", Decimal("120"), currency="CHF", scope="purchase") in rules
    assert Rule(m.F_BILLING_CHF, "<=", Decimal("300"), currency="CHF", scope="period", period_days=7) in rules
    assert Rule(m.F_RETURN_DAYS, ">=", Decimal("14")) in rules


def test_unclear_shop_type_becomes_question():
    draft = compile_instruction("Buy something nice from a good shop for CHF 50 or less. Ask me when uncertain.")
    assert any(q.field == m.F_MERCHANT_CATEGORY or q.field == m.F_ITEM_CATEGORY for q in draft.questions)
    assert all(r.field != m.F_MERCHANT_CATEGORY for r in draft.mandate.rules)  # nothing silently assumed


def test_missing_uncertainty_choice_is_asked_not_defaulted_silently():
    draft = compile_instruction("Buy groceries for CHF 30 or less.")
    assert any(q.field == "uncertainty_policy" for q in draft.questions)
    assert draft.mandate.uncertainty == "ask"  # the safe choice, shown with the question


def test_decision_log_wording():
    delivery = compile_instruction("Order groceries for delivery, CHF 50 or less. Ask me when uncertain.")
    assert Rule(m.F_FULFILLMENT, "in", ("delivery",)) in rules_of(delivery)                  # DEC-022
    one = compile_instruction("Buy one grocery item for CHF 20 or less. Ask me when uncertain.")
    assert {Rule(m.F_MAX_QUANTITY, "<=", Decimal("1")), Rule(m.F_MAX_PURCHASES, "<=", Decimal("1"))} <= rules_of(one)  # DEC-013
    regular = compile_instruction("Buy groceries for CHF 20 or less from a shop I use regularly. Ask me when uncertain.")
    assert Rule(m.F_PRIOR_PURCHASES, ">=", Decimal("3")) in rules_of(regular)                # DEC-014
    before = compile_instruction("Buy clothing up to CHF 250 from shops I have used before. Ask me when uncertain.")
    assert Rule(m.F_PRIOR_PURCHASES, ">=", Decimal("1")) in rules_of(before)
    for draft, dec in ((delivery, "DEC-022"), (one, "DEC-013"), (regular, "DEC-014")):
        assert any(dec in n for n in draft.notes)


def test_decline_policy_and_items_from_the_catalogue():
    draft = compile_instruction("Buy the 27-inch monitor I chose for CHF 400 or less. If unsure, decline.",
                                catalogue=CATALOGUE)
    assert draft.mandate.uncertainty == "decline"
    assert Rule(m.F_ITEM_ID, "in", ("IT0017",)) in rules_of(draft)
    assert any("27-inch computer monitor" in n for n in draft.notes)


def test_an_ambiguous_item_becomes_a_question():
    draft = compile_instruction("Buy the monitor I chose for CHF 400 or less. Ask me when uncertain.",
                                catalogue=CATALOGUE)
    assert any(q.field == m.F_ITEM_ID for q in draft.questions)
    assert all(r.field != m.F_ITEM_ID for r in draft.mandate.rules)


@pytest.mark.parametrize("scenario", sorted(MANDATES))
def test_public_instructions_match_the_fixtures_or_ask(scenario):
    draft = compile_instruction(INSTRUCTIONS[scenario], catalogue=CATALOGUE)
    asked = {q.field for q in draft.questions}
    fixture = set(MANDATES[scenario].rules)
    missing = {r for r in fixture - rules_of(draft) if r.field not in asked}
    extra = {r for r in rules_of(draft) - fixture if r.field not in asked}
    assert not missing, f"fixture rules neither compiled nor asked about: {missing}"
    assert not extra, f"compiled rules the fixture doesn't have and no question covers: {extra}"
    assert draft.mandate.uncertainty == MANDATES[scenario].uncertainty


def test_every_produced_field_exists_in_the_registry():
    for text in INSTRUCTIONS.values():
        for rule in compile_instruction(text, catalogue=CATALOGUE).mandate.rules:
            assert rule.field in REGISTRY


# ----- review round 1: never looser than the words, unclear → question -----------------------------------

def compiled(text):
    return compile_instruction(text + " Ask me when uncertain.", catalogue=CATALOGUE)


def asked(draft, field):
    return any(q.field == field for q in draft.questions)


def billing(draft):
    return [r for r in draft.mandate.rules if r.field == m.F_BILLING_CHF]


@pytest.mark.parametrize("text, rule", [
    ("Buy cosmetics for less than CHF 30.", Rule(m.F_BILLING_CHF, "<", Decimal("30"), currency="CHF", scope="purchase")),
    ("Buy groceries for CHF 1,200 or less.", Rule(m.F_BILLING_CHF, "<=", Decimal("1200"), currency="CHF", scope="purchase")),
    ("Buy groceries for CHF 1'200 or less.", Rule(m.F_BILLING_CHF, "<=", Decimal("1200"), currency="CHF", scope="purchase")),
    ("Buy groceries, at most CHF 300 over 7 days.",
     Rule(m.F_BILLING_CHF, "<=", Decimal("300"), currency="CHF", scope="period", period_days=7)),
])
def test_amounts_are_read_exactly(text, rule):
    assert rule in set(compiled(text).mandate.rules)


@pytest.mark.parametrize("text", ["Buy groceries for 50 CHF or less.", "Buy groceries for 50 francs.",
                                  "Buy groceries for Fr. 50 or less.", "Buy groceries for CHF fifty.",
                                  "Buy groceries for $50 or less.", "Buy groceries for 50 EUR."])
def test_money_in_other_forms_is_asked_about(text):
    draft = compiled(text)
    assert asked(draft, m.F_BILLING_CHF) and not billing(draft)


@pytest.mark.parametrize("text", ["Buy groceries, CHF 300 per day.", "Buy groceries, CHF 300 per year.",
                                  "Buy groceries, at most CHF 300 in total.", "Buy groceries, CHF 300 this week in total."])
def test_an_unclear_period_is_asked_never_read_as_per_order(text):
    draft = compiled(text)
    assert asked(draft, m.F_BILLING_CHF)
    assert all(r.scope != "purchase" for r in billing(draft))


def test_periods_attach_to_their_own_clause():
    a = compiled("Buy groceries weekly, at most CHF 40 each order.")  # "weekly" apart from any amount: asked
    assert billing(a) == [] and asked(a, m.F_BILLING_CHF)
    b = compiled("Keep each order under CHF 120 and the weekly total at or below CHF 300.")
    assert set(billing(b)) == {Rule(m.F_BILLING_CHF, "<", Decimal("120"), currency="CHF", scope="purchase"),
                               Rule(m.F_BILLING_CHF, "<=", Decimal("300"), currency="CHF", scope="period", period_days=7)}


def test_day_counts_in_words_and_weeks():
    assert Rule(m.F_RETURN_DAYS, ">=", Decimal("21")) in compiled(
        "Buy shoes for CHF 100 or less, returnable within twenty-one days.").mandate.rules
    assert Rule(m.F_RETURN_DAYS, ">=", Decimal("14")) in compiled(
        "Buy shoes for CHF 100 or less, if it can be returned within 2 weeks.").mandate.rules


def test_several_sizes_are_asked():
    draft = compiled("Buy shoes in size 43 or 44 for CHF 100 or less.")
    assert asked(draft, m.F_SIZE) and all(r.field != m.F_SIZE for r in draft.mandate.rules)


@pytest.mark.parametrize("text, expected", [
    ("Buy groceries for CHF 20 or less. Never approve when uncertain.", None),
    ("Buy groceries for CHF 20 or less. If uncertain, go ahead unless it's over budget.", None),
    ("Buy groceries for CHF 20 or less. Don't ask me when uncertain, just decline.", None),
    ("Buy groceries for CHF 20 or less. Ask me when uncertain, otherwise decline.", None),
])
def test_conflicting_or_negated_uncertainty_wording_is_asked(text, expected):
    draft = compile_instruction(text, catalogue=CATALOGUE)
    assert asked(draft, "uncertainty_policy") and draft.mandate.uncertainty == "ask"


@pytest.mark.parametrize("text, field", [
    ("Buy clothing for CHF 50 or less. Never buy from a shop I have used before.", m.F_PRIOR_PURCHASES),
    ("Buy groceries for CHF 50 or less, but not from a supermarket.", m.F_MERCHANT_CATEGORY),
    ("Buy something for CHF 50 or less. Don't buy clothing.", m.F_ITEM_CATEGORY),
    ("Buy anything except books for CHF 50 or less.", m.F_ITEM_CATEGORY),
    ("Order groceries for CHF 50 or less, not for delivery.", m.F_FULFILLMENT),
    ("Buy groceries for CHF 50 or less; it's fine to buy more than one item.", m.F_MAX_QUANTITY),
    ("Buy clothing for CHF 50 or less from new shops I have never used before.", m.F_PRIOR_PURCHASES),
])
def test_negated_wording_never_becomes_the_opposite_rule(text, field):
    draft = compiled(text)
    assert all(r.field != field for r in draft.mandate.rules), draft.mandate.rules
    assert asked(draft, field)


@pytest.mark.parametrize("text, field", [
    ("Buy a clothes hanger for CHF 20 or less.", m.F_ITEM_CATEGORY),
    ("Buy a book or some clothing for CHF 50 or less.", m.F_ITEM_CATEGORY),
    ("Buy food from a grocery store or a sports shop for CHF 50 or less.", m.F_MERCHANT_CATEGORY),
    ("Buy the running shoes I chose for CHF 150 or less.", m.F_ITEM_ID),
])
def test_guesses_become_questions(text, field):
    draft = compiled(text)
    assert all(r.field != field for r in draft.mandate.rules), draft.mandate.rules
    assert asked(draft, field)


def test_no_rules_nobody_asked_for():
    draft = compiled("Buy groceries, but no one item over CHF 10.")
    assert all(r.field not in (m.F_MAX_QUANTITY, m.F_MAX_PURCHASES) for r in draft.mandate.rules)
    assert asked(draft, m.F_BILLING_CHF)  # a per-item limit isn't a rule the engine has: asked


@pytest.mark.parametrize("text, rule", [
    ("Buy two grocery items for CHF 50 or less.", Rule(m.F_MAX_QUANTITY, "<=", Decimal("2"))),
    ("Buy groceries for CHF 50 or less, pick up only.", Rule(m.F_FULFILLMENT, "in", ("pickup",))),
    ("Buy groceries for CHF 50 or less from a shop I use regulary.", Rule(m.F_PRIOR_PURCHASES, ">=", Decimal("3"))),
    ("Buy groceries for CHF 50 or less from shops I often use.", Rule(m.F_PRIOR_PURCHASES, ">=", Decimal("3"))),
    ("Buy groceries for CHF 50 or less from a store I've used before.", Rule(m.F_PRIOR_PURCHASES, ">=", Decimal("1"))),
])
def test_stated_limits_are_kept(text, rule):
    assert rule in set(compiled(text).mandate.rules)


def test_an_order_frequency_is_asked():
    draft = compiled("Buy groceries for CHF 50 or less, one order per week.")
    assert asked(draft, m.F_MAX_PURCHASES)


# ----- review round 2: a sentence with anything the compiler doesn't fully understand yields no rules -------

RISKY = [
    ("Spend no less than CHF 50 on groceries.", m.F_BILLING_CHF),
    ("Buy groceries, not less than CHF 20 per order.", m.F_BILLING_CHF),
    ("Buy groceries, never under CHF 20.", m.F_BILLING_CHF),
    ("Buy groceries, do not go below CHF 20.", m.F_BILLING_CHF),
    ("Buy groceries, nothing below CHF 20.", m.F_BILLING_CHF),
    ("Buy groceries, not more than CHF 50 and not less than CHF 10.", m.F_BILLING_CHF),
    ("Buy groceries and don't worry about staying under CHF 50.", m.F_BILLING_CHF),
    ("Buy groceries for CHF 50 or more.", m.F_BILLING_CHF),
    ("Buy groceries for CHF 50 and up.", m.F_BILLING_CHF),
    ("Buy groceries, CHF 50+.", m.F_BILLING_CHF),
    ("Buy groceries, CHF 50 minimum.", m.F_BILLING_CHF),
    ("Buy groceries, orders must exceed CHF 50.", m.F_BILLING_CHF),
    ("Buy groceries, no cheaper than CHF 20.", m.F_BILLING_CHF),
    ("Buy groceries between CHF 20 and CHF 50.", m.F_BILLING_CHF),
    ("Buy groceries from CHF 20 to CHF 50.", m.F_BILLING_CHF),
    ("Buy groceries for CHF 20-50.", m.F_BILLING_CHF),
    ("If it's organic, up to CHF 80, otherwise up to CHF 50.", m.F_BILLING_CHF),
    ("CHF 50 is not my limit, CHF 80 is.", m.F_BILLING_CHF),
    ("Buy groceries up to CHF 1.200 per order.", m.F_BILLING_CHF),
    ("Buy groceries up to CHF 49.999 per order.", m.F_BILLING_CHF),
    ("Buy groceries up to CHF 50.- per order.", m.F_BILLING_CHF),
    ("Buy groceries up to CHF 1 200.", m.F_BILLING_CHF),
    ("Buy groceries up to CHF 5 hundred.", m.F_BILLING_CHF),
    ("Buy groceries up to CHF 50k.", m.F_BILLING_CHF),
    ("Buy groceries up to CHF 50 each.", m.F_BILLING_CHF),
    ("Buy groceries up to CHF 50 excluding delivery.", m.F_BILLING_CHF),
    ("Buy groceries up to CHF 50 plus shipping.", m.F_BILLING_CHF),
    ("Buy groceries up to CHF 50 before delivery.", m.F_BILLING_CHF),
    ("Buy groceries up to CHF 50 per item.", m.F_MAX_QUANTITY),
    ("Buy anything but clothing for CHF 100 or less.", m.F_ITEM_CATEGORY),
    ("Buy clothing other than socks for CHF 100 or less.", m.F_ITEM_CATEGORY),
    ("Don't buy the 27-inch monitor I chose.", m.F_ITEM_ID),
    ("Never replace my headphones.", m.F_ITEM_ID),
    ("Buy anything other than the 27-inch monitor I chose.", m.F_ITEM_ID),
    ("Buy groceries from a shop I do not use regularly.", m.F_PRIOR_PURCHASES),
    ("Buy groceries; delivery or pickup is fine.", m.F_FULFILLMENT),
    ("Buy one or two grocery items.", m.F_MAX_QUANTITY),
    ("Buy the 27-inch monitor I chose, two of them.", m.F_ITEM_ID),
]


@pytest.mark.parametrize("text, field", RISKY)
def test_a_sentence_not_fully_understood_yields_no_rules_only_questions(text, field):
    draft = compiled(text)
    sentence_rules = [r for r in draft.mandate.rules if r.field != m.F_ITEM_CATEGORY or field == m.F_ITEM_CATEGORY]
    assert all(r.field != field for r in draft.mandate.rules), draft.mandate.rules
    assert asked(draft, field), [q.field for q in draft.questions]
    assert asked(draft, "instruction")
    assert sentence_rules is not None


@pytest.mark.parametrize("text, field", [
    ("Buy groceries up to CHF 60, returnable within a month.", m.F_RETURN_DAYS),
    ("Buy shoes up to CHF 100 in size EU 42.", m.F_SIZE),
    ("Buy shoes up to CHF 100, any size except XL.", m.F_SIZE),
    ("Buy groceries up to CHF 60 from familiar shops only.", m.F_PRIOR_PURCHASES),
    ("Replace my headphones and my monitor for CHF 300 or less.", m.F_ITEM_ID),
])
def test_cues_without_a_clear_reading_are_asked(text, field):
    draft = compiled(text)
    assert all(r.field != field for r in draft.mandate.rules)
    assert asked(draft, field)


def test_named_items_that_dont_match_add_no_single_purchase_rules():
    draft = compiled("Replace my headphones and my monitor for CHF 300 or less.")
    assert all(r.field not in (m.F_MAX_QUANTITY, m.F_MAX_PURCHASES) for r in draft.mandate.rules)


@pytest.mark.parametrize("text, rule", [
    ("Buy a single item of clothing for CHF 80 or less.", Rule(m.F_MAX_QUANTITY, "<=", Decimal("1"))),
    ("Buy groceries for CHF 60 or less, and only buy once.", Rule(m.F_MAX_PURCHASES, "<=", Decimal("1"))),
    ("Buy groceries for CHF 60 or less, at most 2 orders.", Rule(m.F_MAX_PURCHASES, "<=", Decimal("2"))),
    ("Buy shoes for CHF 100 or less, returnable within a fortnight.", Rule(m.F_RETURN_DAYS, ">=", Decimal("14"))),
])
def test_more_stated_limits_are_read(text, rule):
    assert rule in set(compiled(text).mandate.rules)


def test_familiarity_split_across_and_is_asked():
    draft = compiled("Buy groceries for CHF 60 or less from shops I have bought from before and use regularly.")
    assert all(r.field != m.F_PRIOR_PURCHASES for r in draft.mandate.rules) and asked(draft, m.F_PRIOR_PURCHASES)


# ----- review round 3: the gate is an allow-list; any word it doesn't know makes the sentence a question -------

ROUND_3 = [
    ("Buy groceries, CHF 50 or less, in all.", m.F_BILLING_CHF),
    ("Buy groceries, CHF 50 or less, combined.", m.F_BILLING_CHF),
    ("Buy groceries, CHF 50 or less, cumulatively.", m.F_BILLING_CHF),
    ("Buy groceries, CHF 50 or less, summed up.", m.F_BILLING_CHF),
    ("Buy groceries, CHF 50 or less, for all orders together.", m.F_BILLING_CHF),
    ("Buy groceries, CHF 50 or less, across all my orders.", m.F_BILLING_CHF),
    ("Buy groceries for CHF 50 or less til Friday.", m.F_BILLING_CHF),
    ("Buy groceries for CHF 50 or less until Sunday.", m.F_BILLING_CHF),
    ("Buy groceries for CHF 50 or less, for the whole year.", m.F_BILLING_CHF),
    ("Buy groceries starting at CHF 50.", m.F_BILLING_CHF),
    ("Buy groceries upwards of CHF 50.", m.F_BILLING_CHF),
    ("Buy groceries worth CHF 50 or less, lowest CHF 20.", m.F_BILLING_CHF),
    ("Buy groceries, CHF 50 or less is too cheap.", m.F_BILLING_CHF),
    ("Buy groceries for CHF 20 through CHF 50.", m.F_BILLING_CHF),
    ("Buy groceries for CHF 20 up to CHF 50.", m.F_BILLING_CHF),
    ("Buy groceries for CHF 20 – CHF 50.", m.F_BILLING_CHF),
    ("Buy groceries for CHF 20 to 50.", m.F_BILLING_CHF),
    ("Buy groceries for just shy of CHF 50.", m.F_BILLING_CHF),
    ("Buy groceries. Stop short of CHF 30.", m.F_BILLING_CHF),
    ("Buy shoes up to CHF 100, size L too big.", m.F_SIZE),
    ("Buy shoes up to CHF 100, size M is too small.", m.F_SIZE),
    ("Buy shoes up to CHF 100, size M for me and size L for my brother.", m.F_SIZE),
    ("Buy shoes up to CHF 100, returns within 14 days are irrelevant.", m.F_RETURN_DAYS),
    ("Buy anything save for books, CHF 50 or less.", m.F_ITEM_CATEGORY),
    ("Buy groceries for CHF 50 or less save for delivery orders.", m.F_FULFILLMENT),
    ("Buy groceries for CHF 50 or less, barring pickup.", m.F_FULFILLMENT),
    ("Forbid pickup orders. Buy groceries for CHF 50 or less.", m.F_FULFILLMENT),
    ("Refrain from buying groceries. CHF 50 or less.", m.F_ITEM_CATEGORY),
    ("Skip shops I've used before. Buy groceries for CHF 50 or less.", m.F_PRIOR_PURCHASES),
    ("Buy groceries for CHF 50 or less, hardly ever from shops I've used before.", m.F_PRIOR_PURCHASES),
    ("Choose delivery rather than pickup. Buy groceries for CHF 50 or less.", m.F_FULFILLMENT),
    ("Should it be clothing, CHF 80 or less.", m.F_ITEM_CATEGORY),
    ("Buy groceries for CHF 50 or less, a dozen items.", m.F_MAX_QUANTITY),
    ("Buy groceries for CHF 50 or less, twenty items.", m.F_MAX_QUANTITY),
    ("Buy groceries for CHF 50 or less, up to three orders.", m.F_MAX_PURCHASES),
    ("Buy groceries for CHF 50 or less, three orders max.", m.F_MAX_PURCHASES),
    ("Buy two items per order, three orders. CHF 50 or less.", m.F_MAX_PURCHASES),
    ("Buy groceries for CHF 50 or less from shops I've used before five times.", m.F_PRIOR_PURCHASES),
    ("Buy groceries for CHF 50 or less. Exclude delivery.", m.F_FULFILLMENT),
    ("Buy groceries for CHF 50 or less. Skip delivery orders.", m.F_FULFILLMENT),
    ("Buy groceries for CHF 50 or less. Refrain from delivery orders.", m.F_FULFILLMENT),
    ("Buy groceries for CHF 50 or less, as long as it is picked up.", m.F_FULFILLMENT),
    ("Buy groceries for CHF 50 or less, delivery/pickup.", m.F_FULFILLMENT),
    ("Buy groceries for CHF 50 or less, pickup & delivery.", m.F_FULFILLMENT),
    ("Buy groceries for CHF 50 or less. Delivery is fine. Pickup is fine as well.", m.F_FULFILLMENT),
    ("Buy groceries for CHF 50 or less from shops I've used before, new shops are ok.", m.F_PRIOR_PURCHASES),
    ("Buy the 27-inch monitor I chose and the headphones I chose for CHF 400 or less.", m.F_ITEM_ID),
    ("Buy groceries for CHF 50 or less. Buy the 27-inch monitor I chose.", m.F_ITEM_CATEGORY),
]


@pytest.mark.parametrize("text, field", ROUND_3)
def test_wording_outside_the_allow_list_is_asked_never_drafted(text, field):
    draft = compiled(text)
    assert all(r.field != field for r in draft.mandate.rules), draft.mandate.rules
    assert asked(draft, field) or asked(draft, "instruction"), [q.field for q in draft.questions]


@pytest.mark.parametrize("text", [
    "Buy groceries for CHF 20 or less. If unsure, skip asking and approve.",
    "Buy groceries for CHF 20 or less. Ask me when uncertain; in case of doubt approve.",
])
def test_uncertainty_wording_outside_the_known_forms_is_asked(text):
    draft = compiled(text)
    assert asked(draft, "uncertainty_policy") and draft.mandate.uncertainty == "ask"


# ----- review round 4: allowed words recombine; every clause must be a known phrase sequence ----------------

ROUND_4 = [
    ("Pause clothing. Buy anything for CHF 50 or less.", m.F_ITEM_CATEGORY),
    ("Stop clothing. Buy anything for CHF 50 or less.", m.F_ITEM_CATEGORY),
    ("Stop anything that looks like clothing. Buy anything for CHF 50 or less.", m.F_ITEM_CATEGORY),
    ("Stop pickup. Buy groceries for CHF 50 or less.", m.F_FULFILLMENT),
    ("Pause shops I've used before. Buy groceries for CHF 50 or less.", m.F_PRIOR_PURCHASES),
    ("Buy anything for CHF 50 or less. Ask me for clothing.", m.F_ITEM_CATEGORY),
    ("Buy groceries for CHF 50 or less. Ask me for delivery.", m.F_FULFILLMENT),
    ("Buy groceries for CHF 50 or less. Ask me before pickup.", m.F_FULFILLMENT),
    ("In any 7 days, buy groceries for at most CHF 300.", m.F_BILLING_CHF),
    ("Weekly, buy groceries for at most CHF 300.", m.F_BILLING_CHF),
    ("Within 30 days, spend at most CHF 300 for groceries.", m.F_BILLING_CHF),
    ("Spend at most CHF 300 for groceries. Over 7 days.", m.F_BILLING_CHF),
    ("Buy groceries for at most CHF 300 per shop.", m.F_BILLING_CHF),
    ("Buy groceries for at most CHF 300 per session.", m.F_BILLING_CHF),
    ("Buy groceries for at most CHF 300 across shops I've used before.", m.F_BILLING_CHF),
    ("Buy groceries, two items a week.", m.F_MAX_QUANTITY),
    ("Buy groceries, at most two items any 7 days.", m.F_MAX_QUANTITY),
    ("Buy groceries once, at most CHF 50.", m.F_MAX_PURCHASES),
    ("Buy groceries for CHF 50 or less, a single purchase.", m.F_MAX_PURCHASES),
    ("Buy groceries for CHF 50 or less, delivery orders only.", m.F_FULFILLMENT),
    ("Buy groceries for CHF 50 or less, only delivery.", m.F_FULFILLMENT),
    ("Buy groceries for CHF 50 or less from shops I've used before, regularly.", m.F_PRIOR_PURCHASES),
    ("Buy groceries for CHF 50 or less. Pickup only, ask me when unsure.", m.F_FULFILLMENT),
    ("Buy groceries for CHF 50 or less. Buy it once, ask me when unsure.", m.F_MAX_PURCHASES),
    ("Buy shoes for CHF 100 or less. Size forty-three, ask me when unsure.", m.F_SIZE),
    ("Buy shoes for CHF 100 or less. Returnable within thirty days, ask me when unsure.", m.F_RETURN_DAYS),
    ("Buy a weekly grocery basket for CHF 50 or less.", m.F_BILLING_CHF),
]


@pytest.mark.parametrize("text, field", ROUND_4)
def test_every_clause_must_be_a_known_phrase_sequence(text, field):
    draft = compiled(text)
    assert all(r.field != field for r in draft.mandate.rules) or asked(draft, field), draft.mandate.rules
    assert asked(draft, field) or asked(draft, "instruction"), [q.field for q in draft.questions]


def test_a_single_book_is_one_item_and_one_purchase():
    rules = set(compiled("Buy a single book for CHF 30 or less.").mandate.rules)
    assert Rule(m.F_MAX_QUANTITY, "<=", Decimal("1")) in rules and Rule(m.F_MAX_PURCHASES, "<=", Decimal("1")) in rules


def test_a_zero_day_period_is_asked_never_a_crash():
    draft = compiled("Buy groceries for CHF 300 or less in 0 days.")
    assert asked(draft, m.F_BILLING_CHF) or asked(draft, "instruction")


@pytest.mark.parametrize("text", [
    "Buy groceries for CHF 50 or less. Ask me nothing when unsure.",
    "Buy groceries for CHF 50 or less. Ask me or buy if unsure.",
])
def test_uncertainty_wording_must_be_exactly_a_known_form(text):
    assert asked(compiled(text), "uncertainty_policy")


@pytest.mark.parametrize("text, field", [
    ("Buy groceries for CHF 50 or less. Buy clothing for CHF 300 or less.", m.F_BILLING_CHF),
    ("Buy two items for CHF 50 or less, one grocery item, one clothing item.", m.F_MAX_QUANTITY),
])
def test_two_different_limits_for_the_same_thing_are_asked(text, field):
    assert asked(compiled(text), field)


# ----- review round 5 -------------------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Buy groceries up to CHF 300 in any 0 days.",
    "Buy groceries up to CHF 300 over 0 days.",
    "Buy groceries for CHF 300 or less across any 0 days.",
])
def test_a_zero_day_window_is_asked_never_a_crash(text):
    draft = compiled(text)
    assert all(r.field != m.F_BILLING_CHF or r.scope != "period" for r in draft.mandate.rules)
    assert asked(draft, m.F_BILLING_CHF)


@pytest.mark.parametrize("text", [
    "Keep the weekly total at or below CHF 300 in any 30 days.",
    "Buy groceries up to CHF 300 per week in any 30 days.",
    "Buy groceries up to CHF 300 in any 7 days over 30 days.",
    "Keep the total across any seven days at or below CHF 300 across any 30 days.",
    "Keep each order under CHF 120 and the weekly total at or below CHF 300 over 30 days.",
])
def test_two_windows_for_one_amount_are_asked(text):
    draft = compiled(text)
    assert all(r.scope != "period" for r in draft.mandate.rules if r.field == m.F_BILLING_CHF)
    assert asked(draft, m.F_BILLING_CHF)


@pytest.mark.parametrize("text, days", [
    ("Buy groceries only if they can be returned within 7 days for CHF 300 or less in any 30 days.", 30),
    ("Buy groceries returnable within 1 day up to CHF 300 in any 30 days.", 30),
])
def test_a_return_window_is_never_read_as_the_spending_window(text, days):
    periods = [r.period_days for r in compiled(text).mandate.rules if r.field == m.F_BILLING_CHF]
    assert periods == [days]


def test_a_return_window_next_to_an_amount_is_not_a_spending_window():
    rules = compiled("Buy groceries for CHF 50 or less returnable within thirty days.").mandate.rules
    assert Rule(m.F_BILLING_CHF, "<=", Decimal("50"), currency="CHF", scope="purchase") in rules


@pytest.mark.parametrize("text, count", [
    ("Buy groceries for CHF 50 or less, at most seventy orders.", 70),
    ("Buy groceries for CHF 50 or less, at most eighty purchases.", 80),
])
def test_purchase_counts_in_words_are_read(text, count):
    assert Rule(m.F_MAX_PURCHASES, "<=", Decimal(count)) in set(compiled(text).mandate.rules)


@pytest.mark.parametrize("text", [
    "Buy groceries for CHF 50 or less, at most 5 orders, at most 2 purchases.",
    "Buy groceries for CHF 50 or less, at most 5 orders. At most 2 orders.",
    "Buy a single book for CHF 30 or less, at most 3 orders.",
])
def test_purchase_counts_are_read_or_asked_never_dropped(text):
    draft = compiled(text)
    counts = {r.value for r in draft.mandate.rules if r.field == m.F_MAX_PURCHASES}
    assert asked(draft, m.F_MAX_PURCHASES) or asked(draft, "instruction"), (counts, draft.questions)


@pytest.mark.parametrize("text, field", [
    ("Buy shoes for CHF 100 or less in size 43 in size 44.", m.F_SIZE),
    ("Buy shoes for CHF 100 or less in size 43. Buy shoes in size 44.", m.F_SIZE),
    ("Buy shoes for CHF 100 or less, returnable within 14 days, returnable within 30 days.", m.F_RETURN_DAYS),
    ("Buy groceries for CHF 300 or less per week. Buy groceries for CHF 100 or less per week.", m.F_BILLING_CHF),
])
def test_two_different_values_for_one_rule_are_asked(text, field):
    assert asked(compiled(text), field)


def test_an_amount_without_a_thousands_separator_is_read():
    assert Rule(m.F_BILLING_CHF, "<=", Decimal("1200"), currency="CHF", scope="purchase") in set(
        compiled("Buy groceries for CHF 1200 or less.").mandate.rules)


def test_an_item_name_is_never_read_as_a_spending_window():
    text = "Buy the weekly grocery basket I chose for CHF 80 or less."
    assert all(r.scope != "period" for r in compiled(text).mandate.rules if r.field == m.F_BILLING_CHF)
    # an open "my …" span may not hold a period word: read as a 7-day window, stricter, never looser
    rules = compiled("Buy my weekly grocery basket for CHF 80 or less.").mandate.rules
    assert [r.period_days for r in rules if r.field == m.F_BILLING_CHF] == [7]


# ----- review round 6 -------------------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Buy my city day pass per week up to CHF 30.",
    "Buy my computer monitor over 30 days at most CHF 400.",
    "Buy my running socks any 7 days at most CHF 40.",
    "Keep the weekly total at or below CHF 300 buy the running socks I chose.",
    "Keep the total at or below CHF 300 over 7 days buy the 27-inch computer monitor I chose.",
    "Buy groceries up to CHF 300, over 30 days if they can be returned within 14 days.",
    "Buy groceries up to CHF 300, returnable within 14 days per week.",
    "Buy groceries up to CHF 300, per week only if they can be returned within 14 days.",
    "Buy groceries at most CHF 300, the weekly total returnable within 14 days.",
])
def test_a_stated_period_is_never_silently_dropped(text):
    draft = compiled(text)
    per_order = [r for r in draft.mandate.rules if r.field == m.F_BILLING_CHF and r.scope == "purchase"]
    assert not per_order or asked(draft, m.F_BILLING_CHF) or asked(draft, "instruction"), (draft.mandate.rules,
                                                                                            draft.questions)


@pytest.mark.parametrize("text", [
    "Buy the running socks I chose, two items, for CHF 30 or less.",
    "Replace my running socks, two items, for CHF 30 or less.",
])
def test_a_chosen_item_is_one_purchase_even_with_a_quantity(text):
    assert Rule(m.F_MAX_PURCHASES, "<=", Decimal("1")) in set(compiled(text).mandate.rules)


@pytest.mark.parametrize("text", [
    "Buy groceries under CHF 50 per order, at most CHF 80 per order.",
    "Buy groceries up to CHF 300 per week, under CHF 500 over 7 days.",
])
def test_the_same_limit_with_different_operators_is_asked(text):
    assert asked(compiled(text), m.F_BILLING_CHF)


def test_a_period_word_in_an_open_item_name_is_read_or_asked_never_dropped():
    draft = compiled("Buy my monthly learning subscription up to CHF 30.")
    per_order = [r for r in draft.mandate.rules if r.field == m.F_BILLING_CHF and r.scope == "purchase"]
    assert not per_order or asked(draft, m.F_BILLING_CHF)


# ----- review round 7 -------------------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Buy groceries in any 7 days,and up to CHF 300.",
    "Buy groceries over 7 days,and up to CHF 300.",
    "Buy groceries in any seven days,and at or below CHF 300.",
    "Keep the weekly total,and at most CHF 300 buy groceries.",
    "Buy groceries up to CHF 300! Per week.",
])
def test_a_period_split_from_its_amount_is_asked_under_billing(text):
    draft = compiled(text)
    per_order = [r for r in draft.mandate.rules if r.field == m.F_BILLING_CHF and r.scope == "purchase"]
    assert not per_order or asked(draft, m.F_BILLING_CHF), (draft.mandate.rules, draft.questions)


@pytest.mark.parametrize("text, count", [
    ("Buy clothing up to CHF 80 two items.", 2),
    ("Buy clothing for CHF 80 or less two items.", 2),
    ("Buy groceries up to CHF 50 per order two items.", 2),
    ("Buy groceries for CHF 20 or less one item.", 1),
    ("Buy groceries up to CHF 50 a single item.", 1),
    ("Buy clothing up to CHF 300 across any 7 days two items.", 2),
    ("Buy groceries up to CHF 300 in any 7 days buy one item.", 1),
])
def test_an_item_count_is_read_from_its_own_number(text, count):
    draft = compiled(text)
    quantities = {r.value for r in draft.mandate.rules if r.field == m.F_MAX_QUANTITY}
    assert quantities == {Decimal(count)} or asked(draft, m.F_MAX_QUANTITY), (quantities, draft.questions)
    if count == 1 and quantities == {Decimal(1)}:
        assert Rule(m.F_MAX_PURCHASES, "<=", Decimal("1")) in set(draft.mandate.rules)


@pytest.mark.parametrize("text", [
    "Buy clothing at most 3 orders per order under CHF 50.",
    "Buy groceries at most 2 orders each order up to CHF 50.",
    "Buy clothing at most 3 purchases a purchase under CHF 50.",
])
def test_at_most_n_orders_is_read_even_next_to_per_order_wording(text):
    draft = compiled(text)
    assert any(r.field == m.F_MAX_PURCHASES for r in draft.mandate.rules) or asked(draft, m.F_MAX_PURCHASES)


@pytest.mark.parametrize("text", [
    "Buy my book for CHF 30 or less.",
    "Buy my paperback book order for CHF 30 or less.",
    "Buy my seasonal clothing order for CHF 30 or less.",
])
def test_buy_my_item_is_an_item_never_a_whole_category(text):
    draft = compiled(text)
    assert all(r.field != m.F_ITEM_CATEGORY for r in draft.mandate.rules) or asked(draft, m.F_ITEM_ID)


# ----- review round 8 -------------------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Buy up to CHF 30.50 the paperback book order I chose.",
    "Buy up to CHF 30.50 the professional reference book I chose.",
    "Buy the paperback book order I chose, up to CHF 30.50 books.",
    "Buy up to CHF 1'200 the professional reference book I chose.",
    "Buy up to CHF 30.20 books.",
    "Buy groceries up to CHF 12.50 grocery items.",
    "Buy up to CHF 2,000 books.",
])
def test_the_digits_of_an_amount_are_never_an_item_count(text):
    quantities = {r.value for r in compiled(text).mandate.rules if r.field == m.F_MAX_QUANTITY}
    assert quantities <= {Decimal(1)}, quantities


@pytest.mark.parametrize("text", [
    "Buy for CHF 30 my paperback book order.",
    "Buy up to CHF 30 my professional reference book.",
    "Buy only my paperback book order for CHF 30 or less.",
])
def test_my_item_anywhere_is_an_item_never_a_whole_category(text):
    draft = compiled(text)
    assert all(r.field != m.F_ITEM_CATEGORY for r in draft.mandate.rules) or asked(draft, m.F_ITEM_ID), draft


def test_two_named_items_are_asked():
    draft = compiled("Buy my running socks up to CHF 30. Buy the paperback book order I chose up to CHF 30.")
    assert asked(draft, m.F_ITEM_ID)


# ----- review round 9 -------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, count", [
    ("Buy up to CHF 20,one grocery item.", 1),
    ("Buy groceries,two items.", 2),
    ("Buy groceries up to CHF 50,two items.", 2),
    ("Buy for CHF 20,one book.", 1),
    ("Buy groceries,one grocery item,up to CHF 20.", 1),
    ("Order clothing,one item of clothing.", 1),
    ("Buy groceries for delivery,one item.", 1),
    ("Buy groceries for CHF 20 or less,one item.", 1),
    ("Buy one ordinary household our grocery item for CHF 20 or less.", 1),
    ("Buy two ordinary household our some grocery items.", 2),
    ("Buy one some some some some books.", 1),
])
def test_a_stated_count_is_read_or_asked_never_dropped(text, count):
    draft = compiled(text)
    quantities = {r.value for r in draft.mandate.rules if r.field == m.F_MAX_QUANTITY}
    assert quantities == {Decimal(count)} or asked(draft, m.F_MAX_QUANTITY) or asked(draft, "instruction"), (
        quantities, draft.questions)


def test_two_counts_split_by_a_bare_comma_are_asked():
    assert asked(compiled("Buy one item,two items."), m.F_MAX_QUANTITY)


# ----- review round 10 ------------------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Buy my hiking boots in size 43 items.",
    "Replace my road-running shoes in size 43 items.",
    "Buy the running socks I chose in size 43 for delivery items.",
    "Buy the hiking boots I chose in size 44 items for CHF 200 or less.",
    "Buy my paperback book order in size 12 books.",
    "Buy the road-running shoes I chose,at most 2 purchases some items.",
    "Buy the 27-inch computer monitor I chose,at most 5 orders items.",
    "Buy groceries in size 3 items for CHF 20 or less.",
    "Buy groceries at most 20 orders items.",
])
def test_a_size_or_an_order_count_is_never_an_item_count(text):
    draft = compiled(text)
    quantities = {r.value for r in draft.mandate.rules if r.field == m.F_MAX_QUANTITY}
    assert quantities <= {Decimal(1)} or asked(draft, m.F_MAX_QUANTITY), (quantities, draft.questions)


def test_a_decimal_comma_amount_is_asked():
    draft = compiled("Buy the road-running shoes I chose up to CHF 200,5 items.")
    assert all(r.value != Decimal("200.50") for r in draft.mandate.rules if r.field == m.F_BILLING_CHF)
    assert asked(draft, m.F_BILLING_CHF)


# ----- review round 11 ------------------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Buy two cosmetics up to CHF 50 per order.",
    "Buy two shoes, from a sports shop, up to CHF 200.",
    "Buy one grocery for CHF 50 or less.",
    "Buy a single grocery for delivery.",
    "Buy two groceries for CHF 50 or less.",
    "Buy two clothing for CHF 50 or less.",
    "Buy one clothes for CHF 50 or less.",
    "Buy a single clothing for CHF 50 or less.",
    "Buy two running shoes for CHF 200 or less.",
])
def test_a_count_before_a_category_noun_is_read_or_asked(text):
    draft = compiled(text)
    quantities = {r.value for r in draft.mandate.rules if r.field == m.F_MAX_QUANTITY}
    assert quantities or asked(draft, m.F_MAX_QUANTITY) or asked(draft, "instruction"), draft.questions


# ----- review round 12 ------------------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "My hiking boots replace my worn road-running shoes.",
    "Buy my running socks replace my worn road-running shoes in size 43.",
    "Replace my worn road-running shoes below CHF 1'000, the 27-inch computer monitor I chose.",
])
def test_two_named_items_anywhere_are_asked(text):
    assert asked(compiled(text), m.F_ITEM_ID)


@pytest.mark.parametrize("text", [
    "Buy my hiking boots below CHF 1'000.",
    "Buy my 27-inch computer monitor below CHF 1'000.",
    "Buy my hiking boots less than CHF 1'500 from a sports shop.",
])
def test_a_named_item_before_an_apostrophe_amount_is_read_or_asked(text):
    draft = compiled(text)
    assert any(r.field == m.F_ITEM_ID for r in draft.mandate.rules) or asked(draft, m.F_ITEM_ID), draft


def test_a_category_word_inside_the_chosen_items_own_name_is_not_another_kind():
    draft = compile_instruction("Buy the paperback book order I chose.", catalogue=CATALOGUE)
    assert Rule(m.F_ITEM_ID, "in", ("IT0041",)) in draft.mandate.rules
    assert not any("only the item you chose" in q.text for q in draft.questions)
    other = compile_instruction("Buy the 27-inch monitor I chose and some books.", catalogue=CATALOGUE)
    assert any("only the item you chose" in q.text for q in other.questions)


def test_several_item_kinds_ask_a_question_that_names_them():
    draft = compile_instruction("Buy clothing and books for CHF 50.", catalogue=CATALOGUE)
    [q] = [q for q in draft.questions if q.field == m.F_ITEM_CATEGORY]
    assert "books" in q.text and "clothing" in q.text
    [none] = [q for q in compile_instruction("At most CHF 50 per order.", catalogue=CATALOGUE).questions
              if q.field == m.F_ITEM_CATEGORY]
    assert none.text == "What kind of items may I buy?"


@pytest.mark.parametrize("text", ["Buy shoes for CHF 50.", "Buy clothing and shoes for CHF 50.", "Buy running shoes for CHF 50."])
def test_shoes_are_no_single_kind_so_the_question_names_them(text):
    draft = compile_instruction(text, catalogue=CATALOGUE)
    assert not any(r.field == m.F_ITEM_CATEGORY for r in draft.mandate.rules)
    assert any(q.field == m.F_ITEM_CATEGORY and "shoes" in q.text for q in draft.questions)


def test_household_is_a_kind_unless_it_describes_another_one():
    alone = compile_instruction("Buy household items for CHF 50 or less.", catalogue=CATALOGUE)
    assert Rule(m.F_ITEM_CATEGORY, "in", ("household",)) in alone.mandate.rules
    both = compile_instruction("Buy groceries and household items for CHF 50 or less.", catalogue=CATALOGUE)
    assert not any(r.field == m.F_ITEM_CATEGORY for r in both.mandate.rules)
    modifier = compile_instruction("Order our household groceries for delivery.", catalogue=CATALOGUE)
    assert Rule(m.F_ITEM_CATEGORY, "in", ("groceries",)) in modifier.mandate.rules
