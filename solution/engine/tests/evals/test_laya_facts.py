from leash.adapters.laya_reader import LayaReader

from evals.laya import fact_cases


def test_fact_evaluation_distinguishes_useful_checks_from_false_flags():
    class Model:
        def predict(self, state, questions):
            assert state["request"] == "Read the product listing."
            return {"answers": {
                "injection": {"type": "noul", "noul": .1},
                "addon": {"type": "noul", "noul": .9},
                "recurring": {"type": "noul", "noul": .1},
                "return_terms": {"type": "choice", "choice": "not_stated",
                                 "probabilities": {"stated": 0, "final_sale": 0, "not_stated": 1}},
            }}

    reader = LayaReader(Model(), fits=lambda *args: None)
    report = fact_cases(reader, cases=[
        {"id": "extra", "text": "Optional installation by a technician.", "addon": True},
        {"id": "ordinary", "text": "An ordinary monitor."},
    ])
    assert report["metrics"]["laya"]["addon"] == {"correct": 1, "total": 2, "tp": 1, "fp": 1, "fn": 0, "tn": 0}
    extra, ordinary = report["rows"]
    assert extra["decisions"]["no_addons"]["regex"]["verdict"] == "approve"
    assert extra["decisions"]["no_addons"]["augmented"]["verdict"] == "decline"
    assert "unrequested_addon" in extra["decisions"]["no_addons"]["augmented"]["reasons"]
    assert ordinary["decisions"]["no_addons"]["augmented"]["verdict"] == "decline"
    assert ordinary["wrong_model_fields"] == ["addon"]  # a stricter verdict is not necessarily better
    assert extra["decisions"]["over_limit"]["augmented"]["verdict"] == "decline"
    assert not report["loosened"]
