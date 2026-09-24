# LEASH-065: Instruction compiler v1

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: L
**Milestone**: M4 — Customer-control journey
**Rule source**: Viseca brief + Team
**Decisions**: DEC-013, DEC-014, DEC-022
**Parent**: LEASH-005
**Task ID**: 005-T6
**Blocked by**: LEASH-013, LEASH-031, LEASH-117
**Blocks**: LEASH-092, LEASH-101, LEASH-123, LEASH-128
**Updated**: 2026-09-23

## Description
Turn a natural-language instruction into a draft compiled mandate with interpretation notes and open questions for the customer.

## Business Value
The frontend requirement: translate the customer's words into clear, executable permissions.

## Acceptance Criteria
- [x] Amounts, periods, sizes and day counts are extracted by pattern and shown for confirmation.
- [x] Shop, item and uncertainty choices are classified (LLM or Laya), each with a note on how it was read. *Classified through a pluggable `Classifier` port; the deterministic `KeywordClassifier` is the default and conservative (unclear → question). An LLM/Laya classifier plugs into the same port later (Laya is M6).*
- [x] Anything unclear becomes an open question, never a silent default.
- [x] For the five public instructions the draft matches the fixture mandates or asks a question where it differs.
- [x] Compiles fulfilment, quantity, single-purchase and 'regularly' wording per the decision log.
- [x] Every produced field exists in the registry.

## Technical Approach
`policy/compiler.py` with a pluggable classifier; deterministic fallback asks the customer.

