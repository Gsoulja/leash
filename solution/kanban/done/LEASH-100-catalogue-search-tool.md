# LEASH-100: Catalogue reference resolution for permissions

**Status**: DONE
**Priority**: P2
**Type**: feature
**Estimated Effort**: S
**Milestone**: M6 — Differentiators (after MVP)
**Rule source**: Engineering
**Decisions**: DEC-033, DEC-034, DEC-035, DEC-036, DEC-037
**Parent**: LEASH-008
**Task ID**: 008-T1
**Blocked by**: LEASH-030
**Blocks**: none
**Updated**: 2026-09-24

## Description
Resolve customer-named items and merchants against the supplied catalogue during permission clarification. This is optional evidence lookup, not product recommendations or an in-house shopping agent.

## Business Value
The customer can identify an exact product without the model inventing its ID.

## Acceptance Criteria
- [x] Search by name and category returns items with price ranges and shops.
- [x] Results carry IDs.
- [x] An ambiguous or absent reference returns candidates or a clarification; it never silently selects a product.
- [x] Catalogue price ranges are context only; the actual checkout supplies the purchase price.

## Technical Approach
`adapters/pack/catalogue.py`. The ticket's original `solution/assistant/` path predates the 2026-09-24
agreement (DEC-033–037): there is no separate assistant package, the engine owns the pack readers, and a
module outside `solution/engine` would not be reached by `uv run pytest`. It reuses `Pack.merchants()` for
shops and reads `items.csv` for price ranges; classified in `policy/registry.py` as not a field meaning,
because nothing here is read at decision time.

### Dependencies
- Needs LEASH-030.

## Testing Requirements
Write first: `test_search_monitor_returns_it0017`. Run `cd solution/engine && uv run pytest tests/adapters/test_catalogue.py`.

## Related Files
- `solution/engine/src/leash/adapters/pack/catalogue.py`
- `solution/engine/tests/adapters/test_catalogue.py`
- `solution/engine/src/leash/policy/registry.py` (one classification entry)

## Out of scope
- Web search.

## Review log

### 2026-09-24 — independent agent review
- [x] met — criterion 1: IT0017's range (140.00/270.00/650.00) and the four `electronics` merchants
  (ME0022, ME0023, ME0024, ME0059) re-checked straight from `data/items.csv` and `data/merchants.csv`, not
  from the test's own numbers. Category-only and name+category searches verified.
- [x] met — criterion 2: `Candidate.item_id` and `Shop.shop_id` on every result; the ME0022/ME0059
  lookalike pair stays two distinct shops keyed by ID.
- [x] met — criterion 3: probed with monitor, computer monitor, Monitor, jacket, waterproof jacket,
  everyday jacket, shoes, running shoes, running, work shoes, 27-inch, an absent reference and an empty
  search. No case resolves a plural reference; `resolved` is structurally impossible with >1 candidate.
- [x] met — criterion 4: no importer outside its own test, so no catalogue price can reach a rule or a
  purchase amount; no bare `price`/`amount` field; `registry.py` pins it as never read at decision time.
Verdict: all met, moved to review. Check: 10 passed (`tests/adapters/test_catalogue.py`), 333 passed
across `tests/adapters/test_catalogue.py tests/policy`, mypy clean.

Carried to the human gate, none of it required by the four criteria:
- **Shops are a heuristic.** The pack has no item↔merchant table, so shops are `item_category ==
  merchant_category`. Joining `purchase_attempt_items` → `purchase_attempts` → `merchants` shows 5 pairs
  that contradict it (e.g. IT0014 road-running shoes bought at ME0053 GreenLoop, `sustainable_goods`), so
  the list both omits real shops and names shops with no evidence they sell the item. The module docstring
  states the rule openly. A truthful "shops seen selling this item" would need the attempt join instead.
- **Items only, no merchant-name search**, though the Description says "items and merchants". No
  acceptance criterion asks for one and no caller needs one yet.
- Name matching reads `item_name` only, so `shoe` (singular) and `gift card` (vs "Digital gift voucher")
  find nothing — both ask rather than guess.
- `search()` with no arguments returns all 66 items with a clarification listing them. Noisy, still no
  selection.
- After the review, `_tokens` is imported from `policy/compiler.py` rather than duplicated, so the
  conversation and the draft compiler read a name the same way. Re-checked: 333 passed.
