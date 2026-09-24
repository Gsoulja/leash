# Leash decision engine — evaluation report

Generated 2026-09-24T09:49:17+00:00 · commit `8fe5c24` · 5 passed, 0 failed, 2 measured

The challenge pack ships purchase inputs with no expected verdicts, so nothing here is an
accuracy score. Each claim below is a property of the engine that can be checked directly.

| ID | Claim | Result | Measure |
| --- | --- | --- | --- |
| E-01 | The engine is deterministic: identical inputs always produce identical verdicts | **PASS** | 3 independent replays agree on all 45 purchases |
| E-02 | Every verdict is pinned to a recorded baseline | **PASS** | 45/45 purchases unchanged |
| E-03 | Ordinary purchases are not blocked: the verdict mix is reported, never assumed | **INFO** | 12 approve, 11 step_up, 22 decline of 45 |
| E-04 | Every rule field the engine advertises is exercised by a real purchase | **PASS** | 13/13 registry fields used · 13 checks fired · 17 distinct reason codes |
| E-05 | A model, a mandate change or merchant text can never loosen a verdict | **PASS** | 992/992 offline tests passed |
| E-06 | Every verdict that rests on our own assumption rather than the brief is declared | **INFO** | the largest single assumption controls 7/45 verdicts |
| E-07 | No approach that only changes fact reading is ever less strict than the reference | **PASS** | 4 approaches compared, 0 safety breaches |

## E-01 — The engine is deterministic: identical inputs always produce identical verdicts

**PASS** · 3 independent replays agree on all 45 purchases

- Verdict-table digest: `cf2fe9351ab42b6f`
- No clock, database or model call takes part in `decide()`; it is a pure function.
- A disagreement here would mean hidden state leaked into the domain.

## E-02 — Every verdict is pinned to a recorded baseline

**PASS** · 45/45 purchases unchanged

- No verdict or reason code changed since the baseline was recorded.

## E-03 — Ordinary purchases are not blocked: the verdict mix is reported, never assumed

**INFO** · 12 approve, 11 step_up, 22 decline of 45

- `SCEN0000`: 1 approve, 0 step_up, 0 decline
- `SCEN0001`: 5 approve, 2 step_up, 3 decline
- `SCEN0002`: 1 approve, 3 step_up, 8 decline
- `SCEN0003`: 4 approve, 1 step_up, 6 decline
- `SCEN0004`: 1 approve, 5 step_up, 5 decline
- There is no expected-verdict column in the pack, so this is a measurement, not a score.
- It exists so that a change which quietly raises the block rate is visible.

## E-04 — Every rule field the engine advertises is exercised by a real purchase

**PASS** · 13/13 registry fields used · 13 checks fired · 17 distinct reason codes

- Checks that ran at least once: duplicate, fulfilment, items, known, once, period, price, returns, session, shoptype, size, split, text.
- Reason codes observed: already_purchased, final_sale, instruction_in_shop_text, item_mismatch, lookalike_merchant, merchant_category, outside_purpose, over_order_limit, over_period_limit, possible_duplicate, possible_split, returns_too_short, returns_unknown, session_risk, size_mismatch, unfamiliar_merchant, unrequested_addon.
- No registry field is left unexercised.

## E-05 — A model, a mandate change or merchant text can never loosen a verdict

**PASS** · 992/992 offline tests passed

- Tightening a mandate never makes any of the 45 verdicts less strict.
- Model-supplied facts never make a verdict less strict than the deterministic one.
- Merchant text never changes the status of a limit check.
- A mandate rule the engine cannot evaluate never approves.
- Proven by the seeded property suite and the domain rules under tests/domain, tests/policy, tests/property, tests/application, tests/contracts.

## E-06 — Every verdict that rests on our own assumption rather than the brief is declared

**INFO** · the largest single assumption controls 7/45 verdicts

- **DEC-013** — Singular wording means buy it once: decides 5/45 verdicts, and appears in 21 explanations.
- **DEC-014** — "A shop I use regularly" = 3 earlier approved purchases: decides 7/45 verdicts, and appears in 7 explanations.
- **DEC-022** — "For delivery" is an enforceable fulfilment rule: decides 0/45 verdicts, and appears in 0 explanations.
- **DEC-024** — Session risk scoring v1: decides 1/45 verdicts, and appears in 5 explanations.
- **DEC-023** — Split-order detection is on: decides 3/45 verdicts, and appears in 3 explanations.
- **Uncertainty policy** set to `approve` instead of `ask`: moves 1/45.
- **Uncertainty policy** set to `decline` instead of `ask`: moves 11/45.
- Each row re-runs all 45 purchases with that assumption removed and counts what moves.
- A verdict can survive an assumption being wrong and still lose the reason it was explained with.
- These are the questions whose answers would change the most, listed in `docs/decisions.md`.

## E-07 — No approach that only changes fact reading is ever less strict than the reference

**PASS** · 4 approaches compared, 0 safety breaches

- `regex`: 12 approve / 11 step_up / 22 decline · 0 stricter, 0 looser than `regex` · 90 facts read · 0.58 ms/purchase
- `blind`: 11 approve / 14 step_up / 20 decline · 1 stricter, 2 looser than `regex` · 0 facts read · 0.51 ms/purchase
- `policy-decline`: 12 approve / 0 step_up / 33 decline · 11 stricter, 0 looser than `regex` · 90 facts read · 0.53 ms/purchase
- `policy-approve`: 13 approve / 10 step_up / 22 decline · 0 stricter, 1 looser than `regex` · 90 facts read · 0.67 ms/purchase
