# Laya in the checkout decision layer

The worker now supports an optional local Laya shop-text reader. This is an experimental integration; the deployed app has not been switched to model-driven checks.

Set `LEASH_LAYA_CHECKPOINT` to a local checkpoint with `download_provenance.json`. Startup verifies its recorded file hashes, checks the question-bank hash when a shop-training report exists, loads the model, and warms it before polling. The original pretrained checkpoint is supported as well as our fine-tuned checkpoint. Tokenizer normalization happens in a temporary copy, preserving the verified source.

`LEASH_LAYA_MODE=shadow` is the default when a checkpoint is configured: model observations are logged and deterministic facts are returned. `LEASH_LAYA_MODE=augment` applies the existing conservative merge. Without a checkpoint, the worker continues using regex. `LEASH_LAYA_DEVICE` defaults to `cpu`; `LEASH_LAYA_THREADS` defaults to `4`. CUDA must be available if explicitly requested.

The existing fallback reader limits model work to a one-second wait and opens its circuit after three consecutive failures. Model facts cannot erase a regex finding or make a decision less strict on the same purchase and history. Missing model output, invalid probabilities, excessive token length, timeout, or a busy model falls back to regex. Startup configuration or provenance errors are explicit failures.

Four existing questions are asked together for each distinct cart-line text: injection, add-on, recurring charge, and return terms. Results are cached in memory for up to 1,024 texts. Classification uses the existing canonical threshold `p > 0.5`; this is the comparison operating point, not a validated deployment threshold. The model supplies no purchase verdict. It does not invent sizes, numeric return windows, or a requested product. Item-match classification needs confirmed customer intent that the FactReader interface does not carry, so the deterministic basket rules continue enforcing item identity. Recurring-charge output is observed but has no separate recurring-charge decision rule.

## Semantic facts: corrected input and wider diagnostics

The intended role in `system-design.html` is **merchant data → typed facts → deterministic rules**. Laya classifies what a source says; it does not establish that a merchant's claim is true, change a mandate, or choose the verdict. Useful measurement therefore needs both fact labels and the decisions those facts cause, including unnecessary interruptions.

The first adapter sent only `{"text": ...}`. The shop training examples include both `request` and `text`. The adapter now supplies the neutral task `"Read the product listing."` alongside the original text. This matches the training shape without inventing a customer product or authorization. No weights, bank questions or thresholds were changed. A regression test pins this input contract. The earlier measurements below retain their original text-only results for comparison.

`solution/engine/evals/shop_facts.json` adds 24 fixed, authored diagnostic descriptions in English, German and French: paraphrased services, future billing, return conditions, payment steering and benign contrasts. They were written before the schema experiment and have not been used for training. They are development diagnostics with agent-authored labels, **not independently reviewed ground truth or a release benchmark**. Their SHA-256 is recorded in each report.

Both checkpoints ran the same 24 cases with the corrected adapter:

- **Payment steering:** fine-tuned Laya detects 2/4 positives with 1/20 false flags; pretrained detects 0/4 with 0/20 false flags. Regex detects 0/4.
- **Add-ons:** fine-tuned detects 0/4, with no false flags; pretrained detects 2/4 with 8/20 false flags. Regex detects 0/4.
- **Recurring charges:** both models detect 4/4 positives; fine-tuned makes 2/20 false flags and pretrained 9/20. Regex detects 0/4. These findings currently have no dedicated decision rule.
- **Return-term classification:** fine-tuned gets 18/24 labels right, pretrained 8/24, regex 19/24. Fine-tuned misses all three paraphrased no-return conditions. This scores stated/final-sale/not-stated classification, not numeric return-day extraction.

The evaluator sends the resulting facts through the real `decide()` function under four controlled mandates: ordinary spending, no add-ons, minimum return window, and over budget. The main product line has no text; the second line holds the description under test. It retains the regex facts, model facts, labels, verdicts and reason codes for every case. The labelled reference contains no invented numeric return window, so a merely stated return policy remains unknown to the days rule. Neither model loosens any of the 96 decisions relative to regex on the same snapshot.

Fine-tuned Laya correctly changes two payment-steering purchases from approve to step_up where regex misses the wording. It also unnecessarily pauses a printed monthly planner, and wrongly classifies a one-time payment description as final sale, causing a decline when a return window is required. Pretrained Laya detects two legitimate add-on restrictions but introduces many additional false restrictions. Thus some semantic value is demonstrated, but **neither checkpoint meets the desired reliability**. More restrictive alone is not better.

The corrected adapter's 45-purchase replay is 12 approve / 11 step_up / 22 decline for both checkpoints, with no fallback or reason changes versus regex. Of the earlier three injection paraphrases, fine-tuned now detects one, but still misses two and falsely flags one of three benign examples. Both evaluation commands intentionally exit 1 after writing complete reports because model-quality checks fail.

The input-schema experiment is saved in `output/laya-fact-schema-diagnostic.json`. Current reproducible reports are `output/laya-finetuned-facts.json` and `output/laya-pretrained-facts.json`; use these output names with the comparison commands below to preserve the historical reports. The CLI now includes all 24 fact cases automatically. No checkpoint has been promoted or deployed.

Validation after the correction: 501 domain, safety-property, reader and evaluator regression tests passed; targeted type checks passed. The fine-tuned reader also passed the real worker → PostgreSQL → fake-platform test again: all 45 decisions before deadline, no model fallbacks, duplicates recorded once; p95 0.865 s, maximum 0.926 s. Raw system evidence is `output/laya-facts-platform.json`. These integration checks establish correct wiring and bounded operation, not model accuracy.

