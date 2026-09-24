# LEASH-117: Hard-rule field registry

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M1 — SCEN0000 offline vertical slice
**Rule source**: Team
**Decisions**: DEC-004
**Parent**: LEASH-005
**Task ID**: 005-T8
**Blocked by**: LEASH-013
**Blocks**: LEASH-051, LEASH-060, LEASH-065, LEASH-119, LEASH-120, LEASH-121, LEASH-128
**Updated**: 2026-09-23

## Description
A canonical, versioned registry of every hard_rule field the engine understands: API paths (authorization.billing_amount_chf, authorization.fulfillment_method, items.item_category …) and our own `leash.`-prefixed fields (leash.merchant.prior_purchases.v1, leash.purchase.max_count.v1, leash.items.max_quantity.v1, leash.items.size.v1, leash.order.return_days.v1, leash.session.risk_score.v1 …).

## Business Value
Guarantees every confirmed restriction reaches the engine through the live event and is understood the same way every time.

## Acceptance Criteria
- [x] Each field has a name, version, allowed operators, value type and meaning.
- [x] All 8 schema operators are implemented for every field where they make sense; others are rejected at compile time.
- [x] Unknown fields are reported, never ignored.
- [x] Changing a field's meaning requires a new version.

## Technical Approach
`policy/registry.py`. Used by the parser (LEASH-060), the compiler (LEASH-065) and the release gate.

