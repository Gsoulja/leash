import pytest

from leash.reading.question_bank import QUESTIONS, as_dict, bank_hash

EXPECTED = {
    "injection": "noul",
    "addon": "noul",
    "recurring": "noul",
    "return_terms": "choice",
    "item_match": "choice",
}


def test_hash_changes_with_wording():
    changed = as_dict(QUESTIONS)
    changed["injection"]["instructions"] += " "
    assert bank_hash(changed) != bank_hash(QUESTIONS)


def test_hash_changes_when_an_option_changes():
    changed = as_dict(QUESTIONS)
    changed["item_match"]["criteria"]["exact"] = "the same product"
    assert bank_hash(changed) != bank_hash(QUESTIONS)


def test_hash_is_stable_and_ignores_key_order():
    reordered = {k: QUESTIONS[k] for k in reversed(list(QUESTIONS))}
    assert bank_hash(QUESTIONS) == bank_hash(QUESTIONS) == bank_hash(reordered)
    assert bank_hash(QUESTIONS).startswith("qb-v1-")


def test_bank_holds_the_five_typed_questions():
    assert {k: q["type"] for k, q in QUESTIONS.items()} == EXPECTED
    assert set(QUESTIONS["return_terms"]["criteria"]) == {"stated", "final_sale", "not_stated"}
    assert set(QUESTIONS["item_match"]["criteria"]) == {"exact", "substitute", "complement", "unrelated"}


def test_bank_cannot_be_edited_at_runtime():
    with pytest.raises(TypeError):
        QUESTIONS["injection"] = {}  # type: ignore[index]


def test_as_dict_is_an_independent_copy():
    copy = as_dict(QUESTIONS)
    copy["addon"]["instructions"] = "changed"
    assert QUESTIONS["addon"]["instructions"] != "changed"