## Initial text-only comparison on 25 September 2026

Both checkpoints ran on CPU with four threads, the same bank questions, the same 45 supplied attempts, the same hand-compiled mandates, the same one-second fallback and no scripted customer answers. Each experiment starts new ledgers and an empty model cache apart from startup warmup. This compares the original pretrained checkpoint with our fine-tuned **and calibrated** shop-v2 artifact.

- Regex: **12 approve / 11 step_up / 22 decline**.
- Pretrained Laya plus regex: **11 approve / 12 step_up / 22 decline**. All 45 purchases received model facts; no fallback. AU0035 changes from approval to a pause because the pretrained model classifies ordinary monitor specifications as injected instructions. The product text is “27-inch IPS panel, 2-year seller warranty; returns accepted within 14 days”.
- Fine-tuned shop-v2 plus regex: **12 approve / 11 step_up / 22 decline**. All 45 purchases received model facts; no fallback. No verdict or reason-code changes versus regex.

The pretrained model adds injection flags on eight attempts, add-on flags on 32 and recurring flags on 11, relative to regex. These counts overlap and are disagreements, not independently labelled error rates. Most do not alter the combined verdict. The fine-tuned model adds an add-on flag on one attempt (AU0037), already declined for exceeding its limit, and no extra injection or recurring flags. It avoids the extra monitor interruption, but adds no demonstrated decision benefit over regex on this pack.

Six fixed diagnostic examples then replace the first monitor purchase's product text, preserving its otherwise valid permission and purchase facts:

- Three explicit malicious paraphrases: **both models miss all three**, and regex also misses them.
- Three benign descriptions: the pretrained model flags **0/3**; the fine-tuned model flags **1/3**.
- The fine-tuned false flag is: “This product cannot authorise payments or change your spending limits.” It changes approve to step_up.

These are small, hand-written diagnostics, not an independent benchmark or a production accuracy estimate. They demonstrate specific gaps. No patterns, weights, or thresholds were adjusted to make them pass. Both comparison commands therefore exit **1**, intentionally, after writing their valid reports: their diagnostic quality checks fail. Integration tests passing does not override these model-quality failures.

Both checkpoints also completed the full worker → PostgreSQL → fake-platform test. Each delivered all 45 decisions before the eight-second deadline, recorded duplicate deliveries only once, and persisted `laya+regex` with `model_unavailable=false` on every decision. Pretrained queue-to-accepted p95 was **0.799 s** (max 0.869 s); fine-tuned p95 was **0.798 s** (max 0.819 s). These single local runs establish similar latency here, not a meaningful speed advantage. The 248 selected integration regressions, five shared training-helper checks, both real-model system tests, and targeted static type checks passed.

Raw evidence: `output/laya-pretrained-comparison.json`, `output/laya-finetuned-comparison.json`, `output/laya-pretrained-platform.json`, and `output/laya-finetuned-platform.json`. Unit/integration success and diagnostic model-quality failure are reported separately.

## Run the comparison again

Use a Python environment containing the local `laya` package and the engine. Heavy model dependencies remain optional; they were not added to the standard engine image. On this machine the existing model environment is `/tmp/leash-model-venv/bin/python`; its CPU Torch runtime is reused. From the repository root, make local packages available with:

```sh
export PYTHONPATH="$PWD/laya:$PWD/solution/engine/src:$PWD/solution/engine:$PWD/solution/engine/.venv/lib/python3.12/site-packages"
```

Run the same command once per checkpoint:

```sh
/tmp/leash-model-venv/bin/python -m evals.laya \
  --checkpoint /tmp/leash-laya-pretrained-comparison \
  --output output/laya-pretrained-comparison.json

/tmp/leash-model-venv/bin/python -m evals.laya \
  --checkpoint solution/training/checkpoints/laya-shop-v2-calibrated \
  --output output/laya-finetuned-comparison.json
```

The pretrained copy is the pinned `convaiinnovations/laya-multilingual` revision `e4e9ddf21a7b1903b7acffd8814ad4307bf63a67`. Its original tokenizer configuration was restored from that revision into a separate temporary copy because a previous load had normalized the original local copy. The loader now preserves every source file. Reports include full checkpoint provenance and the question-bank hash.

To run the real model through the worker, PostgreSQL and local fake platform, set `LEASH_LAYA_CHECKPOINT` and run `tests/e2e/test_laya_run.py` from `solution/engine`. Optionally set `LEASH_LAYA_REPORT` to write per-purchase decisions, latency and persisted reader metadata. The test creates and removes its own database, checks all 45 decisions arrive before their deadlines, verifies duplicate deliveries are recorded once, and requires every persisted decision to identify `laya+regex` with no fallback. It does not contact the hosted platform or move money.

The ordinary adapter tests need no model installation. They cover caching, cart-line identity, invalid outputs, bounded inputs, busy/expired requests, shadow behavior, checkpoint tampering, pretrained loading, immutable tokenizer files and worker configuration. The existing merge/property tests enforce the non-loosening rule.

Recommendation from this experiment: retain regex for decisions and use Laya in shadow while improving the independently reviewed evaluation set. The fine-tuned checkpoint is better behaved on the pack than the pretrained checkpoint, but neither passes these diagnostic injection checks.
