# Product notes

Ideas in this file are product hypotheses, not implemented capabilities or accepted architecture decisions.

## Leash TaskCard — purpose-bound payment authority for AI agents

**Status:** Product vision / hackathon differentiator

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
