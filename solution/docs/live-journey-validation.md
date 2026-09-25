# Live journey validation — 2026-09-25

The implementation uses the hosted Viseca simulator documented in `technical_details.md` and `solution/postman/connection-check-flow.md`. The live worker was ready before the run. No reset was used. No customer confirmation or step-up answer was fabricated by this validation.

## Observed run

- Existing confirmed mandate: `TM1ec39cca34428b70`.
- Scenario from live bootstrap: `SCEN0101`, with its original instruction unchanged: “Buy one ordinary grocery item for CHF 20 or less from a shop I use regularly. Ask me when uncertain.”
- New validation run: `run_f11ee62f0d98d58d`.
- Hosted result: completed; generated/delivered/finalized/processed **2/2/2/2**, pending/queued **0/0**, platform rejections **0**.
- `AU10001-0d98d58d`: CHF 18 grocery checkout; platform records an approval marked `decision_source: human` and `human_confirmation`. This report describes the platform record, not independent authentication of the person who answered.
- `AU10002-0d98d58d`: CHF 38.90 two-line checkout; engine decline for the amount, familiarity, quantity and subsequent-order checks. Platform recorded the decline about 0.77 seconds after queueing.
- After recovery the app reports one accepted approval and one accepted decline. A repeated Start returned the **same run**, adding **zero** runs.

Raw evidence: [platform outcome](../../output/live-hardening-outcome.json), [initial local error](../../output/live-hardening-start.json), [recovered app record and idempotent retry](../../output/live-hardening-recovery.json).

## Bugs exposed by the live flow

Viseca started the run successfully, but the app returned 502 because it looked for the hosted card in the local scenario pack. The start handler now consumes the returned `fixture_profiles`; a run first recorded by the worker can recover its scenario association from the authenticated platform response. Integration tests cover a card and scenario absent from the local pack. The repaired existing run and safe retry were verified live; the new hosted-start branch was regression-tested with the captured response shape, without creating another permanent run.

`pending_step_up` is now recognized as a waiting state. Reconciliation disagreements remain audit events and are also visible in the app as `conflict:<platform status>`; they never silently change the local verdict or spend. The recovered live record subsequently agreed with the platform. A conflict is excluded from the chat's accepted-outcome totals.

## Delivered PoC controls

Submit/confirm require a positive, exact reviewed revision. The chat resumes its recorded run and shows live checkouts, pending decisions, platform acceptance and completion. No search progress, settlement or fulfillment is invented.

Jev scans merchant name, city, item name, item details and purchase description in one bounded request, retaining raw and normalized text. Off-platform payment, injection and uncertain safety answers cannot auto-approve. Model-only size and return claims retain the structured-only uncertainty findings; regex is not reintroduced. Recurring text adds attention when extras/subscriptions are forbidden. Price plausibility uses exact catalogue item IDs, Decimal FX and the synthetic ranges, with missing references explicit.

The permission verifier checks four support labels and separately scans all customer turns for omissions across registry fields and unsupported conditions. Empty rule lists are still checked. Low-confidence answers remain per-question `ambiguous` results. It stays in shadow mode pending reviewed calibration.

## Validation limits

[Guardrail probes](../../output/guardrail-after-hardening.json) include mocked wrong outputs and six calls to live Jev. Invented size/return facts and a 0.5 injection score now lead to attention. Four English hostile samples returned declines; the German sample abstained on extraction. The benign size/returns sample also required attention because its facts were only model-derived. These are synthetic diagnostics, not measured production attack resistance.

The user's explicit `uncertainty_policy: approve` still allows ordinary missing evidence to approve; the integrity protections remain stricter. Common Unicode lookalikes are handled, not every confusable in every script. Price ranges do not establish merchant honesty or product quality.

[Permission diagnostics](../../output/permission-jev-hardening.json) record the exact four synthetic inputs, model, prompt version, threshold, latency and enforcement fingerprints. **Human-reviewed examples: 0; release-ready: false.** No calibration or held-out accuracy claim follows from these examples. LEASH-156's reviewed corpus gate and production authentication remain open. This live run proves connectivity, actual decision delivery and recovery; it is not acceptance of every possible permission journey.

## Runnable checks

From `solution/engine` with `PYTHONPATH=../:src:tests`:

- `.venv/bin/pytest tests/domain tests/policy tests/application tests/adapters/test_jev.py ../assistant/tests -q` — 1,105 passed.
- `.venv/bin/pytest tests/adapters/test_runs.py tests/adapters/test_policy_api.py -q` — 69 passed, using disposable Postgres databases.
- `.venv/bin/pytest tests/adapters/test_delivery_truth.py tests/scripts/test_connection_check.py tests/policy/test_registry.py ../assistant/tests/test_agent.py -q` — 190 passed. These overlap the larger suite and are not additive counts.

From `solution/app`: `npm run build` and `npm test` passed; the UI suite includes 163 tests. No git commit or remote deployment was made; the existing local Compose services were rebuilt against the hosted simulator.
