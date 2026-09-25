from decimal import Decimal

from evals.openrouter import RULE_CASES, canonical, score_rules, summary
from leash.domain.mandate import F_BILLING_CHF, Rule


def test_scoring_normalizes_numbers_but_does_not_hide_wrong_limits_or_missing_cases():
    assert canonical(["x", "<=", Decimal("50")]) == canonical(["x", "<=", 50])
    assert canonical(["x", "=", "delivery"]) == canonical(["x", "in", ["delivery"]])
    case = RULE_CASES[0]
    correct = score_rules(case, [Rule(F_BILLING_CHF, "<=", Decimal(50))], [], "permission")
    wrong = score_rules(case, [Rule(F_BILLING_CHF, "<=", Decimal(500))], [], "permission")
    assert correct["correct"] and not wrong["correct"] and wrong["contradictions"]
    group = summary([{"task": "rules", "source": "test", "score": correct, "ms": 1},
                     {"task": "rules", "source": "test", "error": "timeout", "ms": 5}])[0]
    assert group["n"] == 2 and group["correct"] == 1 and group["errors"] == 1
