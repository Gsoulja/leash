# Historical transaction data pack (history only, no scenarios)

This is a trimmed version of [`../additional-data/`](../additional-data/) for
teams who asked for more data to analyse customer/card behaviour or train a
model. It contains **only the historical transaction data and the reference
tables needed to make sense of it** — no scenarios, no purchase attempts, no
cardholder instructions, and no scenario fixtures.

Like the full pack it contains **no real people, no payment credentials, no
risk labels, no expected decisions, and no answer key**. The only supervised
signal is the historical `status` column, which is an authorization outcome,
not a fraud label — see the note on learnability below before training on it.

## What is in it

| File | Rows | Contents |
| --- | ---: | --- |
| `customers.csv` | 500 | Personas, `CU1001`–`CU1500` |
| `accounts.csv` | 630 | `AC1001+`; account types, purposes, limit pairs |
| `cards.csv` | 835 | `CA1001+` plus 57 replacement cards `CA9000+` |
| `merchants.csv` | 303 | 58 base merchants plus 245 new ones (`ME0101+`) |
| `items.csv` | 146 | 66 base items plus 80 new ones (`IT0101+`) |
| `fx_rates.csv` | 4 | Fixed synthetic CHF/EUR/GBP/USD rates |
| `authorization_history.csv` | 144,674 | `TR100001+`, 2025-09-01 to 2026-07-31, past purchases, cash withdrawals, and refunds |
| `schemas/authorization_history.schema.json` | – | Column contract for the historical CSV |

These are byte-for-byte the same files as in `additional-data/` (same
SHA-256 hashes, listed in that pack's `metadata.json`). Not included here:
`scenario_catalogue.csv`, `scenario_authorities.csv`, `purchase_attempts.csv`,
`purchase_attempt_items.csv`, `scenario_fixtures/`, and the two schemas that
only apply to scenarios/live events (`authorization_event.schema.json`,
`data_pack.schema.json`).

## Joins

```text
customers.csv
  └──< accounts.csv                 via customer_id
        └──< cards.csv              via account_id
              └──< authorization_history.csv  via card_id

merchants.csv ──< authorization_history.csv   via merchant_id
items.csv                                      (not joined here — cart-line
                                                 detail lives in the scenario
                                                 pack, not in history)
```

Use IDs to connect files. Never join on customer, merchant, or item names.

## How the history was made realistic

Rows are simulated per customer from a behavioural archetype (family planner,
business traveller, shift worker, student, renovator, pet owner, retiree,
commuter, cross-border shopper, expat, and so on) that fixes the category
mix, channel mix, hour-of-day profile, agent adoption, travel propensity, and
account/card structure. Modelled explicitly: habitual merchants and devices,
recurring subscriptions, trips abroad, cash withdrawals, refunds, duplicate
submissions, a multi-factor outcome model with latent (unobservable) causes,
card lifecycle (blocks, expiries, replacements), unlabelled anomaly bursts,
and agent activity (13.2% of rows). Full detail is in
[`../additional-data/README.md`](../additional-data/README.md).

### How learnable is `status`? (read this before training on it)

A regularised logistic regression trained on features a participant can build
from the history alone (binned amount z-score, familiarity counts, velocity,
hour, country, channel, limit ratios, card status), with a customer-level
hold-out, scores **AUC 0.81 / AP 0.56** overall and **AUC 0.65 / AP 0.08** on
rows where no hard rule (limit breach, blocked/expired card,
international-disabled card) fires. Outside those deterministic rules,
`status` is only weakly predictable from the row by design — most real
declines have causes the row does not show. Do not treat `status` as a fraud
label.

## Regenerating or scaling

This subset was copied from a run of the generator in
[`../additional-data/generator/`](../additional-data/generator/). To produce
history-only data at a different scale, run the full generator and take just
the files listed above:

```bash
python3 additional-data/generator/generate.py --out <dir> --customers 500 --seed <seed>
```