### Dependencies
- Needs LEASH-013.
- Blocks LEASH-051.
- Blocks LEASH-060.
- Blocks LEASH-065.
- Blocks LEASH-119.
- Blocks LEASH-120.
- Blocks LEASH-121.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_unknown_field_is_reported`, `test_every_registered_field_has_operators`.

## Related Files
- `solution/engine/src/leash/policy/registry.py`
- `solution/engine/tests/policy/test_registry.py`

## Out of scope
- Natural-language compilation.

## Review log

### 2026-09-23 — independent agent review (round 1)
- [x] met — criterion 1: 13 fields with name, version, operators, value kind, meaning, source; derived from FIELD_SPEC.
- [x] met — criterion 2: operator sets sensible per field; everything else rejected by check_rules (probed all 8 operators × fields).
- [x] met — criterion 3: unknown fields reported, never normalised.
- [ ] not met — criterion 4: the fingerprint hashed only the description, not what `supported()` enforces (changing the add-on or split-check logic left all tests green); Viseca-path fields had no way to get a new version.
Verdict: returned to in-progress.

### 2026-09-23 — independent agent review (round 2)
- [x] met — criteria 1–3; lock keyed name@vN; Viseca paths versioned; fingerprint deterministic across hash seeds.
- [ ] not met — criterion 4: mutation testing of mandate.py caught 27 enforcement changes but missed 21: multi-rule combination semantics (union vs intersection, min vs max, tie handling), thresholds between probe points (MAX_RULE_NUMBER 1e6/1e4, period lengths), unprobed values ("yes", "ON", ("on",), "chf", "USD", empty lists). Also: rule behaviour in domain/rules/*.py is outside the fingerprint.
Verdict: returned to in-progress.

### 2026-09-23 — independent agent review (round 3, mutation)
- [x] met — criterion 1: FieldSpec carries name, version, operators, value kind, meaning, source for all 13 fields.
- [x] met — criterion 2: operators come from FIELD_SPEC; unknown operator / wrong kind / unenforceable value rejected at compile time.
- [x] met — criterion 3: unknown fields reported, never dropped.
- [ ] not met (residual) — criterion 4: 21/21 round-2 mutants now caught; 29/42 new mutants caught. 13 missed: split_check synonyms ("true", "enabled"), empty string, magnitudes below -1, period lengths 14/400, lists of 3+, combinations of 3+ rules, and how unsupported rules feed effective constraints (probe recorded "-").
Verdict: stays in progress. Fix: probe texts "true"/"enabled"/""/3- and 4-value lists, -1e10, periods 14 and 400, triples of 8 sampled supported rules, and the effect of every probe rule (supported or not) is now hashed. Lock re-pinned; stable under PYTHONHASHSEED 1/42/999; 442 tests pass; mypy clean. Sent for round 4.

### 2026-09-23 — independent agent review (round 4, mutation)
- [x] met — criteria 1–3 unchanged.
- [ ] not met — criterion 4: all 13 round-3 misses caught; 4 of 18 new mutants missed (period_days > 400 rejected; "GBP" accepted; scope=purchase + period_days read as a period; split_check " on" stripped). Common cause: sampled probes can't cover values between or beyond the samples.
Verdict: stays in progress. Fix: probes for those four (GBP, periods 401 and 100000, ("purchase", 7), " on"/"on "), plus a tripwire test: a structural hash of mandate.py (comments, docstrings and formatting excluded) pinned as ENFORCEMENT_CODE, so any enforcement code change fails until someone decides whether a field's meaning changed (new version) and re-pins. Verified in a scratch copy: an unprobed "JPY accepted" edit trips it; a comment-only edit doesn't. 456 tests pass; mypy clean; stable under PYTHONHASHSEED 1/42/999.

### 2026-09-23 — independent agent review (round 5, mutation)
- [x] met — criteria 1–3.
- [ ] not met — criterion 4: inside mandate.py every one of 27 code mutants trips the tests and none of 7 comment/docstring/format edits do; registry.py edits are caught. But a field's meaning also lives in its rule evaluator: `familiar.py` `>=`→`>` and `session.py` night hour 6→5 passed the whole suite.
Verdict: stays in progress. Fix: `EVALUATORS` maps each field to the code that evaluates it (rule modules and the fact sources they read); each field's fingerprint now also hashes the structure of mandate.py plus those modules, so an evaluation change is a versioned decision (or a deliberate re-pin for a pure refactor). `test_every_field_names_the_code_that_enforces_it` requires an evaluator per field; `authorization.fulfillment_method` has none yet and is listed in `PENDING_EVALUATOR` → LEASH-119. `test_fingerprint_covers_the_evaluator_code` reproduces the round-5 mutant. The separate mandate.py tripwire is folded into the fingerprints. Lock re-pinned; 518 tests pass; mypy clean.

### 2026-09-23 — independent agent review (round 6, mutation)
- [x] met — criteria 1–3.
- [ ] not met — criterion 4: all 27 mutants in listed evaluator modules (incl. round-5 X1–X6) trip the lock, none of 7 formatting edits do; but unlisted shared code can change a field's meaning — `facts.py` `MIN_LINE_SHARE` 64→4000 and `MAX_TEXT_CHARS` 16k→8k passed the whole suite and changed verdicts; clock, decide, purchase and the fallback merge were only caught by other tests; snapshot missing from split_check and max_count.
Verdict: stays in progress. Fix: `SHARED_ENFORCEMENT` (mandate, facts, clock, purchase, checks, decide, fallback_reader, postgres repository) is hashed into every field's fingerprint; snapshot added for split_check and max_count. `test_fingerprint_covers_the_shared_core` reproduces U10. Lock re-pinned; stable under PYTHONHASHSEED 1/42/999; 541 tests pass; mypy clean. Note: fulfilment is accepted by `supported()` but not enforced until LEASH-119 (a pickup order under a delivery-only mandate is approved today) — LEASH-119 is next once this closes.

### 2026-09-23 — independent agent review (round 7, mutation)
- [x] met — criteria 1–3; all round-6 misses (U1–U10) now trip the lock; N18 attributed to the right fields; no false positives.
- [ ] not met — criterion 4: live-path code outside the fingerprint could still change which rows a rule sees with the lock green: the familiarity view in migration 0001 (A5), unit_of_work's run scoping (A10), the seed (A6/A17).
- Outside the criterion: `explain()` could send a step_up as "approve" with the whole suite green (A3).
Verdict: stays in progress. Fix — closing the category rather than patching one more layer: every module in the `leash` package must now be classified as shared core, a field evaluator, or `NOT_A_FIELD_MEANING` with its reason (`test_every_module_is_classified` fails on any unclassified module, so e.g. the event translator LEASH-051 must be classified when added). unit_of_work, seed, decide_purchase and resolve joined the shared core; all migration files are hashed (`test_fingerprint_covers_the_schema` reproduces A5). `test_the_sent_decision_always_equals_the_verdict` pins A3. Lock re-pinned; 589 pass; mypy clean.

### 2026-09-23 — independent agent review (round 8, mutation)
- [x] met — criteria 1–3; all round-7 escapes (A5, A6, A10, A17) now trip the lock; new modules in ordinary packages fail classification; 7 formatting-only edits in Python stay green.
- [ ] not met — criterion 4: `walk_packages` skips directories without `__init__.py`, yet such namespace packages import fine: a fulfilment rule under `domain/rules/ext/` wired into decide escaped classification and hashing, and its meaning could then change with everything green (C3–C5).
- Secondary: `snapshot` missing from billing's evaluators (N10 turned the lock red on the wrong fields); the loader's "offline only" reason was inaccurate (the seed reads merchant names from it). Residual: a contrived field-specific wire change in explain() (K3). False positive: SQL whitespace/comments inside migration strings change the hash (errs safe).
Verdict: stays in progress. Fix: modules are enumerated from the file system and every package directory must have an `__init__.py` (verified: the round-8 namespace-package case now fails the test); `leash` itself classified; snapshot added to billing's evaluators; loader reason corrected; explain() checked on all 45 pack purchases × 5 mandates (`test_the_sent_decision_equals_the_verdict_for_every_pack_purchase_under_every_mandate`). Lock re-pinned; 611 pass; mypy clean.

### 2026-09-23 — independent agent review (round 9, mutation)
- [x] met — criteria 1–3; the round-8 namespace-package hole is closed (C3/C4/C5 caught); N10 now turns billing red; no false positives in 8 formatting-only edits.
- [ ] not met — criterion 4: three honest-looking routes still escaped the fingerprint with everything green: code in a package marker (`leash/__init__.py` patching NIGHT_END_HOUR, E5), rule data in a non-Python file under src/leash (a JSON night hour, E4), and a sibling package `src/leash_ext` wired into decide (E2). Minor: a compiled-only .pyc (E1) and a symlinked directory (E3).
- Correction: the round-8 note claimed the 45×5 explain test addresses K3; it does not — a targeted `explain()` change keyed to one reason code (K3, K6) still passes. Those, like E6 (a patch planted in config.py), are deliberate code in modules classified as not carrying a field's meaning.
Verdict: stays in progress. Fix: `test_nothing_that_decides_behaviour_can_hide_outside_classified_python_modules` — src/ may hold only the leash package, every file in it must be a Python module (or py.typed), no symlinks, and every package marker must be empty. Verified in a scratch copy: E2, E4 and E5 each fail it. Residual stated explicitly: deliberate targeted code in a module classified as "no meaning" (K3, K6, E6) is a code-review matter the fingerprint can't detect; the classification reasons make such modules easy to audit. 615 pass; mypy clean.

### 2026-09-23 — independent agent review (round 10, partial — stopped early on request)
- [x] met — criteria 1–3.
- [x] met for every route run — criterion 4: all round-9 escapes (E1–E5, E7) now fail a test. Not yet run: N15 (a constants module classified "no meaning" imported by an evaluator) and N16 (a helper shared by two fields but listed under one) — both judged likely to escape from reading the code; N1 (a .sql migration input) was caught only by an adapter test.
- Point 3: the code-review residual is a reasonable standard, but it must also cover human classification and attribution, not only deliberate sabotage.
Fix after review: `test_everything_an_evaluator_imports_is_hashed_for_that_field` — every leash module an evaluator imports must be hashed for that field (shared core or its own evaluators), except pure `Protocol` interfaces. `money` and `snapshot` moved into the shared core. Every file under migrations/versions is hashed (Python by structure, others by content). Verified in a scratch copy: N15 and N16 now each fail the new test. Lock re-pinned; 616 pass; mypy clean.
Residual (for the product owner): deliberate code planted in a module classified as not carrying a field's meaning (K3, K6, E6), and the correctness of the written classifications themselves, are code-review matters the fingerprint can't detect.

### 2026-09-23 — independent agent review (round 11)
- [x] met — criteria 1–3.
- [ ] not met — criterion 4: N15, N16, N1 and E1–E5 all caught; 6 formatting-only edits green; but N17 escaped — a constants module classified "no meaning" imported by a *shared-core* module (MIN_LINE_SHARE moved out of facts.py), because the import check only walked evaluators. Also the shared-core regression test searched for a literal a refactor would remove.
- Accepted: a whitespace change in a non-Python migration file trips the lock (errs safe, loud, fixed by a deliberate re-pin).
Fix after review: the import check now also requires everything a shared-core module imports to be hashed (shared core, an evaluator, or a pure Protocol interface). Following it moved shop_text, states, ports.repository, explain and the pack loader into the shared core — which also closes the round-8/9 residual K3/K6 (a targeted change to explain() now turns the lock red). The shared-core regression test appends an override instead of matching a literal. Verified in a scratch copy: N17 fails the test. Lock re-pinned; 616 pass; mypy clean.
Residual (narrowed, for the product owner): the modules still classified "no meaning" (config, API client, outbox sender, replay, HTTP views, question bank, the reader interface, empty package markers) are enforced as never imported by any rule or shared-core code; what remains is deliberate import-time patching planted in one of them (E6) — a code-review matter.

### 2026-09-23 — independent agent review (round 12)
- [x] met — criteria 1–3.
- [x] met for every code route inside src/leash — criterion 4: N17 and the ZURICH variant, K3/K6 (explain() now hashed), N15, N16, N1, E1–E5 all red; 6 formatting-only edits (incl. explain.py and shop_text.py) green.
- [ ] not met as worded — rule parameters read at runtime from outside the code escaped: an environment variable (R1), a data file outside src/ (R2), and a string-based dynamic import (R4). Reviewer: ready once either a test forbids these in hashed modules, or the residual says so.
Fix after review: `test_rule_parameters_are_code_not_environment_files_or_dynamic_imports` — shared-core and evaluator modules may not read `os.environ`/`getenv`, open or read files (only the pack loader and seed read Viseca's read-only CSVs), or import dynamically (`importlib`, `__import__`). Verified in a scratch copy: R1, R2 and R4 each fail it. 617 pass; mypy clean. The reviewer's stated condition for readiness is met.
**Residual accepted into the ticket (product owner to confirm):** deliberate code planted in a module classified as not carrying a field's meaning — config, API client, outbox sender, replay, HTTP views, question bank, the reader interface — that patches other modules at import time (E6). Those modules are enforced as never imported by rule or shared-core code; what remains is a code-review matter.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
