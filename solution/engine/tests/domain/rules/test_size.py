from factories import facts, mandate, purchase, snapshot
from leash.domain import mandate as m
from leash.domain.mandate import Rule
from leash.domain.rules.size import size_rule

SIZE_43 = mandate(Rule(m.F_SIZE, "=", "43"))


def run(mm, **f):
    return size_rule(purchase(), mm, snapshot(), facts(**f))


def test_size_42_fails_when_43_requested():
    [check] = run(SIZE_43, sizes=("42",))
    assert (check.status, check.reason_code, check.actual) == ("fail", "size_mismatch", "Size 42")
    assert check.detail == "Size 42, but you asked for size 43."


def test_missing_size_asks():
    [check] = run(SIZE_43, sizes=None)
    assert (check.status, check.reason_code, check.actual) == ("warn", "size_missing", "Not stated")


def test_matching_size_passes():
    [check] = run(SIZE_43, sizes=("43",))
    assert check.status == "pass" and check.agreed == "Size 43"


def test_any_stated_wrong_size_fails():
    [check] = run(SIZE_43, sizes=("43", "44"))
    assert check.status == "fail"


def test_no_size_rule_no_check():
    assert run(mandate(), sizes=("42",)) == []
