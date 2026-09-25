# Product notes

The agreement below is the current product direction as of 2026-09-24. It is planned behavior, not an implementation-completion claim. The research and TaskCard sections that follow are hypotheses and historical research notes; they do not expand the agreed scope or establish competitor exclusivity, universal intent verification, or production readiness.

## Current agreement — permission control for external shopping agents

Leash owns permission clarification, customer confirmation, checkout validation and evidence. An external shopping agent owns product search and order preparation. Viseca's simulator represents that agent in the challenge. Leash's permission assistant cannot activate authority, purchase, or approve a payment.

### Customer journey and authority

1. The customer describes the task in Leash's permission chat.
2. The LLM proposes supported conditions and asks about missing information. Relevant profile preferences and earlier transaction history help choose questions; they do not grant authority.
3. Check both directions: every proposed rule must have support, and every material restriction in the conversation must be represented or explicitly unresolved. Exact amounts, currency, quantities and IDs are source-backed and code-validated. A valid schema does not prove the interpretation is right.
4. Present the exact permission as **Must follow / May choose / Must ask**, generated from the enforced structured rules. Show which conditions came from explicit answers, which are suggestions, and which requirements cannot be verified. Unresolved material authority blocks confirmation.
5. The customer confirms a specific draft revision. Corrections to an unconfirmed draft create a new revision and invalidate old review actions; a submitted platform draft is replaced by a new draft, not mutated. Active mandates retain the existing tighten-only contract. A broader task requires a separate permission and fresh confirmation.
6. Hand the external agent the task, constraints and permission reference. Leash/platform retain authoritative rules. The existing Viseca run snapshot and checkout event bind the challenge flow; production identity and credential mechanisms remain open.
7. Receive the actual checkout through the platform and apply deterministic rules plus relevant state: approve, decline or ask. A merchant statement is a claim, not verified product quality or delivery. Missing required evidence is never silently represented as a successful check; the confirmed uncertainty policy and existing integrity safeguards apply.
8. Retain the chain from conversation/context, proposed rules and consent to run, checkout, decision and platform outcome. Distinguish a local decision, pending submission, platform acceptance and refusal. Acceptance is not proof of settlement or fulfillment.

### Customer background and history

Use a small task-relevant context bundle: customer/account/card scope, source records, date or unknown freshness, recorded preferences, observed history, current statements/corrections and separately scoped prior permissions. Treat retrieved text as data, not model instructions. Keep unrelated personal details out of model inputs and ordinary logs.

Example: a recorded 30-day clothing-return preference can prompt “Should that be required for this jacket?” Only the explicit answer followed by final confirmation establishes that restriction. Current instructions can differ from old preferences. “Careful budget” never creates a numeric spending limit; “the one I chose” still needs an actual product reference.

The additional pack contains 500 separate personas and 144,674 historical transactions. Its customer IDs do not overlap the base scenarios. Join by IDs and never attach one population's history to the other. Use earlier transactions only for time-specific evaluation. Historical status is an authorization outcome, not a fraud, intent or correct-purchase label. History lacks item-level baskets, so it cannot establish an exact previously purchased product. Additional conversations and checkouts constructed for evaluation must be labelled synthetic and reviewed.

### Jev: separate verification tasks

The existing LEASH-073–082 pipeline concerns **merchant text at checkout**. The proposed second use checks **conversation/context against candidate permissions**, with supported / contradicted / not stated / ambiguous results and a separate omission check. These need separate datasets, question sets, metrics and release evidence.

Start with reviewed examples and a baseline; fine-tune only when measured failures justify it. Keep persona and intent/template families separate across training, calibration and evaluation. Measure false support, omissions, useful and unnecessary questions, abstention and latency, including conflicting context, corrections, injection and missing references. Model agreement or a confidence score is not proof. Use shadow mode first; Jev cannot confirm, widen authority or decide payments. Missing or truncated evidence must remain inconclusive.

### Delivery and task ownership

- LEASH-154: scoped customer context and provenance.
- LEASH-101: permission chat, evidenced proposals and revision-safe draft/confirmation APIs.
- LEASH-145 and LEASH-146: conversation and exact human-readable review.
- LEASH-102 and LEASH-147: external-agent handoff through the existing simulator contract.
- LEASH-130, LEASH-148 and LEASH-150: platform outcome reconciliation and truthful presentation.
- LEASH-156: reviewed permission corpus, baseline metrics and complete-journey acceptance evidence.
- LEASH-155: Jev permission-verifier evaluation and conditional fine-tuning, independent of the baseline release.
- LEASH-140 and LEASH-143: authenticated customer consent and production identity/payment-path enforcement.
- LEASH-175: the assistant's own HTTP surface, without which steps 2–5 have no path from the chat to the model.
- LEASH-174: the DEC-045 authoring path — the model reads, the registry validates, a renderer writes the sentence the customer approves. Its two compensating controls are required, not optional: the unrestricted-fields list (LEASH-146) and omission checking (LEASH-155).
- LEASH-160–173: the trust filter for untrusted shop and agent text: Jev now scans merchant name, city, item name, item details and purchase description, including a canonical Unicode view.

**Build state, 2026-09-25.** The scoped context, assistant HTTP surface, model-authored validated proposals, unrestricted-fields review, correction/revision lifecycle, simulator handoff and platform-outcome views are implemented. Submit and confirm now require the exact reviewed revision at the backend. The Agent chat shows live checkout activity and completion using the existing read model, including pending and conflicting platform outcomes, and resumes its run on reload. The hosted start path consumes `fixture_profiles` rather than assuming hosted cards exist in the local pack.

Jev now independently classifies candidate support in four categories and scans the whole customer conversation for omitted restrictions, including requirements outside the registry and empty candidate lists. Permission verification remains **shadow**, with an explicit enforcement mode, until reviewed calibration supports release; this is not a proven omission-prevention guarantee. The shop reader uses Jev in one bounded batch without a regex fallback. Off-platform payment requests and uncertain safety answers require attention or decline. Model-derived size/return facts cannot erase the structured-only uncertainty findings. Recurring-charge text is checked when the permission forbids extras or subscriptions. Catalogue price ranges use exact item IDs and Decimal FX; missing references remain unknown, and a price anomaly is not proof of fraud. Unicode lookalike handling covers common characters, not every script.

