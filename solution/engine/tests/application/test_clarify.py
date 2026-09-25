"""The clarification loop (LEASH-123): answers add to the local draft, never recompiled, until nothing blocking remains."""

import csv
from decimal import Decimal
from pathlib import Path

import pytest

from leash.application.clarify import AnswerError, clarify
from leash.domain import mandate as m
from leash.policy.compiler import CatalogueItem

DATA = Path(__file__).resolve().parents[4] / "data"
with (DATA / "items.csv").open() as f:
    CATALOGUE = [CatalogueItem(r["item_id"], r["item_name"], r["item_category"]) for r in csv.DictReader(f)]
GROCERIES = "Buy groceries for CHF 50 or less."


def question(view, field_word):
    return next(q for q in view["open_questions"] if field_word in q["text"])


def test_repeating_a_model_limit_with_explicit_scope_is_not_a_conflict():
    from leash.domain.mandate import Rule
    proposed = [Rule(m.F_BILLING_CHF, "<=", Decimal("20"))]
    view = clarify("At most CHF 20 per order, delivery included.", [], CATALOGUE, proposed=proposed)
    # Equivalent rules can differ in bookkeeping, such as an omitted purchase scope.
    from leash.application.clarify import _Built, _clashing_rule
    from leash.policy.compiler import compile_instruction
    base = compile_instruction("At most CHF 20 per order.")
    built = _Built(proposed, [], "ask", False, [])
    assert _clashing_rule(base.mandate.rules, built, base, CATALOGUE) is None
    assert not any('not sure how to read' in q['text'] for q in view['open_questions'])


def test_no_platform_draft_while_questions_open():
    view = clarify(GROCERIES, [], CATALOGUE)
    assert view["status"] == "needs_answers"
    assert any(q["blocking"] for q in view["open_questions"])


def test_question_ids_are_stable_across_recompiles():
    first = clarify(GROCERIES, [], CATALOGUE)
    again = clarify(GROCERIES, [], CATALOGUE)
    assert [q["question_id"] for q in first["open_questions"]] == [q["question_id"] for q in again["open_questions"]]


def test_an_uncertainty_answer_sets_the_choice_and_closes_the_question():
    view = clarify(GROCERIES, [], CATALOGUE)
    q = question(view, "When I'm unsure")
    assert q["options"] == ["Ask me", "Decline", "Approve"]
    after = clarify(GROCERIES, [{"question_id": q["question_id"], "answer": "Decline"}], CATALOGUE)
    assert after["uncertainty_policy"] == "decline"
    assert q["question_id"] not in [x["question_id"] for x in after["open_questions"]]
    assert after["status"] == "ready"


def test_a_shop_answer_adds_the_rule_or_waives_it():
    start = clarify(GROCERIES + " Ask me when uncertain.", [], CATALOGUE)
    q = question(start, "shops")
    only = clarify(GROCERIES + " Ask me when uncertain.", [{"question_id": q["question_id"], "answer": q["options"][0]}],
                   CATALOGUE)
    assert {"field": m.F_MERCHANT_CATEGORY, "operator": "in", "value": ["groceries"]} in only["hard_rules"]
    anyshop = clarify(GROCERIES + " Ask me when uncertain.", [{"question_id": q["question_id"], "answer": "Any kind of shop"}],
                      CATALOGUE)
    assert all(r["field"] != m.F_MERCHANT_CATEGORY for r in anyshop["hard_rules"])
    assert q["question_id"] not in [x["question_id"] for x in anyshop["open_questions"]]


def test_a_split_check_answer():
    start = clarify(GROCERIES + " Ask me when uncertain.", [], CATALOGUE)
    q = question(start, "split in two")
    yes = clarify(GROCERIES + " Ask me when uncertain.", [{"question_id": q["question_id"], "answer": "Yes, ask me"}],
                  CATALOGUE)
    assert {"field": m.F_SPLIT_CHECK, "operator": "=", "value": "on"} in yes["hard_rules"]


def test_a_free_text_answer_is_recompiled_with_the_instruction():
    text = "Buy something nice for a friend."
    start = clarify(text, [], CATALOGUE)
    q = question(start, "not sure how to read")
    after = clarify(text, [{"question_id": q["question_id"], "answer": "Buy groceries for CHF 30 or less"}], CATALOGUE)
    assert {"field": m.F_BILLING_CHF, "operator": "<=", "value": 30, "currency": "CHF", "scope": "purchase"} in \
        after["hard_rules"]
    assert after["instruction"] == text  # the customer's own words stay as they were


def test_an_answer_to_an_unknown_question_or_an_unknown_option_is_refused():
    view = clarify(GROCERIES, [], CATALOGUE)
    with pytest.raises(AnswerError):
        clarify(GROCERIES, [{"question_id": "Q-nope", "answer": "yes"}], CATALOGUE)
    q = question(view, "When I'm unsure")
    with pytest.raises(AnswerError):
        clarify(GROCERIES, [{"question_id": q["question_id"], "answer": "Sometimes"}], CATALOGUE)


