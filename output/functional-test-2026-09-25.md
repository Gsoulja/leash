# Leash functional test — 25 September 2026

Result: the intended customer journey is not yet passing end to end. Existing automated checks pass, but browser testing found blockers in clarification, correction and review.

## Scope and environment

- Browser: Codex in-app browser, http://localhost:8090/.
- Assistant container is configured for Apertus. Configuration alone does not prove that every response came from a successful model call.
- API and worker point to Viseca's hosted challenge API, not the available local fake container.
- Created test conversations and submitted one monitor draft for review: `draft_5a8099772f2b9eab`. It remains unconfirmed. No permission was activated, run started, or checkout approved during this browser test.
- Existing run `RUN-ee425e8525` and checkout `AZ-5d931132f09d` were inspected read-only; they were not created by this test.
- No application code was changed. The workspace already contains substantial uncommitted work; automated results apply to that working tree, while browser findings apply to the running deployment.

## Reproducible browser findings

### P1 — realistic product request cannot reach review

Send:

> Functional test: buy two 1-litre cartons of Oatly Barista oat milk from Alpine Basket. Spend at most CHF 20 total, including delivery and fees. No substitutions, no recurring purchases. Ask me if the exact product is unavailable. This is only a draft; do not activate permission until I review and confirm in the app.

Observed: the draft displays a CHF 20 limit, supermarket category and dairy-alternative category, each labelled “you asked for this.” Exact product, quantity and merchant restrictions are not represented in the displayed rules. Review is disabled with 13 required questions, so this did not become unsafe active authority.

Answer the first clarification:

> Only Oatly Barista oat milk, exactly two 1-litre cartons, from Alpine Basket. No other products or merchants.

Observed: the answer is rejected as unclear and repeats requests to explain the same wording. Expected: resolve against enforceable product/merchant identifiers, or ask a concrete question that lets the customer supply them. Broad category restrictions must not be presented as equivalent to exact restrictions.

### P1 — identical limit is treated as a conflict; correction does not replace it

Start a new conversation and send:

> At most CHF 20 per order, delivery included. Only supermarkets.

Observed: CHF 20 appears as a rule, but the same sentence is called unclear. Eight required questions block review.

Answer using the assistant's recommended syntax:

> At most CHF 20 per order

Observed: revision 2 reports that this conflicts with the instruction, says “a draft can only add to what you wrote,” and raises the question count to nine.

Then send in the main composer:

> Correction: replace the CHF 20 limit with CHF 30 per order. This is still an unconfirmed draft; I will review it again before confirming.

Observed: revision 3 still displays CHF 20; the conflict remains and 15 required questions block review. Expected: replace the unconfirmed rule, invalidate prior review and require fresh confirmation.

Relevant conflict wording: `solution/engine/src/leash/application/clarify.py:249`.

### P2 — review lacks the required structure and correction path

Send the existing baseline instruction:

> Buy the 27-inch monitor I chose, from a seller I have bought from before, for CHF 400 or less. Do not add anything I did not ask for. Ask me when uncertain.

Answer “Any kind of shop,” then “Yes, ask me” for the split-order question. Click “Review what Viseca will receive.”

Observed: this path succeeds. Review shows the exact seven hard rules, uncertainty policy, explanatory guidance and a separate confirmation button. It explicitly says the permission is inactive.

However, there are no “Must follow / May choose / Must ask” groups. The composer disappears after submission; there is no edit action, only starting a new conversation. Expected: review derived from the enforceable rules, with a correction path that produces a new revision and fresh review before confirmation.

Relevant UI: `solution/app/src/screens/Agent.tsx:320` (review), `solution/app/src/screens/Agent.tsx:359` (composer hidden after submission).

### Wording concern — aggregate spending versus approval

The existing checkout is labelled “Approved,” and payment details explicitly say the bank accepted the decision. Engine approval and final approval are displayed separately; merchant text is labelled untrusted, and individual checks include values and evidence. These are useful distinctions.

The aggregate heading says “Agent spent.” Consider labelling this as approved/authorized value unless settlement evidence is available. This test did not observe a newly pending platform response in the browser, so it does not establish that the deployed UI misreports that state.

## Coverage against the intended flow

1. **Chat and assistant authority:** browser verified drafting, clarification and inactive state; automated assistant checks cover absence of confirmation/decision tools. Natural-language handling is blocked for the grocery examples above.
2. **Background is context, not authority:** automated permission-context and assistant checks passed, including preference provenance and scoped background. No personalized preference suggestion was exercised in the browser.
3. **Proposed-rule validation:** automated compiler/assistant checks passed. Browser blocked unresolved wording safely, but did not provide a usable clarification path and showed overly broad proposed categories.
4. **Review and confirmation:** browser reached an inactive exact-rule review for the monitor fixture. Required grouping and correction path are missing. Confirmation and stale-revision enforcement were tested against the fake platform, not by activating the browser draft.
5. **External shopping-agent handoff:** not demonstrated in the browser. Existing fake-run tests exercise confirmed mandate snapshots; that is not proof of a task-and-permission-reference handoff to an external shopping agent.
6. **Checkout enforcement:** isolated fake-platform, domain, replay and property tests passed for deterministic rules, history, uncertainty and untrusted text. No new checkout was sent through the deployed hosted configuration.
7. **Evidence and outcomes:** browser verified existing checkout checks, merchant text, outgoing decision and bank-acceptance wording. Isolated lifecycle/outbox tests passed. Full conversation-to-confirmed-version-to-checkout lineage was not newly exercised through the deployed browser flow.

## Automated verification

Frontend: **134 passed** across 13 files.

```sh
cd solution/app
npm test -- --reporter=dot
```

Backend/assistant: **1,168 passed**, two warnings, 78.33 seconds. Tests used temporary databases and an in-process fake platform.

```sh
cd solution/engine
.venv/bin/python -m pytest -q -o faulthandler_timeout=45 \
  tests/policy tests/application tests/replay tests/property tests/domain \
  tests/adapters/test_worker.py tests/adapters/test_assistant_proxy.py \
  tests/adapters/test_policy_api.py tests/adapters/test_outbox_sender.py \
  tests/e2e/test_full_run.py ../assistant/tests --tb=short
```

An initial sandboxed backend run stalled and showed two failures before interruption. The complete rerun with local database access passed; the initial partial result is not a confirmed product regression.

Warnings: Starlette/AnyIO deprecation and an unawaited test coroutine in an outbox test. Frontend tests also emitted undefined-query-data and overlapping-act warnings despite passing.

Passing existing tests does not close the browser acceptance gaps above. The next checks should reproduce those exact inputs and assert usable clarification, replacement of unconfirmed rules, and editable grouped review.