The hosted connection check and limitations are recorded in [live journey validation](live-journey-validation.md). This is live integration evidence plus synthetic diagnostics, not human-reviewed corpus acceptance. LEASH-156's independent human review, frozen held-out splits and calibrated release thresholds remain open. A new task draft can still encounter the assistant's existing active-mandate tightening guard; broader fresh permissions need a separately reviewed scope decision rather than silently dropping that guard.

Reuse the existing policy service, registry, confirmation lifecycle, run/checkout engine and evidence views. Optional catalogue lookup resolves references; Leash does not need its own shopping executor or a new generic agent framework. First deliver one complete permission-to-checkout journey.

### Open decisions and claims

The current adapters use OpenRouter `google/gemini-3.8-flash` for permission proposals and `typesafe/jev-1.13` for shop facts and permission verification. Apertus and deterministic/regex implementations remain explicit comparison baselines. A model version or confidence score is not a security proof. Verifier release thresholds, human-reviewed evaluation, production authentication, agent identity and credential/handoff enforcement remain open. New TaskCard signing, delegation, cross-protocol support and settlement handling are future hypotheses. Prototype login remains excluded under DEC-019; production consent must be authenticated.

The product claim is: **Leash enforces customer-confirmed permissions against available checkout evidence and exposes uncertainty.** It does not guarantee knowledge of unstated intent, merchant honesty or delivery, and the research below does not prove that Leash is the first or only product with these capabilities.