def test_answers_never_remove_a_rule_the_instruction_stated():
    start = clarify(GROCERIES, [], CATALOGUE)
    answers = [{"question_id": q["question_id"], "answer": (q.get("options") or ["whatever"])[-1]}
               for q in start["open_questions"]]
    after = clarify(GROCERIES, answers, CATALOGUE)
    stated = {"field": m.F_BILLING_CHF, "operator": "<=", "value": 50, "currency": "CHF", "scope": "purchase"}
    assert stated in after["hard_rules"]
    assert Decimal("50") == Decimal(str(stated["value"]))


# ----- review round 1 -------------------------------------------------------------------------------------

def test_a_free_text_answer_never_drops_a_stated_rule_or_changes_a_stated_uncertainty_choice():
    text = "Buy from a sports shop up to CHF 50 per order. Decline when unsure."
    start = clarify(text, [], CATALOGUE)
    stated = [r for r in start["hard_rules"] if r["field"] == m.F_MERCHANT_CATEGORY]
    assert stated and start["uncertainty_policy"] == "decline"
    items = question(start, "What kind of items")
    after = clarify(text, [{"question_id": items["question_id"], "answer": "Buy clothing from a clothing shop. Approve when unsure."}],
                    CATALOGUE)
    assert all(r in after["hard_rules"] for r in start["hard_rules"])  # every stated rule is still there
    assert after["uncertainty_policy"] == "decline"
    assert not any(q["text"].startswith("When I'm unsure") for q in after["open_questions"])  # never asked again


def test_an_answer_to_a_question_that_is_no_longer_open_is_refused():
    text = "Buy something nice for a friend."
    start = clarify(text, [], CATALOGUE)
    unsure = question(start, "When I'm unsure")
    read = question(start, "not sure how to read")
    answers = [{"question_id": read["question_id"], "answer": "Buy groceries for CHF 30 or less. Decline when unsure."}]
    after = clarify(text, answers, CATALOGUE)
    assert after["uncertainty_policy"] == "decline"
    with pytest.raises(AnswerError):
        clarify(text, answers + [{"question_id": unsure["question_id"], "answer": "Approve"}], CATALOGUE)


def test_a_clear_free_text_answer_closes_the_question_it_answers():
    text = "Buy something nice for a friend. Ask me when uncertain."
    start = clarify(text, [], CATALOGUE)
    read = question(start, "not sure how to read")
    after = clarify(text, [{"question_id": read["question_id"], "answer": "Buy groceries for CHF 30 or less"}], CATALOGUE)
    assert read["question_id"] not in [q["question_id"] for q in after["open_questions"]]
    ask = question(clarify("Buy groceries for CHF 50.", [], CATALOGUE), "the most I may spend")
    answered = clarify("Buy groceries for CHF 50.", [{"question_id": ask["question_id"], "answer": "At most CHF 50 per order"}],
                       CATALOGUE)
    assert ask["question_id"] not in [q["question_id"] for q in answered["open_questions"]]


# ----- review round 2 -------------------------------------------------------------------------------------

BASE = "Buy groceries for CHF 50, for delivery. Decline when unsure."


@pytest.mark.parametrize("first, second_field, second", [
    ("Buy clothing for at most CHF 50.", "What kind of items", "Buy clothing."),
    ("Pick up only, at most CHF 50.", "How should orders be fulfilled", "Pickup only."),
    ("At most CHF 5000 per order.", "which one applies", "At most CHF 5000 per order."),
])
def test_an_answer_that_conflicts_with_the_instruction_is_never_silently_dropped(first, second_field, second):
    start = clarify(BASE, [], CATALOGUE)
    most = question(start, "the most I may spend")
    answers = [{"question_id": most["question_id"], "answer": first}]
    view = clarify(BASE, answers, CATALOGUE)
    follow = [q for q in view["open_questions"] if second_field in q["text"]]
    if follow:
        answers.append({"question_id": follow[0]["question_id"], "answer": second})
        view = clarify(BASE, answers, CATALOGUE)
    assert view["status"] == "needs_answers"
    assert any("conflicts with your instruction" in q["text"] and q["blocking"] for q in view["open_questions"])


def test_a_stated_shop_restriction_is_never_optional():
    text = "Buy groceries for CHF 50 or less, only from sports shops. Decline when unsure."
    start = clarify(text, [], CATALOGUE)
    shop = [q for q in start["open_questions"] if "sports shops" in q["text"]]
    assert shop and all(q["blocking"] for q in shop)


