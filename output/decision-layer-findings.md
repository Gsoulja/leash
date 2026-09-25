# Does Leash's decision layer do something useful?

Yes: on the supplied 45 attempts, it enforces constraints beyond spending caps and changes downstream spending state. This demonstrates functioning controls, not measured fraud prevention or real-world accuracy.

## Experiment

Run on 25 September 2026 against the current working tree. The existing replay uses the five **hand-compiled fixture mandates**, the real pure decision function, the real regex reader, supplied card history, and a fresh in-memory ledger per scenario. Human confirmation requests remain waiting. It does not exercise the conversational assistant or claim that its drafts match the fixtures.

The added analysis runs 16 variants: full engine, no controls, money limits only, and each of 13 rule functions removed separately. Every sequential variant gets its own ledger. A second comparison removes each function while keeping the full engine's snapshot fixed, separating immediate rule contribution from downstream changes. The same fixed purchase sequence is used throughout; this is not a model of how a shopping agent might adapt to declines.

## Measured outcome

- Full engine: **12 approve, 22 decline, 11 step_up**. Approved authorization amount CHF 1,538.05; declined amount CHF 4,844.28; paused amount CHF 2,543.40.
- No controls: **45 approve**, CHF 8,925.73.
- Per-order and rolling-period limits only: **36 approve, 9 decline**, CHF 7,048.23 approved.
- Of the money-only control's 36 approvals, the full engine declines **15** and pauses **10**. Those are 25 concrete interventions beyond spending caps.
- This is not simply 24 added blocks: the full engine also approves AU0008, which the money-only control declines after consuming the budget on earlier purchases. Preventing an earlier purchase can preserve room for a later one.

These sums describe attempted authorizations across synthetic scenarios. **They are not money saved, losses avoided, settled payments, or independent customer outcomes.**

## Decisions with inspectable evidence

- AU0004: CHF 126 exceeds the CHF 120 order limit → decline.
- AU0009: CHF 300 already approved in the rolling window plus CHF 24 → decline. AU0011 later passes after old approvals leave the window.
- AU0013: customer requested size 43; merchant text says size 42 → decline. Its earlier-purchase warning alone would only pause it.
- AU0039: PixelHarbour is a different merchant identity from the previously used shop → decline, with lookalike-name evidence.
- AU0026: session-risk check is the deciding reason for a pause; removing it makes this purchase approve.

## Which checks make a difference?

With the existing full-run history held fixed, removing merchant familiarity changes 7 verdicts; purchase-count control 5; price 4; basket 4; returns 2; rolling budget, retailer category, duplicate/split detection, session, and size each change 1. These counts overlap and must not be summed.

Shop-text injection flags occur twice but change **zero final verdicts in the original sequence**: both are masked by other controls. In a controlled counterfactual where the same attempt arrives first, keeping historical familiarity:

- AU0040, CHF 299: with the injection check → step_up; without it → approve.
- AU0037, CHF 520: decline either way because it exceeds CHF 400.

This establishes an independent effect for the text check on one supplied payload. It is not an injection-detection recall benchmark. Fulfilment and unsupported-rule protection produce no adverse findings in this pack; zero contribution here is a coverage limitation, not grounds to delete either guard.

Reading merchant text also helps: the existing blind-reader benchmark produces 11 approve / 14 step_up / 20 decline, versus regex's 12 / 11 / 22. More decisive outcomes are observable; their correctness still requires independent labels.

## Where existing evaluation claims overreach

1. **No accuracy labels.** The pack deliberately has no expected decisions. Determinism and agreement with a frozen baseline establish consistency, not correctness or customer benefit. The 24.4% step-up rate is friction on this challenge pack, not an estimate for production traffic.
2. **No model comparison.** The worker instantiates `RegexReader`. Of the four registered benchmark approaches, only the reference itself has the strictness gate enabled. Therefore “zero safety breaches” in E-07 does not demonstrate an actual candidate model passing a gate. Separate synthetic property tests check model monotonicity.
3. **Mislabelled familiarity sensitivity.** E-06 describes testing “regularly = 3 earlier purchases,” but removes the entire prior-purchases field from every mandate, including the separate “used before = 1” rules. Its 7 affected verdicts measure removal of familiarity requirements, not sensitivity to the threshold of three.
4. **Coverage is weaker than the heading.** E-04 counts registry fields present in fixture mandates and separately lists observed check keys. “13/13 fields used” does not prove every failure branch was exercised; fulfilment produces no adverse findings here.
5. **Interpretation matters.** The once-only rule appears in 21 explanations and independently controls 5 verdicts. Confirming that interpretation with the customer is material to the outcome. This experiment assumes the fixture's permission is already confirmed.

## What we can responsibly say

“Leash changes authorization outcomes using customer constraints, transaction history, and merchant facts. In the 45-attempt simulation it stopped or paused 25 attempts that spending limits alone approved, while still allowing 12 purchases automatically.”

We cannot yet say “73% of fraud prevented,” “CHF 7,387.68 saved,” or “AI makes the checkout decisions.”

The next evaluation should use independently reviewed, held-out purchase sequences with explicit expected approve/decline/ask outcomes. Include ordinary shopping, each control acting alone, missing facts, unseen malicious text, and customer answers. Replay the actual customer-confirmed mandates, then report unsafe approvals and unnecessary declines/asks separately. That would measure whether the system makes the **right** decisions rather than only whether its controls activate.

## Reproduce and inspect

Validation completed: **1,126 passed**, zero failures or skips, in 74.89 seconds. Two warnings concerned a deprecated Starlette/AnyIO helper and JUnit `record_property` compatibility. Three deterministic replays agree; all 45 verdicts and reasons match the stored baseline. Initial sandboxed test attempts could not complete their local networking checks and were interrupted; the completed run used local networking and the isolated test-database fixtures.

The resilience simulation processed all 45 attempts with queue-to-accepted-decision latency of p50 **0.491 s**, p95 **1.118 s**, maximum **1.899 s**, against an 8-second deadline; no late decisions. It also exercised three refusals followed by successful resends. These are local synthetic test measurements, not production latency guarantees.

From `solution/engine`:

```sh
.venv/bin/python scripts/analyze_decisions.py > ../../output/decision-layer-analysis.json
.venv/bin/python -m evals.run --fast --json ../../output/decision-layer-eval-fast.json --markdown ../../output/decision-layer-eval-fast.md
.venv/bin/python -m pytest tests/domain tests/policy tests/property tests/application tests/contracts tests/replay tests/resilience tests/e2e/test_full_run.py -q --junitxml=../../output/decision-layer-validation.xml
```

The analysis includes assertions for parity with the existing replay, unique IDs, the allow-all control, and conservation of attempted amounts. The integration test uses a throwaway PostgreSQL database and a local in-process fake platform, including lost-response recovery, idempotency, and rechecking rules when a customer answers. It does not contact the hosted Viseca platform or move money.

Sources: `solution/engine/src/leash/domain/decide.py`, `application/replay.py`, `adapters/viseca_api/worker.py`, `evals/checks.py`, `evals/approaches.py`, `tests/fixtures/mandates.py`, `tests/e2e/test_full_run.py`; raw results in `output/decision-layer-analysis.json` and `output/decision-layer-eval-fast.json`. Existing user changes were left intact; production decision code was not changed.
