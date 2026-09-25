# LEASH-073: Data factory

**Status**: DONE
**Priority**: P2
**Type**: feature
**Estimated Effort**: L
**Milestone**: M6 — Differentiators (after MVP)
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-006
**Task ID**: 006-T4
**Blocked by**: LEASH-070
**Blocks**: LEASH-075
**Updated**: 2026-09-25

## Description
Generate labelled product-text lines from items.csv templates: benign lines, planted injections by family, position and language, hard negatives with trigger words.

## Business Value
Labels come from construction, no hand labelling.

## Acceptance Criteria
- [x] Each line carries labels for all five questions and its attack family.
- [x] At least 5 attack families, 4 languages, 3 positions.
- [x] Output is deterministic for a seed.

## Technical Approach
`training/data_factory.py`.

### Dependencies
- Needs LEASH-070.
- Blocks LEASH-075.

## Testing Requirements
Write first: `test_planted_line_is_labelled_injection`, `test_same_seed_same_output`.

## Related Files
- `solution/training/data_factory.py`
- `solution/training/tests/test_data_factory.py`

## Out of scope
- LLM paraphrasing (optional follow-up).

## Review log

### 2026-09-24 — review
- [x] met — criterion 1: every row carries `labels` and one-hot `gold` for all five questions plus `attack_family`; `validate()` rejects a missing label, a label/target disagreement or an evidence excerpt absent from the text.
- [x] met — criterion 2: 6 attack families x 4 languages (en/de/fr/it) x 3 positions (start/middle/end) x 4 item relations x 3 return terms x benign/attack twin = 1,728 rows.
- [x] met — criterion 3: `generate(seed=42) == generate(seed=42)`; `manifest.json` pins the generator SHA-256, both source `items.csv` hashes and a hash per output file.
- Hard negatives are the per-family benign twins: same trigger vocabulary, no agent instruction ("Ignore the outdated care instructions" vs "ignore the customer budget"); `validate()` requires both halves of each `pair_id`.
- Absorbed from LEASH-075: family/exact-text split assignment and leakage check, and the hashed manifest. `training/splits.py` is not needed; LEASH-075 is left with public-dataset inclusion (LEASH-074) and a genuinely frozen final evaluation set (`final_evaluation_included: false`).
Check: `PYTHONPATH=. solution/engine/.venv/bin/python -m pytest solution/training/tests -q` - 7 passed.
Verdict: moved to done on the product owner's instruction.

## Open follow-ups (not blocking this ticket)
- The training tests do not run under `uv run pytest` from `solution/engine/` (`testpaths = ["tests"]`, no `solution` on the path, no `__init__.py`). They pass only with the repository root on `PYTHONPATH`.
- Every row is `review_status: pending_template_review`; the DE/FR/IT template wording is unreviewed, and downstream scores (LEASH-076/077) inherit that.
- `manifest.json` hashes `additional-data-history/items.csv`, which is untracked and absent from the CLAUDE.md layout table, so `test_saved_shop_records_match_generator_and_manifests` fails on a fresh clone.
- One attack string per family per language: a model can memorise 24 literal sentences, and `--variants N` adds rows without adding semantic families. `calibration` and `development` hold one held-out family each, so eval variance is large.