def test_yes_confirms_the_amount_as_read():
    text = "Buy groceries for CHF 50. Decline when unsure."
    start = clarify(text, [], CATALOGUE)
    most = question(start, "the most I may spend")
    assert "Yes" in most["options"]
    after = clarify(text, [{"question_id": most["question_id"], "answer": "Yes"}], CATALOGUE)
    assert most["question_id"] not in [q["question_id"] for q in after["open_questions"]]


def test_a_blank_answer_is_refused():
    start = clarify(GROCERIES, [], CATALOGUE)
    with pytest.raises(AnswerError):
        clarify(GROCERIES, [{"question_id": start["open_questions"][0]["question_id"], "answer": "   "}], CATALOGUE)


# ----- review round 3 -------------------------------------------------------------------------------------

def answer_all(text, plan):
    """Answer open questions in order: plan maps a phrase in the question to the answer."""
    answers = []
    for phrase, reply in plan:
        view = clarify(text, answers, CATALOGUE)
        q = question(view, phrase)
        answers.append({"question_id": q["question_id"], "answer": reply})
    return clarify(text, answers, CATALOGUE)


def test_an_answer_that_closes_a_question_takes_effect_even_when_the_instruction_is_ambiguous():
    view = answer_all("Buy groceries for CHF 50. Buy clothing. Decline when unsure.",
                      [("What kind of items", "Buy clothing."), ("the most I may spend", "Yes")])
    assert {"field": m.F_ITEM_CATEGORY, "operator": "in", "value": ["clothing"]} in view["hard_rules"]
    view = answer_all("Buy groceries for CHF 50, for delivery. Pick up only. Decline when unsure.",
                      [("How should orders be fulfilled", "For delivery."), ("the most I may spend", "Yes")])
    assert {"field": "authorization.fulfillment_method", "operator": "in", "value": ["delivery"]} in view["hard_rules"]


def test_an_answer_that_contradicts_an_earlier_answer_is_a_conflict():
    view = answer_all("Buy groceries for CHF 50. Buy something nice. Decline when unsure.",
                      [("the most I may spend", "At most CHF 50, for delivery."),
                       ("not sure how to read", "Pick up only.")])
    assert view["status"] == "needs_answers"
    assert any("conflicts with" in q["text"] for q in view["open_questions"])


def test_a_later_uncertainty_wording_that_differs_from_the_chosen_one_is_a_conflict():
    view = answer_all("Buy groceries for CHF 50.",
                      [("When I'm unsure", "Approve"), ("the most I may spend", "At most CHF 50. Decline when unsure.")])
    assert view["status"] == "needs_answers" and any("conflicts with" in q["text"] for q in view["open_questions"])


def test_a_conflict_question_is_only_closed_by_an_answer_about_its_field():
    base = "Buy groceries for CHF 50, for delivery. Decline when unsure."
    view = answer_all(base, [("the most I may spend", "At most CHF 50, pick up only.")])
    conflict = question(view, "conflicts with")
    answers_so_far = [{"question_id": question(clarify(base, [], CATALOGUE), "the most I may spend")["question_id"],
                       "answer": "At most CHF 50, pick up only."}]
    with pytest.raises(AnswerError, match="doesn't answer this question"):
        clarify(base, answers_so_far + [{"question_id": conflict["question_id"], "answer": "Buy groceries."}], CATALOGUE)


# ----- review round 4 -------------------------------------------------------------------------------------

def test_a_choice_made_on_an_uncertainty_conflict_question_takes_effect():
    text = "Buy groceries for CHF 50, for delivery. Approve when unsure."
    view = answer_all(text, [("the most I may spend", "At most CHF 50. Decline when unsure."),
                             ("conflicts with", "Decline"), ("the most I may spend", "Yes")])
    assert view["uncertainty_policy"] == "decline"


def test_a_chosen_item_outside_the_allowed_category_is_never_ready_unnoticed():
    view = answer_all("Buy groceries for CHF 50, for delivery. Decline when unsure.",
                      [("the most I may spend", "At most CHF 50. Buy the road-running shoes I chose.")])
    assert view["status"] == "needs_answers"
    assert any("can't all be met" in q["text"] or "conflicts with" in q["text"] for q in view["open_questions"])


# ----- review round 5 -------------------------------------------------------------------------------------

def test_an_answer_that_does_not_answer_its_question_is_refused_with_the_reason():
    with pytest.raises(AnswerError, match="doesn't answer this question"):
        answer_all("Buy groceries for CHF 50, for delivery. Decline when unsure.",
                   [("the most I may spend", "Pick up only.")])


def test_an_answer_with_an_unclear_part_is_refused_and_never_half_applied():
    with pytest.raises(AnswerError, match="unclear"):
        answer_all("Buy running shoes for CHF 150 or less. Ask me when uncertain.",
                   [("What kind of items", "Clothing, and something nice.")])