See [the decision log](decisions.md), [designer brief](customer-journey-for-design.md) and [ticket coverage](../kanban/README.md#current-permission-control-plan).

## Leash TaskCard — purpose-bound payment authority for AI agents

**Status:** Product hypothesis. Useful primitive, but not unique by itself.

### Thesis

The AI shopping agent should never receive the customer's general card authority. Viseca instead mints a disposable, signed payment capability for one confirmed task.

Cards identify which account pays. A TaskCard additionally constrains:

- which agent may use it;
- the permitted purpose, item and quantity;
- maximum per-payment and total liability;
- allowed merchants or merchant properties;
- expiry and remaining uses;
- whether uncertainty must be declined or escalated.

Example:

```text
TaskCard
Purpose: One 27-inch monitor
Maximum liability: CHF 400
Quantity: 1
Merchants: Previously used electronics retailers
Add-ons: Forbidden
Expires: 20 minutes
Uses remaining: 1
```

### Attenuating delegation

An agent may delegate a TaskCard to another agent only by narrowing it. A child capability can lower the amount, reduce the merchant set, shorten the expiry or reduce remaining uses. It can never restore or expand authority.

```text
Customer TaskCard: CHF 400 at known electronics merchants
Shopping sub-agent: CHF 350 at PixelHarbor only
```

The deterministic control layer—not the LLM—verifies this monotonic relationship and decides every authorization.

### Lifecycle

1. The customer describes a shopping task.
2. The Leash permission assistant proposes candidate rules as an untrusted draft.
3. The policy service validates the rules and shows the exact authority to the customer.
4. The customer confirms.
5. Viseca signs/mints the TaskCard.
6. The agent presents the TaskCard with each proposed payment.
7. The deterministic engine evaluates the payment and capability state.
8. Successful use consumes the permitted amount/use; completion, expiry or revocation leaves no remaining authority.

### Demo moment

1. Confirm a TaskCard for one monitor up to CHF 400.
2. Show a shopping-agent delegation that narrows the authority to CHF 350 and one merchant.
3. Submit a merchant-injected CHF 79 warranty; it is blocked because the capability contains no add-on authority.
4. Complete the valid monitor purchase.
5. Show `Consumed — authority remaining: CHF 0`.
6. Replay the charge and show that the exhausted capability cannot be reused.

### Why it matters to Viseca

This reframes Leash from a rules UI into an issuer-native credential for agentic commerce:

> Cards were created for people. Tokens were created for devices. TaskCards are payment credentials created for AI agents.

The product promise is not that an agent will obey a prompt. It is that the agent receives only the smallest verifiable fragment of payment authority needed for one task.

Research note: constrained, signed payment mandates are already emerging in AP2, ACP, Mastercard Agent Pay and EMVCo's proposed agentic-payment framework. TaskCard should therefore be presented as Leash's protocol-neutral representation of delegated authority—not as the entire competitive moat. The stronger differentiator is the runtime control described below.

### Non-negotiable boundary

- The LLM may converse and propose draft rules only.
- The LLM never mints, signs, confirms, expands or evaluates a TaskCard.
- Merchant and tool content remains untrusted data.
- The deterministic policy and authorization layers remain authoritative.
- No TaskCard may bypass the wallet-control contract supplied by Viseca.

### Open questions

- Whether the prototype represents the capability as a signed token, a mandate-bound opaque ID, or both.
- Which party signs and verifies it in a production Viseca architecture.
- How agent identity or workload attestation is bound to the capability.
- How partial consumption, refunds, reversals and expired customer step-ups affect remaining authority.
- Whether sub-agent delegation is required for the hackathon demo or retained as the product vision.
- Which TaskCard claims map directly to the supplied mandate contract and which require a future protocol extension.

## Research — agentic payments and the control-layer opportunity

**Research date:** 24 September 2026

**Status:** Strategic research for later work; not an implementation commitment.

### Executive conclusion

The market is converging on ways to identify AI agents and carry signed customer intent. That solves an important part of the problem, but it does not prove that the transaction presented later still means what the customer originally authorized.

Leash should position itself as an **Intent Runtime Firewall** for agentic payments:

> Cryptography can bind a signer to a mandate. Leash checks the checkout against customer-confirmed permission and exposes missing evidence.

Leash would sit between an AI shopping workflow and payment execution. It would accept intent from multiple emerging protocols, normalize it into one enforceable policy, and verify semantic and state consistency at every consequential step. The LLM remains outside the control plane.

This is more defensible than claiming that a signed mandate or limited-use token is novel. It also aligns naturally with Viseca's role: turn customer intent into enforceable issuer-side payment authority and evidence.

### What the ecosystem already provides

#### Google Agent Payments Protocol (AP2)

[AP2](https://github.com/google-agentic-commerce/AP2/blob/main/docs/ap2/specification.md) defines a cryptographically verifiable mandate chain for agent-led commerce. Its design includes:

- a non-agentic trusted surface for sensitive customer confirmation;
- signed intent, checkout and payment mandates;
- human-present and autonomous, human-not-present flows;
- binding autonomous authority to an agent public key;
- deterministic verification rather than trusting model behavior;
- short expiry recommendations and transaction receipts for evidence.

AP2 demonstrates that signed, purpose-scoped mandates are becoming a shared protocol primitive. It discusses the possibility of agent-to-agent delegation, but delegation semantics and enforcement are outside the current core specification. Leash's attenuating TaskCard concept remains useful here, especially if it can prove that delegated authority only narrows.

#### Visa Trusted Agent Protocol

[Visa Trusted Agent Protocol](https://developer.visa.com/capabilities/trusted-agent-protocol) focuses on helping merchants recognize legitimate commerce agents. It uses cryptographic agent identity, signed requests, purpose and timing context, and replay protections.

Its center of gravity is trusted-agent recognition at the merchant boundary. Leash's opportunity is complementary: enforce the customer's exact authority and track its state across the complete transaction lifecycle, not merely establish that a known agent made the request.

#### Agentic Commerce Protocol (ACP)

[ACP architecture documentation](https://www.agenticcommerce.dev/docs/concepts/architecture) and the [open-source ACP specification](https://github.com/agentic-commerce-protocol/agentic-commerce-protocol) define interactions among an agent, seller and payment service provider. ACP supports delegated payment credentials with restrictions such as amount, currency, expiry and merchant, enforced by the payment provider.

ACP helps agents and merchants complete checkout without exposing a general-purpose payment credential. Leash should integrate with this type of orchestration rather than compete with its message format.

#### Mastercard Agent Pay

[Mastercard Agent Pay](https://www.mastercard.com/us/en/business/artificial-intelligence/mastercard-agent-pay.html) introduces registered agents, agentic payment tokens and customer-consent mechanisms. Mastercard describes **Verifiable Intent** as a way to connect customer identity and instructions to the resulting transaction, alongside tokenization and passkey-based confirmation. See also Mastercard's [launch announcement](https://newsroom.mastercard.com/news/press/2025/april/mastercard-unveils-agent-pay-pioneering-agentic-payments-technology-to-power-commerce-in-the-age-of-ai/) and [agentic-commerce vision](https://www.mastercard.com/us/en/news-and-trends/stories/2026/mastercard-agentic-commerce-vision.html).

This is direct evidence that tokenized agent authority and signed intent are becoming network capabilities. Leash needs to differentiate through independent, continuous enforcement of that intent—not by renaming the token.

#### EMVCo agentic-payment framework

[EMVCo's draft framework](https://www.emvco.com/news/emvco-requests-feedback-on-framework-for-secure-interoperable-and-scalable-card-based-agentic-payments/) proposes **Intent Services** that can register, reference, retrieve and manage consumer intent across the payment lifecycle. It anticipates integration with existing EMV technologies such as 3-D Secure, payment tokenization, Secure Remote Commerce and dynamic passcodes, as well as agent identification and agentic-transaction indicators.

This was published for consultation and must be treated as an emerging framework, not a final standard. Its direction reinforces the need for a protocol-neutral enforcement layer that can consume intent references and bind them to actual execution.

#### FIDO Alliance

The [FIDO Alliance agentic-AI initiative](https://fidoalliance.org/fido-alliance-agentic-ai/) is exploring standards for secure agent identity, delegation and verifiable authorization. Its work suggests that passkeys and phishing-resistant user confirmation may become the trusted approval mechanism around autonomous actions.

Leash should use such mechanisms for step-up and consent proof where available rather than invent a weaker authentication ceremony.

#### OAuth Rich Authorization Requests

[RFC 9396](https://datatracker.ietf.org/doc/rfc9396/) defines `authorization_details`, a structured way to request fine-grained authorization. The RFC includes payment examples with amount, currency and creditor/payee information.

RAR can carry granular authority, but the authorization server still defines and enforces the semantics. It is a useful transport and interoperability building block, not a complete payment-intent control layer.

#### Macaroons and attenuating capabilities

The foundational [Macaroons paper](https://research.google/pubs/macaroons-cookies-with-contextual-caveats-for-decentralized-authorization-in-the-cloud/) describes delegated capabilities that can be restricted with contextual caveats. A delegate can add restrictions but cannot remove earlier ones.

This is the conceptual foundation for TaskCard attenuation: a shopping agent may delegate less authority to a specialist sub-agent, never more. The production design still needs precise payment semantics, issuer controls, revocation, atomic consumption and audit evidence.

### What recent research says is still missing

The following sources are research preprints, not settled standards or independently validated production claims. They are valuable for threat modeling and design direction.

#### Cross-stage formal consistency

[A formal analysis of x402, MPP, ACP and AP2](https://arxiv.org/abs/2609.00060) models authorization and economic/service effects across protocol actors and stages. It reports 86 verification cases and 40 undocumented formal-consistency findings.

The practical lesson for Leash is that verifying a valid object at one step is insufficient. Customer intent, merchant checkout, payment authorization, service delivery and final ledger effects must remain mutually consistent.

#### Valid signatures do not guarantee valid intent

[Beyond the Mandate](https://arxiv.org/abs/2608.23858) analyzes threats to agentic-payment protocols, including manipulation of the context *before* a customer signs. Compromised merchant data, tool responses, A2A messages or MCP content can shape a formally valid mandate that does not reflect the customer's real goal.

The lesson is critical: merchant and tool content must always be treated as untrusted. Leash must compare the final purchase semantics to the customer's independently captured goal, not merely verify the signature on a downstream mandate.

#### Stateful, consume-once enforcement

[Research on zero-trust runtime verification](https://arxiv.org/abs/2602.06345) proposes context binding and consume-once semantics for autonomous payments. Its simulation reports approximately 3.8 ms verification latency at up to 10,000 transactions per second; this is an author-reported result, not a Leash performance claim.

The design implication is to make replay prevention, atomic consumption, remaining authority and transaction-context binding first-class control-layer responsibilities.

#### Layered defense

[A systematization of knowledge on agentic payments](https://arxiv.org/abs/2604.15367) organizes risks across agent integrity, transaction authorization, inter-agent trust, market manipulation and regulation. Its broader lesson is that no single token, signature or model guardrail solves the problem.

Leash should combine trusted consent, constrained credentials, deterministic policy, stateful runtime checks, step-up controls and durable evidence.

### The product gap Leash can own

The promising gap is **runtime cross-stage semantic consistency**.

A mandate may be cryptographically valid while the commercial meaning has drifted. Examples include:

- a merchant or tool silently adding a warranty, subscription or donation;
- a product substitution that remains under the amount limit but violates the requested purpose;
- splitting one prohibited purchase into several individually permitted charges;
- replaying a valid authorization or racing simultaneous uses;
- changing merchant, quantity, delivery terms or recurring-payment status after confirmation;
- completing the payment while the promised service or item differs from the authorized checkout;
- obtaining a new step-up approval without showing the material differences from the earlier intent.

Leash should detect these inconsistencies even when identity, token and signature checks all pass.

### Proposed control-layer architecture

1. **Trusted consent surface:** Capture the customer's actual goal and confirmation outside the autonomous LLM. Show the material authority in human language.

2. **Versioned intent and mandate store:** Preserve immutable versions of customer intent, proposed rules, confirmed authority and later changes. Every decision references an exact version.

3. **Agent identity binding:** Bind authority to an approved agent identity, public key or attested workload where supported. Identity is necessary but does not replace policy evaluation.

4. **Scoped credential provider:** Issue or reference a short-lived, least-authority payment credential. Support AP2 mandates, ACP delegated instruments, network agentic tokens or an opaque Viseca capability without making the policy engine protocol-specific.

5. **Checkout binding and normalization:** Convert the customer intent, merchant cart, credential restrictions and payment request into a canonical internal model. Bind price, currency, merchant, line items, quantity, recurrence, delivery conditions and material add-ons.

6. **Deterministic runtime policy engine:** Evaluate semantic purpose, explicit constraints, merchant properties, uncertainty policy and delegation attenuation. The LLM may propose inputs but never decides the outcome.

7. **Stateful consumption ledger:** Atomically track remaining amount, remaining uses, rolling totals, reservations, captures, reversals and refunds. Prevent replay, duplicate execution, split-charge evasion and concurrent overspend.

8. **Customer step-up:** Escalate material or uncertain changes through a trusted surface using passkeys, 3-D Secure or issuer-app approval where appropriate. Present the exact difference and mint a new authority version; never silently broaden the old one.

9. **Outcome binding and consistency receipt:** Reconcile authorization, capture and final platform outcome with the original intent. Produce a signed, human-readable and machine-verifiable receipt showing what was requested, what changed, which rules fired, what was approved and what authority remains.

### Protocol-neutral flow

```text
Customer goal
    -> trusted confirmation
    -> AP2 / ACP / Agentic Token / EMVCo intent reference
    -> Leash normalization
    -> deterministic semantic + state checks
    -> allow | decline | step-up
    -> atomic authority consumption
    -> settlement/outcome reconciliation
    -> cross-stage consistency receipt
```

The model assists before the decision; the control layer owns the decision:

```text
LLM: converse, search, explain, propose candidate rules
Control plane: validate, version, sign, evaluate, consume, revoke, reconcile, prove
```

### Strong hackathon demonstration

The demo should not merely show that a limit blocks an excessive amount. Every team can implement that.

Instead, present a valid signed mandate and a valid agent token for one monitor. Then allow a merchant/tool response to alter the checkout context—for example, substitute a subscription bundle or add a warranty while keeping the charge within the CHF 400 limit.

1. The identity and cryptographic layer reports **valid**.
2. Leash compares customer goal, mandate, checkout and proposed payment.
3. Leash identifies the semantic drift and blocks or steps up the transaction.
4. The UI pinpoints the exact mismatch in plain language.
5. A valid purchase succeeds and atomically consumes the capability.
6. A replay or split-payment attempt fails.
7. The proposed receipt records the evidence and checks from confirmed permission through the reported platform outcome; it cannot prove unstated intent or fulfillment.

The pivotal line for the jury:

> A signed instruction can still be the wrong purchase. Leash is the runtime firewall that keeps every payment faithful to customer intent.

### Product positioning

Avoid these claims:

- "We are the first signed token for AI payments."
- "The LLM safely decides whether to pay."
- "A valid mandate proves the purchase is safe."
- "Amount and merchant limits alone solve agentic-payment risk."

Prefer these claims:

- Leash complements AP2, ACP, Agentic Tokens and future EMVCo Intent Services.
- Leash verifies that intent remains semantically and economically consistent across every stage.
- Leash combines deterministic policy with atomic, stateful authority consumption.
- The AI is useful but untrusted; it cannot bypass or mutate the control plane.
- Viseca can make agentic payments provable, governable and disputable at issuer grade.

### Future work

- Define the canonical intent schema and mappings for AP2, ACP, network tokens and EMVCo intent references.
- Specify semantic comparison rules for products, substitutions, add-ons, recurrence and delivery terms.
- Model reservations, partial captures, tips, FX changes, refunds, reversals and chargebacks.
- Define atomic consume-once behavior under retries and concurrent agent activity.
- Design an attenuating delegation proof for sub-agents.
- Define the step-up threshold and the trusted human confirmation experience.
- Design the cross-stage consistency receipt and dispute-evidence format.
- Threat-model merchant, browser, A2A, MCP and tool-output manipulation before mandate creation.
- Decide which controls belong at Viseca issuer authorization, which require merchant/PSP integration, and which can run in the Leash orchestration layer.
- Validate the proposed positioning with Viseca payment, risk, legal and architecture experts before making production claims.

### Source index

**Industry specifications and initiatives**

- [Google Agent Payments Protocol specification](https://github.com/google-agentic-commerce/AP2/blob/main/docs/ap2/specification.md)
- [Visa Trusted Agent Protocol](https://developer.visa.com/capabilities/trusted-agent-protocol)
- [Agentic Commerce Protocol architecture](https://www.agenticcommerce.dev/docs/concepts/architecture)
- [Agentic Commerce Protocol repository](https://github.com/agentic-commerce-protocol/agentic-commerce-protocol)
- [Mastercard Agent Pay](https://www.mastercard.com/us/en/business/artificial-intelligence/mastercard-agent-pay.html)
- [Mastercard Agent Pay launch announcement](https://newsroom.mastercard.com/news/press/2025/april/mastercard-unveils-agent-pay-pioneering-agentic-payments-technology-to-power-commerce-in-the-age-of-ai/)
- [Mastercard agentic-commerce vision](https://www.mastercard.com/us/en/news-and-trends/stories/2026/mastercard-agentic-commerce-vision.html)
- [EMVCo agentic-payment framework consultation](https://www.emvco.com/news/emvco-requests-feedback-on-framework-for-secure-interoperable-and-scalable-card-based-agentic-payments/)
- [FIDO Alliance agentic-AI initiative](https://fidoalliance.org/fido-alliance-agentic-ai/)
- [OAuth 2.0 Rich Authorization Requests — RFC 9396](https://datatracker.ietf.org/doc/rfc9396/)

**Research**

- [Macaroons: Cookies with Contextual Caveats for Decentralized Authorization in the Cloud](https://research.google/pubs/macaroons-cookies-with-contextual-caveats-for-decentralized-authorization-in-the-cloud/)
- [Formal analysis of x402, MPP, ACP and AP2](https://arxiv.org/abs/2609.00060)
- [Beyond the Mandate](https://arxiv.org/abs/2608.23858)
- [Zero-trust runtime verification for autonomous payments](https://arxiv.org/abs/2602.06345)
- [Systematization of knowledge on agentic payments](https://arxiv.org/abs/2604.15367)

## Research round 2 — what the industry shipped, and what is still unclaimed

**Research date:** 24 September 2026

**Status:** Strategic research. All claims are sourced to public material as of this date; network rules, drafts and startup positioning move fast and must be re-verified before any external presentation.

### What this round looked for

Round 1 read the protocol specifications. This round looked for three things the specs do not show: what is actually **shipped and live**, what **Switzerland and Viseca specifically** are already doing, and whether anyone has already **published or productised** the "runtime semantic consistency" claim that round 1 proposed as Leash's moat.

Three findings change the pitch:

1. **Viseca is not a prospect for agentic rails — it is already on them.** The demo should assume live rails and attack the control gap on top of them.
2. **The runtime-consistency gap now has published prior art, a formal name and a taxonomy.** Good news for credibility, bad news for novelty claims. Use the taxonomy; drop the "nobody has thought of this" framing.
3. **The genuinely unclaimed ground is evidence and dispute, not enforcement.** Enforcement is being built by the networks. Provable, disputable evidence is not, and it is issuer-shaped work.

### Finding 1 — Viseca already runs live agentic rails

- In **May 2026 Mastercard executed the first authenticated agentic commerce transaction in Switzerland together with Cembra, Cornèrcard and Viseca**: an AI agent selected a purchase for a customer and completed booking and payment ([FintechNews CH](https://fintechnews.ch/payments/visa-ai-agent-payments-europe/84486/), [Eco summary](https://eco.com/support/en/articles/15192001-what-is-mastercard-agent-pay-ai-agent-commerce-protocol-in-2026)).
- At the **Visa Payments Forum in Paris (2 July 2026)** Visa took live agentic payments to **30+ European issuers including Cornèrcard, Swisscard and Viseca**, on real merchant websites rather than controlled storefronts ([Visa UK newsroom](https://www.visa.co.uk/about-visa/newsroom/press-releases.3457328.html), [The Industry Spread](https://theindustryspread.com/visa-agentic-payments-live-30-european-issuers/)).
- Visa's **Intelligent Commerce Connect** (April 2026) gives agent platforms one integration point for onboarding, verification and token issuance across agent protocols ([The Paypers](https://thepaypers.com/payments/news/visa-launches-intelligent-commerce-connect-for-agentic-payments), [Visa Developer](https://developer.visa.com/capabilities/visa-intelligent-commerce)). European issuer participation runs through **Visa Payment Passkeys** for SCA-compliant confirmation.

**Implication for Leash.** Do not pitch "agentic payments are coming." Pitch: *Viseca already authorises agent-initiated transactions; today the customer's actual intent is not a first-class object in that authorisation, and nothing proves afterwards that the purchase matched it.* That is a control-layer gap on a live rail, which is a far stronger hackathon framing than a future-market bet.

**Caution.** Visa states that the platform "will validate that requests match the authenticated user instruction," and Mastercard's stack "validates the policy signals before releasing approval," with Decision Intelligence scoring agent identity, session provenance and consent freshness ([Goodwin, *Authorizing Agentic Payments*](https://www.goodwinlaw.com/en/insights/publications/2026/06/insights-technology-aiml-authorizing-agentic-payments)). The networks are moving into the enforcement position round 1 assumed was empty. Leash's defensible claims must be about **depth of semantic comparison, issuer-side state and evidence**, not about being the only party that checks anything.

### Finding 2 — the runtime-consistency gap has a published name

[**Compositional Policy Violations: When Step-Level Compliance Fails in Agentic AI Workflows**](https://arxiv.org/pdf/2609.18820) formalises exactly the failure class round 1 described: *every individual step passes its own check while the composed execution violates the governing policy*. Because "a predicate over a single step cannot evaluate a property that step does not determine," making per-step monitors more accurate **cannot** close this class. Its four-type taxonomy maps almost one-to-one onto our intended checks:

| Paper's violation type | Leash check it names |
| --- | --- |
| Authority creep | Delegation must strictly narrow; no re-broadening across steps |
| Threshold laundering | Restructuring a purchase to slip under a limit or a step-up threshold |
| Cumulative sum violation | Rolling totals, velocity, split-charge evasion |
| Context collapse | Purpose or constraint lost between confirmation, checkout and capture |

Its enforcement proposal is also ours, stated better: a **provenance-aware runtime that evaluates policy over complete execution traces and recomputes guarded quantities from raw provenance rather than from the pipeline's derived representation.** That is the formal version of our "merchant text is untrusted data" rule — never trust a total the agent or shop computed; recompute it from the source rows.

Supporting prior art, all of which strengthens the architecture and weakens any novelty claim:

- [**Out-of-band policy enforcement at a trusted tool boundary**](https://arxiv.org/pdf/2608.27646) — Cedar policy at an HTTP proxy outside the model's reasoning loop. Over 3,621 trials, security failures fell from **57.6% to 0.2%** with task completion at 60.9% (from 79.1%); safe-and-useful completions up 21.8 points. It also states our attenuation rule verbatim: *the data policy owner sets the maximum grant; agent policy can only narrow it.* This is the empirical citation for "rules decide, models advise" — use the numbers, attribute them.
- [**Closure gaps and delegation envelopes**](https://arxiv.org/pdf/2604.25000) — argues authorisation must stop being binary and become a bounded envelope of autonomy measured across semantic, evidentiary, procedural and institutional dimensions. Useful vocabulary for the mandate.
- **Amazon Bedrock AgentCore Cedar policies** (GA 3 March 2026) intercept every agent-to-tool request at a gateway and evaluate deterministic policy *outside agent code, immune to prompt injection* ([AWS](https://aws.amazon.com/blogs/security/enforce-least-privilege-authorization-in-multi-agent-ai-chains-using-cedar/), [implementation guide](https://hidekazu-konishi.com/entry/amazon_bedrock_agentcore_policy_implementation_guide.html)). **Dogwood**, a temporal Cedar extension using metric first-order temporal logic, exists specifically so "a hallucinating AI agent can't circumvent spending limits by rapidly issuing concurrent requests" ([Harness](https://www.harness.io/blog/policy-as-code-in-2026-opa-kyverno-cedar-and-what-s-next)). Our stateful consume-once ledger is therefore **table stakes, not a differentiator** — but it is table stakes almost nobody has implemented on card rails.

**Implication.** Reposition from "we invented runtime intent verification" to "**we are the first to put provenance-aware compositional policy enforcement inside an issuer's payment authorisation path, with money semantics**." The research community has the idea; nobody cited here has it in a card authorisation with Decimal money, FX, partial capture, refunds and a 8-second deadline.

### Finding 3 — competitors and where each one stops

| Player | What it does | Where it stops |
| --- | --- | --- |
| **Nekuda** ([docs](https://docs.nekuda.ai/system-overview), $5M led by Madrona with **Amex Ventures and Visa Ventures**) | "Agentic Mandates": what the agent may buy, under which conditions, spend limits, when approval is required — passed as a verifiable message to the rest of the stack | Mandate *capture and transport*. It asserts intent; it does not adjudicate whether the final charge still means it. **Closest thing to TaskCard that already exists — assume the jury knows it.** |
| **Stripe** ([Shared Payment Tokens](https://docs.stripe.com/agentic-commerce/concepts/shared-payment-tokens), [ACP / UCP](https://docs.stripe.com/agentic-commerce/protocol)) | Scoped seller access to a payment method, risk signals carried in the token, per-transaction visibility | **Today Stripe requires human review before each credential is shared**; spending limits and conditions for acting without fresh approval are explicitly *roadmap*. The policy layer Leash wants is a stated gap in the market leader's own docs. |
| **Visa** (Intelligent Commerce + Trusted Agent Protocol) | Scoped tokens, Cloud Token Framework, agent identity via Web Bot Auth, passkey SCA, issuer trust controls | Recognising a legitimate agent and tying tokens to issuer policy. Purpose-level semantics of one specific purchase are not the unit of control. |
| **Mastercard** (Agent Pay, Agentic Tokens, Verifiable Intent) | Registered agents, tokenised agent authority, consent freshness in Decision Intelligence, **real-time revocation from the issuer app** | Scoring and signal validation, not deterministic purpose adjudication with an auditable reason trail. |
| **Lithic / Marqeta / Stripe Issuing** ([Lithic](https://www.lithic.com/blog/agentic-payments), [Marqeta MCP](https://www.marqeta.com/blog/bringing-agentic-payments-to-life-with-marqetas-mcp-server), [Stripe Issuing for agents](https://docs.stripe.com/issuing/agents)) | Single-use virtual cards, per-merchant and MCC restrictions, velocity and daily caps, **Authorization Stream Access for just-in-time auth rules** | Amount/merchant/velocity — the checks every hackathon team builds. No purpose, no substitution detection, no intent provenance. Lithic's ASA is the closest existing *hook* for what Leash does. |
| **Skyfire, Catena Labs, Payman, PayOS, Proxy, Rye** ([landscape](https://www.useproxy.ai/blog/ai-agent-payments-landscape-2026)) | Agent identity ("Know Your Agent"), agent-native accounts, disbursements, per-agent cards, checkout execution | Identity and execution. Authority semantics are someone else's problem. |
| **Zenity, Lakera, Palo Alto Prisma AIRS, Sweet Security** ([Arthur roundup](https://www.arthur.ai/column/best-ai-agent-security-platforms-2026), [Galileo](https://galileo.ai/blog/best-ai-agent-guardrails-solutions)) | Runtime AI security: prompt-injection blocking, tool-call interception, drift from behavioural baseline, intent-based detection over the full execution path | Security posture, not money. No ledger, no verdict an issuer can authorise on, no dispute evidence. They detect *anomaly*; Leash must decide *authority*. |
| **x402 Foundation** (Linux Foundation, April 2026; Coinbase, Cloudflare, AWS, Anthropic, Visa, Mastercard, Stripe, Amex; 169M payments in year one) ([Coinbase](https://www.coinbase.com/blog/coinbase-and-cloudflare-will-launch-x402-foundation), [InfoQ](https://www.infoq.com/news/2026/07/cloudflare-aws-x402-micropayment/)) | Stablecoin micropayments at the HTTP/edge layer for agent-to-service spend | A different rail (machine-to-machine micropayments), not consumer card commerce. Out of scope for the hackathon; relevant to the protocol-neutral intent schema later. |

**The honest read:** identity is solved, credential scoping is solved, amount/merchant/velocity limits are commodity, and per-step guardrails are a crowded vendor category. The uncrowded seats are **cross-stage semantic adjudication** and **evidence**.

### Finding 4 — the evidence and dispute gap is the strongest unclaimed wedge

This is the most useful thing this round found, and round 1 only touched it as "consistency receipt."

- **No binding rule exists.** As of 2026 no government has enacted agentic-commerce liability rules, and neither Visa nor Mastercard has published a binding chargeback rule for agent disputes, despite both shipping scoped-credential rails ([Chargeflow](https://www.chargeflow.io/blog/ai-agent-chargeback-liability)).
- **The evidence simply is not there.** Traditional dispute evidence — 3-D Secure results, device fingerprints, IP, browsing history — assumes a human decided. For agent-initiated purchases that trail does not exist, so **merchants pay by default** and disputes are hard to fight in either direction ([Justt](https://justt.ai/blog/solving-agentic-commerce-chargebacks/)).
- **What is missing is exactly what Leash captures.** Rivero (Swiss, Zurich) lists the gaps as: *what did the cardholder actually ask the agent to do; what options did the agent present; did the agent omit information that affected the decision; were there misleading techniques in the checkout flow.* Their recommendation to issuers is to build infrastructure to ingest **intent data, agent behaviour logs and presentation records** ([Rivero](https://rivero.tech/blog/agentic-commerce-needs-new-dispute-framework)). Their framing — *"proving how it happened matters more than whether it happened"* — is the receipt Leash should produce.
- **Fraud is handled; everything short of fraud is not.** Worldpay: for authenticated tokenised transactions liability follows existing rules, but disputes where "the agent misunderstood instructions or bought the wrong item" have no defined allocation among merchant, issuer and agent platform. US Regulation E assumes binary authorisation with no concept of agent misinterpretation; **European PSD2/SCA protections may block agentic transactions outright without technical workarounds** ([Worldpay](https://www.worldpay.com/en/insights/articles/agentic-commerce-liability-is-still-being-written)).
- **US law leans against the consumer.** Under the EFTA a transfer is presumed authorised once the consumer hands credentials to an agent, *even if the agent acts outside what the consumer intended*; TILA turns on actual, implied or apparent authority ([Goodwin](https://www.goodwinlaw.com/en/insights/publications/2026/06/insights-technology-aiml-authorizing-agentic-payments)). Goodwin's fix is to capture authorisation "in retrievable form" beyond a voice prompt or a checkbox, with records establishing **what the consumer reviewed and authorised, when, and under what conditions** — including the conditions governing discretion the customer did not specify.

**Implication for Leash.** The consistency receipt is not a nice-to-have demo screen; it is the artefact that makes an agent purchase **disputable at all**. Reframe it as *the dispute-evidence record agentic commerce is missing*, produced as a by-product of enforcement. It is issuer-native, Viseca owns the customer relationship and the dispute process, and no competitor in the table above is building it.

### Finding 5 — Swiss law already prescribes the control list

[**When AI agents pay: the legal challenges of agentic payments in Switzerland**](https://www.mondaq.com/new-technology/1840674/when-ai-agents-pay-the-legal-challenges-of-agentic-payments-in-switzerland) analyses this under the **Code of Obligations**, not fintech-specific rules: mandate/agency **Art. 394–397 CO**, representation **Art. 32–34 CO** applied by analogy (an AI agent has no legal personality), bank–customer payment relationship **Art. 466 ff. CO**, and liability for auxiliary persons **Art. 101 CO**. FINMA's AI governance guidance **08/2024** and AML duties apply on top.

Its central sentence is the one to quote to the jury: **"an institution cannot delegate its liability to a tool."** Loss allocation:

| Scenario | Who bears it |
| --- | --- |
| Agent exceeds its mandate | The bank pays at its own risk, absent a valid risk-transfer clause |
| Poor discretionary choice within the mandate | Whoever assumed the agency function — provider, platform or institution |
| Agent manipulated (prompt injection) | Contractual allocation only; **no default rule exists yet** |
| Compromised credentials | Classical fraud; allocation depends on mandate binding and behavioural monitoring |

The article requires authority to be split into **the authority to decide** (transaction, counterparty, terms) and **the authority to pay** — which is precisely the wish/mandate split Leash already has. Minimum mandate content: per-transaction and cumulative limits, validity period, permitted merchant categories, payment-instrument scope, geographic restrictions. It insists that **contractual terms, customer instructions and technical enforcement must align** — gaps between them are the dispute vector.

Its seven issuer control points map onto our engine almost one-to-one:

| Legal control point | Leash component |
| --- | --- |
| Mandate — clear, evidenced customer definition of authority | Policy context: wish → confirmed `hard_rules`, versioned |
| Authentication — verify the customer *and* the agent's scoped authority | Agent identity binding + mandate version check |
| Limits — enforced **technically at authorisation** | `domain/decide.py` + rule interpreter |
| Execution — flag and track agent-initiated payments distinctly | `authorizations` projection, agent-initiated marker |
| Monitoring — recalibrate behaviour models for machine velocity | Velocity and familiarity checks on simulated time |
| Revocation — immediate termination or amendment | Mandate state machine (`active → revoked`), tighten-only |
| Audit — records proving compliance with each control | Append-only `decision_events` + consistency receipt |

Its conclusion — **"the payment mandate becomes the new control point"** rather than the individual transaction — is the thesis of this repository, stated by Swiss payment lawyers. That is a strong slide.

**Caveat for the demo:** the paper's own note that PSD2/SCA may block agentic transactions without workarounds, and Visa's European route through Payment Passkeys, mean our `step_up` design should reference passkey/3-D Secure as the trusted confirmation mechanism rather than inventing one.

### Consequences for Leash — what to change

**Positioning.** Drop any "first/novel" claim about signed mandates, scoped tokens, attenuating delegation or consume-once state; each has a 2026 citation or a shipping product. Keep and sharpen these three:

1. **Compositional adjudication with money semantics.** Provenance-aware policy over the whole trace — recomputed from source rows, never from agent- or merchant-derived totals — inside a card authorisation with exact Decimal money, FX, partial capture and an 8-second deadline. Published research does this for data access; nobody cited here does it for money.
2. **Dispute-grade evidence as a by-product.** The record that makes an agent purchase provable, governable and disputable — the gap Rivero, Justt, Worldpay and Chargeflow all independently name, and that the networks have not filled.
3. **Issuer-native placement.** Swiss law puts the liability on the institution and the control point on the mandate. Leash is the mandate control point for an issuer that is already live on agentic rails.

**Demo.** Keep round 1's semantic-drift demo, and add one step that lands the new wedge: after the blocked substitution, show the **receipt answering a dispute** — what the customer asked for, what was shown, what the agent proposed, what changed, which rule fired, what authority remains. Then the jury line becomes: *a signed instruction can still be the wrong purchase — and today nobody can prove which it was.*

**Status of these three consequences, 2026-09-25: none of them is ticketed.** The demo receipt and the CPV renaming exist only in this document. They are research direction, not planned work, until someone writes the tickets.

**Terminology.** Adopt the CPV taxonomy (authority creep, threshold laundering, cumulative sum violation, context collapse) as the names of our check families, with attribution. Free credibility, and it makes the check list look like engineering instead of invention.

**Open questions added by this round**

- Which of the four CPV types can we actually detect with the 45-purchase pack, and which need a scenario we construct?
- Does Viseca's live Mastercard/Visa integration expose an issuer-side hook comparable to Lithic's Authorization Stream Access, i.e. is there a real place to put `decide()` in production?
- Is the receipt an internal audit artefact, a customer-facing statement item, or a dispute-representment document? The three have different content requirements.
- Under Art. 101 CO, does a Leash verdict of `approve` shift or retain liability when the merchant substituted the item? Needs a lawyer, not us.
- If PSD2/SCA blocks some agentic flows outright, does `step_up` via passkey resolve it, or does the mandate itself need to carry an SCA exemption basis?

**Sources added this round**

- [Visa: banks across Europe reach the next phase of agentic commerce](https://www.visa.co.uk/about-visa/newsroom/press-releases.3457328.html) · [FintechNews CH on the European trials](https://fintechnews.ch/payments/visa-ai-agent-payments-europe/84486/) · [Visa takes agentic payments live with 30 European issuers](https://theindustryspread.com/visa-agentic-payments-live-30-european-issuers/) · [Visa Intelligent Commerce Connect](https://thepaypers.com/payments/news/visa-launches-intelligent-commerce-connect-for-agentic-payments) · [Visa Intelligent Commerce (developer)](https://developer.visa.com/capabilities/visa-intelligent-commerce)
- [Stripe shared payment tokens](https://docs.stripe.com/agentic-commerce/concepts/shared-payment-tokens) · [Stripe Universal Commerce Protocol](https://docs.stripe.com/agentic-commerce/protocol) · [Stripe Issuing for agents](https://docs.stripe.com/issuing/agents) · [Lithic agentic payments](https://www.lithic.com/blog/agentic-payments) · [Marqeta MCP server](https://www.marqeta.com/blog/bringing-agentic-payments-to-life-with-marqetas-mcp-server)
- [Nekuda system overview](https://docs.nekuda.ai/system-overview) · [Nekuda funding (Amex + Visa Ventures)](https://www.businesswire.com/news/home/20250514808097/en/Nekuda-Raises-$5M-Led-by-Madrona-Together-with-Amex-Ventures-and-Visa-Ventures-to-Power-Agentic-Payments) · [AI agent payments landscape 2026](https://www.useproxy.ai/blog/ai-agent-payments-landscape-2026)
- [x402 Foundation](https://www.coinbase.com/blog/coinbase-and-cloudflare-will-launch-x402-foundation) · [Cloudflare and AWS embed x402 at the edge](https://www.infoq.com/news/2026/07/cloudflare-aws-x402-micropayment/)
- [Compositional Policy Violations](https://arxiv.org/pdf/2609.18820) · [Out-of-band policy enforcement at a trusted tool boundary](https://arxiv.org/pdf/2608.27646) · [Closure gaps and delegation envelopes](https://arxiv.org/pdf/2604.25000) · [Cedar least-privilege for multi-agent chains (AWS)](https://aws.amazon.com/blogs/security/enforce-least-privilege-authorization-in-multi-agent-ai-chains-using-cedar/) · [Policy as code in 2026 (Cedar, Dogwood, OPA)](https://www.harness.io/blog/policy-as-code-in-2026-opa-kyverno-cedar-and-what-s-next)
- [Rivero: agentic commerce needs a new dispute framework](https://rivero.tech/blog/agentic-commerce-needs-new-dispute-framework) · [Justt: agentic commerce chargebacks and the evidence gap](https://justt.ai/blog/solving-agentic-commerce-chargebacks/) · [Worldpay: agentic commerce liability is still being written](https://www.worldpay.com/en/insights/articles/agentic-commerce-liability-is-still-being-written) · [Chargeflow: AI agent chargeback liability](https://www.chargeflow.io/blog/ai-agent-chargeback-liability)
- [When AI agents pay: the legal challenges of agentic payments in Switzerland](https://www.mondaq.com/new-technology/1840674/when-ai-agents-pay-the-legal-challenges-of-agentic-payments-in-switzerland) · [Goodwin: authorizing agentic payments](https://www.goodwinlaw.com/en/insights/publications/2026/06/insights-technology-aiml-authorizing-agentic-payments)
- [AI agent security platforms 2026 (Zenity, Lakera, Prisma AIRS)](https://www.arthur.ai/column/best-ai-agent-security-platforms-2026) · [AI agent guardrails solutions](https://galileo.ai/blog/best-ai-agent-guardrails-solutions)
