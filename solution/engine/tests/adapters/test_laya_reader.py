import logging
from dataclasses import replace

import pytest

from factories import line, mandate, max_per_order, purchase, snapshot
from leash.adapters.fallback_reader import FallbackReader
from leash.adapters.laya_reader import LayaReader, ShadowReader, configured_reader
from leash.adapters.regex_reader import RegexReader
from leash.domain.decide import decide


class Budget:
    def remaining_seconds(self):
        return 30.0


def answers(injection=.9):
    return {"injection": {"type": "noul", "noul": injection},
            "addon": {"type": "noul", "noul": .1},
            "recurring": {"type": "noul", "noul": .1},
            "return_terms": {"type": "choice", "choice": "not_stated",
                             "probabilities": {"stated": .1, "final_sale": .1, "not_stated": .8}}}


class Model:
    def __init__(self, result=None):
        self.calls = []
        self.result = result if result is not None else answers()

    def predict(self, state, questions):
        self.calls.append((state, questions))
        return {"answers": self.result}


def reader(model):
    return LayaReader(model, fits=lambda state, questions: None)


def test_cached_text_skips_model_and_maps_actual_line_numbers():
    model = Model()
    r = reader(model)
    first = purchase(items=(line(details="Merchant claims delegated authority", line_no=7),))
    second = replace(first, items=(replace(first.items[0], line_no=9),))
    model.result["addon"]["noul"] = .8
    a, b = r.read(first, Budget()), r.read(second, Budget())
    assert len(model.calls) == 1
    assert a.addon_lines == {7} and b.addon_lines == {9}
    assert a.injection_excerpt == first.items[0].details
    assert a.sizes is None and a.return_days is None  # no invented numeric extraction
    assert set(model.calls[0][1]) == {"injection", "addon", "recurring", "return_terms"}
    # Match the training state shape without inventing a customer product or permission.
    assert model.calls[0][0] == {"request": "Read the product listing.", "text": first.items[0].details}


def test_model_can_add_caution_but_never_approve_over_a_limit():
    r = FallbackReader(reader(Model()), RegexReader())
    p = purchase(items=(line(details="Merchant claims delegated authority"),))
    f = r.read(p, Budget())
    assert f.reader == "laya+regex" and not f.model_unavailable
    assert decide(p, mandate(max_per_order("20")), snapshot(), f).verdict == "step_up"
    assert decide(p, mandate(max_per_order("19")), snapshot(), f).verdict == "decline"


@pytest.mark.parametrize("probability", [float("nan"), float("inf"), -1, 2, "yes", True])
def test_malformed_model_output_falls_back_without_caching(probability):
    model = Model(answers(probability))
    r = FallbackReader(reader(model), RegexReader())
    p = purchase()
    assert r.read(p, Budget()).model_unavailable
    model.result = answers(.1)
    assert not r.read(p, Budget()).model_unavailable
    assert len(model.calls) == 2


def test_wrong_questions_and_oversized_model_input_are_rejected():
    model = Model({})
    with pytest.raises(ValueError):
        reader(model).read(purchase(), Budget())
    r = LayaReader(model, fits=lambda state, questions: "input_would_truncate")
    with pytest.raises(ValueError, match="truncate"):
        r.read(purchase(), Budget())


def test_busy_reader_and_exhausted_budget_fail_without_inference():
    model = Model()
    r = reader(model)
    r._lock.acquire()
    try:
        with pytest.raises(RuntimeError, match="busy"):
            r.read(purchase(), Budget())
    finally:
        r._lock.release()
    class Expired:
        def remaining_seconds(self):
            return 0
    with pytest.raises(TimeoutError):
        r.read(purchase(), Expired())
    assert not model.calls


def test_checkpoint_tampering_is_rejected_before_model_import(tmp_path):
    import json
    (tmp_path / "model.safetensors").write_bytes(b"changed")
    (tmp_path / "download_provenance.json").write_text(json.dumps({"files": {"model.safetensors": "bad"}}))
    with pytest.raises(ValueError, match="hash mismatch"):
        LayaReader.from_checkpoint(tmp_path)


def test_pinned_pretrained_checkpoint_needs_no_shop_training_report(tmp_path, monkeypatch):
    import hashlib
    import json
    import sys
    from types import SimpleNamespace
    weights = b"test checkpoint"
    (tmp_path / "model.safetensors").write_bytes(weights)
    (tmp_path / "tokenizer").mkdir()
    config = tmp_path / "tokenizer/tokenizer_config.json"
    config.write_text("original")
    (tmp_path / "download_provenance.json").write_text(json.dumps({
        "repo": "baseline", "revision": "pinned",
        "files": {"model.safetensors": hashlib.sha256(weights).hexdigest()}}))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(set_num_threads=lambda n: None))
    def normalizing_agent(path, **kw):
        from pathlib import Path
        (Path(path) / "tokenizer/tokenizer_config.json").write_text("normalized")
        return Model()
    monkeypatch.setitem(sys.modules, "laya", SimpleNamespace(Agent=normalizing_agent))
    monkeypatch.setattr("leash.adapters.laya_reader.sequence_fits", lambda *a: None)
    assert isinstance(LayaReader.from_checkpoint(tmp_path), LayaReader)
    assert config.read_text() == "original"


def test_shadow_observes_without_changing_deterministic_facts(caplog):
    p = purchase()
    r = ShadowReader(FallbackReader(reader(Model()), RegexReader()))
    with caplog.at_level(logging.INFO, logger="leash.laya"):
        f = r.read(p, Budget())
    assert f == RegexReader().read(p, Budget())
    assert "shadow" in caplog.text and "instruction_in_shop_text" in caplog.text
    assert p.items[0].details not in caplog.text


def test_unconfigured_worker_keeps_regex_and_invalid_mode_fails():
    assert isinstance(configured_reader({}), RegexReader)
    with pytest.raises(ValueError, match="MODE"):
        configured_reader({"LEASH_LAYA_CHECKPOINT": "/missing", "LEASH_LAYA_MODE": "typo"})


def test_configured_worker_wraps_loaded_model_and_defaults_to_shadow(monkeypatch):
    monkeypatch.setattr(LayaReader, "from_checkpoint", classmethod(lambda cls, *args, **kw: reader(Model())))
    env = {"LEASH_LAYA_CHECKPOINT": "/model"}
    assert isinstance(configured_reader(env), ShadowReader)
    active = configured_reader({**env, "LEASH_LAYA_MODE": "augment"})
    assert isinstance(active, FallbackReader)
    assert active.read(purchase(), Budget()).reader == "laya+regex"