def test_a_chosen_shop_kind_stays_after_later_answers():
    view = answer_all(GROCERIES, [("groceries shops", "Only groceries shops"), ("When I'm unsure", "Decline"),
                                  ("split in two", "Yes, ask me")])
    assert {"field": m.F_MERCHANT_CATEGORY, "operator": "in", "value": ["groceries"]} in view["hard_rules"]
    assert view["status"] == "ready"


def test_an_answer_that_leaves_no_purchase_possible_on_a_new_field_is_a_conflict_not_a_dead_end():
    text = "Buy the 27-inch monitor I chose and some books for CHF 400 or less. Ask me when uncertain."
    view = answer_all(text, [("only the item you chose", "Buy books.")])
    assert any("conflicts with" in q["text"] for q in view["open_questions"])
    assert not any("can't all be met" in q["text"] for q in view["open_questions"])
    assert not any(r["field"] == m.F_ITEM_CATEGORY for r in view["hard_rules"])  # never used
    after = answer_all(text, [("only the item you chose", "Buy books."), ("only the item you chose", "Only the item I chose")])
    assert after["status"] == "needs_answers"  # the conflict stays until it is answered on its own field
    after = answer_all(text, [("only the item you chose", "Buy books."), ("conflicts with", "Keep what I had"),
                              ("only the item you chose", "Only the item I chose")])
    assert after["status"] == "ready" and not any(r["field"] == m.F_ITEM_CATEGORY for r in after["hard_rules"])


def test_an_answer_whose_own_reading_is_unsure_about_other_kinds_is_refused():
    with pytest.raises(AnswerError, match="unclear"):
        answer_all("Buy running shoes for CHF 150 or less. Ask me when uncertain.",
                   [("What kind of items", "Buy the road-running shoes I chose. Buy groceries.")])


def test_a_conflict_on_the_uncertainty_choice_never_offers_a_looser_one():
    view = answer_all("Buy groceries for CHF 50, for delivery. Decline when unsure.",
                      [("the most I may spend", "At most CHF 50. Approve when unsure.")])
    assert question(view, "conflicts with")["options"] == ["Decline"]


def test_the_chosen_item_question_closes_with_its_option_or_a_restatement():
    text = "Buy the 27-inch monitor I chose and some books for CHF 400 or less. Ask me when uncertain."
    for reply in ("Only the item I chose", "Buy the 27-inch monitor I chose."):
        view = answer_all(text, [("only the item you chose", reply)])
        assert view["status"] == "ready", reply
        assert {"field": m.F_ITEM_ID, "operator": "in", "value": ["IT0017"]} in view["hard_rules"]


def test_a_restatement_that_adds_nothing_changes_nothing():
    text = "Buy running shoes for CHF 150 or less. Ask me when uncertain."
    once = answer_all(text, [("What kind of items", "Buy clothing.")])
    again = answer_all(text, [("What kind of items", "Buy clothing."), ("certain shops", "Any kind of shop")])
    assert once["hard_rules"] == again["hard_rules"]


# ----- review round 6 -------------------------------------------------------------------------------------

def test_an_answer_naming_a_value_that_a_stricter_one_overrides_is_a_conflict():
    text = "Buy groceries for CHF 50 or less. Buy groceries for CHF 40 or less. Ask me when uncertain."
    view = answer_all(text, [("which one applies", "At most CHF 50 per order.")])
    assert view["status"] == "needs_answers" and any("conflicts with" in q["text"] for q in view["open_questions"])
    view = answer_all(text, [("which one applies", "At most CHF 40 per order.")])
    assert view["status"] == "ready"


def test_an_answer_with_contradictory_uncertainty_wording_is_refused():
    with pytest.raises(AnswerError, match="unclear"):
        answer_all("Buy groceries for CHF 50. Decline when unsure.",
                   [("the most I may spend", "At most CHF 50. Approve when unsure. Ask me when unsure.")])


# ----- review round 7 -------------------------------------------------------------------------------------

def test_an_option_that_makes_the_rules_impossible_is_a_conflict_with_a_way_back():
    text = "Buy groceries for CHF 50. Ask me when uncertain."
    view = answer_all(text, [("the most I may spend", "At most CHF 50 per order. Only from a sports shop."),
                             ("groceries shops", "Only groceries shops")])
    assert not any("can't all be met" in q["text"] for q in view["open_questions"])
    assert question(view, "conflicts with")["options"] == ["Keep what I had"]
    assert {"field": m.F_MERCHANT_CATEGORY, "operator": "in", "value": ["groceries"]} not in view["hard_rules"]


@pytest.mark.parametrize("reply", ["Under CHF 0 per order.", "At most CHF 0 per order."])
def test_a_spending_limit_nothing_can_meet_is_never_ready(reply):
    view = answer_all("Buy groceries for CHF 50. Ask me when uncertain.", [("the most I may spend", reply)])
    assert view["status"] == "needs_answers"
    assert clarify("Buy groceries for under CHF 0. Ask me when uncertain.", [], CATALOGUE)["status"] == "needs_answers"