### Dependencies
- Needs LEASH-013.
- Needs LEASH-031.
- Needs LEASH-117.
- Blocks LEASH-092.
- Blocks LEASH-101.
- Blocks LEASH-123.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_extracts_chf_200_and_size_43`, `test_unclear_shop_type_becomes_question`.

## Related Files
- `solution/engine/src/leash/policy/compiler.py`
- `solution/engine/tests/policy/test_compiler.py`

## Out of scope
- Free-form chat (LEASH-101).

## Review log

### 2026-09-23 — independent agent review
- [ ] not met — criterion 1 (partly): amounts without a CHF prefix or in words neither read nor asked; "CHF 1,200" read as 1.20; unclear periods ("per day", "in total") became per-order limits; a period attached to the wrong amount; return windows in words/weeks dropped; "size 43 or 44" became 43.
- [x] met as design — criterion 2 (pluggable port; deterministic default), but the classifier guessed.
- [ ] not met — criterion 3: looser operators ("less than" → ≤), misread uncertainty ("Never approve when uncertain" → approve), negations reversed ("Never buy from a shop I have used before" → ≥ 1 purchase; "not for delivery" → delivery), guessed categories, one item picked where several fit, rules nobody asked for, stated limits dropped.
- [x] met — criteria 4 and 6; criterion 5 met for the logged wording, not at the edges (negated delivery, "more than one item").
Verdict: returned to in-progress. Fix — rewrote the reading to be clause-based and conservative: a rule only from un-negated, unambiguous wording in its own clause, everything else a question. Thousands separators; money in other forms asked; "or less" only after the amount; minimum/per-item wording asked; periods only from clear windows in the same clause, other time words asked; return windows in words and weeks; several sizes asked; uncertainty accepted only when exactly one clear, un-negated choice; multiple categories/shops/items asked; hyphenated words match their parts; stated quantities kept ("two items" → ≤ 2), frequencies asked; negated familiarity/fulfilment asked; typos and "often"/"I've used before" recognised. 39 new tests (one per reproduction); 706 pass; mypy clean.

### 2026-09-23 — independent agent review (round 2)
- Most round-1 reproductions fixed. [ ] not met — criteria 1, 3, 5: ~150 new instructions found reversed negations ("not less than CHF 20" → < 20; "anything but clothing" → clothing; "Don't buy the monitor I chose" → that item; "a shop I do not use regularly" → ≥ 3), minimum wording drafted as maximums, ranges and conditionals drafted, unreadable number formats (1.200, 50.-, 1 200, 5 hundred, 50k) dropped or misread, "each"/"per item"/"excluding delivery" misread, stated limits dropped ("a single item", "only buy once", "at most 2 orders", "within a month", "size EU 42", "familiar shops").
- [x] met — criteria 2, 4, 6.
Verdict: returned to in-progress. Fix — structural rather than word-by-word: a sentence-level confidence gate. Constructions the compiler fully understands are removed first; if anything risky remains (negations, minimum/range/conditional wording, "or" alternatives, "each" without "order", unreadable number formats, shipping/excluding wording), the sentence yields no rules, only a question quoting it plus questions for every field its words touch. New readings: "a single item", "only buy once", "at most N orders", "within a fortnight"; cues without a clear reading (size, returns, familiar shops, any unread CHF amount) are asked; single-purchase rules only for a uniquely matched item. 49 new tests (one per reproduction); 780 pass; mypy clean.

### 2026-09-23 — independent agent review, round 3
- [x] met — criteria 2, 4, 6.
- [ ] not met — criteria 1, 3, 5: the `_RISKY` deny-list missed wording it didn't contain ("save for", "barring", "forbid", "starting at", "upwards of", "combined", "til Friday", "too big", "a dozen items", "up to three orders", "delivery/pickup", ranges with two amounts, two chosen items, an item plus a category, extra words around the uncertainty choice).
Verdict: returned to in-progress. Fix: the gate is now an allow-list (`_KNOWN` plus the catalogue's item-name words). Any other word or symbol, or any number no reader accounts for (`_COUNTED` / `_STRAY_NUMBER`), makes the sentence a question. Also: two CHF amounts in one clause are asked; several chosen items are asked; a chosen item plus an item category is asked; an uncertainty sentence may hold only the choice itself. All 48 round-3 counterexamples are regression tests (`ROUND_3` in `tests/policy/test_compiler.py`).

### 2026-09-23 — independent agent review, round 4
- [x] met — criteria 2, 4, 6.
- [ ] not met — criteria 1, 3, 5: allowed words recombined into wrong readings:
  - "Pause clothing." and "Stop pickup." were reversed;
  - "Ask me for delivery.";
  - a period in another clause was dropped ("In any 7 days, buy …");
  - "per shop" and "per session" were read as per order;
  - "Buy groceries once", "a single book", "delivery orders only" and ", regularly" dropped or misread their limit;
  - uncertainty-looking sentences bypassed the gate;
  - "in 0 days" crashed.
Verdict: returned to in-progress. Fix:
- The gate is now a clause grammar (`_PHRASES` + `_grammar`): every clause must be consumed start to end by known phrases.
- Catalogue words are allowed only inside a chosen-item phrase ("the … I chose", "my …").
- A period is read only in the same clause as its CHF amount.
- An uncertainty sentence is skipped only when it is exactly a known form (`_UNCERTAINTY_FORMS`); any other sentence mentioning uncertainty makes the choice a question.
- Two different per-order limits, or two different item counts, are asked.
- "a single book" counts as one item.
- 27 round-4 counterexamples plus 5 more are regression tests.

### 2026-09-23 — independent agent review, round 5
- [x] met — criteria 2, 4 and 6. All 553 earlier probes re-run: every accepted sentence reads as stated, reads stricter, or asks.
- [ ] not met — criteria 1, 3 and 5:
  - "any 0 days" and "over 0 days" crashed;
  - with two day counts in one clause, the first was used, so a return window or a 7-day window could become the spending window (looser, silent);
  - "at most seventy orders" was dropped;
  - "at most 5 orders, at most 2 purchases" read only the first count.
Verdict: returned to in-progress. Fixes:
- A zero-day window is asked.
- Return windows and item names ("the … I chose", "my …") are removed before looking for the spending window.
- More than one window for one amount is asked.
- Every "at most N orders" is read, and one no reader knows is asked. "Buy once" no longer hides a count.
- seventy and eighty were added.
- One general check: the same rule stated with different values (two per-order limits, sizes, return windows, counts, period limits) is asked.
- "CHF 1200" without a separator is read.
- 20 regression tests; 1115 pass.

### 2026-09-23 — independent agent review, round 6
- [x] met — criteria 2, 4 and 6. All 646 earlier probes re-run with no regressions; all round-5 cases fixed.
- [ ] not met — criteria 1 and 3: a stated period was silently dropped (read per order) when an item-name span swallowed it ("Buy my city day pass per week up to CHF 30"), or when a clause mentioning a return window carried a period ("up to CHF 300, over 30 days if they can be returned within 14 days").
- [ ] not met (edge) — criterion 5: a chosen item with a stated quantity dropped the DEC-013 one-purchase rule.
- Stricter, reported: the conflict check could be defeated with a different operator; "a payment" wasn't per order.
Verdict: returned to in-progress. Fixes:
- Item-name spans never cross an amount, period or "the/my" word. An open "my …" span also stops at period words, so the period is read (stricter) or asked, never dropped.
- A return window no longer licenses a period elsewhere in its clause; a period without a CHF amount in the same clause makes the sentence a question.
- A chosen item always adds max_count ≤ 1.
- The conflict check ignores the operator.
- "a payment" counts as per order.
- 14 regression tests; 1139 pass.

### 2026-09-23 — independent agent review, round 7
- [x] met — criteria 2, 4 and 6. All round-6 counterexamples fixed; no regressions across 13 probe sets.
- [ ] not met — criteria 1, 3 and 5:
  - ",and" hid a period: the gate and the amount reader split clauses differently;
  - an item count was dropped when a CHF number preceded it, or bound to a window's day number ("any 7 days two items" gave ≤ 7);
  - "at most N orders" was dropped whenever "per/a/each order" appeared anywhere.
- Borderline: "buy my book" was read as the whole books category; a period alone in its own sentence was asked only as "instruction", not under billing.
Verdict: returned to in-progress. Fixes:
- The gate now uses the readers' own clause split (`_clauses`), so both see the same clauses.
- An item count binds only to its own number: no number, amount or period word may sit between the count and "items".
- "at most N orders" is read unless it is itself a frequency ("… per week", which is asked).
- "buy/order my X" names an item: the catalogue item, or an item_id question.
- Period words cue a billing question.
- 23 regression tests.
- Diff against round-7 outputs: only a1, b1, r4 and r4b change, and every change is a new question or a stricter rule.

### 2026-09-23 — independent agent review, round 8
- [x] met — criteria 1, 2, 4 and 6. 747 instructions probed; the round-7 changes are all questions or stricter rules.
- [ ] not met — criteria 3 and 5:
  - (a) the digits after an amount's separator became an item count: "Buy up to CHF 30.50 the paperback book order I chose" gave max_quantity ≤ 50, replacing DEC-013's ≤ 1; "CHF 2,000 books" gave ≤ 0;
  - (b) "my X" not directly after "buy" was read as the whole category.
Verdict: returned to in-progress. Fixes:
- A count never starts right after a digit or separator, and "the/my/I/chose" can't sit between a count and "items".
- "my X" anywhere names an item (`_MY_ITEM`), and every named item counts towards "several named items → ask".
- 11 regression tests. Diff against round-8 outputs: one line changed (a false count removed).

### 2026-09-23 — independent agent review, round 9
- [x] met — criteria 1, 2, 4 and 6. 800 probes, round-8 fixes held.
- [ ] not met — criteria 3 and 5: a stated count was dropped, together with DEC-013's one purchase:
  - (A) after a comma with no space ("Buy up to CHF 20,one grocery item"). This came from the round-8 lookbehind;
  - (B) with more than three filler words before "items".
Verdict: returned to in-progress. Fixes:
- ",word" becomes ", word" before any reading, so the gate and the readers see the same text; the stored instruction stays verbatim.
- The count window allows up to six words, matching the grammar's fillers.
- New safety net: any clause that states a count next to "items" or "books" and yields no quantity reading gets a quantity question. An unreadable count is asked too.
- 12 regression tests. The diff against the round-9 outputs is empty on every earlier set; the e1 and e2 counts are all read or asked.

### 2026-09-23 — independent agent review, round 10
- [x] met — criteria 1, 2, 4 and 6. 877 probes; round-9 fixes held; public five unchanged.
- [ ] not met — criteria 3 and 5: a size or an order count was read as the item count and overrode DEC-013's one item. Examples: "Buy my hiking boots in size 43 items" gave max_quantity ≤ 43; "Buy the road-running shoes I chose, at most 2 purchases some items" gave ≤ 2. Borderline: "CHF 200,5" was read as 200.50.
Verdict: returned to in-progress. Fixes:
- A count right after "size", "EU" or "at most" is never an item count.
- "orders/purchases/size" can't sit between a count and "items"; the safety net still asks.
- An amount with a decimal comma is asked, not guessed.
- 10 regression tests. Diff against round 10: only false counts removed and decimal-comma amounts turned into questions.

### 2026-09-23 — independent agent review, round 11
- [x] met — criteria 1, 2, 4 and 6. All round-10 changes are removed false rules or new questions; a 160k-combination fuzz found only the family below.
- [ ] not met — criteria 3 and 5: the grammar accepted a count before a category noun ("Buy two cosmetics", "Buy one grocery"), but the count reader only reads "items"/"books". The count and DEC-013's single purchase were dropped silently.
Verdict: returned to in-progress. Fix: the grammar allows a count only before "item(s)", "item(s) of clothing", "grocery item(s)" or "book(s)". A count before a plain category noun makes the sentence a question. "a single" likewise needs "item of clothing", "book" or "grocery item". 9 regression tests. Diff against round 11: one mixed sentence (p7) is now asked in full.

### 2026-09-23 — independent agent review, round 12
- [x] met — criteria 1, 2, 4 and 6. A new oracle fuzz (about 145k accepted instructions, 7 seeds) found no silent looser or reversed rule in any family except item naming.
- [ ] not met — criteria 3 and 5 (item naming only):
  - "My hiking boots replace my worn road-running shoes" silently named one of the two items;
  - "Buy my hiking boots below CHF 1'000" lost the named item and its DEC-013 rules, because the `_MY_ITEM` span found no ending word.
Verdict: returned to in-progress. Fix:
- Every "my …" and every "… I chose" counts as a named item, whatever follows it. More than one → item_id question.
- A "my …" whose name can't be read → item_id question.
- 6 regression tests; probe diff against round 12 is empty; 1255 tests pass.

### 2026-09-23 — independent agent review, round 13
- [x] met — criteria 1–6.
  - All 25 earlier probe sets (1,004 instructions) match round 12 exactly.
  - The round-12 oracle over 13 seeds (about 270k accepted instructions) and an extended oracle over 8 seeds (about 224k: more separators, item-naming phrases and windows) found no silent looser or reversed rule. Every remaining hit either asks the field or is stricter.
  - About 100 targeted item-naming probes: two named items are always asked, and an unreadable name is asked.
- Silent stricter readings, reported for the record (none looser):
  - "delivery only" inside an item name becomes a delivery rule;
  - a shop phrase also adds an item category;
  - a plain category next to a named item is dropped in favour of the item;
  - conflicting rules are kept together.
Verdict: all met. Moved to done on the product owner's standing instruction for this run.
