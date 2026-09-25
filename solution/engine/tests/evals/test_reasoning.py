import json

import pytest

from evals.reasoning import cases, evaluate, guarded, validate


def test_reasoning_inputs_hide_reference_and_expected_answers_and_preserve_money():
    rows = cases()
    assert len(rows) == 57
    assert sum(r["expected"] is not None for r in rows) == 12
    for row in rows:
        payload = row["input"]
        assert set(payload) == {"permission", "checkout", "history"}
        assert isinstance(payload["checkout"]["billing_amount_chf"], str)
        assert "decision" not in json.dumps(payload)
        if row["expected"] is not None:
            assert payload["checkout"]["merchant"]["category"] == "electronics"
            assert payload["history"]["session_signals"] == []
    by_id = {r["id"]: r for r in rows}
    assert by_id["probe-extra-service"]["reference"]["verdict"] == "approve"
    assert by_id["probe-extra-service"]["expected"] == "decline"
    assert by_id["probe-no-returns"]["reference"]["verdict"] == "step_up"
    assert by_id["probe-no-returns"]["expected"] == "decline"
    assert by_id["probe-approved-spend"]["reference"]["verdict"] == "decline"
    assert by_id["probe-waiting-spend"]["reference"]["verdict"] == "approve"


@pytest.mark.parametrize("patch", [
    {"decision": "pay"}, {"evidence": ["/checkout/invented"]},
    {"evidence": []}, {"reason": ""}, {"reason": "x" * 1001},
])
def test_invalid_or_unsupported_reasoning_output_is_rejected(patch):
    value = {"decision": "approve", "reason": "Within the limit.", "evidence": ["/checkout/amount"]}
    with pytest.raises(ValueError):
        validate(json.dumps({**value, **patch}), {"checkout": {"amount": "20.00"}})


def test_source_references_are_checked_but_do_not_claim_semantic_verification():
    result = validate('{"decision":"approve","reason":"Within limit.","evidence":["/checkout/items/0/details"]}',
                      {"checkout": {"items": [{"details": "A monitor."}]}})
    assert result["decision"] == "approve"


def test_hypothetical_guard_preserves_engine_and_turns_ai_objections_into_a_question():
    assert guarded("decline", "approve", "ask") == "decline"
    assert guarded("step_up", "approve", "ask") == "step_up"
    assert guarded("approve", "decline", "ask") == "step_up"
    assert guarded("approve", "step_up", "decline") == "decline"
    assert guarded("approve", None, "ask") == "approve"  # model failure: existing engine remains authoritative


def test_advisory_arm_receives_code_checks_and_invalid_evidence_never_becomes_a_suggestion():
    from types import SimpleNamespace
    row = next(r for r in cases() if r["id"] == "probe-over-limit")
    captured = []
    def create(**kwargs):
        captured.append(json.loads(kwargs["messages"][1]["content"]))
        return SimpleNamespace(model="fake", usage=None, choices=[SimpleNamespace(finish_reason="stop",
            message=SimpleNamespace(content='{"decision":"approve","reason":"Unsupported claim.",'
                                            '"evidence":["/invented"]}'))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    result = evaluate(client, "fake", row, advisory=True)
    assert any(c["status"] == "fail" for c in captured[0]["engine_checks"])
    assert "engine_checks" not in row["input"]  # independent arm remains blind
    assert result["error"] == "ValueError" and "suggestion" not in result
    assert result["guarded_suggestion"] == "decline"