@pytest.mark.parametrize("reply", ["At most CHF 500 in any 7 days.", "At most CHF 30 per order."])
def test_a_question_about_an_amount_the_customer_wrote_needs_its_own_answer(reply):
    text = "Buy groceries for CHF 30. Keep the weekly total at or below CHF 100 per order. Ask me when uncertain."
    view = answer_all(text, [("Is CHF 30.00 the most", reply)])
    assert question(view, "CHF 100.00")["blocking"]
    assert view["status"] == "needs_answers"


@pytest.mark.parametrize("text, reply", [
    ("Buy groceries for CHF 50. Ask me when uncertain.", "At most CHF 40 per order, from a grocery shop, from a sports shop."),
    ("Buy groceries for CHF 50. Ask me when uncertain.", "At most CHF 50 per order. Only from a sports shop. Only from a grocery shop."),
])
def test_an_answer_with_unclear_shop_wording_is_refused_not_half_applied(text, reply):
    with pytest.raises(AnswerError, match="unclear"):
        answer_all(text, [("the most I may spend", reply)])


# ----- review round 8 -------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, phrase, reply", [
    ("Buy groceries for CHF 50 or less. Frobnicate the wibble. Ask me when uncertain.", "not sure how to read",
     "For delivery. Buy clothing. Buy books."),
    ("Buy for CHF 50. Ask me when uncertain.", "the most I may spend", "At most CHF 40 per order. Buy groceries. Buy clothing."),
])
def test_an_answer_whose_sentences_cancel_out_is_refused_not_half_applied(text, phrase, reply):
    with pytest.raises(AnswerError, match="unclear"):
        answer_all(text, [(phrase, reply)])


@pytest.mark.parametrize("text", ["Buy groceries for under CHF 0.01 per order. Ask me when uncertain.",
                                  "Buy groceries for under CHF 0.01 in any 7 days. Ask me when uncertain.",
                                  "Buy groceries for at most CHF 0.004 per order. Ask me when uncertain."])
def test_a_limit_not_even_one_cent_can_meet_is_never_ready(text):
    assert clarify(text, [], CATALOGUE)["status"] == "needs_answers"


def test_an_unknown_item_can_be_named_after_the_customer_gave_its_kind():
    text = "Replace my shoes for CHF 150 or less. Ask me when uncertain."
    view = answer_all(text, [("What kind of items", "Buy books."), ("Which item is", "Buy the paperback book order I chose.")])
    assert view["status"] == "ready"
    assert {"field": m.F_ITEM_ID, "operator": "in", "value": ["IT0041"]} in view["hard_rules"]


# ----- review round 9 -------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, phrase, reply", [
    ("Buy groceries for CHF 50 or less. Frobnicate the wibble. Ask me when uncertain.", "not sure how to read",
     "For delivery, clothing and books."),
    ("Buy groceries for CHF 50. Ask me when uncertain.", "the most I may spend", "At most CHF 40 per order, clothing and books."),
    ("Buy the 27-inch monitor I chose for CHF 400 or less. Frobnicate the wibble. Ask me when uncertain.",
     "not sure how to read", "For delivery, clothing and books."),
    ("Buy groceries for CHF 50. Ask me when uncertain.", "the most I may spend", "At most CHF 40 per order, groceries and cosmetics."),
])
def test_an_answer_naming_several_item_kinds_in_one_sentence_is_refused_not_half_applied(text, phrase, reply):
    with pytest.raises(AnswerError, match="unclear"):
        answer_all(text, [(phrase, reply)])


# ----- review round 10 ------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, phrase, reply", [
    ("Buy for CHF 50. Decline when unsure.", "What kind of items", "Buy groceries and shoes."),
    ("Buy for CHF 50. Decline when unsure.", "What kind of items", "Buy groceries. Buy running shoes."),
    ("Buy clothing for CHF 100. Ask me when uncertain.", "the most I may spend", "At most CHF 100 per order. Buy running shoes."),
    ("Buy groceries for CHF 50. Ask me when uncertain.", "the most I may spend", "At most CHF 50 per order. Buy shoes."),
])
def test_shoe_wording_in_an_answer_is_never_dropped(text, phrase, reply):
    with pytest.raises(AnswerError, match="unclear"):
        answer_all(text, [(phrase, reply)])


# ----- review round 11 ------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, phrase, reply", [
    ("Buy clothing for CHF 100. Ask me when uncertain.", "the most I may spend", "At most CHF 100 per order. Buy household items."),
    ("Buy clothing for delivery. Pick up only. At most CHF 80 per order. Ask me when uncertain.", "fulfilled",
     "For delivery, household items."),
])
def test_household_items_in_an_answer_are_a_kind_that_can_conflict(text, phrase, reply):
    view = answer_all(text, [(phrase, reply)])
    assert any("conflicts with" in q["text"] for q in view["open_questions"])


