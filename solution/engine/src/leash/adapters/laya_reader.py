"""Optional local shop-text model. Model facts never carry payment authority.

Four applicable bank questions run together per cart line. Item matching requires
the customer's requested product, which the FactReader port does not receive;
it stays in deterministic basket rules. Numeric size/days stay with regex.
"""

import hashlib
import json
import logging
import shutil
import tempfile
import threading
from functools import lru_cache
from pathlib import Path

from leash.adapters.fallback_reader import FallbackReader
from leash.adapters.regex_reader import RegexReader
from leash.domain.facts import Facts, bounded_lines
from leash.reading.laya import decode, sequence_fits
from leash.reading.question_bank import BANK_HASH, QUESTIONS, as_dict

log = logging.getLogger("leash.laya")


class LayaReader:
    def __init__(self, agent, *, fits=None):
        self.agent = agent
        self.questions = as_dict({k: v for k, v in QUESTIONS.items() if k != "item_match"})
        self._fits = fits or (lambda state, questions: sequence_fits(agent, state, questions))
        self._lock = threading.Lock()
        self._cached = lru_cache(maxsize=1024)(self._predict)

    @classmethod
    def from_checkpoint(cls, checkpoint, *, device="cpu", threads=4):
        path = Path(checkpoint).resolve(strict=True)
        provenance = json.loads((path / "download_provenance.json").read_text())
        for name, expected in provenance["files"].items():
            with (path / name).open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                    raise ValueError(f"Laya checkpoint hash mismatch: {name}")
        training = path / "training_report.json"
        if training.exists() and json.loads(training.read_text())["question_bank_hash"] != BANK_HASH:
            raise ValueError("Laya question bank mismatch")
        if threads < 1:
            raise ValueError("LEASH_LAYA_THREADS must be positive")
        # Optional dependencies load only when a local checkpoint is explicitly configured.
        import torch  # type: ignore[import-not-found]  # optional model runtime
        from laya import Agent  # type: ignore[import-not-found]
        if device == "cuda" and not torch.cuda.is_available():
            raise ValueError("Laya CUDA requested but unavailable")
        torch.set_num_threads(threads)
        # Laya normalizes tokenizer files on load. Keep the verified source immutable;
        # only the large, read-only weight file is linked into this temporary copy.
        with tempfile.TemporaryDirectory(prefix="leash-laya-") as directory:
            local = Path(directory) / "checkpoint"
            shutil.copytree(path, local, ignore=shutil.ignore_patterns("model.safetensors"))
            (local / "model.safetensors").symlink_to(path / "model.safetensors")
            reader = cls(Agent(str(local), device=device))
        reader._cached("Ordinary product. Returns within 14 days.")  # warm before polling
        log.info("Laya loaded: weights=%s bank=%s device=%s", provenance["files"]["model.safetensors"],
                 BANK_HASH, device)
        return reader

    def _predict(self, text):
        # The shop checkpoint was trained on request + text. This neutral reading task
        # supplies that schema without inventing a customer request or payment authority.
        state = {"request": "Read the product listing.", "text": text}
        reason = self._fits(state, self.questions)
        if reason:
            raise ValueError(reason)  # do not silently truncate a model input
        return decode(self.agent.predict(state, self.questions)["answers"], self.questions)

    def read(self, purchase, budget):
        # ponytail: one model call at a time; reject busy calls rather than queue timed-out
        # work. Use a batched inference service if concurrent checkout throughput needs it.
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("Laya reader busy")
        try:
            texts, oversized = bounded_lines([item.details for item in purchase.items])
            injection, final_sale, addons, recurring = None, None, set(), set()
            for item, text in zip(purchase.items, texts, strict=True):
                if budget.remaining_seconds() <= 0:
                    raise TimeoutError("Laya budget exhausted")
                if not text:
                    continue
                result = self._cached(text)
                if result["injection"] and injection is None:
                    injection = text  # entire source line, not a model-invented quotation
                if result["addon"]:
                    addons.add(item.line_no)
                if result["recurring"]:
                    recurring.add(item.line_no)
                if result["return_terms"] == "final_sale":
                    final_sale = True
            return Facts("laya", None, None, final_sale, injection, frozenset(addons),
                         frozenset(recurring), oversized_text=oversized)
        finally:
            self._lock.release()


class ShadowReader:
    def __init__(self, reader):
        self.reader = reader

    def read(self, purchase, budget):
        merged = self.reader.read(purchase, budget)
        baseline = merged.deterministic or merged
        log.info("Laya shadow: authorization=%s unavailable=%s cautions=%s addons=%s final_sale=%s",
                 purchase.authorization_id, merged.model_unavailable, merged.cautions,
                 sorted(merged.addon_lines - baseline.addon_lines), merged.final_sale)
        return baseline


def configured_reader(env):
    checkpoint = env.get("LEASH_LAYA_CHECKPOINT")
    if not checkpoint:
        return RegexReader()
    mode = env.get("LEASH_LAYA_MODE", "shadow")
    if mode not in ("shadow", "augment"):
        raise ValueError("LEASH_LAYA_MODE must be shadow or augment")
    primary = LayaReader.from_checkpoint(checkpoint, device=env.get("LEASH_LAYA_DEVICE", "cpu"),
                                         threads=int(env.get("LEASH_LAYA_THREADS", "4")))
    reader = FallbackReader(primary, RegexReader())
    return ShadowReader(reader) if mode == "shadow" else reader
