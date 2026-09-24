# Product notes

Ideas in this file are product hypotheses, not implemented capabilities or accepted architecture decisions.

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
2. The LLM shopping assistant proposes candidate rules as an untrusted draft.
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

> Cryptography proves who signed the intent. Leash proves the transaction still means what the customer intended.

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
7. The final receipt proves consistency from customer intent through payment outcome.

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