@pytest.mark.parametrize("reply", ["Buy household items. Buy groceries.", "Buy groceries and household items."])
def test_household_next_to_another_kind_is_refused_not_half_applied(reply):
    with pytest.raises(AnswerError, match="unclear"):
        answer_all("At most CHF 80 per order. Ask me when uncertain.", [("What kind of items", reply)])


def test_household_items_answer_the_item_question():
    view = answer_all("At most CHF 80 per order. Ask me when uncertain.", [("What kind of items", "Buy household items.")])
    assert {"field": m.F_ITEM_CATEGORY, "operator": "in", "value": ["household"]} in view["hard_rules"]


# ----- review round 12 ------------------------------------------------------------------------------------

def test_shoes_next_to_a_chosen_item_are_never_dropped_from_an_answer():
    with pytest.raises(AnswerError, match="unclear"):
        answer_all("At most CHF 400 per order. Ask me when uncertain.",
                   [("What kind of items", "Buy the 27-inch monitor I chose and running shoes.")])


@pytest.mark.parametrize("text", ["Buy the paperback I chose. Buy running shoes. Ask me when uncertain.",
                                  "Buy the 27-inch monitor I chose and shoes for CHF 400 or less. Ask me when uncertain."])
def test_shoes_next_to_a_chosen_item_ask_before_ready(text):
    view = clarify(text, [], CATALOGUE)
    assert view["status"] == "needs_answers" and question(view, "only the item you chose")["blocking"]


# ----- review round 13 ------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, reply", [
    ("Buy the paperback I chose. Buy books. Ask me when uncertain.", "Buy books."),
    ("Buy the paperback I chose. Buy running shoes. Ask me when uncertain.", "Buy books."),
    ("Buy the pantry staples I chose. Buy groceries. Ask me when uncertain.", "Buy groceries."),
    ("Buy the work shoes I chose and clothing. Ask me when uncertain.", "Buy clothing."),
    ("Buy my household essentials and groceries. Ask me when uncertain.", "Buy household items."),
])
def test_a_kind_next_to_a_chosen_item_can_never_widen_it_so_it_is_a_conflict(text, reply):
    view = answer_all(text, [("only the item you chose", reply)])
    assert view["status"] == "needs_answers"
    assert question(view, "conflicts with")["options"] == ["Keep what I had"]
    after = answer_all(text, [("only the item you chose", reply), ("conflicts with", "Keep what I had"),
                              ("only the item you chose", "Only the item I chose")])
    assert after["status"] == "ready"


# ----- DEC-045: rules the model read, and what was left unrestricted ------------------------------

GERMAN = "höchstens CHF 50 pro Bestellung"


def test_a_rule_the_compiler_cannot_read_still_reaches_the_draft():
    """The compiler reads no German; under DEC-045 the model's rule is carried into the draft anyway."""
    proposed = [m.Rule(m.F_BILLING_CHF, "<=", Decimal("50"), currency="CHF", scope="purchase")]
    view = clarify(GERMAN, [], CATALOGUE, proposed=proposed)
    assert [(r["field"], r["value"]) for r in view["hard_rules"]] == [(m.F_BILLING_CHF, 50)]


def test_a_proposed_rule_is_read_back_from_the_rule_not_the_instruction():
    proposed = [m.Rule(m.F_BILLING_CHF, "<=", Decimal("50"), currency="CHF", scope="purchase")]
    view = clarify(GERMAN, [], CATALOGUE, proposed=proposed)
    assert "At most CHF 50.00 per order, delivery included." in view["notes"]


def test_model_echo_of_session_default_is_not_relabelled_as_customer_instruction():
    words = "Pause anything that looks like someone other than me is driving the session. Ask me when uncertain."
    view = clarify(words, [], CATALOGUE, proposed=[m.Rule(m.F_SESSION_RISK, "<", Decimal("2"))])
    assert any(r["source"] == "team" and r["decision"] == "DEC-024" for r in view["rules"])
    assert not any(r["source"] == "customer" and "risk score" in r["text"] for r in view["rules"])


def test_historical_shops_are_a_customer_rule_without_a_blocking_shop_question():
    text = ("The agent may buy clothing for me, up to CHF 250 per order, from shops I have used before. "
            "Pause anything that looks like someone other than me is driving the session. Ask me when uncertain.")
    view = clarify(text, [], CATALOGUE)
    assert view["status"] == "ready"
    assert any(r["field"] == m.F_PRIOR_PURCHASES and r["value"] == 1 for r in view["hard_rules"])
    assert any("shops you have paid before" in r["text"] and r["source"] == "customer" for r in view["rules"])
    assert not any(q["blocking"] and q["field"] in {m.F_PRIOR_PURCHASES, m.F_MERCHANT_CATEGORY}
                   for q in view["open_questions"])


