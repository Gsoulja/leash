# LEASH-072: Timeout, fallback and circuit breaker for readers

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M2 — All five scenarios offline
**Rule source**: Engineering
**Decisions**: DEC-009
**Parent**: LEASH-006
**Task ID**: 006-T3
**Blocked by**: LEASH-071
**Blocks**: LEASH-034, LEASH-082, LEASH-128
**Updated**: 2026-09-23

## Description
Wrap the primary reader: 1 s timeout, regex fallback marked 'model unavailable', circuit opens after repeated failures.

## Business Value
Predictable answers when the model fails, as the brief requires.

## Acceptance Criteria
- [x] A slow reader returns regex facts after 1 s.
- [x] Three consecutive failures open the circuit for 60 s.
- [x] Facts always record which reader produced them.
- [x] Applies DEC-009: model unavailability is information only; missing required facts follow the uncertainty policy; a definite regex injection always adds caution.
- [x] Merge: model output can add facts or warnings, never erase a deterministic warning, never turn 'missing' into a pass.

## Technical Approach
`adapters/fallback_reader.py`.

### Dependencies
- Needs LEASH-071.
- Blocks LEASH-034.
- Blocks LEASH-082.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_slow_reader_falls_back_after_one_second`.

## Related Files
- `solution/engine/src/leash/adapters/fallback_reader.py`
- `solution/engine/tests/adapters/test_fallback_reader.py`

## Out of scope
- Laya itself (LEASH-082).

## Review log

### 2026-09-23 — independent agent review
- [x] met — slow reader abandoned after 1.000 s → regex facts marked model unavailable; timeout capped by the budget; raise / None / non-Facts all fall back.
- [x] met — three consecutive failures open the circuit for 60 s (injected clock: open at 59.999 s, trial at 60 s, failed trial reopens, success closes).
- [x] met — facts always name the reader ("regex" on every fallback path, "laya+regex" on merge).
- [x] met — model unavailability is information only; model-only sizes/returns stay missing; regex injection survives merge and fallback.
- [ ] not met — criterion 5: fuzzing 1.4 M combinations found 30,081 merged verdicts less strict than regex alone, all from `addon_lines` under "nothing extra" (model flags the requested line too → basket treats every line as flagged → decline became approve).
- Side issues: an exhausted budget counted as a model failure (could open the circuit); half-open let every concurrent caller through.
Verdict: returned to in-progress. Fix: merged Facts carry `deterministic`; `decide()` never returns a verdict less strict than the deterministic facts give (DEC-009's verdict guard, independent of any rule's quirks). No time left is not a failure. Half-open allows a single trial call. New tests for each; 497 pass; mypy clean.

### 2026-09-23 — independent agent review (round 2)
- [x] met — criteria 1–4; exhausted budget no longer counts; half-open admits exactly one trial (20 threads on a barrier).
- [ ] not met — criterion 5, explanation only: 1.5 M fuzz cases gave 0 looser verdicts, but the guard returned one whole Decision, so on a verdict tie a deterministic `unrequested_addon` could vanish from the reasons (4,404 cases), and on fallback the model's added warning was dropped.
- Remark: a budget-cut timeout (0.001 s left) still counted as a model failure.
Verdict: returned to in-progress. Fix: with merged facts, `decide()` uses the merged checks plus every deterministic finding (a merged pass for a flagged key is dropped); the verdict is `combine()` of that set, so it is never less strict than the deterministic verdict and every finding from both readers stays in the explanation. A timeout counts as a failure only when the model had its full timeout or failed itself. Tests `test_merged_explanation_keeps_every_finding_from_both_readers`, `test_a_budget_cut_timeout_is_not_a_model_failure`; 533 pass; mypy clean.

### 2026-09-23 — independent agent review (round 3)
- [x] met — 1 s timeout (1.000–1.001 s measured); raise / non-Facts fall back.
- [x] met — circuit: three genuine timeouts or failures open it for 60 s; budget-cut timeouts don't count; half-open single trial; a budget-cut trial releases the slot without reopening.
- [x] met — facts always name the reader.
- [x] met — DEC-009: unavailability is information only; model-only facts stay missing; injection and oversized text survive merge and fallback.
- [x] met — merge: 2,000,000 fuzz cases, 0 violations of (a) no looser verdict, (b) every deterministic finding kept, (c) every model-added finding kept, (d) no merged pass for a flagged check, (e) explain() consistent. The fuzz was shown to catch the round-1/2 bugs with the guard removed (345 looser verdicts, 6,722 lost codes in 100k).
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
