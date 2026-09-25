# Benchmark and evaluation archive

[Back to the jury README](../README.md#what-we-measured)

Evidence snapshot: **25 September 2026**. The current application uses **Gemini for permission drafting and Jev for merchant-text reading**. Jev permission verification is in shadow mode. Laya and Apertus reports document earlier experiments and comparisons; their results are not transferred to the current models.

This catalogue preserves the existing results, including unsuccessful runs. No benchmark was rerun for this documentation update. Follow a report for its exact cases, predictions, timing, model configuration, code/data hashes and limitations where recorded. Counts from different runs or overlapping regression suites must not be added together.

## How to read the evidence

- **Replay and properties:** consistency, ledger behavior and enforcement under specified rules. The 45 supplied purchases have no official answer key; verdict agreement is not payment accuracy.
- **Model diagnostics:** small authored examples, often repeated or template-derived. Trials, examples and independent semantic families are different units. These are not production error-rate estimates.
- **Training and calibration:** results on the named partition and checkpoint. Development data inspected during iteration is not an unseen final test. Calibration measures confidence, not whether a rule interpretation is correct.
- **Integration and browser checks:** whether the tested path delivers and displays outcomes. They do not prove authenticated consent, settlement, fulfillment or universal journey acceptance.
- **Plans and supporting records:** hypotheses, sampling, provenance, token checks and review queues. A plan or execution script alone does not establish a completed result.

The README contains the principal [comparison scores](../README.md#permission-drafting-and-merchant-text-reading) and [training lessons](../README.md#what-training-taught-us). This archive provides the full evidence behind them, including results not selected as headline numbers.

## Gemini and Jev results

The migration comparison covers 16 permission cases and 24 merchant texts, each repeated twice, with Gemini, Apertus, the compiler, enforcing Jev verification, Jev-only reading and Jev/regex reading. The four-flag reader measurements predate the expanded reader. Later expanded-reader and hardening diagnostics have their own reports and budgets.

Read [the benchmark methods and interpretation](openrouter-benchmark.md) and [the later live validation](live-journey-validation.md) before comparing their numbers. The combined OpenRouter report derives targeted scores from the original predictions; it is not an additional independent run.

- [guardrail-after-hardening.json](../../output/guardrail-after-hardening.json)
- [guardrail-live-probes.json](../../output/guardrail-live-probes.json)
- [guardrail-probes.json](../../output/guardrail-probes.json)
- [jev-full-reader-quality-check.json](../../output/jev-full-reader-quality-check.json)
- [jev-full-reader-recheck.json](../../output/jev-full-reader-recheck.json)
- [jev-full-reader-reverse-order.json](../../output/jev-full-reader-reverse-order.json)
- [jev-full-reader.json](../../output/jev-full-reader.json)
- [openrouter-benchmark-2026-09-25.json](../../output/openrouter-benchmark-2026-09-25.json)
- [openrouter-comparison-2026-09-25.json](../../output/openrouter-comparison-2026-09-25.json)
- [openrouter-controls-2026-09-25.json](../../output/openrouter-controls-2026-09-25.json)
- [permission-jev-hardening.json](../../output/permission-jev-hardening.json)

## Deterministic engine, replay and assumptions

These reports retain repeated replay, rule coverage, assumption sensitivity, reader/policy comparisons and regression evidence. `baseline.json` is the recorded expected regression baseline; it is not Viseca ground truth. The historical benchmark ledger records separate measurements rather than a cumulative score.

- [decision-layer-analysis.json](../../output/decision-layer-analysis.json)
- [decision-layer-eval-fast.json](../../output/decision-layer-eval-fast.json)
- [decision-layer-eval-fast.md](../../output/decision-layer-eval-fast.md)
- [decision-layer-findings.md](../../output/decision-layer-findings.md)
- [decision-layer-validation.xml](../../output/decision-layer-validation.xml)
- [scenario-evaluation-2026-09-25.json](../../output/scenario-evaluation-2026-09-25.json)
- [scenario-evaluation-2026-09-25.md](../../output/scenario-evaluation-2026-09-25.md)
- [scenario-replay-2026-09-25.txt](../../output/scenario-replay-2026-09-25.txt)

- [REPORT.md](../engine/evals/REPORT.md)
- [baseline.json](../engine/evals/baseline.json)
- [benchmark-history.jsonl](../engine/evals/benchmark-history.jsonl)
- [benchmark.json](../engine/evals/benchmark.json)
- [report.json](../engine/evals/report.json)

## Historical Apertus payment-reasoning experiment

Read [the experiment report](ai-decision-experiment.md). The initial independent run contains superseded control fixtures; use its 45 pack rows and the separately corrected control report. The advisory run uses corrected controls. Valid JSON or an existing evidence pointer does not prove that the model's conclusion follows from the input.

- [ai-reasoning-advisory-v2.json](../../output/ai-reasoning-advisory-v2.json)
- [ai-reasoning-controls-v2.json](../../output/ai-reasoning-controls-v2.json)
- [ai-reasoning-shadow-v1.json](../../output/ai-reasoning-shadow-v1.json)

## Historical Laya checkout experiments

Read [the system evaluation](laya-system-evaluation.md). Initial text-only inputs, corrected training-shaped inputs, semantic diagnostics and fake-platform delivery runs are distinct conditions. Integration success did not override failed model-quality checks. XML files record test execution, not semantic accuracy.

- [laya-fact-schema-diagnostic.json](../../output/laya-fact-schema-diagnostic.json)
- [laya-facts-platform.json](../../output/laya-facts-platform.json)
- [laya-finetuned-comparison.json](../../output/laya-finetuned-comparison.json)
- [laya-finetuned-facts.json](../../output/laya-finetuned-facts.json)
- [laya-finetuned-platform.json](../../output/laya-finetuned-platform.json)
- [laya-finetuned-platform.xml](../../output/laya-finetuned-platform.xml)
- [laya-injection-probes.json](../../output/laya-injection-probes.json)
- [laya-integration-regression.xml](../../output/laya-integration-regression.xml)
- [laya-platform-eval.json](../../output/laya-platform-eval.json)
- [laya-platform-eval.xml](../../output/laya-platform-eval.xml)
- [laya-pretrained-comparison.json](../../output/laya-pretrained-comparison.json)
- [laya-pretrained-facts.json](../../output/laya-pretrained-facts.json)
- [laya-pretrained-platform.json](../../output/laya-pretrained-platform.json)
- [laya-pretrained-platform.xml](../../output/laya-pretrained-platform.xml)
- [laya-system-eval.json](../../output/laya-system-eval.json)

## Customer journey, hosted delivery and recovery

These records include earlier failures, subsequent fixes, local simulator runs and the later hosted run. Use [the latest hosted validation](live-journey-validation.md) for the documented state after hardening. Earlier browser reports are retained as regression evidence, not a claim that every earlier defect is still present or that every journey is now accepted.

- [clothing-history-check.txt](../../output/clothing-history-check.txt)
- [functional-test-2026-09-25.md](../../output/functional-test-2026-09-25.md)
- [history-draft-repair.json](../../output/history-draft-repair.json)
- [history-quote-regression-replay.json](../../output/history-quote-regression-replay.json)
- [live-hardening-outcome.json](../../output/live-hardening-outcome.json)
- [live-hardening-recovery.json](../../output/live-hardening-recovery.json)
- [live-hardening-start.json](../../output/live-hardening-start.json)
- [local-browser-journey.json](../../output/local-browser-journey.json)
- [local-household-retest.json](../../output/local-household-retest.json)
- [local-model-scenarios.json](../../output/local-model-scenarios.json)
- [local-simulation-verification.md](../../output/local-simulation-verification.md)
- [manipulated-clarification-failure.json](../../output/manipulated-clarification-failure.json)
- [manipulated-latest-draft.json](../../output/manipulated-latest-draft.json)
- [manipulated-local-platform-run.json](../../output/manipulated-local-platform-run.json)
- [manipulated-local-replay.txt](../../output/manipulated-local-replay.txt)
- [manipulated-scenario-retest.md](../../output/manipulated-scenario-retest.md)

## Laya shop-text training and calibration

Read [the training record](../training/README.md#shop-text-task) for data construction, public-source restrictions, split discipline and results. The baseline, v1 and v2 training, development comparison and calibration reports are separate experiments. Neither improving recall on template-derived cases nor lower calibration error establishes deployment readiness.

- [laya-baseline-shop-splits-v1.json](../training/reports/laya-baseline-shop-splits-v1.json)
- [laya-calibration-shop-splits-v1.json](../training/reports/laya-calibration-shop-splits-v1.json)
- [laya-calibration-shop-splits-v2.json](../training/reports/laya-calibration-shop-splits-v2.json)
- [laya-development-comparison-shop-splits-v1.json](../training/reports/laya-development-comparison-shop-splits-v1.json)
- [laya-development-comparison-shop-splits-v2.json](../training/reports/laya-development-comparison-shop-splits-v2.json)
- [laya-finetune-shop-splits-v1.json](../training/reports/laya-finetune-shop-splits-v1.json)
- [laya-finetune-shop-splits-v1.log](../training/reports/laya-finetune-shop-splits-v1.log)
- [laya-finetune-shop-splits-v2.json](../training/reports/laya-finetune-shop-splits-v2.json)
- [laya-finetune-shop-splits-v2.log](../training/reports/laya-finetune-shop-splits-v2.log)
- [pack-review-v2.csv](../training/reports/pack-review-v2.csv)
- [regex-shop-splits-v1.json](../training/reports/regex-shop-splits-v1.json)
- [shop-data-v2-preflight.json](../training/reports/shop-data-v2-preflight.json)
- [shop-data-v2.json](../training/reports/shop-data-v2.json)

## Laya permission data readiness and review

Draft labels and assistant review passes are not independent human adjudication. Token preflights check whether evidence fits the model; they do not score understanding. Review and sampling artifacts are retained so that later corrections can be traced.

- [permission-challenge-v4-review-guide.md](../training/reports/permission-challenge-v4-review-guide.md)
- [permission-data-readiness-v1.json](../training/reports/permission-data-readiness-v1.json)
- [permission-scenarios-v1-token-preflight.json](../training/reports/permission-scenarios-v1-token-preflight.json)
- [permission-v2-token-preflight.json](../training/reports/permission-v2-token-preflight.json)
- [permission-v3-token-preflight.json](../training/reports/permission-v3-token-preflight.json)
- [permission-v4-token-preflight.json](../training/reports/permission-v4-token-preflight.json)
- [permission-v6-review-assistant-pass.jsonl](../training/reports/permission-v6-review-assistant-pass.jsonl)
- [permission-v6-review-decisions.jsonl](../training/reports/permission-v6-review-decisions.jsonl)
- [permission-v6-review-sample.jsonl](../training/reports/permission-v6-review-sample.jsonl)
- [permission-v7-omission-sample.jsonl](../training/reports/permission-v7-omission-sample.jsonl)

## Permission v3: baseline, fine-tuning and calibration

The first permission training comparison, epoch diagnostics, tensor verification and local checkpoint reload. See the [executed baseline and training narrative](../training/README.md#executed-original-model-diagnostic).

- [laya-permission-baseline-v3.json](../training/reports/laya-permission-baseline-v3.json)
- [laya-permission-baseline-v3.log](../training/reports/laya-permission-baseline-v3.log)
- [laya-permission-calibration-v3.json](../training/reports/laya-permission-calibration-v3.json)
- [laya-permission-comparison-v3.json](../training/reports/laya-permission-comparison-v3.json)
- [laya-permission-completion-v3.json](../training/reports/laya-permission-completion-v3.json)
- [laya-permission-epoch-diagnostics-v3.json](../training/reports/laya-permission-epoch-diagnostics-v3.json)
- [laya-permission-finetune-v3.json](../training/reports/laya-permission-finetune-v3.json)
- [laya-permission-finetune-v3.log](../training/reports/laya-permission-finetune-v3.log)
- [laya-permission-local-load-v3.json](../training/reports/laya-permission-local-load-v3.json)
- [laya-permission-sampling-v3.json](../training/reports/laya-permission-sampling-v3.json)
- [laya-permission-weight-verification-v3.json](../training/reports/laya-permission-weight-verification-v3.json)

## Permission v4: matched objective comparison

CE and RLCD+CE used matched samples; selection preceded the separately authored challenge. The archive includes both candidates, failed generalization, input-format probes and calibration. See the [v4 interpretation](../training/README.md#executed-v4-results-coverage-repaired-generalization-still-inadequate).

- [laya-permission-baseline-v4.json](../training/reports/laya-permission-baseline-v4.json)
- [laya-permission-calibration-v4.json](../training/reports/laya-permission-calibration-v4.json)
- [laya-permission-local-load-v4.json](../training/reports/laya-permission-local-load-v4.json)
- [laya-permission-v4-ce-comparison.json](../training/reports/laya-permission-v4-ce-comparison.json)
- [laya-permission-v4-ce-diagnostics-complete.json](../training/reports/laya-permission-v4-ce-diagnostics-complete.json)
- [laya-permission-v4-ce-run.json](../training/reports/laya-permission-v4-ce-run.json)
- [laya-permission-v4-ce-sampling.json](../training/reports/laya-permission-v4-ce-sampling.json)
- [laya-permission-v4-ce-training.log](../training/reports/laya-permission-v4-ce-training.log)
- [laya-permission-v4-challenge.json](../training/reports/laya-permission-v4-challenge.json)
- [laya-permission-v4-complete.json](../training/reports/laya-permission-v4-complete.json)
- [laya-permission-v4-finish.log](../training/reports/laya-permission-v4-finish.log)
- [laya-permission-v4-format-probe.json](../training/reports/laya-permission-v4-format-probe.json)
- [laya-permission-v4-rlcd-ce-comparison.json](../training/reports/laya-permission-v4-rlcd-ce-comparison.json)
- [laya-permission-v4-rlcd-ce-diagnostics-complete.json](../training/reports/laya-permission-v4-rlcd-ce-diagnostics-complete.json)
- [laya-permission-v4-rlcd-ce-run.json](../training/reports/laya-permission-v4-rlcd-ce-run.json)
- [laya-permission-v4-rlcd-ce-sampling.json](../training/reports/laya-permission-v4-rlcd-ce-sampling.json)
- [laya-permission-v4-rlcd-ce-training.log](../training/reports/laya-permission-v4-rlcd-ce-training.log)
- [laya-permission-v4-selection.json](../training/reports/laya-permission-v4-selection.json)

## Permission v5: scenario augmentation

The added-scenario experiment failed its predeclared improvement criterion. In-sample scenario results remain separate from development results. See the [v5 interpretation](../training/README.md#permission-v5-scenario-augmentation-experiment).

- [laya-permission-baseline-v5.json](../training/reports/laya-permission-baseline-v5.json)
- [laya-permission-baseline-v5.log](../training/reports/laya-permission-baseline-v5.log)
- [laya-permission-calibration-v5.json](../training/reports/laya-permission-calibration-v5.json)
- [laya-permission-v5-comparison.json](../training/reports/laya-permission-v5-comparison.json)
- [laya-permission-v5-complete.json](../training/reports/laya-permission-v5-complete.json)
- [laya-permission-v5-experiment-summary.json](../training/reports/laya-permission-v5-experiment-summary.json)
- [laya-permission-v5-experiment.log](../training/reports/laya-permission-v5-experiment.log)
- [laya-permission-v5-extra-diagnostics.json](../training/reports/laya-permission-v5-extra-diagnostics.json)
- [laya-permission-v5-run.json](../training/reports/laya-permission-v5-run.json)
- [laya-permission-v5-sampling.json](../training/reports/laya-permission-v5-sampling.json)
- [laya-permission-v5-training.log](../training/reports/laya-permission-v5-training.log)
- [laya-permission-v5-verification.json](../training/reports/laya-permission-v5-verification.json)

## Permission v6: sampling and contrast diagnostics

The summary records a failed improvement criterion and zero human-reviewed examples. Its execution note explains that summary completion followed an error in the runner’s final diagnostic.

- [laya-permission-v6-comparison.json](../training/reports/laya-permission-v6-comparison.json)
- [laya-permission-v6-complete.json](../training/reports/laya-permission-v6-complete.json)
- [laya-permission-v6-experiment-summary.json](../training/reports/laya-permission-v6-experiment-summary.json)
- [laya-permission-v6-experiment.log](../training/reports/laya-permission-v6-experiment.log)
- [laya-permission-v6-extra-diagnostics.json](../training/reports/laya-permission-v6-extra-diagnostics.json)
- [laya-permission-v6-run.json](../training/reports/laya-permission-v6-run.json)
- [laya-permission-v6-sampling.json](../training/reports/laya-permission-v6-sampling.json)
- [laya-permission-v6-training.log](../training/reports/laya-permission-v6-training.log)

## Permission v7: equal and precision weighting

Both reported variants failed the improvement criterion. The v4-to-v7 comparison changes both corpus and question bank; equal versus precision weighting is the controlled comparison. The prior-fit diagnostic is separate from the unadjusted predictions.

- [laya-permission-v7-equal-comparison.json](../training/reports/laya-permission-v7-equal-comparison.json)
- [laya-permission-v7-equal-prior-fit.json](../training/reports/laya-permission-v7-equal-prior-fit.json)
- [laya-permission-v7-equal-run.json](../training/reports/laya-permission-v7-equal-run.json)
- [laya-permission-v7-equal-sampling.json](../training/reports/laya-permission-v7-equal-sampling.json)
- [laya-permission-v7-experiment-summary.json](../training/reports/laya-permission-v7-experiment-summary.json)
- [laya-permission-v7-experiment.log](../training/reports/laya-permission-v7-experiment.log)
- [laya-permission-v7-extra-diagnostics.json](../training/reports/laya-permission-v7-extra-diagnostics.json)
- [laya-permission-v7-precision-comparison.json](../training/reports/laya-permission-v7-precision-comparison.json)
- [laya-permission-v7-precision-run.json](../training/reports/laya-permission-v7-precision-run.json)

## Experiment plans and later research hypotheses

These are **plans, not standalone result reports**. Completed v4–v7 results appear above. For v8–v12, this checkout contains plans and archived execution scripts but no corresponding complete result report in this catalogue. Some plans mention earlier observations; that does not establish the outcome of the planned run. No new score or completion claim is inferred from them.

The later hypotheses include epoch/objective sweeps, reference/context examples, sampling balance, shop add-on variety and corrected condition IDs. The v11 plan concerns shop-text training despite its permission-prefixed filename.

- [laya-permission-v10-plan.json](../training/reports/laya-permission-v10-plan.json)
- [laya-permission-v11-plan.json](../training/reports/laya-permission-v11-plan.json)
- [laya-permission-v12-plan.json](../training/reports/laya-permission-v12-plan.json)
- [laya-permission-v4-plan.json](../training/reports/laya-permission-v4-plan.json)
- [laya-permission-v5-plan.json](../training/reports/laya-permission-v5-plan.json)
- [laya-permission-v6-plan.json](../training/reports/laya-permission-v6-plan.json)
- [laya-permission-v7-plan.json](../training/reports/laya-permission-v7-plan.json)
- [laya-permission-v8-plan.json](../training/reports/laya-permission-v8-plan.json)
- [laya-permission-v9-plan.json](../training/reports/laya-permission-v9-plan.json)

## Reproduction and source material

- [Engine evaluation runners](../engine/evals/) — replay, comparative readers, reasoning, OpenRouter, expanded Jev and guardrail diagnostics.
- [Training scripts and datasets](../training/) — corpus generation, source imports, splitting, training, calibration and evaluation.
- [Archived training scripts, logs and reports](../training/reports/) — exact executed sources and supporting artifacts alongside the linked result files.
- [Runtime setup and model configuration](../RUNBOOK.md) — current Gemini/Jev configuration, explicit offline mode, simulator and hosted setup.
- [Decision log](decisions.md) — rule sources, assumptions and authority boundaries used to interpret the results.

Reproduction commands are documented with their individual experiments. Keep the original reports and write reruns to new paths. Historical Laya/Apertus setup instructions describe those experiments; the current application configuration is documented in the runbook.