def test_the_draft_names_the_fields_left_unrestricted():
    """DEC-045's omission defence: what the customer did not limit has to be visible."""
    view = clarify(GERMAN, [], CATALOGUE,
                   proposed=[m.Rule(m.F_BILLING_CHF, "<=", Decimal("50"))])
    assert m.F_BILLING_CHF not in view["unrestricted"]
    assert m.F_MERCHANT_CATEGORY in view["unrestricted"]
    assert m.F_MAX_QUANTITY in view["unrestricted"]


def test_a_proposed_rule_can_only_tighten_the_draft():
    """Proposed rules are appended, so the strictest per field still wins (DEC-006)."""
    view = clarify("Buy groceries for CHF 50 or less.", [], CATALOGUE,
                   proposed=[m.Rule(m.F_BILLING_CHF, "<=", Decimal("20"), currency="CHF", scope="purchase")])
    amounts = sorted(r["value"] for r in view["hard_rules"] if r["field"] == m.F_BILLING_CHF)
    assert amounts == [20, 50]


def test_customer_can_state_count_and_familiarity_clarifications_directly():
    text = ("Buy one ordinary grocery item for CHF 20 or less from a shop I use regularly. "
            "At most 1 item per order and at most 1 purchase. "
            "By a regular shop I mean at least 3 earlier purchases on this card. "
            "Only groceries. Ask me when uncertain.")
    view = clarify(text, [], CATALOGUE)
    assert view["status"] == "ready", view["open_questions"]
    assert {"field": m.F_PRIOR_PURCHASES, "operator": ">=", "value": 3} in view["hard_rules"]


# --- LEASH-174 -------------------------------------------------------------------------------

def test_the_draft_lists_unrestricted_fields():
    """Every registry field with no rule, by name.

    A model that silently drops a restriction leaves no trace in the rules it did return, so the
    only defence is naming what is *not* restricted and showing it to the customer (LEASH-146
    renders it). The list is derived from the registry, so a new field appears in it for free.
    """
    from leash.policy.registry import REGISTRY

    view = clarify(GROCERIES, [], CATALOGUE)
    restricted = {r["field"] for r in view["hard_rules"]}
    assert view["unrestricted"] == [name for name in REGISTRY if name not in restricted]
    assert m.F_BILLING_CHF in restricted and m.F_BILLING_CHF not in view["unrestricted"]
    assert m.F_RETURN_DAYS in view["unrestricted"], "a field nobody restricted must be named"


def test_the_same_limit_read_twice_appears_once_in_hard_rules():
    """The compiler's rule carries currency and scope, the model's the same restriction without them.

    Kept as two, the customer reviews one limit twice and it is submitted to the platform twice.
    """
    view = clarify("At most CHF 50 per order.", [], CATALOGUE,
                   proposed=[m.Rule(m.F_BILLING_CHF, "<=", Decimal("50"))])
    assert [(r["field"], r["value"]) for r in view["hard_rules"]] == [(m.F_BILLING_CHF, 50)]


def test_a_set_rule_read_in_another_order_is_the_same_restriction():
    view = clarify("Buy groceries or household items for CHF 50 or less.", [], CATALOGUE,
                   proposed=[m.Rule(m.F_ITEM_CATEGORY, "in", ("household", "groceries"))])
    kinds = [r for r in view["hard_rules"] if r["field"] == m.F_ITEM_CATEGORY]
    assert len(kinds) == 1, kinds


def test_a_sentence_the_compiler_cannot_read_stops_blocking_once_a_rule_covers_it():
    """DEC-045: the grammar is English-only, so its "I'm not sure how to read …" cannot gate a draft.

    Measured on 2026-09-25: a correctly read German instruction still carried six blocking questions,
    and a free-text answer in German is refused too — so the draft could never reach `ready`.
    """
    proposed = [m.Rule(m.F_BILLING_CHF, "<=", Decimal("50"), currency="CHF", scope="purchase")]
    view = clarify(GERMAN, [], CATALOGUE, proposed=proposed)
    asked = [q["text"] for q in view["open_questions"] if q["blocking"]]
    assert not any("not sure how to read" in t for t in asked), asked
    assert not any("means for this rule" in t for t in asked), asked


def test_a_sentence_no_proposed_rule_covers_is_still_blocking():
    """The omission net stays: a restriction nobody read must not vanish (DEC-045, LEASH-146)."""
    view = clarify("Keine Abonnemente. Höchstens CHF 50 pro Bestellung.", [], CATALOGUE,
                   proposed=[m.Rule(m.F_BILLING_CHF, "<=", Decimal("50"))])
    asked = [q["text"] for q in view["open_questions"] if q["blocking"]]
    assert any("Abonnemente" in t for t in asked), asked


