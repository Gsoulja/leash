# OpenRouter migration benchmark — 25 September 2026

Use Gemini 3.8 Flash with low reasoning and latency-based OpenRouter routing for permission drafting. Keep Jev rule verification in **shadow** mode until calibrated: the measured enforcement threshold rejected valid instructions.

Implementation update: the production fact reader now uses Jev alone, including typed sizes and return windows. Regex remains an offline/benchmark baseline. Reader failures and ambiguous extractions reach customer confirmation. The measurements below describe the earlier four-flag reader and its regex merge; they are historical results, not measurements of the expanded reader. Reproduce the expanded-reader checks with `evals.jev` as documented in the runbook.

Expanded-reader live diagnostics: the first run passed 9/12 cases, with three transport failures. Rechecking those failures passed 1/3; reversing all cases passed 7/12, again with transport failures. The two inputs never successfully read in those runs both returned the expected facts with a five-second diagnostic HTTP timeout (5.63 s and 2.12 s total elapsed). All 12 expected outcomes were therefore observed across runs, **not** in one successful production-budget run. Production retains its one-second per-phase HTTP timeout and the engine's overall deadline; failures request confirmation. These results validate extraction behavior but do not establish a reliable latency target. Raw runs are retained at `output/jev-full-reader.json`, `output/jev-full-reader-recheck.json`, `output/jev-full-reader-reverse-order.json` and `output/jev-full-reader-quality-check.json`.

## Measured results

The permission corpus contains 16 authored cases, run twice per approach. A pass requires the labeled restrictions, intended routing, forbidden-field checks and clarification on specified ambiguous cases. Extra proposals are recorded, but not all are scored as errors.

- **Gemini:** 32/32 passes; median 1.147 s, p95 1.540 s.
- **Apertus:** 24/32; median 1.228 s, p95 59.610 s.
- **Deterministic compiler:** 12/32; median 0.20 ms, p95 0.35 ms. Its deliberately narrow grammar does not cover several paraphrases, corrections and languages in this corpus.
- **Gemini with enforcing Jev verification:** 29/32; median 1.438 s, p95 1.842 s. The verifier rejected three correct readings. This is the enforcement experiment, not the selected shadow behavior.

The fact corpus contains 24 authored texts, run twice. Each has a targeted condition: add-on, recurring charge, final sale or payment-steering instruction.

- **Regex:** targeted condition correct in 16/48 trials; median 0.22 ms.
- **Jev:** 44/48; median 299 ms, p95 596 ms.
- **Jev + regex, one-second fallback budget:** 43/48; median 303 ms, p95 501 ms. No fallback was observed in these trials.

A stricter comparison against all four flags gives 16/48, 34/48 and 33/48 respectively. It treats omitted labels as false; some cross-label mismatches are ambiguous, such as subscription text also being identified as an add-on. Both scores and every prediction are retained. Included product warranties and a negated authority statement are genuine false-alarm examples; more flags are not automatically better.

In 12 separate rule-verification controls at threshold 0.9, Jev rejected all six deliberately wrong rules **and all six valid rules**. That is why blocking verification is disabled by default. The threshold was not tuned on these results.

An offline replay of all 45 fixture purchases produced the same verdict counts with regex and Jev + regex: 12 approve, 11 step-up, 22 decline. There were no weaker decisions or model timeouts. This checks the deterministic floor, not payment accuracy: those fixtures have no ground-truth verdict labels.

## Scope and reproduction

These are small authored diagnostics, not independently reviewed production benchmarks. Two repeats are not 32 independent permission cases. Models use their actual adapters and prompts, followed by the same current permission validation; this is an application comparison, not an identical-prompt model leaderboard. Chat requests used a 15-second per-attempt timeout and one SDK retry; latency includes waits and validation (Apertus timing excludes the host-side validation step). Jev fact calls use a one-second timeout. No payment or permission-activation API was called.

Results and all cases: `output/openrouter-benchmark-2026-09-25.json` at the repository root. Original measurements remain in `output/openrouter-comparison-2026-09-25.json`; verifier controls and replay are in `output/openrouter-controls-2026-09-25.json`. The combined report adds targeted fact scores from the unchanged predictions without replacing the original strict scores.

```bash
cd solution/engine
PYTHONPATH=..:src .venv/bin/python -m evals.openrouter \
  --apertus-container leash-local-assistant-1 \
  --repeats 2 --output ../../output/new-comparison.json
```

The Apertus comparison invokes its original adapter inside the configured container; no credential is extracted. Keep that adapter for reproducibility. The worker no longer loads Laya; its old training/evaluation files remain historical experiments.

Configuration in `solution/.env` stays ignored and private. Runtime defaults are `LEASH_MODEL=google/gemini-3.8-flash`, `LEASH_MODEL_REASONING=low`, `LEASH_FACT_READER=jev`, `LEASH_RULE_CLASSIFIER=jev`, and `LEASH_JEV_RULE_MODE=shadow`. `enforce` is an explicit experiment, not the recommended default. The engine still validates rules and requires customer confirmation of permissions. Structured amounts and confirmed policy are enforced deterministically; the production reader no longer imposes regex findings on Jev's interpretation.

Sources: [Gemini 3.8 Flash on OpenRouter](https://openrouter.ai/google/gemini-3.8-flash), [Jev Decisions API tutorial](https://openrouter.ai/docs/guides/community/jev-tutorial), [TypeSafe System One introduction](https://typesafe.ai/blog/introducing-system-one-models-and-jev).
