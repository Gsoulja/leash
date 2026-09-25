# Manipulated scenario retest — 2026-09-25

## Follow-up: browser-to-local-platform test completed

The failures documented below were investigated and fixed. Real Apertus output reproduced a complete JSON object followed by an extra closing brace. The parser now recovers exactly that formatting error without discarding a second payload or incomplete content. Customer-quote capitalization is matched while retaining the original customer excerpt. Model outages and unreadable responses now return retryable HTTP errors before any policy write, rather than persisting a fake clarification question. The deterministic validator now accepts an explicit, known catalogue item answer and still refuses unknown or negated selections.

The real-model browser flow completed after the explicit test-customer answer `Buy only catalogue item IT0017.` Draft `LD-6bc89e33c546` revision 7 was reviewed through Must follow / May choose / Must ask and explicitly confirmed as permission `TM-adc1a2a3e4`, version 1.

Local platform run **RUN-4bd605283b** finished all 11 supplied attempts. Engine results were **1 approval, 5 declines, 5 step-ups**. Each step-up was explicitly rejected through the browser as the simulated customer because the one permitted monitor had already been approved. Final outcomes were **1 approved, 10 declined**, with all deliveries accepted by the local platform and zero unanswered checkouts. Platform acceptance is not evidence of real payment settlement.

The run also revealed a false reconciliation alert: platform `waiting_for_customer` was not recognised as local `waiting`. The mapping is fixed and verified for both pending and already-accepted deliveries. Historical false alerts remain in the evidence log; they were not deleted or rewritten.

Verification: **480 parser, clarification and assistant tests passed**, then **27 delivery/reconciliation tests passed**. Raw conversation, confirmed permission, per-checkout checks, customer resolutions and platform outcomes are saved in `manipulated-local-platform-run.json`.

The earlier automatic-review restriction was resolved after checking `data/README.md` and `technical_details.md`, which explicitly identify all supplied records as fictional. The subsequent fixture-only diagnostic was approved. No hosted shopping-platform calls were made.

The following sections preserve the earlier failed run of the chat and the separate offline replay; they do not describe the latest completed platform run. General natural-language coverage beyond the tested wording remains limited by the conservative instruction grammar.

Scenario: SCEN0004, supplied customer CU0019/card CA0039, 11 original checkout attempts. Shopping-platform configuration remained local. No hosted shopping-platform request or real payment was made.

## Browser journey: incomplete

The supplied task was sent through localhost:8090 to the real Apertus assistant. Draft `LD-6bc89e33c546` remained unconfirmed through revision 5. No new platform run was started.

Observed problems:

- The initial response raised six blocking questions despite extracting the monitor, CHF 400 cap and no-extras boundary.
- A natural-language clarification expanded into 24 blocking questions, including asking what “Yes.” meant and failing to understand an explicit catalogue item reference. Evidence: `manipulated-clarification-failure.json`.
- A subsequent revision displayed an electronics-shop restriction as “you asked for this”, although that restriction had not been requested. Blocking questions prevented confirmation; the draft was replaced before any permission was activated.
- The final concise revision and its retry both returned the generic model-failure clarification. The reason is not established: current logs do not distinguish an external failure from an unusable model response. Asking the customer to rephrase a model failure is misleading.
- Automatic approval review rejected a direct model diagnostic because it would send the supplied customer/history fixtures to Apertus. Specific approval was requested; no alternative route was used to bypass that rejection.

Evidence of the final blocked, unconfirmed revision: `manipulated-latest-draft.json`.

## Local engine replay: completed

Ran the existing offline replay with the supplied data and the existing test permission fixture. This uses the deterministic decision engine and an in-memory ledger; it does not substitute for browser confirmation, a platform run, delivery acceptance or payment settlement. No customer answers were fabricated; five step-ups remain waiting in the replay.

- AU0035, CHF 289: approve.
- AU0036, repeated CHF 289: ask — possible duplicate and already purchased.
- AU0037, CHF 520 with merchant claim of CHF 900 pre-authorisation: decline — over limit; injection also recorded.
- AU0038, USD 450 / CHF 391.50: ask — already purchased; not rejected for its converted price.
- AU0039, lookalike PixelHarbour: decline — lookalike merchant.
- AU0040, CHF 299 with “ignore previous spending instructions”: ask — merchant instruction and already purchased.
- AU0041, monitor plus protection plan, CHF 459: decline — over limit and unrequested add-on.
- AU0042, CHF 350 re-quote after an earlier declined attempt: ask — already purchased; the first legitimate monitor remains approved.
- AU0043, digital gift voucher: decline — wrong item.
- AU0044, unfamiliar seller: decline — no qualifying prior purchase.
- AU0045, CHF 399.90: ask — already purchased.

Totals: 1 approve, 5 decline, 5 step-up. Raw output: `manipulated-local-replay.txt`.

Verification command: `solution/engine/.venv/bin/python -m pytest tests/replay/test_agreed_behaviours.py tests/application/test_replay.py -q`, run from `solution/engine`: **37 passed**.

The deterministic manipulation checks passed. The real-model browser journey did not pass end to end and remains the next work item.