def test_a_sentence_whose_other_restriction_nobody_read_stays_blocking():
    """One rule out of a three-clause sentence is not a reading of the sentence (DEC-056, amended)."""
    view = clarify("Buy me a jacket, at most CHF 120 per order, and no subscriptions.", [], CATALOGUE,
                   proposed=[m.Rule(m.F_BILLING_CHF, "<=", Decimal("120"))])
    asked = [q["text"] for q in view["open_questions"] if q["blocking"]]
    assert any("not sure how to read" in t for t in asked), asked


SHOPS = "Only from shops with at least 3 previous purchases on this card."


def test_a_cue_question_about_a_read_sentence_is_answered_whatever_field_it_guessed():
    """From a live chat on 2026-09-25.

    "Only from shops with at least 3 previous purchases on this card." is about familiarity, but the
    compiler's cues match the word "shops", so it asked what the sentence means for the *merchant
    category*. The model had read it correctly as `prior_purchases >= 3`. The customer was left with a
    blocking question about a sentence that had been read, and no answer clears it — a cue question is
    a guess at which field an unreadable sentence is about, so the sentence being read answers it too.
    """
    view = clarify(SHOPS, [], CATALOGUE, proposed=[m.Rule(m.F_PRIOR_PURCHASES, ">=", Decimal("3"))])
    asked = [q["text"] for q in view["open_questions"] if q["blocking"]]
    assert not any("previous purchases on this card" in t for t in asked), asked


def test_a_cue_question_is_not_answered_by_a_rule_read_from_another_sentence():
    """Sharing a field is not being read: the rule has to come from this sentence."""
    view = clarify(f"At most CHF 20 per order. {SHOPS}", [], CATALOGUE,
                   proposed=[m.Rule(m.F_BILLING_CHF, "<=", Decimal("20"))])
    asked = [q["text"] for q in view["open_questions"] if q["blocking"]]
    assert any("previous purchases on this card" in t for t in asked), asked


# --- the customer's own words are not our suggestion -------------------------------------------

def test_a_count_the_customer_stated_is_shown_as_theirs_not_as_our_default():
    """Found in a live transcript: "At most 1 item per order." came back labelled as our default.

    Provenance was inferred by sniffing the note for a `DEC-\\d{3}`, so any rule whose note cites a
    decision read as ours — including one read straight from the customer's sentence. Telling a
    customer they may disagree with a boundary they themselves set is the mirror of letting a
    preference pass as their instruction, and worse: it puts words in their mouth.
    """
    view = clarify("Buy the monitor I chose. At most 1 item per order. At most 1 purchase in total.",
                   [], CATALOGUE)
    stated = [r for r in view["rules"] if "item per order" in r["text"]]
    assert stated, [r["text"] for r in view["rules"]]
    assert stated[0]["source"] == "customer", "the customer typed this sentence"
    assert stated[0]["decision"] == "DEC-013", "still says how we read it; that is not the same as whose it is"
    total = [r for r in view["rules"] if "One purchase" in r["text"]]
    assert total and total[0]["source"] == "customer", "they typed this one too"


def test_a_default_we_applied_is_still_shown_as_ours():
    """The mirror. An instruction that never states a count still gets the item-mode default, and
    that one really is ours to disagree with."""
    view = clarify("Buy the 27-inch monitor I chose, from a seller I have bought from before, "
                   "for CHF 400 or less. Ask me when uncertain.", [], CATALOGUE)
    ours = [r for r in view["rules"] if r["source"] == "team"]
    assert [r["text"] for r in ours] == ["One item per order",
                                         "One purchase: a second matching order asks you first"], \
        "item mode supplies these; the customer never stated a count"
    assert all(r["decision"] == "DEC-013" for r in ours)
    # everything they did state stays theirs
    assert all(r["source"] == "customer" for r in view["rules"] if r not in ours)


def test_a_rule_reads_without_our_decision_code():
    """LEASH-146: `DEC-013` is our vocabulary. It stays on the view as provenance, out of the sentence.

    The code is kept — the customer can still be shown how a sentence was read — but a boundary they
    are asked to agree to must read as a boundary, not as a citation.
    """
    view = clarify("Buy the 27-inch monitor I chose, from a seller I have bought from before, "
                   "for CHF 400 or less. Ask me when uncertain.", [], CATALOGUE)
    ours = [r for r in view["rules"] if r["source"] == "team"]
    assert ours, [r["text"] for r in view["rules"]]
    assert not any("DEC-" in r["text"] for r in view["rules"]), [r["text"] for r in view["rules"]]
    assert all(r["decision"] == "DEC-013" for r in ours)
